"""Real library integration. Skips are not passes; install pins before claiming success."""
import sys
import unittest
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import oracle as o

READY=all(v['ok'] for v in o.dependency_status().values())

@unittest.skipUnless(READY,'真实历法依赖未安装或版本不符；未执行真实日期集成，不能视为通过')
class Live(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.provider=o.LiveProvider()

    def test_known_lunar_new_year_and_crosscheck(self):
        f=self.provider.facts(o.parse_aware('2024-02-10T10:00:00+08:00'))
        self.assertEqual(f['lunar_date'],{'year':2024,'month':1,'day':1})
        self.assertEqual(f['calendar_crosscheck'],'cnlunar+lunar_python_passed')

    def test_full_day_boundaries(self):
        a=self.provider.facts(o.parse_aware('2026-11-02T22:59:00+08:00'))
        b=self.provider.facts(o.parse_aware('2026-11-02T23:00:00+08:00'))
        c=self.provider.facts(o.parse_aware('2026-11-03T00:00:00+08:00'))
        self.assertNotEqual(a['day_ganzhi'],b['day_ganzhi'])
        self.assertEqual(b['day_ganzhi'],c['day_ganzhi'])
        self.assertEqual(b['hour_ganzhi'],c['hour_ganzhi'])

    def test_fourteen_day_full_run_repeatable(self):
        rules=o.load_rules()
        ws=o.enumerate_windows(date(2026,11,1),date(2026,11,14),'Asia/Shanghai')
        a=o.rank_windows(ws,self.provider,rules,'submission')
        b=o.rank_windows(ws,self.provider,rules,'submission')
        self.assertEqual(a,b)
        self.assertEqual(a['candidate_count'],84)
        self.assertTrue(all(0<=c['score']<=100 for c in a['candidates']))

if __name__=='__main__': unittest.main()
