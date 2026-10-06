#!/usr/bin/env python3
"""Compare mechanically protected manuscript tokens before and after editing."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

TOKEN_PATTERNS: dict[str, re.Pattern[str]] = {
    "number": re.compile(r"(?<![A-Za-z_])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?%?"),
    "quantity": re.compile(r"(?<![A-Za-z_])[-+]?(?:\d+(?:\.\d+)?)(?:\s*)(?:%|°C|K|ms|s|min|h|Hz|kHz|MHz|mm|cm|m|km|µm|nm|µL|mL|L|µg|mg|g|kg|Pa|kPa|MPa)\b", re.I),
    "latex_reference": re.compile(r"\\(?:cite\w*|ref|eqref|autoref)\{[^{}]+\}"),
    "numeric_citation": re.compile(r"\[(?:\d+[a-z]?(?:\s*[-–,;]\s*\d+[a-z]?)*?)\]"),
    "author_year": re.compile(r"\([A-Z][A-Za-z'’-]+(?:\s+et\s+al\.)?,?\s+(?:19|20)\d{2}[a-z]?(?:;[^()]*)?\)"),
    "cross_reference": re.compile(r"\b(?:Fig(?:ure)?|Table|Eq(?:uation)?|Section|Appendix|Supplementary\s+(?:Fig(?:ure)?|Table))\.?\s+[A-Z]?[S]?\d+(?:[a-z]|\.\d+)*", re.I),
    "doi_or_url": re.compile(r"https?://[^\s)>\]}]+|\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I),
    "latex_math": re.compile(r"(?s)(?<!\\)\$\$.*?(?<!\\)\$\$|(?<!\\)\$[^\n$]+?(?<!\\)\$|\\\([^\n]+?\\\)|\\\[.*?\\\]"),
    "quoted_text": re.compile(r"“[^”\n]{1,300}”|\"[^\"\n]{1,300}\""),
}


def _normalize(category: str, value: str) -> str:
    value = " ".join(value.split())
    return value.casefold() if category in {"cross_reference", "doi_or_url"} else value


def extract(text: str) -> dict[str, Counter[str]]:
    return {
        category: Counter(_normalize(category, match.group(0))
                          for match in pattern.finditer(text))
        for category, pattern in TOKEN_PATTERNS.items()
    }


def compare(before: str, after: str) -> dict[str, Any]:
    original = extract(before)
    revised = extract(after)
    differences: list[dict[str, Any]] = []
    for category in TOKEN_PATTERNS:
        missing = list((original[category] - revised[category]).elements())
        added = list((revised[category] - original[category]).elements())
        if missing or added:
            differences.append({"category": category, "missing": missing, "added": added})
    return {
        "status": "PASS" if not differences else "REVIEW",
        "differences": differences,
        "scope": (
            "Mechanical token comparison only; review negation, attribution, causality, "
            "uncertainty, comparison direction, and study scope semantically."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()
    try:
        result = compare(
            args.before.read_text(encoding="utf-8-sig"),
            args.after.read_text(encoding="utf-8-sig"),
        )
    except (OSError, UnicodeError) as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)}, ensure_ascii=False),
              file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
