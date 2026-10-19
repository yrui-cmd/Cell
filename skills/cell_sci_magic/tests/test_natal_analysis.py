import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, date, timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import natal_analysis as n
import personal as p
import oracle as o


def profile(**kwargs):
    return {'calendar':'solar','birth_date':'2005-12-23','birth_time':'08:37',
            'birth_place':'测试地点','birth_timezone':'Asia/Shanghai','birth_longitude':120,
            'birth_time_uncertainty_minutes':0,'yun_gender':'male',**kwargs}


def full(row=None):
    row=row or profile()
    natal=p.resolve_birth(row)
    natal['analysis']=n.analyze(natal)
    natal['dayun']=n.build_yun(natal,row)
    return natal


class NatalAnalysis(unittest.TestCase):
    def test_strong_and_weak_are_not_same_fixed_yongshen(self):
        strong=n.analyze({'pillars':['甲寅','丙寅','甲寅','甲子']})
        weak=n.analyze({'pillars':['辛酉','甲午','甲戌','庚申']})
        self.assertEqual(strong['strength']['label'],'偏强')
        self.assertEqual(weak['strength']['label'],'偏弱')
        self.assertLess(strong['yongshen']['preferences']['水'],0)
        self.assertGreater(weak['yongshen']['preferences']['水'],0)

    def test_no_day_master_self_count(self):
        a=n.analyze({'pillars':['乙酉','戊子','辛巳','壬辰']})
        self.assertFalse(any(x['source']=='日干' for x in a['strength']['evidence']))
        self.assertTrue(any('stem' in x for x in a['strength']['evidence']))

    def test_root_and_month_evidence(self):
        a=n.analyze({'pillars':['甲寅','丙寅','甲寅','甲子']})
        self.assertTrue(a['strength']['roots'])
        self.assertEqual(a['strength']['season'],'木')
        self.assertEqual(a['pattern']['candidate'],'建禄格候选')

    def test_yang_blade_and_yin_not_assumed_blade(self):
        self.assertEqual(n.pattern(['甲子','丁卯','甲辰','丙寅'])['candidate'],'阳刃格候选')
        self.assertNotEqual(n.pattern(['乙丑','丙寅','乙卯','丁亥'])['candidate'],'阳刃格候选')

    def test_multiple_exposure_needs_review(self):
        a=n.analyze({'pillars':['甲子','丙寅','庚辰','戊午']})
        self.assertIn('mixed_month_exposure',[x['code'] for x in a['review_flags']])

    def test_formations_not_automatically_transformed(self):
        a=n.analyze({'pillars':['甲亥','丙卯','庚未','壬子']})
        self.assertIn('full_branch_formation',[x['code'] for x in a['review_flags']])
        self.assertEqual(a['status'],'review_required')

    def test_stem_combination_not_forced(self):
        a=n.analyze({'pillars':['甲子','己卯','庚辰','壬午']})
        self.assertIn('stem_combination',[x['code'] for x in a['review_flags']])

    def test_sensitivity_instability_abstains(self):
        natal={'pillars':['乙酉','戊子','辛巳','壬辰']}
        rules=n.load_rules();rules['weak_below']=n.strength(natal['pillars'])['support_ratio'];rules['strong_above']=0.8
        result=n.analyze(natal,rules=rules)
        self.assertIn('unstable_strength',[x['code'] for x in result['review_flags']])

    def test_missing_gender_and_direction_is_not_guessed(self):
        row=profile();del row['yun_gender']
        with self.assertRaises(o.OracleError):n.build_yun(p.resolve_birth(row),row)

    def test_forward_backward_with_year_polarity(self):
        for birth,yang in [('2004-06-15',True),('2005-06-15',False)]:
            male=full(profile(birth_date=birth,yun_gender='male'))
            female=full(profile(birth_date=birth,yun_gender='female'))
            self.assertEqual(male['dayun']['forward'],yang)
            self.assertEqual(female['dayun']['forward'],not yang)
            self.assertNotEqual(male['dayun']['cycles'][0]['ganzhi'],female['dayun']['cycles'][0]['ganzhi'])

    def test_explicit_direction_without_gender(self):
        row=profile(yun_direction='forward');del row['yun_gender']
        self.assertTrue(full(row)['dayun']['forward'])

    def test_conflicting_direction_rejected(self):
        with self.assertRaises(o.OracleError):full(profile(yun_gender='male',yun_direction='forward'))

    def test_official_yun_sect2_fixture(self):
        a=full(profile(birth_date='2022-03-09',birth_time='20:51',yun_gender='male'))
        self.assertEqual(a['dayun']['start_age']['years'],8)
        self.assertEqual(a['dayun']['start_age']['months'],9)
        self.assertEqual(a['dayun']['start_age']['days'],2)
        self.assertEqual(o.parse_aware(a['dayun']['start_utc']).astimezone(o.CST).date(),date(2030,12,12))

    def test_cycles_use_real_instants_half_open(self):
        yun=full()['dayun'];first,second=yun['cycles'][:2]
        edge=o.parse_aware(first['end_utc'])
        self.assertEqual(first['end_utc'],second['start_utc'])
        self.assertEqual(n.active_yun(yun,edge-timedelta(seconds=1))['ganzhi'],first['ganzhi'])
        self.assertEqual(n.active_yun(yun,edge)['ganzhi'],second['ganzhi'])

    def test_birth_uncertainty_propagated_to_yun(self):
        yun=full(profile(birth_time_uncertainty_minutes=1))['dayun']
        c=yun['cycles'][0]
        lo,hi=o.parse_aware(c['earliest_start_utc']),o.parse_aware(c['latest_start_utc'])
        self.assertGreater(hi,lo)
        self.assertEqual(n.active_yun(yun,lo+(hi-lo)/2)['status'],'uncertain_transition')

    def test_before_yun_not_fake_current_cycle(self):
        natal=full()
        self.assertEqual(n.active_yun(natal['dayun'],o.parse_aware(natal['birth_utc']))['status'],'before_start')

    def test_dayun_year_month_change_effective_qi(self):
        natal=full();t=datetime(2026,10,25,3,tzinfo=o.UTC)
        candidate=p.pillars(t,116.4)
        context=n.context_for(natal,candidate,t)
        self.assertEqual(context['dayun']['status'],'active')
        self.assertNotEqual(context['analysis']['strength']['element_qi'],natal['analysis']['strength']['element_qi'])
        self.assertEqual(len(context['context_evidence']),3)

    def test_different_dayun_changes_candidate_contribution_not_just_label(self):
        natal=full();t=datetime(2026,10,25,3,tzinfo=o.UTC);candidate=p.pillars(t,116.4)
        a=n.candidate_fit(natal,candidate,t)
        altered=copy.deepcopy(natal)
        for cycle in altered['dayun']['cycles']:
            if cycle['ganzhi']==a['context']['dayun']['ganzhi']:cycle['ganzhi']='戊戌'
        b=n.candidate_fit(altered,candidate,t)
        self.assertNotEqual(a['fit_scenarios'][1]['score'],b['fit_scenarios'][1]['score'])

    def test_real_ranking_does_not_require_all_charts_abstain(self):
        natal=full();rules=p.load_rules()
        ws=o.enumerate_windows(date(2026,11,1),date(2026,11,7),'Asia/Shanghai')
        base=o.rank_windows(p.refine_windows(ws,116.4,o.ensure_zone('Asia/Shanghai'),20,rules),o.LiveProvider(),o.load_rules(),'submission')
        r=p.rank_personal(base,natal,116.4,rules)
        self.assertTrue(r['ranked_personal_dates'])
        c=r['ranked_personal_dates'][0]['windows'][0]
        self.assertIn('fit_scenarios',c['analysis_fit'])
        self.assertEqual(len(c['analysis_fit']['fit_scenarios']),2)
        self.assertFalse(c['analysis_fit']['review_flags'])
        self.assertTrue(all(x['points']==0 for x in c['personal_reasons'] if x['relation']=='日主十神'))

    def test_special_chart_never_returns_definite_recommendation(self):
        natal=full()
        natal['analysis']['review_flags']=[{'code':'test_special','reason':'合成存疑测试'}]
        t=datetime(2026,11,1,3,tzinfo=o.UTC)
        fit=n.candidate_fit(natal,p.pillars(t,116.4),t)
        self.assertFalse(fit['auto_eligible'])

    def test_v1_rank_fallback_removed(self):
        with self.assertRaises(o.OracleError):p.rank_personal({},p.resolve_birth(profile()),116.4,p.load_rules())

    def test_full_cli_report_and_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'profile.json';path.write_text(json.dumps(profile()),encoding='utf-8')
            audit=Path(tmp)/'audit.json'
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(p.main(['rank','--profile',str(path),'--timezone','Asia/Shanghai','--longitude','116.4','--days','7','--audit',str(audit)]),0)
            result=json.loads(audit.read_text(encoding='utf-8'))
            self.assertIn('analysis',result['natal']);self.assertIn('dayun',result['natal'])
            self.assertIn('旺衰',output.getvalue());self.assertIn('大运',output.getvalue())
            self.assertEqual(result['analysis_rule_id'],'natal-analysis-v2')


if __name__=='__main__':unittest.main()
