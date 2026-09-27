#!/usr/bin/env python3
"""Render exactly five topic slots without asking a model to add new content."""
from __future__ import annotations
import argparse
import html
import json
import hashlib
from pathlib import Path

STATUS = {'qualified':'通过本轮审查','conditional':'条件性候选','vacant':'可靠候选不足'}
CONF = {'high':'高','moderate':'中','low':'低','unknown':'未知'}

def safe(value: object) -> str:
    return html.escape(str(value)).replace('|', '\\|')

def render(report: dict, sensitivity: dict | None = None) -> str:
    if report.get('schema_version') == '2.0':
        from render_final import render_v2
        return render_v2(report, sensitivity)
    slots = report.get('slots', [])
    if len(slots) != 5:
        raise ValueError('Report must have exactly five slots.')
    if sensitivity is not None:
        raw = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        expected = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        if sensitivity.get('baseline_report_sha256') != expected:
            raise ValueError('Sensitivity results do not match this exact baseline report.')
    run = report['run']
    lines = ['# 五个科研选题及创新性', '', f"**主题：** {safe(report['brief']['research_content'])}",
             f"**截至日期：** {safe(run['as_of'])}　**模式：** {safe(run['mode'])}",
             f"**状态：** {safe(report['overall_status'])}；{report['qualified_count']}/5题通过本轮审查。",
             f"**规则版本：** {safe(report['policy_version'])}　**证据快照：** `{safe(run['snapshot_id'])}`", '',
             '**覆盖来源：** ' + ('；'.join(map(safe, run['source_channels'])) or '未记录'),
             '**覆盖限制：** ' + ('；'.join(map(safe, run['coverage_limitations'])) or '未声明；不代表穷尽全部研究'), '']
    lines += ['**执行方式：** 单个模型分阶段执行；反证审查是同模型自查，不是独立专家评审。', '']
    if report.get('execution', {}).get('context_mode') == 'same_context':
        lines += ['**上下文限制：** 自查仍在原上下文中，不能视为对前序评分的盲审。', '']
    if sensitivity is None:
        lines += ['**权重敏感性：** 本报告未附计算结果；不宣称排序稳健。', '']
    else:
        meaning = '五题入选集合随权重变化，入选结论对权重敏感。' if sensitivity['selection_sensitive'] else '在本次固定权重网格中，五题入选集合未变。'
        lines += ['**权重敏感性：** ' + meaning + ('题目顺序存在变化。' if sensitivity['order_sensitive'] else '题目顺序未变。'),
                  '以下频次仅反映基准与10个权重扰动配置，不是成功概率，也不证明科学判断正确。', '']
    if run['mode'] == 'synthetic':
        lines += ['> 本报告是纯合成测试数据，不含真实论文，不可用于科研选题。', '']
    lines += ['| 编号 | 题目 | 创新级别 | 置信度 | 状态 |', '|---|---|---|---|---|']
    for slot in slots:
        c = slot['candidate']
        level = f"N{slot['effective_levels']['N']}" if c and slot['effective_novelty_confidence'] != 'unknown' else '无法可靠判定'
        lines.append(f"| {slot['rank']} | {safe(c['title']) if c else '未形成可靠候选'} | {level} | {CONF[slot['effective_novelty_confidence']]} | {STATUS[slot['status']]} |")
    for slot in slots:
        c = slot['candidate']
        lines += ['', f"## 选题{slot['rank']}：{safe(c['title']) if c else '未形成可靠候选'}", '']
        if not c:
            lines += ['现有证据或约束不足以形成另一项可靠、独立的候选；本位未编造题目。']
            continue
        if sensitivity is not None:
            row = next(x for x in sensitivity['candidates'] if x['candidate_id'] == c['id'])
            lines += [f"**入选敏感性：** {row['selected_count']}/{row['configurations']}个配置入选；入选时排名范围{row['best_selected_rank']}–{row['worst_selected_rank']}。", '']
        lines += [f"**科学问题：** {safe(c['question'])}", '', f"**待验证假说：** {safe(c['hypothesis'])}", '', '**最接近的现有研究：**']
        for work in c['nearest_work']:
            lines += [f"{safe(work['what_done'])} [^{safe(work['source_id'])}]（定位：{safe(work['locator'])}）",
                      f"与本题的差量：{safe(work['remaining_delta'])}", '']
        if not c['nearest_work']:
            lines += ['尚未获得可核实的最近工作比较，不能确认创新程度。', '']
        lines += [f"**具体创新差量：** {safe(c['novelty_delta'])}", '',
                  f"**为什么值得研究：** {safe(c['why_it_matters'])}", '',
                  f"**创新判定：** {'N' + str(slot['effective_levels']['N']) if slot['effective_novelty_confidence'] != 'unknown' else '无法可靠判定'}，置信度{CONF[slot['effective_novelty_confidence']]}；{STATUS[slot['status']]}。", '',
                  '**前提证据与边界：**']
        for claim in c['claims']:
            refs = ' '.join(f"[^{safe(x['source_id'])}]" for x in claim['citations'])
            label = {'known':'已知陈述','inference':'推断','hypothesis':'假说'}[claim['kind']]
            lines += [f"{label}：{safe(claim['text'])} {refs}", '']
        design = c['design']
        fields = [('最小判别测试','key_test'),('主要读数/终点','main_readout'),('必要对照/基线','controls'),
                  ('最强替代解释','alternative_explanation'),('正交验证','orthogonal_test'),('证伪条件','falsifier'),
                  ('第一步','first_step'),('继续条件','continue_if'),('停止条件','stop_if')]
        for label, key in fields:
            lines += [f"**{label}：** {safe(design[key])}", '']
        resources = c['resources']
        for label, key in [('所需资源','required'),('已确认资源','confirmed'),('缺少资源','missing'),('关键未知资源','critical_unknowns')]:
            lines += [f"**{label}：** " + ('；'.join(map(safe, resources[key])) or '未列出'), '']
        lines += ['**主要风险：** ' + '；'.join(map(safe, c['risks'])), '', f"**审查结论：** {safe(c['audit_summary'])}", '']
        if slot['reasons']:
            lines += ['**程序记录的限制：** ' + '；'.join(map(safe, slot['reasons'])), '']
    lines += ['', '## 来源与使用限制', '', '以下来源和语义审查由宿主提供；本地程序未独立联网验证。', '']
    used = {ref for s in slots for ref in s['referenced_source_ids']}
    for source in report['sources']:
        if source['id'] in used:
            # Source links are emitted only from supplied audit records, not invented here.
            lines += [f"[^{safe(source['id'])}]: {safe(source['title'])}；{safe(source['url'])}；{safe(source['access'])}；来源类型{safe(source['source_type'])}。"]
    lines += ['', '创新性仅相对于实际检索和读取的资料判断，不代表绝对首创或研究必成功。']
    return '\n'.join(lines) + '\n'

def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--sensitivity',type=Path,help='Optional exact-baseline weight diagnostic JSON.')
    p.add_argument('--quiet',action='store_true')
    p.add_argument('--verbose', dest='quiet', action='store_false', help='Print local diagnostic output.')
    p.set_defaults(quiet=True)
    args=p.parse_args()
    if args.input.resolve()==args.output.resolve() or (args.sensitivity and args.sensitivity.resolve()==args.output.resolve()):
        p.error('Output cannot overwrite the input report.')
    try:
        report=json.loads(args.input.read_text(encoding='utf-8'))
        sensitivity=json.loads(args.sensitivity.read_text(encoding='utf-8')) if args.sensitivity else None
        text=render(report,sensitivity)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(text,encoding='utf-8')
    except (OSError,ValueError,KeyError) as error:
        p.exit(2,f'ERROR: {error}\n')
    if not args.quiet:print(str(args.output))
    return 0
if __name__=='__main__':raise SystemExit(main())
