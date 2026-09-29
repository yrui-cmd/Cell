import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(SKILL / "assets"))

from export_triplet import export_triplet  # noqa: E402
from figure_tools import (  # noqa: E402
    FINAL_CHECKS,
    REF_CHECKS,
    analyze_palette,
    command_compare,
    command_gate,
    command_publish,
    inspect_stage,
    sha256,
    verify_gate,
)


def observations(names):
    return {name: {"passed": True, "observation": f"Observed and verified {name}."} for name in names}


class FigureDeliveryTests(unittest.TestCase):
    dpi = 120

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.stage = self.root / "staging"
        self.stage.mkdir()
        (self.stage / "plot.py").write_text(
            "from pathlib import Path\nprint(Path(__file__).name)\n", encoding="utf-8"
        )
        (self.stage / "plot_data.csv").write_text("group,value\nA,1\nB,2\n", encoding="utf-8")

        from matplotlib.figure import Figure

        figure = Figure(figsize=(2, 1.5))
        axis = figure.subplots()
        axis.plot([0, 1], [1, 2], marker="o")
        axis.set(xlabel="Group", ylabel="Value", title="Example")
        export_triplet(figure, self.stage / "figure", dpi=self.dpi)

    def tearDown(self):
        self.temp.cleanup()

    def audit(self):
        return inspect_stage(self.stage, ["plot_data.csv"], ["figure"], self.dpi)

    def create_gate(self):
        reference_code = self.root / "reference_plot.py"
        reference_data = self.root / "reference_data.csv"
        reference_code.write_text("print('reference')\n", encoding="utf-8")
        reference_data.write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
        comparison_dir = self.root / "comparison"
        comparison = command_compare(SimpleNamespace(
            reference=self.stage / "figure.jpg",
            render=self.stage / "figure.jpg",
            code=reference_code,
            data=[reference_data],
            work=comparison_dir,
            max_side=600,
            reference_page=1,
            render_page=1,
        ))
        comparison_path = Path(comparison["comparison"])
        review_path = self.root / "reference_review.json"
        review_path.write_text(json.dumps({
            "kind": "reference_visual_review",
            "comparison_sha256": sha256(comparison_path),
            "actual_images_inspected": True,
            "data_driven_render": True,
            "source_verified": True,
            "code_executed": True,
            "no_material_mismatch": True,
            "execution_exit_code": 0,
            "execution_command": "python reference_plot.py",
            "data_origin": "reported_values",
            "unresolved": [],
            "checks": observations(REF_CHECKS),
            "target_figures": ["figure"],
            "reference": {
                "figure": "Figure 1",
                "locator": "doi:10.0000/example",
                "accessed": "2026-09-28",
            },
        }), encoding="utf-8")
        gate_path = self.root / "reference_gate.json"
        command_gate(SimpleNamespace(comparison=comparison_path, review=review_path, output=gate_path))
        return gate_path, reference_data

    def test_exported_triplet_passes_structural_audit(self):
        result = self.audit()
        self.assertTrue(result["structural_valid"])
        self.assertGreater(result["figures"]["figure"]["pdf_vector_objects"], 0)
        self.assertTrue(result["figures"]["figure"]["pdf_fonts"])
        self.assertEqual(len(result["artifacts"]), 5)

    def test_palette_diagnostic_never_auto_passes(self):
        result = analyze_palette(["#000", "#FFFFFF", "#0072B2"])
        self.assertFalse(result["automatic_accessibility_pass"])
        self.assertEqual(result["colors"][0]["contrast_against_background"], 21.0)
        self.assertEqual(len(result["pairs"]), 3)
        self.assertIn("deuteranopia", result["pairs"][0]["delta_e_76"])

    def test_duplicate_palette_color_is_exposed(self):
        result = analyze_palette(["#123456", "#123456"])
        self.assertEqual(result["pairs"][0]["delta_e_76"]["normal"], 0.0)

    def test_bad_palette_input_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "#RGB"):
            analyze_palette(["red", "#fff"])
        with self.assertRaisesRegex(ValueError, "at least two"):
            analyze_palette(["#fff"])

    def test_extra_delivery_file_is_rejected(self):
        (self.stage / "README.md").write_text("extra", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Delivery mismatch"):
            self.audit()

    def test_stale_gate_is_rejected_after_evidence_changes(self):
        gate_path, reference_data = self.create_gate()
        reference_data.write_text("x,y\n0,9\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Evidence changed after review"):
            verify_gate(gate_path)

    def test_full_gate_audit_and_publish_chain(self):
        gate_path, _ = self.create_gate()
        audit = self.audit()
        final_review = self.root / "final_review.json"
        final_review.write_text(json.dumps({
            "kind": "final_delivery_review",
            "artifacts": audit["artifacts"],
            "actual_formats_inspected": ["tif", "jpg", "pdf"],
            "unresolved": [],
            "checks": observations(FINAL_CHECKS),
            "rerun": {
                "isolated_code_and_data_only": True,
                "exit_code": 0,
                "outputs_match": True,
                "command": "python plot.py",
            },
        }), encoding="utf-8")
        destination = self.root / "final"
        result = command_publish(SimpleNamespace(
            stage=self.stage,
            destination=destination,
            gate=[gate_path],
            review=final_review,
            data=["plot_data.csv"],
            figures=["figure"],
            dpi=self.dpi,
        ))
        self.assertEqual(Path(result["published"]), destination)
        self.assertEqual({path.name for path in destination.iterdir()}, set(audit["artifacts"]))


if __name__ == "__main__":
    unittest.main()
