import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import oracle as o
import regional as r

class Defaults(unittest.TestCase):
    def test_both_policies_work_without_records(self):
        base=o.load_rules(); regions=r.load_regions()
        self.assertFalse(o.require_approval(base)['confirmation_required'])
        self.assertFalse(r.require_approval(regions,base)['confirmation_required'])
        self.assertEqual(o.require_approval(base)['mode'],'built_in_default')

    def test_doctors_ready_without_approval(self):
        for module in (o,r):
            with contextlib.redirect_stdout(io.StringIO()) as capture:
                self.assertEqual(module.main(['doctor']),0)
            state=json.loads(capture.getvalue())
            self.assertFalse(state['confirmation_required'])
            self.assertEqual(state['runtime_ready'],all(x['ok'] for x in o.dependency_status().values()))

    @unittest.skipUnless(all(x['ok'] for x in o.dependency_status().values()),'历法依赖不可用')
    def test_both_real_cli_entries_need_no_approval(self):
        for module,args in [(o,['rank','--timezone','Asia/Shanghai','--days','7']), (r,['public','--days','7'])]:
            with contextlib.redirect_stdout(io.StringIO()) as capture:
                self.assertEqual(module.main(args),0)
            self.assertIn('投稿',capture.getvalue())
