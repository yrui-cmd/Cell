#!/usr/bin/env python3
"""Validate a portable visualization-code profile; no rendering or scientific claims."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

BACKENDS = {"python": ".py", "matlab": ".m"}
MODES = {"new", "refactor", "audit"}
MEDIA = {"journal", "report", "presentation", "screen"}
PLACEMENTS = {"single_column", "double_column", "custom"}
RENDER_STRATEGIES = {"native_final_size", "scaled_source"}
FORMATS = {"pdf", "png", "tif", "tiff", "svg", "eps"}
VECTOR = {"pdf", "svg", "eps"}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def positive(value: Any) -> bool:
    return type(value) in (int, float) and value > 0


def safe_relative(value: Any) -> bool:
    if not text(value) or "\\" in value:
        return False
    path = PurePosixPath(value)
    return (not path.is_absolute() and ".." not in path.parts
            and bool(path.parts) and ":" not in path.parts[0])


def validate(profile: Any, root: Path | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(profile, dict):
        return {"status": "BLOCKED", "errors": ["Profile root must be an object."],
                "warnings": []}
    if profile.get("schema_version") != 1:
        errors.append("schema_version must be 1.")
    backend = profile.get("backend")
    if backend not in BACKENDS:
        errors.append("backend must be python or matlab.")
    if profile.get("mode") not in MODES:
        errors.append("mode must be new, refactor or audit.")

    target = profile.get("target")
    if not isinstance(target, dict):
        errors.append("target must be an object.")
        target = {}
    if target.get("medium") not in MEDIA:
        errors.append("target.medium is invalid.")
    if not text(target.get("venue")):
        errors.append("target.venue must identify the actual venue or project profile.")
    if target.get("placement") not in PLACEMENTS:
        errors.append("target.placement is invalid.")
    strategy = target.get("render_strategy")
    if strategy not in RENDER_STRATEGIES:
        errors.append("target.render_strategy is invalid.")
    for key in ("width_cm", "height_cm", "display_width_cm"):
        if not positive(target.get(key)):
            errors.append(f"target.{key} must be positive.")
    if type(target.get("tight_width_normalization")) is not bool:
        errors.append("target.tight_width_normalization must be boolean.")
    if (strategy == "native_final_size" and positive(target.get("width_cm"))
            and positive(target.get("display_width_cm"))
            and abs(target["width_cm"] - target["display_width_cm"]) > 0.01):
        errors.append("native_final_size requires source width_cm to equal display_width_cm.")
    if strategy == "scaled_source" and target.get("tight_width_normalization") is not True:
        errors.append("scaled_source requires tight_width_normalization=true.")
    if type(target.get("dpi")) is not int or target.get("dpi", 0) < 72:
        errors.append("target.dpi must be an integer >=72.")
    formats = target.get("formats")
    if (not isinstance(formats, list) or not formats
            or any(not text(item) or item.lower() not in FORMATS for item in formats)
            or len({item.lower() for item in formats if isinstance(item, str)}) != len(formats)):
        errors.append("target.formats must be a unique nonempty list of supported formats.")
        formats = []
    normalized_formats = {item.lower() for item in formats if isinstance(item, str)}
    if type(target.get("vector_required")) is not bool:
        errors.append("target.vector_required must be boolean.")
    elif target.get("vector_required") and not (normalized_formats & VECTOR):
        errors.append("A vector-required profile must declare pdf, svg or eps output.")

    typography = profile.get("typography")
    if not isinstance(typography, dict):
        errors.append("typography must be an object.")
        typography = {}
    families = typography.get("font_families")
    if not isinstance(families, list) or not families or any(not text(item) for item in families):
        errors.append("typography.font_families must be a nonempty string list.")
    for key in ("title_pt", "axis_label_pt", "tick_pt", "legend_pt", "annotation_pt"):
        if not positive(typography.get(key)):
            errors.append(f"typography.{key} must be positive.")

    strokes = profile.get("strokes")
    if not isinstance(strokes, dict):
        errors.append("strokes must be an object.")
        strokes = {}
    for key in ("main_pt", "secondary_pt", "axes_pt", "grid_pt"):
        if not positive(strokes.get(key)):
            errors.append(f"strokes.{key} must be positive.")
    if positive(strokes.get("main_pt")) and positive(strokes.get("secondary_pt")):
        if strokes["secondary_pt"] > strokes["main_pt"]:
            warnings.append("secondary_pt exceeds main_pt; confirm the intended hierarchy.")

    colors = profile.get("semantic_colors")
    if not isinstance(colors, dict) or not colors:
        errors.append("semantic_colors must be a nonempty role-to-color object.")
    else:
        for role, color in colors.items():
            if not text(role) or not isinstance(color, str) or not HEX.fullmatch(color):
                errors.append("semantic_colors requires nonempty roles and six-digit hex colors.")
                break

    inputs = profile.get("inputs")
    input_paths: list[str] = []
    if not isinstance(inputs, list) or not inputs:
        errors.append("inputs must be a nonempty list.")
    else:
        for index, item in enumerate(inputs):
            if (not isinstance(item, dict) or not safe_relative(item.get("path"))
                    or not text(item.get("role"))):
                errors.append(f"inputs[{index}] needs a safe relative path and nonempty role.")
                continue
            input_paths.append(item["path"])

    outputs = profile.get("outputs")
    output_paths: list[str] = []
    if not isinstance(outputs, dict):
        errors.append("outputs must be an object.")
        outputs = {}
    code = outputs.get("code")
    if not safe_relative(code):
        errors.append("outputs.code must be a safe relative path.")
    else:
        output_paths.append(code)
        if backend in BACKENDS and PurePosixPath(code).suffix.lower() != BACKENDS[backend]:
            errors.append(f"outputs.code must use {BACKENDS[backend]} for backend {backend}.")
    figures = outputs.get("figures")
    if not isinstance(figures, list) or not figures:
        errors.append("outputs.figures must be a nonempty list.")
    else:
        for index, value in enumerate(figures):
            if not safe_relative(value):
                errors.append(f"outputs.figures[{index}] must be a safe relative path.")
                continue
            suffix = PurePosixPath(value).suffix.lower().lstrip(".")
            if suffix not in normalized_formats:
                errors.append(f"outputs.figures[{index}] format is not declared in target.formats.")
            output_paths.append(value)
    editable = outputs.get("editable", [])
    if not isinstance(editable, list) or any(not safe_relative(value) for value in editable):
        errors.append("outputs.editable must be a list of safe relative paths.")
    else:
        output_paths.extend(editable)
        if backend == "python" and editable:
            warnings.append("Python editable outputs are unusual; verify they are real supported artifacts.")
        if backend == "matlab" and any(PurePosixPath(value).suffix.lower() != ".fig"
                                       for value in editable):
            warnings.append("MATLAB editable outputs normally use .fig; verify other formats.")
    all_paths = input_paths + output_paths
    if len(all_paths) != len(set(all_paths)):
        errors.append("Input and output paths must be unique and must not overwrite each other.")

    if root is not None:
        root = root.resolve()
        for value in input_paths:
            if not (root / value).is_file():
                errors.append(f"Declared input is missing: {value}")
        if safe_relative(code) and not (root / code).is_file():
            errors.append(f"Declared code is missing: {code}")
        for value in output_paths[1:]:
            if not (root / value).is_file():
                errors.append(f"Declared output is missing: {value}")

    return {"status": "PASS" if not errors else "BLOCKED",
            "errors": errors, "warnings": warnings,
            "scope": "Profile structure and optional file presence only; no rendering or scientific validation."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    try:
        profile = json.loads(args.profile.read_text(encoding="utf-8-sig"))
        result = validate(profile, args.root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "PASS" else 1
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)},
                         ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
