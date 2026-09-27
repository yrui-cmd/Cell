#!/usr/bin/env python3
"""Internal release checks for evidence records, task state and plan prose.

This command reads local files only. Its JSON is internal control information,
not text to append to the research plan. Source interpretation remains with the
host that performed the actual reading.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from check_plan import validate


# These detect process/self-exculpatory prose, not research dependencies such as
# ethics approval, sample availability, uncertain findings or quality control.
AUDIT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("self_scope", r"(?:本次交付|本次输出|本次报告|本计划|本次任务).{0,18}(?:仅为|仅是|只是|是|属于).{0,8}(?:研究安排|研究计划|规划建议)"),
    ("non_execution", r"尚未执行细胞[、，,\s]*动物(?:或|及|和)患者研究"),
    ("model_non_execution", r"(?:本次|本模型|本工具|本Skill|本助手|我).{0,25}(?:尚未|未|没有)(?:执行|开展|进行).{0,18}(?:实际实验|细胞实验|动物实验|患者研究)"),
    ("unanalysed_user_data", r"未分析(?:用户|作者)(?:的)?原始数据"),
    ("reading_shortfall", r"(?:尚未|未|没有)(?:完成|进行).{0,20}全文(?:精读|阅读)"),
    ("abstract_only", r"(?:目前|本次|当前)?.{0,8}仅(?:核对|检查|阅读|检索).{0,18}摘要(?:片段)?"),
    ("not_counted", r"未计入.{0,12}(?:\d+|二十|上述)篇"),
    ("checker_disclaimer", r"(?:结构检查|检查脚本|脚本检查|自动校验).{0,30}(?:只能|不能|不代表|无法|不等于)"),
    ("not_scientific_validation", r"(?:不能|无法|不可)(?:替代|代替).{0,10}科学验证"),
    ("generic_disclaimer", r"仅供参考|不构成(?:科研|研究|专业)建议"),
    ("audit_heading", r"^\s*#{1,6}\s*(?:免责声明|能力边界|执行范围|模型限制|完成度说明|补充依据与未完成阅读)"),
    ("english_scope", r"\b(?:this\s+(?:deliverable|output|plan)\s+is\s+(?:only|just)\s+(?:a\s+)?(?:research\s+)?plan|structural\s+checks?\s+(?:cannot|do\s+not)\s+(?:replace|substitute))\b"),
)
PLACEHOLDER = re.compile(r"\{\{.*?\}\}|\b(?:TODO|TBD|Rxx|Txx)\b|以(?:实际核实的文献标题|实际可访问的DOI链接|已核验的图号)[^\n]{0,60}替换", re.I)
PAPER_ID = re.compile(r"\[\s*(R\d{2,})\s*\]|^\s*\|\s*(R\d{2,})(?=\s|[；;：:|])", re.M)
TASK_ID = re.compile(r"(?<![A-Za-z0-9])T\d{2,}(?![A-Za-z0-9])")
NOTE_SECTIONS = ("原文定位", "主图", "方法", "补充材料", "对计划的影响")


@dataclass
class DeliveryReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    counted_core_papers: int = 0
    target_paper_count: int = 0

    @property
    def delivery_ready(self) -> bool:
        return not self.errors


def lint_plan(text: str) -> list[str]:
    """Reject unfinished/process prose without editing the user's content."""
    if not isinstance(text, str) or not text.strip():
        return ["研究计划正文为空。"]
    found: list[str] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if PLACEHOLDER.search(line):
            found.append(f"正文第{line_number}行仍有模板占位符。")
        for label, pattern in AUDIT_PATTERNS:
            if re.search(pattern, line, re.I):
                found.append(f"正文第{line_number}行包含过程性免责或未完成说明：{label}。先完成相应工作，再改写正文。")
                break
    return found


def _nonempty_strings(value: Any) -> bool:
    return (isinstance(value, list) and bool(value)
            and all(isinstance(item, str) and item.strip() for item in value))


def check_delivery(data: Any, document: str, state_directory: Path) -> DeliveryReport:
    """Combine release-state checks, local evidence checks and output lint."""
    result = DeliveryReport()
    state = validate(data, mode="release")
    result.errors.extend(state.errors)
    result.warnings.extend(state.warnings)
    result.counted_core_papers = state.counted_core_papers
    result.target_paper_count = state.target_paper_count
    result.errors.extend(lint_plan(document))
    if not isinstance(data, dict) or not isinstance(document, str):
        return result

    papers = data.get("papers")
    if not isinstance(papers, list):
        papers = []
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        tasks = []
    recorded_ids = {p["id"] for p in papers if isinstance(p, dict)
                    and isinstance(p.get("id"), str)}
    cited = {first or second for first, second in PAPER_ID.findall(document)}
    for pid in sorted(cited - recorded_ids):
        result.errors.append(f"正文存在未记录的文献编号：{pid}。")
    task_ids = {t["id"] for t in tasks if isinstance(t, dict)
                and isinstance(t.get("id"), str)}
    document_tasks = set(TASK_ID.findall(document))
    for tid in sorted(task_ids - document_tasks):
        result.errors.append(f"正文未呈现已安排任务：{tid}。")
    for tid in sorted(document_tasks - task_ids):
        result.errors.append(f"正文存在未记录的任务编号：{tid}。")

    base = Path(state_directory).resolve()
    used_notes: set[Path] = set()
    for index, paper in enumerate(papers):
        if not isinstance(paper, dict):
            continue
        pid = paper.get("id")
        if not isinstance(pid, str) or not pid.strip():
            continue  # Already reported by the state validator.
        counted = paper.get("counted") is True
        if counted and pid not in cited:
            result.errors.append(f"{pid}计入对标但未出现在正文/文献对照表。")
        if paper.get("read_status") != "full":
            continue
        if not counted and pid not in cited:
            continue

        receipts = paper.get("read_receipts")
        if not isinstance(receipts, dict):
            result.errors.append(f"{pid}缺少实际读取凭据read_receipts。")
            receipts = {}
        required = ["main_text", "main_figures", "methods"]
        parts = paper.get("parts") if isinstance(paper.get("parts"), dict) else {}
        if parts.get("core_supplement") == "read":
            required.append("core_supplement")
        for part in required:
            values = receipts.get(part)
            if not _nonempty_strings(values):
                result.errors.append(f"{pid}缺少{part}的实际读取凭据。")
            elif any(PLACEHOLDER.search(value) for value in values):
                result.errors.append(f"{pid}的{part}读取凭据仍含占位符。")

        relative = paper.get("evidence_file")
        if not isinstance(relative, str) or not relative.strip():
            result.errors.append(f"{pid}缺少evidence_file。")
            continue
        candidate = Path(relative)
        if candidate.is_absolute():
            result.errors.append(f"{pid}的证据路径必须相对于状态目录。")
            continue
        try:
            note_path = (base / candidate).resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            result.errors.append(f"{pid}证据路径不可解析：{exc}。")
            continue
        if not note_path.is_relative_to(base):
            result.errors.append(f"{pid}的证据路径越出任务状态目录。")
            continue
        if note_path in used_notes:
            result.errors.append(f"{pid}复用了其他论文的证据笔记；逐篇保存。")
        used_notes.add(note_path)
        try:
            note = note_path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError, ValueError) as exc:
            result.errors.append(f"{pid}证据笔记无法读取：{exc}。")
            continue
        if PLACEHOLDER.search(note):
            result.errors.append(f"{pid}证据笔记仍有占位符。")
        for key in ("title", "source"):
            value = paper.get(key)
            if isinstance(value, str) and value.strip() and value not in note:
                result.errors.append(f"{pid}证据笔记未包含记录的{key}。")
        sections = {heading.strip(): content for heading, content in re.findall(
            r"^##\s+([^\n]+)\n(.*?)(?=^##\s|\Z)", note, re.M | re.S)}
        for heading in NOTE_SECTIONS:
            content = sections.get(heading, "").strip()
            if not content or not re.search(r"[\w\u4e00-\u9fff]", content):
                result.errors.append(f"{pid}证据笔记缺少实质内容：{heading}。")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path, help="Internal plan_state.json")
    parser.add_argument("document", type=Path, help="UTF-8 Markdown draft for release")
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.state.read_text(encoding="utf-8-sig"))
        document = args.document.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"无法读取交付输入：{exc}", file=sys.stderr)
        return 2
    report = check_delivery(data, document, args.state.parent)
    payload = {"delivery_ready": report.delivery_ready, **asdict(report)}
    try:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    except UnicodeEncodeError:
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0 if report.delivery_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
