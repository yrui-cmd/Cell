#!/usr/bin/env python3
"""Local review workspace and record-consistency audit. Python 3.10+, no network.

This module does NOT retrieve papers, authenticate reading, assess semantic
support, or certify scientific quality. Host-populated fields are attestations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
CHECKS = (
    "question_answered", "added_value_explained", "main_claims_traced",
    "counterevidence_addressed", "design_limits_respected",
    "citations_semantically_checked", "review_type_honest",
    "manuscript_complete", "benchmark_checked_or_disclosed", "limitations_disclosed",
)
FORMAL_CHECKS = (
    "protocol_documented", "search_complete", "counts_reconciled",
    "reviewer_setup_disclosed", "quality_appraisal_applicable_and_addressed",
    "synthesis_reported", "protocol_deviations_disclosed",
)
READ_FLAGS = {
    "abstract": "abstract_read", "full_text": "full_text_read",
    "figure": "key_figures_checked", "supplement": "supplements_checked",
}
KINDS = {"descriptive", "association", "intervention", "mechanism", "prediction", "synthesis", "hypothesis"}
REVIEW_TYPES = {"critical_narrative", "scoping", "systematic", "meta_analysis"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement in the same directory; originals are never input files.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def one_of(value: Any, values: set[str] | dict[str, Any]) -> bool:
    return isinstance(value, str) and value in values


def valid_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text)


def init_review(topic: str, root: Path, language: str = "zh-CN") -> Path:
    if not topic.strip():
        raise ValueError("Topic must not be empty.")
    # Exclusive mkdir prevents overwriting even when two calls share a timestamp.
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run = root / stamp
    run.mkdir(exist_ok=False)
    work = run / "_work"
    (work / "sources").mkdir(parents=True)
    protocol = read_json(SKILL_ROOT / "templates" / "protocol.json")
    protocol.update(topic=topic.strip(), language=language, created_at=now_iso())
    protocol["capabilities"]["local_execution"] = True
    write_json(work / "protocol.json", protocol)
    write_json(work / "evidence.json", read_json(SKILL_ROOT / "templates" / "evidence.json"))
    (work / "notes.md").write_text(
        "# 内部工作记录\n\n当前阶段：第1步\n\n"
        "记录问题、文章价值、主线、尚缺证据和下一步，不存冗长思维过程。\n"
        "_work/review.md 与 review.docx 尚未生成；不得把本目录当成已完成的综述。\n", encoding="utf-8"
    )
    return run


def citation_numbers(text: str) -> set[int]:
    """Read [1], [1, 2], [1–3]; ignore Markdown links, footnotes and huge ranges."""
    numbers: set[int] = set()
    for match in re.finditer(r"(?<!!)\[(\d+(?:\s*[,，\-–]\s*\d+)*)\](?!\s*\()", text):
        for part in re.split(r"[,，]", match.group(1)):
            ends = re.split(r"[\-–]", part.strip())
            if len(ends) == 1:
                numbers.add(int(ends[0]))
            elif len(ends) == 2:
                a, b = map(int, ends)
                if 0 < a <= b and b - a <= 10000:
                    numbers.update(range(a, b + 1))
    return numbers


def audit_review(run_dir: Path) -> dict[str, Any]:
    run = run_dir.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    counts: dict[str, int] = {}

    def error(message: str) -> None:
        errors.append(message)

    def warning(message: str) -> None:
        warnings.append(message)

    def obj(value: Any, label: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            error(f"{label}: expected object")
            return {}
        return value

    def rows(value: Any, label: str) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            error(f"{label}: expected array")
            return []
        result = []
        for i, row in enumerate(value):
            if isinstance(row, dict):
                result.append(row)
            else:
                error(f"{label}[{i}]: expected object")
        return result

    def source_check(value: Any, label: str, states: set[str]) -> dict[str, Any]:
        data = obj(value, label)
        if not one_of(data.get("status"), states):
            error(f"{label}: unchecked or invalid status")
        if not has_text(data.get("source")) or not valid_date(data.get("checked_at")):
            error(f"{label}: actual source and ISO check date required")
        return data

    def report() -> dict[str, Any]:
        return {
            "status": "RECORDS_CONSISTENT" if not errors else "NEEDS_REVISION",
            "checked_at": now_iso(), "run_dir": str(run),
            "errors": errors, "warnings": warnings, "counts": counts,
            "scope": "Local record consistency only; no network or scientific/semantic verification. Final DOCX and >=30 article checks require delivery_gate.py.",
            "scientific_quality_certified": False,
            "independent_peer_review_performed": False,
        }

    try:
        protocol = read_json(run / "_work" / "protocol.json")
        ledger = read_json(run / "_work" / "evidence.json")
    except (OSError, ValueError) as exc:
        error(str(exc))
        return report()
    if protocol.get("schema_version") != "1.0" or ledger.get("schema_version") != "1.0":
        error("Unsupported or missing schema_version (expected 1.0)")
    for key in ("topic", "question", "added_value"):
        if not has_text(protocol.get(key)):
            error(f"protocol.{key}: required")
    review_type = protocol.get("review_type")
    if not one_of(review_type, REVIEW_TYPES):
        error("protocol.review_type: invalid")
    manuscript = run / "_work" / "review.md"
    try:
        text = manuscript.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        text = ""
        error(f"review.md: {exc}")
    if not text.strip():
        error("review.md is empty or absent; a plan is not a completed review")
    if re.search(r"\{\{[^{}]+\}\}|\bTODO\b|\bTBD\b|\[待(?:补充|填写|核验)[^\]]*\]", text):
        error("review.md contains unresolved template placeholders")
    parts = re.split(r"(?im)^##\s+(?:参考文献|References|Bibliography)\s*$", text, maxsplit=1)
    body, bibliography = parts[0], parts[1] if len(parts) == 2 else ""
    normalized_body = normalize(body)

    issues = rows(ledger.get("issues"), "issues")
    open_types: set[str] = set()
    for issue in issues:
        label = f"issue {issue.get('id', '?')}"
        if not one_of(issue.get("status"), {"open", "resolved"}):
            error(f"{label}: invalid status")
        if not one_of(issue.get("impact"), {"core", "scope", "internal"}):
            error(f"{label}: invalid impact")
        if issue.get("status") == "open":
            if isinstance(issue.get("type"), str):
                open_types.add(issue["type"])
            if issue.get("impact") != "internal":
                disclosure = issue.get("manuscript_disclosure")
                if not has_text(disclosure) or normalize(disclosure) not in normalized_body:
                    error(f"{label}: unresolved limitation not disclosed in manuscript")
            if issue.get("impact") == "core":
                error(f"{label}: unresolved core evidence/method issue")
            elif issue.get("impact") == "scope":
                warning(f"{label}: disclosed scope limitation remains")

    searches = rows(ledger.get("searches"), "searches")
    counts["searches"] = len(searches)
    usable_searches = 0
    for q in searches:
        label = f"search {q.get('id', '?')}"
        for key in ("source", "query", "purpose", "result_locator"):
            if not has_text(q.get(key)):
                error(f"{label}: {key} required")
        if not valid_date(q.get("searched_at")):
            error(f"{label}: actual searched_at date required")
        if not one_of(q.get("status"), {"completed", "partial", "failed"}):
            error(f"{label}: invalid status")
        if one_of(q.get("status"), {"completed", "partial"}):
            usable_searches += 1
        for key in ("reported_count", "examined_count", "retrieved_count"):
            value = q.get(key)
            if value is not None and (type(value) is not int or value < 0):
                error(f"{label}: {key} must be nonnegative integer or null")
    if not usable_searches and "search_unavailable" not in open_types:
        error("No completed/partial search or disclosed search_unavailable issue")
    if usable_searches and not valid_date(protocol.get("last_search_date")):
        error("protocol.last_search_date must record the actual search date")

    records = rows(ledger.get("records"), "records")
    counts["records"] = len(records)
    record_map: dict[str, dict[str, Any]] = {}
    numbered: dict[int, dict[str, Any]] = {}
    for r in records:
        rid = r.get("id")
        if not isinstance(rid, str) or not re.fullmatch(r"R\d+", rid):
            error("record: invalid id; use R followed by digits")
            continue
        if rid in record_map:
            error(f"{rid}: duplicate record id")
        record_map[rid] = r
        if not has_text(r.get("study_id")):
            error(f"{rid}: study_id required")
        screening = r.get("screening_status")
        if not one_of(screening, {"included", "excluded", "awaiting_full_text", "context_only"}):
            error(f"{rid}: invalid screening_status")
        if not has_text(r.get("screening_reason")):
            error(f"{rid}: screening_reason required")
        reading = obj(r.get("reading"), f"{rid}.reading")
        for flag in READ_FLAGS.values():
            if type(reading.get(flag)) is not bool:
                error(f"{rid}.reading.{flag}: explicit boolean required")
        if screening == "awaiting_full_text" and reading.get("full_text_read") is True:
            error(f"{rid}: awaiting_full_text conflicts with full_text_read")
        num = r.get("citation_number")
        if num is None:
            continue
        if type(num) is not int or num < 1:
            error(f"{rid}: citation_number must be positive integer or null")
            continue
        if num in numbered:
            error(f"{rid}: duplicate citation_number {num}")
        numbered[num] = r
        for key in ("title", "identifier"):
            if not has_text(r.get(key)):
                error(f"{rid}: cited reference requires {key}")
        if not isinstance(r.get("authors"), list):
            error(f"{rid}: authors must be a list; use an empty list only if genuinely unavailable")
        if r.get("year") is not None and type(r.get("year")) is not int:
            error(f"{rid}: year must be integer or null")
        metadata = source_check(r.get("metadata_check"), f"{rid}.metadata_check", {"verified"})
        fields = metadata.get("fields_checked")
        if not isinstance(fields, list) or not all(isinstance(x, str) for x in fields):
            error(f"{rid}: metadata fields_checked must be a list of field names")
        elif not {"title", "authors", "year", "identifier"}.issubset(fields):
            error(f"{rid}: metadata identity fields have not all been checked")
        pub = source_check(r.get("publication_check"), f"{rid}.publication_check", {"checked", "limited"})
        if not one_of(pub.get("outcome"), {"no_notice_found", "notice_found", "unclear"}):
            error(f"{rid}: publication_check requires an explicit outcome")
        if pub.get("status") == "limited" and "publication_status_limited" not in open_types:
            error(f"{rid}: limited publication check needs a disclosed issue")
        if not one_of(r.get("publication_status"), {"published", "preprint", "corrected", "retracted", "expression_of_concern", "unknown"}):
            error(f"{rid}: invalid publication_status")
        if one_of(r.get("publication_status"), {"preprint", "retracted", "expression_of_concern", "unknown"}):
            warning(f"{rid}: host must ensure publication status is explicit in the relevant prose")
    counts["cited_records"] = len(numbered)
    if not numbered:
        error("No cited records; cannot claim a verified literature review")

    if protocol.get("citation_style") == "numeric_draft":
        if len(parts) != 2:
            error("Numeric draft requires a ## 参考文献 or ## References section")
        in_body = citation_numbers(body)
        bib_list = [int(x) for x in re.findall(r"(?m)^\s*\[(\d+)\]\s+", bibliography)]
        in_bib = set(bib_list)
        if len(bib_list) != len(in_bib):
            error("Duplicate bibliography number")
        bib_entries = {
            int(m.group(1)): m.group(2)
            for m in re.finditer(r"(?ms)^\s*\[(\d+)\]\s+(.+?)(?=^\s*\[\d+\]\s+|\Z)", bibliography)
        }
        for n, record in numbered.items():
            # This compares recorded title text, not the truth of the source identity.
            title = record.get("title")
            if n in bib_entries and has_text(title):
                canonical_title = re.sub(r"[\W_]+", "", title, flags=re.UNICODE).casefold()
                canonical_entry = re.sub(r"[\W_]+", "", bib_entries[n], flags=re.UNICODE).casefold()
                if canonical_title and canonical_title not in canonical_entry:
                    error(f"Bibliography [{n}] title differs from its ledger record")
        for n in sorted(in_body - in_bib):
            error(f"Citation [{n}] has no bibliography entry")
        for n in sorted(in_bib - in_body):
            error(f"Bibliography [{n}] is not cited in the body")
        for n in sorted((in_body | in_bib) - numbered.keys()):
            error(f"Citation [{n}] has no verified ledger record")
        for n in sorted(numbered.keys() - in_bib):
            error(f"Ledger citation [{n}] is missing from the bibliography")
        for n in sorted(numbered.keys() - in_body):
            error(f"Ledger citation [{n}] is missing from the body")
    else:
        warning("Custom citation style: numbering/bibliography matching is not programmatically checked")

    claims = rows(ledger.get("claims"), "claims")
    counts["claims"] = len(claims)
    if not claims:
        error("No claim-to-source mapping")
    seen_claims: set[str] = set()
    for claim in claims:
        cid = claim.get("id")
        if not isinstance(cid, str) or not re.fullmatch(r"C\d+", cid):
            error("claim: invalid id; use C followed by digits")
            continue
        if cid in seen_claims:
            error(f"{cid}: duplicate claim id")
        seen_claims.add(cid)
        ctext = claim.get("text")
        if not has_text(ctext) or normalize(ctext) not in normalized_body:
            error(f"{cid}: claim text does not occur in the manuscript body")
        if not one_of(claim.get("kind"), KINDS):
            error(f"{cid}: invalid evidence kind")
        if not has_text(claim.get("scope_note")):
            error(f"{cid}: scope_note required")
        if claim.get("content_checked") is not True:
            error(f"{cid}: content support has not been checked by the host")
        links = rows(claim.get("links"), f"{cid}.links")
        if not links:
            error(f"{cid}: no source links")
        for link in links:
            rid = link.get("ref_id")
            if not isinstance(rid, str) or rid not in record_map:
                error(f"{cid}: unknown ref_id")
                continue
            r = record_map[rid]
            if r.get("citation_number") is None:
                error(f"{cid}->{rid}: source is not assigned a visible citation")
            level = link.get("check_level")
            if not one_of(level, READ_FLAGS):
                error(f"{cid}->{rid}: invalid check_level")
            else:
                reading = r.get("reading") if isinstance(r.get("reading"), dict) else {}
                if reading.get(READ_FLAGS[level]) is not True:
                    error(f"{cid}->{rid}: check_level conflicts with actual reading flags")
            if link.get("checked") is not True or not has_text(link.get("locator")):
                error(f"{cid}->{rid}: checked source locator required")
            if not one_of(link.get("support"), {"direct", "context", "counter"}):
                error(f"{cid}->{rid}: invalid support type")
            if link.get("support") == "direct":
                extraction = obj(r.get("extraction"), f"{rid}.extraction")
                for key in ("question", "object_and_conditions", "design", "role_in_review"):
                    if not has_text(extraction.get(key)):
                        error(f"{cid}->{rid}: extraction.{key} required for directly supporting evidence")
                if r.get("publication_status") == "retracted":
                    error(f"{cid}->{rid}: retracted work cannot provide normal direct support")
                if r.get("screening_status") == "excluded":
                    error(f"{cid}->{rid}: excluded study cannot silently provide direct support")
                if one_of(claim.get("kind"), {"mechanism", "intervention"}) and level == "abstract":
                    error(f"{cid}->{rid}: mechanism/intervention claim supported only by abstract")

    benchmarks = rows(ledger.get("benchmarks"), "benchmarks")
    counts["benchmarks"] = len(benchmarks)
    if not benchmarks and "benchmark_unavailable" not in open_types:
        error("No journal benchmark or disclosed benchmark_unavailable issue")
    for i, bench in enumerate(benchmarks):
        label = f"benchmark {i + 1}"
        for key in ("journal", "article_type", "rationale"):
            if not has_text(bench.get(key)):
                error(f"{label}: {key} required")
        guide = source_check(bench.get("official_guideline"), f"{label}.official_guideline", {"read", "partial", "unavailable"})
        if guide.get("status") != "read" and "benchmark_unavailable" not in open_types:
            error(f"{label}: unread guide needs a disclosed limitation")
        exemplars = rows(bench.get("exemplars"), f"{label}.exemplars")
        if not exemplars and "exemplar_unavailable" not in open_types:
            error(f"{label}: no read exemplars or disclosed exemplar_unavailable issue")
        for ex in exemplars:
            for key in ("title", "identifier", "lesson"):
                if not has_text(ex.get(key)):
                    error(f"{label}.exemplar: {key} required")
            if not one_of(ex.get("read_level"), {"abstract", "partial", "full_text"}):
                error(f"{label}.exemplar: invalid read_level")
            if ex.get("read_level") != "full_text":
                warning(f"{label}: exemplar not fully read; do not infer unseen structure")

    self_review = obj(ledger.get("host_self_review"), "host_self_review")
    if self_review.get("status") != "completed":
        error("Host self-review is incomplete")
    if not valid_date(self_review.get("checked_at")):
        error("Host self-review requires actual check date")
    checked_items = obj(self_review.get("checks"), "host_self_review.checks")
    for key in CHECKS:
        if checked_items.get(key) is not True:
            error(f"Host self-review item incomplete: {key}")
    if manuscript.is_file() and self_review.get("review_sha256") != file_hash(manuscript):
        error("Host self-review hash does not match the current manuscript")
    if one_of(review_type, {"systematic", "scoping", "meta_analysis"}):
        formal = obj(protocol.get("formal_methods"), "formal_methods")
        if formal.get("completed") is not True:
            error("Formal review methods are not completed; deliver only a clearly labelled draft")
        if not formal.get("guidance_sources"):
            error("Formal review requires actual applicable guidance sources")
        checks = obj(formal.get("checks"), "formal_methods.checks")
        for key in FORMAL_CHECKS:
            if checks.get(key) is not True:
                error(f"Formal methods item incomplete: {key}")
        if review_type == "meta_analysis" and formal.get("quantitative_synthesis_completed") is not True:
            error("Meta-analysis quantitative synthesis has not been completed")
        warning("Formal review flags are host attestations, not independent methodological certification")
    return report()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_init = sub.add_parser("init", help="Create a new empty review workspace; never overwrite")
    p_init.add_argument("--topic", required=True)
    p_init.add_argument("--root", type=Path, default=Path.cwd() / "reviews")
    p_init.add_argument("--language", default="zh-CN")
    p_hash = sub.add_parser("hash", help="Print SHA-256; does not mark any self-review complete")
    p_hash.add_argument("file", type=Path)
    p_audit = sub.add_parser("audit", help="Check local record consistency; no network")
    p_audit.add_argument("run_dir", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            run = init_review(args.topic, args.root, args.language)
            print(json.dumps({"run_dir": str(run), "status": "INITIALIZED_NOT_REVIEWED"}, ensure_ascii=False))
            return 0
        if args.command == "hash":
            print(file_hash(args.file))
            return 0
        result = audit_review(args.run_dir)
        # Avoid creating a misleading workspace when the requested path is invalid.
        work = args.run_dir.expanduser().resolve() / "_work"
        if work.is_dir():
            write_json(work / "audit.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if not result["errors"] else 1
    except (OSError, ValueError, UnicodeError) as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
