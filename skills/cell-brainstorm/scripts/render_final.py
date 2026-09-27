"""Render an audited v2 record as a concise supervisor-facing research memo.

No network, LLM, scoring rewrite, or scientific inference is performed here.
Long scientific text is not truncated; the host must author concise, faithful sections.
"""
from __future__ import annotations
import hashlib
import html
import json
from typing import Any
from urllib.parse import urlsplit

NUMERALS = ('一','二','三','四','五')
LABELS = (('basis','研究依据'),('question','拟研究内容'),('plan','研究方案'),('limitations','可行性与限制'))


def plain(value: Any) -> str:
    return html.escape(str(value), quote=False).replace('\n',' ').strip()


def reference_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in ('https','http') or not parsed.netloc:
        raise ValueError('Bibliographic links must be actual HTTP(S) source URLs.')
    return value.replace('<','%3C').replace('>','%3E').replace(' ','%20')


def cautious_notes(slot: dict[str,Any], source_map: dict[str,Any]) -> list[str]:
    """Expose decision-relevant limitations, not raw scores or diagnostic logs."""
    c = slot['candidate']; e = c['enhancement']; audit = slot['enhancement_audit']
    notes: list[str] = []
    if not audit['novelty_version_current']:
        notes.append('本题修订后尚未完成文献复核，研究增量暂不能确认。')
    elif not c['novelty_queries_complete']:
        notes.append('相关研究检索尚未完成，目前不足以确认拟议研究的新增内容。')
    elif not c['critical_comparison_verified'] or not c['nearest_work']:
        notes.append('与最接近研究的差异仍需依据原文核对。')
    elif any(source_map.get(w['source_id'],{}).get('access') in ('metadata','abstract') for w in c['nearest_work']):
        notes.append('部分关键文献仅取得摘要，尚不能据此判断其全文是否完成同一检验。')
    elif slot['effective_novelty_confidence'] in ('low','unknown'):
        notes.append('现有资料仍不足以可靠判断本题与既有研究的差异。')
    resources = list(dict.fromkeys(c['resources']['missing'] + c['resources']['critical_unknowns']))
    if resources:
        notes.append('待落实条件：'+'；'.join(resources)+'。')
    elif audit['path_statuses']['P1'] != 'ready':
        unknown=[]
        for route in e['paths']['P1']['routes']:
            if route['claim_preserved']:
                unknown.extend(d['resource'] for d in route['dependencies'] if d['status']!='confirmed')
        if unknown:
            notes.append('核心研究仍以落实'+'、'.join(dict.fromkeys(unknown))+'为前提。')
        else:
            notes.append('核心研究所需条件尚未全部落实。')
    # A host may set conditional gates for issues not captured by resource arrays.
    for gate in e['scientific_gates'].values():
        if gate['status'] == 'conditional':
            notes.append(gate['reason'])
    if any(s in slot['reasons'] for s in ('Final current-literature check is missing.',)):
        notes.append('尚需补充近期文献复核。')
    if slot['status']=='conditional' and not notes:
        notes.append('现有依据或研究条件仍有待核实，暂作为备选方案。')
    return list(dict.fromkeys(notes))


def render_v2(report: dict[str,Any], sensitivity: dict[str,Any] | None=None) -> str:
    slots=report.get('slots',[])
    if len(slots)!=5:
        raise ValueError('Report requires exactly five slots.')
    if sensitivity is not None:
        raw=json.dumps(report,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
        if hashlib.sha256(raw.encode()).hexdigest()!=sensitivity.get('baseline_report_sha256'):
            raise ValueError('Sensitivity does not match the current report.')
    # Sensitivity remains in the audit; it is deliberately not a public score display.
    run=report['run']; source_map={x['id']:x for x in report['sources']}
    order: list[str]=[]
    def cites(ids: list[str]) -> str:
        nums=[]
        for sid in ids:
            if sid not in source_map:
                raise ValueError('Unknown memo citation: '+sid)
            if sid not in order:order.append(sid)
            n=order.index(sid)+1
            if n not in nums:nums.append(n)
        return ('['+','.join(str(n) for n in nums)+']') if nums else ''
    lines=[f"# {plain(report['brief']['research_content'])}选题论证",'',f"资料检索截至：{plain(run['as_of'])}。"]
    if run['mode']=='synthetic':
        lines+=['本文件为合成数据的格式与程序测试，不含真实文献或科研结论。']
    elif run['mode']!='live':
        lines+=['本文依据已有资料提出研究方案，未完成运行当日的文献复核。']
    if run['coverage_limitations']:
        lines+=['资料范围：'+'；'.join(plain(x) for x in run['coverage_limitations'])+'。']
    for i,slot in enumerate(slots):
        c=slot['candidate']
        lines+=['',f"## {NUMERALS[i]}、{plain(c['title']) if c else '暂缺'}",'']
        if not c:
            lines+=['现有资料与研究条件不足以支持另一项独立选题，暂不补列。']
            continue
        sections=c['report_sections']
        for key,label in LABELS:
            section=sections[key];body=section['text'].strip()
            if key=='limitations':
                for note in cautious_notes(slot,source_map):
                    if note.strip('。； ') not in body:
                        body+=' '+note
            lines+=[f"{label}：{plain(body)}{cites(section['source_ids'])}",'']
    if report.get('shared_risks'):
        display={s['candidate']['id']:NUMERALS[i] for i,s in enumerate(slots) if s['candidate']}
        notes=[]
        for risk in report['shared_risks']:
            names='、'.join(display[k] for k in risk['candidate_ids'])
            notes.append('第'+names+'项共同依赖尚待检验的前提“'+plain(risk['assumption_id'])+'”，需先确认该前提')
        lines+=['；'.join(notes)+'。','']
    if order:
        lines+=['## 参考文献','']
        for n,sid in enumerate(order,1):
            source=source_map[sid]
            author='，'.join(plain(a) for a in source.get('authors',[]))
            title=plain(source['title'])
            year=source.get('publication_year')
            if year is None and source.get('first_public_date'):
                year=source['first_public_date'][:4]
            venue=source.get('venue')
            entry=(author+'. ' if author else '')+title+'.'
            if venue:entry+=' '+plain(venue)+'.'
            if year:entry+=' '+str(year)+'.'
            if source.get('doi'):entry+=' DOI: '+plain(source['doi'])+'.'
            if source['source_type']=='preprint':entry+=' [预印本]'
            if source['access']=='abstract':entry+=' [仅取得摘要]'
            if source['access']=='metadata':entry+=' [仅核对元数据]'
            entry+=' <'+reference_url(source['url'])+'>'
            lines += [f'[{n}] {entry}','']
    return '\n'.join(lines).rstrip()+'\n'
