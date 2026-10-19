import copy
import sys
import unittest
from datetime import date,datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import oracle as o
import regional as r


class BriefOutput(unittest.TestCase):
    def result(self):
        day=date(2026,10,25)
        result=o.rank_windows(o.enumerate_windows(day,day,'Asia/Shanghai'),o.LiveProvider(),o.load_rules(),'submission')
        result.update(timezone='Asia/Shanghai',request={'start':str(day),'end':str(day)})
        return result

    def test_brief_has_date_weekday_hour_time_and_direction(self):
        text=o.public_report(self.result())
        self.assertIn('公历2026年10月25日（周日）',text)
        self.assertIn('巳时（09:00—11:00）',text)
        self.assertIn('位置：',text)
        self.assertIn('时喜神方',text)
        self.assertNotIn('/100',text)

    def test_direction_is_from_library_not_reference_screenshot(self):
        facts=o.LiveProvider().facts(datetime(2026,10,22,12,tzinfo=o.CST))
        self.assertEqual(facts['hour_branch'],'午')
        self.assertEqual(facts['direction']['description'],'西北')
        self.assertEqual(facts['direction']['kind'],'hour_xishen')

    def test_brief_does_not_change_ranking_data(self):
        result=self.result();before=copy.deepcopy(result)
        o.public_report(result)
        self.assertEqual(result,before)
        self.assertIn('100/100',o.public_report(result,style='detailed'))

    def test_unverified_direction_not_fabricated(self):
        result=self.result()
        for c in result['ranked_dates'][0]['best_windows']:c['facts'].pop('direction')
        self.assertIn('未提供可核验的方位依据',o.public_report(result))

    def test_regional_default_is_same_brief_format(self):
        result=r.regional_rank(self.result(),r.load_regions())
        text=r.public_report(result)
        self.assertIn('公历2026年10月25日（周日）',text)
        self.assertIn('位置：',text)
        self.assertNotIn('/100',text)
        self.assertIn('100/100',r.public_report(result,style='detailed'))
