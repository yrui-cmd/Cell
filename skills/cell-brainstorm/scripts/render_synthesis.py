"""Render the validated synthesis-1.1 contract without inventing candidate text."""
from __future__ import annotations

from render_final import LABELS, NUMERALS, plain, reference_url
from synthesis_gate import validate


def render_synthesis(data: dict) -> str:
    if data.get('schema_version') != 'synthesis-1.1':
        raise ValueError('Rendering requires synthesis-1.1 with sources and report_sections; migrate legacy audits first.')
    errors = validate(data)
    if errors:
        raise ValueError('\n'.join(errors))
    run = data['run']
    sources = {s['id']: s for s in data['sources']}
    order = []

    def citations(ids):
        for sid in ids:
            if sid not in order:
                order.append(sid)
        return '[' + ','.join(str(order.index(sid) + 1) for sid in dict.fromkeys(ids)) + ']' if ids else ''

    lines = [f"# {plain(data['brief']['research_content'])}选题论证", '', f"资料检索截至：{plain(run['as_of'])}。"]
    if run['mode'] == 'synthetic':
        lines += ['本文件为合成数据的程序测试，不含真实文献或科研结论。']
    elif run['mode'] != 'live':
        lines += ['本文依据已有资料提出证据综合方案，未完成运行当日的文献复核。']
    elif run.get('final_checked_at') is None:
        lines += ['尚未完成最终时效复核，不能据此确认当前研究增量。']
    else:
        from datetime import datetime
        created = datetime.fromisoformat(run['report_created_at'].replace('Z', '+00:00'))
        checked = datetime.fromisoformat(run['final_checked_at'].replace('Z', '+00:00'))
        if (created - checked).total_seconds() > 24 * 3600:
            lines += ['最终文献复核距成稿已超过24小时，近期研究状态仍需更新。']
    for i in range(5):
        candidate = data['candidates'][i] if i < len(data['candidates']) else None
        if candidate is None or candidate['status'] in {'vacant', 'fail'}:
            lines += ['', f'## {NUMERALS[i]}、暂缺', '']
            reason = candidate.get('reason') if candidate and candidate['status'] == 'vacant' else None
            lines += [plain(reason or '现有资料不足以支持另一项可靠选题，暂不补列。')]
            continue
        lines += ['', f"## {NUMERALS[i]}、{plain(candidate['title'])}", '']
        for key, label in LABELS:
            section = candidate['report_sections'][key]
            body = section['text']
            if key == 'question':
                relation = candidate['relationship_to_primary_candidate']
                if relation == 'subtopic':
                    body += ' 本题是主线中的子题。'
                elif relation == 'overlap':
                    body += ' 本题与主线实质重叠，仅作为备选角度。'
            if key == 'limitations':
                for item in candidate['open_items']:
                    body += ' ' + '；'.join(item[k] for k in ('issue', 'affects', 'allowed_now', 'fallback')) + '。'
            lines += [f'{label}：{plain(body)}{citations(section["source_ids"])}', '']
    if order:
        lines += ['', '## 参考文献', '']
        for n, sid in enumerate(order, 1):
            source = sources[sid]
            lines += [f"[{n}] {plain(source['title'])}. <{reference_url(source['url'])}>", '']
    return '\n'.join(lines).rstrip() + '\n'
