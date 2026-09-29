"""Synthetic fixtures only: no real papers, journal claims, or live retrieval."""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import review_tools as rt
import install_skill as installer


class ReviewAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run = rt.init_review("SYNTHETIC TEST TOPIC — NOT A REAL REVIEW", Path(self.tmp.name))
        self.protocol = rt.read_json(self.run / "_work" / "protocol.json")
        self.protocol.update(question="Synthetic test question", added_value="Test-only value", last_search_date="2026-09-27")
        self.ledger = rt.read_json(self.run / "_work" / "evidence.json")
        self.text = "# Synthetic test only\n\n## Evidence\nA synthetic observation is limited to the test fixture.[1]\n\n## Limitations\nThis is not a real review.\n\n## References\n[1] Test Author. Synthetic test reference. 2024. TEST-ONLY-ID.\n"
        self.ledger["searches"] = [{
            "id": "Q001", "source": "TEST FIXTURE (not a database)", "query": "synthetic query",
            "searched_at": "2026-09-27", "purpose": "mapping", "status": "completed",
            "reported_count": 1, "examined_count": 1, "retrieved_count": 1,
            "limits": "test only", "result_locator": "synthetic fixture",
        }]
        self.ledger["records"] = [{
            "id": "R001", "study_id": "S001", "citation_number": 1,
            "title": "Synthetic test reference", "authors": ["Test Author"], "year": 2024,
            "identifier": "TEST-ONLY-ID", "publication_type": "original_research",
            "publication_status": "published", "screening_status": "included", "screening_reason": "test only",
            "reading": {"abstract_read": True, "full_text_read": True, "key_figures_checked": False, "supplements_checked": False},
            "metadata_check": {"status": "verified", "checked_at": "2026-09-27", "source": "synthetic fixture", "fields_checked": ["title", "authors", "year", "identifier"]},
            "publication_check": {"status": "checked", "checked_at": "2026-09-27", "source": "synthetic fixture", "outcome": "no_notice_found"},
            "extraction": {"question": "test", "object_and_conditions": "test", "design": "test", "role_in_review": "test"},
        }]
        self.ledger["claims"] = [{
            "id": "C001", "text": "A synthetic observation is limited to the test fixture.",
            "kind": "descriptive", "scope_note": "Synthetic record only", "content_checked": True,
            "links": [{"ref_id": "R001", "locator": "synthetic section", "support": "direct", "check_level": "full_text", "checked": True}],
        }]
        self.ledger["benchmarks"] = [{
            "journal": "SYNTHETIC TEST JOURNAL (not real)", "article_type": "Review", "rationale": "test fixture",
            "official_guideline": {"status": "read", "source": "synthetic fixture", "checked_at": "2026-09-27", "requirements": ["test"]},
            "exemplars": [{"title": "TEST EXEMPLAR", "identifier": "TEST-EX", "read_level": "full_text", "lesson": "synthetic"}],
        }]
        self.ledger["host_self_review"].update(status="completed", checked_at="2026-09-27", checks={key: True for key in rt.CHECKS})

    def save(self, refresh_hash=True):
        (self.run / "_work" / "review.md").write_text(self.text, encoding="utf-8")
        if refresh_hash:
            self.ledger["host_self_review"]["review_sha256"] = rt.file_hash(self.run / "_work" / "review.md")
        rt.write_json(self.run / "_work" / "protocol.json", self.protocol)
        rt.write_json(self.run / "_work" / "evidence.json", self.ledger)

    def audit(self):
        self.save()
        return rt.audit_review(self.run)

    def assert_error(self, fragment):
        report = self.audit()
        self.assertEqual(report["status"], "NEEDS_REVISION")
        self.assertTrue(any(fragment in e for e in report["errors"]), report["errors"])

    def test_valid_synthetic_records(self):
        result = self.audit()
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["status"], "RECORDS_CONSISTENT")
        self.assertFalse(result["scientific_quality_certified"])

    def test_new_workspace_is_not_review(self):
        fresh = rt.init_review("Another test", Path(self.tmp.name))
        result = rt.audit_review(fresh)
        self.assertEqual(result["status"], "NEEDS_REVISION")
        self.assertFalse((fresh / "_work" / "review.md").exists())

    def test_empty_topic_rejected(self):
        with self.assertRaises(ValueError):
            rt.init_review(" ", Path(self.tmp.name))

    def test_missing_bibliography_entry(self):
        self.text = self.text.replace("fixture.[1]", "fixture.[1,2]")
        self.assert_error("[2] has no bibliography")

    def test_uncited_bibliography_entry(self):
        self.text += "[2] Another synthetic reference.\n"
        self.assert_error("[2] is not cited")

    def test_bibliography_title_mismatch(self):
        self.text = self.text.replace("Synthetic test reference.", "Wrong reference title.")
        self.assert_error("title differs")

    def test_duplicate_record_id(self):
        self.ledger["records"].append(copy.deepcopy(self.ledger["records"][0]))
        self.assert_error("duplicate record id")

    def test_boolean_not_accepted_as_count(self):
        self.ledger["searches"][0]["reported_count"] = True
        self.assert_error("reported_count must be")

    def test_unknown_counts_are_allowed(self):
        self.ledger["searches"][0]["reported_count"] = None
        self.assertEqual(self.audit()["errors"], [])

    def test_fulltext_reading_conflict(self):
        self.ledger["records"][0]["reading"]["full_text_read"] = False
        self.assert_error("conflicts with actual reading")

    def test_awaiting_fulltext_conflict(self):
        self.ledger["records"][0]["screening_status"] = "awaiting_full_text"
        self.assert_error("awaiting_full_text conflicts")

    def test_mechanism_from_abstract_blocked(self):
        self.ledger["claims"][0]["kind"] = "mechanism"
        self.ledger["claims"][0]["links"][0]["check_level"] = "abstract"
        self.assert_error("supported only by abstract")

    def test_nonexistent_claim_text(self):
        self.ledger["claims"][0]["text"] = "This is not in the manuscript."
        self.assert_error("does not occur")

    def test_unverified_content(self):
        self.ledger["claims"][0]["content_checked"] = False
        self.assert_error("content support has not")

    def test_missing_source_locator(self):
        self.ledger["claims"][0]["links"][0]["locator"] = ""
        self.assert_error("checked source locator required")

    def test_unverified_metadata(self):
        self.ledger["records"][0]["metadata_check"]["status"] = "pending"
        self.assert_error("metadata_check: unchecked")

    def test_incomplete_metadata_fields(self):
        self.ledger["records"][0]["metadata_check"]["fields_checked"] = ["identifier"]
        self.assert_error("identity fields")

    def test_retracted_positive_support(self):
        self.ledger["records"][0]["publication_status"] = "retracted"
        self.assert_error("retracted work cannot")

    def test_no_false_causal_inference_detection_claim(self):
        # Structural audit cannot know whether host-entered semantic labels are true.
        self.assertIn("no network", self.audit()["scope"])

    def test_missing_benchmark(self):
        self.ledger["benchmarks"] = []
        self.assert_error("No journal benchmark")

    def test_unread_guideline_not_silently_accepted(self):
        self.ledger["benchmarks"][0]["official_guideline"]["status"] = "unavailable"
        self.assert_error("unread guide needs")

    def test_missing_exemplars(self):
        self.ledger["benchmarks"][0]["exemplars"] = []
        self.assert_error("no read exemplars")

    def test_undisclosed_issue(self):
        self.ledger["issues"] = [{"id": "I001", "type": "full_text_unavailable", "status": "open", "impact": "scope", "manuscript_disclosure": "Not present"}]
        self.assert_error("not disclosed")

    def test_disclosed_scope_limitation(self):
        self.ledger["issues"] = [{"id": "I001", "type": "full_text_unavailable", "status": "open", "impact": "scope", "manuscript_disclosure": "This is not a real review."}]
        result = self.audit()
        self.assertEqual(result["errors"], [])
        self.assertTrue(result["warnings"])

    def test_core_issue_blocks_even_when_disclosed(self):
        self.ledger["issues"] = [{"id": "I001", "type": "methods_incomplete", "status": "open", "impact": "core", "manuscript_disclosure": "This is not a real review."}]
        self.assert_error("unresolved core")

    def test_formal_review_cannot_pass_with_empty_methods(self):
        self.protocol["review_type"] = "systematic"
        self.assert_error("Formal review methods are not completed")

    def test_custom_style_not_falsely_certified(self):
        self.protocol["citation_style"] = "custom"
        result = self.audit()
        self.assertTrue(any("not programmatically checked" in w for w in result["warnings"]))

    def test_stale_hash(self):
        self.save()
        with (self.run / "_work" / "review.md").open("a", encoding="utf-8") as f:
            f.write("\nChanged after self-review.\n")
        result = rt.audit_review(self.run)
        self.assertTrue(any("hash does not match" in e for e in result["errors"]))

    def test_malformed_json(self):
        self.save()
        (self.run / "_work" / "evidence.json").write_text("{broken", encoding="utf-8")
        self.assertEqual(rt.audit_review(self.run)["status"], "NEEDS_REVISION")

    def test_wrong_nested_type_reported_not_crashed(self):
        self.ledger["claims"][0]["links"][0]["check_level"] = []
        self.assert_error("invalid check_level")

    def test_unfilled_placeholder(self):
        self.text += "\n{{INSERT_TEXT}}\n"
        self.assert_error("unresolved template placeholders")

    def test_citation_parser(self):
        self.assertEqual(rt.citation_numbers("[1, 3–5] [7](https://example.test) [^8] ![9](x)"), {1, 3, 4, 5})

    def test_cli_returns_nonzero_for_unready(self):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "cp1252"
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "review_tools.py"), "audit", str(self.run)],
            capture_output=True, text=True, encoding="utf-8", env=env,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["status"], "NEEDS_REVISION")


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / ".agents" / "skills"

    def test_install_to_temp(self):
        result = installer.install(self.root)
        self.assertTrue((Path(result["installed_to"]) / "SKILL.md").exists())

    def test_existing_install_not_overwritten(self):
        installer.install(self.root)
        with self.assertRaises(FileExistsError):
            installer.install(self.root)

    def test_replace_keeps_backup_outside_skill_scan(self):
        installer.install(self.root)
        result = installer.install(self.root, replace=True)
        backup = Path(result["backup"])
        self.assertTrue((backup / "SKILL.md").is_file())
        self.assertNotIn(self.root, backup.parents)
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_refuse_recursive_copy(self):
        with self.assertRaises(ValueError):
            installer.install(ROOT / "nested-test-root")


if __name__ == "__main__":
    unittest.main(verbosity=2)
