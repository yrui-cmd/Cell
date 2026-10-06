#!/usr/bin/env python3
"""Validate an explicit, task-local author style profile."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

MODES = {"language_edit", "logic_edit", "audit", "translation_edit", "comprehensive_edit"}
SOURCES = {"explicit", "observed"}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _text_list(value: Any) -> bool:
    return isinstance(value, list) and all(_text(item) for item in value)


def validate(profile: Any) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(profile, dict):
        return {"status": "BLOCKED", "errors": ["Profile root must be an object."],
                "warnings": []}

    if profile.get("schema_version") != 1:
        errors.append("schema_version must be 1.")
    if not _text(profile.get("manuscript_id")):
        errors.append("manuscript_id must be nonempty.")
    if profile.get("default_edit_mode") not in MODES:
        errors.append("default_edit_mode is invalid.")

    preferences = profile.get("preferences")
    if not isinstance(preferences, dict) or not preferences:
        errors.append("preferences must be a nonempty object.")
    elif any(not _text(key) or not (_text(value) or _text_list(value))
             for key, value in preferences.items()):
        errors.append("preferences values must be text or text lists.")

    locked_terms = profile.get("locked_terms")
    if not isinstance(locked_terms, list):
        errors.append("locked_terms must be a list.")
        locked_terms = []
    preferred_terms: list[str] = []
    for index, item in enumerate(locked_terms):
        if not isinstance(item, dict) or not _text(item.get("preferred")) \
                or not _text_list(item.get("avoid")) or not _text(item.get("scope")):
            errors.append(f"locked_terms[{index}] needs preferred, avoid, and scope.")
            continue
        preferred_terms.append(item["preferred"].casefold())
        if item["preferred"].casefold() in {value.casefold() for value in item["avoid"]}:
            errors.append(f"locked_terms[{index}] cannot avoid its preferred term.")
    if len(preferred_terms) != len(set(preferred_terms)):
        errors.append("locked_terms preferred values must be unique.")

    for key in ("disfavored_phrases", "protected_passages"):
        if not _text_list(profile.get(key)):
            errors.append(f"{key} must be a string list.")

    rules = profile.get("confirmed_rules")
    if not isinstance(rules, list):
        errors.append("confirmed_rules must be a list.")
        rules = []
    for index, item in enumerate(rules):
        if not isinstance(item, dict) or not _text(item.get("rule")) \
                or item.get("source") not in SOURCES or not _text(item.get("scope")):
            errors.append(
                f"confirmed_rules[{index}] needs rule, source explicit/observed, and scope."
            )

    if not rules and not locked_terms and not profile.get("disfavored_phrases"):
        warnings.append("The profile contains no confirmed reusable author preference yet.")

    return {
        "status": "PASS" if not errors else "BLOCKED",
        "errors": errors,
        "warnings": warnings,
        "scope": "Profile structure only; manuscript science and prose still need human review.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    args = parser.parse_args()
    try:
        profile = json.loads(args.profile.read_text(encoding="utf-8-sig"))
        result = validate(profile)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)},
                         ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
