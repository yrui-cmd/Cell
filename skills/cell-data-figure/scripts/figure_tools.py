#!/usr/bin/env python3
"""Local evidence, gate and delivery checks. Never executes research code.

Python >=3.10; pip install pillow numpy pymupdf
Commands: compare, gate, check-gate, audit, publish. Run COMMAND --help.
All comparison/review JSON and previews belong in temporary work, not final/.
Metrics are diagnostic, NOT an automatic judgement of visual equivalence.
Gate files record the host's review; they cannot prove that a model looked at a
figure, or mathematically certify scientific correctness or perceptual identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import sys
import tempfile
from pathlib import Path

NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]*$')
REF_CHECKS = ('layout', 'axes', 'marks', 'typography', 'data_geometry', 'annotations')
FINAL_CHECKS = ('data_integrity', 'statistics', 'visual_layout', 'format_consistency',
                'vector_pdf', 'clean_rerun')
DATA_EXTS = {'.csv', '.tsv', '.parquet', '.npz', '.npy', '.h5', '.h5ad', '.mtx'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink(), f'Not a regular file: {p}')
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def file_record(path):
    p = Path(path).expanduser().resolve(strict=True)
    return {'path': str(p), 'sha256': sha256(p)}


def check_records(records):
    require(isinstance(records, list) and records, 'Missing file evidence')
    for item in records:
        require(sha256(item['path']) == item['sha256'],
                f'Evidence changed after review: {item["path"]}')


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_new_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def check_observations(checks, names):
    require(isinstance(checks, dict), 'checks must be an object')
    for name in names:
        item = checks.get(name, {})
        require(item.get('passed') is True, f'Check has not passed: {name}')
        note = item.get('observation', '')
        require(isinstance(note, str) and len(note.strip()) >= 8,
                f'Missing concrete observation: {name}')


def open_rgb(path, page=1):
    from PIL import Image, ImageOps
    p = Path(path)
    if p.suffix.lower() == '.pdf':
        import fitz
        with fitz.open(p) as doc:
            require(1 <= page <= len(doc), f'PDF page out of range: {page}')
            pix = doc[page - 1].get_pixmap(dpi=160, alpha=False, colorspace=fitz.csRGB)
            return Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    with Image.open(p) as image:
        image = ImageOps.exif_transpose(image).convert('RGBA')
        background = Image.new('RGBA', image.size, 'white')
        background.alpha_composite(image)
        return background.convert('RGB')


def command_compare(args):
    import numpy as np
    from PIL import Image, ImageChops, ImageEnhance, ImageFilter
    work = Path(args.work).expanduser()
    require(not work.exists(), 'Use a NEW comparison work directory for each iteration')
    require(128 <= args.max_side <= 2400, 'max-side must be between 128 and 2400')
    require(args.code.suffix == '.py', 'Reference code must be a Python file')
    evidence = [file_record(p) for p in [args.reference, args.render, args.code, *args.data]]
    reference = open_rgb(args.reference, args.reference_page)
    rendered = open_rgb(args.render, args.render_page)
    require(min(*reference.size, *rendered.size) > 1, 'Empty or invalid image dimensions')
    aspect_error = abs((rendered.width / rendered.height) /
                       (reference.width / reference.height) - 1)
    require(reference.size != (0, 0), 'Empty reference')
    scale = min(1.0, args.max_side / max(reference.size))
    target = tuple(max(1, round(v * scale)) for v in reference.size)
    # Rendered image is resized only uniformly, with padding, never anisotropically.
    ref = reference.resize(target, Image.Resampling.LANCZOS)
    factor = min(target[0] / rendered.width, target[1] / rendered.height)
    newsize = tuple(max(1, round(v * factor)) for v in rendered.size)
    ren = Image.new('RGB', target, 'white')
    ren.paste(rendered.resize(newsize, Image.Resampling.LANCZOS),
              ((target[0] - newsize[0]) // 2, (target[1] - newsize[1]) // 2))
    a, b = np.asarray(ref, dtype=np.float32), np.asarray(ren, dtype=np.float32)
    mask = (a.min(axis=2) < 245) | (b.min(axis=2) < 245)
    diff = np.abs(a - b).mean(axis=2) / 255.0
    ea = np.asarray(ref.convert('L').filter(ImageFilter.FIND_EDGES), dtype=float)
    eb = np.asarray(ren.convert('L').filter(ImageFilter.FIND_EDGES), dtype=float)
    edges = (ea > 30) | (eb > 30)
    if edges.shape[0] > 2 and edges.shape[1] > 2:
        edges[[0, -1], :] = False
        edges[:, [0, -1]] = False
    metrics = {'aspect_relative_error': float(aspect_error),
               'foreground_mean_absolute_difference': float(diff[mask].mean()) if mask.any() else None,
               'edge_mean_absolute_difference': float(np.abs(ea - eb)[edges].mean() / 255) if edges.any() else None,
               'comparison_size_px': list(target),
               'reference_original_px': list(reference.size),
               'render_original_px': list(rendered.size),
               'automatic_visual_pass': False}
    work.mkdir(parents=True)
    side = Image.new('RGB', (target[0] * 2, target[1]), 'white')
    side.paste(ref, (0, 0)); side.paste(ren, (target[0], 0))
    side.save(work / 'side_by_side.png')
    Image.blend(ref, ren, 0.5).save(work / 'overlay.png')
    ImageEnhance.Contrast(ImageChops.difference(ref, ren)).enhance(3).save(work / 'difference.png')
    preview_records = [file_record(work / n) for n in ('side_by_side.png', 'overlay.png', 'difference.png')]
    report = {'schema': 1, 'kind': 'reference_comparison', 'metrics': metrics,
              'inputs': evidence, 'previews': preview_records,
              'reference_page': args.reference_page, 'render_page': args.render_page,
              'note': 'Diagnostic only. Host must actually inspect reference and rendered figures.'}
    write_new_json(work / 'comparison.json', report)
    return {'comparison': str((work / 'comparison.json').resolve()), 'metrics': metrics}


def command_gate(args):
    comp = load_json(args.comparison)
    review = load_json(args.review)
    require(comp.get('kind') == 'reference_comparison', 'Invalid comparison artifact')
    check_records(comp['inputs']); check_records(comp['previews'])
    require(review.get('kind') == 'reference_visual_review', 'Wrong review kind')
    require(review.get('comparison_sha256') == sha256(args.comparison), 'Review is stale or references another comparison')
    for key in ('actual_images_inspected', 'data_driven_render', 'source_verified',
                'code_executed', 'no_material_mismatch'):
        require(review.get(key) is True, f'Review requirement not met: {key}')
    require(review.get('execution_exit_code') == 0, 'Reference program did not execute successfully')
    require(review.get('data_origin') in ('author_source', 'reported_values', 'digitized_approximate'),
            'Simulated or invented reference data cannot pass the reproduction gate')
    require(review.get('unresolved') == [], 'Unresolved reference differences remain')
    check_observations(review.get('checks'), REF_CHECKS)
    targets = review.get('target_figures', [])
    require(isinstance(targets, list) and targets and len(set(targets)) == len(targets)
            and all(isinstance(x, str) and NAME.fullmatch(x) for x in targets), 'Invalid target_figures')
    source = review.get('reference', {})
    require(isinstance(source, dict) and source.get('figure') and source.get('locator')
            and source.get('accessed'), 'Missing actual reference locator/figure/access date')
    require(isinstance(review.get('execution_command'), str) and review['execution_command'].strip(),
            'Missing executed reference command')
    # Only the actual aspect ratio has a default hard tolerance. This is not a
    # universal scientific standard, nor a replacement for perceptual review.
    require(comp['metrics']['aspect_relative_error'] <= 0.01,
            'Aspect ratio differs by more than 1%; correct reference crop or canvas')
    gate = {'schema': 1, 'kind': 'reference_gate', 'passed': True,
            'target_figures': targets, 'data_origin': review['data_origin'],
            'evidence': [file_record(args.comparison), file_record(args.review),
                         *comp['inputs'], *comp['previews']]}
    write_new_json(args.output, gate)
    return {'gate': str(args.output.resolve()), 'passed': True,
            'scope': 'Evidence integrity and host-declared visual review, not a proof of identity'}


def verify_gate(path):
    gate = load_json(path)
    require(gate.get('kind') == 'reference_gate' and gate.get('passed') is True,
            'Reference reproduction gate has not passed')
    check_records(gate['evidence'])
    return gate


def inspect_stage(stage, data_names, figures, dpi):
    from PIL import Image
    import fitz
    stage = Path(stage).resolve(strict=True)
    require(stage.is_dir(), 'Staging path must be a directory')
    require(data_names and len(set(data_names)) == len(data_names), 'Missing/duplicate data names')
    require(figures and len(set(figures)) == len(figures), 'Missing/duplicate figure stems')
    require(dpi >= 72, 'Invalid target dpi')
    for f in figures:
        require(NAME.fullmatch(f) is not None, f'Invalid figure stem: {f}')
    for name in data_names:
        p = Path(name)
        require(p.name == name and p.suffix in DATA_EXTS and p.stem.startswith('plot_data'),
                f'Use a simple plot_data* filename in a supported data format: {name}')
    expected = {'plot.py', *data_names, *(f'{f}.{e}' for f in figures for e in ('tif', 'jpg', 'pdf'))}
    actual = {p.name for p in stage.iterdir()}
    require(actual == expected, f'Delivery mismatch. Extra={sorted(actual - expected)}; missing={sorted(expected - actual)}')
    artifacts = {}
    for name in sorted(expected):
        p = stage / name
        require(p.is_file() and not p.is_symlink() and p.stat().st_size > 0, f'Empty/non-regular file: {name}')
        artifacts[name] = sha256(p)
    # Syntax check only; NEVER import or execute an untrusted plot.py in this tool.
    compile((stage / 'plot.py').read_text(encoding='utf-8-sig'), 'plot.py', 'exec')
    for name in data_names:
        if Path(name).suffix in {'.csv', '.tsv'}:
            import csv
            with (stage / name).open(encoding='utf-8-sig', newline='') as f:
                reader = csv.reader(f, delimiter='\t' if name.endswith('.tsv') else ',')
                header = next(reader, [])
                require(header and len(header) == len(set(header)) and all(x.strip() for x in header),
                        f'Empty or duplicate column headers: {name}')
                rows = 0
                for row in reader:
                    require(len(row) == len(header), f'Irregular table row: {name}')
                    rows += 1
                require(rows > 0, f'No observations in data file: {name}')
    summaries = {}
    for stem in figures:
        sizes = []
        for suffix, fmt in [('tif', 'TIFF'), ('jpg', 'JPEG')]:
            with Image.open(stage / f'{stem}.{suffix}') as im:
                require(im.format == fmt, f'File extension/format mismatch: {stem}.{suffix}')
                require(getattr(im, 'n_frames', 1) == 1, 'Use one frame per figure')
                require(im.mode == 'RGB', f'Expected RGB raster export: {stem}.{suffix}')
                im.load()
                sizes.append(im.size)
                recorded_dpi = im.info.get('dpi', (0, 0))
                require(len(recorded_dpi) == 2 and all(abs(float(x) - dpi) <= 1 for x in recorded_dpi),
                        f'Incorrect/missing dpi: {stem}.{suffix}')
                if suffix == 'tif':
                    require(int(im.tag_v2.get(259, 1)) in (1, 5, 8, 32946, 32773),
                            'TIFF is not in an accepted lossless encoding')
        require(sizes[0] == sizes[1], f'TIF/JPG dimensions differ: {stem}')
        with fitz.open(stage / f'{stem}.pdf') as pdf:
            require(len(pdf) == 1, 'Each PDF must contain one complete figure page')
            page = pdf[0]
            expected_inches = [sizes[0][0] / dpi, sizes[0][1] / dpi]
            observed_inches = [page.rect.width / 72, page.rect.height / 72]
            require(all(abs(a - b) <= max(0.005, 2 / dpi) for a, b in zip(expected_inches, observed_inches)),
                    f'PDF/raster physical sizes differ: {stem}')
            vectors, text = len(page.get_drawings()), page.get_text().strip()
            require(vectors > 0, 'PDF has no vector paths; inspect for whole-page rasterization')
            require(bool(text) or bool(page.get_fonts()), 'PDF lacks text/font objects; inspect label rasterization')
            summaries[stem] = {'size_px': list(sizes[0]), 'dpi': dpi, 'pdf_vector_objects': vectors,
                               'pdf_text_characters': len(text), 'pdf_embedded_image_count': len(page.get_images())}
    return {'kind': 'delivery_audit', 'structural_valid': True, 'artifacts': artifacts,
            'figures': summaries, 'note': 'Semantic/data/visual validity still requires host inspection and rerun.'}


def command_publish(args):
    stage, destination = args.stage.resolve(strict=True), args.destination.expanduser().absolute()
    require(not destination.exists() and not destination.is_symlink(),
            'Destination already exists; choose a new task output directory (nothing is deleted)')
    require(stage != destination and not stage.is_relative_to(destination)
            and not destination.is_relative_to(stage), 'Stage and destination must be separate')
    target_figures = set()
    for path in args.gate:
        gate = verify_gate(path)
        target_figures.update(gate['target_figures'])
    require(set(args.figures) <= target_figures, 'At least one output figure lacks a reference gate')
    audit = inspect_stage(stage, args.data, args.figures, args.dpi)
    review = load_json(args.review)
    require(review.get('kind') == 'final_delivery_review', 'Wrong final review kind')
    require(review.get('artifacts') == audit['artifacts'], 'Final files changed after review or hashes are incomplete')
    require(review.get('actual_formats_inspected') == ['tif', 'jpg', 'pdf'], 'All three formats must be inspected')
    require(review.get('unresolved') == [], 'Unresolved final issues remain')
    check_observations(review.get('checks'), FINAL_CHECKS)
    rerun = review.get('rerun', {})
    require(rerun.get('isolated_code_and_data_only') is True and rerun.get('exit_code') == 0
            and rerun.get('outputs_match') is True, 'Clean rerun has not passed')
    require(isinstance(rerun.get('command'), str) and rerun['command'].strip(), 'Missing clean rerun command')
    # Copy to a temporary sibling, audit the copy, then rename; no clobber/deletion.
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.publish-', dir=destination.parent) as tmp:
        bundle = Path(tmp) / 'bundle'
        bundle.mkdir()
        for name in audit['artifacts']:
            shutil.copy2(stage / name, bundle / name)
        copied = inspect_stage(bundle, args.data, args.figures, args.dpi)
        require(copied['artifacts'] == audit['artifacts'], 'Copy integrity check failed')
        require(not destination.exists(), 'Destination appeared during publishing')
        # All work is in a task-specific directory; no user files are removed.
        bundle.rename(destination)
    return {'published': str(destination), 'files': sorted(audit['artifacts'])}


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    compare = sub.add_parser('compare', help='Create diagnostic previews, not a PASS decision')
    for n in ('reference', 'render', 'code'):
        compare.add_argument('--' + n, type=Path, required=True)
    compare.add_argument('--data', type=Path, nargs='+', required=True)
    compare.add_argument('--work', type=Path, required=True)
    compare.add_argument('--max-side', type=int, default=1200)
    compare.add_argument('--reference-page', type=int, default=1)
    compare.add_argument('--render-page', type=int, default=1)
    gate = sub.add_parser('gate', help='Validate host review and freeze reference evidence')
    for n in ('comparison', 'review', 'output'):
        gate.add_argument('--' + n, type=Path, required=True)
    verify = sub.add_parser('check-gate', help='Invalidate gate when any reviewed input changes')
    verify.add_argument('--gate', type=Path, required=True)
    for command in ('audit', 'publish'):
        p = sub.add_parser(command)
        p.add_argument('--stage', type=Path, required=True)
        p.add_argument('--data', nargs='+', required=True, help='Basenames only, e.g. plot_data.csv')
        p.add_argument('--figures', nargs='+', default=['figure'])
        p.add_argument('--dpi', type=int, default=600)
        if command == 'publish':
            p.add_argument('--gate', type=Path, action='append', required=True)
            p.add_argument('--review', type=Path, required=True)
            p.add_argument('--destination', type=Path, required=True)
    return parser


def main():
    args = build_parser().parse_args()
    try:
        if args.command == 'compare':
            result = command_compare(args)
        elif args.command == 'gate':
            result = command_gate(args)
        elif args.command == 'check-gate':
            gate = verify_gate(args.gate)
            result = {'passed': True, 'target_figures': gate['target_figures']}
        elif args.command == 'audit':
            result = inspect_stage(args.stage, args.data, args.figures, args.dpi)
        else:
            result = command_publish(args)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, SyntaxError, ImportError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
