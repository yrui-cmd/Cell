import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from quality_gate import build_report, score, validate_input
from render_report import render
from freeze_snapshot import make_manifest

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.bundle=json.loads((ROOT/'examples/synthetic_audit_bundle.json').read_text(encoding='utf-8'))
    def live(self):
        # This changes only the fixture's mode to exercise branches, not its factual status.
        self.bundle['run']['mode']='live'
        return self.bundle
    def test_schema_accepts_fixture(self):validate_input(self.bundle)
    def test_exactly_five_slots(self):self.assertEqual(len(build_report(self.bundle)['slots']),5)
    def test_demo_never_claims_pass(self):self.assertEqual(build_report(self.bundle)['overall_status'],'SYNTHETIC_DEMO')
    def test_deterministic(self):self.assertEqual(build_report(self.bundle),build_report(copy.deepcopy(self.bundle)))
    def test_stable_tie_break(self):
        self.bundle['candidates'].reverse()
        self.assertEqual([s['candidate']['id'] for s in build_report(self.bundle)['slots']],['C01','C02','C03','C04','C05'])
    def test_unknown_reference_rejected(self):
        self.bundle['candidates'][0]['claims'][0]['citations'][0]['source_id']='INVENTED'
        self.assertIn('C01',[r['candidate_id'] for r in build_report(self.bundle)['rejected_candidates']])
    def test_future_source_rejected(self):
        self.bundle['sources'][0]['first_public_date']='2026-10-01'
        self.assertTrue(all(s['status']=='vacant' for s in build_report(self.bundle)['slots']))
    def test_future_version_rejected(self):
        self.bundle['sources'][0]['version_date']='2026-10-01'
        self.assertEqual(build_report(self.bundle)['qualified_count'],0)
    def test_retracted_premise_rejected(self):
        self.bundle['sources'][0]['integrity']='retracted'
        self.assertEqual(len(build_report(self.bundle)['rejected_candidates']),6)
    def test_missing_resource_conditional_not_novelty_downgrade(self):
        c=self.bundle['candidates'][0];c['resources']['critical_unknowns']=['data access'];c['ratings']['N']['level']=4
        self.bundle['candidates']=self.bundle['candidates'][:5]
        result=[s for s in build_report(self.bundle)['slots'] if s['candidate'] and s['candidate']['id']=='C01'][0]
        self.assertEqual(result['status'],'conditional');self.assertEqual(result['effective_levels']['F'],1)
        self.assertEqual(result['effective_novelty_confidence'],'high')
    def test_metadata_only_conditional(self):
        self.bundle['sources'][0]['access']='metadata'
        self.assertEqual(build_report(self.bundle)['qualified_count'],0)
    def test_abstract_closest_work_conditional(self):
        self.bundle['sources'][0]['access']='abstract'
        self.assertTrue(all(s['status']=='conditional' for s in build_report(self.bundle)['slots']))
    def test_duplicate_question_deduplicated(self):
        self.bundle['candidates'][1]['question_key']=self.bundle['candidates'][0]['question_key']
        ids=[s['candidate']['id'] for s in build_report(self.bundle)['slots'] if s['candidate']]
        self.assertNotIn('C02',ids);self.assertEqual(len(ids),5)
    def test_same_gap_cap(self):
        for c in self.bundle['candidates']:c['primary_gap_id']='SAME'
        report=build_report(self.bundle)
        self.assertEqual(sum(s['candidate'] is not None for s in report['slots']),2)
    def test_no_candidates_still_five_vacancies(self):
        self.bundle['candidates']=[]
        report=build_report(self.bundle)
        self.assertEqual(len(report['slots']),5);self.assertTrue(all(s['status']=='vacant' for s in report['slots']))
    def test_boolean_not_accepted_as_numeric_score(self):
        self.bundle['candidates'][0]['ratings']['N']['level']=True
        with self.assertRaises(ValueError):build_report(self.bundle)
    def test_duplicate_ids_invalid(self):
        self.bundle['sources'][1]['id']='S1'
        with self.assertRaises(ValueError):build_report(self.bundle)
    def test_fully_covered_question_rejected(self):
        self.bundle['candidates'][0]['nearest_work'][0]['overlap']='full'
        self.assertEqual(build_report(self.bundle)['rejected_candidates'][0]['candidate_id'],'C01')
    def test_n0_rejected(self):
        self.bundle['candidates'][0]['ratings']['N']['level']=0
        self.assertEqual(build_report(self.bundle)['rejected_candidates'][0]['candidate_id'],'C01')
    def test_missing_claim_citation_rejected(self):
        self.bundle['candidates'][0]['claims'][0]['citations']=[]
        self.assertEqual(build_report(self.bundle)['rejected_candidates'][0]['candidate_id'],'C01')
    def test_freshness_missing_prevents_live_pass(self):
        self.live()['run']['final_checked_at']=None
        self.assertEqual(build_report(self.bundle)['overall_status'],'PARTIAL')
    def test_stale_freshness_prevents_live_pass(self):
        self.live()['run']['final_checked_at']='2026-09-24T11:00:00+00:00'
        self.assertEqual(build_report(self.bundle)['overall_status'],'PARTIAL')
    def test_future_check_timestamp_rejected(self):
        self.live()['run']['final_checked_at']='2026-09-27T11:00:00+00:00'
        self.assertEqual(len(build_report(self.bundle)['rejected_candidates']),6)
    def test_replay_label_not_live_pass(self):
        self.bundle['run']['mode']='replay'
        self.assertEqual(build_report(self.bundle)['overall_status'],'REPLAY_PASS')
    def test_offline_not_current_recommendation(self):
        self.bundle['run']['mode']='offline'
        self.assertEqual(build_report(self.bundle)['overall_status'],'EXPLORATORY')
    def test_incomplete_search_is_unknown_not_low_novelty_in_render(self):
        for c in self.bundle['candidates']:c['novelty_queries_complete']=False
        output=render(build_report(self.bundle))
        self.assertIn('无法可靠判定',output)
    def test_score_max(self):
        self.assertEqual(score({k:4 for k in ['N','V','F','T','E']},{'N':.3,'V':.2,'F':.2,'T':.15,'E':.15}),100)
    def test_renderer_has_five_topic_sections(self):
        self.assertEqual(render(build_report(self.bundle)).count('\n## 选题'),5)
    def test_snapshot_stable_then_changes(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);(d/'evidence.txt').write_text('one',encoding='utf-8')
            a=make_manifest(d);b=make_manifest(d);self.assertEqual(a,b)
            (d/'evidence.txt').write_text('two',encoding='utf-8')
            self.assertNotEqual(a['snapshot_sha256'],make_manifest(d)['snapshot_sha256'])

if __name__=='__main__':unittest.main()
