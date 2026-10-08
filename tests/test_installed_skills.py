import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from install import install


FREE_SKILLS = {
    "cell",
    "cell-brainstorm",
    "cell-plan",
    "cell-review",
    "cell-reviewer",
    "cell-reviewer-response",
    "cell-submission",
    "cell-data-figure",
}
ENTRYPOINTS = (
    ("cell-brainstorm", "scripts/quality_gate.py"),
    ("cell-plan", "scripts/check_plan.py"),
    ("cell-plan", "scripts/check_delivery.py"),
    ("cell-review", "scripts/review_tools.py"),
    ("cell-review", "scripts/delivery_gate.py"),
    ("cell-reviewer-response", "scripts/reviewer_docs.py"),
    ("cell-submission", "scripts/preflight.py"),
    ("cell-data-figure", "scripts/figure_tools.py"),
)
LOCAL_PREFIXES = ("assets/", "config/", "prompts/", "references/", "schemas/", "scripts/", "templates/")


@pytest.fixture(scope="module")
def installed_root():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        install(root, force=False)
        yield root


def test_installed_free_skills_keep_all_entrypoint_links(installed_root):
    for name in FREE_SKILLS:
        skill_file = installed_root / name / "SKILL.md"
        text = skill_file.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^]]*\]\(([^)#]+)(?:#[^)]+)?\)", text):
            if target.startswith(LOCAL_PREFIXES):
                assert (skill_file.parent / target).exists(), f"Broken installed link: {name}/{target}"


@pytest.mark.parametrize(("skill", "relative"), ENTRYPOINTS)
def test_installed_cli_entrypoint_starts(installed_root, skill, relative):
    script = installed_root / skill / relative
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp1252"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=20,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()


def test_installed_data_figure_has_runtime_requirements(installed_root):
    requirements = installed_root / "cell-data-figure" / "requirements.txt"
    text = requirements.read_text(encoding="utf-8")
    for package in ("matplotlib", "numpy", "Pillow", "PyMuPDF"):
        assert re.search(rf"(?mi)^{re.escape(package)}(?:[<>=!~].*)?$", text)
