#!/usr/bin/env python3
"""Public submission timing in five symbolic regions; fully local extension.

The regional relation is a predeclared cultural tie-break, NOT extra score,
solar-time conversion, individual birth analysis, or predictive evidence.
Base almanac calculations remain in this package's oracle module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import oracle as o

ROOT = Path(__file__).resolve().parents[1]
REGION_PATH = ROOT / 'rules' / 'regions-v1.json'
APPROVAL_PATH = ROOT / '.state' / 'regions-approval.json'
REGION_ACK = '确认采用五方通用择时规则 regions-v1'
REGION_ORDER = ['east', 'south', 'west', 'north', 'center']
RELATION_LABELS = {
    'hour_generates_region': '时生方', 'same_element': '时方比和',
    'region_generates_hour': '方生时', 'region_controls_hour': '方克时',
    'hour_controls_region': '时克方'
}


def load_regions(path: Path = REGION_PATH) -> dict[str, Any]:
    r = json.loads(path.read_text(encoding='utf-8'))
    if r.get('rule_id') != 'regions-v1' or r.get('base_rule_id') != 'submission-v1':
        raise o.OracleError('未知五方规则版本，请先审核。')
    if r.get('calendar_timezone') != 'Asia/Shanghai' or r.get('local_window') != ['09:00', '21:00']:
        raise o.OracleError('五方公开版固定北京时间09:00—21:00，不做真太阳时换算。')
    if r.get('region_order') != REGION_ORDER or set(r.get('regions', {})) != set(REGION_ORDER):
        raise o.OracleError('五方不全或顺序变化，请核验规则。')
    elements = {'east':'木','south':'火','west':'金','north':'水','center':'土'}
    for key, elem in elements.items():
        if r['regions'][key].get('element') != elem:
            raise o.OracleError('五方五行对应不符，不得补猜。')
    provinces = [p for region in r['regions'].values() for p in region['provinces']]
    if len(provinces) != 34 or len(set(provinces)) != 34:
        raise o.OracleError('栏目省域对照存在重复或遗漏。')
    required_stems = dict(zip('甲乙丙丁戊己庚辛壬癸', '木木火火土土金金水水'))
    if r.get('stem_elements') != required_stems:
        raise o.OracleError('时干五行对照异常。')
    if r.get('generates') != {'木':'火','火':'土','土':'金','金':'水','水':'木'}:
        raise o.OracleError('相生循环异常。')
    if r.get('controls') != {'木':'土','土':'水','水':'火','火':'金','金':'木'}:
        raise o.OracleError('相克循环异常。')
    expected_tiers = {'hour_generates_region':2,'same_element':2,
                      'region_generates_hour':1,'region_controls_hour':1,
                      'hour_controls_region':0}
    if r.get('relation_tiers') != expected_tiers:
        raise o.OracleError('辅助顺序改变，须另立版本并重新确认。')
    if r.get('qualification') != {'event_fit':'favorable','hour_luck':'吉','eligible':True}:
        raise o.OracleError('大众优选入围条件改变，须重新审核。')
    expected_selection = {'primary':'base_window_score_desc', 'secondary':'regional_relation_tier_desc',
                          'display_order':'datetime_asc', 'retain_ties':True, 'add_points_to_base':False,
                          'national_list':'same_qualified_candidates_without_regional_tiebreak'}
    if r.get('selection') != expected_selection:
        raise o.OracleError('五方层排序约定不符，不能修改基础分或隐藏并列。')
    if r.get('hour_element_source') != 'actual_hour_ganzhi_first_stem' or r.get('default_days') != 1:
        raise o.OracleError('时干来源或默认范围变化，先审核而非静默忽略。')
    return r


def implementation_digest() -> str:
    h = hashlib.sha256()
    for p in [Path(__file__), ROOT/'scripts/oracle.py']:
        h.update(p.name.encode('utf-8'))
        h.update(p.read_bytes())
    return h.hexdigest()


def approve_regions(regions: dict[str, Any], base: dict[str, Any], ack: str,
                    path: Path = APPROVAL_PATH,
                    base_approval_path: Path = o.APPROVAL_PATH) -> dict[str, Any]:
    if ack != REGION_ACK:
        raise o.OracleError('需要用户明确确认五方v1，不把制作功能当作批准规则。')
    o.require_approval(base, base_approval_path)
    record = {'rule_id': regions['rule_id'], 'rule_digest': o.rule_digest(regions),
              'base_rule_digest': o.rule_digest(base), 'implementation_digest': implementation_digest(),
              'acknowledgement': ack, 'approved_at_utc': datetime.now(o.UTC).isoformat()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record


def require_approval(regions: dict[str, Any], base: dict[str, Any],
                     path: Path = APPROVAL_PATH,
                     base_approval_path: Path = o.APPROVAL_PATH) -> dict[str, Any]:
    o.require_approval(base, base_approval_path)
    if path == APPROVAL_PATH:
        return {'rule_id': regions['rule_id'], 'rule_digest': o.rule_digest(regions),
                'base_rule_digest': o.rule_digest(base), 'implementation_digest': implementation_digest(),
                'mode': 'built_in_default', 'confirmation_required': False}
    if not path.is_file():
        raise o.OracleError('五方规则尚未确认。先简要展示 references/regions-v1.md，确认后再算。')
    rec = json.loads(path.read_text(encoding='utf-8'))
    checks = {'rule_id': regions['rule_id'], 'rule_digest': o.rule_digest(regions),
              'base_rule_digest': o.rule_digest(base), 'implementation_digest': implementation_digest(),
              'acknowledgement': REGION_ACK}
    if any(rec.get(k) != v for k, v in checks.items()):
        raise o.OracleError('五方规则、基础规则或实现已变化，须重新确认，不沿用旧批准。')
    return rec


def resolve_region(regions: dict[str, Any], region: str = 'all',
                   province: str | None = None) -> str:
    aliases = {'东':'east','东方':'east','东部':'east', '南':'south','南方':'south','南部':'south',
               '西':'west','西方':'west','西部':'west', '北':'north','北方':'north','北部':'north',
               '中':'center','中方':'center','中央':'center','中部':'center','全部':'all','五方':'all'}
    key = aliases.get(region, region)
    if key not in REGION_ORDER + ['all']:
        raise o.OracleError('请选择东、南、西、北、中或all；不能根据姓名或籍贯推定。')
    if province is None:
        return key
    text = province.strip()
    special = {'广西壮族自治区':'广西','宁夏回族自治区':'宁夏','新疆维吾尔自治区':'新疆',
               '内蒙古自治区':'内蒙古','西藏自治区':'西藏', '香港特别行政区':'香港','澳门特别行政区':'澳门'}
    text = special.get(text, text)
    if text.endswith(('省', '市')):
        text = text[:-1]
    matches = [k for k, v in regions['regions'].items() if text in v['provinces']]
    if len(matches) != 1:
        raise o.OracleError('未识别省级地区。请提供实际提交所在地的省级地区，或直接选五方；不猜城市归属。')
    if key != 'all' and key != matches[0]:
        raise o.OracleError('指定方位与栏目省域对照冲突，请明确采用哪一种，不静默覆盖。')
    return matches[0]


def hour_element(ganzhi: str, regions: dict[str, Any]) -> str:
    if not isinstance(ganzhi, str) or len(ganzhi) != 2:
        raise o.OracleError('缺少实际时干支，不能给地区排序补默认五行。')
    if ganzhi[0] not in regions['stem_elements'] or ganzhi[1] not in '子丑寅卯辰巳午未申酉戌亥':
        raise o.OracleError('实际时干支格式异常。')
    return regions['stem_elements'][ganzhi[0]]


def relation(hour: str, region: str, rules: dict[str, Any]) -> tuple[str, int]:
    if hour not in rules['generates'] or region not in rules['generates']:
        raise o.OracleError('未知五行关系，不默认中性。')
    if hour == region:
        key = 'same_element'
    elif rules['generates'][hour] == region:
        key = 'hour_generates_region'
    elif rules['generates'][region] == hour:
        key = 'region_generates_hour'
    elif rules['controls'][region] == hour:
        key = 'region_controls_hour'
    elif rules['controls'][hour] == region:
        key = 'hour_controls_region'
    else:
        raise o.OracleError('五行关系不完整，停止。')
    return key, rules['relation_tiers'][key]


def group_ranked_dates(entries: list[dict[str, Any]], directional: bool) -> list[dict[str, Any]]:
    dates: dict[str, list[dict[str, Any]]] = {}
    for c in entries:
        dates.setdefault(c['local_date'], []).append(c)
    result = []
    for d, values in dates.items():
        key = lambda c: (c['score'], c['regional_tier'] if directional else 0)
        best = max(key(c) for c in values)
        tied = sorted([c for c in values if key(c) == best], key=lambda c:c['start'])
        result.append({'date':d, 'best_window_score':best[0],
                       'regional_tier':best[1] if directional else None,
                       'best_windows':tied, 'tie_count':len(tied)})
    result.sort(key=lambda d:(-d['best_window_score'], -(d['regional_tier'] or 0), d['date']))
    return result


def regional_rank(base_result: dict[str, Any], regions: dict[str, Any],
                  selected: str = 'all') -> dict[str, Any]:
    if base_result.get('event') not in {'submission','revision','grant'}:
        raise o.OracleError('五方通用投稿入口仅用于初投、修回和基金文书提交。其他问事用原细化入口。')
    selected = resolve_region(regions, selected)
    candidates = base_result.get('candidates', [])
    qualified = [c for c in candidates if c['eligible'] and c['event_fit'] == 'favorable'
                 and c['facts']['hour_luck'] == '吉']
    # Neutral or explicitly inauspicious hours remain in the base audit only.
    rows = []
    for key in REGION_ORDER:
        if selected != 'all' and key != selected:
            continue
        cfg = regions['regions'][key]
        items = []
        for c in qualified:
            elem = hour_element(c['facts'].get('hour_ganzhi'), regions)
            rel, tier = relation(elem, cfg['element'], regions)
            items.append({**c, 'region':key, 'region_element':cfg['element'],
                          'hour_element':elem, 'regional_relation':rel,
                          'regional_relation_label':RELATION_LABELS[rel],
                          'regional_tier':tier, 'regional_points_added':0,
                          'regional_origin':'project_defined_tiebreak_not_classical_submission_formula'})
        dates = group_ranked_dates(items, directional=True)
        best = (dates[0]['best_window_score'], dates[0]['regional_tier']) if dates else None
        rows.append({'region':key, **cfg, 'ranked_dates':dates,
                     'top_tied_dates':[d['date'] for d in dates if (d['best_window_score'],d['regional_tier']) == best],
                     'top_tied_windows':[c for d in dates if (d['best_window_score'],d['regional_tier']) == best for c in d['best_windows']],
                     'candidate_count':len(items)})
    nationwide = group_ranked_dates(qualified, directional=False)
    status = 'ranked' if qualified else ('no_feasible_window' if not candidates else 'no_explicit_public_preference')
    return {'status':status, 'event':base_result['event'], 'event_label':base_result['event_label'],
            'timezone':'Asia/Shanghai', 'selected_region':selected,
            'base_rule_id':base_result['rule_id'], 'regional_rule_id':regions['rule_id'],
            'regional_rule_digest':o.rule_digest(regions),
            'public_scope':'不结合个人生辰；通用不是适合所有个体的保证',
            'qualified_count':len(qualified), 'national_ranked_dates':nationwide,
            'regions':rows, 'base_audit':base_result,
            'ranking_note':'原百分制分数不变；同分时采用内置的方位五行辅助顺序；同分同层保留并列。'}


def times_text(windows: list[dict[str, Any]]) -> str:
    return '；'.join(o.parse_aware(c['start']).strftime('%H:%M') + '—' +
                    o.parse_aware(c['end']).strftime('%H:%M') for c in windows)


def detailed_report(result: dict[str, Any], top: int = 3) -> str:
    if not 1 <= top <= 93:
        raise o.OracleError('展示日期数须为1—93。')
    request = result.get('request', {})
    lines = [f"# Cell 科研玄学｜五方通用版·{result['event_label']}",
             f"范围：{request.get('start','已指定范围')}—{request.get('end','已指定范围')}。",
             '东、南、西、北、中统一使用北京时间（UTC+8）；每日只看09:00—21:00。',
             '不结合个人生辰，面向一般文稿提交；不表示对所有人都吉。', '']
    if result['status'] != 'ranked':
        lines += ['本范围内没有同时满足“明确日宜、时神吉、现实可用”的大众优选。',
                  '不将中性日、日忌或凶时改称吉时；如有截止，按稿件准备情况及时提交。',
                  '五方结果均无明确优选，不为补齐表格编造日期。']
    else:
        lines += ['## 通用优选（不作方位细分）',
                  '| 顺位 | 日期 | 北京时间 | 取象分 |', '|---|---|---|---:|']
        for i,d in enumerate(result['national_ranked_dates'][:top]):
            lines.append(f"| {'首选' if i == 0 else '备选'} | {d['date']} | {times_text(d['best_windows'])} | {d['best_window_score']}/100 |")
        lines += ['', '## 五方分列', '| 方位 | 顺位 | 日期 | 北京时间 | 取象分 |', '|---|---|---|---|---:|']
        for region in result['regions']:
            for i,d in enumerate(region['ranked_dates'][:top]):
                lines.append(f"| {region['label']} | {'首选' if i == 0 else '备选'} | {d['date']} | {times_text(d['best_windows'])} | {d['best_window_score']}/100 |")
        lines += ['', '五方分数沿用同一通书评分；仅在同分时作方位辅助排序。相同结果不强行改成不同。']
        for region in result['regions']:
            n = len(region['top_tied_windows'])
            if n > 1:
                lines.append(f"{region['label']}最高顺位共有{n}个并列时窗；表中按日期先后展示，未列出的同顺位时窗保留在完整结果中。")
        first = result['national_ranked_dates'][0]['best_windows'][0]
        lines += ['', '**掌历官断：** ' + o.verdict(first), '**临门一策：** ' + first['action']]
    lines += ['', '民俗取象，仅供娱乐；分数不是录用概率，稿件完备与正式截止优先。']
    return '\n'.join(lines)


def public_report(result: dict[str, Any], top: int = 3, style: str = 'brief') -> str:
    if not 1 <= top <= 93 or style not in ('brief','detailed'):
        raise o.OracleError('展示日期数须为1—93，格式须为brief或detailed。')
    if style == 'detailed' or result['status'] != 'ranked':
        return detailed_report(result, top)
    req = result.get('request', {})
    lines = ['# 投稿参考时间（通用）', f"范围：{req.get('start','已指定范围')}—{req.get('end','已指定范围')}；北京时间。", '']
    if result['selected_region'] == 'all':
        lines += o.brief_date_lines(result['national_ranked_dates'], top)
    else:
        for region in result['regions']:
            lines += [region['label'] + '投稿候选', '']
            lines += o.brief_date_lines(region['ranked_dates'], top)
    lines += ['位置采用时喜神方；出生地域的五方分组与此方位不是同一含义。',
              '不结合个人生辰，不表示对所有人都吉；民俗娱乐，实际截止优先。']
    return '\n'.join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description='五方大众投稿择时：同一北京时间，无生辰、无随机、无分钟伪精度。')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('rules', help='显示默认五方规则')
    sub.add_parser('doctor', help='检查依赖及两层默认规则状态')
    ap = sub.add_parser('approve', help='基础规则已确认后，单独记录用户对五方规则的确认')
    ap.add_argument('--ack', required=True)
    rp = sub.add_parser('public', help='默认仅比较北京时间明天09:00—21:00')
    rp.add_argument('--event', choices=['submission','revision','grant'], default='submission')
    rp.add_argument('--days', type=int, default=1)
    rp.add_argument('--start', type=date.fromisoformat)
    rp.add_argument('--end', type=date.fromisoformat)
    rp.add_argument('--region', default='all')
    rp.add_argument('--province', help='可选，实际提交所在地的省级地区；不要填出生地')
    rp.add_argument('--ready-at', type=o.parse_aware)
    rp.add_argument('--deadline', type=o.parse_aware)
    rp.add_argument('--deadline-buffer', type=int, default=30)
    rp.add_argument('--exclude-date', type=date.fromisoformat, action='append', default=[])
    rp.add_argument('--block', action='append', default=[])
    rp.add_argument('--minimum-minutes', type=int, default=20)
    rp.add_argument('--top', type=int, default=3)
    rp.add_argument('--output', type=Path)
    rp.add_argument('--audit', type=Path)
    rp.add_argument('--report-style', choices=['brief','detailed'], default='brief')
    args = p.parse_args(argv)
    try:
        base = o.load_rules()
        regions = load_regions()
        if args.command == 'rules':
            print(json.dumps(regions, ensure_ascii=False, indent=2)); return 0
        if args.command == 'doctor':
            states = {}
            for key, check in [('base_enabled', lambda:o.require_approval(base)),
                               ('regions_enabled', lambda:require_approval(regions, base))]:
                try:
                    check(); states[key] = True
                except o.OracleError:
                    states[key] = False
            print(json.dumps({'dependencies':o.dependency_status(), **states, 'confirmation_required':False,
                              'runtime_ready':all(states.values()) and all(x['ok'] for x in o.dependency_status().values()),
                              'mode':'五方是取象分组，不是五个时区；此五方入口不做个人八字或真太阳时；个人计算使用personal.py'},
                             ensure_ascii=False, indent=2)); return 0
        if args.command == 'approve':
            rec = approve_regions(regions, base, args.ack)
            print('已记录用户确认：' + rec['rule_id']); return 0
        if not 1 <= args.days <= 93 or not 1 <= args.top <= 93:
            raise o.OracleError('--days及--top须为1—93。')
        selected = resolve_region(regions, args.region, args.province)
        approval = require_approval(regions, base)
        provider = o.LiveProvider()
        now = datetime.now(o.UTC)
        start = args.start or now.astimezone(o.CST).date() + timedelta(days=1)
        end = args.end or start + timedelta(days=args.days - 1)
        lower = max(now, args.ready_at.astimezone(o.UTC)) if args.ready_at else now
        blocked = []
        for text in args.block:
            try:
                a,b = text.split('/', 1)
                blocked.append((o.parse_aware(a),o.parse_aware(b)))
            except ValueError as exc:
                raise o.OracleError('--block须为带UTC偏移的开始ISO时间/结束ISO时间。') from exc
        windows = o.enumerate_windows(start, end, 'Asia/Shanghai', lower, args.deadline,
                                      args.deadline_buffer, blocked, set(args.exclude_date), args.minimum_minutes)
        base_result = o.rank_windows(windows, provider, base, args.event)
        result = regional_rank(base_result, regions, selected)
        result.update({'generated_at_utc':now.isoformat(),'rule_policy':approval,
                       'dependencies':provider.versions,'request':{'start':str(start),'end':str(end),
                       'province':args.province, 'selected_region':selected,
                       'ready_at':args.ready_at.isoformat() if args.ready_at else None,
                       'deadline':args.deadline.isoformat() if args.deadline else None,
                       'excluded_dates':[str(d) for d in args.exclude_date],'blocked':args.block}})
        report = public_report(result, args.top, args.report_style)
        for path, content in [(args.output,report), (args.audit,json.dumps(result,ensure_ascii=False,indent=2))]:
            if path:
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(content,encoding='utf-8')
        print(report)
        return 0
    except (o.OracleError, OSError, json.JSONDecodeError) as exc:
        print('未生成推荐：' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    o.configure_cli_streams()
    raise SystemExit(main())
