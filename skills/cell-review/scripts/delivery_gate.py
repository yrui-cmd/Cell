#!/usr/bin/env python3
"""Final editable-DOCX and user-confirmed cited article gate; Python 3.10+, no network.

Checks file structure, citation anchors, deduplication and host attestations.
It does not retrieve/verify papers, render Word, or certify scientific correctness.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote
from xml.etree import ElementTree as ET

import review_tools as rt

ARTICLE_TYPES = {
    'original_research', 'research_article', 'review', 'systematic_review',
    'scoping_review', 'meta_analysis', 'methods_article', 'conference_paper',
}
COUNTABLE_STATUSES = {'published', 'corrected', 'preprint'}
DELIVERY_CHECKS = (
    'editable_word', 'source_matches_word', 'all_pages_visually_checked',
    'layout_clean', 'citations_match', 'unique_article_identity_checked',
    'no_padding_references',
)
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
CT = '{http://schemas.openxmlformats.org/package/2006/content-types}'
DOCX_TYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'
MAX_XML_BYTES = 32 * 1024 * 1024


def obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def rows(value: Any) -> list[dict[str, Any]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def compact(value: str) -> str:
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value))


def canonical_title(value: str) -> str:
    return re.sub(r'[\W_]+', '', unicodedata.normalize('NFKC', value).casefold())


def canonical_identifier(value: str) -> str:
    text = unquote(unicodedata.normalize('NFKC', value).strip()).casefold()
    # Recognize the DOI in common textual/URL wrappers without altering its suffix.
    doi = re.search(r'10\.\d{4,9}/[^\s?#]+', text)
    if doi:
        return 'doi:' + doi.group(0).rstrip('.,;')
    pmid = re.search(r'(?:pmid\s*:?\s*|pubmed\.ncbi\.nlm\.nih\.gov/)(\d+)', text)
    if pmid:
        return 'pmid:' + pmid.group(1)
    arxiv = re.search(r'(?:arxiv\s*:?\s*|arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5})(?:v\d+)?', text)
    if arxiv:
        return 'arxiv:' + arxiv.group(1)
    return text.rstrip('/')


def read_docx(path: Path) -> tuple[str, str, int]:
    """Read real editable paragraph text in document order, including table cells."""
    if path.suffix.lower() != '.docx' or not zipfile.is_zipfile(path):
        raise ValueError('Final output must be a real DOCX package, not renamed text/PDF.')
    with zipfile.ZipFile(path) as package:
        for part in ('[Content_Types].xml', 'word/document.xml'):
            info = package.getinfo(part)
            if info.file_size > MAX_XML_BYTES:
                raise ValueError(f'DOCX XML part exceeds safety limit: {part}')
        types = ET.fromstring(package.read('[Content_Types].xml'))
        if not any(n.attrib.get('PartName') == '/word/document.xml'
                   and n.attrib.get('ContentType') == DOCX_TYPE
                   for n in types.findall(CT + 'Override')):
            raise ValueError('DOCX main content type is missing or incorrect.')
        tree = ET.fromstring(package.read('word/document.xml'))
    body_node = tree.find(W + 'body')
    if body_node is None:
        raise ValueError('DOCX has no document body.')
    if any(True for _ in body_node.iter(W + 'ins')) or any(True for _ in body_node.iter(W + 'del')):
        raise ValueError('Finalize tracked changes before validating the Word deliverable.')
    paragraphs: list[str] = []
    for paragraph in body_node.iter(W + 'p'):
        chunks = []
        for node in paragraph.iter():
            if node.tag == W + 't':
                chunks.append(node.text or '')
            elif node.tag in {W + 'tab', W + 'br', W + 'cr'}:
                chunks.append(' ')
        text = ''.join(chunks).strip()
        if text:
            paragraphs.append(text)
    if not paragraphs:
        raise ValueError('DOCX has no editable paragraph text; images alone are not a Word manuscript.')
    headings = [i for i, p in enumerate(paragraphs)
                if re.fullmatch(r'(?:\d+[.、]?\s*)?(?:参考文献|References|Bibliography)\s*[:：]?', p, re.I)]
    if len(headings) != 1:
        raise ValueError('DOCX needs one identifiable References/参考文献 heading (not duplicated in a contents list).')
    index = headings[0]
    body, bibliography = '\n'.join(paragraphs[:index]), '\n'.join(paragraphs[index + 1:])
    if not body.strip() or not bibliography.strip():
        raise ValueError('DOCX must contain both manuscript body and references.')
    return body, bibliography, len(paragraphs)


def count_unique(records: list[dict[str, Any]]) -> tuple[int, list[list[str]], list[dict[str, Any]]]:
    """Deduplicate strong identities; expose title collisions instead of hiding them."""
    parents = list(range(len(records)))
    def find(i: int) -> int:
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    keys: dict[tuple[str, str], int] = {}
    for i, record in enumerate(records):
        identities = (
            ('article_id', compact(record['article_id']).casefold()),
            ('identifier', canonical_identifier(record['identifier'])),
        )
        for kind, identity in identities:
            if not identity:
                continue
            key = kind, identity
            if key in keys:
                parents[find(i)] = find(keys[key])
            else:
                keys[key] = i
    title_groups: dict[str, list[int]] = {}
    for i, record in enumerate(records):
        title = canonical_title(record['title'])
        if title:
            title_groups.setdefault(title, []).append(i)
    conflicts: list[dict[str, Any]] = []
    for indices in title_groups.values():
        roots = {find(i) for i in indices}
        if len(roots) <= 1:
            continue
        # A title is only a candidate match. Conflicting strong identities require
        # a human decision and must never be silently collapsed by punctuation/case.
        conflicts.append({
            'records': [records[i]['id'] for i in indices],
            'title': records[indices[0]]['title'],
            'article_ids': sorted({compact(records[i]['article_id']).casefold() for i in indices}),
            'identifiers': sorted({canonical_identifier(records[i]['identifier']) for i in indices}),
        })
    groups: dict[int, list[str]] = {}
    for i, record in enumerate(records):
        groups.setdefault(find(i), []).append(record['id'])
    return len(groups), [group for group in groups.values() if len(group) > 1], conflicts


def validate_delivery(run_dir: Path) -> dict[str, Any]:
    run = run_dir.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    counts: dict[str, int | None] = {
        'minimum_articles': None, 'maximum_articles': None, 'unique_eligible_articles': 0,
    }
    duplicate_groups: list[list[str]] = []
    excluded: dict[str, str] = {}
    result: dict[str, Any] = {
        'status': 'NEEDS_REVISION', 'checked_at': rt.now_iso(), 'errors': errors,
        'warnings': warnings, 'counts': counts, 'duplicate_article_groups': duplicate_groups,
        'identity_conflicts': [],
        'not_counted': excluded, 'scientific_quality_certified': False,
        'scope': 'DOCX structure, recorded citation support, deduplication and host-attested visual/content checks only. No live reference verification, rendering or independent review.',
    }
    try:
        protocol = rt.read_json(run / '_work' / 'protocol.json')
        ledger = rt.read_json(run / '_work' / 'evidence.json')
        preflight = rt.audit_review(run)
    except (OSError, ValueError, UnicodeError, TypeError, AttributeError, KeyError) as exc:
        errors.append(f'Cannot read/audit workspace: {exc}')
        return result
    if preflight['errors']:
        errors.extend('Preflight: ' + str(e) for e in preflight['errors'])
    warnings.extend(str(w) for w in preflight['warnings'])
    if protocol.get('output_format') != 'docx':
        errors.append('protocol.output_format must be docx.')
    if protocol.get('citation_style') != 'numeric_draft':
        errors.append('Internal manuscript must retain numeric_draft for deterministic citation checks.')
    minimum, maximum, count_errors = rt.reference_count_contract(protocol)
    if count_errors:
        errors.extend('Reference-count gate: ' + message for message in count_errors)
        return result
    counts['minimum_articles'] = minimum
    counts['maximum_articles'] = maximum
    filename = protocol.get('output_file', 'review.docx')
    if (not isinstance(filename, str) or '/' in filename or '\\' in filename
            or ':' in filename or Path(filename).suffix.lower() != '.docx'):
        errors.append('output_file must be a single local .docx filename, without directory traversal.')
        return result
    path = run / filename
    if not path.is_file() or path.is_symlink():
        errors.append('Final editable Word file is missing or is a symlink.')
        return result
    try:
        body, bibliography, paragraphs = read_docx(path)
    except (OSError, ValueError, KeyError, ET.ParseError, zipfile.BadZipFile, RuntimeError) as exc:
        errors.append(f'Invalid Word file: {exc}')
        return result
    result['output_file'] = str(path)
    counts['editable_paragraphs'] = paragraphs
    if re.search(r'\{\{[^{}]+\}\}|\bTODO\b|\bTBD\b|\[待(?:补充|填写|核验)[^\]]*\]', body + bibliography):
        errors.append('Word contains unresolved template placeholders.')
    d = obj(ledger.get('delivery_review'))
    if d.get('status') != 'completed' or not rt.valid_date(d.get('checked_at')):
        errors.append('Word content and visual self-review is not completed with an actual date.')
    for key in DELIVERY_CHECKS:
        if obj(d.get('checks')).get(key) is not True:
            errors.append(f'Word self-review item incomplete: {key}')
    source = run / '_work' / 'review.md'
    if not source.is_file() or d.get('source_sha256') != rt.file_hash(source):
        errors.append('Word source hash does not match the current internal manuscript.')
    if d.get('docx_sha256') != rt.file_hash(path):
        errors.append('Word self-review hash does not match the current DOCX.')
    pages, inspected = d.get('page_count'), d.get('pages_inspected')
    if type(pages) is not int or pages < 1 or type(inspected) is not int or inspected != pages:
        errors.append('Word requires an actual positive page_count and all pages_inspected.')
    if not rt.has_text(d.get('preview_locator')):
        errors.append('Word requires an actual render/preview locator; do not claim unseen pages were checked.')

    body_compact = compact(body)
    bib_compact = compact(bibliography)
    for issue in rows(ledger.get('issues')):
        if issue.get('status') != 'open' or issue.get('impact') not in {'scope', 'core'}:
            continue
        disclosure = issue.get('manuscript_disclosure')
        if not rt.has_text(disclosure) or compact(disclosure) not in body_compact:
            errors.append(
                f'{issue.get("id", "?")}: unresolved scope/core disclosure is missing from final Word.'
            )
    records = rows(ledger.get('records'))
    cited = [r for r in records if type(r.get('citation_number')) is int and r['citation_number'] > 0]
    expected = {r['citation_number'] for r in cited}
    docx_cited_ids: set[str] = set()
    style = protocol.get('output_citation_style', 'numeric')
    if style == 'numeric':
        in_body = rt.citation_numbers(body)
        entries = {int(m.group(1)): m.group(2) for m in re.finditer(
            r'(?ms)^\s*\[(\d+)\]\s+(.+?)(?=^\s*\[\d+\]\s+|\Z)', bibliography)}
        numbers = re.findall(r'(?m)^\s*\[(\d+)\]\s+', bibliography)
        if len(numbers) != len(set(numbers)):
            errors.append('Word contains duplicate bibliography numbers.')
        if in_body != expected or set(entries) != expected:
            errors.append('Word body citations, reference entries and ledger citation sets differ.')
        for r in cited:
            n = r['citation_number']
            title = canonical_title(str(r.get('title', '')))
            if n in in_body and n in entries and title and title in canonical_title(entries[n]):
                docx_cited_ids.add(r['id'])
            else:
                errors.append(f'{r.get("id")}: Word body citation/reference title missing or mismatched.')
    elif style == 'custom':
        mapping = rows(d.get('citation_map'))
        by_id = {m.get('ref_id'): m for m in mapping if isinstance(m.get('ref_id'), str)}
        expected_ids = {r['id'] for r in cited}
        if len(mapping) != len(by_id) or set(by_id) != expected_ids:
            errors.append('Custom Word style requires one exact citation map entry for every cited record.')
        for r in cited:
            m = by_id.get(r['id'], {})
            anchor, reference, marker = (m.get(k) for k in ('body_excerpt', 'reference_excerpt', 'marker'))
            valid = all(rt.has_text(x) for x in (anchor, reference, marker))
            if valid:
                valid = (compact(anchor) in body_compact and compact(reference) in bib_compact
                         and compact(marker) in compact(anchor)
                         and canonical_title(str(r.get('title', ''))) in canonical_title(reference))
            if not valid:
                errors.append(f'{r["id"]}: custom-style Word citation anchors are missing or unmatched.')
            else:
                docx_cited_ids.add(r['id'])
    else:
        errors.append('output_citation_style must be numeric or custom with actual anchors.')
    counts['actual_docx_cited_records'] = len(docx_cited_ids)

    # Every article counted toward the floor must support/contextualize/counter an actual claim.
    supported_ids: set[str] = set()
    claims = rows(ledger.get('claims'))
    custom_map = {m.get('ref_id'): m for m in rows(d.get('citation_map')) if isinstance(m.get('ref_id'), str)}
    for claim in claims:
        text = claim.get('text')
        if claim.get('content_checked') is not True or not rt.has_text(text):
            continue
        if compact(text) not in body_compact:
            errors.append(f'{claim.get("id")}: registered claim is missing from final Word body.')
            continue
        for link in rows(claim.get('links')):
            rid = link.get('ref_id')
            if link.get('checked') is not True or not rt.has_text(link.get('locator')):
                continue
            word_excerpt = link.get('word_excerpt')
            if not rt.has_text(word_excerpt) or compact(text) not in compact(word_excerpt) or compact(word_excerpt) not in body_compact:
                errors.append(f'{claim.get("id")}/{rid}: checked link needs a final Word excerpt containing the claim and citation marker.')
                continue
            if style == 'numeric':
                record = next((item for item in cited if item.get('id') == rid), None)
                if record is None or record.get('citation_number') not in rt.citation_numbers(word_excerpt):
                    errors.append(f'{claim.get("id")}/{rid}: Word excerpt does not contain this reference marker.')
                    continue
            elif style == 'custom':
                mapping = custom_map.get(rid, {})
                marker = mapping.get('marker')
                mapped_excerpt = mapping.get('body_excerpt')
                if (not rt.has_text(marker) or compact(marker) not in compact(word_excerpt)
                        or not rt.has_text(mapped_excerpt)
                        or compact(text) not in compact(mapped_excerpt)):
                    errors.append(f'{claim.get("id")}/{rid}: Word excerpt does not contain this custom reference marker.')
                    continue
            if isinstance(rid, str):
                supported_ids.add(rid)
    eligible = []
    for r in cited:
        rid = r['id']
        reason = None
        if rid not in docx_cited_ids:
            reason = 'not actually cited with a matched reference in Word'
        elif not rt.one_of(r.get('publication_type'), ARTICLE_TYPES):
            reason = 'not a qualifying scholarly article type'
        elif not rt.one_of(r.get('publication_status'), COUNTABLE_STATUSES):
            reason = 'retracted, uncertain or other non-countable publication status'
        elif not rt.one_of(r.get('screening_status'), {'included', 'context_only'}):
            reason = 'not included or relevant contextual evidence'
        elif obj(r.get('metadata_check')).get('status') != 'verified':
            reason = 'metadata identity not verified'
        elif not rt.has_text(r.get('article_id')):
            reason = 'article_id missing; version deduplication not recorded'
        elif not (obj(r.get('reading')).get('abstract_read') is True or obj(r.get('reading')).get('full_text_read') is True):
            reason = 'article reading not recorded'
        elif not rt.has_text(obj(r.get('extraction')).get('role_in_review')):
            reason = 'relevance to review not recorded'
        elif rid not in supported_ids:
            reason = 'no checked source-to-claim mapping in final Word'
        if reason:
            excluded[rid] = reason
        else:
            eligible.append(r)
    # Identity fields already checked by the preflight; omit malformed fields rather than crash.
    eligible = [r for r in eligible if all(rt.has_text(r.get(k)) for k in ('id', 'article_id', 'identifier', 'title'))]
    count, groups, identity_conflicts = count_unique(eligible)
    counts['eligible_article_records'] = len(eligible)
    counts['unique_eligible_articles'] = count
    counts['related_study_families'] = len({r.get('study_id') for r in eligible if isinstance(r.get('study_id'), str)})
    duplicate_groups.extend(groups)
    result['identity_conflicts'].extend(identity_conflicts)
    if groups:
        warnings.append('Duplicate article/version groups were counted once; study families are not independent replications.')
    if identity_conflicts:
        errors.append('Same-title records have conflicting article identifiers; verify the records or versions before delivery.')
    if count < minimum:
        errors.append(f'At least {minimum} unique verified relevant articles actually cited in Word are required; found {count}. Continue evidence work or label as incomplete; never pad or fabricate.')
    if maximum is not None and count > maximum:
        errors.append(f'At most {maximum} unique verified relevant articles actually cited in Word are permitted by the user-confirmed requirement; found {count}. Revise the selection or obtain a revised user requirement.')
    if not errors:
        result['status'] = 'DELIVERY_CHECKS_PASSED'
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir', type=Path)
    args = parser.parse_args(argv)
    try:
        result = validate_delivery(args.run_dir)
        work = args.run_dir.expanduser().resolve() / '_work'
        if work.is_dir():
            rt.write_json(work / 'delivery-audit.json', result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['status'] == 'DELIVERY_CHECKS_PASSED' else 1
    except (OSError, ValueError, UnicodeError, TypeError, KeyError) as exc:
        print(json.dumps({'status': 'ERROR', 'message': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
