from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_profile import validate  # noqa: E402


def fixture() -> dict:
    return json.loads((ROOT / "assets" / "profile.example.json").read_text(encoding="utf-8"))


class ProfileTests(unittest.TestCase):
    def test_example_passes(self):
        self.assertEqual(validate(fixture())["status"], "PASS")

    def test_backend_controls_code_suffix(self):
        profile = fixture()
        profile["backend"] = "matlab"
        self.assertEqual(validate(profile)["status"], "BLOCKED")
        profile["outputs"]["code"] = "plot.m"
        profile["outputs"]["editable"] = ["figure.fig"]
        self.assertEqual(validate(profile)["status"], "PASS")

    def test_vector_requirement_is_enforced(self):
        profile = fixture()
        profile["target"]["formats"] = ["png"]
        profile["outputs"]["figures"] = ["figure.png"]
        self.assertTrue(any("vector-required" in item for item in validate(profile)["errors"]))

    def test_unsafe_and_overlapping_paths_are_blocked(self):
        profile = fixture()
        profile["inputs"][0]["path"] = "../raw.csv"
        self.assertEqual(validate(profile)["status"], "BLOCKED")
        profile = fixture()
        profile["outputs"]["code"] = "plot_data.csv"
        self.assertTrue(any("overwrite" in item for item in validate(profile)["errors"]))

    def test_boolean_is_not_a_numeric_size(self):
        profile = fixture()
        profile["target"]["width_cm"] = True
        self.assertEqual(validate(profile)["status"], "BLOCKED")

    def test_render_strategy_contract(self):
        profile = fixture()
        profile["target"]["display_width_cm"] = 17.8
        self.assertTrue(any("native_final_size" in item for item in validate(profile)["errors"]))
        profile["target"].update(render_strategy="scaled_source",
                                 tight_width_normalization=False)
        self.assertTrue(any("tight_width_normalization" in item
                            for item in validate(profile)["errors"]))
        profile["target"]["tight_width_normalization"] = True
        self.assertEqual(validate(profile)["status"], "PASS")

    def test_optional_root_checks_files(self):
        profile = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "plot_data.csv").write_text("x,y,series\n", encoding="utf-8")
            (root / "plot.py").write_text("pass\n", encoding="utf-8")
            result = validate(profile, root)
            self.assertTrue(any("Declared output is missing" in item
                                for item in result["errors"]))

    def test_secondary_line_warning_does_not_block(self):
        profile = fixture()
        profile["strokes"]["secondary_pt"] = 2
        result = validate(profile)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["warnings"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
