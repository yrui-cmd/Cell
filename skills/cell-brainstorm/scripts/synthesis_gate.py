#!/usr/bin/env python3
"""Offline consistency contract for evidence-synthesis candidates, not semantic certification."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

RELATIONSHIPS = {"parallel", "subtopic", "overlap"}
STATUSES = {"pass", "conditional", "fail", "vacant"}
ACCESS_LEVELS = {"metadata", "abstract", "excerpt", "fulltext"}
DELTA_FIELDS = {"prior_synthesis", "changed_judgment", "synthesis_operation", "visible_artifact", "boundaries", "negating_evidence"}
OPEN_ITEM_FIELDS = {"issue", "affects", "allowed_now", "fallback"}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def identities(row: dict) -> set[str]:
    keys = {"id:" + row["source_id"].strip()}
    if _text(row.get("article_id")):
        keys.add("article:" + row["article_id"].strip().casefold())
    if _text(row.get("doi")):
        doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", unquote(row["doi"]).strip(), flags=re.I)
        keys.add("doi:" + doi.casefold().rstrip(".,;"))
    if _text(row.get("url")):
        try:
            url = urlsplit(row['url'])
            if url.hostname and url.hostname.casefold() in {'doi.org', 'dx.doi.org'}:
                keys.add('doi:' + unquote(url.path).lstrip('/').casefold().rstrip('.,;'))
        except ValueError:
            pass  # The registry URL validator reports malformed URLs separately.
    return keys


def validate(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    errors = []
    version = data.get("schema_version")
    if not isinstance(version, str) or version not in {"synthesis-1.0", "synthesis-1.1"}:
        errors.append("schema_version must be synthesis-1.0 or synthesis-1.1")
    modern = version == "synthesis-1.1"
    run = data.get("run")
    fresh = True
    if not isinstance(run, dict):
        errors.append("run must be an object")
    else:
        try:
            date.fromisoformat(run.get("as_of", ""))
        except (TypeError, ValueError):
            errors.append("run.as_of must be an ISO date")
        if not isinstance(run.get("mode"), str) or run.get("mode") not in {"live", "offline", "replay", "synthetic"}:
            errors.append("run.mode is invalid")
        if "final_checked_at" not in run:
            errors.append("run.final_checked_at must be recorded, using null when not completed")
        if modern and run.get("mode") == "live":
            fresh = False
            try:
                created = datetime.fromisoformat(run.get("report_created_at", "").replace("Z", "+00:00"))
                if created.tzinfo is None:
                    raise ValueError("timezone required")
                if created.date().isoformat() != run.get("as_of"):
                    errors.append("live as_of must match report_created_at date")
                if run.get("final_checked_at") is not None:
                    checked = datetime.fromisoformat(run["final_checked_at"].replace("Z", "+00:00"))
                    if checked.tzinfo is None:
                        raise ValueError("timezone required")
                    hours = (created - checked).total_seconds() / 3600
                    if hours < 0:
                        errors.append("final_checked_at cannot be after report_created_at")
                    fresh = 0 <= hours <= 24
            except (AttributeError, TypeError, ValueError):
                errors.append("live timestamps must be valid ISO datetimes with timezones")

    source_map = {}
    if modern:
        brief = data.get("brief")
        if not isinstance(brief, dict) or not _text(brief.get("research_content")):
            errors.append("brief.research_content must be non-empty")
        sources = data.get("sources")
        if not isinstance(sources, list):
            errors.append("sources must be an array (may be empty for a vacant report)")
        else:
            for row in sources:
                if not isinstance(row, dict) or not _text(row.get("id")):
                    errors.append("each source must have a non-empty id")
                    continue
                sid = row["id"]
                if sid in source_map:
                    errors.append("source IDs must be unique")
                source_map[sid] = row
                if not _text(row.get("title")) or not isinstance(row.get("kind"), str) or row.get("kind") not in {"review", "original_research"}:
                    errors.append(f"source {sid} requires title and kind=review/original_research")
                url = row.get("url")
                try:
                    parsed = urlsplit(url) if isinstance(url, str) else None
                except ValueError:
                    parsed = None
                if parsed is None or parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    errors.append(f"source {sid} requires a source HTTP(S) URL")

    candidates = data.get("candidates")
    if not isinstance(candidates, list) or len(candidates) > 5:
        return errors + ["candidates must contain zero to five entries; renderer supplies vacant slots"]
    ids = [c.get("id") for c in candidates if isinstance(c, dict)]
    if len(ids) != len(candidates) or any(not _text(x) for x in ids):
        errors.append("candidate IDs must be unique non-empty strings")
    elif len(set(ids)) != len(ids):
        errors.append("candidate IDs must be unique non-empty strings")

    for index, c in enumerate(candidates, 1):
        prefix = f"candidates[{index}]"
        if not isinstance(c, dict):
            errors.append(f"{prefix} must be an object")
            continue
        status = c.get("status")
        if not isinstance(status, str) or status not in STATUSES:
            errors.append(f"{prefix}.status is invalid")
            continue
        if status == "vacant":
            if not _text(c.get("reason")):
                errors.append(f"{prefix}.reason must explain the vacant slot")
            continue
        for field in ("title", "question"):
            if not _text(c.get(field)):
                errors.append(f"{prefix}.{field} must be non-empty")
        relation = c.get("relationship_to_primary_candidate")
        if not isinstance(relation, str) or relation not in RELATIONSHIPS:
            errors.append(f"{prefix}.relationship_to_primary_candidate is invalid")

        role_keys = []
        role_ids = set()
        nearest_ids = set()
        for field, required, kind in [("nearest_reviews", ("source_id", "prior_synthesis", "comparison_result"), "review"),
                                      ("primary_evidence", ("source_id", "role"), "original_research")]:
            rows = c.get(field)
            keys = set()
            if not isinstance(rows, list) or (status == "pass" and not rows):
                errors.append(f"{prefix}.{field} must contain an actual comparison or load-bearing evidence")
                rows = []
            for n, row in enumerate(rows, 1):
                label = f"{prefix}.{field}[{n}]"
                if not isinstance(row, dict):
                    errors.append(f"{label} must be an object")
                    continue
                for key in required:
                    if not _text(row.get(key)):
                        errors.append(f"{label}.{key} must be non-empty")
                access = row.get("access")
                if not isinstance(access, str) or access not in ACCESS_LEVELS:
                    errors.append(f"{label}.access is invalid")
                sid = row.get("source_id")
                if not _text(sid):
                    continue
                role_ids.add(sid)
                if field == "nearest_reviews":
                    nearest_ids.add(sid)
                registered = source_map.get(sid, {})
                if modern and (not registered or registered.get("kind") != kind):
                    errors.append(f"{label} must reference a registered {kind} source")
                keys.update(identities(row))
                if registered:
                    keys.update(identities({**registered, 'source_id': sid}))
            role_keys.append(keys)
        if role_keys[0] & role_keys[1]:
            errors.append(f"{prefix}: nearest_reviews and primary_evidence must use distinct article identities")

        delta = c.get("synthesis_delta")
        if not isinstance(delta, dict):
            errors.append(f"{prefix}.synthesis_delta must be an object")
        else:
            for field in sorted(DELTA_FIELDS):
                if not _text(delta.get(field)):
                    errors.append(f"{prefix}.synthesis_delta.{field} must be non-empty")
        search = c.get("search_status")
        incomplete = False
        if not isinstance(search, dict):
            errors.append(f"{prefix}.search_status must be an object")
        else:
            for field in ("request_succeeded", "screening_sufficient", "novelty_complete"):
                if type(search.get(field)) is not bool:
                    errors.append(f"{prefix}.search_status.{field} must be boolean")
                incomplete |= search.get(field) is not True
        if status == "pass" and (incomplete or not fresh):
            errors.append(f"{prefix}: incomplete search/freshness cannot have status=pass")

        plan = c.get("evidence_plan")
        if not isinstance(plan, dict):
            errors.append(f"{prefix}.evidence_plan must be an object")
        else:
            for phase in ("P0", "P1"):
                if not _text(plan.get(phase)):
                    errors.append(f"{prefix}.evidence_plan.{phase} must be non-empty")
            if plan.get("P2") is not None and not _text(plan.get("P2")):
                errors.append(f"{prefix}.evidence_plan.P2 must be text or null")
        items = c.get("open_items")
        if not isinstance(items, list):
            errors.append(f"{prefix}.open_items must be an array")
        else:
            for row in items:
                if not isinstance(row, dict) or any(not _text(row.get(k)) for k in OPEN_ITEM_FIELDS):
                    errors.append(f"{prefix}.open_items requires issue, affects, allowed_now and fallback")
        if status == "conditional" and not items:
            errors.append(f"{prefix} is conditional but has no scoped open_items")
        if status == "pass" and items:
            errors.append(f"{prefix}: unresolved open_items cannot have status=pass")
        if modern and status in {"pass", "conditional"}:
            from report_style import check_sections
            sections = c.get("report_sections")
            try:
                if not isinstance(sections, dict) or any(not isinstance(v, dict) or not _text(v.get("text")) or not isinstance(v.get("source_ids"), list) or any(not _text(sid) for sid in v["source_ids"]) for v in sections.values()):
                    raise ValueError("report_sections requires four text/source_ids objects")
                check_sections(sections, role_ids & source_map.keys(), nearest_ids)
            except (KeyError, TypeError, ValueError) as exc:
                errors.append(f"{prefix}: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    try:
        errors = validate(json.loads(args.input.read_text(encoding="utf-8-sig")))
    except (OSError, UnicodeError, ValueError) as exc:
        errors = [str(exc)]
    if errors:
        for error in errors:
            print("ERROR: " + error, file=sys.stderr)
        return 2
    print("SYNTHESIS_CONTRACT_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
