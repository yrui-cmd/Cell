import copy
import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from quality_gate import build_report, validate_input
from weight_sensitivity import analyze, weight_scenarios, canonical_hash
from render_report import render

class SingleModelTests(unittest.TestCase):
    def setUp(self):
        self.bundle=json.loads((ROOT/'examples/synthetic_audit_bundle.json').read_text(encoding='utf-8'))
        self.weights={'N':.30,'V':.20,'F':.20,'T':.15,'E':.15}
    def test_one_model_declaration(self):
        self.assertEqual(build_report(self.bundle)['execution']['mode'],'single_model_sequential')
    def test_second_reviewer_model_rejected(self):
        self.bundle['execution']['reviewer_model_id']='OTHER'
        with self.assertRaises(ValueError):validate_input(self.bundle)
    def test_second_generator_model_rejected(self):
        self.bundle['execution']['generator_model_id']='OTHER'
        with self.assertRaises(ValueError):validate_input(self.bundle)
    def test_fake_independent_review_rejected(self):
        self.bundle['execution']['independent_review']=True
        with self.assertRaises(ValueError):validate_input(self.bundle)
    def test_fake_same_context_blinding_rejected(self):
        self.bundle['execution']['exposed_to_previous_scores']=False
        with self.assertRaises(ValueError):validate_input(self.bundle)
    def test_actual_fresh_context_declaration_accepted(self):
        self.bundle['execution'].update(context_mode='fresh_context',exposed_to_previous_scores=False)
        validate_input(self.bundle)
    def test_missing_execution_rejected(self):
        del self.bundle['execution']
        with self.assertRaises(ValueError):validate_input(self.bundle)
    def test_eleven_weight_configurations(self):
        self.assertEqual(len(weight_scenarios(self.weights)),11)
    def test_weights_normalized(self):
        for s in weight_scenarios(self.weights):self.assertAlmostEqual(sum(s['weights'].values()),1)
    def test_target_perturbation(self):
        scenarios=weight_scenarios(self.weights)
        self.assertAlmostEqual(scenarios[1]['weights']['N'],.25)
        self.assertAlmostEqual(scenarios[2]['weights']['N'],.35)
    def test_relative_non_target_weights_preserved(self):
        for s in weight_scenarios(self.weights)[1:3]:
            self.assertAlmostEqual(s['weights']['V']/s['weights']['T'],.20/.15)
    def test_invalid_delta_rejected(self):
        for delta in (0,-.05,float('nan'),True,2):
            with self.assertRaises(ValueError):weight_scenarios(self.weights,delta)
    def test_invalid_weights_rejected(self):
        with self.assertRaises(ValueError):weight_scenarios({'N':1})
    def test_sensitivity_deterministic_and_no_mutation(self):
        original=copy.deepcopy(self.bundle)
        self.assertEqual(analyze(self.bundle),analyze(self.bundle))
        self.assertEqual(self.bundle,original)
    def test_same_grid_stable_fixture(self):
        result=analyze(self.bundle)
        self.assertFalse(result['selection_sensitive']);self.assertFalse(result['order_sensitive'])
    def test_baseline_hash_exact(self):
        self.assertEqual(analyze(self.bundle)['baseline_report_sha256'],canonical_hash(build_report(self.bundle)))
    def test_rejected_candidate_never_selected(self):
        self.bundle['candidates'][0]['checks']['scope']='fail'
        result=analyze(self.bundle)
        self.assertTrue(all('C01' not in s['selected_ids'] for s in result['scenarios']))
    def test_duplicate_question_never_selected_twice(self):
        self.bundle['candidates'][1]['question_key']=self.bundle['candidates'][0]['question_key']
        for s in analyze(self.bundle)['scenarios']:
            self.assertFalse('C01' in s['selected_ids'] and 'C02' in s['selected_ids'])
    def test_sensitive_selection_detected(self):
        # Four clearly higher candidates; the remaining pair ties at baseline,
        # but changes membership when V/F relative weights move.
        for c in self.bundle['candidates'][:4]:
            for r in c['ratings'].values():r['level']=4
        c5,c6=self.bundle['candidates'][4:6]
        c5['ratings']['V']['level']=4;c5['ratings']['F']['level']=2
        c6['ratings']['V']['level']=2;c6['ratings']['F']['level']=4
        self.assertTrue(analyze(self.bundle)['selection_sensitive'])
    def test_no_candidates_grid_supported(self):
        self.bundle['candidates']=[]
        result=analyze(self.bundle)
        self.assertEqual(result['baseline_ids'],[]);self.assertFalse(result['selection_sensitive'])
    def test_renderer_discloses_self_audit(self):
        text=render(build_report(self.bundle),analyze(self.bundle))
        self.assertIn('不是独立专家评审',text)
        self.assertIn('不是成功概率',text)
        self.assertEqual(text.count('\n## 选题'),5)
    def test_renderer_rejects_mismatched_diagnostic(self):
        result=analyze(self.bundle);result['baseline_report_sha256']='invalid'
        with self.assertRaises(ValueError):render(build_report(self.bundle),result)
    def test_renderer_flags_missing_diagnostic(self):
        self.assertIn('未附计算结果',render(build_report(self.bundle)))

if __name__=='__main__':unittest.main()
