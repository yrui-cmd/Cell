"""Offline synthetic regressions for the 2026-10-31 contract repair."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from quality_gate import build_report
from render_report import render
from synthesis_gate import validate
from test_synthesis_gate import bundle


def modern_bundle(n=5):
    data = bundle()
    data['schema_version'] = 'synthesis-1.1'
    data['brief'] = {'research_content': 'SYNTHETIC evidence synthesis'}
    data['sources'] = []
    data['candidates'] = data['candidates'][:n]
    for c in data['candidates']:
        rev = c['nearest_reviews'][0]['source_id']
        primary = c['primary_evidence'][0]['source_id']
        for sid, kind in [(rev, 'review'), (primary, 'original_research')]:
            data['sources'].append({'id': sid, 'kind': kind, 'title': 'SYNTHETIC ' + sid, 'url': 'https://example.invalid/' + sid})
        c['report_sections'] = {
            'basis': {'text': 'Synthetic previous synthesis and evidence.', 'source_ids': [rev, primary]},
            'question': {'text': 'Synthetic bounded judgment.', 'source_ids': []},
            'plan': {'text': 'Synthetic extraction and comparison plan.', 'source_ids': [primary]},
            'limitations': {'text': 'Synthetic test only, not research evidence.', 'source_ids': []},
        }
    return data


class SynthesisRuntimeTests(unittest.TestCase):
    def test_zero_and_four_candidates_render_five_slots(self):
        for n in (0, 4):
            with self.subTest(n=n):
                data = modern_bundle(n)
                self.assertEqual(validate(data), [])
                text = render(data)
                self.assertEqual(sum(text.count('## ' + x + '、') for x in '一二三四五'), 5)
                self.assertEqual(text.count('、暂缺'), 5-n)

    def test_explicit_vacant_requires_no_fabricated_evidence(self):
        data = modern_bundle(4)
        data['candidates'].append({'id': 'VACANT5', 'status': 'vacant', 'reason': 'Insufficient reliable evidence.'})
        self.assertEqual(validate(data), [])
        self.assertIn('Insufficient reliable evidence.', render(data))

    def test_rejected_topic_is_not_recommended(self):
        data = modern_bundle(1)
        data['candidates'][0]['status'] = 'fail'
        self.assertNotIn(data['candidates'][0]['title'], render(data))

    def test_pass_cannot_hide_incomplete_search(self):
        data = modern_bundle(1)
        data['candidates'][0]['search_status']['novelty_complete'] = False
        self.assertTrue(any('status=pass' in e for e in validate(data)))

    def test_conditional_issue_is_disclosed(self):
        data = modern_bundle(1)
        c = data['candidates'][0]
        c['status'] = 'conditional'
        c['search_status']['novelty_complete'] = False
        c['open_items'] = [{'issue': 'Missing comparison', 'affects': 'Novelty not established', 'allowed_now': 'Pilot extraction', 'fallback': 'Bounded synthesis'}]
        self.assertEqual(validate(data), [])
        text = render(data)
        for value in c['open_items'][0].values():
            self.assertIn(value, text)

    def test_same_source_id_cannot_fill_two_roles(self):
        data = bundle()
        c = data['candidates'][0]
        c['primary_evidence'][0]['source_id'] = c['nearest_reviews'][0]['source_id']
        self.assertTrue(any('distinct article identities' in e for e in validate(data)))

    def test_doi_alias_cannot_fill_two_roles(self):
        data = modern_bundle(1)
        data['sources'][0]['doi'] = 'https://doi.org/10.0000/SYNTHETIC'
        data['sources'][1]['doi'] = 'doi:10.0000/synthetic'
        self.assertTrue(any('distinct article identities' in e for e in validate(data)))
        data = modern_bundle(1)
        data['sources'][0]['url'] = 'https://doi.org/10.0000/SYNTHETIC'
        data['sources'][1]['url'] = 'https://dx.doi.org/10.0000/synthetic'
        self.assertTrue(any('distinct article identities' in e for e in validate(data)))

    def test_registry_identity_cannot_be_overridden_by_role_row(self):
        data = modern_bundle(1)
        for source in data['sources']:
            source['article_id'] = 'SAME-ARTICLE'
        data['candidates'][0]['primary_evidence'][0]['article_id'] = 'different'
        self.assertTrue(any('distinct article identities' in e for e in validate(data)))

    def test_unknown_report_citation_is_rejected(self):
        data = modern_bundle(1)
        data['candidates'][0]['report_sections']['plan']['source_ids'] = ['UNREAD']
        with self.assertRaises(ValueError):
            render(data)

    def test_malformed_root_and_nested_values_return_errors(self):
        bad_status = modern_bundle(1)
        bad_status['candidates'][0]['status'] = []
        for value in (None, [], 'invalid', {'schema_version': [], 'run': {'mode': []}}, bad_status):
            with self.subTest(value=value):
                self.assertTrue(validate(value))

    def test_live_missing_freshness_cannot_pass(self):
        data = modern_bundle(1)
        data['run'].update(mode='live', report_created_at='2026-10-31T12:00:00+08:00', as_of='2026-10-31')
        self.assertTrue(any('freshness' in e for e in validate(data)))

    def test_gate_to_renderer_cli(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / 'audit.json'
            output = Path(temp) / 'report.md'
            data.write_text(json.dumps(modern_bundle(4)), encoding='utf-8')
            for cmd in ([str(ROOT / 'scripts/synthesis_gate.py'), str(data)],
                        [str(ROOT / 'scripts/render_report.py'), '--input', str(data), '--output', str(output)]):
                result = subprocess.run([sys.executable, *cmd], capture_output=True, text=True, encoding='utf-8', timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
            text = output.read_text(encoding='utf-8')
            self.assertIn('## 五、暂缺', text)
            self.assertIn('## 参考文献', text)


class FreshnessRenderingTests(unittest.TestCase):
    def fixture(self):
        data = json.loads((ROOT / 'examples/synthetic_audit_bundle_v2.json').read_text(encoding='utf-8'))
        data['run']['mode'] = 'live'
        return data

    def test_missing_freshness_reaches_final_memo(self):
        data = self.fixture()
        data['run']['final_checked_at'] = None
        report = build_report(data)
        self.assertIn('FRESHNESS_MISSING', report['slots'][0]['reason_codes'])
        self.assertIn('尚未完成最终文献时效复核', render(report))

    def test_stale_freshness_reaches_final_memo(self):
        from datetime import datetime, timedelta
        data = self.fixture()
        created = datetime.fromisoformat(data['run']['report_created_at'])
        data['run']['final_checked_at'] = (created-timedelta(hours=25)).isoformat()
        self.assertIn('最终文献复核已超出规定时限', render(build_report(data)))

    def test_legacy_report_reason_remains_readable(self):
        data = self.fixture()
        data['run']['final_checked_at'] = None
        report = build_report(data)
        for slot in report['slots']:
            slot.pop('reason_codes', None)
        self.assertIn('尚未完成最终文献时效复核', render(report))


if __name__ == '__main__':
    unittest.main()
