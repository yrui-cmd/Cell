"""Queue-to-production timing, persistence, and transient status failures."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import job_progress as progress
import progress_panel as panel


class QueueProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.order = dict(job_id='a'*32, credits=5, status='queued', queued_at_unix=1)

    def reply(self, status, queue=None):
        return dict(job_id=self.order['job_id'], status=status, queue=queue,
                    mode='planned_deck', page_count=5)

    def test_waiting_does_not_spend_estimate_and_reopen_keeps_start(self):
        queue = dict(position=3, ahead=2, waiting=5, processing=8, as_of_unix=10000)
        waiting = progress.observe(self.root, self.order, self.reply('queued', queue), now=10000)
        view = panel.snapshot(self.order, waiting, now=10010)
        self.assertEqual(view['estimate_seconds'], 4500)
        self.assertEqual(view['elapsed_seconds'], 0)
        self.assertIsNone(view['remaining_seconds'])
        self.assertFalse(view['overdue'])
        self.assertEqual(view['queue'], queue)
        self.assertIn('当前排第 3 位', view['queue_text'])
        progress.observe(self.root, self.order, self.reply('processing', queue), now=10100)
        # Subsequent polling and reopening must never reset the first start time.
        progress.observe(self.root, self.order, self.reply('processing'), now=10200)
        loaded = progress.load(self.root, self.order)
        view = panel.snapshot(self.order, loaded, now=10200)
        self.assertEqual(view['elapsed_seconds'], 100)
        self.assertEqual(view['remaining_seconds'], 4400)
        self.assertEqual(view['label'], '制作中')
        with panel.make_server(self.order, 'test', self.root) as server:
            self.assertEqual(server.remote['processing_started_at_unix'], 10100)

    def test_processing_and_terminal_clear_queue_and_freeze_clock(self):
        started = progress.observe(self.root, self.order, self.reply('processing',
                    dict(position=3, ahead=2, waiting=4, processing=2)), now=100)
        self.assertIsNone(started['queue']['position'])
        self.assertIsNone(started['queue']['ahead'])
        self.assertNotIn('排第', panel.snapshot(self.order, started, now=110)['queue_text'])
        self.assertTrue(panel.snapshot(self.order, started, now=5000)['overdue'])
        for status in ('completed', 'failed', 'cancelled', 'expired'):
            ended = progress.observe(self.root, self.order, self.reply(status, dict(position=1)), now=200)
            view = panel.snapshot(self.order, ended, now=9000)
            self.assertIsNone(view['queue'])
            self.assertIsNone(view['remaining_seconds'])
            self.assertEqual(view['elapsed_seconds'], 100)
            self.assertFalse(view['overdue'])
            self.assertTrue(view['terminal'])
        later = progress.observe(self.root, self.order, self.reply('expired'), now=10000)
        self.assertEqual(later['finished_at_unix'], 200)

    def test_missing_queue_never_invents_rank_or_start(self):
        waiting = progress.observe(self.root, self.order, self.reply('queued'), now=100)
        self.assertIn('等待排位信息', panel.snapshot(self.order, waiting, now=100)['queue_text'])
        completed = progress.observe(self.root, self.order, self.reply('completed'), now=200)
        self.assertNotIn('processing_started_at_unix', completed)
        self.assertEqual(panel.snapshot(self.order, completed, now=300)['percent'], 100)
        with self.assertRaises(ValueError):
            progress.observe(self.root, self.order, dict(job_id='b'*32, status='processing'))
        self.assertEqual(progress.load(self.root, self.order), completed)

    def test_refresh_failure_is_visible_and_recovers_after_five_seconds(self):
        server = SimpleNamespace(remote=None)
        client = Mock()
        client.call.side_effect = [self.reply('queued', dict(position=2, ahead=1)),
                                  ValueError('temporary HTTP failure'), self.reply('failed')]
        observed = []
        def sleep(seconds):
            self.assertEqual(seconds, 5)
            observed.append(panel.snapshot(self.order, dict(server.remote)))
        with patch.object(panel, 'Client', return_value=client), patch.object(panel.time, 'sleep', side_effect=sleep):
            panel.refresh(server, self.root, self.order, 'dummy')
        self.assertFalse(observed[0]['updating'])
        self.assertTrue(observed[1]['updating'])
        self.assertEqual(observed[1]['queue']['position'], 2)
        self.assertFalse(panel.snapshot(self.order, server.remote)['updating'])
        self.assertEqual(client.call.call_count, 3)


if __name__ == '__main__':
    unittest.main()
