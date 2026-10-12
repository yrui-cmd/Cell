#!/usr/bin/env python3
"""Validate the auditable structure of evidence-synthesis topic candidates."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any


RELATIONSHIPS = {"parallel", "subtopic", "overlap"}
STATUSES = {"pass", "conditional", "fail"}
ACCESS_LEVELS = {"metadata", "abstract", "excerpt", "fulltext"}
DELTA_FIELDS = {
    "prior_synthesis",
    "changed_judgment",
    "synthesis_operation",
    "visible_artifact",
    "boundaries",
    "negating_evidence",
}
OPEN_ITEM_FIELDS = {"issue", "affects", "allowed_now", "fallback"}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("schema_version") != "synthesis-1.0":
        errors.append("schema_version must be synthesis-1.0")

    run = data.get("run")
    if not isinstance(run, dict):
        errors.append("run must be an object")
    else:
        try:
            date.fromisoformat(run.get("as_of", ""))
        except (TypeError, ValueError):
            errors.append("run.as_of must be an ISO date")
        if run.get("mode") not in {"live", "offline", "replay", "synthetic"}:
            errors.append("run.mode is invalid")
        if "final_checked_at" not in run:
            errors.append("run.final_checked_at must be recorded, using null when not completed")

    candidates = data.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 5:
        errors.append("candidates must contain exactly five explicit slots")
        return errors

    ids = [candidate.get("id") for candidate in candidates if isinstance(candidate, dict)]
    if len(ids) != 5 or any(not _text(item) for item in ids) or len(set(ids)) != 5:
        errors.append("candidate IDs must be five unique non-empty strings")

    for index, candidate in enumerate(candidates, start=1):
        prefix = f"candidates[{index}]"
        if not isinstance(candidate, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for field in ("title", "question"):
            if not _text(candidate.get(field)):
                errors.append(f"{prefix}.{field} must be non-empty")
        if candidate.get("relationship_to_primary_candidate") not in RELATIONSHIPS:
            errors.append(f"{prefix}.relationship_to_primary_candidate is invalid")
        if candidate.get("status") not in STATUSES:
            errors.append(f"{prefix}.status is invalid")

        nearest = candidate.get("nearest_reviews")
        if not isinstance(nearest, list) or not nearest:
            errors.append(f"{prefix}.nearest_reviews must contain an actual comparison")
        else:
            for row_index, row in enumerate(nearest, start=1):
                row_prefix = f"{prefix}.nearest_reviews[{row_index}]"
                if not isinstance(row, dict):
                    errors.append(f"{row_prefix} must be an object")
                    continue
                for field in ("source_id", "prior_synthesis", "comparison_result"):
                    if not _text(row.get(field)):
                        errors.append(f"{row_prefix}.{field} must be non-empty")
                if row.get("access") not in ACCESS_LEVELS:
                    errors.append(f"{row_prefix}.access is invalid")

        primary = candidate.get("primary_evidence")
        if not isinstance(primary, list) or not primary:
            errors.append(f"{prefix}.primary_evidence must contain load-bearing evidence")
        else:
            for row_index, row in enumerate(primary, start=1):
                row_prefix = f"{prefix}.primary_evidence[{row_index}]"
                if not isinstance(row, dict):
                    errors.append(f"{row_prefix} must be an object")
                    continue
                for field in ("source_id", "role"):
                    if not _text(row.get(field)):
                        errors.append(f"{row_prefix}.{field} must be non-empty")
                if row.get("access") not in ACCESS_LEVELS:
                    errors.append(f"{row_prefix}.access is invalid")

        delta = candidate.get("synthesis_delta")
        if not isinstance(delta, dict):
            errors.append(f"{prefix}.synthesis_delta must be an object")
        else:
            for field in sorted(DELTA_FIELDS):
                if not _text(delta.get(field)):
                    errors.append(f"{prefix}.synthesis_delta.{field} must be non-empty")

        search = candidate.get("search_status")
        if not isinstance(search, dict):
            errors.append(f"{prefix}.search_status must be an object")
        else:
            for field in ("request_succeeded", "screening_sufficient", "novelty_complete"):
                if not isinstance(search.get(field), bool):
                    errors.append(f"{prefix}.search_status.{field} must be boolean")

        plan = candidate.get("evidence_plan")
        if not isinstance(plan, dict):
            errors.append(f"{prefix}.evidence_plan must be an object")
        else:
            for phase in ("P0", "P1"):
                if not _text(plan.get(phase)):
                    errors.append(f"{prefix}.evidence_plan.{phase} must be non-empty")
            if plan.get("P2") is not None and not _text(plan.get("P2")):
                errors.append(f"{prefix}.evidence_plan.P2 must be text or null")

        open_items = candidate.get("open_items")
        if not isinstance(open_items, list):
            errors.append(f"{prefix}.open_items must be an array")
        else:
            for row_index, row in enumerate(open_items, start=1):
                row_prefix = f"{prefix}.open_items[{row_index}]"
                if not isinstance(row, dict):
                    errors.append(f"{row_prefix} must be an object")
                    continue
                for field in sorted(OPEN_ITEM_FIELDS):
                    if not _text(row.get(field)):
                        errors.append(f"{row_prefix}.{field} must be non-empty")
        if candidate.get("status") == "conditional" and not open_items:
            errors.append(f"{prefix} is conditional but has no scoped open_items")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        errors = validate(data)
    except (OSError, json.JSONDecodeError) as error:
        errors = [str(error)]
    if errors:
        for error in errors:
            print("ERROR: " + error, file=sys.stderr)
        return 2
    print("SYNTHESIS_CONTRACT_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
