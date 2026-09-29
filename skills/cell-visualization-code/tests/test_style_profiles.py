from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_style_profile import validate  # noqa: E402


class PublisherStyleProfileTests(unittest.TestCase):
    def test_bundled_profiles_pass(self):
        for path in sorted((ROOT / "assets" / "styles").glob("*.json")):
            with self.subTest(profile=path.name):
                profile = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(validate(profile)["status"], "PASS")

    def test_missing_art_type_is_blocked(self):
        path = ROOT / "assets" / "styles" / "elsevier-general.json"
        profile = json.loads(path.read_text(encoding="utf-8"))
        del profile["raster_dpi"]["line_art"]
        result = validate(profile)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("line_art" in error for error in result["errors"]))

    def test_non_https_source_is_blocked(self):
        path = ROOT / "assets" / "styles" / "ieee-transactions.json"
        profile = json.loads(path.read_text(encoding="utf-8"))
        profile["source_urls"] = ["http://example.com"]
        self.assertEqual(validate(profile)["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
