import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from lxml import etree
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import playback
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

if __name__=='__main__':unittest.main()
