#!/usr/bin/env python3
"""Validate a shared Python/MATLAB publisher style profile."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]*$")
TYPOGRAPHY_KEYS = ("title_pt", "axis_label_pt", "tick_pt", "legend_pt", "annotation_pt")
STROKE_KEYS = ("main_pt", "secondary_pt", "axes_pt", "grid_pt", "marker_pt")
ART_TYPES = ("color_grayscale", "combination", "line_art")
VECTOR_FORMATS = {"pdf", "eps", "svg"}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _positive(value: Any) -> bool:
    return type(value) in (int, float) and value > 0


def validate(profile: Any) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(profile, dict):
        return {"status": "BLOCKED", "errors": ["Profile root must be an object."],
                "warnings": []}

    if profile.get("schema_version") != 1:
        errors.append("schema_version must be 1.")
    if not _text(profile.get("id")) or not re.fullmatch(r"[a-z0-9-]+", profile["id"]):
        errors.append("id must contain lowercase letters, digits, or hyphens.")
    if not _text(profile.get("publisher")):
        errors.append("publisher must be nonempty.")
    if profile.get("scope") not in {"publisher_general", "journal_specific", "project_specific"}:
        errors.append("scope must describe the profile authority.")
    if type(profile.get("journal_specific_override_required")) is not bool:
        errors.append("journal_specific_override_required must be boolean.")
    try:
        date.fromisoformat(profile.get("verified_on", ""))
    except (TypeError, ValueError):
        errors.append("verified_on must be an ISO date.")

    urls = profile.get("source_urls")
    if not isinstance(urls, list) or not urls:
        errors.append("source_urls must be a nonempty list.")
    else:
        for value in urls:
            parsed = urlparse(value) if _text(value) else None
            if parsed is None or parsed.scheme != "https" or not parsed.netloc:
                errors.append("Every source URL must be an absolute HTTPS URL.")
                break

    placements = profile.get("placements")
    widths: list[float] = []
    if not isinstance(placements, dict) or not placements:
        errors.append("placements must be a nonempty object.")
    else:
        for name, value in placements.items():
            if not IDENTIFIER.fullmatch(name) or not isinstance(value, dict) \
                    or not _positive(value.get("width_cm")):
                errors.append("Every placement needs a valid identifier and positive width_cm.")
                break
            widths.append(float(value["width_cm"]))
        if len(widths) != len(set(widths)):
            errors.append("Placement widths must be unique.")

    fonts = profile.get("font_families")
    if not isinstance(fonts, list) or not fonts or any(not _text(value) for value in fonts):
        errors.append("font_families must be a nonempty string list.")

    typography = profile.get("typography")
    if not isinstance(typography, dict):
        errors.append("typography must be an object.")
        typography = {}
    for key in TYPOGRAPHY_KEYS:
        if not _positive(typography.get(key)):
            errors.append(f"typography.{key} must be positive.")
    if any(_positive(typography.get(key)) and typography[key] < 6 for key in TYPOGRAPHY_KEYS):
        warnings.append("A visible text size is below 6 pt; verify final-size readability.")

    strokes = profile.get("strokes")
    if not isinstance(strokes, dict):
        errors.append("strokes must be an object.")
        strokes = {}
    for key in STROKE_KEYS:
        if not _positive(strokes.get(key)):
            errors.append(f"strokes.{key} must be positive.")

    raster = profile.get("raster_dpi")
    if not isinstance(raster, dict):
        errors.append("raster_dpi must be an object.")
        raster = {}
    for key in ART_TYPES:
        value = raster.get(key)
        if type(value) is not int or value < 72:
            errors.append(f"raster_dpi.{key} must be an integer >=72.")

    vector = profile.get("vector_formats")
    if not isinstance(vector, list) or not vector or any(
            not _text(value) or value.lower() not in VECTOR_FORMATS for value in vector):
        errors.append("vector_formats must contain supported vector formats.")

    return {
        "status": "PASS" if not errors else "BLOCKED",
        "errors": errors,
        "warnings": warnings,
        "scope": "Style-profile structure only; journal-specific and rendered-output checks remain required.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profiles", nargs="+", type=Path)
    args = parser.parse_args()
    exit_code = 0
    for path in args.profiles:
        try:
            result = validate(json.loads(path.read_text(encoding="utf-8-sig")))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            result = {"status": "ERROR", "errors": [str(exc)], "warnings": []}
        print(json.dumps({"profile": str(path), **result}, ensure_ascii=False, indent=2))
        if result["status"] != "PASS":
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
