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
        "design_review": {
            "applicability": "not_applicable",
            "reason": "Synthetic structure fixture does not represent a real study.",
            "designs": [],
        },
        "resource_review": {
            "applicability": "required",
            "reason": "The synthetic task uses one bounded input-processing resource.",
            "resources": [{
                "id": "RES-INPUT", "name": "Synthetic input processing",
                "kind": "equipment", "capacity": 1, "unit": "slot_per_week",
                "availability_note": "One synthetic slot is available in week 1."
            }],
            "allocations": [{
                "resource_id": "RES-INPUT", "task_id": "T01",
                "start_week": 1, "end_week": 1, "amount": 1,
                "occupancy": "active", "holds_capacity": True,
                "note": "The validation task actively occupies the only slot."
            }],
        },
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
            "resources": ["RES-INPUT"]
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
        allocation = copy.deepcopy(d["resource_review"]["allocations"][0])
        allocation.update(task_id="T02", occupancy="passive_wait", holds_capacity=False,
                          note="Same-week handover does not add simultaneous slot demand.")
        d["resource_review"]["allocations"].append(allocation)
        r = validate(d)
        self.assertTrue(r.ok)
        self.assertTrue(r.warnings)

    def test_known_resource_capacity_conflict_is_blocked(self):
        d = fixture()
        other = copy.deepcopy(d["tasks"][0])
        other.update(id="T02", depends_on=[])
        d["tasks"].append(other)
        allocation = copy.deepcopy(d["resource_review"]["allocations"][0])
        allocation["task_id"] = "T02"
        d["resource_review"]["allocations"].append(allocation)
        self.assertTrue(any("超过容量" in error for error in validate(d).errors))

    def test_passive_wait_without_hold_does_not_consume_capacity(self):
        d = fixture()
        other = copy.deepcopy(d["tasks"][0])
        other.update(id="T02", depends_on=[])
        d["tasks"].append(other)
        allocation = copy.deepcopy(d["resource_review"]["allocations"][0])
        allocation.update(task_id="T02", occupancy="passive_wait", holds_capacity=False,
                          note="External processing wait does not reserve the local slot.")
        d["resource_review"]["allocations"].append(allocation)
        self.assertTrue(validate(d).ok)

    def test_unknown_capacity_overlap_needs_resolution(self):
        d = fixture()
        d["resource_review"]["resources"][0]["capacity"] = None
        other = copy.deepcopy(d["tasks"][0])
        other.update(id="T02", depends_on=[])
        d["tasks"].append(other)
        allocation = copy.deepcopy(d["resource_review"]["allocations"][0])
        allocation["task_id"] = "T02"
        d["resource_review"]["allocations"].append(allocation)
        self.assertTrue(any("容量未知" in error for error in validate(d).errors))
        d["resource_review"]["resources"][0]["overlap_resolution"] = (
            "The facility manager confirmed two independent slots for week 1.")
        self.assertTrue(validate(d).ok)

    def test_no_tasks_rejected(self):
        d = fixture()
        d["tasks"] = []
        self.assertFalse(validate(d).ok)

    def test_design_review_required_for_release(self):
        d = fixture()
        del d["design_review"]
        self.assertFalse(validate(d).ok)
        draft = validate(d, mode="draft")
        self.assertTrue(draft.ok)
        self.assertTrue(any("design_review" in warning for warning in draft.warnings))

    def test_resource_review_required_for_release(self):
        d = fixture()
        del d["resource_review"]
        self.assertFalse(validate(d).ok)
        draft = validate(d, mode="draft")
        self.assertTrue(draft.ok)
        self.assertTrue(any("resource_review" in warning for warning in draft.warnings))

    def test_undetermined_design_is_draft_only(self):
        d = fixture()
        d["design_review"].update(
            applicability="undetermined",
            reason="The actual research mode has not yet been classified.",
        )
        self.assertFalse(validate(d).ok)
        self.assertTrue(validate(d, mode="draft").ok)

    def test_required_design_checks_units_and_controls(self):
        d = fixture()
        d["design_review"] = {
            "applicability": "required",
            "reason": "The plan contains a synthetic intervention comparison.",
            "designs": [{
                "id": "D01",
                "task_ids": ["T01"],
                "design_type": "Synthetic parallel comparison",
                "experimental_unit": "independently generated synthetic record",
                "observation_unit": "one recorded measurement",
                "analysis_unit": "independently generated synthetic record",
                "independence_basis": "Measurements from one record are not counted as new records.",
                "assignment": "randomized",
                "assignment_rationale": "Random order limits position effects.",
                "randomization_record": "Store the generated seed and assignment table.",
                "blocking_factors": ["synthetic batch"],
                "blocking_rationale": "Balance the only known nuisance factor.",
                "blinding": "Use coded group labels during scoring.",
                "biological_replication": "Use independently generated records as independent replicates.",
                "technical_replication_role": "Repeated reads estimate measurement variation only.",
                "batch_run_order": "Interleave groups within each synthetic batch.",
                "sample_size_basis": "Choose before inspection using the stated precision target.",
                "primary_outcomes": ["predeclared structural validation result"],
                "known_confounders": [],
                "exclusion_stop_rules": "Exclude only unreadable records using a logged rule.",
            }],
        }
        self.assertTrue(validate(d).ok)

        del d["design_review"]["designs"][0]["experimental_unit"]
        self.assertTrue(any("experimental_unit" in error for error in validate(d).errors))

    def test_randomized_design_requires_reproducible_record(self):
        d = fixture()
        design = {
            "id": "D01", "task_ids": ["T01"], "design_type": "Parallel",
            "experimental_unit": "sample", "observation_unit": "measurement",
            "analysis_unit": "sample", "independence_basis": "one value per sample",
            "assignment": "randomized", "assignment_rationale": "balance order effects",
            "blocking_factors": [], "blocking_rationale": "no known blocking factor",
            "blinding": "coded labels", "biological_replication": "independent samples",
            "technical_replication_role": "measurement precision only",
            "batch_run_order": "interleaved", "sample_size_basis": "precision target",
            "primary_outcomes": ["outcome"], "known_confounders": [],
            "exclusion_stop_rules": "predeclared quality failure only",
        }
        d["design_review"] = {"applicability": "required", "reason": "intervention",
                              "designs": [design]}
        self.assertTrue(any("randomization_record" in error for error in validate(d).errors))

    def test_observational_design_does_not_require_randomization(self):
        d = fixture()
        design = {
            "id": "D01", "task_ids": ["T01"], "design_type": "Observational",
            "experimental_unit": "participant", "observation_unit": "visit",
            "analysis_unit": "participant", "independence_basis": "participant-level analysis",
            "assignment": "observational", "assignment_rationale": "exposure is observed",
            "blocking_factors": [], "blocking_rationale": "adjust known confounders instead",
            "blinding": "outcome coder sees masked identifiers",
            "biological_replication": "independent participants",
            "technical_replication_role": "repeat assays assess measurement error",
            "batch_run_order": "mix exposure groups across assay batches",
            "sample_size_basis": "precision and detectable association",
            "primary_outcomes": ["predefined outcome"],
            "known_confounders": ["age"],
            "exclusion_stop_rules": "predeclared eligibility and data-quality rules",
        }
        d["design_review"] = {"applicability": "required", "reason": "observational comparison",
                              "designs": [design]}
        self.assertTrue(validate(d).ok)

    def test_design_cannot_reference_unknown_task(self):
        d = fixture()
        d["design_review"] = {
            "applicability": "required", "reason": "test link validation",
            "designs": [{
                "id": "D01", "task_ids": ["T99"], "design_type": "Observational",
                "experimental_unit": "sample", "observation_unit": "measurement",
                "analysis_unit": "sample", "independence_basis": "sample-level",
                "assignment": "observational", "assignment_rationale": "observed groups",
                "blocking_factors": [], "blocking_rationale": "none known",
                "blinding": "coded labels", "biological_replication": "independent samples",
                "technical_replication_role": "precision only", "batch_run_order": "interleaved",
                "sample_size_basis": "precision", "primary_outcomes": ["outcome"],
                "known_confounders": [], "exclusion_stop_rules": "predeclared QC",
            }],
        }
        self.assertTrue(any("T99" in error for error in validate(d).errors))

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
