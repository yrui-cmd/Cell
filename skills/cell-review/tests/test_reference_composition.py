"""Synthetic classification/counting tests; no actual scientific sources."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reference_composition as composition


def record(i, category='experimental', origin='added', final_cited=True):
    return {
        'id': f'R{i:03}', 'article_id': f'A{i:03}', 'identifier': f'TEST-ONLY-{i:03}',
        'title': f'Synthetic paper {i}', 'publication_type': 'original_research',
        'origin': origin, 'final_cited': final_cited,
        'study_design': {
            'category': category, 'verified': category != 'unverified',
            'basis': 'Synthetic test classification only.', 'locator': 'Synthetic methods fixture',
        },
    }


class CompositionTests(unittest.TestCase):
    def test_boundary_and_ceiling(self):
        for total, experimental, passes, required in (
            (4, 3, True, 3), (4, 2, False, 3), (3, 2, False, 3),
            (80, 60, True, 60), (81, 60, False, 61), (81, 61, True, 61),
        ):
            with self.subTest(total=total, experimental=experimental):
                records = [record(i, 'experimental' if i <= experimental else 'observational')
                           for i in range(1, total + 1)]
                result = composition.composition_summary(records)
                self.assertEqual(result['status'] == 'COMPOSITION_CHECKS_PASSED', passes, result)
                self.assertEqual(result['required_experimental_articles'], required)

    def test_original_research_does_not_imply_experimental(self):
        for category in ('observational', 'computational', 'theoretical', 'evidence_synthesis', 'other'):
            with self.subTest(category=category):
                result = composition.composition_summary([record(1, category)])
                self.assertEqual(result['experimental_articles'], 0)
                self.assertEqual(result['unique_articles'], 1)
                self.assertEqual(result['status'], 'NEEDS_REVISION')

    def test_unknown_design_stays_in_denominator(self):
        result = composition.composition_summary([record(1), record(2), record(3, 'unverified')])
        self.assertEqual(result['unique_articles'], 3)
        self.assertEqual(result['experimental_articles'], 2)
        self.assertEqual(result['unverified_design_articles'], 1)
        self.assertEqual(result['status'], 'NEEDS_REVISION')

    def test_duplicate_experiment_cannot_inflate_ratio(self):
        records = [record(1), record(2), record(3, 'observational'), record(4)]
        records[3]['article_id'] = records[0]['article_id']
        result = composition.composition_summary(records)
        self.assertEqual((result['experimental_articles'], result['unique_articles']), (2, 3))
        self.assertEqual(result['status'], 'NEEDS_REVISION')

    def test_conflicting_duplicate_classifications_block(self):
        records = [record(1), record(2, 'observational')]
        records[1]['article_id'] = records[0]['article_id']
        result = composition.composition_summary(records)
        self.assertEqual(result['experimental_articles'], 0)
        self.assertTrue(any('conflicting design' in e for e in result['errors']))

    def test_review_or_meta_analysis_cannot_be_marked_experimental(self):
        for publication_type in ('review', 'systematic_review', 'scoping_review', 'meta_analysis'):
            r = record(1)
            r['publication_type'] = publication_type
            result = composition.composition_summary([r])
            self.assertEqual(result['experimental_articles'], 0)
            self.assertEqual(result['status'], 'NEEDS_REVISION')

    def test_verified_classification_requires_evidence(self):
        for update in ({'verified': 1}, {'basis': ''}, {'locator': ''}, {'category': []}):
            r = record(1)
            r['study_design'].update(update)
            result = composition.composition_summary([r])
            self.assertEqual(result['status'], 'NEEDS_REVISION', result)
            self.assertEqual(result['experimental_articles'], 0)

    def test_added_scope_excludes_existing_and_removed(self):
        records = [record(1), record(2), record(3), record(4, 'observational'),
                   record(5, 'observational', origin='existing'), record(6, final_cited=False)]
        result = composition.audit_manifest({'scope': 'added', 'records': records})
        self.assertEqual((result['experimental_articles'], result['unique_articles']), (3, 4))
        self.assertEqual(result['status'], 'COMPOSITION_CHECKS_PASSED')
        result = composition.audit_manifest({'scope': 'all', 'records': records})
        self.assertEqual((result['experimental_articles'], result['unique_articles']), (3, 5))
        self.assertEqual(result['status'], 'NEEDS_REVISION')

    def test_new_version_of_existing_article_is_not_new_reference(self):
        records = [record(1, origin='existing'), record(2)]
        records[0]['identifier'] = '10.1234/synthetic'
        records[1]['identifier'] = 'https://doi.org/10.1234/SYNTHETIC'
        result = composition.audit_manifest({'scope': 'added', 'records': records})
        self.assertEqual(result['status'], 'NOT_APPLICABLE')
        self.assertIsNone(result['experimental_percentage'])

    def test_empty_scope_is_not_100_percent(self):
        result = composition.audit_manifest({'scope': 'added', 'records': []})
        self.assertEqual(result['status'], 'NOT_APPLICABLE')
        self.assertIsNone(result['experimental_percentage'])
        result = composition.audit_manifest({'scope': 'all', 'records': []})
        self.assertEqual(result['status'], 'NEEDS_REVISION')
        self.assertIsNone(result['experimental_percentage'])

    def test_malformed_manifest_rejected(self):
        for data in (None, [], {'scope': []}, {'scope': 'all', 'records': None},
                     {'scope': 'all', 'records': [{}]}):
            with self.subTest(data=data):
                self.assertEqual(composition.audit_manifest(data)['status'], 'NEEDS_REVISION')

    def test_standalone_cli_returns_actionable_status(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.json'
            for category, code in (('experimental', 0), ('observational', 1)):
                path.write_text(json.dumps({'scope': 'added', 'records': [record(1, category)]}), encoding='utf-8')
                result = subprocess.run(
                    [sys.executable, str(Path(composition.__file__)), str(path)],
                    capture_output=True, text=True, encoding='utf-8',
                )
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertEqual(json.loads(result.stdout)['unique_articles'], 1)


if __name__ == '__main__':
    unittest.main()
