"""Explicit, bounded BaZi interpretation model; separate calendar facts from estimates."""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

from lunar_python import Solar
from lunar_python.util import LunarUtil
import oracle as o

ROOT = Path(__file__).resolve().parents[1]
STEMS = '甲乙丙丁戊己庚辛壬癸'
ELEMENTS = dict(zip(STEMS, '木木火火土土金金水水'))
CYCLE = '木火土金水'
GENERATES = dict(zip(CYCLE, CYCLE[1:]+CYCLE[:1]))
RESOURCE = {v:k for k,v in GENERATES.items()}
CONTROLS = dict(zip(CYCLE, CYCLE[2:]+CYCLE[:2]))
OFFICER = {v:k for k,v in CONTROLS.items()}
SEASON = dict(zip('寅卯辰巳午未申酉戌亥子丑','木木土火火土金金土水水土'))
CLASH = {frozenset(x) for x in ['子午','丑未','寅申','卯酉','辰戌','巳亥']}
LU = dict(zip(STEMS,'寅卯巳午巳午申酉亥子'))
BLADE = dict(zip('甲丙戊庚壬','卯午午酉子'))
FORMATIONS = [('三合木','亥卯未'),('三合火','寅午戌'),('三合金','巳酉丑'),('三合水','申子辰'),
              ('三会木','寅卯辰'),('三会火','巳午未'),('三会金','申酉戌'),('三会水','亥子丑')]
STEM_PAIRS = ['甲己','乙庚','丙辛','丁壬','戊癸']


def load_rules():
    rules=json.loads((ROOT/'rules/analysis-v2.json').read_text(encoding='utf-8'))
    if rules['rule_id']!='natal-analysis-v2' or rules['yun_sect']!=2:
        raise o.OracleError('未知旺衰/大运模型版本。')
    if not 0<rules['weak_below']<rules['strong_above']<1 or len(rules['stem_weights'])!=4 or len(rules['branch_weights'])!=4:
        raise o.OracleError('旺衰阈值或柱权重结构无效。')
    numbers=rules['stem_weights']+rules['branch_weights']+rules['season_factors']+list(rules['context_weights'].values())
    if len(rules['season_factors'])!=5 or any(not math.isfinite(v) or v<0 for v in numbers):
        raise o.OracleError('五行系数须为有限非负数。')
    for size,shares in rules['hidden_weights'].items():
        if len(shares)!=int(size) or abs(sum(shares)-1)>1e-8 or any(x<=0 for x in shares):
            raise o.OracleError('藏干分配系数无效。')
    return rules


def element_roles(dm):
    elem=ELEMENTS[dm]
    return {elem:'比劫',RESOURCE[elem]:'印',GENERATES[elem]:'食伤',CONTROLS[elem]:'财',OFFICER[elem]:'官杀'}


def strength(gz, rules=None, context=(), month_scale=1.0, season_scale=1.0):
    rules=rules or load_rules()
    dm=gz[2][0]
    roles=element_roles(dm)
    season=SEASON[gz[1][1]]
    # 旺、相、休、囚、死: same, produced by season, produces season, controls season, controlled by season.
    order=[season,GENERATES[season],RESOURCE[season],OFFICER[season],CONTROLS[season]]
    factors={e:1+(v-1)*season_scale for e,v in zip(order,rules['season_factors'])}
    amounts={e:0.0 for e in CYCLE}
    evidence=[]
    roots=[]
    for i,pillar in enumerate(gz):
        stem,branch=pillar
        weight=rules['stem_weights'][i]
        if weight:
            points=weight*factors[ELEMENTS[stem]]
            amounts[ELEMENTS[stem]]+=points
            evidence.append({'source':['年干','月干','日干','时干'][i],'stem':stem,'qi':round(points,4)})
        hidden=LunarUtil.ZHI_HIDE_GAN[branch]
        for h,w in zip(hidden,rules['hidden_weights'][str(len(hidden))]):
            points=rules['branch_weights'][i]*w*factors[ELEMENTS[h]]*(month_scale if i==1 else 1)
            amounts[ELEMENTS[h]]+=points
            evidence.append({'source':['年支','月支','日支','时支'][i],'branch':branch,'stem':h,'qi':round(points,4)})
            if ELEMENTS[h]==ELEMENTS[dm]:roots.append({'pillar':i,'branch':branch,'stem':h,'same_stem':h==dm,'share':w})
    for label,pillar,weight in context:
        if not pillar:continue
        parts=[(pillar[0],0.5)]
        hidden=LunarUtil.ZHI_HIDE_GAN[pillar[1]]
        parts.extend(zip(hidden,[0.5*w for w in rules['hidden_weights'][str(len(hidden))]]))
        for stem,w in parts:
            points=weight*w*factors[ELEMENTS[stem]]
            amounts[ELEMENTS[stem]]+=points
            evidence.append({'source':label,'ganzhi':pillar,'stem':stem,'qi':round(points,4)})
    support=sum(v for e,v in amounts.items() if roles[e] in ['印','比劫'])
    ratio=support/sum(amounts.values())
    label='偏弱' if ratio<rules['weak_below'] else '偏强' if ratio>rules['strong_above'] else '中和区间'
    return {'label':label,'support_ratio':round(ratio,6),'element_qi':{e:round(v,4) for e,v in amounts.items()},
            'season':season,'month_main_god':LunarUtil.SHI_SHEN[dm+LunarUtil.ZHI_HIDE_GAN[gz[1][1]][0]],
            'day_master_season_factor':factors[ELEMENTS[dm]],
            'season_relation':'得旺令' if season==ELEMENTS[dm] else '季令相生' if GENERATES[season]==ELEMENTS[dm] else '非旺相令（仍须看根、透干与制泄）',
            'season_factors':factors,'roots':roots,'evidence':evidence,'roles':roles,
            'nature':'月令/藏干加权估算；支持比例不是命理强弱概率'}


def pattern(gz):
    dm=gz[2][0]
    month=gz[1][1]
    hidden=LunarUtil.ZHI_HIDE_GAN[month]
    visible=[gz[i][0] for i in [0,1,3]]
    exposed=[s for s in hidden if s in visible]
    selected=exposed[0] if exposed else hidden[0]
    god=LunarUtil.SHI_SHEN[dm+selected]
    name='阳刃格候选' if BLADE.get(dm)==month else '建禄格候选' if LU[dm]==month else god+'格候选'
    all_gods={LunarUtil.SHI_SHEN[dm+s] for s in visible}
    all_gods.update(LunarUtil.SHI_SHEN[dm+s] for p in gz for s in LunarUtil.ZHI_HIDE_GAN[p[1]])
    lines=[]
    if '食神' in all_gods and '七杀' in all_gods:lines.append('食神与七杀并见，存在食神制杀结构线索，未断成格')
    if '伤官' in all_gods and '正印' in all_gods:lines.append('伤官与正印并见，存在伤官配印结构线索，未断成格')
    if '七杀' in all_gods and ('正印' in all_gods or '偏印' in all_gods):lines.append('杀印同见，需看力量与位置，未断杀印成格')
    if '正官' in all_gods and '七杀' in all_gods:lines.append('官杀并见，需复核清浊去留')
    return {'candidate':name,'month_branch':month,'month_hidden_stems':hidden,'exposed_stems':exposed,
            'selected_stem':selected,'month_yongshen_god':god,
            'basis':'月令藏干透出优先；多透按藏干顺序展示候选，不能据此断清纯成格',
            'structure_clues':lines,'status':'candidate_not_final_formation'}


def analyze(natal, context=(), rules=None):
    rules=rules or load_rules()
    gz=natal['pillars']
    base=strength(gz,rules,context)
    scenarios=[strength(gz,rules,context,a,b) for a,b in rules['sensitivity']]
    labels={s['label'] for s in scenarios}
    pat=pattern(gz)
    flags=[]
    if len(labels)>1:flags.append({'code':'unstable_strength','reason':'月令/季节系数敏感性试算跨旺衰类别，不能唯一自动取用'})
    if base['support_ratio']<0.15 or base['support_ratio']>0.85:
        flags.append({'code':'possible_special_pattern','reason':'极端偏向可能涉及从格或专旺，普通扶抑法不能代替特殊格判断'})
    branches={x[1] for x in gz}
    for name,group in FORMATIONS:
        if set(group)<=branches:flags.append({'code':'full_branch_formation','reason':name+'字齐，合化条件未自动裁决'})
    stems={x[0] for x in gz}
    for pair in STEM_PAIRS:
        if set(pair)<=stems:flags.append({'code':'stem_combination','reason':pair+'相合涉及合而不化/合化差异，不能自动改五行'})
    if len(pat['exposed_stems'])>1:
        flags.append({'code':'mixed_month_exposure','reason':'月令多藏干透出，格局取用存在分支'})
    if any(frozenset([gz[1][1],x[1]]) in CLASH for i,x in enumerate(gz) if i!=1):
        flags.append({'code':'month_clash','reason':'月令逢冲，格局成败未自动裁决'})
    base_preferences={e:rules['yong_preferences'][base['label']][role] for e,role in base['roles'].items()}
    total_qi=sum(base['element_qi'].values())
    pressure=1+rules['imbalance_pressure_multiplier']*abs(base['support_ratio']-0.5)
    choices={}
    for e,value in base_preferences.items():
        share=base['element_qi'][e]/total_qi
        # Explicit engineering severity/scarcity adjustment, not a traditional formula.
        adjustment=1+rules['element_share_adjustment']*share*(-1 if value>0 else 1)
        choices[e]=round(value*pressure*adjustment,4)
    by_value=sorted(choices,key=lambda e:(-choices[e],CYCLE.index(e)))
    favorable=[e for e in by_value if choices[e]>0]
    unfavorable=[e for e in by_value if choices[e]<0]
    hints=[]
    if gz[1][1] in '亥子丑':hints.append('冬月寒暖需复核；不能见冬就一律认定火为用神')
    if gz[1][1] in '巳午未':hints.append('夏月燥湿需复核；不能见夏就一律认定水为用神')
    if base['label']=='中和区间':hints.append('扶抑估算位于中和区间，不据此硬定唯一用神')
    # Pattern and strength are separate layers; do not call every monthly god favorable.
    god=pat['month_yongshen_god']
    role=base['roles']
    target_role=None
    if god in ['正官','七杀']:
        target_role='印' if base['label']=='偏弱' else '食伤' if god=='七杀' else '财'
    elif god in ['正财','偏财']:
        target_role='比劫' if base['label']=='偏弱' else '食伤'
    elif god in ['食神','伤官']:
        target_role='比劫' if base['label']=='偏弱' else '财'
    elif god in ['正印','偏印']:
        target_role='比劫' if base['label']=='偏弱' else '财'
    elif god in ['比肩','劫财']:
        target_role='印' if base['label']=='偏弱' else '食伤'
    target=next((e for e in CYCLE if role[e]==target_role),None)
    pat['strategy']={'role':target_role,'element':target,
                     'eligible_for_bonus':target in favorable,
                     'basis':'按月令格候选与身强弱选择辅助路径；不等于成格、相神或喜用已获定论'}
    return {'rule_id':rules['rule_id'],'rule_digest':o.rule_digest(rules),'strength':base,
            'sensitivity':[{'label':x['label'],'support_ratio':x['support_ratio']} for x in scenarios],
            'pattern':pat,'yongshen':{'method':'普通命局扶抑候选，不等同月令格局用神',
              'primary_candidate':favorable[0] if favorable else None,'favorable':favorable,
              'unfavorable':unfavorable,'preferences':choices,'tiao_hou_hints':hints,
              'base_preferences':base_preferences,'imbalance_pressure':round(pressure,6),
              'status':'review_required' if flags or not favorable else 'model_candidate'},
            'review_flags':flags,'status':'review_required' if flags else 'model_estimate',
            'limits':'旺衰系数、用神倾向是本项目显式估算，不是古籍原公式；格局成败与特殊格不强判'}


def build_yun(natal,profile,rules=None):
    rules=rules or load_rules()
    instant=o.parse_aware(natal['birth_utc'])
    birth=instant.astimezone(o.CST)
    lunar=Solar.fromYmdHms(birth.year,birth.month,birth.day,birth.hour,birth.minute,birth.second).getLunar()
    year_yang=STEMS.index(natal['pillars'][0][0])%2==0
    gender=profile.get('yun_gender')
    direction=profile.get('yun_direction')
    if gender not in (None,'male','female') or direction not in (None,'forward','backward'):
        raise o.OracleError('排运参数yun_gender须为male/female，或明确yun_direction为forward/backward。')
    if gender is None and direction is None:
        raise o.OracleError('完整大运计算需要传统排运参数yun_gender（male/female），或指定yun_direction（forward/backward）；不猜顺逆。')
    inferred=(year_yang and gender=='male') or (not year_yang and gender=='female') if gender else None
    if direction and inferred is not None and (direction=='forward')!=inferred:
        raise o.OracleError('指定顺逆与传统性别/年干排运规则冲突，请明确采用哪个口径。')
    forward=(direction=='forward') if direction else inferred
    effective_gender=1 if forward==year_yang else 0
    yun=lunar.getEightChar().getYun(effective_gender,rules['yun_sect'])
    start=yun.getStartSolar()
    def aware(s):return datetime.fromisoformat(s.toYmdHms()).replace(tzinfo=o.CST).astimezone(o.UTC)
    uncertainty=float(natal['uncertainty_minutes'])
    # Birth-clock uncertainty is magnified by start-age conversion; preserve both endpoints.
    variations=[]
    for delta in [-uncertainty,0,uncertainty]:
        t=(instant+timedelta(minutes=delta)).astimezone(o.CST)
        l=Solar.fromYmdHms(t.year,t.month,t.day,t.hour,t.minute,t.second).getLunar()
        variations.append(l.getEightChar().getYun(effective_gender,rules['yun_sect']).getStartSolar())
    cycles=[]
    for i,dy in enumerate(yun.getDaYun(rules['yun_cycles']+1)[1:]):
        starts=[aware(s.nextYear(i*10)) for s in variations]
        ends=[aware(s.nextYear((i+1)*10)) for s in variations]
        pref=natal.get('analysis',analyze(natal,rules=rules))['yongshen']['preferences']
        gz=dy.getGanZhi()
        h=LunarUtil.ZHI_HIDE_GAN[gz[1]]
        fit=pref[ELEMENTS[gz[0]]]+sum(w*pref[ELEMENTS[s]] for s,w in zip(h,rules['hidden_weights'][str(len(h))]))
        cycles.append({'index':i+1,'ganzhi':gz,'natal_fuyi_fit':round(fit,4),
                       'judgment':'按本命扶抑候选倾向支持' if fit>0 else '按本命扶抑候选倾向制耗或加剧失衡' if fit<0 else '扶抑候选未明确或正负抵消',
                       'start_utc':aware(start.nextYear(i*10)).isoformat(),'end_utc':aware(start.nextYear((i+1)*10)).isoformat(),
                       'earliest_start_utc':min(starts).isoformat(),'latest_start_utc':max(starts).isoformat(),
                       'earliest_end_utc':min(ends).isoformat(),'latest_end_utc':max(ends).isoformat()})
    return {'forward':bool(forward),'parameter_basis':'explicit_direction' if direction else 'traditional_gender_year_polarity',
            'sect':rules['yun_sect'],'start_age':{'years':yun.getStartYear(),'months':yun.getStartMonth(),'days':yun.getStartDay(),'hours':yun.getStartHour()},
            'start_utc':aware(start).isoformat(),'cycles':cycles,
            'convention':rules['yun_convention'],'uncertainty_basis':'出生钟表误差端点传播至起运时刻；不以整年标签代替换运瞬间'}


def active_yun(yun,instant):
    t=instant.astimezone(o.UTC)
    for c in yun['cycles']:
        if o.parse_aware(c['earliest_start_utc'])<=t<o.parse_aware(c['latest_start_utc']):
            return {'status':'uncertain_transition','ganzhi':None,'cycle':c}
        if o.parse_aware(c['latest_start_utc'])<=t<o.parse_aware(c['earliest_end_utc']):
            return {'status':'active','ganzhi':c['ganzhi'],'cycle':c}
    first=o.parse_aware(yun['cycles'][0]['earliest_start_utc'])
    return {'status':'before_start' if t<first else 'outside_supported_cycles','ganzhi':None}


def context_for(natal,candidate,instant,rules=None):
    rules=rules or load_rules()
    current=active_yun(natal['dayun'],instant)
    w=rules['context_weights']
    context=[('大运',current['ganzhi'],w['dayun']),('流年',candidate[0],w['year']),('流月',candidate[1],w['month'])]
    analysis=analyze(natal,context,rules)
    return {'dayun':current,'year':candidate[0],'month':candidate[1],
            'analysis':analysis,'context_evidence':context}


def candidate_fit(natal,candidate,instant,rules=None):
    rules=rules or load_rules()
    ctx=context_for(natal,candidate,instant,rules)
    natal_analysis=natal['analysis']
    contextual=ctx['analysis']
    blockers=natal_analysis['review_flags']+contextual['review_flags']
    if ctx['dayun']['status'] in ['uncertain_transition','outside_supported_cycles']:
        blockers=blockers+[{'code':ctx['dayun']['status'],'reason':'大运交界不确定或超过支持范围'}]
    # Different natal-vs-context labels are exposed, not silently collapsed into one score.
    scores=[]
    for label,analysis in [('本命扶抑',natal_analysis),('运年流月扶抑',contextual)]:
        pref=analysis['yongshen']['preferences']
        contributions=[]
        for name,pillar in zip(['候选日','候选时'],candidate[2:]):
            stem=ELEMENTS[pillar[0]]
            contributions.append({'source':name+'干','element':stem,'points':pref[stem]})
            hidden=LunarUtil.ZHI_HIDE_GAN[pillar[1]]
            for h,weight in zip(hidden,rules['hidden_weights'][str(len(hidden))]):
                contributions.append({'source':name+'支藏'+h,'element':ELEMENTS[h],'points':round(weight*pref[ELEMENTS[h]],4)})
            strategy=analysis['pattern']['strategy']
            if strategy['eligible_for_bonus'] and stem==strategy['element']:
                contributions.append({'source':name+'干格局辅助路径','element':stem,'points':0.5})
        scores.append({'scenario':label,'score':round(sum(x['points'] for x in contributions),4),'contributions':contributions})
    uncertain_yong=not natal_analysis['yongshen']['favorable'] or not contextual['yongshen']['favorable']
    if uncertain_yong:blockers.append({'code':'no_unique_fuyi_preference','reason':'中和区间未定扶抑用神，不强行给唯一偏好'})
    return {'context':ctx,'fit_scenarios':scores,'fit_score':min(x['score'] for x in scores),
            'review_flags':blockers,'auto_eligible':not blockers,
            'nature':'本命与运势上下文两种估算取较保守值；不是命理或录用概率'}
