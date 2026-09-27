"""Synthetic local tests, not a trial on real papers or real research projects."""
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
from check_plan import validate  # noqa: E402


def fixture() -> dict:
    return {
        "schema_version": 1,
        "target_paper_count": 1,
        "reading_status": "complete",
        "limitations": [],
        "open_skill_tasks": [],
        "target_count_instruction": "Synthetic test: explicit requested target is one.",
        "papers": [{
            "id": "R01", "work_id": "synthetic-work-01",
            "title": "Synthetic unit-test record; not a real paper",
            "source": "urn:research-plan-test:R01", "article_type": "original",
            "read_status": "full", "counted": True,
            "parts": {"main_text": True, "main_figures": True,
                      "methods": True, "core_supplement": "not_needed"},
            "supplement_note": "Synthetic fixture has no supplement.",
            "locators": ["Synthetic Figure 1"],
            "plan_impact": "Test reference linkage only."
        }],
        "tasks": [{
            "id": "T01", "title": "Check synthetic inputs",
            "question": "Is the fixture structurally valid?",
            "action": "Check fixture fields", "deliverable": "Validation record",
            "basis": "literature", "basis_note": "Synthetic test only",
            "source_ids": ["R01"], "depends_on": [], "priority": "must",
            "condition": "", "start_week": 1, "end_week": 1,
            "duration_basis": "Synthetic scheduling fixture",
            "resources": ["Synthetic inputs"]
        }]
    }


class PlanCheckTests(unittest.TestCase):
    def test_valid_fixture(self):
        self.assertTrue(validate(fixture()).ok)

    def test_partial_rejected_for_release_but_allowed_as_internal_draft(self):
        d = fixture()
        d.update(target_paper_count=20, reading_status="partial",
                 limitations=["Only one synthetic record, not real reading."])
        self.assertFalse(validate(d).ok)
        self.assertTrue(validate(d, mode="draft").ok)

    def test_false_complete_rejected(self):
        d = fixture()
        d["target_paper_count"] = 20
        self.assertFalse(validate(d).ok)

    def test_partial_without_disclaimer_still_rejected(self):
        d = fixture()
        d.update(target_paper_count=20, reading_status="partial")
        self.assertFalse(validate(d).ok)

    def test_abstract_cannot_count(self):
        d = fixture()
        d["papers"][0]["read_status"] = "abstract"
        self.assertFalse(validate(d).ok)

    def test_review_cannot_count(self):
        d = fixture()
        d["papers"][0]["article_type"] = "review"
        self.assertFalse(validate(d).ok)

    def test_missing_figure_cannot_count(self):
        d = fixture()
        d["papers"][0]["parts"]["main_figures"] = False
        self.assertFalse(validate(d).ok)

    def test_unavailable_supplement_cannot_count(self):
        d = fixture()
        d["papers"][0]["parts"]["core_supplement"] = "unavailable"
        self.assertFalse(validate(d).ok)

    def test_not_needed_requires_note(self):
        d = fixture()
        del d["papers"][0]["supplement_note"]
        self.assertFalse(validate(d).ok)

    def test_duplicate_work_rejected(self):
        d = fixture()
        other = copy.deepcopy(d["papers"][0])
        other.update(id="R02", source="urn:research-plan-test:R02")
        d["papers"].append(other)
        self.assertFalse(validate(d).ok)

    def test_doi_variants_not_double_counted(self):
        d = fixture()
        d["papers"][0]["source"] = "https://doi.org/10.0000/synthetic"
        other = copy.deepcopy(d["papers"][0])
        other.update(id="R02", work_id="synthetic-work-02",
                     source="DOI:10.0000/SYNTHETIC")
        d["papers"].append(other)
        self.assertFalse(validate(d).ok)

    def test_unknown_source_rejected(self):
        d = fixture()
        d["tasks"][0]["source_ids"] = ["R99"]
        self.assertFalse(validate(d).ok)

    def test_partial_reference_warns(self):
        d = fixture()
        d["papers"][0].update(read_status="partial", counted=False)
        d.update(reading_status="partial", limitations=["Incomplete synthetic record"])
        self.assertFalse(validate(d).ok)
        r = validate(d, mode="draft")
        self.assertTrue(r.ok)
        self.assertTrue(r.warnings)

    def test_cycle_rejected(self):
        d = fixture()
        other = copy.deepcopy(d["tasks"][0])
        other.update(id="T02", depends_on=["T01"])
        d["tasks"][0]["depends_on"] = ["T02"]
        d["tasks"].append(other)
        self.assertTrue(any("循环" in e for e in validate(d).errors))

    def test_dependency_timing_rejected(self):
        d = fixture()
        d["tasks"][0]["end_week"] = 3
        other = copy.deepcopy(d["tasks"][0])
        other.update(id="T02", depends_on=["T01"], start_week=2, end_week=4)
        d["tasks"].append(other)
        self.assertTrue(any("尚未结束" in e for e in validate(d).errors))

    def test_required_cannot_depend_on_optional(self):
        d = fixture()
        d["tasks"][0].update(priority="optional", condition="Extra capacity")
        other = copy.deepcopy(d["tasks"][0])
        other.update(id="T02", priority="must", condition="", depends_on=["T01"],
                     start_week=2, end_week=2)
        d["tasks"].append(other)
        self.assertFalse(validate(d).ok)

    def test_same_week_handover_warns(self):
        d = fixture()
        other = copy.deepcopy(d["tasks"][0])
        other.update(id="T02", depends_on=["T01"])
        d["tasks"].append(other)
        r = validate(d)
        self.assertTrue(r.ok)
        self.assertTrue(r.warnings)

    def test_no_tasks_rejected(self):
        d = fixture()
        d["tasks"] = []
        self.assertFalse(validate(d).ok)

    def test_malformed_values_do_not_crash(self):
        for data in (None, [], {}, {"papers": [None], "tasks": [None]},
                     {"papers": {}, "tasks": "not a list"}):
            with self.subTest(data=data):
                self.assertFalse(validate(data).ok)
        d = fixture()
        d["tasks"][0].update(depends_on=[None], source_ids=[{}], start_week=True)
        self.assertFalse(validate(d).ok)

    def test_cli_and_invalid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text(json.dumps(fixture()), encoding="utf-8")
            command = [sys.executable, str(ROOT / "scripts" / "check_plan.py"), str(path)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["ok"])
            self.assertFalse(json.loads(result.stdout)["delivery_ready"])
            path.write_text("{bad json", encoding="utf-8")
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
