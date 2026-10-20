#!/usr/bin/env python3
"""Require a successful independent update check before a customer workflow."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


RESTART_COUNT = "CELL_SU8_UPDATE_RESTARTS"
MAX_RESTARTS = 2


class UpdateGateError(RuntimeError):
    pass


def enforce_latest(entry, argv=None):
    """Return a restarted entry's exit code, or None when this code is current.

    There is no skip flag or persisted approval. Each entry runs the updater in
    its own Python process. A replacement entry must start in a fresh process.
    """
    entry = Path(entry).resolve()
    updater = Path(__file__).resolve().with_name("auto_update.py")
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not updater.is_file():
        raise UpdateGateError("The required Skill updater is missing; processing stopped before authentication or upload.")
    try:
        check = subprocess.run([sys.executable, "-X", "utf8", "-B", str(updater)],
            capture_output=True, text=True, encoding="utf-8", timeout=300)
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise UpdateGateError("The Skill update check could not complete; processing stopped before authentication or upload.") from None
    try:
        if len(check.stdout) > 1024 * 1024:
            raise ValueError()
        value = json.loads(check.stdout)
        if not isinstance(value, dict):
            raise ValueError()
        status = value.get("status")
    except (TypeError, ValueError):
        raise UpdateGateError("The Skill updater returned an invalid result; processing stopped before authentication or upload.") from None
    if check.returncode != 0 or status not in {"up_to_date", "updated"}:
        raise UpdateGateError("The latest Skill version could not be confirmed; processing stopped before authentication or upload.")
    if status == "up_to_date":
        return None
    try:
        count = int(os.environ.get(RESTART_COUNT, "0"))
        if not 0 <= count < MAX_RESTARTS:
            raise ValueError()
    except ValueError:
        raise UpdateGateError("The Skill changed repeatedly during this workflow; processing stopped without uploading.") from None
    environment = os.environ.copy()
    environment[RESTART_COUNT] = str(count + 1)
    try:
        result = subprocess.run([sys.executable, "-X", "utf8", "-B", str(entry), *arguments], env=environment)
    except (OSError, UnicodeError):
        raise UpdateGateError("The updated Skill could not restart; processing stopped before authentication or upload.") from None
    return result.returncode
