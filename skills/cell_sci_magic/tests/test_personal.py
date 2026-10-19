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
import oracle as o
import personal as p


def profile(**kwargs):
    return {'calendar':'solar','birth_date':'2005-12-23','birth_time':'08:37',
            'birth_place':'测试地点','birth_timezone':'Asia/Shanghai','birth_longitude':120,'yun_gender':'male',**kwargs}


class Personal(unittest.TestCase):
    def test_official_library_fixture(self):
        chart=p.resolve_birth(profile())
        self.assertEqual(chart['pillars'],['乙酉','戊子','辛巳','壬辰'])
        self.assertEqual(chart['day_master'],'辛')
        self.assertEqual(len(chart['details']),4)
        self.assertTrue(all(x['hidden_stems'] for x in chart['details']))

    def test_missing_fields_never_fall_back(self):
        for field in ['birth_time','birth_place','birth_date','birth_longitude','calendar','birth_timezone']:
            row=profile();del row[field]
            with self.subTest(field=field),self.assertRaises(o.OracleError):p.resolve_birth(row)

    def test_birth_future_rejected(self):
        with self.assertRaises(o.OracleError):p.resolve_birth(profile(birth_date='2099-01-01'))

    def test_birth_lunar_solar_equivalence(self):
        l=p.Lunar.fromYmd(2005,11,23).getSolar()
        solar=f'{l.getYear():04d}-{l.getMonth():02d}-{l.getDay():02d}'
        self.assertEqual(p.resolve_birth(profile(birth_date=solar))['pillars'],
                         p.resolve_birth(profile(calendar='lunar',birth_date='2005-11-23',leap_month=False))['pillars'])

    def test_lunar_needs_leap_flag(self):
        with self.assertRaises(o.OracleError):p.resolve_birth(profile(calendar='lunar'))

    def test_unsupported_leap_month_rejected(self):
        with self.assertRaises(o.OracleError):
            p.resolve_birth(profile(calendar='lunar',birth_date='2005-11-23',leap_month=True))

    def test_dst_nonexistent(self):
        with self.assertRaises(o.OracleError):p.resolve_birth(profile(birth_date='2005-03-27',birth_time='02:30',birth_timezone='Europe/Berlin',birth_longitude=13.4))

    def test_dst_ambiguous_requires_offset(self):
        row=profile(birth_date='2005-10-30',birth_time='02:30',birth_timezone='Europe/Berlin',birth_longitude=13.4)
        with self.assertRaises(o.OracleError):p.resolve_birth(row)
        a=p.resolve_birth({**row,'birth_utc_offset':'+02:00'})
        b=p.resolve_birth({**row,'birth_utc_offset':'+01:00'})
        self.assertNotEqual(a['birth_utc'],b['birth_utc'])

    def test_longitude_changes_hour(self):
        a=p.resolve_birth(profile())
        b=p.resolve_birth(profile(birth_longitude=90))
        self.assertNotEqual(a['pillars'][3],b['pillars'][3])

    def test_time_uncertainty_crosses_pillars(self):
        with self.assertRaises(o.OracleError):p.resolve_birth(profile(birth_time_uncertainty_minutes=120))

    def test_23_rollover(self):
        a=datetime(2005,12,23,14,30,tzinfo=o.UTC)
        b=a+timedelta(hours=1)
        self.assertNotEqual(p.pillars(a,120)[2],p.pillars(b,120)[2])

    def test_actual_lichun_boundary(self):
        term=p.Solar.fromYmd(2005,2,4).getLunar().getJieQiTable()['立春']
        instant=datetime.fromisoformat(term.toYmdHms()).replace(tzinfo=o.CST)
        for lon in [90,120,-74]:
            a=p.pillars(instant-timedelta(seconds=1),lon)
            b=p.pillars(instant+timedelta(seconds=1),lon)
            self.assertNotEqual(a[0],b[0]);self.assertNotEqual(a[1],b[1])

    def test_different_natal_charts_change_scores(self):
        rules=p.load_rules()
        a=p.resolve_birth(profile())
        b=p.resolve_birth(profile(birth_date='1995-06-15',birth_time='14:30'))
        changed=0
        for day in range(1,15):
            c=p.pillars(datetime(2026,11,day,3,tzinfo=o.UTC),120)
            x=p.personal_score(a,c,rules);y=p.personal_score(b,c,rules)
            changed+=x['personal_score']!=y['personal_score'] or x['personal_eligible']!=y['personal_eligible']
        self.assertGreater(changed,0)

    def test_day_clash_excluded_not_promoted_by_almanac(self):
        natal={'pillars':['甲子','丙寅','戊辰','壬戌'],'day_master':'戊'}
        result=p.personal_score(natal,['丙午','戊戌','甲戌','丁卯'],p.load_rules())
        self.assertTrue(result['natal_day_clash']);self.assertFalse(result['personal_eligible'])

    def test_refined_windows_stable_and_within_constraints(self):
        windows=o.enumerate_windows(date(2026,11,1),date(2026,11,2),'Asia/Shanghai')
        refined=p.refine_windows(windows,116.4,o.ensure_zone('Asia/Shanghai'),20,p.load_rules())
        self.assertTrue(refined)
        for w in refined:
            a,b=o.parse_aware(w['start']),o.parse_aware(w['end'])
            self.assertGreaterEqual(a.hour,9);self.assertLessEqual(b.hour,21)
            self.assertGreaterEqual((b-a).total_seconds(),1200)
            self.assertEqual(p.pillars(a,116.4),p.pillars(b-timedelta(seconds=1),116.4))

    def test_both_end_to_end_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'birth.json';path.write_text(json.dumps(profile()),encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(p.main(['chart','--profile',str(path)]),0)
            self.assertEqual(json.loads(output.getvalue())['day_master'],'辛')
            audit=Path(tmp)/'audit.json'
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(p.main(['rank','--profile',str(path),'--timezone','Asia/Shanghai','--longitude','116.4','--days','7','--audit',str(audit)]),0)
            r=json.loads(audit.read_text(encoding='utf-8'))
            self.assertEqual(r['mode'],'personal_bazi')
            self.assertTrue(all('personal_reasons' in c for c in r['candidates']))
            self.assertNotIn('ranked_dates',r)
            self.assertNotIn('top_tied_windows',r)

    def test_invalid_lunar_cli_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'birth.json'
            path.write_text(json.dumps(profile(calendar='lunar',leap_month=True)),encoding='utf-8')
            with contextlib.redirect_stderr(io.StringIO()) as error:
                self.assertEqual(p.main(['chart','--profile',str(path)]),2)
            self.assertIn('未生成个人推荐',error.getvalue())

    def test_solar_equation_known_sign_and_longitude(self):
        instant=datetime(2026,11,3,12,tzinfo=o.UTC)
        self.assertTrue(15<p.equation_of_time(instant)<18)
        diff=p.solar_clock(instant,120)-p.solar_clock(instant,90)
        self.assertEqual(diff,timedelta(hours=2))

    def test_profile_file_missing_no_fallback(self):
        with contextlib.redirect_stderr(io.StringIO()):self.assertEqual(p.main(['rank','--profile','__missing__.json']),2)
