#!/usr/bin/env python3
"""Locate template-like academic prose patterns; never infer authorship."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PatternSpec = tuple[str, str, str, re.Pattern[str]]

PATTERNS: tuple[PatternSpec, ...] = (
    ("chatbot-residue", "high", "Remove assistant-facing wrapper text.",
     re.compile(r"\b(?:great question|i hope this helps|would you like me to|let me know if you(?:'d| would) like)\b", re.I)),
    ("formulaic-opener", "review", "Replace generic scene-setting with the paper's concrete problem.",
     re.compile(r"\b(?:in recent years|with the rapid development of|despite recent advances)\b", re.I)),
    ("boilerplate-emphasis", "review", "State the claim directly instead of announcing importance.",
     re.compile(r"\b(?:it is worth noting that|it should be emphasized that|notably|importantly)\b", re.I)),
    ("significance-inflation", "review", "Tie significance to a supplied result or remove the inflation.",
     re.compile(r"\b(?:paves? the way|opens? new avenues?|sheds? light on|paradigm shift|revolutioni[sz]e|of paramount importance|bridges? the gap)\b", re.I)),
    ("negative-parallelism", "review", "Keep this contrast only if both halves carry real information.",
     re.compile(r"\bnot\s+(?:just|only|merely)\b.{0,100}?\bbut\b", re.I)),
    ("stacked-hedges", "review", "Keep only the qualifier required by the evidence.",
     re.compile(r"\b(?:could potentially|may possibly|might arguably|could conceivably|may potentially)\b", re.I)),
    ("copula-avoidance", "review", "Prefer a precise simple verb when the longer phrase adds nothing.",
     re.compile(r"\b(?:serves as|functions as|stands as)\b", re.I)),
    ("vague-authority", "review", "Name and cite the supporting source or keep the claim bounded.",
     re.compile(r"\b(?:experts (?:argue|believe|suggest)|studies have shown|the literature suggests)\b", re.I)),
    ("shallow-ing-tail", "review", "Verify that the trailing interpretation is supported, not decorative.",
     re.compile(r",\s+(?:highlighting|underscoring|showcasing|emphasizing)\b", re.I)),
)

WATCH_WORDS = re.compile(
    r"\b(?:delve|tapestry|pivotal|groundbreaking|multifaceted|intricate|"
    r"seamless|transformative|crucial|landscape|testament|underscore|showcase)\b",
    re.I,
)
TRANSITIONS = {"additionally", "furthermore", "moreover", "notably", "importantly"}
FENCE = re.compile(r"(?ms)^\s*```.*?^\s*```\s*$|^\s*~~~.*?^\s*~~~\s*$")
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _excerpt(text: str, start: int, end: int, limit: int = 150) -> str:
    value = " ".join(text[start:end].split())
    return value if len(value) <= limit else value[:limit - 1] + "…"


def _paragraphs(text: str) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for match in re.finditer(r"(?ms)(?:^|\n\s*\n)(\S.*?)(?=\n\s*\n|\Z)", text):
        body = match.group(1)
        if body.lstrip().startswith((">", "#", "|")):
            continue
        result.append((match.start(1), body))
    return result


def lint_text(source: str) -> list[dict[str, Any]]:
    text = FENCE.sub(lambda match: "\n" * match.group(0).count("\n"), source)
    issues: list[dict[str, Any]] = []

    for code, severity, message, pattern in PATTERNS:
        for match in pattern.finditer(text):
            issues.append({
                "code": code,
                "severity": severity,
                "line": _line_number(text, match.start()),
                "excerpt": _excerpt(text, match.start(), match.end()),
                "message": message,
            })

    for start, paragraph in _paragraphs(text):
        watch_hits = [match.group(0).lower() for match in WATCH_WORDS.finditer(paragraph)]
        if len(set(watch_hits)) >= 3:
            issues.append({
                "code": "watch-word-cluster",
                "severity": "review",
                "line": _line_number(text, start),
                "excerpt": ", ".join(dict.fromkeys(watch_hits)),
                "message": "Review the cluster in context; individual technical uses are allowed.",
            })

        sentences = [sentence.strip() for sentence in SENTENCE.split(paragraph) if sentence.strip()]
        transition_run = 0
        for sentence in sentences:
            words = WORD.findall(sentence)
            first = words[0].lower() if words else ""
            transition_run = transition_run + 1 if first in TRANSITIONS else 0
            if transition_run == 2:
                issues.append({
                    "code": "transition-run",
                    "severity": "review",
                    "line": _line_number(text, start + paragraph.find(sentence)),
                    "excerpt": _excerpt(sentence, 0, len(sentence)),
                    "message": "Let the argument carry the link instead of repeating transition openers.",
                })

        opening_run = 1
        previous: tuple[str, ...] | None = None
        for sentence in sentences:
            opening = tuple(word.lower() for word in WORD.findall(sentence)[:2])
            opening_run = opening_run + 1 if opening and opening == previous else 1
            if opening_run == 3:
                issues.append({
                    "code": "repeated-opening",
                    "severity": "review",
                    "line": _line_number(text, start + paragraph.find(sentence)),
                    "excerpt": " ".join(opening),
                    "message": "Review three consecutive identical sentence openings; preserve deliberate repetition.",
                })
            previous = opening

    return sorted(issues, key=lambda item: (item["line"], item["code"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, help="UTF-8 text/Markdown/LaTeX file; omit for stdin")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    try:
        source = args.path.read_text(encoding="utf-8-sig") if args.path else sys.stdin.read()
    except (OSError, UnicodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    issues = lint_text(source)
    if args.as_json:
        print(json.dumps({
            "status": "REVIEW" if issues else "PASS",
            "issues": issues,
            "scope": "Writing-pattern hints only; no AI-authorship inference or detector score.",
        }, ensure_ascii=False, indent=2))
    elif issues:
        for item in issues:
            print(f"{item['line']}:{item['code']}:{item['severity']}: {item['excerpt']}")
    else:
        print("PASS|no configured prose-pattern findings")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
