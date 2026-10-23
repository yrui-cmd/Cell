"""Normal entrypoints work without invoking the optional updater."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh")


class OptionalUpdateTests(unittest.TestCase):
    def test_python_entries_ignore_failing_or_missing_updater(self):
        with tempfile.TemporaryDirectory(prefix="su8 optional update ") as temp:
            base = Path(temp)
            for name in ("update_gate.py", "run_cell_su8.py", "vectorize_xiaomiao.py", "no_ai_pro.py"):
                shutil.copy2(SCRIPTS / name, base / name)
            updater = base / "auto_update.py"
            updater.write_text("from pathlib import Path\nPath(__file__).with_name('unexpected-update').touch()\nraise SystemExit(99)\n", encoding="utf-8")
            for present in (True, False):
                if not present:
                    updater.unlink()
                for name in ("run_cell_su8.py", "vectorize_xiaomiao.py", "no_ai_pro.py"):
                    with self.subTest(updater_present=present, entry=name):
                        child = subprocess.run([sys.executable, "-X", "utf8", str(base / name), "--help"], capture_output=True, text=True, timeout=20)
                        self.assertEqual(child.returncode, 0, child.stderr + child.stdout)
                        self.assertIn("usage:", child.stdout)
                        self.assertFalse((base / "unexpected-update").exists())

    @unittest.skipUnless(POWERSHELL, "PowerShell unavailable")
    def test_powershell_entry_reaches_backend_without_update_or_restart(self):
        with tempfile.TemporaryDirectory(prefix="su8 optional update ") as temp:
            base = Path(temp)
            for name in ("update_gate.ps1", "run_cell_su8.ps1"):
                shutil.copy2(SCRIPTS / name, base / name)
            (base / "auto_update.py").write_text("from pathlib import Path\nPath(__file__).with_name('unexpected-update').touch()\nraise SystemExit(99)\n", encoding="utf-8")
            (base / "run_from_image.ps1").write_text("param($InputImage,$OutputRoot,$EstimatedCredits,[switch]$ApproveHighCost)\nif ($InputImage -ne 'reference.png' -or $EstimatedCredits -ne 3 -or -not $ApproveHighCost) {exit 9}\nWrite-Output 'BACKEND_REACHED'\n", encoding="utf-8-sig")
            child = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(base / "run_cell_su8.ps1"), "-InputImage", "reference.png", "-OutputRoot", str(base / "output"), "-Application", "ppt", "-EstimatedCredits", "3", "-ApproveHighCost"], capture_output=True, text=True, timeout=30)
            self.assertEqual(child.returncode, 0, child.stderr + child.stdout)
            self.assertIn("BACKEND_REACHED", child.stdout)
            self.assertFalse((base / "unexpected-update").exists())


if __name__ == "__main__":
    unittest.main()
