"""Task-specific evidence policy regressions using synthetic article records."""
import copy
import unittest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import reference_composition as composition
from test_reference_composition import record


def policy(mode='domain_specific', designs=None):
    return {'mode': mode, 'minimum_experimental_percent': None,
            'unit': 'unique_eligible_articles_actually_cited',
            'target_designs': designs or ['theoretical'],
            'basis': 'Synthetic task requires this design; not chosen to rescue a failed ratio.'}


class EvidencePolicyTests(unittest.TestCase):
    def test_pure_theory_computation_and_observation_can_pass_applicable_policy(self):
        for design in ('theoretical', 'computational', 'observational'):
            with self.subTest(design=design):
                result = composition.composition_summary([record(1, design)], policy(designs=[design]))
                self.assertEqual(result['status'], 'COMPOSITION_CHECKS_PASSED', result)
                self.assertEqual(result['experimental_articles'], 0)
                self.assertIsNone(result['required_experimental_articles'])
                self.assertEqual(result['target_design_articles'], 1)

    def test_prespecified_observational_evidence_does_not_require_experiments(self):
        result = composition.composition_summary([record(1, 'observational')], policy('prespecified', ['observational']))
        self.assertEqual(result['status'], 'COMPOSITION_CHECKS_PASSED', result)

    def test_policy_cannot_be_empty_malformed_or_lower_the_existing_threshold(self):
        for p in ({}, {'mode': []}, {**policy(), 'basis': ''}, {**policy(), 'minimum_experimental_percent': 0},
                  {**policy(), 'target_designs': ['unverified']}, {**policy(), 'mode': 'experimental75', 'minimum_experimental_percent': 50}):
            with self.subTest(policy=p):
                self.assertEqual(composition.composition_summary([record(1)], p)['status'], 'NEEDS_REVISION')

    def test_empty_bibliography_and_irrelevant_design_do_not_pass(self):
        for records in ([], [record(1, 'experimental')], [record(1, 'unverified')]):
            self.assertEqual(composition.composition_summary(records, policy())['status'], 'NEEDS_REVISION')

    def test_identity_verification_is_still_enforced_without_experimental_quota(self):
        rows = [record(1, 'theoretical'), record(2, 'theoretical')]
        rows[1]['title'] = rows[0]['title']
        self.assertEqual(composition.composition_summary(rows, policy())['status'], 'NEEDS_REVISION')

    def test_editing_manifest_accepts_a_single_necessary_theory_citation(self):
        result = composition.audit_manifest({'scope': 'added', 'reference_composition_policy': policy(), 'records': [record(1, 'theoretical')]})
        self.assertEqual(result['status'], 'COMPOSITION_CHECKS_PASSED', result)

    def test_experimental75_remains_binding_and_legacy_records_remain_readable(self):
        legacy = composition.composition_summary([record(1, 'theoretical')])
        self.assertEqual(legacy['status'], 'NEEDS_REVISION')
        result = composition.composition_summary([record(1)], {'mode': 'experimental75', 'minimum_experimental_percent': 75,
            'unit': 'unique_eligible_articles_actually_cited', 'basis': 'Synthetic experimental theme.'})
        self.assertEqual(result['status'], 'COMPOSITION_CHECKS_PASSED')


if __name__ == '__main__':
    unittest.main()
