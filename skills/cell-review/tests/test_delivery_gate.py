"""Synthetic local contract tests only: no real sources, Word rendering or live QA.

Preview attestations are test fixtures, not claims that the pages were inspected.
"""
from __future__ import annotations

import copy
import sys
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import delivery_gate as gate
import review_tools as rt
import test_review_tools as fixtures


class DeliveryGateTests(unittest.TestCase):
    def setUp(self):
        self.base = fixtures.ReviewAuditTests('test_valid_synthetic_records')
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.run, self.protocol, self.ledger = self.base.run, self.base.protocol, self.base.ledger
        self.source_record = copy.deepcopy(self.ledger['records'][0])
        self.claim_text = self.ledger['claims'][0]['text']
        self.make_articles(30)

    def make_articles(self, n):
        self.ledger['records'] = []
        links = []
        refs = []
        for i in range(1, n + 1):
            r = copy.deepcopy(self.source_record)
            r.update(id=f'R{i:03}', study_id=f'S{i:03}', article_id=f'A{i:03}',
                     citation_number=i, title=f'Synthetic test reference {i:03}',
                     identifier=f'TEST-ONLY-ID-{i:03}')
            self.ledger['records'].append(r)
            links.append({'ref_id': r['id'], 'locator': 'synthetic section', 'support': 'direct',
                          'check_level': 'full_text', 'checked': True})
            refs.append(f'[{i}] Test Author. {r["title"]}. 2024. {r["identifier"]}.')
        self.ledger['claims'][0]['links'] = links
        self.body = f'Synthetic test only\nEvidence\n{self.claim_text}[1–{n}]\nLimitations\nThis is not a real review.'
        self.refs = '\n'.join(refs)
        word_excerpt = f'{self.claim_text}[1–{n}]'
        for link in links:
            link['word_excerpt'] = word_excerpt
        self.base.text = f'# Synthetic test only\n\n## Evidence\n{self.claim_text}[1–{n}]\n\n## Limitations\nThis is not a real review.\n\n## References\n{self.refs}\n'

    def word(self, body=None, refs=None):
        # Minimal standards-based editable Word fixture, using only the standard library.
        body = self.body if body is None else body
        refs = self.refs if refs is None else refs
        root = ET.Element(gate.W + 'document')
        b = ET.SubElement(root, gate.W + 'body')
        for line in (body + '\nReferences\n' + refs).splitlines():
            p = ET.SubElement(b, gate.W + 'p')
            r = ET.SubElement(p, gate.W + 'r')
            ET.SubElement(r, gate.W + 't').text = line
        ET.SubElement(b, gate.W + 'sectPr')
        ct = ET.Element(gate.CT + 'Types')
        ET.SubElement(ct, gate.CT + 'Default', Extension='rels', ContentType='application/vnd.openxmlformats-package.relationships+xml')
        ET.SubElement(ct, gate.CT + 'Default', Extension='xml', ContentType='application/xml')
        ET.SubElement(ct, gate.CT + 'Override', PartName='/word/document.xml', ContentType=gate.DOCX_TYPE)
        rels = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
        with zipfile.ZipFile(self.run / 'review.docx', 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('[Content_Types].xml', ET.tostring(ct, encoding='utf-8', xml_declaration=True))
            z.writestr('_rels/.rels', rels)
            z.writestr('word/document.xml', ET.tostring(root, encoding='utf-8', xml_declaration=True))

    def save(self, body=None, refs=None):
        self.base.save()
        self.word(body, refs)
        self.ledger['delivery_review'].update(
            status='completed', checked_at='2026-09-27',
            source_sha256=rt.file_hash(self.run / '_work' / 'review.md'),
            docx_sha256=rt.file_hash(self.run / 'review.docx'),
            page_count=2, pages_inspected=2,
            preview_locator='SYNTHETIC TEST ATTESTATION ONLY — NOT RENDERED',
            checks={key: True for key in gate.DELIVERY_CHECKS},
        )
        self.flush()

    def flush(self):
        rt.write_json(self.run / '_work' / 'protocol.json', self.protocol)
        rt.write_json(self.run / '_work' / 'evidence.json', self.ledger)

    def prepare_custom_style(self):
        self.protocol['output_citation_style'] = 'custom'
        markers = [f'(Test Author, 2024, item {i:03})' for i in range(1, 31)]
        body_excerpt = self.claim_text + ' ' + ' '.join(markers)
        body = self.body.replace(self.claim_text + '[1–30]', body_excerpt)
        self.save(body=body)
        refs = self.refs.splitlines()
        self.ledger['delivery_review']['citation_map'] = [
            {'ref_id': f'R{i:03}', 'marker': markers[i-1], 'body_excerpt': body_excerpt,
             'reference_excerpt': refs[i-1]} for i in range(1, 31)]
        for link in self.ledger['claims'][0]['links']:
            link['word_excerpt'] = body_excerpt
        self.flush()
        return markers, body_excerpt

    def check(self, fragment):
        result = gate.validate_delivery(self.run)
        self.assertEqual(result['status'], 'NEEDS_REVISION', result)
        self.assertTrue(any(fragment in e for e in result['errors']), result)
        return result

    def test_exactly_30_counted_articles_pass(self):
        self.save()
        result = gate.validate_delivery(self.run)
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['status'], 'DELIVERY_CHECKS_PASSED')
        self.assertEqual(result['counts']['unique_eligible_articles'], 30)
        self.assertFalse(result['scientific_quality_certified'])

    def test_31_articles_pass(self):
        self.make_articles(31)
        self.save()
        self.assertEqual(gate.validate_delivery(self.run)['status'], 'DELIVERY_CHECKS_PASSED')

    def test_29_articles_blocked(self):
        self.make_articles(29)
        self.save()
        self.check('found 29')

    def test_floor_cannot_be_lowered(self):
        self.protocol['minimum_article_count'] = 1
        self.save()
        self.check('lowering the gate')

    def test_boolean_is_not_article_floor(self):
        self.protocol['minimum_article_count'] = True
        self.save()
        self.check('integer >=30')

    def test_higher_user_minimum_honored(self):
        self.protocol['minimum_article_count'] = 40
        self.save()
        self.check('At least 40')

    def test_missing_docx_blocked(self):
        self.save()
        (self.run / 'review.docx').unlink()
        self.check('Word file is missing')

    def test_renamed_plaintext_is_not_word(self):
        self.save()
        (self.run / 'review.docx').write_text('not really Word')
        self.check('real DOCX package')

    def test_pdf_protocol_not_accepted(self):
        self.protocol['output_format'] = 'pdf'
        self.save()
        self.check('output_format must be docx')

    def test_output_traversal_blocked(self):
        self.protocol['output_file'] = '../review.docx'
        self.save()
        self.check('without directory traversal')

    def test_article_family_duplicate_counts_once(self):
        self.ledger['records'][-1]['article_id'] = 'A001'
        self.save()
        self.check('found 29')

    def test_doi_url_alias_duplicate_counts_once(self):
        self.ledger['records'][0]['identifier'] = '10.1234/example.test'
        self.ledger['records'][-1]['identifier'] = 'https://doi.org/10.1234/EXAMPLE.TEST'
        self.save()
        self.check('found 29')

    def test_same_title_conflicting_ids_are_not_silently_merged(self):
        self.ledger['records'][-1]['title'] = 'Synthetic test reference 001'
        self.refs = self.refs.replace('Synthetic test reference 030', 'Synthetic test reference 001')
        self.base.text = self.base.text.replace('Synthetic test reference 030', 'Synthetic test reference 001')
        self.save()
        result = self.check('conflicting article identifiers')
        self.assertEqual(result['counts']['unique_eligible_articles'], 30)
        self.assertTrue(result['identity_conflicts'])

    def test_claim_link_requires_final_word_range(self):
        self.ledger['claims'][0]['links'][0]['word_excerpt'] = 'Unrelated sentence [1].'
        self.save()
        self.check('final Word excerpt containing the claim')

    def test_different_articles_same_study_family_can_count(self):
        for r in self.ledger['records']:
            r['study_id'] = 'S001'
        self.save()
        result = gate.validate_delivery(self.run)
        self.assertEqual(result['status'], 'DELIVERY_CHECKS_PASSED', result)
        self.assertEqual(result['counts']['related_study_families'], 1)

    def test_guideline_is_not_article(self):
        self.ledger['records'][-1]['publication_type'] = 'journal_guidelines'
        self.save()
        self.check('found 29')

    def test_review_articles_are_valid_article_type(self):
        self.ledger['records'][-1]['publication_type'] = 'review'
        self.save()
        self.assertEqual(gate.validate_delivery(self.run)['status'], 'DELIVERY_CHECKS_PASSED')

    def test_retracted_article_cannot_fill_floor(self):
        self.ledger['records'][-1]['publication_status'] = 'retracted'
        self.save()
        self.check('found 29')

    def test_uncited_word_entry_not_counted(self):
        excerpt = f'{self.claim_text}[1–29]'
        for link in self.ledger['claims'][0]['links']:
            link['word_excerpt'] = excerpt
        self.save(body=self.body.replace('[1–30]', '[1–29]'))
        self.check('found 29')

    def test_unverified_identity_not_counted(self):
        self.ledger['records'][-1]['metadata_check']['status'] = 'pending'
        self.save()
        self.check('found 29')

    def test_no_content_mapping_not_counted(self):
        self.ledger['claims'][0]['links'].pop()
        self.save()
        self.check('found 29')

    def test_no_article_identity_not_counted(self):
        self.ledger['records'][-1].pop('article_id')
        self.save()
        self.check('found 29')

    def test_unread_article_not_counted(self):
        self.ledger['records'][-1]['reading'].update(abstract_read=False, full_text_read=False)
        self.save()
        self.check('found 29')

    def test_all_pages_must_be_inspected(self):
        self.save()
        self.ledger['delivery_review']['pages_inspected'] = 1
        self.flush()
        self.check('all pages_inspected')

    def test_no_preview_attestation_blocked(self):
        self.save()
        self.ledger['delivery_review']['preview_locator'] = None
        self.flush()
        self.check('render/preview locator')

    def test_changed_docx_invalidates_self_review(self):
        self.save()
        with zipfile.ZipFile(self.run / 'review.docx', 'a') as z:
            z.comment = b'Changed after synthetic attestation'
        self.check('hash does not match the current DOCX')

    def test_changed_source_invalidates_docx_source_link(self):
        self.save()
        source = self.run / '_work' / 'review.md'
        source.write_text(source.read_text(encoding='utf-8') + '\nChanged after export.\n', encoding='utf-8')
        self.ledger['host_self_review']['review_sha256'] = rt.file_hash(source)
        self.flush()
        self.check('source hash does not match')

    def test_custom_citation_style_requires_word_mapping(self):
        self.protocol['output_citation_style'] = 'custom'
        self.save()
        self.check('one exact citation map')

    def test_custom_style_with_actual_anchors_passes(self):
        self.prepare_custom_style()
        result = gate.validate_delivery(self.run)
        self.assertEqual(result['status'], 'DELIVERY_CHECKS_PASSED', result)

    def test_custom_claim_link_requires_its_own_marker(self):
        markers, _ = self.prepare_custom_style()
        self.ledger['claims'][0]['links'][1]['word_excerpt'] = self.claim_text + ' ' + markers[0]
        self.flush()
        self.check('R002: Word excerpt does not contain this custom reference marker')

    def test_open_scope_disclosure_must_reach_final_word(self):
        disclosure = 'This is not a real review.'
        self.ledger['issues'] = [{
            'id': 'I001', 'type': 'full_text_unavailable', 'status': 'open',
            'impact': 'scope', 'manuscript_disclosure': disclosure,
        }]
        self.save(body=self.body.replace(disclosure, 'The final file silently omitted the disclosure.'))
        self.check('unresolved scope/core disclosure is missing from final Word')

    def test_open_scope_disclosure_in_source_and_word_passes(self):
        self.ledger['issues'] = [{
            'id': 'I001', 'type': 'full_text_unavailable', 'status': 'open',
            'impact': 'scope', 'manuscript_disclosure': 'This is not a real review.',
        }]
        self.save()
        self.assertEqual(gate.validate_delivery(self.run)['status'], 'DELIVERY_CHECKS_PASSED')

    def test_no_fake_scientific_or_visual_certification(self):
        self.save()
        result = gate.validate_delivery(self.run)
        self.assertFalse(result['scientific_quality_certified'])
        self.assertIn('host-attested', result['scope'])

    def test_zero_editable_text_is_rejected(self):
        self.save()
        self.word(body='', refs='')
        self.check('both manuscript body and references')

    def test_word_title_mismatch_blocked(self):
        self.save(refs=self.refs.replace('Synthetic test reference 030', 'Wrong title'))
        self.check('Word body citation/reference title missing')

    def test_hash_and_count_checks_are_not_bypassed_by_preflight_pass(self):
        self.make_articles(29)
        self.save()
        self.assertEqual(rt.audit_review(self.run)['status'], 'RECORDS_CONSISTENT')
        self.check('found 29')


if __name__ == '__main__':
    unittest.main(verbosity=2)
