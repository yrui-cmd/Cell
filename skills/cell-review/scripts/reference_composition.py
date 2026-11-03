#!/usr/bin/env python3
"""Local identity and task-specific citation composition checks; no network."""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import unquote


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



ARTICLE_TYPES = {
    'original_research', 'research_article', 'review', 'systematic_review',
    'scoping_review', 'meta_analysis', 'methods_article', 'conference_paper',
}
EXPERIMENTAL_ARTICLE_TYPES = {
    'original_research', 'research_article', 'methods_article', 'conference_paper',
}
DESIGNS = {
    'experimental', 'observational', 'computational', 'theoretical',
    'evidence_synthesis', 'other', 'unverified',
}
MINIMUM_EXPERIMENTAL_PERCENT = 75


def has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def composition_policy_errors(policy: Any) -> list[str]:
    """Validate an explicit task policy; legacy 75% records remain readable."""
    if not isinstance(policy, dict):
        return ['reference_composition_policy must be an object.']
    if policy.get('unit') != 'unique_eligible_articles_actually_cited':
        return ['reference_composition_policy.unit is invalid.']
    mode = policy.get('mode', 'experimental75')
    if mode == 'experimental75':
        if type(policy.get('minimum_experimental_percent')) is not int or policy['minimum_experimental_percent'] != 75:
            return ['experimental75 requires minimum_experimental_percent=75.']
        if 'mode' in policy and not has_text(policy.get('basis')):
            return ['An explicit composition policy requires its task-specific basis.']
        return []
    if not isinstance(mode, str) or mode not in {'domain_specific', 'prespecified'}:
        return ['Select reference_composition_policy.mode before evidence work.']
    errors = []
    if policy.get('minimum_experimental_percent') is not None:
        errors.append('Non-experimental policies require minimum_experimental_percent=null.')
    if not has_text(policy.get('basis')):
        errors.append('The domain or prespecified inclusion basis must be recorded.')
    targets = policy.get('target_designs')
    if (not isinstance(targets, list) or not targets
            or any(not isinstance(x, str) or x not in {'experimental', 'observational', 'computational', 'theoretical', 'other'} for x in targets)
            or len(set(targets)) != len(targets)):
        errors.append('target_designs must name unique applicable original-study designs.')
    return errors


def design_classification(record: dict[str, Any]) -> tuple[str, list[str]]:
    """Check recorded design evidence; never infer experimentation from article type."""
    design = record.get('study_design')
    rid = record.get('id', '?')
    if not isinstance(design, dict):
        return 'unverified', [f'{rid}: study_design classification record required.']
    category = design.get('category')
    if not isinstance(category, str) or category not in DESIGNS:
        return 'unverified', [f'{rid}: invalid study_design.category.']
    if type(design.get('verified')) is not bool:
        return 'unverified', [f'{rid}: study_design.verified must be a boolean.']
    if design['verified'] is False:
        return 'unverified', []
    if category == 'unverified':
        return 'unverified', [f'{rid}: unverified design cannot be verified=true.']
    if not all(has_text(design.get(key)) for key in ('basis', 'locator')):
        return 'unverified', [f'{rid}: verified study_design requires actual basis and locator.']
    if category == 'experimental':
        if record.get('publication_type') not in EXPERIMENTAL_ARTICLE_TYPES:
            return 'unverified', [f'{rid}: experimental design conflicts with publication_type.']
        return 'experimental', []
    return 'non_experimental', []


def composition_summary(records: Any, policy: Any = None) -> dict[str, Any]:
    """Audit unique final eligible articles, using integer arithmetic at the boundary."""
    result: dict[str, Any] = {
        'status': 'NEEDS_REVISION', 'minimum_experimental_percent': 75,
        'unique_articles': 0, 'experimental_articles': 0,
        'required_experimental_articles': 0, 'experimental_percentage': None,
        'unverified_design_articles': 0, 'duplicate_article_groups': [],
        'identity_conflicts': [], 'errors': [], 'warnings': [],
        'scope': 'Recorded classifications and identities only; no source-content verification.',
    }
    errors = result['errors']
    # Omitted policy is compatibility for existing callers, not a new-task default.
    if policy is None:
        policy = {'minimum_experimental_percent': 75, 'unit': 'unique_eligible_articles_actually_cited'}
    errors.extend(composition_policy_errors(policy))
    if errors:
        return result
    mode = policy.get('mode', 'experimental75')
    result['policy_mode'] = mode
    result['minimum_experimental_percent'] = 75 if mode == 'experimental75' else None
    if not isinstance(records, list):
        errors.append('records must be a list of final eligible article records.')
        return result
    ids = []
    for record in records:
        if not isinstance(record, dict) or not all(
            has_text(record.get(key)) for key in ('id', 'article_id', 'identifier', 'title')
        ):
            errors.append('Every final article requires id, article_id, identifier and title.')
            continue
        ids.append(record['id'])
        publication_type = record.get('publication_type')
        if not isinstance(publication_type, str) or publication_type not in ARTICLE_TYPES:
            errors.append(f'{record["id"]}: not a qualifying scholarly article type.')
    if len(ids) != len(set(ids)):
        errors.append('Duplicate record id; article versions need distinct record ids.')
    if errors:
        return result
    total, duplicates, conflicts = count_unique(records)
    result.update(unique_articles=total, duplicate_article_groups=duplicates, identity_conflicts=conflicts)
    if conflicts:
        errors.append('Same-title records have conflicting article identifiers; verify before delivery.')
    by_id = {record['id']: record for record in records}
    grouped_ids = {rid for group in duplicates for rid in group}
    groups = duplicates + [[rid] for rid in by_id if rid not in grouped_ids]
    experimental = 0
    unknown = 0
    target_articles = 0
    targets = set(policy['target_designs']) if mode != 'experimental75' else set()
    for group in groups:
        states = set()
        for rid in group:
            state, classification_errors = design_classification(by_id[rid])
            errors.extend(classification_errors)
            states.add(state)
        if 'experimental' in states and 'non_experimental' in states:
            errors.append(f'{", ".join(group)}: conflicting design classifications for one article.')
            unknown += 1
        elif states == {'experimental'}:
            experimental += 1
        elif 'unverified' in states:
            unknown += 1
        categories = set()
        for rid in group:
            design = by_id[rid].get('study_design')
            category = design.get('category') if isinstance(design, dict) else None
            categories.add(category if isinstance(category, str) else None)
        if (len(categories) == 1 and next(iter(categories)) in targets
                and 'unverified' not in states
                and all(by_id[rid].get('publication_type') in EXPERIMENTAL_ARTICLE_TYPES for rid in group)):
            target_articles += 1
    required = (3 * total + 3) // 4 if mode == 'experimental75' else None
    result.update(
        experimental_articles=experimental, required_experimental_articles=required,
        experimental_percentage=round(100 * experimental / total, 4) if total else None,
        unverified_design_articles=unknown,
        target_design_articles=target_articles,
    )
    if unknown:
        result['warnings'].append(f'{unknown} articles have unverified/conflicting designs; retained in denominator only.')
    if not total:
        errors.append('No final eligible articles; an empty bibliography cannot pass composition checks.')
    elif mode == 'experimental75' and 4 * experimental < 3 * total:
        errors.append(
            f'Experimental articles must be at least 75%: found {experimental}/{total}; '
            f'at least {required} required. Continue relevant evidence work or report the shortfall.'
        )
    elif mode != 'experimental75' and target_articles == 0:
        errors.append('No verified original article matches the recorded target_designs; check evidence coverage.')
    if not errors:
        result['status'] = 'COMPOSITION_CHECKS_PASSED'
    return result


def audit_manifest(manifest: Any) -> dict[str, Any]:
    """For editing: deduplicate all retained articles before selecting newly added ones."""
    def invalid(message: str) -> dict[str, Any]:
        return {'status': 'NEEDS_REVISION', 'errors': [message]}

    if not isinstance(manifest, dict) or manifest.get('scope') not in ('added', 'all'):
        return invalid('scope must be added or all.')
    if 'reference_composition_policy' in manifest:
        policy_errors = composition_policy_errors(manifest['reference_composition_policy'])
        if policy_errors:
            return invalid('; '.join(policy_errors))
    records = manifest.get('records')
    if not isinstance(records, list):
        return invalid('records must be a list.')
    final = []
    for record in records:
        if not isinstance(record, dict) or type(record.get('final_cited')) is not bool:
            return invalid('Every record requires final_cited as a boolean.')
        if not record['final_cited']:
            continue
        if record.get('origin') not in ('added', 'existing'):
            return invalid('Every final record requires origin=added or existing.')
        if not all(has_text(record.get(key)) for key in ('id', 'article_id', 'identifier', 'title')):
            return invalid('Every final article requires id, article_id, identifier and title.')
        final.append(record)
    ids = [r['id'] for r in final]
    if len(ids) != len(set(ids)):
        return invalid('Duplicate record id.')
    _, duplicates, conflicts = count_unique(final)
    if conflicts:
        return invalid('Same-title records have conflicting article identifiers; verify before counting.')
    if manifest['scope'] == 'added':
        existing = {r['id'] for r in final if r['origin'] == 'existing'}
        for group in duplicates:
            if existing.intersection(group):
                existing.update(group)
        final = [r for r in final if r['id'] not in existing]
        if not final:
            return {
                'status': 'NOT_APPLICABLE', 'scope': 'added', 'unique_articles': 0,
                'experimental_articles': 0, 'experimental_percentage': None, 'errors': [],
                'note': 'No newly added articles retained; not reported as 100%.',
            }
    result = composition_summary(final, manifest.get('reference_composition_policy'))
    result['selection_scope'] = manifest['scope']
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Check the recorded task-specific citation composition policy.')
    parser.add_argument('manifest', type=Path)
    args = parser.parse_args(argv)
    try:
        result = audit_manifest(json.loads(args.manifest.read_text(encoding='utf-8-sig')))
    except (OSError, ValueError, UnicodeError) as exc:
        result = {'status': 'ERROR', 'errors': [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] in {'COMPOSITION_CHECKS_PASSED', 'NOT_APPLICABLE'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
