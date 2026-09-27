"""v2 deterministic consistency checks; not semantic, source or resource verification."""
from __future__ import annotations
from typing import Any


def inspect_enhancement(candidate: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    e = candidate['enhancement']
    constraints = {x['id']: x for x in bundle['constraints']}
    rejected: list[str] = []
    conditional: list[str] = []
    caps: dict[str, int] = {}
    sources: set[str] = set()
    gates = {key: value['status'] for key, value in e['scientific_gates'].items()}

    def cap(key: str, value: int) -> None:
        caps[key] = min(caps.get(key, 4), value)

    for name, gate in e['scientific_gates'].items():
        if gate['status'] == 'fail':
            rejected.append('科学门不通过：' + name + '；' + gate['reason'])
        elif gate['status'] == 'conditional':
            conditional.append('科学门条件性：' + name + '；' + gate['reason'])
    for value in e['scientific_gates'].values():
        sources.update(value['evidence_refs'])
    for constraint in bundle['constraints']:
        if constraint['status'] == 'confirmed' and not constraint['evidence_ref']:
            raise ValueError('Confirmed constraint requires an actual verification reference.')
    all_declared_sources = set(sources)
    all_declared_sources.update(w['source_id'] for w in candidate['nearest_work'])
    all_declared_sources.update(cit['source_id'] for claim in candidate['claims'] for cit in claim['citations'])
    all_declared_sources.update(sid for rating in candidate['ratings'].values() for sid in rating['source_ids'])
    all_declared_sources.update(sid for a in e['assumptions'] for sid in a['source_ids'])
    all_declared_sources.update(sid for a in e['analogies'] for sid in a['source_ids'])
    from report_style import check_sections
    check_sections(candidate['report_sections'], all_declared_sources,
                   {w['source_id'] for w in candidate['nearest_work']})
    for section in candidate['report_sections'].values():
        sources.update(section['source_ids'])
    revision = e['revision']
    if revision['last_novelty_checked_version'] > revision['version']:
        raise ValueError('Novelty check version cannot be later than the candidate version.')
    if revision['last_novelty_checked_version'] != revision['version']:
        conditional.append('当前候选版本尚未完成重新查新。')
        gates['knowledge_gain'] = 'conditional' if gates['knowledge_gain'] != 'fail' else 'fail'
        cap('N', 1)
    for assumption in e['assumptions']:
        sources.update(assumption['source_ids'])
        if assumption['status'] == 'supported' and not assumption['source_ids']:
            conditional.append('声明有支持的前提未提供来源。')
            cap('E', 1)
    for analogy in e['analogies']:
        sources.update(analogy['source_ids'])
        if not analogy['source_ids']:
            conditional.append('跨领域类比来源尚未核实。')
    seen_scenarios = [row['scenario'] for row in e['constraint_ladder']]
    if sorted(seen_scenarios) != ['current', 'relaxed', 'tightened']:
        raise ValueError('Constraint ladder requires exactly current/relaxed/tightened.')
    for row in e['constraint_ladder']:
        ref = row['constraint_ref']
        if ref is not None and ref not in constraints:
            raise ValueError('Unknown constraint reference: ' + ref)
        if row['status'] == 'applicable' and row['scenario'] == 'relaxed':
            if ref is None:
                raise ValueError('A relaxed scenario must identify its changed constraint.')
            target = constraints[ref]
            if not target['negotiable'] or target['category'] in ('safety', 'ethics', 'authorization'):
                rejected.append('约束阶梯放宽了不可协商的安全、伦理、授权或用户硬约束。')
    path_statuses: dict[str, str] = {}
    for phase in ('P0', 'P1', 'P2'):
        path = e['paths'][phase]
        if phase == 'P2' and path['status'] == 'not_assessed' and not path['routes']:
            path_statuses[phase] = 'not_assessed'
            continue
        route_states: list[str] = []
        route_ids = [r['id'] for r in path['routes']]
        if len(set(route_ids)) != len(route_ids):
            raise ValueError('Duplicate execution route IDs in ' + phase)
        for route in path['routes']:
            if not route['claim_preserved']:
                route_states.append('blocked')
                continue
            state = 'ready'
            dep_ids = [d['id'] for d in route['dependencies']]
            if len(set(dep_ids)) != len(dep_ids):
                raise ValueError('Duplicate dependency IDs within an execution route.')
            for dep in route['dependencies']:
                status = dep['status']
                ref = dep['constraint_ref']
                if ref is not None and ref not in constraints:
                    raise ValueError('Unknown dependency constraint reference: ' + ref)
                if status == 'confirmed' and (not dep['verification_ref'] or not dep['verification_ref'].strip()):
                    raise ValueError('Confirmed dependency must have a verification reference.')
                if ref is not None:
                    constraint = constraints[ref]
                    if status == 'confirmed' and constraint['status'] != 'confirmed':
                        # Do not treat a declared reference as permission to invent access.
                        raise ValueError('Dependency says confirmed but referenced constraint is not confirmed.')
                    if constraint['status'] == 'unavailable':
                        status = 'unavailable'
                if status == 'unavailable':
                    state = 'blocked'
                elif status in ('unknown', 'path_identified') and state != 'blocked':
                    state = 'conditional'
            route_states.append(state)
        derived = ('ready' if 'ready' in route_states else
                   'conditional' if 'conditional' in route_states else
                   'blocked' if route_states else 'not_assessed')
        # A conservative host assessment is retained. It cannot upgrade missing dependencies.
        declared = path['status']
        if declared == 'ready' and derived != 'ready':
            conditional.append(phase + '声明可启动，但必需依赖未满足。')
        if declared == 'conditional' and derived == 'ready':
            derived = 'conditional'
        if declared == 'blocked':
            derived = 'blocked'
        if declared == 'not_assessed' and phase != 'P2':
            derived = 'not_assessed'
        path_statuses[phase] = derived
    if path_statuses['P1'] == 'blocked':
        rejected.append('核心研究P1没有可保留主张且可执行的路径。')
        gates['feasibility'] = 'fail'
        cap('F', 0)
    elif path_statuses['P1'] != 'ready':
        conditional.append('核心研究P1的必需资源或可执行路径尚未落实。')
        gates['feasibility'] = 'conditional' if gates['feasibility'] != 'fail' else 'fail'
        cap('F', 1)
    if path_statuses['P0'] != 'ready':
        conditional.append('最小验证P0仍需解决启动条件。')
        if gates['feasibility'] != 'fail':
            gates['feasibility'] = 'conditional'
    validation = e['minimum_validation']
    if validation['execution_status'] == 'executed' and not validation['execution_evidence_refs']:
        raise ValueError('Executed validation requires actual execution evidence references.')
    # Exact duplicate strings are a cheap guard, not a semantic equivalence checker.
    for row in e['prediction_matrix']:
        if row['favored_prediction'].strip() == row['comparison_prediction'].strip():
            conditional.append('同一测试的两个比较预测文本完全相同，需要检查可回答性。')
            if gates['answerability'] != 'fail':
                gates['answerability'] = 'conditional'
            cap('T', 1)
    if candidate['ratings']['F']['level'] == 4 and validation['execution_status'] == 'planned':
        # F4 may still be supported by other genuine preliminary evidence, but it must be recorded.
        if not validation['execution_evidence_refs']:
            conditional.append('F4缺少已记录的预实验或可执行基线证据；按F3上限排序。')
            cap('F', 3)
    return {'rejected': rejected, 'conditional': conditional, 'caps': caps,
            'source_ids': sorted(sources), 'scientific_gates': gates,
            'path_statuses': path_statuses,
            'novelty_version_current': revision['last_novelty_checked_version'] == revision['version']}


def shared_risks(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mapping: dict[str, list[str]] = {}
    for slot in slots:
        candidate = slot.get('candidate')
        if not candidate or 'enhancement' not in candidate:
            continue
        for aid in set(candidate['enhancement']['essential_assumption_ids']):
            mapping.setdefault(aid, []).append(candidate['id'])
    return [{'assumption_id': key, 'candidate_ids': sorted(values)}
            for key, values in sorted(mapping.items()) if len(values) > 1]
