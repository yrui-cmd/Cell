"""Offline update-entry gating; fake updaters never access the network."""
from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import update_gate as gate


def load_script(name):
    spec = importlib.util.spec_from_file_location("su8_gate_test_" + name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def completed(status="up_to_date", code=0):
    return subprocess.CompletedProcess([], code, json.dumps({"status": status}), "")


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="su8 gate ")
        self.base = Path(self.temp.name)
        self.entry = self.base / "entry file.py"

    def tearDown(self):
        self.temp.cleanup()

    def test_current_check_is_an_independent_updater_process_without_skip_or_check_flag(self):
        with patch.object(gate.subprocess, "run", return_value=completed()) as run:
            self.assertIsNone(gate.enforce_latest(self.entry, ["--input", "图 1.png"]))
        command = run.call_args.args[0]
        self.assertEqual(command, [sys.executable, "-X", "utf8", "-B", str(SCRIPTS / "auto_update.py")])
        self.assertNotIn("--check", command)
        self.assertTrue(run.call_args.kwargs["capture_output"])
        self.assertEqual(run.call_count, 1)

    def test_update_failure_unknown_status_or_check_only_result_fails_closed(self):
        for answer in [completed("unavailable", 1), completed("up_to_date", 1),
                       completed("update_available"), completed("future_status")]:
            with self.subTest(answer=answer.stdout), \
                 patch.object(gate.subprocess, "run", return_value=answer) as run, \
                 self.assertRaises(gate.UpdateGateError):
                gate.enforce_latest(self.entry)
            self.assertEqual(run.call_count, 1)

    def test_invalid_or_non_object_updater_output_fails_closed(self):
        for body in ["", "not JSON", '[]', '[{"status":"up_to_date"}]', '"up_to_date"']:
            with self.subTest(body=body), patch.object(gate.subprocess, "run",
                    return_value=subprocess.CompletedProcess([], 0, body, "")), \
                    self.assertRaises(gate.UpdateGateError):
                gate.enforce_latest(self.entry)

    def test_updater_subprocess_timeout_or_launch_error_fails_closed(self):
        for error in [OSError("fake launch error"), subprocess.TimeoutExpired("fake updater", 300)]:
            with self.subTest(error=type(error).__name__), \
                 patch.object(gate.subprocess, "run", side_effect=error), \
                 self.assertRaises(gate.UpdateGateError):
                gate.enforce_latest(self.entry)

    def test_updater_decode_failure_is_a_fixed_closed_gate_error(self):
        error = UnicodeDecodeError("utf-8", b"\xd6\xd0", 0, 1, "fake non-UTF locale output")
        with patch.object(gate.subprocess, "run", side_effect=error) as run, \
             self.assertRaisesRegex(gate.UpdateGateError, "processing stopped before authentication or upload"):
            gate.enforce_latest(self.entry)
        self.assertEqual(run.call_count, 1)

    def test_real_updater_with_non_utf_parent_mode_can_emit_actual_chinese_json(self):
        shutil.copy2(SCRIPTS / "update_gate.py", self.base / "update_gate.py")
        (self.base / "auto_update.py").write_text(
            "import json, sys\nfrom pathlib import Path\n"
            "Path(__file__).with_name('encoding.json').write_text(json.dumps({'stdout_encoding':sys.stdout.encoding,'utf8_mode':sys.flags.utf8_mode}),encoding='utf-8')\n"
            "print(json.dumps({'status':'up_to_date','note':'中文版本已确认'},ensure_ascii=False))\n",
            encoding="utf-8")
        spec = importlib.util.spec_from_file_location("su8_locale_gate", self.base / "update_gate.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        environment = os.environ.copy()
        environment.pop("PYTHONIOENCODING", None)
        environment["PYTHONUTF8"] = "0"
        with patch.dict(os.environ, environment, clear=True):
            self.assertIsNone(module.enforce_latest(self.entry, ["--image", "中文 图.png"]))
        actual = json.loads((self.base / "encoding.json").read_text(encoding="utf-8"))
        self.assertEqual(actual["utf8_mode"], 1)
        self.assertEqual(actual["stdout_encoding"].lower().replace("-", ""), "utf8")

    def test_missing_updater_fails_before_any_child(self):
        with patch.object(gate.Path, "is_file", return_value=False), \
             patch.object(gate.subprocess, "run") as run, self.assertRaises(gate.UpdateGateError):
            gate.enforce_latest(self.entry)
        run.assert_not_called()

    def test_updated_restarts_entry_in_fresh_process_with_original_arguments_and_real_exit(self):
        arguments = ["--input-image", "F:/科研 图/原图 1.png", "--output-root", "F:/结果 目录", "--approve-high-cost"]
        with patch.dict(os.environ, {gate.RESTART_COUNT: "0"}), \
             patch.object(gate.subprocess, "run", side_effect=[completed("updated"),
                 subprocess.CompletedProcess([], 19)]) as run:
            self.assertEqual(gate.enforce_latest(self.entry, arguments), 19)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[1].args[0], [sys.executable, "-X", "utf8", "-B", str(self.entry), *arguments])
        self.assertEqual(run.call_args_list[1].kwargs["env"][gate.RESTART_COUNT], "1")

    def test_restart_count_bounds_repeated_updates_but_never_skips_the_check(self):
        with patch.dict(os.environ, {gate.RESTART_COUNT: "2"}), \
             patch.object(gate.subprocess, "run", return_value=completed("updated")) as run, \
             self.assertRaises(gate.UpdateGateError):
            gate.enforce_latest(self.entry)
        self.assertEqual(run.call_count, 1)
        with patch.dict(os.environ, {gate.RESTART_COUNT: "2"}), \
             patch.object(gate.subprocess, "run", return_value=completed()) as run:
            self.assertIsNone(gate.enforce_latest(self.entry))
        self.assertEqual(run.call_count, 1)

    def test_python_selectors_stop_before_backend_or_credentials_when_check_fails(self):
        for name in ["run_cell_su8", "vectorize_xiaomiao"]:
            module = load_script(name)
            with self.subTest(name=name), patch.object(module, "enforce_latest",
                    side_effect=gate.UpdateGateError("offline update unavailable")), \
                    patch.object(module.subprocess, "run") as child, \
                    patch.object(module.sys, "stdout", io.StringIO()):
                if hasattr(module, "call"):
                    with patch.object(module, "call") as adapter:
                        self.assertEqual(module.main([]), 1)
                        adapter.assert_not_called()
                else:
                    self.assertEqual(module.main([]), 1)
                child.assert_not_called()

    def test_python_selectors_return_restarted_entry_exit_without_old_processing(self):
        for name in ["run_cell_su8", "vectorize_xiaomiao"]:
            module = load_script(name)
            with self.subTest(name=name), patch.object(module, "enforce_latest", return_value=23), \
                    patch.object(module.subprocess, "run") as child:
                self.assertEqual(module.main([]), 23)
                child.assert_not_called()

    def test_real_python_relaunch_loads_replacement_entry_and_preserves_unicode_arguments(self):
        shutil.copy2(SCRIPTS / "update_gate.py", self.base / "update_gate.py")
        self.entry.write_text(
            "from pathlib import Path\nimport json, os, sys\nfrom update_gate import enforce_latest\n"
            "VERSION = 'old'\ncode = enforce_latest(__file__)\n"
            "if code is not None: raise SystemExit(code)\n"
            "Path(__file__).with_name('result.json').write_text(json.dumps({'version':VERSION,'args':sys.argv[1:],'pid':os.getpid()}),encoding='utf-8')\n"
            "raise SystemExit(17)\n", encoding="utf-8")
        (self.base / "auto_update.py").write_text(
            "from pathlib import Path\nimport json, os\nb = Path(__file__).parent\nm = b/'marker.json'\n"
            "if not m.exists():\n"
            " m.write_text(json.dumps({'parent_pid':os.getppid()}))\n"
            " p=b/'entry file.py'\n p.write_text(p.read_text(encoding='utf-8').replace(\"VERSION = 'old'\",\"VERSION = 'new'\"),encoding='utf-8')\n"
            " print(json.dumps({'status':'updated'}))\n"
            "else: print(json.dumps({'status':'up_to_date'}))\n", encoding="utf-8")
        arguments = ["--image", "F:/科研 图/原图 1.png", "--output", "F:/结果 目录"]
        environment = os.environ.copy()
        environment.pop(gate.RESTART_COUNT, None)
        child = subprocess.run([sys.executable, "-B", str(self.entry), *arguments],
                               env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(child.returncode, 17, child.stderr)
        result = json.loads((self.base / "result.json").read_text(encoding="utf-8"))
        marker = json.loads((self.base / "marker.json").read_text())
        self.assertEqual(result["version"], "new")
        self.assertEqual(result["args"], arguments)
        self.assertNotEqual(result["pid"], marker["parent_pid"])


POWERSHELL = shutil.which("powershell.exe") or shutil.which("powershell")


@unittest.skipUnless(POWERSHELL, "Windows PowerShell is unavailable")
class PowerShellGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="su8 PS gate ")
        self.base = Path(self.temp.name) / "中文 空格"
        self.base.mkdir()
        shutil.copy2(SCRIPTS / "update_gate.ps1", self.base / "update_gate.ps1")
        self.environment = os.environ.copy()
        self.environment.pop(gate.RESTART_COUNT, None)

    def tearDown(self):
        self.temp.cleanup()

    def run_ps(self, script, *arguments):
        return subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                               *arguments], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=self.environment, timeout=45)

    def fake_updater(self, *, fail=False):
        if fail:
            content = "import json\nprint(json.dumps({'status':'unavailable'}))\nraise SystemExit(1)\n"
        else:
            content = (
                "from pathlib import Path\nimport json, os\np=Path(__file__).with_name('updates.json')\n"
                "v=json.loads(p.read_text()) if p.exists() else {'count':0,'first_parent_pid':os.getppid()}\n"
                "v['count']+=1\np.write_text(json.dumps(v))\n"
                "print(json.dumps({'status':'updated' if v['count']==1 else 'up_to_date'}))\n")
        (self.base / "auto_update.py").write_text(content, encoding="utf-8")

    def test_powershell_scripts_parse_under_windows_powershell_51(self):
        parser = self.base / "parse.ps1"
        parser.write_text(
            "param([string]$Root)\n$ErrorActionPreference='Stop'\n$count=0\n"
            "foreach($name in @('update_gate.ps1','run_cell_su8.ps1','vectorize-xiaomiao.ps1')) {\n"
            " $tokens=$null; $issues=$null\n"
            " [void][System.Management.Automation.Language.Parser]::ParseFile((Join-Path $Root $name),[ref]$tokens,[ref]$issues)\n"
            " if($issues.Count -gt 0) { $issues | Out-String | Write-Host; exit 1 }; $count++\n"
            "}\nWrite-Output $count\n", encoding="utf-8-sig")
        child = self.run_ps(parser, "-Root", str(SCRIPTS))
        self.assertEqual(child.returncode, 0, child.stderr + child.stdout)
        self.assertIn("3", child.stdout)

    def test_real_powershell_restart_preserves_bound_unicode_paths_switches_and_exit(self):
        self.fake_updater()
        entry = self.base / "entry script.ps1"
        entry.write_text(
            "[CmdletBinding()]\nparam([string]$InputImage,[string]$OutputRoot,[switch]$ApproveHighCost,[switch]$ExplicitFalse,[int]$EstimatedCredits,[uri]$BaseUrl)\n"
            "$ErrorActionPreference='Stop'\n$entryArgs=@{}\nforeach($key in $PSBoundParameters.Keys){$entryArgs[$key]=$PSBoundParameters[$key]}\n"
            "$entryPath=$PSCommandPath\n. (Join-Path $PSScriptRoot 'update_gate.ps1')\n"
            "$code=Invoke-CellSu8UpdateGate -EntryScript $entryPath -BoundParameters $entryArgs\n"
            "if($null -ne $code){exit [int]$code}\n"
            "$v=@{input=$InputImage;output=$OutputRoot;approved=[bool]$ApproveHighCost;explicitFalse=[bool]$ExplicitFalse;falseWasBound=$PSBoundParameters.ContainsKey('ExplicitFalse');estimated=$EstimatedCredits;baseUrl=$BaseUrl.OriginalString;pid=$PID}\n"
            "[IO.File]::WriteAllText($OutputRoot,($v|ConvertTo-Json -Compress),(New-Object Text.UTF8Encoding($true)))\nexit 7\n",
            encoding="utf-8-sig")
        wrapper = self.base / "wrapper.ps1"
        wrapper.write_text(
            "param([string]$InputValue,[string]$OutputFile)\n$ErrorActionPreference='Stop'\n"
            "$v=@{InputImage=$InputValue;OutputRoot=$OutputFile;ApproveHighCost=[switch]$true;ExplicitFalse=[switch]$false;EstimatedCredits=3;BaseUrl=[uri]'https://xiaomiao-ai.com'}\n"
            "& (Join-Path $PSScriptRoot 'entry script.ps1') @v\nexit [int]$LASTEXITCODE\n", encoding="utf-8-sig")
        source = "F:/科研 图/原图 1.png"
        output = self.base / "结果 文件.json"
        child = self.run_ps(wrapper, "-InputValue", source, "-OutputFile", str(output))
        self.assertEqual(child.returncode, 7, child.stdout + child.stderr)
        value = json.loads(output.read_text(encoding="utf-8-sig"))
        updates = json.loads((self.base / "updates.json").read_text())
        self.assertEqual(value["input"], source)
        self.assertEqual(value["output"], str(output))
        self.assertTrue(value["approved"])
        self.assertFalse(value["explicitFalse"])
        self.assertTrue(value["falseWasBound"])
        self.assertEqual(value["estimated"], 3)
        self.assertEqual(value["baseUrl"], "https://xiaomiao-ai.com")
        self.assertEqual(updates["count"], 2)
        self.assertNotEqual(value["pid"], updates["first_parent_pid"])

    def test_failed_powershell_gate_blocks_both_canonical_entries_before_backend(self):
        self.fake_updater(fail=True)
        for script, arguments in [
            ("run_cell_su8.ps1", ["-InputImage", "missing.png", "-OutputRoot", str(self.base / "never output"), "-Application", "ppt"]),
            ("vectorize-xiaomiao.ps1", ["-InputImage", "missing.png", "-OutputSvg", str(self.base / "never output.svg")])]:
            shutil.copy2(SCRIPTS / script, self.base / script)
            child = self.run_ps(self.base / script, *arguments)
            self.assertNotEqual(child.returncode, 0, script)
            self.assertIn("latest Skill version could not be confirmed", child.stdout + child.stderr)
        self.assertFalse((self.base / "never output").exists())
        self.assertFalse((self.base / "never output.svg").exists())


if __name__ == "__main__":
    unittest.main()
