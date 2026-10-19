"""Package-local knowledge, declared dependencies and non-delegation checks."""
import ast
import json
import re
import unittest
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import oracle as o

class Standalone(unittest.TestCase):
    def test_local_work_files_exist(self):
        for rel in ['SKILL.md','rules/submission-v1.json','scripts/oracle.py',
                    'references/scoring-v1.md','references/systems.md',
                    'references/method.md','references/interpretation.md',
                    'references/sources.md','requirements.txt']:
            with self.subTest(file=rel):
                self.assertTrue((ROOT/rel).is_file())
                self.assertTrue((ROOT/rel).read_text(encoding='utf-8').strip())

    def test_no_remote_skill_uri(self):
        marker='skills'+':'+'//'
        for p in ROOT.rglob('*'):
            if p.is_file() and p.suffix in {'.md','.py','.json','.yaml','.txt'}:
                self.assertNotIn(marker,p.read_text(encoding='utf-8'),p.name)

    def test_only_own_explicit_skill_handle(self):
        for p in ROOT.rglob('*'):
            if p.is_file() and p.suffix in {'.md','.json','.yaml'}:
                text=p.read_text(encoding='utf-8')
                handles=re.findall(r'\$([A-Za-z][A-Za-z0-9_-]*)',text)
                self.assertTrue(all(h=='cell_sci_magic' for h in handles),p.name)

    def test_runtime_imports_only_standard_and_declared_libraries(self):
        tree=ast.parse((ROOT/'scripts/oracle.py').read_text(encoding='utf-8'))
        allowed={'__future__','argparse','hashlib','importlib','json','sys','datetime',
                 'functools','pathlib','typing','zoneinfo','cnlunar','lunar_python'}
        found=set()
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                found.update(n.name.split('.')[0] for n in node.names)
            elif isinstance(node,ast.ImportFrom):
                found.add((node.module or '').split('.')[0])
        self.assertTrue(found.issubset(allowed),repr(found-allowed))
        calls={n.func.id for n in ast.walk(tree)
               if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
        self.assertFalse(calls.intersection({'eval','exec','__import__'}))

    def test_no_runtime_network_or_shell_dispatch(self):
        tree=ast.parse((ROOT/'scripts/oracle.py').read_text(encoding='utf-8'))
        imports=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import): imports.extend(n.name for n in node.names)
            elif isinstance(node,ast.ImportFrom): imports.append(node.module or '')
        prohibited={'requests','httpx','socket','subprocess','urllib','webbrowser','os'}
        self.assertFalse({n.split('.')[0] for n in imports}.intersection(prohibited))

    def test_pins_match_local_rule(self):
        rules=json.loads((ROOT/'rules/submission-v1.json').read_text(encoding='utf-8'))
        pins={}
        for line in (ROOT/'requirements.txt').read_text().splitlines():
            line=line.strip()
            if line and not line.startswith('#'):
                name,ver=line.split('==',1); pins[name]=ver
        self.assertEqual(pins,rules['dependencies'])

    def test_internal_knowledge_contains_complete_scoring_and_windows(self):
        method=(ROOT/'references/method.md').read_text(encoding='utf-8')
        for fragment in ['09:00—21:00','事件分：宜60，中性30，不宜0','23:00',
                         '并列','20分钟','30分钟','上表章']:
            self.assertIn(fragment,method)

    def test_verdict_does_not_label_bad_hour_as_auspicious(self):
        c={'event':'submission','event_fit':'favorable',
           'facts':{'day_officer':'开','hour_deity':'玄武','hour_luck':'凶'}}
        text=o.verdict(c)
        self.assertIn('时象未全',text)
        self.assertNotIn('文卷得宜',text)

    def test_general_event_has_no_manuscript_claim(self):
        c={'event':'travel','event_fit':'favorable',
           'facts':{'day_officer':'开','hour_deity':'玉堂','hour_luck':'吉'}}
        text=o.verdict(c)
        self.assertIn('此事',text)
        self.assertNotIn('文卷',text)

    def test_submission_verdict_uses_actual_fact_fields(self):
        c={'event':'submission','event_fit':'favorable',
           'facts':{'day_officer':'成','hour_deity':'明堂','hour_luck':'吉'}}
        text=o.verdict(c)
        self.assertIn('成日',text)
        self.assertIn('明堂',text)
        self.assertNotIn('玉堂',text)

    def test_neutral_verdict_does_not_invent_event_favorability(self):
        c={'event':'submission','event_fit':'neutral',
           'facts':{'day_officer':'开','hour_deity':'玉堂','hour_luck':'吉'}}
        text=o.verdict(c)
        self.assertIn('未列明确宜忌',text)
        self.assertNotIn('文卷得宜',text)

    def test_no_packaged_approval_or_generated_recommendations(self):
        self.assertFalse((ROOT/'.state/approval.json').exists())
        self.assertFalse((ROOT/'output').exists())

if __name__=='__main__': unittest.main()
