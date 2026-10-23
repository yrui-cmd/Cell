#!/usr/bin/env python3
"""Compatibility hook: normal workflows use the installed Skill without updating.

Run auto_update.py explicitly to check or install updates.
"""
from __future__ import annotations


class UpdateGateError(RuntimeError):
    """Retained for compatibility with existing entrypoint imports."""


def enforce_latest(entry, argv=None):
    """Continue locally without network checks, subprocesses or restarts."""
    return None
