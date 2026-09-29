#!/usr/bin/env python3
"""Validate research-plan metadata locally; this does not verify scientific truth.

Python standard library only. No network calls, model calls, or file modification.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


@dataclass
class Report:
    mode: str = "release"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    counted_core_papers: int = 0
    target_paper_count: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _positive_int(value: Any) -> bool:
    return type(value) is int and value > 0


def _strings(value: Any, allow_empty: bool = True) -> bool:
    return (isinstance(value, list) and all(_text(item) for item in value)
            and (allow_empty or bool(value)))


def _source_key(source: str) -> str:
    """Normalize common DOI spellings without fetching the source."""
    value = source.strip()
    lowered = value.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/",
                   "http://dx.doi.org/", "doi:"):
        if lowered.startswith(prefix):
            return "doi:" + lowered[len(prefix):].strip().rstrip("/")
    if lowered.startswith("10.") and "/" in lowered:
        return "doi:" + lowered.rstrip("/")
    try:
        parsed = urlsplit(value)
        if parsed.scheme in ("http", "https"):
            return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(),
                               parsed.path.rstrip("/"), parsed.query, ""))
    except ValueError:
        pass
    return value


def _validate_design_review(
        value: Any, task_map: dict[str, dict[str, Any]], report: Report) -> None:
    """Validate explicit study-design decisions without judging scientific truth."""
    if not isinstance(value, dict):
        message = "design_review必须是对象，并明确设计审查是否适用。"
        if report.mode == "release":
            report.errors.append(message)
        else:
            report.warnings.append(message)
        return

    applicability = value.get("applicability")
    if applicability not in ("required", "not_applicable", "undetermined"):
        report.errors.append(
            "design_review.applicability必须为required、not_applicable或undetermined。")
    if not _text(value.get("reason")):
        report.errors.append("design_review.reason必须说明适用性判断。")

    designs = value.get("designs")
    if not isinstance(designs, list):
        report.errors.append("design_review.designs必须为数组。")
        return
    if applicability == "undetermined":
        message = "研究设计适用性仍为undetermined；正式交付前必须判定。"
        if report.mode == "release":
            report.errors.append(message)
        else:
            report.warnings.append(message)
        return
    if applicability == "not_applicable":
        if designs:
            report.errors.append("设计审查标为not_applicable时designs必须为空数组。")
        return
    if applicability != "required":
        return
    if not designs:
        report.errors.append("设计审查适用时designs不能为空。")
        return

    design_ids: set[str] = set()
    text_fields = (
        "id", "design_type", "experimental_unit", "observation_unit",
        "analysis_unit", "independence_basis", "assignment_rationale",
        "blocking_rationale", "blinding", "biological_replication",
        "technical_replication_role", "batch_run_order", "sample_size_basis",
        "exclusion_stop_rules",
    )
    for index, design in enumerate(designs):
        label = f"design_review.designs[{index}]"
        if not isinstance(design, dict):
            report.errors.append(f"{label}必须是对象。")
            continue
        for key in text_fields:
            if not _text(design.get(key)):
                report.errors.append(f"{label}.{key}必须是非空字符串。")
        design_id = design.get("id")
        if _text(design_id):
            if design_id in design_ids:
                report.errors.append(f"重复设计ID：{design_id}。")
            design_ids.add(design_id)
            label = design_id

        task_ids = design.get("task_ids")
        if not _strings(task_ids, allow_empty=False):
            report.errors.append(f"{label}.task_ids必须是非空字符串数组。")
        else:
            for task_id in task_ids:
                if task_id not in task_map:
                    report.errors.append(f"{label}关联了不存在的任务：{task_id}。")

        assignment = design.get("assignment")
        if assignment not in ("randomized", "nonrandomized", "observational",
                               "not_applicable"):
            report.errors.append(f"{label}.assignment无效。")
        if assignment == "randomized" and not _text(design.get("randomization_record")):
            report.errors.append(
                f"{label}采用随机分配但缺少randomization_record；记录方法、种子或分配表保存位置。")
        for key in ("blocking_factors", "known_confounders"):
            if not _strings(design.get(key)):
                report.errors.append(f"{label}.{key}必须是字符串数组，可为空。")
        if not _strings(design.get("primary_outcomes"), allow_empty=False):
            report.errors.append(f"{label}.primary_outcomes必须是非空字符串数组。")


def validate(data: Any, *, mode: str = "release") -> Report:
    """Return structural errors and warnings; never assert papers were read."""
    r = Report(mode=mode)
    if mode not in ("release", "draft"):
        r.errors.append("mode必须为release或draft。")
        return r
    if not isinstance(data, dict):
        r.errors.append("根对象必须是JSON对象。")
        return r
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        r.errors.append("schema_version必须为整数1。")
    target = data.get("target_paper_count")
    if not _positive_int(target):
        r.errors.append("target_paper_count必须为正整数。")
    else:
        r.target_paper_count = target
    if mode == "release" and _positive_int(target) and target != 20:
        if not _text(data.get("target_count_instruction")):
            r.errors.append("非默认篇数须记录用户明确改变数量的target_count_instruction。")
    if data.get("reading_status") not in ("complete", "partial"):
        r.errors.append("reading_status必须为complete或partial。")
    if not _strings(data.get("limitations")):
        r.errors.append("limitations必须是字符串数组，可为空。")

    pending = data.get("open_skill_tasks")
    if not _strings(pending):
        r.errors.append("open_skill_tasks必须是字符串数组；无未完成工作时为空数组。")
    elif pending and mode == "release":
        r.errors.append("仍有未完成的Skill工作，继续处理后再正式交付。")
    if mode == "release" and data.get("reading_status") != "complete":
        r.errors.append("部分阅读状态不能正式交付；继续获取和阅读全文。")

    papers = data.get("papers")
    if not isinstance(papers, list):
        r.errors.append("papers必须为数组。")
        papers = []
    paper_map: dict[str, dict[str, Any]] = {}
    counted_work: set[str] = set()
    counted_source: set[str] = set()
    for index, p in enumerate(papers):
        label = f"papers[{index}]"
        if not isinstance(p, dict):
            r.errors.append(f"{label}必须是对象。")
            continue
        for key in ("id", "work_id", "title", "source"):
            if not _text(p.get(key)):
                r.errors.append(f"{label}.{key}必须是非空字符串。")
        pid = p.get("id")
        if _text(pid):
            if pid in paper_map:
                r.errors.append(f"重复文献ID：{pid}。")
            else:
                paper_map[pid] = p
            label = pid
        if p.get("article_type") not in ("original", "preprint", "review", "other"):
            r.errors.append(f"{label}的article_type无效。")
        if p.get("read_status") not in ("metadata", "abstract", "partial", "full"):
            r.errors.append(f"{label}的read_status无效。")
        if type(p.get("counted")) is not bool:
            r.errors.append(f"{label}.counted必须为布尔值。")

        # A full-reading assertion needs recorded components, even if uncounted.
        if p.get("read_status") == "full" or p.get("counted") is True:
            parts = p.get("parts")
            if not isinstance(parts, dict):
                r.errors.append(f"{label}缺少parts对象。")
                parts = {}
            for key in ("main_text", "main_figures", "methods"):
                if parts.get(key) is not True:
                    r.errors.append(f"{label}不能记为全文完成：{key}未完成。")
            supplement = parts.get("core_supplement")
            if supplement not in ("read", "not_needed"):
                r.errors.append(f"{label}核心补充未完成或状态无效。")
            if supplement == "not_needed" and not _text(p.get("supplement_note")):
                r.errors.append(f"{label}的not_needed必须说明依据。")
            if not _strings(p.get("locators"), allow_empty=False):
                r.errors.append(f"{label}缺少非空图号/方法节等定位。")
            if not _text(p.get("plan_impact")):
                r.errors.append(f"{label}缺少对计划的具体影响。")
        if p.get("counted") is True:
            r.counted_core_papers += 1
            if p.get("article_type") != "original" or p.get("read_status") != "full":
                r.errors.append(f"{label}不能计入已读核心原始研究。")
            work = p.get("work_id")
            if _text(work):
                key = work.strip().casefold()
                if key in counted_work:
                    r.errors.append(f"同一工作被重复计数：{work}。")
                counted_work.add(key)
            source = p.get("source")
            if _text(source):
                key = _source_key(source)
                if key in counted_source:
                    r.errors.append(f"同一文献来源被重复计数：{source}。")
                counted_source.add(key)

    if _positive_int(target):
        if r.counted_core_papers < target:
            if data.get("reading_status") == "complete":
                r.errors.append("实际记录的完成篇数不足目标，不能标记complete。")
            if mode == "release":
                r.errors.append(f"全文记录不足目标：{r.counted_core_papers}/{target}；继续阅读。")
        elif data.get("reading_status") == "partial":
            r.warnings.append("计数已达到目标；核实阅读状态，切勿用计数代替科学核验。")

    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        r.errors.append("tasks必须是非空数组，不能只有文献没有工作安排。")
        tasks = []
    task_map: dict[str, dict[str, Any]] = {}
    for index, task in enumerate(tasks):
        label = f"tasks[{index}]"
        if not isinstance(task, dict):
            r.errors.append(f"{label}必须是对象。")
            continue
        for key in ("id", "title", "question", "action", "deliverable",
                    "basis_note", "duration_basis"):
            if not _text(task.get(key)):
                r.errors.append(f"{label}.{key}必须是非空字符串。")
        tid = task.get("id")
        if _text(tid):
            if tid in task_map:
                r.errors.append(f"重复任务ID：{tid}。")
            else:
                task_map[tid] = task
            label = tid
        if task.get("basis") not in ("literature", "user_data", "design", "operational"):
            r.errors.append(f"{label}的basis无效。")
        refs = task.get("source_ids")
        if not _strings(refs):
            r.errors.append(f"{label}.source_ids必须为字符串数组。")
        else:
            if task.get("basis") == "literature" and not refs:
                r.errors.append(f"{label}以文献为依据但没有source_ids。")
            for ref in refs:
                if ref not in paper_map:
                    r.errors.append(f"{label}引用了不存在的文献：{ref}。")
                elif paper_map[ref].get("read_status") != "full":
                    message = f"{label}引用{ref}未完成全文；先补齐任务依据。"
                    if mode == "release":
                        r.errors.append(message)
                    else:
                        r.warnings.append(message)
        if not _strings(task.get("depends_on")):
            r.errors.append(f"{label}.depends_on必须为字符串数组。")
        if not _strings(task.get("resources"), allow_empty=False):
            r.errors.append(f"{label}必须记录所需resources及其条件。")
        priority = task.get("priority")
        if priority not in ("must", "conditional", "optional"):
            r.errors.append(f"{label}的priority无效。")
        if priority in ("conditional", "optional") and not _text(task.get("condition")):
            r.errors.append(f"{label}必须写明开展条件condition。")
        start, end = task.get("start_week"), task.get("end_week")
        if not _positive_int(start) or not _positive_int(end):
            r.errors.append(f"{label}的周次必须为正整数。")
        elif start > end:
            r.errors.append(f"{label}开始时间晚于结束时间。")

    # Kahn's algorithm: finite checks even with malformed or cyclic dependencies.
    outgoing: dict[str, list[str]] = {tid: [] for tid in task_map}
    indegree = {tid: 0 for tid in task_map}
    for tid, task in task_map.items():
        deps = task.get("depends_on")
        if not _strings(deps):
            continue
        if len(deps) != len(set(deps)):
            r.errors.append(f"{tid}存在重复依赖。")
        for dep in set(deps):
            if dep not in task_map:
                r.errors.append(f"{tid}依赖不存在的任务：{dep}。")
                continue
            parent = task_map[dep]
            outgoing[dep].append(tid)
            indegree[tid] += 1
            if task.get("priority") == "must" and parent.get("priority") in ("optional", "conditional"):
                r.errors.append(f"必做任务{tid}依赖未触发的非必做任务{dep}。")
            end, start = parent.get("end_week"), task.get("start_week")
            if _positive_int(end) and _positive_int(start):
                if end > start:
                    r.errors.append(f"{tid}开始时前置任务{dep}尚未结束。")
                elif end == start:
                    r.warnings.append(f"{dep}与{tid}同周衔接，正文须说明周内先后顺序。")
    ready = [tid for tid, degree in indegree.items() if degree == 0]
    visited = 0
    while ready:
        tid = ready.pop()
        visited += 1
        for child in outgoing[tid]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    if visited < len(task_map):
        blocked = ", ".join(sorted(tid for tid, degree in indegree.items() if degree))
        r.errors.append(f"存在循环依赖或被循环阻塞的任务：{blocked}。")
    _validate_design_review(data.get("design_review"), task_map, r)
    return r


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path, help="Path to plan_state.json")
    parser.add_argument("--mode", choices=("release", "draft"), default="release",
                        help="release检查完整状态；draft只检查续做结构")
    args = parser.parse_args(argv)
    try:
        with args.state.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"无法读取计划状态：{exc}", file=sys.stderr)
        return 2
    report = validate(data, mode=args.mode)
    payload = {"ok": report.ok, "delivery_ready": False,
               "stage": "STATE_CHECK_ONLY", **asdict(report)}
    output = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        print(output)
    except UnicodeEncodeError:
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
