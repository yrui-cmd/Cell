"""Install the Cell router and non-plugin member skills into Codex."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "skills"
PLUGIN_SKILL = "cell-ppt-edited"


def default_destination() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    return Path(codex_home).expanduser() / "skills" if codex_home else Path.home() / ".codex" / "skills"


def install(destination: Path, force: bool) -> list[str]:
    destination = destination.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []
    for source in sorted(SOURCE.iterdir()):
        if not source.is_dir() or source.name == PLUGIN_SKILL:
            continue
        if not (source / "SKILL.md").is_file():
            raise RuntimeError(f"Missing SKILL.md: {source}")
        target = destination / source.name
        if target.exists():
            if not force:
                raise RuntimeError(f"Skill already exists: {target}; rerun with --force to replace it")
            resolved_target = target.resolve()
            if not resolved_target.is_relative_to(destination):
                raise RuntimeError(f"Refusing to replace a path outside the destination: {target}")
            shutil.rmtree(resolved_target)
        shutil.copytree(
            source,
            target,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "runtime-profile.json"),
        )
        installed.append(source.name)
    return installed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=default_destination())
    parser.add_argument("--force", action="store_true", help="Replace existing Cell skill directories")
    args = parser.parse_args()
    installed = install(args.destination, args.force)
    print(f"INSTALLED|count={len(installed)}|destination={args.destination.expanduser().resolve()}")
    print("NEXT|codex plugin marketplace add .")
    print("NEXT|codex plugin add cell-ppt-edited@cell")
    print("Restart Codex and start a new task before first use.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
