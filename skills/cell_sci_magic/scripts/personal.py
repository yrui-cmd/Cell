"""Birth-chart-based cultural ranking. No network, no fabricated birth data."""
from __future__ import annotations

import argparse
import calendar
import json
import math
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

from lunar_python import Solar, Lunar
from lunar_python.util import LunarUtil
import oracle as o
import natal_analysis as na

ROOT = Path(__file__).resolve().parents[1]
RULE_PATH = ROOT / 'rules/personal-v1.json'
STEMS = '甲乙丙丁戊己庚辛壬癸'
ELEMENTS = dict(zip(STEMS, '木木火火土土金金水水'))
CLASH = {frozenset(x) for x in ['子午','丑未','寅申','卯酉','辰戌','巳亥']}
COMBINE = {frozenset(x) for x in ['子丑','寅亥','卯戌','辰酉','巳申','午未']}
STEM_COMBINE = {frozenset(x) for x in ['甲己','乙庚','丙辛','丁壬','戊癸']}


def load_rules():
    rules = json.loads(RULE_PATH.read_text(encoding='utf-8'))
    if rules['rule_id'] != 'personal-bazi-v1' or rules['pillar_sect'] != 1:
        raise o.OracleError('未知个人排盘版本，不能静默换算法。')
    return rules


def longitude(value):
    x = float(value)
    if not math.isfinite(x) or not -180 <= x <= 180:
        raise o.OracleError('经度须为-180至180度，东经为正。')
    return x


def equation_of_time(instant):
    """NOAA fractional-year approximation, minutes; not ephemeris precision."""
    dt = instant.astimezone(o.UTC)
    hour = dt.hour + dt.minute / 60 + dt.second / 3600
    gamma = 2 * math.pi / (366 if calendar.isleap(dt.year) else 365) * (dt.timetuple().tm_yday - 1 + (hour - 12) / 24)
    return 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
                     - 0.014615 * math.cos(2*gamma) - 0.040849 * math.sin(2*gamma))


def solar_clock(instant, lon):
    return instant.astimezone(o.UTC).replace(tzinfo=None) + timedelta(minutes=4*lon + equation_of_time(instant))


def lunar_at(clock):
    return Solar.fromYmdHms(clock.year, clock.month, clock.day, clock.hour, clock.minute, clock.second).getLunar()


def pillars(instant, lon):
    # Solar terms are absolute instants; never shift the Li Chun boundary by longitude.
    actual = lunar_at(instant.astimezone(o.CST)).getEightChar()
    local = lunar_at(solar_clock(instant, lon)).getEightChar()
    local.setSect(1)
    return [actual.getYear(), actual.getMonth(), local.getDay(), local.getTime()]


def resolve_birth(profile):
    required = ['calendar', 'birth_date', 'birth_time', 'birth_place', 'birth_timezone', 'birth_longitude']
    missing = [k for k in required if k not in profile or profile[k] in (None, '')]
    if missing:
        raise o.OracleError('个人八字资料缺失：' + '、'.join(missing) + '。不回退为通用推荐。')
    if not isinstance(profile['birth_place'], str) or not profile['birth_place'].strip():
        raise o.OracleError('请提供出生城市，不需要详细地址。')
    zone = o.ensure_zone(profile['birth_timezone'])
    lon = longitude(profile['birth_longitude'])
    parts = [int(x) for x in profile['birth_date'].split('-')]
    if len(parts) != 3:
        raise o.OracleError('出生日期格式为YYYY-MM-DD。')
    year, month, day = parts
    if not 1901 <= year <= 2099:
        raise o.OracleError('本版出生年份范围1901—2099。')
    if profile['calendar'] == 'lunar':
        if profile['birth_timezone'] != 'Asia/Shanghai' or type(profile.get('leap_month')) is not bool:
            raise o.OracleError('农历输入须明确闰月与Asia/Shanghai时区；海外农历请先核实公历日期。')
        month = -month if profile['leap_month'] else month
        try:
            lunar = Lunar.fromYmd(year, month, day)
        except Exception as exc:
            raise o.OracleError('农历日期或闰月不存在：' + str(exc)) from exc
        solar = lunar.getSolar()
        check = solar.getLunar()
        if (check.getYear(), check.getMonth(), check.getDay()) != (year, month, day):
            raise o.OracleError('农历日期或闰月不存在。')
        raw = date(solar.getYear(), solar.getMonth(), solar.getDay())
    elif profile['calendar'] == 'solar':
        raw = date(year, month, day)
    else:
        raise o.OracleError('calendar只能为solar或lunar，不能猜阴阳历。')
    clock = time.fromisoformat(profile['birth_time'])
    if clock.tzinfo is not None:
        raise o.OracleError('birth_time填写当地钟表时间，偏移另填birth_utc_offset。')
    naive = datetime.combine(raw, clock)
    valid = {}
    for fold in [0, 1]:
        aware = naive.replace(tzinfo=zone, fold=fold)
        if aware.astimezone(o.UTC).astimezone(zone).replace(tzinfo=None) == naive:
            valid[aware.utcoffset()] = aware
    if not valid:
        raise o.OracleError('出生钟表时间在夏令时跳时中不存在。')
    offset = profile.get('birth_utc_offset')
    if offset:
        explicit = datetime.fromisoformat(naive.isoformat() + offset)
        valid = {k:v for k,v in valid.items() if k == explicit.utcoffset()}
    if len(valid) != 1:
        raise o.OracleError('出生时刻存在夏令时歧义或偏移不匹配，请补充birth_utc_offset。')
    instant = next(iter(valid.values())).astimezone(o.UTC)
    if instant > datetime.now(o.UTC):
        raise o.OracleError('出生时间不能在未来。')
    uncertainty = float(profile.get('birth_time_uncertainty_minutes', 1))
    if not math.isfinite(uncertainty) or uncertainty < 0:
        raise o.OracleError('出生时间误差须为非负分钟数。')
    safety = uncertainty + load_rules()['solar_error_buffer_minutes']
    chart = pillars(instant, lon)
    if any(pillars(instant + timedelta(minutes=delta), lon) != chart for delta in [-safety, safety]):
        raise o.OracleError('出生时刻误差范围跨越时辰、换日或节气边界；需核实时间或分别排盘，不能给唯一推荐。')
    dm = chart[2][0]
    details = []
    for name, gz in zip(['年柱','月柱','日柱','时柱'], chart):
        hidden = LunarUtil.ZHI_HIDE_GAN[gz[1]]
        details.append({'name':name, 'ganzhi':gz, 'stem_element':ELEMENTS[gz[0]],
                        'stem_god':LunarUtil.SHI_SHEN[dm+gz[0]],
                        'hidden_stems':[{'stem':x,'element':ELEMENTS[x],'god':LunarUtil.SHI_SHEN[dm+x]} for x in hidden]})
    return {'pillars':chart, 'day_master':dm, 'details':details,
            'birth_place':profile['birth_place'], 'birth_timezone':profile['birth_timezone'],
            'longitude':lon, 'birth_utc':instant.isoformat(),
            'solar_clock':solar_clock(instant,lon).isoformat(),
            'uncertainty_minutes':uncertainty, 'boundary_buffer_minutes':safety,
            'calendar_method':'立春年界、节令月界；当地近似真太阳时定日时，23点换日'}


def personal_score(natal, candidate, rules):
    reasons, score = [], 0
    for cname, gz in zip(['候选日柱','候选时柱'], candidate[2:]):
        for name, ngz, weight in zip(['本命年柱','本命月柱','本命日柱','本命时柱'], natal['pillars'], rules['natal_pillar_weights']):
            branch = frozenset([gz[1],ngz[1]])
            for applies, label, points in [
                (branch in CLASH,'地支六冲',-rules['clash_penalty']*weight),
                (branch in COMBINE,'地支六合',rules['branch_combine_bonus']*weight),
                (frozenset([gz[0],ngz[0]]) in STEM_COMBINE,'天干五合',rules['stem_combine_bonus']*weight)]:
                if applies:
                    score += points
                    reasons.append({'candidate':cname,'natal':name,'relation':label,'points':points,'pair':gz+' / '+ngz})
        god = LunarUtil.SHI_SHEN[natal['day_master']+gz[0]]
        bonus = rules['writing_god_bonus'].get(god,0)
        score += bonus
        reasons.append({'candidate':cname,'relation':'日主十神','god':god,'points':bonus,'stem':gz[0]})
    day_clash = frozenset([candidate[2][1],natal['pillars'][2][1]]) in CLASH
    return {'personal_score':score,'personal_reasons':reasons,
            'natal_day_clash':day_clash,'candidate_bazi':candidate,
            'personal_eligible':not (day_clash and rules['exclude_candidate_day_clash_natal_day'])}


def solar_boundaries(a, b, lon):
    cuts = {a,b}
    d = solar_clock(a,lon).date() - timedelta(days=1)
    last = solar_clock(b,lon).date() + timedelta(days=1)
    while d <= last:
        for h in range(1,24,2):
            target = datetime.combine(d,time(h))
            guess = target.replace(tzinfo=o.UTC) - timedelta(minutes=4*lon)
            for _ in range(5):
                guess = target.replace(tzinfo=o.UTC) - timedelta(minutes=4*lon+equation_of_time(guess))
            if a < guess < b: cuts.add(guess)
        d += timedelta(days=1)
    for year in range(a.year-1,b.year+2):
        for term in Solar.fromYmd(year,6,1).getLunar().getJieQiTable().values():
            cut = datetime.fromisoformat(term.toYmdHms()).replace(tzinfo=o.CST).astimezone(o.UTC)
            if a < cut < b: cuts.add(cut)
    return sorted(cuts)


def refine_windows(windows, lon, zone, minimum, rules, extra_cuts=()):
    out=[]
    buffer=timedelta(minutes=rules['solar_error_buffer_minutes'])
    for w in windows:
        a,b=o.parse_aware(w['start']).astimezone(o.UTC),o.parse_aware(w['end']).astimezone(o.UTC)
        cuts=sorted(set(solar_boundaries(a,b,lon)) | {c for c in extra_cuts if a<c<b})
        for x,y in zip(cuts,cuts[1:]):
            mid=x+(y-x)/2
            signature=pillars(mid,lon)
            if pillars(x-buffer,lon)!=signature: x+=buffer
            if pillars(y+buffer,lon)!=signature: y-=buffer
            # Display whole minutes only; round inward so boundaries never claim false precision.
            if x.second or x.microsecond:x=x.replace(second=0,microsecond=0)+timedelta(minutes=1)
            y=y.replace(second=0,microsecond=0)
            if (y-x).total_seconds() < minimum*60:continue
            out.append({**w,'start':x.astimezone(zone).isoformat(),'end':y.astimezone(zone).isoformat(),
                        'start_cst':x.astimezone(o.CST).isoformat(),'end_cst':y.astimezone(o.CST).isoformat(),
                        'duration_minutes':(y-x).total_seconds()/60})
    return out


def rank_personal(base,natal,lon,rules):
    if 'analysis' not in natal or 'dayun' not in natal:
        raise o.OracleError('完整个人排序缺少旺衰取用或大运分析；不回退v1固定冲合排序。')
    analysis_rules=na.load_rules()
    # Remove generic recommendations from the personal result contract entirely.
    base['almanac_summary'] = {key:base.pop(key) for key in
        ['status','best_score','eligible_count']}
    base.pop('ranked_dates')
    base.pop('top_tied_windows')
    for c in base['candidates']:
        a,b=o.parse_aware(c['start']),o.parse_aware(c['end'])
        mid=a+(b-a)/2
        candidate=pillars(mid,lon)
        # v2 removes the old unconditional 印/食神 bonus. Preferences come from the analyzed chart.
        c.update(personal_score(natal,candidate,{**rules,'writing_god_bonus':{}}))
        compatibility=c['personal_score']
        fit=na.candidate_fit(natal,candidate,mid,analysis_rules)
        edge_states=[na.active_yun(natal['dayun'],t) for t in [a,b-timedelta(seconds=1)]]
        if any(x['status']=='uncertain_transition' for x in edge_states) or edge_states[0].get('ganzhi')!=edge_states[1].get('ganzhi'):
            fit['review_flags'].append({'code':'window_crosses_yun_transition','reason':'候选窗横跨换运或出生误差引起的换运区间'})
            fit['auto_eligible']=False
        c['compatibility_score']=compatibility
        c['analysis_fit']=fit
        c['personal_score']=round(fit['fit_score']+analysis_rules['interaction_weight']*compatibility,4)
        c['almanac_and_clash_eligible']=c['eligible'] and c['personal_eligible']
        c['eligible']=c['almanac_and_clash_eligible'] and fit['auto_eligible']
    eligible=[c for c in base['candidates'] if c['eligible']]
    eligible.sort(key=lambda c:(-c['personal_score'],-c['score'],c['start']))
    dates={}
    for c in eligible:
        key=(c['personal_score'],c['score'])
        if c['local_date'] not in dates:dates[c['local_date']]={'date':c['local_date'],'key':key,'windows':[c]}
        elif dates[c['local_date']]['key']==key:dates[c['local_date']]['windows'].append(c)
    base.update({'mode':'personal_bazi','natal':natal,'personal_rule_id':rules['rule_id'],
                 'analysis_rule_id':analysis_rules['rule_id'],'analysis_rule_digest':o.rule_digest(analysis_rules),
                 'personal_rule_digest':o.rule_digest(rules), 'submission_longitude':lon,
                 'ranked_personal_dates':sorted(dates.values(),key=lambda d:(-d['key'][0],-d['key'][1],d['date'])),
                 'personal_eligible_count':len(eligible),
                 'status':'personal_ranked' if eligible else 'analysis_review_required' if any(c['almanac_and_clash_eligible'] for c in base['candidates']) else 'no_personal_eligible_window',
                 'review_candidates':sorted([c for c in base['candidates'] if c['almanac_and_clash_eligible'] and not c['eligible']],key=lambda c:(-c['personal_score'],-c['score'],c['start']))})
    return base


def report(result,top):
    n=result['natal']
    lines=['# Cell 科研玄学｜个人八字投稿择时',
           f"范围：{result['request']['start']}—{result['request']['end']}；显示时区：{result['timezone']}。",
           '四柱：'+' / '.join(n['pillars'])+f"；日主：{n['day_master']}。",
           f"出生地：{n['birth_place']}；出生时区：{n['birth_timezone']}；经度：{n['longitude']}。",
           '出生校正后近似真太阳时：'+n['solar_clock']+'；节气月、立春年界、23点换日。',
           '排序：本命旺衰取用与大运/流年/流月上下文估算取保守值，冲合为辅助；通书分另列。','',
           '| 顺位 | 日期 | 当地时窗 | 个人栏目分 | 通书分 |','|---|---|---|---:|---:|']
    for i,d in enumerate(result['ranked_personal_dates'][:top]):
        ts='；'.join(o.parse_aware(c['start']).strftime('%H:%M')+'—'+o.parse_aware(c['end']).strftime('%H:%M') for c in d['windows'])
        lines.append(f"| {'首选' if i==0 else '备选'} | {d['date']} | {ts} | {d['key'][0]} | {d['key'][1]}/100 |")
    if not result['ranked_personal_dates']:
        lines.append('\n本次未生成可自动认定的个人首选。下列解释或待复核候选不能当作已确定推荐，不回退通用结果。')
    else:
        best=result['ranked_personal_dates'][0]['windows'][0]
        lines+=['','首窗候选四柱：'+' / '.join(best['candidate_bazi'])+'。','个人依据：']
        for reason in best['personal_reasons']:
            if reason['relation']=='日主十神':
                lines.append(f"- {reason['candidate']}天干为日主的{reason['god']}，栏目分{reason['points']:+d}。")
            else:
                lines.append(f"- {reason['candidate']}与{reason['natal']}{reason['relation']}（{reason['pair']}），栏目分{reason['points']:+d}。")
    an=n['analysis'];yun=n['dayun'];s=an['strength'];ys=an['yongshen'];age=yun['start_age'];display_zone=o.ensure_zone(result['timezone'])
    lines+=['','## 本命旺衰、格局与取用',
            f"旺衰模型：{s['label']}；同类与印支持比例{s['support_ratio']:.3f}（工程指标，不是概率）；季令五行{s['season']}，{s['season_relation']}，通根记录{len(s['roots'])}项。",
            f"格局线索：{an['pattern']['candidate']}；月令藏干透出：{'、'.join(an['pattern']['exposed_stems']) or '未透，保留月令本气候选'}。不直接断成格。",
            '结构线索：'+'；'.join(an['pattern']['structure_clues'] or ['未列出特定十神组合线索']),
            f"月令格局用神标签：{an['pattern']['month_yongshen_god']}；扶抑用神候选：{ys['primary_candidate'] or '未唯一确定'}；喜向：{'、'.join(ys['favorable']) or '未定'}；忌向：{'、'.join(ys['unfavorable']) or '未定'}。",
            '调候提示：'+'；'.join(ys['tiao_hou_hints'] or ['调候未单独裁决，不将五行缺项当用神']),
            '敏感性试算：'+' / '.join(x['label'] for x in an['sensitivity']),
            '', '## 大运与投稿时段上下文',
            f"排运：{'顺行' if yun['forward'] else '逆行'}，采用节气间隔分钟折算法；出生后{age['years']}年{age['months']}个月{age['days']}天{age['hours']}小时起运；起运时刻{o.parse_aware(yun['start_utc']).astimezone(display_zone).isoformat()}。",
            '十年换运按起运实际时刻周年计算，完整运表及出生误差区间见JSON依据。']
    selected=result['ranked_personal_dates'][0]['windows'][0] if result['ranked_personal_dates'] else next(iter(result['review_candidates']),None)
    if selected:
        ctx=selected['analysis_fit']['context'];active=ctx['dayun']
        lines += [f"所列首窗/待复核首窗上下文：大运{active.get('ganzhi') or active['status']}，流年{ctx['year']}，流月{ctx['month']}；运势上下文旺衰估算：{ctx['analysis']['strength']['label']}。"]
        lines+=['候选日时如何承接取用（模型依据）：']
        for scenario in selected['analysis_fit']['fit_scenarios']:
            details='；'.join(f"{x['source']}属{x['element']}：{x['points']:+g}" for x in scenario['contributions'])
            lines.append(f"- {scenario['scenario']}，合计{scenario['score']:+g}：{details}。")
        lines.append(f"冲合辅助分：{selected['compatibility_score']}，按0.2系数计入；不再固定奖励印星。")
        for cycle in yun['cycles']:
            if active.get('cycle',{}).get('index')==cycle['index']:
                lines.append(f"当前大运范围：{o.parse_aware(cycle['start_utc']).astimezone(display_zone).isoformat()} 至 {o.parse_aware(cycle['end_utc']).astimezone(display_zone).isoformat()}（不含结束时刻）；{cycle['judgment']}。")
    flags=an['review_flags']+([*selected['analysis_fit']['review_flags']] if selected else [])
    unique={x['reason']:x for x in flags}
    if unique:lines+=['','需复核：']+['- '+x for x in unique]
    if result['review_candidates']:
        lines+=['','待复核窗口（不是推荐）：']
        for c in result['review_candidates'][:top]:
            lines.append(f"- {c['start']} 至 {c['end']}；模型比较值{c['personal_score']}，通书{c['score']}分。")
    lines+=['','旺衰和扶抑取用为公开系数估算，格局只给条件候选；从格、专旺、合化或歧义不自动强断。不是全流派完整命理判断。近似太阳时保留误差缓冲。',
            '民俗取象，仅供娱乐；个人栏目分与通书分均不是录用概率，稿件完备和截止优先。']
    return '\n'.join(lines)


def main(argv=None):
    p=argparse.ArgumentParser(description='个人四柱实排及投稿冲合比较；缺出生资料不回退通用结果。')
    p.add_argument('command',choices=['chart','rank'])
    p.add_argument('--profile',type=Path,required=True)
    p.add_argument('--timezone')
    p.add_argument('--longitude',type=longitude,help='当前实际投稿地点经度；东正西负')
    p.add_argument('--start',type=date.fromisoformat)
    p.add_argument('--end',type=date.fromisoformat)
    p.add_argument('--days',type=int,default=7)
    p.add_argument('--event',choices=['submission','revision','grant'],default='submission')
    p.add_argument('--ready-at',type=o.parse_aware)
    p.add_argument('--deadline',type=o.parse_aware)
    p.add_argument('--deadline-buffer',type=int,default=30)
    p.add_argument('--exclude-date',type=date.fromisoformat,action='append',default=[])
    p.add_argument('--block',action='append',default=[])
    p.add_argument('--minimum-minutes',type=int,default=20)
    p.add_argument('--top',type=int,default=3)
    p.add_argument('--output',type=Path)
    p.add_argument('--audit',type=Path)
    a=p.parse_args(argv)
    try:
        o.LiveProvider()  # Check pinned dependencies before claiming an actual chart.
        rules=load_rules()
        profile=json.loads(a.profile.read_text(encoding='utf-8-sig'))
        natal=resolve_birth(profile)
        natal['analysis']=na.analyze(natal)
        natal['dayun']=na.build_yun(natal,profile)
        if a.command=='chart':
            print(json.dumps(natal,ensure_ascii=False,indent=2));return 0
        if not a.timezone or a.longitude is None:
            raise o.OracleError('个人投稿排序还需要当前所在地时区--timezone和经度--longitude，不假设与出生地相同。')
        if not 1<=a.days<=93 or not 1<=a.top<=93:
            raise o.OracleError('days和top须为1—93。')
        zone=o.ensure_zone(a.timezone)
        now=datetime.now(o.UTC)
        start=a.start or now.astimezone(zone).date()+timedelta(days=1)
        end=a.end or start+timedelta(days=a.days-1)
        lower=max(now,a.ready_at.astimezone(o.UTC)) if a.ready_at else now
        blocked=[]
        for item in a.block:
            x,y=item.split('/',1);blocked.append((o.parse_aware(x),o.parse_aware(y)))
        windows=o.enumerate_windows(start,end,a.timezone,lower,a.deadline,a.deadline_buffer,blocked,set(a.exclude_date),a.minimum_minutes)
        transition_cuts=[o.parse_aware(c[key]) for c in natal['dayun']['cycles'] for key in ['earliest_start_utc','latest_start_utc','earliest_end_utc','latest_end_utc']]
        refined=refine_windows(windows,a.longitude,zone,a.minimum_minutes,rules,transition_cuts)
        base=o.rank_windows(refined,o.LiveProvider(),o.load_rules(),a.event)
        result=rank_personal(base,natal,a.longitude,rules)
        result.update({'timezone':a.timezone,'generated_at_utc':now.isoformat(),
                       'request':{'start':str(start),'end':str(end),'ready_at':a.ready_at.isoformat() if a.ready_at else None,
                                  'deadline':a.deadline.isoformat() if a.deadline else None,'blocked':a.block,
                                  'excluded_dates':[str(x) for x in a.exclude_date]},
                       'solar_method':'NOAA fractional-year equation of time, east-positive longitude, 2-minute boundary guard',
                       'dependencies':o.dependency_status()})
        text=report(result,a.top)
        for path,content in [(a.output,text),(a.audit,json.dumps(result,ensure_ascii=False,indent=2))]:
            if path:
                path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
        print(text);return 0
    except (o.OracleError,ValueError,KeyError,TypeError,OSError) as exc:
        print('未生成个人推荐：'+str(exc),file=sys.stderr);return 2


if __name__=='__main__':
    o.configure_cli_streams()
    raise SystemExit(main())
