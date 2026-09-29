from __future__ import annotations

import os
import re
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "matlab_plot_template.m"
FIXTURE = ROOT / "tests" / "fixtures" / "basic_plot_data.csv"


class MatlabTemplateContractTests(unittest.TestCase):
    def test_primary_function_matches_file_name(self):
        source = TEMPLATE.read_text(encoding="utf-8")
        match = re.search(r"(?m)^function\s+([A-Za-z]\w*)\s*\(", source)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), TEMPLATE.stem)

    def test_template_has_no_machine_specific_absolute_path(self):
        source = TEMPLATE.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"[A-Za-z]:\\|/home/|/Users/", source))

    def test_template_uses_explicit_input_and_vector_export(self):
        source = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("readtable(inputCsv", source)
        self.assertIn("jsondecode(fileread(path))", source)
        self.assertIn("ContentType=\"vector\"", source)
        self.assertIn("Width=widthCm", source)
        self.assertIn("Height=heightCm", source)
        self.assertIn("Padding=\"figure\"", source)
        self.assertIn("savefig(fig", source)

    @unittest.skipUnless(
        os.environ.get("MATLAB_BIN"),
        "set MATLAB_BIN to run the real MATLAB rendering check",
    )
    def test_template_renders_publisher_profiles_at_requested_physical_size(self):
        matlab_bin = os.environ["MATLAB_BIN"]

        with tempfile.TemporaryDirectory() as temporary_directory:
            ieee_stem = Path(temporary_directory) / "ieee"
            elsevier_stem = Path(temporary_directory) / "elsevier"
            styles = ROOT / "assets" / "styles"
            matlab_command = (
                f"addpath('{_matlab_quote(TEMPLATE.parent)}'); "
                f"matlab_plot_template('{_matlab_quote(FIXTURE)}', "
                f"'{_matlab_quote(ieee_stem)}', 8.89, 6, 0, "
                f"'{_matlab_quote(styles / 'ieee-transactions.json')}', "
                "'single_column', 'color_grayscale'); "
                f"matlab_plot_template('{_matlab_quote(FIXTURE)}', "
                f"'{_matlab_quote(elsevier_stem)}', 9, 6, 0, "
                f"'{_matlab_quote(styles / 'elsevier-general.json')}', "
                "'single_column', 'color_grayscale');"
            )
            completed = subprocess.run(
                [matlab_bin, "-batch", matlab_command],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )

            self.assertEqual(
                completed.returncode,
                0,
                msg=f"MATLAB failed:\n{completed.stdout}\n{completed.stderr}",
            )
            for output_stem in (ieee_stem, elsevier_stem):
                for suffix in (".pdf", ".png", ".fig"):
                    output_path = output_stem.with_suffix(suffix)
                    self.assertTrue(output_path.is_file(), output_path)
                    self.assertGreater(output_path.stat().st_size, 0)

            ieee_width, ieee_height = _png_dimensions(ieee_stem.with_suffix(".png"))
            self.assertLessEqual(abs(ieee_width - 2100), 2)
            self.assertLessEqual(abs(ieee_height - 1417), 2)
            elsevier_width, elsevier_height = _png_dimensions(
                elsevier_stem.with_suffix(".png")
            )
            self.assertLessEqual(abs(elsevier_width - 1063), 2)
            self.assertLessEqual(abs(elsevier_height - 709), 2)


def _matlab_quote(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def _png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"not a valid PNG: {path}")
    return struct.unpack(">II", data[16:24])


if __name__ == "__main__":
    unittest.main(verbosity=2)
