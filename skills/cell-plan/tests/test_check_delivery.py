"""Regression checks with synthetic records; no external literature is used."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_delivery import check_delivery, lint_plan  # noqa: E402
from check_plan import validate  # noqa: E402
from test_check_plan import fixture  # noqa: E402


def complete_fixture(directory: Path, count: int = 20) -> tuple[dict, str]:
    data = fixture()
    base_paper = data["papers"][0]
    data["papers"] = []
    data["target_paper_count"] = count
    if count == 20:
        data.pop("target_count_instruction", None)
    note_dir = directory / "evidence"
    note_dir.mkdir(exist_ok=True)
    for number in range(1, count + 1):
        paper = copy.deepcopy(base_paper)
        pid = f"R{number:02}"
        paper.update(id=pid, work_id=f"synthetic-{pid}",
                     title=f"Synthetic unit-test record {pid}",
                     source=f"urn:synthetic-test:{pid}",
                     evidence_file=f"evidence/{pid}.md",
                     read_receipts={
                         "main_text": [f"synthetic-read:{pid}:text"],
                         "main_figures": [f"synthetic-read:{pid}:figure"],
                         "methods": [f"synthetic-read:{pid}:methods"],
                         "core_supplement": [],
                     })
        note = (f'# {paper["title"]}\n{paper["source"]}\n\n'
                '## 原文定位\nSynthetic section locator.\n'
                '## 主图\nSynthetic Figure 1 tests fixture.\n'
                '## 方法\nSynthetic method description.\n'
                '## 补充材料\nNo supplement in synthetic test fixture.\n'
                '## 对计划的影响\nSupports synthetic task T01.\n')
        (note_dir / f"{pid}.md").write_text(note, encoding="utf-8")
        data["papers"].append(paper)
    document = ("# 研究执行计划\n\n## 具体工作安排\n"
                "T01：第1周核查样本标签与重复单位，交付可分析样本清单。[R01]\n"
                "## 文献对照表\n" + "\n".join(
                    f'[{p["id"]}] {p["title"]}；{p["source"]}；用于T01。'
                    for p in data["papers"]))
    return data, document


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.data, self.document = complete_fixture(self.directory)

    def tearDown(self):
        self.temp.cleanup()

    def check(self):
        return check_delivery(self.data, self.document, self.directory)

    def test_complete_synthetic_release(self):
        report = self.check()
        self.assertTrue(report.delivery_ready, report.errors)
        self.assertEqual(report.counted_core_papers, 20)

    def test_original_user_complaint_is_rejected(self):
        self.document += ("\n目前仅核对检索摘要片段，未计入上述20篇，也未据此增加15-LOX实验。"
                          "开始氧化脂质实验前需针对其底物鉴定与现有路线核对方法，避免漏掉近期证据。\n"
                          "本次交付是研究安排，尚未执行细胞、动物或患者研究，未分析用户原始数据，"
                          "也未完成20篇全文精读。结构检查只能核验任务依赖、时间和引用记录，不能替代科学验证。")
        self.assertFalse(self.check().delivery_ready)

    def test_deleting_caveat_cannot_rescue_missing_papers(self):
        self.data["papers"] = self.data["papers"][:1]
        self.data["reading_status"] = "partial"
        self.data["limitations"] = []
        self.document = "# 研究执行计划\nT01：核查样本标签。[R01]\n"
        self.assertFalse(self.check().delivery_ready)

    def test_fake_complete_count_rejected(self):
        self.data["papers"] = self.data["papers"][:19]
        self.assertFalse(self.check().delivery_ready)

    def test_unfinished_skill_task_rejected(self):
        self.data["open_skill_tasks"] = ["尚需核查会影响主线的新论文方法"]
        self.assertFalse(self.check().delivery_ready)

    def test_reducing_target_without_instruction_rejected(self):
        self.data["target_paper_count"] = 1
        self.assertFalse(self.check().delivery_ready)

    def test_explicit_user_target_supported(self):
        self.data, self.document = complete_fixture(self.directory, count=1)
        self.assertTrue(self.check().delivery_ready)

    def test_receipt_required(self):
        del self.data["papers"][0]["read_receipts"]
        self.assertFalse(self.check().delivery_ready)

    def test_all_figures_need_receipt(self):
        self.data["papers"][0]["read_receipts"]["main_figures"] = []
        self.assertFalse(self.check().delivery_ready)

    def test_supplement_receipt_required_when_read(self):
        self.data["papers"][0]["parts"]["core_supplement"] = "read"
        self.assertFalse(self.check().delivery_ready)

    def test_note_required(self):
        (self.directory / "evidence/R01.md").unlink()
        self.assertFalse(self.check().delivery_ready)

    def test_empty_note_rejected(self):
        (self.directory / "evidence/R01.md").write_text("", encoding="utf-8")
        self.assertFalse(self.check().delivery_ready)

    def test_missing_section_rejected(self):
        path = self.directory / "evidence/R01.md"
        path.write_text(path.read_text(encoding="utf-8").replace("## 主图", "## 其他"), encoding="utf-8")
        self.assertFalse(self.check().delivery_ready)

    def test_placeholder_in_note_rejected(self):
        path = self.directory / "evidence/R01.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n{{待填内容}}\n", encoding="utf-8")
        self.assertFalse(self.check().delivery_ready)

    def test_note_outside_state_directory_rejected(self):
        self.data["papers"][0]["evidence_file"] = "../external.md"
        self.assertFalse(self.check().delivery_ready)

    def test_absolute_note_path_rejected(self):
        self.data["papers"][0]["evidence_file"] = str(self.directory / "evidence/R01.md")
        self.assertFalse(self.check().delivery_ready)

    def test_note_reuse_rejected(self):
        self.data["papers"][1]["evidence_file"] = "evidence/R01.md"
        self.assertFalse(self.check().delivery_ready)

    def test_unknown_reference_rejected(self):
        self.document += "\n方法依据：[R99]。"
        self.assertFalse(self.check().delivery_ready)

    def test_missing_counted_reference_rejected(self):
        self.document = self.document.replace("[R20]", "[X20]")
        self.assertFalse(self.check().delivery_ready)

    def test_missing_task_rejected(self):
        self.document = self.document.replace("T01", "样本核查")
        self.assertFalse(self.check().delivery_ready)

    def test_unknown_task_rejected(self):
        self.document += "\nT99：未经排程的工作。"
        self.assertFalse(self.check().delivery_ready)

    def test_empty_plan_rejected(self):
        self.document = ""
        self.assertFalse(self.check().delivery_ready)

    def test_real_research_conditions_preserved(self):
        self.document += ("\n完成伦理审批后开始入组；样本可用性在第1周确认。"
                          "现有结果尚不能区分两种解释，因此增加阴性对照。"
                          "剂量范围由参数预实验确定。该方法尚未在此模型验证，先测试重复性。"
                          "若质量检查不通过，先修复样本与批次问题，不扩大样本量。"
                          "以质量合格的新样本替换受损样本，并记录替换原因。")
        self.assertTrue(self.check().delivery_ready, self.check().errors)

    def test_self_scope_variants_rejected(self):
        for text in ("本次交付仅为研究安排。", "本次输出只是研究计划。",
                     "结构检查不能替代科学验证。", "目前仅核对摘要片段。",
                     "尚未完成20篇全文阅读。", "未分析用户原始数据。",
                     "## 免责声明\n仅供参考。", "本模型没有进行实际实验。"):
            with self.subTest(text=text):
                self.assertTrue(lint_plan(text))

    def test_internal_draft_never_becomes_release(self):
        self.data["reading_status"] = "partial"
        draft = validate(self.data, mode="draft")
        self.assertTrue(draft.ok)
        self.assertFalse(self.check().delivery_ready)

    def test_malformed_data_does_not_crash(self):
        for data in (None, [], {}, {"papers": [None], "tasks": [None]}):
            with self.subTest(data=data):
                self.assertFalse(check_delivery(data, self.document, self.directory).delivery_ready)

    def test_cli_ready_then_caveat_then_bad_json(self):
        state = self.directory / "plan_state.json"
        plan = self.directory / "plan.md"
        state.write_text(json.dumps(self.data), encoding="utf-8")
        plan.write_text(self.document, encoding="utf-8")
        command = [sys.executable, str(ROOT / "scripts/check_delivery.py"), str(state), str(plan)]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["delivery_ready"])
        self.assertNotIn("scope", json.loads(completed.stdout))
        plan.write_text(self.document + "\n本次交付仅为研究安排。", encoding="utf-8")
        completed = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 1)
        self.assertFalse(json.loads(completed.stdout)["delivery_ready"])
        state.write_text("{bad json", encoding="utf-8")
        completed = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
