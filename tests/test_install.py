import tempfile
from pathlib import Path

import pytest

from install import PLUGIN_SKILL, SOURCE, install


EXPECTED = {
    path.name
    for path in SOURCE.iterdir()
    if path.is_dir() and path.name != PLUGIN_SKILL
}


def test_install_copies_every_non_plugin_skill():
    with tempfile.TemporaryDirectory() as temp:
        destination = Path(temp)
        installed = install(destination, force=False)
        assert set(installed) == EXPECTED
        assert {path.name for path in destination.iterdir()} == EXPECTED
        assert all((destination / name / "SKILL.md").is_file() for name in EXPECTED)


def test_conflict_is_detected_before_any_skill_is_copied():
    with tempfile.TemporaryDirectory() as temp:
        destination = Path(temp)
        conflict = destination / "cell-review"
        conflict.mkdir()
        (conflict / "keep.txt").write_text("existing", encoding="utf-8")

        with pytest.raises(RuntimeError, match="Skill already exists"):
            install(destination, force=False)

        assert {path.name for path in destination.iterdir()} == {"cell-review"}
        assert (conflict / "keep.txt").read_text(encoding="utf-8") == "existing"


def test_force_replaces_skills_but_preserves_unrelated_content():
    with tempfile.TemporaryDirectory() as temp:
        destination = Path(temp)
        old = destination / "cell-review"
        old.mkdir()
        (old / "obsolete.txt").write_text("old", encoding="utf-8")
        unrelated = destination / "my-own-skill"
        unrelated.mkdir()
        (unrelated / "SKILL.md").write_text("personal", encoding="utf-8")

        install(destination, force=True)

        assert not (destination / "cell-review" / "obsolete.txt").exists()
        assert (destination / "cell-review" / "SKILL.md").is_file()
        assert (unrelated / "SKILL.md").read_text(encoding="utf-8") == "personal"


def test_force_refuses_symlink_that_resolves_outside_destination():
    with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
        destination = Path(temp)
        try:
            (destination / "cell").symlink_to(Path(outside), target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"Directory symlinks are unavailable for this test account: {exc}")

        with pytest.raises(RuntimeError, match="outside the destination"):
            install(destination, force=True)

        assert {path.name for path in destination.iterdir()} == {"cell"}
