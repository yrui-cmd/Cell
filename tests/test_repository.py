import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SKILLS = {
    "cell",
    "cell-brainstorm",
    "cell-plan",
    "cell-review",
    "cell-reviewer-response",
    "cell-submission",
    "cell-data-figure",
    "cell_su7",
    "cell-cns-figure",
    "cell-ppt-edited",
}


def check_repository() -> None:
    actual = {path.name for path in (ROOT / "skills").iterdir() if path.is_dir()}
    if actual != EXPECTED_SKILLS:
        raise AssertionError(f"Unexpected skill set: missing={EXPECTED_SKILLS - actual}, extra={actual - EXPECTED_SKILLS}")
    for name in EXPECTED_SKILLS:
        if not (ROOT / "skills" / name / "SKILL.md").is_file():
            raise AssertionError(f"Missing SKILL.md: {name}")

    plugin = json.loads((ROOT / "plugins" / "cell-ppt-edited" / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    if plugin.get("name") != "cell-ppt-edited" or plugin.get("skills") != "./skills/":
        raise AssertionError("Invalid cell-ppt-edited plugin manifest")
    marketplace = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
    entry = marketplace["plugins"][0]
    if marketplace.get("name") != "cell" or entry.get("name") != "cell-ppt-edited":
        raise AssertionError("Invalid Cell marketplace identity")
    if entry["source"].get("path") != "./plugins/cell-ppt-edited":
        raise AssertionError("Invalid marketplace source path")

    tracked = subprocess.check_output(["git", "-C", str(ROOT), "ls-files"], text=True).splitlines()
    forbidden = [path for path in tracked if "__pycache__" in path or path.endswith((".pyc", ".pyo", "runtime-profile.json", ".dpapi"))]
    if forbidden:
        raise AssertionError(f"Generated or local files are tracked: {forbidden}")

    with tempfile.TemporaryDirectory() as temp:
        subprocess.run([sys.executable, str(ROOT / "install.py"), "--destination", temp], check=True)
        installed = {path.name for path in Path(temp).iterdir() if path.is_dir()}
        expected_installed = EXPECTED_SKILLS - {"cell-ppt-edited"}
        if installed != expected_installed:
            raise AssertionError(f"Installer mismatch: {installed}")


def test_repository_contract() -> None:
    check_repository()


if __name__ == "__main__":
    check_repository()
    print("REPOSITORY_OK|skills=10|plugin=cell-ppt-edited|installer=verified|tracked_artifacts=clean")
