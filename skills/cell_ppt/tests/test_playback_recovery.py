import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from lxml import etree
import requests
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import playback
import return_watch
import progress_panel
import transfer

class PlaybackRecoveryTests(unittest.TestCase):
    def test_wrong_type_removed_but_valid_tags_preserved(self):
        rel='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
        xml=etree.fromstring(f'<p:sld xmlns:p="{playback.NS}" xmlns:r="{rel}"><p:nvPr><p:custDataLst><p:tags r:id="wrong"/><p:tags r:id="good"/></p:custDataLst></p:nvPr></p:sld>')
        relationships=[etree.Element('Relationship',Id='wrong',Type=rel+'/slideLayout'),etree.Element('Relationship',Id='good',Type=rel+'/tags')]
        self.assertEqual(playback.remove_invalid_tags(xml,relationships),1)
        self.assertEqual(list(xml.iter(playback.p('tags')))[0].get('{'+rel+'}id'),'good')

    def test_failed_worker_rebuilds_instead_of_reusing_dead_pid(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source.pptx';source.write_bytes(b'original')
            state={'job_id':'job','run_id':'old','worker_pid':987654,'copy':'old.pptx'}
            transfer.write(root/'element-playback-state.json',state)
            transfer.write(root/'element-output-result.json',{'job_id':'job','run_id':'old','status':'failed'})
            class Client:
                def receive(self,*args): return source
            def prepare(src,dest,**kwargs):dest.write_bytes(b'preview');return {'256':[1]}
            with patch.object(transfer,'inspect',return_value={}),patch.object(playback,'prepare',side_effect=prepare),patch.object(playback,'launch',return_value=123):
                result=transfer.play_elements(Client(),root,{'job_id':'job'},{})
            self.assertEqual(result['worker_pid'],123)
            self.assertNotEqual(result['run_id'],'old')
            self.assertEqual(source.read_bytes(),b'original')

    def test_live_worker_not_launched_twice(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);state={'job_id':'job','run_id':'active','worker_pid':123}
            transfer.write(root/'element-playback-state.json',state)
            with patch.object(playback,'worker_alive',return_value=True),patch.object(playback,'launch') as launch:
                self.assertEqual(transfer.play_elements(None,root,{'job_id':'job'},{}),state)
                launch.assert_not_called()

    def test_download_timeout_retries_same_job_before_return_to_chat(self):
        order = {"job_id": "a" * 32, "status": "queued", "credits": 1, "queued_at_unix": 1000}
        reply = {**order, "mode": transfer.MODE, "page_count": 1, "status": "completed"}
        server = MagicMock()
        server.output = None
        state = {"job_id": order["job_id"], "worker_pid": 321}

        def check_wait(_seconds):
            current = progress_panel.snapshot(order, server.remote, output="failed")
            self.assertEqual(current["percent"], 100)
            self.assertTrue(current["receiving"])
            self.assertFalse(current["terminal"])
            self.assertIsNone(current["output_state"])

        with tempfile.TemporaryDirectory() as directory, \
                patch.object(progress_panel, "Client") as client, \
                patch.object(return_watch, "receive_ready", side_effect=[requests.Timeout(), state]) as receive, \
                patch.object(progress_panel.time, "sleep", side_effect=check_wait) as delay:
            client.return_value.call.return_value = reply
            progress_panel.refresh(server, Path(directory), order, "synthetic")
        self.assertEqual(receive.call_count, 2)
        self.assertEqual(receive.call_args_list[0], receive.call_args_list[1])
        delay.assert_called_once()
        self.assertFalse(server.remote["receiving"])
        self.assertIsNone(server.output)
        self.assertIn("原对话", server.remote["playback_label"])

if __name__=='__main__':unittest.main()
