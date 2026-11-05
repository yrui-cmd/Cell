"""Validate a node result and choose a declared edge; no LLM or agent launcher."""
import argparse
import json


def validate(w):
    nodes = w['nodes']
    entry, end = w['entry'], w['exit']
    if entry == end or entry not in nodes or end not in nodes:
        raise ValueError('Distinct entry and exit must exist')
    if type(w['max_steps']) is not int or w['max_steps'] < 1:
        raise ValueError('max_steps must be a positive integer')
    links = [(e['from'], e['to']) for e in w['edges']]
    links += list(w.get('error_targets', {}).items())
    if any(a not in nodes or b not in nodes for a, b in links):
        raise ValueError('Unknown edge endpoint')
    # Output may have an error fallback but no ordinary outbound edge.
    if any(e['from'] == end for e in w['edges']):
        raise ValueError('Output cannot have ordinary outbound edges')
    def reachable(start, pairs):
        seen, queue = {start}, [start]
        while queue:
            a = queue.pop()
            for src, dst in pairs:
                if src == a and dst not in seen:
                    seen.add(dst)
                    queue.append(dst)
        return seen
    if reachable(entry, links) != set(nodes):
        raise ValueError('Unreachable nodes')
    if reachable(end, [(b, a) for a, b in links]) != set(nodes):
        raise ValueError('Some nodes cannot reach output')


def matches(c, data):
    if c == {'always': True}:
        return True
    v, wanted = data[c['field']], c['value']
    op = c['op']
    if op == 'eq': return type(v) is type(wanted) and v == wanted
    if op == 'ne': return not (type(v) is type(wanted) and v == wanted)
    if op == 'gt': return v > wanted
    if op == 'ge': return v >= wanted
    if op == 'lt': return v < wanted
    if op == 'le': return v <= wanted
    raise ValueError('Unknown condition operator')


def route(w, packet, steps):
    validate(w)
    node = packet['node_id']
    if node not in w['nodes']:
        raise ValueError('Unknown current node')
    def failure(reason):
        target = w.get('error_targets', {}).get(node)
        if target is None:
            raise ValueError('No declared error edge: ' + reason)
        if steps >= w['max_steps']:
            outgoing = [e for e in w['edges'] if e['from'] == target]
            if len(outgoing) != 1 or outgoing[0]['to'] != w['exit'] or outgoing[0]['when'] != {'always': True}:
                raise ValueError('Exhaustion fallback must go directly to output')
        return {'next_node': target, 'previous_result': {
            'node_id': node, 'status': 'error',
            'result': {'error': reason, 'original_packet': packet},
            'decision_data': {}, 'evidence': []}, 'reason': reason}
    try:
        if packet['status'] not in ('ok', 'error'):
            raise ValueError('Invalid status')
        if not isinstance(packet['result'], dict) or not isinstance(packet['decision_data'], dict) or not isinstance(packet['evidence'], list):
            raise ValueError('Invalid result envelope')
        if packet['status'] == 'error':
            return failure('node_execution_error')
        types = {'bool': (bool,), 'int': (int,), 'number': (int, float), 'str': (str,)}
        for key, kind in w['nodes'][node]['decision_schema'].items():
            if type(packet['decision_data'][key]) not in types[kind]:
                raise ValueError('Invalid decision field type: ' + key)
        if node == w['exit']:
            return {'done': True, 'output': packet['result']}
        if steps >= w['max_steps']:
            # Allow the declared failure node to complete its direct output edge.
            es = [e for e in w['edges'] if e['from'] == node]
            if not (node in w.get('error_targets', {}).values() and len(es) == 1 and es[0]['to'] == w['exit'] and es[0]['when'] == {'always': True}):
                return failure('max_steps_exhausted')
        selected = [e for e in w['edges'] if e['from'] == node and matches(e['when'], packet['decision_data'])]
        if len(selected) != 1:
            return failure('no_match' if not selected else 'multiple_matches')
        return {'next_node': selected[0]['to'], 'previous_result': packet}
    except (KeyError, TypeError, ValueError) as exc:
        return failure(str(exc))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('workflow')
    p.add_argument('packet')
    p.add_argument('--steps', type=int, required=True)
    a = p.parse_args()
    with open(a.workflow, encoding='utf-8-sig') as f: w = json.load(f)
    with open(a.packet, encoding='utf-8-sig') as f: packet = json.load(f)
    print(json.dumps(route(w, packet, a.steps), ensure_ascii=False))
