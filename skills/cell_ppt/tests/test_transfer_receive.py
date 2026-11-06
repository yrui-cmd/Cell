"""Offline single-PDF result delivery and legacy-order compatibility."""
import hashlib
from io import BytesIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

from pptx import Presentation

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import transfer


def result_bytes(pages):
    deck = Presentation()
    for index in range(pages):
        deck.slides.add_slide(deck.slide_layouts[6])
    out = BytesIO()
    deck.save(out)
    return out.getvalue()


class ReceiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = result_bytes(2)
        self.bundle = {'sha256': {'material': 'a' * 64}, 'credits': 3,
                       'plan_pages': 3, 'template_pages': 0}
        self.order = {'job_id': 'b' * 32}
        self.reply = {
            **self.order, 'mode': 'planned_deck', 'page_count': 3,
            'price': {'amount': 3, 'unit': 'ppt_page_credit'},
            'files': {'material': {'sha256': 'a' * 64}},
            'status': 'completed', 'billing': 'settled',
            'result': {'page_count': 2, 'bytes': len(self.payload),
                       'sha256': hashlib.sha256(self.payload).hexdigest()},
        }
        self.session = MagicMock()
        response = self.session.get.return_value.__enter__.return_value
        response.status_code = 200
        response.iter_content.return_value = [self.payload]
        self.client = transfer.Client(self.session, 'synthetic-token')

    def receive(self):
        return self.client.receive(self.root, self.order, self.reply, self.bundle)

    def test_single_pdf_can_deliver_fewer_pages_and_reuse_verified_result(self):
        destination = self.receive()
        self.assertEqual(destination, self.root / '交付' / '成品.pptx')
        self.assertEqual(destination.read_bytes(), self.payload)
        self.assertEqual(self.receive(), destination)
        self.session.get.assert_called_once()

    def test_result_page_count_must_match_downloaded_pptx(self):
        self.reply['result']['page_count'] = 1
        with self.assertRaisesRegex(ValueError, '摘要或页数'):
            self.receive()
        self.assertFalse((self.root / '交付' / '成品.pptx').exists())

    def test_invalid_reported_page_count_rejected_before_download(self):
        for pages in (0, -1, True, '2', 501):
            with self.subTest(pages=pages):
                self.reply['result']['page_count'] = pages
                with self.assertRaises(ValueError):
                    self.receive()
        self.session.get.assert_not_called()

    def test_tampered_payload_rejected(self):
        self.reply['result']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, '摘要或页数'):
            self.receive()
        self.assertFalse((self.root / '交付' / '成品.pptx').exists())

    def test_legacy_order_keeps_planned_page_count_rule(self):
        self.bundle['sha256']['pptx'] = 'c' * 64
        self.reply['files']['pptx'] = {'sha256': 'c' * 64, 'page_count': 3}
        with self.assertRaisesRegex(ValueError, '页数或文件信息'):
            self.receive()
        self.session.get.assert_not_called()
        self.bundle['plan_pages'] = 2
        self.reply['files']['pptx']['page_count'] = 2
        self.assertEqual(self.receive().read_bytes(), self.payload)

    def test_existing_old_filename_migrated_without_new_download(self):
        legacy = self.root / '交付' / '成品ppt.pptx'
        legacy.parent.mkdir()
        legacy.write_bytes(self.payload)
        destination = self.receive()
        self.assertEqual(destination.name, '成品.pptx')
        self.assertEqual(destination.read_bytes(), self.payload)
        self.assertEqual(legacy.read_bytes(), self.payload)
        self.session.get.assert_not_called()


if __name__ == '__main__':
    unittest.main()
