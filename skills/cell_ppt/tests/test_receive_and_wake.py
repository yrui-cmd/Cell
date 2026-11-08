from pathlib import Path
import hashlib
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import receive_and_wake as r


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.state = dict(job_id='job', thread_id='origin', nonce='nonce', status='ready', wake_state='pending')
        r.write(self.root / 'order.json', dict(job_id='job', thread_id='origin', billing='settled'))
        file = self.root / 'result.pptx'
        file.write_bytes(b'offline receipt fixture')
        r.write(self.root / 'return-ready.json', dict(job_id='job', thread_id='origin', path=str(file),
                sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
        r.write(self.root / r.STATE, self.state)
        self.bridge = Mock()
        self.bridge._desktop_tool.return_value = {'thread': {'id': 'origin', 'status': {'type': 'idle'}}}
        self.bridge.submit.return_value = {'queued': True, 'thread_id': 'origin'}
        self.factory = Mock(return_value=self.bridge)

    def test_receipt_before_one_wake(self):
        self.assertTrue(r.wake(self.root, self.state, self.factory))
        self.assertTrue(r.wake(self.root, self.state, self.factory))
        self.bridge.submit.assert_called_once()
        self.assertEqual(self.bridge.submit.call_args.args[0], 'origin')

    def test_bad_hash_never_wakes(self):
        (self.root / 'result.pptx').write_bytes(b'changed')
        with self.assertRaises(ValueError): r.wake(self.root, self.state, self.factory)
        self.factory.assert_not_called()

    def test_pending_never_wakes(self):
        self.state['status'] = 'waiting'
        with self.assertRaises(ValueError): r.wake(self.root, self.state, self.factory)
        self.factory.assert_not_called()

    def test_uncertain_response_never_resends(self):
        self.bridge.submit.side_effect = TimeoutError()
        r.wake(self.root, self.state, self.factory)
        self.assertEqual(self.state['wake_state'], 'uncertain')
        r.wake(self.root, self.state, self.factory)
        self.bridge.submit.assert_called_once()

    def test_stop_and_active_chat_defer(self):
        (self.root / r.STOP).touch()
        self.assertFalse(r.wake(self.root, self.state, self.factory))
        self.factory.assert_not_called()
        (self.root / r.STOP).unlink()
        self.bridge._desktop_tool.return_value['thread']['status']['type'] = 'active'
        self.assertFalse(r.wake(self.root, self.state, self.factory))
        self.bridge.submit.assert_not_called()

    def test_wrong_order_binding_rejected(self):
        self.state['job_id'] = 'other'
        r.write(self.root / r.STATE, self.state)
        with self.assertRaises(ValueError): r.bound_state(self.root, 'origin')

    def test_repeated_start_never_launches_duplicate(self):
        with patch.object(r, 'probe'), patch.object(r, 'launch') as launch:
            r.start(self.root, 'origin')
            launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
