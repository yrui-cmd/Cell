import contextlib
import io
import json
import tempfile
import unittest
import sys
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import oracle as o
import regional as r


class Clock(datetime):
    @classmethod
    def now(cls,tz=None):
        return cls(2026,12,31,16,30,tzinfo=timezone.utc).astimezone(tz)


class TomorrowDefault(unittest.TestCase):
    def test_both_generic_entries_only_local_tomorrow_across_year(self):
        with tempfile.TemporaryDirectory() as tmp:
            for module,args in [(o,['rank','--timezone','Asia/Shanghai']),(r,['public'])]:
                audit=Path(tmp)/'report.json'
                with patch.object(module,'datetime',Clock),contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(module.main(args+['--audit',str(audit)]),0)
                request=json.loads(audit.read_text(encoding='utf-8'))['request']
                self.assertEqual(request['start'],'2027-01-02')
                self.assertEqual(request['end'],'2027-01-02')

    def test_explicit_range_still_honored(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit=Path(tmp)/'report.json'
            with patch.object(o,'datetime',Clock),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(o.main(['rank','--timezone','Asia/Shanghai','--start','2027-01-03','--end','2027-01-05','--audit',str(audit)]),0)
            request=json.loads(audit.read_text(encoding='utf-8'))['request']
            self.assertEqual((request['start'],request['end']),('2027-01-03','2027-01-05'))
