#!/usr/bin/env python3
"""Read-only structural preflight for a minimal, journal-specific submission package.

Python 3.10+ standard library. No network, Word execution, XML entities or macros.
A passing check does NOT independently verify scientific claims or visual layout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any
import xml.etree.ElementTree as ET

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
MAX_XML_BYTES = 64 * 1024 * 1024
TEXT_EXTS = {'.txt', '.md', '.tex', '.bib'}
HASH = re.compile(r'^[0-9a-f]{64}$')
PLACEHOLDER = re.compile(
    r'\[\[(?:TODO|TBD|MISSING|AUTHOR_REQUIRED|VERIFY)\b[^\]\n]*\]\]'
    r'|\[(?:TODO|TBD|待补充|待填写|待确认|待核实)\]'
    r'|^\s*(?:TODO|TBD|待补充|待填写|待确认|待核实)\s*[:：.。]?\s*$',
    re.I | re.M,
)
FIELD_ERROR = re.compile(
    r'Error!\s*(?:Reference source not found|Bookmark not defined|No text of specified style in document)'
    r'|错误[!！]\s*(?:未找到引用源|未定义书签|文档中没有指定样式的文字)', re.I,
)
NUMBER = re.compile(r'(?<![\w])[-−+]?\d+(?:[.,]\d+)*(?:[eE][-+]?\d+)?%?(?![\w])')
GATES = ('journal_rules', 'science_preserved', 'materials_complete', 'visual',
         'references', 'declarations', 'anonymity')
NA_GATES = {'references', 'declarations', 'anonymity'}
REVISION_TAGS = {'ins', 'del', 'moveFrom', 'moveTo', 'moveFromRangeStart',
                 'moveToRangeStart', 'cellIns', 'cellDel', 'cellMerge',
                 'numberingChange', 'tblGridChange'}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def local_name(tag: str) -> str:
    return tag.rsplit('}', 1)[-1]


def parse_xml(raw: bytes) -> ET.Element:
    if re.search(br'<!\s*(?:DOCTYPE|ENTITY)\b', raw, re.I):
        raise ValueError('DTD/entity declarations are not supported.')
    return ET.fromstring(raw)


def _docx(path: Path) -> dict[str, Any]:
    paragraphs: list[dict[str, str]] = []
    revisions: Counter[str] = Counter()
    comments = 0
    comment_anchors = 0
    fields: list[str] = []
    metadata: dict[str, str] = {}
    hidden_runs = 0
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [i.filename for i in infos]
        if len(set(names)) != len(names):
            raise ValueError('DOCX has duplicate ZIP entries.')
        if 'word/document.xml' not in names or '[Content_Types].xml' not in names:
            raise ValueError('Not a valid DOCX package.')
        if any(i.flag_bits & 1 for i in infos):
            raise ValueError('Encrypted ZIP entries are not supported.')
        xml_infos = [i for i in infos if i.filename.endswith('.xml')]
        if sum(i.file_size for i in xml_infos) > MAX_XML_BYTES:
            raise ValueError('DOCX XML exceeds the 64 MiB scan limit; use a suitable local parser.')
        for info in xml_infos:
            name = info.filename
            if not (name.startswith('word/') or name.startswith('docProps/')):
                continue
            tree = parse_xml(archive.read(info))
            if name == 'word/document.xml' and tree.tag != '{' + W + '}document':
                raise ValueError('Unsupported Word XML namespace; use a compatible local parser.')
            if name.startswith('docProps/'):
                for node in tree.iter():
                    if local_name(node.tag) in {'creator', 'lastModifiedBy', 'title', 'subject', 'description'} and node.text:
                        metadata[f'{name}:{local_name(node.tag)}'] = node.text
                continue
            for node in tree.iter():
                if node.tag.startswith('{' + W + '}'):
                    tag = local_name(node.tag)
                    if tag in REVISION_TAGS or tag.endswith('PrChange'):
                        revisions[tag] += 1
                    if tag == 'comment':
                        comments += 1
                    if tag == 'commentRangeStart':
                        comment_anchors += 1
                    if tag in {'vanish', 'webHidden'}:
                        hidden_runs += 1
                    if tag == 'instrText' and node.text:
                        fields.append(node.text)
            is_story = bool(re.fullmatch(r'word/(?:document|header\d*|footer\d*|footnotes|endnotes)\.xml', name))
            if not is_story:
                continue
            for paragraph in tree.iter('{' + W + '}p'):
                text = ''.join(
                    n.text or '' for n in paragraph.iter()
                    if n.tag in {'{' + W + '}t', '{' + M + '}t', '{' + A + '}t'}
                )
                if text.strip():
                    paragraphs.append({'part': name, 'text': text})
    return {'paragraphs': paragraphs, 'revisions': dict(revisions), 'comments': comments,
            'comment_anchors': comment_anchors, 'field_instructions': fields,
            'metadata': metadata, 'hidden_text_markers': hidden_runs}


def scan(path: Path) -> dict[str, Any]:
    path = path.resolve(strict=True)
    if not path.is_file():
        raise ValueError('Input is not a regular file.')
    suffix = path.suffix.lower()
    if suffix == '.docx':
        detail = _docx(path)
    elif suffix in TEXT_EXTS:
        text = path.read_text(encoding='utf-8-sig')
        detail = {'paragraphs': [{'part': 'text', 'text': text}], 'revisions': {},
                  'comments': 0, 'comment_anchors': 0, 'field_instructions': [],
                  'metadata': {}, 'hidden_text_markers': 0}
    else:
        raise ValueError(f'Scan unsupported for {suffix}; use the host format-specific tool.')
    text = '\n'.join(p['text'] for p in detail['paragraphs'])
    numbers = [
        {'value': m.group(), 'context': text[max(0, m.start()-65):m.end()+65]}
        for m in NUMBER.finditer(text)
    ]
    return {'path': str(path), 'sha256': sha256(path), 'bytes': path.stat().st_size,
            'word_count_approx': len(re.findall(r"\b[\w]+(?:[-'’][\w]+)*\b", text)),
            'placeholders': [m.group() for m in PLACEHOLDER.finditer(text)],
            'field_errors': [m.group() for m in FIELD_ERROR.finditer(text)],
            'review_terms': sorted(set(re.findall(r'\b(?:TODO|TBD|TBC|XXX)\b', text))),
            'numeric_contexts': numbers, **detail,
            'scope': 'Static text/object scan only. No visual, scientific, reference, privacy or journal compliance proof.'}


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def internal_path(base: Path, value: Any) -> Path:
    if not nonempty(value):
        raise ValueError('A path must be a nonempty string.')
    path = Path(value)
    return (path if path.is_absolute() else base / path).resolve()


def file_in_root(root: Path, relative: Any) -> Path:
    if not nonempty(relative) or '\\' in relative:
        raise ValueError('Deliverable paths must be relative POSIX paths.')
    rel = PurePosixPath(relative)
    if rel.is_absolute() or '..' in rel.parts or not rel.parts or ':' in rel.parts[0]:
        raise ValueError('Unsafe deliverable path.')
    path = root.joinpath(*rel.parts)
    if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root):
        raise ValueError('Symlinked deliverables are not supported.')
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError('Deliverable escapes package root.')
    return resolved


def check(manifest_path: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve(strict=True)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    if not isinstance(manifest, dict) or manifest.get('version') != 1:
        raise ValueError('Manifest version must be 1.')
    root = internal_path(manifest_path.parent, manifest.get('root'))
    if manifest_path.is_relative_to(root):
        raise ValueError('The internal manifest must not be inside the deliverables directory.')
    errors: list[str] = []
    review: list[str] = []
    checks = manifest.get('checks', {})
    if not isinstance(checks, dict):
        raise ValueError('checks must be an object.')
    for field in ('journal', 'article_type', 'stage', 'rules_checked_at'):
        if not nonempty(manifest.get(field)):
            errors.append(f'Missing manifest field: {field}')
    for gate in GATES:
        item = checks.get(gate, {})
        if not isinstance(item, dict):
            errors.append(f'Invalid gate: {gate}')
            continue
        status = item.get('status')
        if status != 'pass' and not (gate in NA_GATES and status == 'not_applicable'):
            errors.append(f'Gate not complete: {gate}')
        if not nonempty(item.get('evidence')):
            errors.append(f'Gate evidence missing: {gate}')
    blockers = manifest.get('blockers')
    if not isinstance(blockers, list):
        errors.append('blockers must be a list.')
    else:
        errors.extend(f'Unresolved: {b}' for b in blockers)
    sources = manifest.get('sources')
    if not isinstance(sources, list) or not sources:
        errors.append('At least one immutable source file is required.')
        sources = []
    for item in sources:
        try:
            source = internal_path(manifest_path.parent, item.get('path'))
            if source.is_relative_to(root):
                errors.append(f'Source must be outside deliverables: {source.name}')
            digest = item.get('sha256', '')
            if not isinstance(digest, str) or not HASH.fullmatch(digest):
                errors.append(f'Invalid source hash: {source.name}')
            elif not source.is_file() or sha256(source) != digest:
                errors.append(f'Source is missing or changed: {source.name}')
        except (AttributeError, ValueError, OSError) as exc:
            errors.append(f'Invalid source entry: {exc}')
    files = manifest.get('files')
    if not isinstance(files, list) or not files:
        errors.append('No deliverable files listed.')
        files = []
    expected: set[str] = set()
    scanned: dict[str, Any] = {}
    for item in files:
        try:
            if not isinstance(item, dict):
                raise ValueError('file entry must be an object.')
            path = file_in_root(root, item.get('path'))
            relative = path.relative_to(root).as_posix()
            if relative in expected:
                errors.append(f'Duplicate deliverable: {relative}')
            expected.add(relative)
            if item.get('basis') not in {'journal_required', 'conditional_required', 'author_requested'}:
                errors.append(f'File has no required/requested basis: {relative}')
            if not nonempty(item.get('evidence')):
                errors.append(f'File basis evidence missing: {relative}')
            if not nonempty(item.get('role')):
                errors.append(f'File role missing: {relative}')
            clean = item.get('clean', True)
            if not isinstance(clean, bool):
                errors.append(f'clean must be boolean: {relative}')
                clean = True
            if not clean and item.get('role') != 'marked_manuscript':
                errors.append(f'Only a required marked manuscript may retain revisions: {relative}')
            if not path.is_file() or path.stat().st_size == 0:
                errors.append(f'File missing or empty: {relative}')
                continue
            digest = item.get('sha256', '')
            if not isinstance(digest, str) or not HASH.fullmatch(digest) or sha256(path) != digest:
                errors.append(f'Invalid/stale final hash: {relative}')
            if path.suffix.lower() in TEXT_EXTS | {'.docx'}:
                report = scan(path)
                scanned[relative] = {k: report[k] for k in ('sha256', 'placeholders', 'field_errors', 'revisions', 'comments', 'comment_anchors')}
                if report['placeholders']:
                    errors.append(f'Unresolved placeholder(s): {relative}')
                if report['field_errors']:
                    errors.append(f'Broken field(s): {relative}')
                if clean and report['revisions']:
                    errors.append(f'Tracked changes in clean file: {relative}')
                if clean and (report['comments'] or report['comment_anchors']):
                    errors.append(f'Comments in clean file: {relative}')
                if report['hidden_text_markers'] or report['review_terms']:
                    review.append(f'{relative}: manually inspect hidden text and review terms shown in scan.')
            else:
                review.append(f'{relative}: content requires host format-specific and visual checks.')
        except (OSError, ValueError, ET.ParseError, zipfile.BadZipFile, RuntimeError) as exc:
            errors.append(f'File scan failed: {exc}')
    if not root.is_dir():
        errors.append('Deliverables directory does not exist.')
    else:
        for path in root.rglob('*'):
            if path.is_symlink():
                errors.append(f'Symlink in deliverables: {path.relative_to(root).as_posix()}')
            elif path.is_file() and path.relative_to(root).as_posix() not in expected:
                errors.append(f'Extra file outside whitelist: {path.relative_to(root).as_posix()}')
    return {'status': 'PASS' if not errors else 'BLOCKED', 'errors': errors,
            'manual_review_notes': review, 'files_checked': scanned,
            'scope': 'Static checks plus recorded host gates only; not an independent scientific or visual review.'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    scan_parser = commands.add_parser('scan', help='Read DOCX or UTF-8 text into an internal scan JSON.')
    scan_parser.add_argument('--input', required=True, type=Path)
    scan_parser.add_argument('--out', required=True, type=Path)
    check_parser = commands.add_parser('check', help='Validate a private package manifest and its whitelist.')
    check_parser.add_argument('--manifest', required=True, type=Path)
    check_parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    try:
        input_path = args.input if args.command == 'scan' else args.manifest
        if args.out and args.out.resolve() == input_path.resolve():
            raise ValueError('Output must not overwrite the input.')
        if args.out and args.out.suffix.lower() != '.json':
            raise ValueError('Internal scan/check reports must use a .json extension.')
        result = scan(args.input) if args.command == 'scan' else check(args.manifest)
        if args.out:
            if args.command == 'check':
                m = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
                root = internal_path(args.manifest.resolve().parent, m.get('root'))
                if args.out.resolve().is_relative_to(root):
                    raise ValueError('Internal check JSON must not enter deliverables.')
                for source in m.get('sources', []):
                    if isinstance(source, dict):
                        source_path = internal_path(args.manifest.resolve().parent, source.get('path'))
                        if args.out.resolve() == source_path:
                            raise ValueError('Internal report must not overwrite a source file.')
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == 'scan':
            print('SCAN_WRITTEN')
            return 0
        if args.out:
            print(result['status'])
        return 0 if result['status'] == 'PASS' else 1
    except (OSError, ValueError, ET.ParseError, zipfile.BadZipFile, RuntimeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
