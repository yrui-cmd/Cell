#!/usr/bin/env python3
"""Deterministic almanac-based event timing; not Qimen or predictive science.

Dates/pillars come from pinned libraries. Numbers come only from the approved
project rubric. The SHA-256 digest protects the rule version; it never sets a
score. No network access, credentials, telemetry or external writes occur here.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import sys
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parents[1]
RULE_PATH = ROOT / 'rules' / 'submission-v1.json'
APPROVAL_PATH = ROOT / '.state' / 'approval.json'
UTC = timezone.utc
CST = timezone(timedelta(hours=8), name='UTC+08:00')
PINNED = {'cnlunar': '0.2.5', 'lunar_python': '1.4.8', 'tzdata': '2026.5'}
RULE_ACK = '确认采用投稿择日规则 submission-v1'


class OracleError(ValueError):
    """Actionable error: never turn missing facts into invented scores."""


def load_rules(path: Path = RULE_PATH) -> dict[str, Any]:
    r = json.loads(path.read_text(encoding='utf-8'))
    if r.get('rule_id') != 'submission-v1' or r.get('engine') != 'almanac-not-qimen':
        raise OracleError('未知规则版本，先审核规则，不得静默换算法。')
    if r.get('dependencies') != PINNED:
        raise OracleError('依赖版本变化，须与规则一并审核。')
    conventions = {'calendar_timezone': 'Asia/Shanghai', 'day_boundary': '23:00',
                   'god_type': 'cnlunar', 'year_boundary': 'lunar_new_year',
                   'hour_source': 'lunar-python:getTimeTianShenLuck'}
    if any(r.get(k) != value for k, value in conventions.items()):
        raise OracleError('历法口径与当前实现不一致，请建立新版本并重新核验。')
    w = r['weights']
    if w['event'] != {'favorable': 60, 'neutral': 30, 'unfavorable': 0}:
        raise OracleError('事件权重与v1实现不一致，请建立新版本并重新确认。')
    if w['day'] != {'黄道日': 15, '黑道日': 0} or w['hour'] != {'吉': 25, '凶': 0}:
        raise OracleError('日时权重与v1实现不一致，请重新审核。')
    if r['local_window'] != ['09:00', '21:00']:
        raise OracleError('本Skill固定09:00—21:00，不接受静默扩大时段。')
    return r


def rule_digest(rules: dict[str, Any]) -> str:
    raw = json.dumps(rules, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def approve_rules(rules: dict[str, Any], acknowledgement: str,
                  path: Path = APPROVAL_PATH) -> dict[str, Any]:
    if acknowledgement != RULE_ACK:
        raise OracleError('需要用户对当前v1规则的明确确认，不能替用户批准。')
    record = {'rule_id': rules['rule_id'], 'rule_digest': rule_digest(rules),
              'engine_digest': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'acknowledgement': acknowledgement,
              'approved_at_utc': datetime.now(UTC).isoformat()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record


def require_approval(rules: dict[str, Any], path: Path = APPROVAL_PATH) -> dict[str, Any]:
    if path == APPROVAL_PATH:
        return {'rule_id': rules['rule_id'], 'rule_digest': rule_digest(rules),
                'mode': 'built_in_default', 'confirmation_required': False,
                'engine_digest': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if not path.is_file():
        raise OracleError('规则尚未确认。先展示 references/scoring-v1.md 的简要方案，待用户确认再计算。')
    record = json.loads(path.read_text(encoding='utf-8'))
    if (record.get('rule_digest') != rule_digest(rules)
            or record.get('engine_digest') != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            or record.get('acknowledgement') != RULE_ACK):
        raise OracleError('规则已变化或确认记录无效，必须重新确认；不沿用旧批准。')
    return record


def dependency_status() -> dict[str, Any]:
    rows = {}
    for name, expected in PINNED.items():
        try:
            installed = metadata.version(name)
        except metadata.PackageNotFoundError:
            installed = None
        rows[name] = {'required': expected, 'installed': installed,
                      'ok': installed == expected}
    return rows


class Provider(Protocol):
    def facts(self, instant: datetime) -> dict[str, Any]: ...


class LiveProvider:
    """CNLunar day almanac + lunar-python hour deity; fixed, declared method.

    Daily almanac uses lunar-month godType='cnlunar', not exact solar-term
    astrology. Hour deity uses the effective day branch, with day turnover at
    23:00 CST. Never substitute a library's differently-scoped Yi/Ji dataset.
    """
    def __init__(self) -> None:
        state = dependency_status()
        bad = {k: v for k, v in state.items() if not v['ok']}
        if bad:
            raise OracleError('历法依赖缺失或版本不符。先运行 python -m pip install -r requirements.txt；'
                              '不可用演示数据代替。详情：' + json.dumps(bad, ensure_ascii=False))
        import cnlunar
        from lunar_python import Solar
        # Force the pinned timezone database instead of silently using OS data.
        import zoneinfo
        zoneinfo.reset_tzpath([])
        ZoneInfo.clear_cache()
        self.CNLunar = cnlunar.Lunar
        self.Solar = Solar
        self.versions = state

    @lru_cache(maxsize=512)
    def _day(self, effective_date: date) -> dict[str, Any]:
        if not 1902 <= effective_date.year <= 2099:
            raise OracleError('当前适配器仅支持1902—2099年，禁止越界外推。')
        noon = datetime.combine(effective_date, time(12))
        c = self.CNLunar(noon, godType='cnlunar', year8Char='year', yeargod='duty')
        l = self.Solar.fromYmdHms(noon.year, noon.month, noon.day, 12, 0, 0).getLunar()
        cn_month = -c.lunarMonth if c.isLunarLeapMonth else c.lunarMonth
        left = (c.lunarYear, cn_month, c.lunarDay, c.day8Char)
        right = (l.getYear(), l.getMonth(), l.getDay(), l.getDayInGanZhi())
        if left != right:
            raise OracleError(f'{effective_date} 的农历/日干支交叉核验不一致：{left} != {right}。停止排序。')
        officer, deity, day_type = c.get_today12DayOfficer()
        if day_type not in ('黄道日', '黑道日'):
            raise OracleError('未知日值神类型，不能按中性值补分。')
        return {
            'effective_date_cst': effective_date.isoformat(),
            'lunar_date': {'year': c.lunarYear, 'month': cn_month, 'day': c.lunarDay},
            'lunar_text': f'{c.lunarYearCn}年{c.lunarMonthCn}{c.lunarDayCn}',
            'day_ganzhi': c.day8Char,
            'day_officer': officer, 'day_deity': deity, 'day_type': day_type,
            'good_activities': sorted(set(c.goodThing)),
            'bad_activities': sorted(set(c.badThing)),
            'good_deities': sorted(set(c.goodGodName)),
            'bad_deities': sorted(set(c.badGodName)),
            'almanac_level': c.todayLevelName,
            'solar_term_on_effective_date': c.todaySolarTerms,
            'calendar_crosscheck': 'cnlunar+lunar_python_passed',
            'sources': ['S1', 'S2', 'S3']
        }

    def facts(self, instant: datetime) -> dict[str, Any]:
        require_aware(instant)
        b = instant.astimezone(CST)
        effective = b.date() + timedelta(days=int(b.hour >= 23))
        result = dict(self._day(effective))
        lunar = self.Solar.fromYmdHms(b.year, b.month, b.day, b.hour, b.minute, b.second).getLunar()
        if result['day_ganzhi'] != lunar.getDayInGanZhiExact():
            raise OracleError('子初换日口径不一致，停止推荐而不是补写干支。')
        luck = lunar.getTimeTianShenLuck()
        if luck not in ('吉', '凶'):
            raise OracleError('未知时神吉凶，不能猜分。')
        result.update({'evaluated_at_cst': b.isoformat(),
                       'hour_ganzhi': lunar.getTimeInGanZhi(),
                       'hour_branch': lunar.getTimeZhi(),
                       'direction': {'kind': 'hour_xishen', 'label': '时喜神方',
                                     'palace': lunar.getTimePositionXi(),
                                     'description': lunar.getTimePositionXiDesc(),
                                     'source': 'lunar_python==1.4.8:Lunar.getTimePositionXiDesc',
                                     'calendar_timezone': 'Asia/Shanghai'},
                       'hour_deity': lunar.getTimeTianShen(), 'hour_luck': luck})
        return result


def require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise OracleError('时间必须带时区或UTC偏移，不能默认为UTC。')


def parse_aware(text: str) -> datetime:
    try:
        value = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError as exc:
        raise OracleError('时间格式应为2026-11-01T18:00:00+08:00。') from exc
    require_aware(value)
    return value


def ensure_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise OracleError('未知IANA时区；请给出如Asia/Shanghai或Europe/Berlin，并安装tzdata。') from exc


def local_boundary(day: date, hour: int, zone: ZoneInfo) -> datetime:
    naive = datetime.combine(day, time(hour))
    aware = naive.replace(tzinfo=zone)
    if aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != naive:
        raise OracleError('该地此日的工作时段边界不存在，请核对夏令时。')
    # Ambiguous wall-clock boundaries cannot be selected without a fold choice.
    if aware.utcoffset() != naive.replace(tzinfo=zone, fold=1).utcoffset():
        raise OracleError('该地此日工作边界有夏令时歧义，请明确UTC偏移。')
    return aware.astimezone(UTC)


def subtract_blocked(start: datetime, end: datetime,
                     blocked: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    pieces = [(start, end)]
    for lo, hi in blocked:
        require_aware(lo); require_aware(hi)
        lo, hi = lo.astimezone(UTC), hi.astimezone(UTC)
        if hi <= lo:
            raise OracleError('排除时段的结束必须晚于开始。')
        new = []
        for a, b in pieces:
            if hi <= a or lo >= b:
                new.append((a, b)); continue
            if a < lo: new.append((a, min(b, lo)))
            if hi < b: new.append((max(a, hi), b))
        pieces = new
    return pieces


def enumerate_windows(start_day: date, end_day: date, timezone_name: str,
                      not_before: datetime | None = None,
                      deadline: datetime | None = None,
                      deadline_buffer_minutes: int = 30,
                      blocked: list[tuple[datetime, datetime]] | None = None,
                      excluded_dates: set[date] | None = None,
                      minimum_minutes: int = 20) -> list[dict[str, Any]]:
    if not 0 <= (end_day - start_day).days <= 92:
        raise OracleError('日期范围须为1—93天，不能反向或无限搜索。')
    if minimum_minutes <= 0 or deadline_buffer_minutes < 0:
        raise OracleError('最短窗口须大于0；截止缓冲不能为负。')
    zone = ensure_zone(timezone_name)
    excluded_dates = excluded_dates or set()
    blocked = blocked or []
    if not_before is not None:
        require_aware(not_before); not_before = not_before.astimezone(UTC)
    if deadline is not None:
        require_aware(deadline)
        deadline = deadline.astimezone(UTC) - timedelta(minutes=deadline_buffer_minutes)
    output = []
    for n in range((end_day - start_day).days + 1):
        d = start_day + timedelta(days=n)
        if d in excluded_dates: continue
        lo, hi = local_boundary(d, 9, zone), local_boundary(d, 21, zone)
        if not_before is not None: lo = max(lo, not_before)
        if deadline is not None: hi = min(hi, deadline)
        if hi <= lo: continue
        for a, b in subtract_blocked(lo, hi, blocked):
            # Split at every CST hour-branch boundary and calendar midnight.
            # Thus international local slots may end at :30 or :45; that is a
            # timezone/availability boundary, never invented minute divination.
            cuts = {a, b}
            cdate = a.astimezone(CST).date() - timedelta(days=1)
            last = b.astimezone(CST).date() + timedelta(days=1)
            while cdate <= last:
                for hour in [0] + list(range(1, 24, 2)):
                    cut = datetime.combine(cdate, time(hour), CST).astimezone(UTC)
                    if a < cut < b: cuts.add(cut)
                cdate += timedelta(days=1)
            cuts = sorted(cuts)
            for x, y in zip(cuts, cuts[1:]):
                if (y-x).total_seconds() < minimum_minutes * 60: continue
                output.append({'local_date': d.isoformat(),
                               'start': x.astimezone(zone).isoformat(),
                               'end': y.astimezone(zone).isoformat(),
                               'start_cst': x.astimezone(CST).isoformat(),
                               'end_cst': y.astimezone(CST).isoformat(),
                               'duration_minutes': (y-x).total_seconds()/60,
                               'granularity': 'traditional_hour_clipped_by_real_constraints'})
    return output


def score_facts(facts: dict[str, Any], event: dict[str, Any],
                rules: dict[str, Any]) -> dict[str, Any]:
    good, bad = set(facts['good_activities']), set(facts['bad_activities'])
    proxy = event['proxy']
    all_bad = bool({'诸事不宜', '诸事不利', '诸事皆忌', '诸事不吉', '诸事不宜。'} & (bad | good))
    if all_bad or (proxy is not None and proxy in bad):
        fit = 'unfavorable'
    elif proxy is not None and proxy in good:
        fit = 'favorable'
    else:
        fit = 'neutral'
    try:
        event_points = rules['weights']['event'][fit]
        day_points = rules['weights']['day'][facts['day_type']]
        hour_points = rules['weights']['hour'][facts['hour_luck']]
    except KeyError as exc:
        raise OracleError('历书字段或评分条件缺失，拒绝补默认分。') from exc
    return {'event_fit': fit, 'eligible': fit != 'unfavorable',
            'score': event_points + day_points + hour_points,
            'score_kind': 'cultural_ranking_not_acceptance_probability',
            'breakdown': [
                {'id': 'event', 'points': event_points, 'max': 60,
                 'basis': {'proxy': proxy, 'mapping': event['mapping'], 'status': fit,
                           'explicit_favorable': proxy in good if proxy else False,
                           'explicit_unfavorable': proxy in bad if proxy else False,
                           'global_unfavorable': all_bad},
                 'weight_origin': 'project_rubric_v1'},
                {'id': 'day', 'points': day_points, 'max': 15,
                 'basis': facts['day_type'], 'weight_origin': 'project_rubric_v1'},
                {'id': 'hour', 'points': hour_points, 'max': 25,
                 'basis': facts['hour_luck'], 'weight_origin': 'project_rubric_v1'}]}


def rank_windows(windows: list[dict[str, Any]], provider: Provider,
                 rules: dict[str, Any], event_key: str) -> dict[str, Any]:
    if event_key not in rules['events']:
        raise OracleError('未定义事件映射；不能私自把任何问事当成投稿。')
    event = rules['events'][event_key]
    candidates = []
    for w in windows:
        a, b = parse_aware(w['start']), parse_aware(w['end'])
        probe = a.astimezone(UTC) + (b.astimezone(UTC)-a.astimezone(UTC))/2
        facts = provider.facts(probe)
        scoring = score_facts(facts, event, rules)
        candidates.append({**w, **scoring, 'facts': facts, 'action': event['action'], 'event': event_key})
    candidates.sort(key=lambda c: (-c['score'], parse_aware(c['start']).astimezone(UTC)))
    eligible = [c for c in candidates if c['eligible']]
    dates: dict[str, list] = {}
    for c in eligible: dates.setdefault(c['local_date'], []).append(c)
    ranked_dates = []
    for d, entries in dates.items():
        maximum = max(c['score'] for c in entries)
        tied = [c for c in entries if c['score'] == maximum]
        ranked_dates.append({'date': d, 'best_window_score': maximum,
                             'definition': '当日最高可用时窗分，不是另算的全天运势分',
                             'best_windows': tied})
    ranked_dates.sort(key=lambda c: (-c['best_window_score'], c['date']))
    if not candidates:
        status = 'no_feasible_window'
    elif not eligible:
        status = 'no_almanac_preferred_window_keep_real_deadline'
    else:
        status = 'ranked'
    best_score = eligible[0]['score'] if eligible else None
    return {'status': status, 'event': event_key, 'event_label': event['label'],
            'proxy': event['proxy'], 'mapping': event['mapping'],
            'rule_id': rules['rule_id'], 'rule_digest': rule_digest(rules),
            'candidate_count': len(candidates), 'eligible_count': len(eligible),
            'best_score': best_score,
            'top_tied_windows': [c for c in eligible if c['score'] == best_score],
            'ranked_dates': ranked_dates, 'candidates': candidates}


def chinese_number(n: int) -> str:
    if not 0 <= n <= 100: raise OracleError('分数越界。')
    a = '零一二三四五六七八九'
    if n == 100: return '一百'
    if n < 10: return a[n]
    q, r = divmod(n, 10)
    return (a[q] if q > 1 else '') + '十' + (a[r] if r else '')


def verdict(c: dict[str, Any]) -> str:
    f = c['facts']
    # Interpret only calculated fields. No independent scoring occurs here.
    writing = c.get('event', 'submission') in {'submission', 'revision', 'grant'}
    noun = '文卷' if writing else '此事'
    if c['event_fit'] == 'unfavorable':
        return '此窗不列通书优选；期限在前，务以如期完备为重。'
    prefix = f"{f['day_officer']}日当值，{f['hour_deity']}临时；"
    if c['event_fit'] == 'neutral':
        return prefix + '未列明确宜忌，取象平允，现实准备为先。'
    if f.get('hour_luck') == '凶':
        return prefix + '日事得宜，时象未全；不称大吉，期限与准备为先。'
    return prefix + f'{noun}得宜，先备而后行。'


def detailed_report(result: dict[str, Any], top: int = 3) -> str:
    if result['status'] == 'no_feasible_window':
        return '给定日期、09:00—21:00和截止约束内，没有足够长的可用时段。请调整现实可用范围。'
    if result['status'] != 'ranked':
        return ('给定范围内没有通书取象优选时段。不要为择日错过正式截止；按准备完成情况尽早提交。'
                '\n民俗取象，仅供娱乐；不代表录用概率。')
    lines = [f"# Cell 科研玄学｜通用{result['event_label']}（不含个人八字）",
             f"显示时区：{result['timezone']}；排历口径：北京时间通书、子初换日。",
             '只选当地09:00—21:00。分数为取象排序分。', '',
             '| 顺位 | 日期 | 首选时窗 | 取象分 |', '|---|---|---|---:|']
    for i, d in enumerate(result['ranked_dates'][:top], 1):
        times = '；'.join(parse_aware(c['start']).strftime('%H:%M') + '—' +
                          parse_aware(c['end']).strftime('%H:%M') for c in d['best_windows'])
        lines.append(f"| {'首选' if i == 1 else '备选'} | {d['date']} | {times} | {d['best_window_score']}/100 |")
    if len(result['top_tied_windows']) > 1:
        lines += ['', f"最高分共有{len(result['top_tied_windows'])}个并列时窗；表内按日期先后展示，并非有隐藏高低。"]
    best = result['ranked_dates'][0]['best_windows'][0]
    lines += ['', '**判词：** ' + verdict(best), '**临门一策：** ' + best['action'], '',
              '实际截止和稿件完备优先。民俗取象，仅供娱乐；分数不代表录用概率。']
    return '\n'.join(lines)


def brief_date_lines(dates: list[dict[str, Any]], top: int = 3) -> list[str]:
    lines = []
    for row in sorted(dates[:top], key=lambda d: d['date']):
        day = date.fromisoformat(row['date'])
        lines += [f"公历{day.year}年{day.month}月{day.day}日（周{'一二三四五六日'[day.weekday()]}）"]
        for c in row['best_windows']:
            facts = c['facts']
            branch = facts.get('hour_branch')
            name = branch + '时' if branch and branch in '子丑寅卯辰巳午未申酉戌亥' else '时辰待核验'
            start, end = parse_aware(c['start']), parse_aware(c['end'])
            lines.append(f"{name}（{start:%H:%M}—{end:%H:%M}）")
            direction = facts.get('direction', {})
            desc = direction.get('description')
            if direction.get('kind') == 'hour_xishen' and desc in ['正东','正南','正西','正北','东南','东北','西南','西北']:
                lines.append('位置：' + desc + '方')
            else:
                lines.append('位置：未提供可核验的方位依据')
        lines.append('')
    return lines


def public_report(result: dict[str, Any], top: int = 3, style: str = 'brief') -> str:
    if style == 'detailed':
        return detailed_report(result, top)
    if style != 'brief' or not 1 <= top <= 93:
        raise OracleError('通用输出格式须为brief或detailed，日期数量须为1—93。')
    if result['status'] != 'ranked':
        return detailed_report(result, top)
    request = result.get('request', {})
    lines = ['# 投稿参考时间（通用，不含个人八字）',
             f"范围：{request.get('start', result['ranked_dates'][0]['date'])}—{request.get('end', '已指定范围')}；显示时区：{result['timezone']}。", '']
    lines += brief_date_lines(result['ranked_dates'], top)
    lines += ['时辰名称与方位按北京时间通书；位置采用时喜神方，不是个人命盘喜用方。',
              '民俗取象，仅供娱乐；稿件完备与正式截止优先。']
    return '\n'.join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description='Cell 科研玄学：默认采用内置规则直接计算；不随机抽分。')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('rules', help='查看当前默认规则')
    sub.add_parser('doctor', help='查看依赖与默认规则状态')
    ap = sub.add_parser('approve', help='仅在用户已明确确认后记录批准')
    ap.add_argument('--ack', required=True)
    rp = sub.add_parser('rank', help='计算可用时窗；默认仅计算当地明天')
    rp.add_argument('--event', default='submission')
    rp.add_argument('--timezone', required=True)
    rp.add_argument('--start', type=date.fromisoformat)
    rp.add_argument('--end', type=date.fromisoformat)
    rp.add_argument('--days', type=int, default=1)
    rp.add_argument('--ready-at', type=parse_aware)
    rp.add_argument('--deadline', type=parse_aware)
    rp.add_argument('--deadline-buffer', type=int, default=30)
    rp.add_argument('--exclude-date', type=date.fromisoformat, action='append', default=[])
    rp.add_argument('--block', action='append', default=[], help='带偏移开始/结束ISO时间')
    rp.add_argument('--minimum-minutes', type=int, default=20)
    rp.add_argument('--top', type=int, default=3)
    rp.add_argument('--output', type=Path, help='可选结论Markdown路径')
    rp.add_argument('--audit', type=Path, help='可选本地完整事实、分项、排序JSON；不上传')
    rp.add_argument('--report-style', choices=['brief','detailed'], default='brief', help='默认按日期/星期/时辰/位置简洁展示')
    args = p.parse_args(argv)
    try:
        rules = load_rules()
        if args.command == 'rules':
            print(json.dumps(rules, ensure_ascii=False, indent=2)); return 0
        if args.command == 'doctor':
            state = dependency_status()
            try:
                require_approval(rules); approved = True
            except OracleError:
                approved = False
            print(json.dumps({'dependencies': state, 'rules_enabled': approved, 'confirmation_required': False,
                              'engine': '通书择日，不是奇门排盘',
                              'runtime_ready': approved and all(v['ok'] for v in state.values())},
                             ensure_ascii=False, indent=2)); return 0
        if args.command == 'approve':
            print(json.dumps(approve_rules(rules, args.ack), ensure_ascii=False, indent=2)); return 0
        approval = require_approval(rules)
        provider = LiveProvider()
        zone = ensure_zone(args.timezone)
        now = datetime.now(UTC)
        if args.days < 1 or args.top < 1: raise OracleError('天数和展示数量必须为正。')
        start = args.start or (now.astimezone(zone).date() + timedelta(days=1))
        end = args.end or start + timedelta(days=args.days - 1)
        lower = max(now, args.ready_at.astimezone(UTC)) if args.ready_at else now
        blocked = []
        for value in args.block:
            try:
                a, b = value.split('/', 1)
                blocked.append((parse_aware(a), parse_aware(b)))
            except ValueError as exc:
                raise OracleError('--block格式为开始ISO时间/结束ISO时间，均含UTC偏移。') from exc
        windows = enumerate_windows(start, end, args.timezone, lower, args.deadline,
                                    args.deadline_buffer, blocked, set(args.exclude_date), args.minimum_minutes)
        result = rank_windows(windows, provider, rules, args.event)
        result.update({'timezone': args.timezone,
                       'calendar_convention': 'CST lunar-month almanac + CST hour deity; 23:00 day rollover; not local true solar time',
                       'rule_policy': approval, 'dependencies': provider.versions,
                       'generated_at_utc': now.isoformat(),
                       'request': {'start': str(start), 'end': str(end),
                                   'ready_at': args.ready_at.isoformat() if args.ready_at else None,
                                   'deadline': args.deadline.isoformat() if args.deadline else None,
                                   'deadline_buffer_minutes': args.deadline_buffer,
                                   'excluded_dates': [str(d) for d in args.exclude_date], 'blocked': args.block}})
        report = public_report(result, args.top, args.report_style)
        for path, text in [(args.output, report), (args.audit, json.dumps(result, ensure_ascii=False, indent=2))]:
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding='utf-8')
        print(report)
        return 0
    except (OracleError, OSError, json.JSONDecodeError) as exc:
        print('未生成推荐：' + str(exc), file=sys.stderr)
        return 2


def configure_cli_streams() -> None:
    """Keep Chinese CLI output readable under Windows legacy encodings."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')


if __name__ == '__main__':
    configure_cli_streams()
    raise SystemExit(main())
