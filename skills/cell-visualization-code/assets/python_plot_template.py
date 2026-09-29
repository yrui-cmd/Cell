#!/usr/bin/env python3
"""Reusable long-form x/y/series plotting scaffold; adapt to the real study."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator


DEFAULT_STYLE: dict[str, Any] = {
    "font_families": ["STIXGeneral", "Times New Roman", "serif"],
    "typography": {
        "axis_label_pt": 8.5,
        "tick_pt": 8.0,
        "legend_pt": 7.5,
    },
    "strokes": {
        "main_pt": 1.25,
        "axes_pt": 0.8,
        "grid_pt": 0.5,
        "marker_pt": 3.5,
    },
}


def load_data(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def validate_data(rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError("Input data are empty.")
    required = {"x", "y", "series"}
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
    for index, row in enumerate(rows, 2):
        try:
            float(row["x"])
            float(row["y"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Row {index} has nonnumeric x/y values.") from exc
        if not row["series"].strip():
            raise ValueError(f"Row {index} has an empty series label.")


def compute_plot_data(rows: list[dict[str, str]]) -> dict[str, list[tuple[float, float]]]:
    grouped: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        grouped[row["series"]].append((float(row["x"]), float(row["y"])))
    return {name: sorted(values) for name, values in grouped.items()}


def load_style_profile(path: Path | None, placement: str, width_cm: float,
                       art_type: str) -> tuple[dict[str, Any], int]:
    if path is None:
        return DEFAULT_STYLE, 600
    profile = json.loads(path.read_text(encoding="utf-8-sig"))
    if profile.get("schema_version") != 1:
        raise ValueError("Style profile schema_version must be 1.")
    placements = profile.get("placements", {})
    if placement not in placements:
        raise ValueError(f"Placement {placement!r} is not defined by the style profile.")
    expected_width = placements[placement].get("width_cm")
    if not isinstance(expected_width, (int, float)) or isinstance(expected_width, bool):
        raise ValueError("The selected placement needs a numeric width_cm.")
    if abs(float(expected_width) - width_cm) > 0.01:
        raise ValueError(
            f"width_cm must be {expected_width:g} for placement {placement!r}; "
            "copy and document a journal-specific profile before overriding it."
        )
    dpi = profile.get("raster_dpi", {}).get(art_type)
    if not isinstance(dpi, int) or isinstance(dpi, bool) or dpi < 72:
        raise ValueError(f"No valid raster DPI for art type {art_type!r}.")
    return profile, dpi


def draw_figure(data: dict[str, list[tuple[float, float]]], width_cm: float,
                height_cm: float, style: dict[str, Any] = DEFAULT_STYLE) -> plt.Figure:
    fonts = style["font_families"]
    typography = style["typography"]
    strokes = style["strokes"]
    generic_family = "sans-serif" if "sans-serif" in fonts else "serif"
    with plt.rc_context({
        "font.family": generic_family,
        f"font.{generic_family}": fonts,
        "mathtext.fontset": "dejavusans" if generic_family == "sans-serif" else "stix",
        "axes.linewidth": strokes["axes_pt"],
    }):
        fig, ax = plt.subplots(
            figsize=(width_cm / 2.54, height_cm / 2.54), layout="constrained"
        )
        markers = ("o", "s", "^", "D", "v", "P")
        linestyles = ("-", "--", "-.", ":")
        for index, (name, values) in enumerate(data.items()):
            x, y = zip(*values)
            ax.plot(x, y, label=name, linewidth=strokes["main_pt"],
                    marker=markers[index % len(markers)], markersize=strokes["marker_pt"],
                    linestyle=linestyles[index % len(linestyles)])
        ax.set_xlabel("Verified x label (unit)",
                      fontsize=typography["axis_label_pt"])
        ax.set_ylabel("Verified y label (unit)",
                      fontsize=typography["axis_label_pt"])
        ax.xaxis.set_major_locator(MaxNLocator(nbins=5))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
        ax.tick_params(labelsize=typography["tick_pt"],
                       width=strokes["axes_pt"], direction="in")
        ax.grid(True, linestyle="--", linewidth=strokes["grid_pt"], alpha=0.3)
        ax.set_axisbelow(True)
        ax.legend(fontsize=typography["legend_pt"], frameon=True)
        return fig


def export_figure(fig: plt.Figure, output_stem: Path, dpi: int) -> None:
    output_stem.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_stem.with_suffix(".pdf"))
    fig.savefig(output_stem.with_suffix(".png"), dpi=dpi)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-stem", type=Path, required=True)
    parser.add_argument("--width-cm", type=float, required=True)
    parser.add_argument("--height-cm", type=float, required=True)
    parser.add_argument("--dpi", type=int)
    parser.add_argument("--style-profile", type=Path)
    parser.add_argument("--placement", default="single_column")
    parser.add_argument("--art-type", choices=("color_grayscale", "combination", "line_art"),
                        default="color_grayscale")
    args = parser.parse_args()
    if args.width_cm <= 0 or args.height_cm <= 0:
        raise ValueError("Physical dimensions must be positive.")
    style, recommended_dpi = load_style_profile(
        args.style_profile, args.placement, args.width_cm, args.art_type
    )
    dpi = args.dpi if args.dpi is not None else recommended_dpi
    if dpi < 72:
        raise ValueError("Physical dimensions must be positive and dpi must be at least 72.")
    rows = load_data(args.input)
    validate_data(rows)
    data = compute_plot_data(rows)
    fig = draw_figure(data, args.width_cm, args.height_cm, style)
    try:
        export_figure(fig, args.output_stem, dpi)
    finally:
        plt.close(fig)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
