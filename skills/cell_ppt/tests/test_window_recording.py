import unittest
from pathlib import Path
import sys
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from window_recording import matches_preview_title, bound_window


class WindowBindingTests(unittest.TestCase):
    def test_hidden_extension_and_similarly_named_windows(self):
        for title in ("PPT-replay-123.pptx - PowerPoint", "PPT-replay-123 - PowerPoint"):
            self.assertTrue(matches_preview_title(title, "PPT-replay-123.pptx"))
        for title in ("PPT-replay-1234 - PowerPoint", "PPT-replay-123.pptx.bak - PowerPoint", "Other - PowerPoint"):
            self.assertFalse(matches_preview_title(title, "PPT-replay-123.pptx"))

    def test_bound_window_is_independent_of_focus_but_checks_run_and_pid(self):
        info = {"job_id": "job", "run_id": "run", "hwnd": 10, "pid": 20}
        state = {"job_id": "job", "run_id": "run", "copy": "PPT-replay-123.pptx"}
        gui = SimpleNamespace(IsWindow=lambda h: h == 10,
                              GetWindowText=lambda h: "PPT-replay-123 - PowerPoint")
        proc = SimpleNamespace(GetWindowThreadProcessId=lambda h: (1, 20))
        self.assertEqual(bound_window(info, state, gui, proc), 10)
        for field, value in (("run_id", "old"), ("job_id", "other"), ("hwnd", 11), ("pid", 21)):
            with self.assertRaises((RuntimeError, ValueError)):
                bound_window(dict(info, **{field: value}), state, gui, proc)
