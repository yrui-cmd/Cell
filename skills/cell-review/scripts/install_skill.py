#!/usr/bin/env python3
"""Install this skill locally. No downloads, API calls, or package installations."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

NAME = "cell-review"
SOURCE = Path(__file__).resolve().parents[1]


def install(skills_root: Path, replace: bool = False) -> dict[str, str | None]:
    source = SOURCE.resolve()
    if not (source / "SKILL.md").is_file():
        raise ValueError("Cannot locate the bundled SKILL.md.")
    root = skills_root.expanduser().resolve()
    dest = root / NAME
    if source == dest or source in dest.parents:
        raise ValueError("Installation destination cannot be inside the source skill.")
    if dest.is_symlink():
        raise ValueError("Existing destination is a symlink; inspect it manually before replacing.")
    if dest.exists() and not replace:
        raise FileExistsError(f"Already exists: {dest}. Use --replace to back it up and replace it.")
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup: Path | None = None
    # Stage OUTSIDE the scanned skills root to avoid discovering duplicate skills.
    staging_root = root.parent / "skill-staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    staging = staging_root / f"{NAME}_{stamp}"
    shutil.copytree(source, staging, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
    try:
        if dest.exists():
            backup_root = root.parent / "skill-backups"
            backup_root.mkdir(parents=True, exist_ok=True)
            backup = backup_root / f"{NAME}_{stamp}"
            dest.rename(backup)
        staging.rename(dest)
    except OSError:
        if backup is not None and backup.exists() and not dest.exists():
            backup.rename(dest)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {"installed_to": str(dest), "backup": str(backup) if backup else None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-root", type=Path, default=Path.home() / ".agents" / "skills")
    parser.add_argument("--replace", action="store_true", help="Back up an existing installation outside the skills root")
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.skills_root, args.replace), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
