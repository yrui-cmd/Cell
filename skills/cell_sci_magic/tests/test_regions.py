"""Synthetic facts verify rules only; no fixture is an actual auspicious date."""
import ast
import copy
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import oracle as o
import regional as r


def candidate(hour='09:00', ganzhi='甲子', day='2026-11-01', day_type='黄道日',
              luck='吉', good=True, bad=False):
    base=o.load_rules()
    facts={'good_activities':['上表章'] if good else [],
           'bad_activities':['上表章'] if bad else [],
           'day_type':day_type, 'hour_luck':luck, 'hour_ganzhi':ganzhi,
           'hour_deity':'玉堂', 'day_officer':'开',
           'fixture_type':'SYNTHETIC_NOT_AN_ACTUAL_CALENDAR_FACT'}
    score=o.score_facts(facts,base['events']['submission'],base)
    hh=int(hour[:2])
    return {'local_date':day,'start':f'{day}T{hour}:00+08:00',
            'end':f'{day}T{hh+2:02d}:00:00+08:00', 'facts':facts, **score,
            'event':'submission','action':'测试用，不是实际投稿建议'}


def base_result(items):
    return {'event':'submission','event_label':'论文投稿','rule_id':'submission-v1',
            'candidates':items}


class Regions(unittest.TestCase):
    def setUp(self):
        self.rules=r.load_regions()
        self.base=o.load_rules()

    def test_five_regions_in_order(self):
        self.assertEqual(list(self.rules['regions']),r.REGION_ORDER)

    def test_province_partition_complete_unique(self):
        names=[p for v in self.rules['regions'].values() for p in v['provinces']]
        self.assertEqual(len(names),34)
        self.assertEqual(len(set(names)),34)

    def test_province_lookup(self):
        for k,v in self.rules['regions'].items():
            for province in v['provinces']:
                self.assertEqual(r.resolve_region(self.rules,province=province),k)

    def test_full_province_names(self):
        for name,key in [('湖北省','center'),('北京市','north'),('广西壮族自治区','south'),
                         ('新疆维吾尔自治区','west'),('香港特别行政区','south')]:
            self.assertEqual(r.resolve_region(self.rules,province=name),key)

    def test_city_not_guessed(self):
        with self.assertRaises(o.OracleError):r.resolve_region(self.rules,province='武汉')

    def test_conflicting_selection_rejected(self):
        with self.assertRaises(o.OracleError):r.resolve_region(self.rules,'west','湖北')

    def test_region_aliases(self):
        self.assertEqual(r.resolve_region(self.rules,'北方'),'north')
        self.assertEqual(r.resolve_region(self.rules,'五方'),'all')

    def test_bad_region_rejected(self):
        with self.assertRaises(o.OracleError):r.resolve_region(self.rules,'东南')

    def test_ten_stems(self):
        for stem,elem in zip('甲乙丙丁戊己庚辛壬癸','木木火火土土金金水水'):
            self.assertEqual(r.hour_element(stem+'子',self.rules),elem)

    def test_missing_hour_not_defaulted(self):
        for bad in [None,'','甲','甲不存在','午子','甲甲']:
            with self.subTest(value=bad), self.assertRaises(o.OracleError):
                r.hour_element(bad,self.rules)

    def test_all_25_relations_defined(self):
        for a in '木火土金水':
            for b in '木火土金水':
                key,tier=r.relation(a,b,self.rules)
                self.assertIn(key,self.rules['relation_tiers'])
                self.assertIn(tier,[0,1,2])

    def test_known_relations(self):
        self.assertEqual(r.relation('水','木',self.rules),('hour_generates_region',2))
        self.assertEqual(r.relation('金','木',self.rules),('hour_controls_region',0))
        self.assertEqual(r.relation('木','火',self.rules),('hour_generates_region',2))
        self.assertEqual(r.relation('木','土',self.rules),('hour_controls_region',0))
        self.assertEqual(r.relation('木','木',self.rules),('same_element',2))

    def test_unknown_element_fails(self):
        with self.assertRaises(o.OracleError):r.relation('风','木',self.rules)

    def test_public_qualification_strict(self):
        items=[candidate(),candidate('11:00',good=False),candidate('13:00',bad=True),
               candidate('15:00',luck='凶')]
        out=r.regional_rank(base_result(items),self.rules)
        self.assertEqual(out['qualified_count'],1)
        self.assertEqual(len(out['regions']),5)

    def test_no_qualified_no_fabrication(self):
        out=r.regional_rank(base_result([candidate(good=False)]),self.rules)
        self.assertEqual(out['status'],'no_explicit_public_preference')
        self.assertTrue(all(not row['ranked_dates'] for row in out['regions']))
        self.assertIn('没有',r.public_report(out))

    def test_empty_range(self):
        self.assertEqual(r.regional_rank(base_result([]),self.rules)['status'],'no_feasible_window')

    def test_base_scores_not_changed(self):
        items=[candidate(),candidate('11:00','壬子',day_type='黑道日')]
        original=copy.deepcopy(items)
        out=r.regional_rank(base_result(items),self.rules)
        lookup={c['start']:c['score'] for c in items}
        for row in out['regions']:
            for d in row['ranked_dates']:
                for c in d['best_windows']:
                    self.assertEqual(c['score'],lookup[c['start']])
                    self.assertEqual(c['regional_points_added'],0)
        self.assertEqual(items,original)

    def test_base_score_beats_direction(self):
        # North: wood is secondary tier1 at score100; water tier2 at score85.
        out=r.regional_rank(base_result([candidate(),candidate('11:00','壬子',day_type='黑道日')]),self.rules,'north')
        best=out['regions'][0]['ranked_dates'][0]
        self.assertEqual(best['best_window_score'],100)
        self.assertEqual(best['best_windows'][0]['facts']['hour_ganzhi'],'甲子')

    def test_ties_retained(self):
        out=r.regional_rank(base_result([candidate(),candidate('11:00','壬子')]),self.rules,'east')
        self.assertEqual(len(out['regions'][0]['top_tied_windows']),2)

    def test_direction_can_change_tiebreak_without_score_change(self):
        out=r.regional_rank(base_result([candidate(),candidate('11:00','壬子')]),self.rules)
        rows={v['region']:v for v in out['regions']}
        self.assertEqual(rows['north']['top_tied_windows'][0]['facts']['hour_ganzhi'],'壬子')
        self.assertEqual(rows['south']['top_tied_windows'][0]['facts']['hour_ganzhi'],'甲子')
        self.assertEqual(rows['north']['top_tied_windows'][0]['score'],100)
        self.assertEqual(rows['south']['top_tied_windows'][0]['score'],100)

    def test_nationwide_does_not_apply_direction(self):
        out=r.regional_rank(base_result([candidate(),candidate('11:00','壬子')]),self.rules,'north')
        self.assertEqual(len(out['national_ranked_dates'][0]['best_windows']),2)
        self.assertEqual(len(out['regions'][0]['top_tied_windows']),1)

    def test_multiple_dates_tie_kept(self):
        out=r.regional_rank(base_result([candidate(day='2026-11-02'),candidate()]),self.rules,'east')
        self.assertEqual(out['regions'][0]['top_tied_dates'],['2026-11-01','2026-11-02'])

    def test_determinism(self):
        inp=base_result([candidate(),candidate('11:00','壬子')])
        self.assertEqual(r.regional_rank(inp,self.rules),r.regional_rank(inp,self.rules))

    def test_non_writing_event_rejected(self):
        inp=base_result([candidate()]);inp['event']='experiment'
        with self.assertRaises(o.OracleError):r.regional_rank(inp,self.rules)

    def test_window_all_days_9_to_21(self):
        ws=o.enumerate_windows(date(2026,11,1),date(2026,11,7),'Asia/Shanghai')
        self.assertEqual(len(ws),42)
        for w in ws:
            self.assertGreaterEqual(o.parse_aware(w['start']).hour,9)
            self.assertLessEqual(o.parse_aware(w['end']).hour,21)
            self.assertEqual(o.parse_aware(w['start']).utcoffset().total_seconds(),28800)

    def test_public_report_scope_and_score(self):
        text=r.public_report(r.regional_rank(base_result([candidate()]),self.rules),style="detailed")
        self.assertIn('北京时间',text)
        self.assertIn('不表示对所有人都吉',text)
        self.assertIn('100/100',text)
        self.assertIn('不作方位细分',text)

    def test_public_report_limit_validated(self):
        for top in [0,-1,94]:
            with self.assertRaises(o.OracleError):r.public_report({},top)

    def test_rule_changes_fail_closed(self):
        for key,value in [('calendar_timezone','Asia/Urumqi'),('default_days',14),
                          ('hour_element_source','random'),('qualification',{})]:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as td:
                x=copy.deepcopy(self.rules);x[key]=value
                p=Path(td)/'r.json';p.write_text(json.dumps(x))
                with self.assertRaises(o.OracleError):r.load_regions(p)

    def test_no_packaged_approval(self):
        self.assertFalse(r.APPROVAL_PATH.exists())
        self.assertFalse(o.APPROVAL_PATH.exists())

    def test_region_approval_requires_base(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(o.OracleError):
                r.approve_regions(self.rules,self.base,r.REGION_ACK,Path(td)/'a.json',Path(td)/'missing.json')

    def test_approval_wrong_ack_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(o.OracleError):
                r.approve_regions(self.rules,self.base,'请增加功能',Path(td)/'a.json')

    def test_approval_tampering_detected_in_isolated_fixture(self):
        with tempfile.TemporaryDirectory() as td,patch.object(r.o,'require_approval',return_value={'fixture':'test-only'}):
            p=Path(td)/'a.json'
            r.approve_regions(self.rules,self.base,r.REGION_ACK,p)
            self.assertEqual(r.require_approval(self.rules,self.base,p)['rule_id'],'regions-v1')
            rec=json.loads(p.read_text());rec['rule_digest']='tampered'
            p.write_text(json.dumps(rec))
            with self.assertRaises(o.OracleError):r.require_approval(self.rules,self.base,p)

    def test_only_local_and_standard_runtime_imports(self):
        tree=ast.parse((ROOT/'scripts/regional.py').read_text())
        imports=set()
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):imports.update(x.name.split('.')[0] for x in n.names)
            elif isinstance(n,ast.ImportFrom):imports.add((n.module or '').split('.')[0])
        self.assertTrue(imports.issubset({'__future__','argparse','hashlib','json','sys','datetime','pathlib','typing','oracle'}))

    def test_input_guide_has_no_birth_requirement(self):
        text=(ROOT/'references/inputs.md').read_text()
        self.assertIn('不是按生辰八字细化',text)
        self.assertIn('最早准备完成时间',text)
        self.assertIn('正式截止',text)


READY=all(v['ok'] for v in o.dependency_status().values())
@unittest.skipUnless(READY,'指定真实历法依赖缺失或版本不符；五方真实集成未运行')
class LiveRegions(unittest.TestCase):
    def test_five_region_seven_day_live(self):
        ws=o.enumerate_windows(date(2026,11,1),date(2026,11,7),'Asia/Shanghai')
        base=o.rank_windows(ws,o.LiveProvider(),o.load_rules(),'submission')
        result=r.regional_rank(base,r.load_regions())
        self.assertEqual(len(base['candidates']),42)
        self.assertEqual(len(result['regions']),5)
        for c in base['candidates']:
            self.assertEqual(c['facts']['calendar_crosscheck'],'cnlunar+lunar_python_passed')
        self.assertEqual(result,r.regional_rank(base,r.load_regions()))


if __name__=='__main__':unittest.main()
