"""Original-chat binding, recording question, and completion evidence."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import return_watch as w
import progress_panel as panel


class ReturnWatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.order = {'job_id': 'a'*32, 'thread_id': 'original', 'billing': 'settled', 'credits': 2}
        w.write(self.root/'order.json', self.order)
        self.client = Mock()

    def test_prepare_is_not_registration_and_reuses_real_id(self):
        result = w.prepare(self.root, 'original')
        self.assertFalse(result['registered'])
        self.assertEqual(result['automation_request']['targetThreadId'], 'original')
        w.bind(self.root, 'original', 'actual-id')
        self.assertEqual(w.prepare(self.root, 'original')['existing_automation_id'], 'actual-id')
        with self.assertRaises(ValueError): w.bind(self.root, 'original', 'duplicate')
        with self.assertRaises(ValueError): w.check_return(self.client, self.root, 'wrong')
        self.client.call.assert_not_called()

    def test_question_and_recording_start_gate_output(self):
        w.prepare(self.root, 'original')
        with self.assertRaisesRegex(ValueError, '询问'): w.require_output_choice(self.root, 'original')
        with self.assertRaises(ValueError): w.choose(self.root, 'original', 'no', '')
        w.choose(self.root, 'original', 'yes', 'user selected recording')
        with self.assertRaisesRegex(ValueError, '先启动'): w.require_output_choice(self.root, 'original')
        w.recording_ready(self.root, 'original', str(self.root/'capture.mp4'), 'synthetic test evidence')
        w.require_output_choice(self.root, 'original')
        w.choose(self.root, 'original', 'no', 'user selected no recording')
        w.require_output_choice(self.root, 'original')
        self.assertNotIn('recording', w.read(self.root/w.WATCH))

    def test_ready_returns_question_not_playback(self):
        w.prepare(self.root, 'original')
        self.client.call.return_value = {'job_id': self.order['job_id'], 'status': 'completed'}
        with patch.object(w, 'receive_ready', return_value={'status':'ready'}):
            self.assertEqual(w.check_return(self.client, self.root, 'original')['status'], 'awaiting_recording_choice')
        w.choose(self.root, 'original', 'yes', 'explicit yes')
        with patch.object(w, 'receive_ready', return_value={'status':'ready'}):
            self.assertEqual(w.check_return(self.client, self.root, 'original')['status'], 'awaiting_recording_start')
        w.choose(self.root, 'original', 'no', 'explicit no')
        with patch.object(w, 'receive_ready', return_value={'status':'ready'}):
            self.assertEqual(w.check_return(self.client, self.root, 'original')['status'], 'ready')

    def test_old_result_cannot_complete_current_output(self):
        w.write(self.root/'element-playback-state.json', {'job_id':self.order['job_id'], 'run_id':'new', 'worker_pid':1})
        w.write(self.root/'element-output-result.json', {'job_id':self.order['job_id'], 'run_id':'old', 'status':'completed'})
        with patch.object(w, 'worker_alive', return_value=True):
            self.assertEqual(w.check_return(self.client, self.root, 'original')['status'], 'running')
        with patch.object(w, 'worker_alive', return_value=False):
            self.assertEqual(w.check_return(self.client, self.root, 'original')['status'], 'failed')
        w.write(self.root/'element-output-result.json', {'job_id':self.order['job_id'], 'run_id':'new', 'status':'completed'})
        self.assertEqual(w.check_return(self.client, self.root, 'original')['status'], 'completed')
        self.client.call.assert_not_called()

    def test_panel_receives_without_launching_office(self):
        server = SimpleNamespace(remote=None, output=None)
        self.client.call.return_value = {'job_id': self.order['job_id'], 'status':'completed',
                                         'mode':'planned_deck', 'page_count':2}
        with patch.object(panel, 'Client', return_value=self.client), patch.object(w, 'receive_ready') as receive:
            panel.refresh(server, self.root, self.order, 'test')
        receive.assert_called_once()
        self.assertIsNone(server.output)
        self.assertIn('原对话', server.remote['playback_label'])
        self.assertNotIn('play_elements', vars(panel))


if __name__ == '__main__':
    unittest.main()
