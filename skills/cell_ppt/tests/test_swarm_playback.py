import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from hashlib import sha256
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import swarm_playback as swarm
import output_worker

class SwarmTests(unittest.TestCase):
    def test_parallel_progress_not_serial_drain(self):
        seen=[]
        def worker(name,steps):
            for n in range(steps):
                seen.append((name,n));yield
        active=[worker('drawing',2),worker('chinese',3),worker('english',1)]
        active=swarm.advance(active)
        self.assertEqual(seen,[('drawing',0),('chinese',0),('english',0)])
        while active:active=swarm.advance(active)
        self.assertEqual(seen[-2:],[('chinese',1),('chinese',2)])

    def test_mixed_typing_preserves_all_characters_and_utf16_offsets(self):
        text='中文 DNA🧬\rβ'
        steps=list(swarm.character_steps(text))
        self.assertEqual(''.join(row[2] for row in steps),text)
        self.assertEqual(steps[0][3],'zhong')
        dna=next(row for row in steps if row[2]=='🧬')
        following=next(row for row in steps if row[2]=='\r')
        self.assertEqual(dna[1],2)
        self.assertEqual(following[0],dna[0]+2)

    def test_missing_or_exposed_elements_fail_before_animation(self):
        s=SimpleNamespace(Id=4,Visible=0)
        deck=SimpleNamespace(Slides=[SimpleNamespace(SlideID=256,Shapes=[s])])
        swarm.validate_targets(deck,{'256':[4]})
        for ids in [[5],[4,4]]:
            with self.assertRaises(ValueError):swarm.validate_targets(deck,{'256':ids})
        s.Visible=-1
        with self.assertRaises(ValueError):swarm.validate_targets(deck,{'256':[4]})

    def test_windows_routes_to_swarm_and_preserves_bound_result_on_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);copy=root/'copy.pptx';copy.write_bytes(b'isolated')
            manifest=root/'manifest.json'
            manifest.write_text(json.dumps({'job_id':'job','run_id':'run','copy':str(copy),
                'source':str(root/'source.pptx'),'copy_sha256':sha256(copy.read_bytes()).hexdigest()}))
            for code in [0,1]:
                with patch.object(output_worker.sys,'platform','win32'), patch.object(output_worker.subprocess,'run',return_value=SimpleNamespace(returncode=code)) as launch:
                    self.assertEqual(output_worker.run(manifest),code)
                argv=launch.call_args.args[0]
                self.assertEqual(Path(argv[3]).name,'swarm_playback.py')
                result=json.loads((root/output_worker.RESULT).read_text())
                self.assertEqual((result['job_id'],result['run_id']),('job','run'))
                self.assertEqual(result['status'],'completed' if code==0 else 'failed')
if __name__=='__main__':unittest.main()
