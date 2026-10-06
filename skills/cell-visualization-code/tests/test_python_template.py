from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "python_plot_template.py"


class PythonTemplateTests(unittest.TestCase):
    def test_template_runs_and_exports_pdf_and_png(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "plot_data.csv"
            data.write_text(
                "x,y,series\n0,1,Method A\n1,2,Method A\n0,1.5,Method B\n1,1.8,Method B\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(TEMPLATE), "--input", str(data),
                 "--output-stem", str(root / "figure"),
                 "--width-cm", "8.89", "--height-cm", "6", "--dpi", "300"],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertGreater((root / "figure.pdf").stat().st_size, 0)
            self.assertGreater((root / "figure.png").stat().st_size, 0)

    def test_template_rejects_missing_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "bad.csv"
            data.write_text("x,value\n0,1\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(TEMPLATE), "--input", str(data),
                 "--output-stem", str(root / "figure"),
                 "--width-cm", "8.89", "--height-cm", "6"],
                capture_output=True, text=True, timeout=30,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "figure.pdf").exists())

    def test_publisher_profiles_control_style_width_and_default_dpi(self):
        cases = (
            ("ieee-transactions.json", "8.89", (2100, 1417)),
            ("elsevier-general.json", "9", (1063, 709)),
        )
        for profile_name, width_cm, expected_pixels in cases:
            with self.subTest(profile=profile_name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                output = root / "figure"
                result = subprocess.run(
                    [sys.executable, str(TEMPLATE),
                     "--input", str(ROOT / "tests" / "fixtures" / "basic_plot_data.csv"),
                     "--output-stem", str(output), "--width-cm", width_cm,
                     "--height-cm", "6", "--style-profile",
                     str(ROOT / "assets" / "styles" / profile_name),
                     "--placement", "single_column", "--art-type", "color_grayscale"],
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                actual_pixels = _png_dimensions(output.with_suffix(".png"))
                self.assertLessEqual(abs(actual_pixels[0] - expected_pixels[0]), 1)
                self.assertLessEqual(abs(actual_pixels[1] - expected_pixels[1]), 1)

    def test_publisher_profile_rejects_mismatched_width(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = subprocess.run(
                [sys.executable, str(TEMPLATE),
                 "--input", str(ROOT / "tests" / "fixtures" / "basic_plot_data.csv"),
                 "--output-stem", str(root / "figure"), "--width-cm", "8",
                 "--height-cm", "6", "--style-profile",
                 str(ROOT / "assets" / "styles" / "ieee-transactions.json")],
                capture_output=True, text=True, timeout=30,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("width_cm must be 8.89", result.stderr)


def _png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"not a valid PNG: {path}")
    return struct.unpack(">II", data[16:24])


if __name__ == "__main__":
    unittest.main(verbosity=2)
