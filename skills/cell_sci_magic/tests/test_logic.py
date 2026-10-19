"""Pure logic tests use deliberately synthetic almanac facts, not real rankings."""
import copy
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import oracle as o


def fake_facts(good=None, bad=None, day_type='黄道日', hour_luck='吉'):
    return {'good_activities': ['上表章'] if good is None else good,
            'bad_activities': [] if bad is None else bad,
            'day_type': day_type, 'hour_luck': hour_luck,
            'day_officer': '开', 'hour_deity': '玉堂',
            'fixture_type': 'synthetic_logic_only_not_a_computed_chart'}


class FakeProvider:
    def facts(self, instant):
        return fake_facts()


class Logic(unittest.TestCase):
    def setUp(self):
        self.rules = o.load_rules()
        self.event = self.rules['events']['submission']

    def test_calendar_convention_edits_fail_closed(self):
        for key in ['calendar_timezone', 'day_boundary', 'god_type', 'year_boundary', 'hour_source']:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as td:
                changed=copy.deepcopy(self.rules); changed[key]='unverified_change'
                path=Path(td)/'rules.json'
                path.write_text(json.dumps(changed),encoding='utf-8')
                with self.assertRaises(o.OracleError): o.load_rules(path)

    def test_proposal_not_approved_by_default(self):
        self.assertEqual(self.rules['status'], 'enabled_by_default')

    def test_score_favorable(self):
        r = o.score_facts(fake_facts(), self.event, self.rules)
        self.assertEqual(r['score'], 100)
        self.assertTrue(r['eligible'])
        self.assertEqual(sum(x['points'] for x in r['breakdown']), 100)

    def test_neutral_not_favorable(self):
        r = o.score_facts(fake_facts(good=[]), self.event, self.rules)
        self.assertEqual(r['score'], 70)
        self.assertEqual(r['event_fit'], 'neutral')

    def test_unfavorable_not_promoted_by_good_hour(self):
        r = o.score_facts(fake_facts(good=[], bad=['上表章']), self.event, self.rules)
        self.assertFalse(r['eligible'])
        self.assertEqual(r['score'], 40)

    def test_conflicting_yi_ji_is_not_favorable(self):
        self.assertFalse(o.score_facts(fake_facts(bad=['上表章']), self.event, self.rules)['eligible'])

    def test_global_unfavorable(self):
        self.assertFalse(o.score_facts(fake_facts(bad=['诸事不宜']), self.event, self.rules)['eligible'])

    def test_generic_experiment_does_not_borrow_submission_proxy(self):
        r = o.score_facts(fake_facts(), self.rules['events']['experiment'], self.rules)
        self.assertEqual(r['event_fit'], 'neutral')
        self.assertEqual(r['breakdown'][0]['points'], 30)

    def test_market_not_submission(self):
        r = o.score_facts(fake_facts(good=['开市']), self.event, self.rules)
        self.assertEqual(r['event_fit'], 'neutral')

    def test_no_hour_fallback(self):
        with self.assertRaises(o.OracleError):
            o.score_facts(fake_facts(hour_luck='不详'), self.event, self.rules)

    def test_no_day_fallback(self):
        with self.assertRaises(o.OracleError):
            o.score_facts(fake_facts(day_type='不详'), self.event, self.rules)

    def test_all_score_combinations_are_bounded(self):
        for good, bad in [([], []), (['上表章'], []), ([], ['上表章'])]:
            for d in ['黄道日', '黑道日']:
                for h in ['吉', '凶']:
                    v = o.score_facts(fake_facts(good, bad, d, h), self.event, self.rules)['score']
                    self.assertGreaterEqual(v, 0); self.assertLessEqual(v, 100)

    def test_submission_and_revision_do_not_fake_different_scores(self):
        a = o.score_facts(fake_facts(), self.rules['events']['submission'], self.rules)
        b = o.score_facts(fake_facts(), self.rules['events']['revision'], self.rules)
        self.assertEqual(a, b)

    def test_six_beijing_windows(self):
        d = date(2026, 11, 2)
        ws = o.enumerate_windows(d, d, 'Asia/Shanghai')
        self.assertEqual(len(ws), 6)
        self.assertEqual([o.parse_aware(w['start']).hour for w in ws], [9,11,13,15,17,19])
        self.assertEqual(o.parse_aware(ws[-1]['end']).hour, 21)
        self.assertTrue(all(w['duration_minutes'] == 120 for w in ws))

    def test_ready_at_clips_not_divination_precision(self):
        d = date(2026,11,2)
        ws = o.enumerate_windows(d,d,'Asia/Shanghai',not_before=o.parse_aware('2026-11-02T10:30:00+08:00'))
        self.assertEqual(o.parse_aware(ws[0]['start']).strftime('%H:%M'), '10:30')
        self.assertEqual(ws[0]['duration_minutes'], 30)
        self.assertIn('clipped', ws[0]['granularity'])

    def test_ready_after_21_has_no_windows(self):
        d = date(2026,11,2)
        self.assertEqual(o.enumerate_windows(d,d,'Asia/Shanghai',
            not_before=o.parse_aware('2026-11-02T21:00:00+08:00')), [])

    def test_deadline_buffer(self):
        d = date(2026,11,2)
        ws = o.enumerate_windows(d,d,'Asia/Shanghai', deadline=o.parse_aware('2026-11-02T16:00:00+08:00'))
        self.assertEqual(o.parse_aware(ws[-1]['end']).strftime('%H:%M'), '15:30')

    def test_deadline_before_working_day(self):
        d = date(2026,11,2)
        ws = o.enumerate_windows(d,d,'Asia/Shanghai', deadline=o.parse_aware('2026-11-02T09:00:00+08:00'))
        self.assertEqual(ws, [])

    def test_excluded_day(self):
        a = date(2026,11,2); b = a + timedelta(days=1)
        ws = o.enumerate_windows(a,b,'Asia/Shanghai', excluded_dates={a})
        self.assertEqual(len(ws), 6)
        self.assertEqual({w['local_date'] for w in ws}, {str(b)})

    def test_block_splits(self):
        d = date(2026,11,2)
        block = [(o.parse_aware('2026-11-02T09:45:00+08:00'), o.parse_aware('2026-11-02T10:15:00+08:00'))]
        ws = o.enumerate_windows(d,d,'Asia/Shanghai',blocked=block)
        self.assertEqual(len(ws), 7)
        self.assertEqual(ws[0]['duration_minutes'], 45)
        self.assertEqual(ws[1]['duration_minutes'], 45)

    def test_overlapping_blocks(self):
        start = o.parse_aware('2026-11-02T09:00:00+08:00').astimezone(o.UTC)
        end = start + timedelta(hours=4)
        out = o.subtract_blocked(start,end,[(start+timedelta(hours=1),start+timedelta(hours=2)),
                                          (start+timedelta(hours=1,minutes=30),end)])
        self.assertEqual(out, [(start,start+timedelta(hours=1))])

    def test_invalid_block_rejected(self):
        a = datetime(2026,1,1,tzinfo=o.UTC)
        with self.assertRaises(o.OracleError):
            o.subtract_blocked(a,a+timedelta(hours=3),[(a,a)])

    def test_short_window_excluded(self):
        d = date(2026,11,2)
        ws=o.enumerate_windows(d,d,'Asia/Shanghai',not_before=o.parse_aware('2026-11-02T20:50:00+08:00'))
        self.assertEqual(ws, [])

    def test_reverse_range(self):
        with self.assertRaises(o.OracleError):
            o.enumerate_windows(date(2026,11,3),date(2026,11,2),'Asia/Shanghai')

    def test_range_limit(self):
        with self.assertRaises(o.OracleError):
            o.enumerate_windows(date(2026,1,1),date(2027,1,1),'Asia/Shanghai')

    def test_invalid_timezone(self):
        with self.assertRaises(o.OracleError): o.ensure_zone('No/SuchPlace')

    def test_naive_time_is_rejected(self):
        with self.assertRaises(o.OracleError): o.parse_aware('2026-11-02T09:00:00')

    def test_berlin_local_window_and_dst(self):
        for d in [date(2026,7,1),date(2026,11,2)]:
            ws=o.enumerate_windows(d,d,'Europe/Berlin')
            self.assertEqual(o.parse_aware(ws[0]['start']).hour, 9)
            self.assertEqual(o.parse_aware(ws[-1]['end']).hour, 21)
            self.assertAlmostEqual(sum(w['duration_minutes'] for w in ws),720)
        a=o.enumerate_windows(date(2026,7,1),date(2026,7,1),'Europe/Berlin')
        b=o.enumerate_windows(date(2026,11,2),date(2026,11,2),'Europe/Berlin')
        self.assertNotEqual(o.parse_aware(a[0]['start']).utcoffset(),o.parse_aware(b[0]['start']).utcoffset())

    def test_half_hour_timezone_converts_without_guess(self):
        d=date(2026,11,2)
        ws=o.enumerate_windows(d,d,'Asia/Kolkata')
        self.assertEqual(o.parse_aware(ws[0]['start']).hour,9)
        self.assertEqual(o.parse_aware(ws[-1]['end']).hour,21)
        self.assertTrue(any(o.parse_aware(w['start']).minute==30 for w in ws))

    def test_ties_kept_not_randomized(self):
        d=date(2026,11,2)
        ws=o.enumerate_windows(d,d,'Asia/Shanghai')
        r=o.rank_windows(ws,FakeProvider(),self.rules,'submission')
        self.assertEqual(len(r['top_tied_windows']),6)
        self.assertEqual(len(r['ranked_dates'][0]['best_windows']),6)

    def test_repeatability(self):
        d=date(2026,11,2)
        ws=o.enumerate_windows(d,d+timedelta(days=2),'Asia/Shanghai')
        a=o.rank_windows(ws,FakeProvider(),self.rules,'submission')
        b=o.rank_windows(ws,FakeProvider(),self.rules,'submission')
        self.assertEqual(a,b)
        self.assertEqual(len(a['ranked_dates']),3)

    def test_no_feasible_no_fabricated_date(self):
        r=o.rank_windows([],FakeProvider(),self.rules,'submission')
        self.assertEqual(r['status'],'no_feasible_window')
        self.assertEqual(r['ranked_dates'],[])

    def test_unfavorable_all_no_fake_recommendations(self):
        class BadProvider:
            def facts(self, instant): return fake_facts(good=[],bad=['上表章'])
        d=date(2026,11,2)
        r=o.rank_windows(o.enumerate_windows(d,d,'Asia/Shanghai'),BadProvider(),self.rules,'submission')
        self.assertEqual(r['status'],'no_almanac_preferred_window_keep_real_deadline')
        self.assertEqual(r['ranked_dates'],[])
        self.assertEqual(len(r['candidates']),6)

    def test_unsupported_event_rejected(self):
        with self.assertRaises(o.OracleError): o.rank_windows([],FakeProvider(),self.rules,'winning_lottery')

    def test_chinese_score_reading(self):
        for n,s in [(0,'零'),(10,'十'),(15,'十五'),(85,'八十五'),(100,'一百')]:
            self.assertEqual(o.chinese_number(n),s)

    def test_approval_gate_and_record(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'approval.json'
            with self.assertRaises(o.OracleError): o.require_approval(self.rules,p)
            with self.assertRaises(o.OracleError): o.approve_rules(self.rules,'替用户同意',p)
            o.approve_rules(self.rules,o.RULE_ACK,p)
            self.assertEqual(o.require_approval(self.rules,p)['rule_id'],'submission-v1')

    def test_changed_rule_invalidates_approval(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'approval.json'
            o.approve_rules(self.rules,o.RULE_ACK,p)
            changed=copy.deepcopy(self.rules); changed['events']['submission']['proxy']='开市'
            with self.assertRaises(o.OracleError): o.require_approval(changed,p)

    def test_fake_engine_digest_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'approval.json'
            rec=o.approve_rules(self.rules,o.RULE_ACK,p); rec['engine_digest']='fake'
            p.write_text(json.dumps(rec),encoding='utf-8')
            with self.assertRaises(o.OracleError): o.require_approval(self.rules,p)

    def test_public_report_not_qimen(self):
        d=date(2026,11,2)
        r=o.rank_windows(o.enumerate_windows(d,d,'Asia/Shanghai'),FakeProvider(),self.rules,'submission')
        r['timezone']='Asia/Shanghai'
        s=o.public_report(r,style="detailed")
        self.assertIn('100/100',s); self.assertIn('并列',s)
        self.assertNotIn('杜门',s); self.assertNotIn('保证录用',s)

    def test_rule_file_has_no_actual_approval(self):
        self.assertFalse(o.APPROVAL_PATH.exists())

if __name__=='__main__': unittest.main()
