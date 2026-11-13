import json
from pathlib import Path
import sys
import tempfile
import unittest
from hashlib import sha256
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from replay import resolve_source


class LocalReplayTests(unittest.TestCase):
    def test_original_receipt_and_chinese_path_checked_offline(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ppt = root / '成品.pptx'
            ppt.write_bytes(b'saved-source')
            order = {'job_id': 'original', 'thread_id': 'chat', 'billing': 'settled'}
            receipt = dict(order, path=str(ppt), sha256=sha256(ppt.read_bytes()).hexdigest())
            for name, obj in [('order.json', order), ('return-ready.json', receipt)]:
                (root / name).write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')
            self.assertEqual(resolve_source(None, root, 'chat')[0], ppt)
            with self.assertRaises(ValueError):
                resolve_source(None, root, 'another-chat')
            ppt.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                resolve_source(None, root, 'chat')
