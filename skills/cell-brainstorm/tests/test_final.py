import contextlib
import copy
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from quality_gate import build_report, validate_input
from render_report import render
from weight_sensitivity import analyze
from session import init, advance, record, load_state


def fixture():
    return json.loads((ROOT/'examples/synthetic_audit_bundle_v2.json').read_text(encoding='utf-8'))

class EnhancedTests(unittest.TestCase):
    def setUp(self):
        self.b=fixture();self.b['candidates']=self.b['candidates'][:5]
        self.c=self.b['candidates'][0];self.e=self.c['enhancement']
    def target(self):
        return next(s for s in build_report(self.b)['slots'] if s['candidate'] and s['candidate']['id']==self.c['id'])
    def test_v2_fixture_schema(self):validate_input(self.b)
    def test_v2_five_topics(self):self.assertEqual(len(build_report(self.b)['slots']),5)
    def test_new_source_in_summary_disallowed(self):
        self.c['report_sections']['plan']['source_ids']=['UNREAD']
        with self.assertRaises(ValueError):build_report(self.b)
    def test_summary_cites_closest_work(self):
        self.c['report_sections']['basis']['source_ids']=[]
        with self.assertRaises(ValueError):build_report(self.b)
    def test_report_sections_required(self):
        del self.c['report_sections']
        with self.assertRaises(ValueError):validate_input(self.b)
    def test_summary_hype_rejected(self):
        self.c['report_sections']['question']['text']='全球首创的顶刊潜力选题。'
        with self.assertRaises(ValueError):build_report(self.b)
    def test_summary_is_four_paragraphs_not_table(self):
        self.c['report_sections']['question']['text']='说明\n|分数|说明|'
        with self.assertRaises(ValueError):build_report(self.b)
    def test_revision_must_be_rechecked(self):
        self.e['revision'].update(version=2,claim_changed=True)
        s=self.target();self.assertEqual(s['status'],'conditional')
        self.assertEqual(s['effective_novelty_confidence'],'unknown')
        self.assertIn('修订后尚未完成文献复核',render(build_report(self.b)))
    def test_invalid_future_revision_check(self):
        self.e['revision']['last_novelty_checked_version']=2
        with self.assertRaises(ValueError):build_report(self.b)
    def test_scientific_gate_fail_not_offset_by_score(self):
        self.e['scientific_gates']['answerability']['status']='fail'
        for rating in self.c['ratings'].values():rating['level']=4
        self.assertIn(self.c['id'],[x['candidate_id'] for x in build_report(self.b)['rejected_candidates']])
    def test_scientific_gate_conditional_retained(self):
        self.e['scientific_gates']['knowledge_gain'].update(status='conditional',reason='尚缺关键全文。')
        self.assertEqual(self.target()['status'],'conditional')
        self.assertIn('尚缺关键全文',render(build_report(self.b)))
    def test_confirmed_constraint_needs_reference(self):
        self.b['constraints'][0]['evidence_ref']=None
        with self.assertRaises(ValueError):build_report(self.b)
    def test_unknown_constraint_cannot_look_confirmed(self):
        self.b['constraints'][0]['status']='unknown'
        with self.assertRaises(ValueError):build_report(self.b)
    def test_unknown_core_dependency_is_conditional(self):
        dep=self.e['paths']['P1']['routes'][0]['dependencies'][0]
        dep.update(status='unknown',constraint_ref=None,verification_ref=None)
        result=self.target()
        self.assertEqual(result['enhancement_audit']['path_statuses']['P0'],'ready')
        self.assertEqual(result['enhancement_audit']['path_statuses']['P1'],'conditional')
        self.assertEqual(result['effective_levels']['F'],1)
        self.assertEqual(result['effective_novelty_confidence'],'high')
        self.assertIn('落实合成资源',render(build_report(self.b)))
    def test_required_dependency_and(self):
        route=self.e['paths']['P1']['routes'][0]
        dep=copy.deepcopy(route['dependencies'][0]);dep.update(id='D2',status='unavailable',constraint_ref=None)
        route['dependencies'].append(dep)
        self.assertIn(self.c['id'],[x['candidate_id'] for x in build_report(self.b)['rejected_candidates']])
    def test_alternative_routes_or(self):
        route=self.e['paths']['P1']['routes'][0]
        route['dependencies'][0].update(status='unavailable',constraint_ref=None)
        alt=copy.deepcopy(self.e['paths']['P0']['routes'][0]);alt['id']='P1_ALT';self.e['paths']['P1']['routes'].append(alt)
        self.assertEqual(self.target()['enhancement_audit']['path_statuses']['P1'],'ready')
    def test_false_claim_preservation_does_not_rescue(self):
        self.e['paths']['P1']['routes'][0]['claim_preserved']=False
        self.assertIn(self.c['id'],[x['candidate_id'] for x in build_report(self.b)['rejected_candidates']])
    def test_relaxed_hard_constraint_rejected(self):
        self.b['constraints'][0]['negotiable']=False
        self.assertEqual(build_report(self.b)['qualified_count'],0)
    def test_relaxed_authorization_cannot_override(self):
        self.b['constraints'][0]['category']='authorization'
        self.assertEqual(build_report(self.b)['qualified_count'],0)
    def test_ladder_has_three_different_scenarios(self):
        self.e['constraint_ladder'][2]['scenario']='relaxed'
        with self.assertRaises(ValueError):build_report(self.b)
    def test_executed_requires_record(self):
        self.e['minimum_validation']['execution_status']='executed'
        with self.assertRaises(ValueError):build_report(self.b)
    def test_planned_is_allowed(self):self.assertEqual(self.target()['status'],'qualified')
    def test_inconclusive_branch_required(self):
        del self.e['minimum_validation']['inconclusive_if']
        with self.assertRaises(ValueError):build_report(self.b)
    def test_identical_predictions_need_check(self):
        row=self.e['prediction_matrix'][0];row['comparison_prediction']=row['favored_prediction']
        self.assertEqual(self.target()['status'],'conditional')
    def test_description_not_rejected_for_lack_of_causality(self):
        self.e['research_type']='descriptive';self.e['minimum_validation']['purpose']='measurement'
        self.assertEqual(self.target()['status'],'qualified')
    def test_theory_supported(self):
        self.e['research_type']='theory';self.e['minimum_validation']['purpose']='proof_task'
        self.assertEqual(self.target()['status'],'qualified')
    def test_analogy_target_cannot_be_known(self):
        self.e['analogies']=[{'source_system':'源','target_system':'目标','transferred_relation':'关系','required_conditions':'条件','mismatches':'差异','target_prediction':'预测','source_ids':['S1'],'target_status':'known'}]
        with self.assertRaises(ValueError):validate_input(self.b)
    def test_shared_unverified_premise_disclosed(self):
        for c in self.b['candidates'][:2]:
            c['enhancement']['assumptions'][0].update(
                statement='合成共同前提', status='unverified', source_ids=[])
            c['enhancement']['essential_assumption_ids']=['合成共同前提']
        r=build_report(self.b);self.assertEqual(len(r['shared_risks']),1)
        self.assertIn('合成共同前提',render(r))
    def test_essential_assumption_must_exist_in_ledger(self):
        self.e['essential_assumption_ids']=['不存在的前提']
        with self.assertRaisesRegex(ValueError,'not present'):
            build_report(self.b)
    def test_duplicate_assumption_statement_rejected(self):
        self.e['assumptions'].append(copy.deepcopy(self.e['assumptions'][0]))
        with self.assertRaisesRegex(ValueError,'unique stable'):
            build_report(self.b)
    def test_exact_five_memo_sections(self):
        out=render(build_report(self.b));self.assertEqual(len(re.findall(r'^## [一二三四五]、',out,re.M)),5)
        for name in ('研究依据','拟研究内容','研究方案','可行性与限制'):self.assertEqual(out.count(name+'：'),5)
    def test_memo_hides_audit_and_scores(self):
        r=build_report(self.b);out=render(r,analyze(self.b))
        for term in ('N3','N/V/F','创新等级','置信度','权重','三道门','执行方式','SYNTHETIC_DEMO','单模型自查'):
            self.assertNotIn(term,out)
        self.assertNotIn('|---',out)
    def test_numbered_citations_unique_bibliography(self):
        out=render(build_report(self.b));self.assertEqual(out.count('[1] SYNTHETIC'),1)
        self.assertEqual(out.count('## 参考文献'),1)
    def test_author_not_invented(self):
        out=render(build_report(self.b));self.assertNotIn('et al.',out)
    def test_abstract_limit_visible(self):
        self.b['sources'][0]['access']='abstract'
        out=render(build_report(self.b));self.assertIn('仅取得摘要',out)
    def test_offline_limit_visible(self):
        self.b['run']['mode']='offline'
        self.assertIn('未完成运行当日的文献复核',render(build_report(self.b)))
    def test_summary_unknowns_not_hidden(self):
        self.c['resources']['critical_unknowns']=['特定组织样本的取得权限']
        out=render(build_report(self.b));self.assertIn('特定组织样本的取得权限',out)
    def test_vacancies_preserved(self):
        self.b['candidates']=[];out=render(build_report(self.b))
        self.assertEqual(out.count('暂缺'),5)
    def test_memo_determinism(self):self.assertEqual(render(build_report(self.b)),render(build_report(copy.deepcopy(self.b))))
    def test_sensitivity_still_matched_when_hidden(self):
        r=build_report(self.b);a=analyze(self.b);r['brief']['research_content']='changed'
        with self.assertRaises(ValueError):render(r,a)

class ProgressAndCLITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=init(self.root/'run','M','synthetic','测试主题')
    def test_only_six_brief_messages(self):
        self.assertEqual([advance(self.path,n,'M') for n in range(1,7)],[f'第{n}步' for n in range(1,7)])
    def test_no_repeat_or_backtracking_message(self):
        advance(self.path,1,'M');advance(self.path,2,'M')
        self.assertEqual(advance(self.path,2,'M'),'');self.assertEqual(advance(self.path,1,'M'),'')
    def test_progress_cannot_skip(self):
        with self.assertRaises(ValueError):advance(self.path,3,'M')
    def test_progress_no_second_model(self):
        with self.assertRaises(ValueError):advance(self.path,1,'OTHER')
    def test_invalid_step(self):
        for n in (0,7,True):
            with self.assertRaises(ValueError):advance(self.path,n,'M')
    def test_init_no_overwrite(self):
        with self.assertRaises(ValueError):init(self.root/'run','M','synthetic','主题')
    def test_record_real_file_hash(self):
        f=self.path.parent/'records'/'r.txt';f.write_text('abc')
        record(self.path,'S05',f,'M');self.assertEqual(len(load_state(self.path)['artifact_records']),1)
    def test_record_rejects_outside_run(self):
        f=self.root/'outside.txt';f.write_text('abc')
        with self.assertRaises(ValueError):record(self.path,'S05',f,'M')
    def test_default_cli_chain_silent(self):
        inp=ROOT/'examples/synthetic_audit_bundle_v2.json';r=self.root/'r.json';s=self.root/'s.json';out=self.root/'r.md'
        commands=[['quality_gate.py','--input',str(inp),'--output',str(r)],
                  ['weight_sensitivity.py','--input',str(inp),'--output',str(s)],
                  ['render_report.py','--input',str(r),'--sensitivity',str(s),'--output',str(out)],
                  ['freeze_snapshot.py','--directory',str(self.path.parent/'evidence'),'--output',str(self.root/'snap.json')]]
        for cmd in commands:
            p=subprocess.run([sys.executable,str(ROOT/'scripts'/cmd[0])]+cmd[1:],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stdout,'')
        self.assertTrue(out.is_file())
    def test_cli_progress_line(self):
        env=os.environ.copy();env['PYTHONIOENCODING']='cp1252'
        p=subprocess.run([sys.executable,str(ROOT/'scripts/session.py'),'progress','--state',str(self.path),'--step','1','--model-id','M'],capture_output=True,text=True,encoding='utf-8',env=env)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stdout,'第1步\n')
    def test_cli_no_input_overwrite(self):
        p=subprocess.run([sys.executable,str(ROOT/'scripts/quality_gate.py'),'--input',str(ROOT/'examples/synthetic_audit_bundle_v2.json'),'--output',str(ROOT/'examples/synthetic_audit_bundle_v2.json')],capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0)
    def test_cli_error_not_silenced(self):
        p=subprocess.run([sys.executable,str(ROOT/'scripts/quality_gate.py'),'--input',str(self.root/'missing'),'--output',str(self.root/'out')],capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0);self.assertTrue(p.stderr)

if __name__=='__main__':unittest.main()
