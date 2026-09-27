#!/usr/bin/env python3
"""Deterministic checks of host-supplied research audits; not a literature verifier."""
from __future__ import annotations
import argparse
import copy
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    with path.open(encoding='utf-8') as handle:
        return json.load(handle)


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timestamps must include a timezone.')
    return parsed


def validate_input(bundle: dict[str, Any]) -> None:
    version = bundle.get('schema_version')
    if version not in ('1.1', '2.0'):
        raise ValueError('Unsupported schema version.')
    schema = load_json(ROOT / ('schemas/audit-bundle-v1.1.schema.json' if version == '1.1' else 'schemas/audit-bundle.schema.json'))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(bundle), key=lambda e: str(list(e.absolute_path)))
    if errors:
        descriptions = [f"{list(e.absolute_path)}: {e.message}" for e in errors[:12]]
        raise ValueError('Schema validation failed:\n' + '\n'.join(descriptions))
    execution = bundle['execution']
    model_ids = {bundle['run']['model_id'], execution['generator_model_id'], execution['reviewer_model_id']}
    if len(model_ids) != 1:
        raise ValueError('Single-model contract violated: run/generator/reviewer IDs must match.')
    if execution['context_mode'] == 'same_context' and not execution['exposed_to_previous_scores']:
        raise ValueError('Same-context self-audit must disclose exposure to earlier scoring.')
    for key in (('sources', 'candidates', 'constraints') if version == '2.0' else ('sources', 'candidates')):
        ids = [item['id'] for item in bundle[key]]
        if len(ids) != len(set(ids)):
            raise ValueError(f'Duplicate IDs in {key}.')


def score(levels: dict[str, int], weights: dict[str, float]) -> float:
    weighted = sum(Decimal(str(weights[k])) * Decimal(levels[k]) for k in weights)
    return float(Decimal(25) * weighted)


def audit_candidate(candidate: dict[str, Any], bundle: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    c = copy.deepcopy(candidate)
    sources = {s['id']: s for s in bundle['sources']}
    rejected: list[str] = []
    conditional: list[str] = []
    levels = {key: value['level'] for key, value in c['ratings'].items()}
    confidence = c['novelty_confidence']
    as_of = date.fromisoformat(bundle['run']['as_of'])

    for check in policy['required_checks']:
        status = c['checks'][check]
        if status == 'fail':
            rejected.append('Gate failed: ' + check)
        elif status == 'unknown':
            conditional.append('Gate unresolved: ' + check)

    references: set[str] = set()
    premise_sources: set[str] = set()
    for claim in c['claims']:
        citations = claim['citations']
        if claim['kind'] in ('known', 'inference') and not citations:
            rejected.append('Known/inferred statement has no traceable premise citation.')
        for citation in citations:
            source_id = citation['source_id']
            references.add(source_id)
            source = sources.get(source_id)
            if source is None:
                rejected.append('Unknown citation ID: ' + source_id)
                continue
            if claim['kind'] in ('known', 'inference'):
                premise_sources.add(source_id)
                if source['access'] == 'metadata':
                    conditional.append('A premise only has metadata-level access: ' + source_id)
                    levels['E'] = min(levels['E'], 1)
                if source['integrity'] == 'retracted':
                    rejected.append('Retracted source used as an unqualified premise: ' + source_id)

    for work in c['nearest_work']:
        references.add(work['source_id'])
        if work['overlap'] == 'full':
            rejected.append('Substantive research question is already covered by closest work.')
        if work['overlap'] == 'unknown':
            conditional.append('Overlap with closest work is unresolved.')
    for rating in c['ratings'].values():
        references.update(rating['source_ids'])

    enhancement_audit = None
    if bundle['schema_version'] == '2.0':
        from enhanced_checks import inspect_enhancement
        enhancement_audit = inspect_enhancement(c, bundle)
        rejected.extend(enhancement_audit['rejected'])
        conditional.extend(enhancement_audit['conditional'])
        references.update(enhancement_audit['source_ids'])
        for dimension, maximum in enhancement_audit['caps'].items():
            levels[dimension] = min(levels[dimension], maximum)
        if not enhancement_audit['novelty_version_current']:
            confidence = 'unknown'

    for source_id in sorted(references):
        source = sources.get(source_id)
        if source is None:
            rejected.append('Unknown reference ID: ' + source_id)
            continue
        if not source['verified_metadata']:
            conditional.append('Source metadata not verified: ' + source_id)
        if source['integrity'] in ('unknown', 'concern'):
            conditional.append('Source integrity unresolved: ' + source_id)
        for field in ('first_public_date', 'version_date'):
            value = source[field]
            if value and date.fromisoformat(value) > as_of:
                rejected.append(f'Source {source_id} {field} is after the evidence cutoff.')
        if source['first_public_date'] is None:
            conditional.append('Source publication date is unknown: ' + source_id)
        if source['access'] != 'metadata' and source['content_sha256'] is None:
            conditional.append('Read content has no recorded hash: ' + source_id)

    if not premise_sources:
        conditional.append('No cited known/inferred foundation was supplied.')
        levels['E'] = min(levels['E'], 1)
    if not c['nearest_work']:
        conditional.append('No closest-work comparison is available.')
    if not c['novelty_queries_complete']:
        conditional.append('Candidate-specific novelty searches are incomplete.')
        levels['N'] = min(levels['N'], 1)
        confidence = 'unknown'
    if not c['critical_comparison_verified']:
        conditional.append('Critical closest-work comparison has not been verified.')
        levels['N'] = min(levels['N'], 2)
        levels['E'] = min(levels['E'], 2)
        if confidence == 'high':
            confidence = 'moderate'
    if any(sources.get(w['source_id'], {}).get('access') in ('metadata', 'abstract') for w in c['nearest_work']):
        conditional.append('A closest-work comparison has only title/abstract access.')
        levels['N'] = min(levels['N'], 2)
        levels['E'] = min(levels['E'], 2)
        if confidence == 'high':
            confidence = 'moderate'
    if c['resources']['missing'] or c['resources']['critical_unknowns']:
        conditional.append('Required resources are missing or unknown.')
        levels['F'] = min(levels['F'], 1)
    if c['ratings']['N']['level'] == 0:
        rejected.append('N0: no established novelty delta.')
    elif levels['N'] < policy['minimum_novelty_for_qualified']:
        conditional.append('Only limited or unverified novelty is established.')
    if levels['T'] == 0:
        rejected.append('No discriminating or testable proposition.')
    if levels['F'] == 0:
        rejected.append('Known feasibility failure.')
    if confidence in ('low', 'unknown'):
        conditional.append('Novelty confidence is low or unknown.')

    run = bundle['run']
    if run['mode'] == 'offline':
        conditional.append('Offline exploration does not establish current novelty.')
    if run['mode'] == 'live':
        if not run['query_log_refs']:
            conditional.append('No actual search-log references were supplied.')
        if not run['source_channels']:
            conditional.append('No source channels were recorded.')
        if not run['final_checked_at']:
            conditional.append('Final freshness check was not completed.')
        else:
            age = (parse_time(run['report_created_at']) - parse_time(run['final_checked_at'])).total_seconds() / 3600
            if age < 0:
                rejected.append('Final check timestamp is after report creation.')
            elif age > policy['live_source_read_age_hours']:
                conditional.append('Final freshness check exceeds the configured age.')
        if as_of != parse_time(run['report_created_at']).date():
            conditional.append('Live report cutoff is not its recorded report date.')

    # Resource uncertainty must not be confused with novelty uncertainty.
    evidence_uncertain = any(c['checks'][key] == 'unknown' for key in
                             ('premise_support', 'novelty_delta', 'counterevidence', 'integrity'))
    for source_id in references:
        source = sources.get(source_id)
        if source and (not source['verified_metadata'] or source['integrity'] in ('unknown', 'concern')
                       or source['first_public_date'] is None):
            evidence_uncertain = True
    freshness_uncertain = run['mode'] == 'live' and any(
        'freshness' in reason or 'search-log' in reason or 'source channels' in reason
        or 'report cutoff' in reason for reason in conditional)
    if (evidence_uncertain or freshness_uncertain) and confidence == 'high':
        confidence = 'moderate'
    independent_foundations = {sources[sid]['study_id'] for sid in premise_sources if sid in sources}
    if len(independent_foundations) < 2:
        levels['E'] = min(levels['E'], 3)
    status = 'rejected' if rejected else ('conditional' if conditional else 'qualified')
    return {'candidate': c, 'status': status, 'score': score(levels, policy['score_weights']),
            'effective_levels': levels, 'effective_novelty_confidence': confidence,
            'reasons': sorted(set(rejected + conditional)), 'referenced_source_ids': sorted(references),
            'enhancement_audit': enhancement_audit}


def build_report(bundle: dict[str, Any], *, _policy: dict[str, Any] | None = None) -> dict[str, Any]:
    validate_input(bundle)
    # Internal override is for deterministic weight-sensitivity diagnostics only.
    policy = copy.deepcopy(_policy) if _policy is not None else load_json(ROOT / 'config/policy.json')
    weights = policy['score_weights']
    if set(weights) != {'N', 'V', 'F', 'T', 'E'}:
        raise ValueError('Exactly N/V/F/T/E weights are required.')
    decimals = [Decimal(str(v)) for v in weights.values()]
    if any(not v.is_finite() or v < 0 for v in decimals) or abs(sum(decimals) - 1) > Decimal('0.000000001'):
        raise ValueError('Weights must be finite, nonnegative, and sum to one.')
    results = [audit_candidate(c, bundle, policy) for c in bundle['candidates']]
    eligible = [r for r in results if r['status'] != 'rejected']
    eligible.sort(key=lambda r: (0 if r['status'] == 'qualified' else 1, -r['score'],
                    -r['effective_levels']['E'], -r['effective_levels']['F'],
                    -r['effective_levels']['N'], r['candidate']['id']))
    slots: list[dict[str, Any]] = []
    seen_questions: set[str] = set()
    gap_counts: dict[str, int] = {}
    selection_exclusions: list[dict[str, str]] = []
    for result in eligible:
        if len(slots) == policy['final_slots']:
            break
        c = result['candidate']
        if c['question_key'] in seen_questions:
            selection_exclusions.append({'candidate_id': c['id'], 'reason': 'Duplicate normalized research question.'})
            continue
        if gap_counts.get(c['primary_gap_id'], 0) >= policy['max_candidates_per_primary_gap']:
            selection_exclusions.append({'candidate_id': c['id'], 'reason': 'Primary-gap diversity cap.'})
            continue
        slots.append({'rank': len(slots) + 1, **result})
        seen_questions.add(c['question_key'])
        gap_counts[c['primary_gap_id']] = gap_counts.get(c['primary_gap_id'], 0) + 1
    while len(slots) < policy['final_slots']:
        slots.append({'rank': len(slots) + 1, 'status': 'vacant', 'candidate': None,
                      'score': None, 'effective_levels': None, 'effective_novelty_confidence': 'unknown',
                      'reasons': ['Insufficient distinct, non-rejected candidates; no topic was fabricated.'],
                      'referenced_source_ids': []})
    qualified = sum(s['status'] == 'qualified' for s in slots)
    mode = bundle['run']['mode']
    overall = 'PASS' if qualified == policy['final_slots'] else 'PARTIAL'
    if mode == 'synthetic':
        overall = 'SYNTHETIC_DEMO'
    elif mode == 'offline':
        overall = 'EXPLORATORY'
    elif mode == 'replay' and overall == 'PASS':
        overall = 'REPLAY_PASS'
    from enhanced_checks import shared_risks
    return {'schema_version': bundle['schema_version'], 'policy_version': policy['policy_version'],
            'shared_risks': shared_risks(slots),
            'execution': copy.deepcopy(bundle['execution']), 'score_weights': copy.deepcopy(weights),
            'run': copy.deepcopy(bundle['run']), 'brief': copy.deepcopy(bundle['brief']),
            'overall_status': overall, 'qualified_count': qualified, 'slots': slots,
            'sources': copy.deepcopy(bundle['sources']),
            'rejected_candidates': [{'candidate_id': r['candidate']['id'], 'reasons': r['reasons']} for r in results if r['status'] == 'rejected'],
            'selection_exclusions': selection_exclusions,
            'limitations': ['Semantic reviews and source-reading claims are supplied by the host; this program does not independently verify them.',
                           'A deterministic rank is not a guarantee of novelty, feasibility, publication or cross-model agreement.']}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--quiet', action='store_true', help='Write results without stdout logs.')
    parser.add_argument('--verbose', dest='quiet', action='store_false', help='Print local diagnostic output.')
    parser.set_defaults(quiet=True)
    args = parser.parse_args()
    try:
        if args.input.resolve() == args.output.resolve():
            raise ValueError('Output must not overwrite the input evidence bundle.')
        report = build_report(load_json(args.input))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if not args.quiet:
            print(json.dumps({'status': report['overall_status'], 'qualified_count': report['qualified_count'],
                          'slots': len(report['slots']), 'output': str(args.output)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
