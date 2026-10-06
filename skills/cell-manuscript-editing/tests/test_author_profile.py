from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_author_profile import validate  # noqa: E402


def example() -> dict:
    return json.loads(
        (ROOT / "assets" / "author-style-profile.example.json").read_text(encoding="utf-8")
    )


class AuthorStyleProfileTests(unittest.TestCase):
    def test_example_passes(self):
        self.assertEqual(validate(example())["status"], "PASS")

    def test_invalid_mode_is_blocked(self):
        profile = example()
        profile["default_edit_mode"] = "write_from_scratch"
        self.assertEqual(validate(profile)["status"], "BLOCKED")

    def test_preferred_term_cannot_be_avoided(self):
        profile = example()
        profile["locked_terms"][0]["avoid"] = ["technical term"]
        result = validate(profile)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("preferred term" in error for error in result["errors"]))

    def test_rule_source_must_be_confirmed(self):
        profile = example()
        profile["confirmed_rules"][0]["source"] = "guessed"
        self.assertEqual(validate(profile)["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
