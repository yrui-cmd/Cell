from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from academic_prose_lint import lint_text  # noqa: E402
from check_manuscript_preservation import compare  # noqa: E402


class AcademicProseLintTests(unittest.TestCase):
    def test_flags_template_patterns_without_authorship_score(self):
        text = (
            "In recent years, this pivotal and groundbreaking landscape has changed. "
            "Moreover, the method serves as a crucial tool. Furthermore, it paves the way "
            "for new avenues, highlighting its importance."
        )
        codes = {issue["code"] for issue in lint_text(text)}
        self.assertIn("formulaic-opener", codes)
        self.assertIn("significance-inflation", codes)
        self.assertIn("transition-run", codes)
        self.assertIn("watch-word-cluster", codes)

    def test_legitimate_single_technical_word_is_not_a_cluster(self):
        issues = lint_text("The estimator is robust to the specified contamination model.")
        self.assertFalse(any(issue["code"] == "watch-word-cluster" for issue in issues))

    def test_fenced_code_is_not_linted(self):
        issues = lint_text("```text\nIt is worth noting that this paves the way.\n```")
        self.assertEqual(issues, [])


class PreservationTests(unittest.TestCase):
    def test_copy_edit_with_same_protected_tokens_passes(self):
        before = r"We tested 120 samples at 25 °C (Fig. 2; \cite{smith2024}); accuracy was 91.2%."
        after = r"At 25 °C, we tested 120 samples; accuracy was 91.2% (Fig. 2; \cite{smith2024})."
        self.assertEqual(compare(before, after)["status"], "PASS")

    def test_changed_number_and_figure_require_review(self):
        before = "We tested 120 samples (Fig. 2)."
        after = "We tested 125 samples (Fig. 3)."
        result = compare(before, after)
        self.assertEqual(result["status"], "REVIEW")
        categories = {item["category"] for item in result["differences"]}
        self.assertIn("number", categories)
        self.assertIn("cross_reference", categories)

    def test_semantic_limit_is_disclosed(self):
        self.assertIn("causality", compare("The result may hold.", "The result holds.")["scope"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
