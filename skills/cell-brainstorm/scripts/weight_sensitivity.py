#!/usr/bin/env python3
"""Fixed one-at-a-time weight diagnostics. No network or model calls."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any
from quality_gate import ROOT, audit_candidate, build_report, load_json


def canonical_hash(data: Any) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def weight_scenarios(weights: dict[str, float], delta: float = 0.05) -> list[dict[str, Any]]:
    keys = ('N', 'V', 'F', 'T', 'E')
    if set(weights) != set(keys):
        raise ValueError('Exactly N/V/F/T/E weights are required.')
    if isinstance(delta, bool) or not isinstance(delta, (int, float)) or not math.isfinite(delta) or delta <= 0:
        raise ValueError('Delta must be finite and positive.')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 or v >= 1
           for v in weights.values()) or not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-10):
        raise ValueError('Baseline weights must be positive, finite, below one, and sum to one.')
    if any(not 0 < weights[k] - delta < weights[k] + delta < 1 for k in keys):
        raise ValueError('The configured perturbation moves a weight outside (0, 1).')
    output = [{'name': 'baseline', 'weights': copy.deepcopy(weights)}]
    for key in keys:
        for sign in (-1, 1):
            target = weights[key] + sign * delta
            multiplier = (1 - target) / (1 - weights[key])
            adjusted = {k: round(target if k == key else weights[k] * multiplier, 12) for k in keys}
            # Remove floating rounding drift while preserving the target weight.
            fix_key = next(k for k in reversed(keys) if k != key)
            adjusted[fix_key] += 1 - sum(adjusted.values())
            output.append({'name': f'{key}_{"minus" if sign < 0 else "plus"}', 'weights': adjusted})
    return output


def analyze(bundle: dict[str, Any]) -> dict[str, Any]:
    policy = load_json(ROOT / 'config/policy.json')
    baseline = build_report(bundle)
    base_ids = [s['candidate']['id'] for s in baseline['slots'] if s['candidate']]
    scenarios = []
    ranks: dict[str, list[int]] = {c['id']: [] for c in bundle['candidates']}
    for variant in weight_scenarios(policy['score_weights'], policy['weight_sensitivity_delta']):
        modified = copy.deepcopy(policy)
        modified['score_weights'] = variant['weights']
        report = build_report(bundle, _policy=modified)
        selected = [s['candidate']['id'] for s in report['slots'] if s['candidate']]
        for slot in report['slots']:
            if slot['candidate']:
                ranks[slot['candidate']['id']].append(slot['rank'])
        scenarios.append({**variant, 'selected_ids': selected, 'qualified_count': report['qualified_count'],
                          'overall_status': report['overall_status']})
    audited = {c['id']: audit_candidate(c, bundle, policy) for c in bundle['candidates']}
    rows = []
    for candidate_id in sorted(ranks):
        positions = ranks[candidate_id]
        rows.append({'candidate_id': candidate_id, 'eligibility': audited[candidate_id]['status'],
                     'baseline_rank': base_ids.index(candidate_id) + 1 if candidate_id in base_ids else None,
                     'selected_count': len(positions), 'configurations': len(scenarios),
                     'best_selected_rank': min(positions) if positions else None,
                     'worst_selected_rank': max(positions) if positions else None})
    first = base_ids[0] if base_ids else None
    return {'policy_version': policy['policy_version'], 'run_id': bundle['run']['run_id'],
            'snapshot_id': bundle['run']['snapshot_id'], 'baseline_report_sha256': canonical_hash(baseline),
            'method': 'one_at_a_time_fixed_delta_other_weights_proportionally_renormalized',
            'delta': policy['weight_sensitivity_delta'], 'baseline_ids': base_ids,
            'selection_sensitive': any(set(s['selected_ids']) != set(base_ids) for s in scenarios),
            'order_sensitive': any(s['selected_ids'] != base_ids for s in scenarios),
            'top_choice_sensitive': any((s['selected_ids'][0] if s['selected_ids'] else None) != first for s in scenarios),
            'candidates': rows, 'scenarios': scenarios,
            'limitations': [
                'This is a deterministic, finite weight-grid diagnostic, not a confidence interval or success probability.',
                'Rank ranges include selected positions only; nonselection is reported by selected_count.',
                'No second model or independent expert was used; scientific truth and rubric judgments were not validated.',
                'A stable grid result does not imply stability under all possible weights, score changes, or new evidence.'
            ]}


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
            raise ValueError('Output must not overwrite the input audit bundle.')
        result = analyze(load_json(args.input))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        if not args.quiet:
            print(json.dumps({'output': str(args.output), 'configurations': len(result['scenarios']),
                          'selection_sensitive': result['selection_sensitive']}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
