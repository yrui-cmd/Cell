"""Offline HTTP-contract checks. No live uploads or credit spending."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import handoff as h
import transfer
loader=importlib.util.spec_from_file_location('pdf_fixture',Path(__file__).with_name('test_content_pdf.py'))
fixture=importlib.util.module_from_spec(loader);loader.loader.exec_module(fixture)

HEALTH={'ok':True,'version':2,'job_modes':['planned_deck'],
        'planned_upload':{'files':['material'],'format':'pdf','billing':'declared_ppt_content_pages'}}

class FakeClient(transfer.Client):
    def __init__(self,bundle):
        super().__init__(None,'synthetic');self.bundle=bundle;self.calls=[];self.mismatch=False
    def call(self,method,route,**payload):
        self.calls.append((method,route,payload))
        if route=='/health':return HEALTH
        if route=='/balance':return {'available_pages':100}
        if route=='/uploads':
            assert set(payload['files'])=={'material'}
            assert payload['files']['material'][2]=='application/pdf'
            assert payload['files']['material'][1].read(4)==b'%PDF'
        n=self.bundle['credits']+(1 if self.mismatch else 0)
        return {'job_id':'a'*32,'mode':'planned_deck','page_count':n,
                'price':{'amount':n,'unit':'ppt_page_credit'},
                'files':{'material':{'sha256':self.bundle['sha256']['material']}},
                'status':'queued' if route.endswith('/confirm') else 'quoted',
                'billing':'settled' if route.endswith('/confirm') else 'unsettled'}

class PdfTransportTests(unittest.TestCase):
    def approval(self,b):
        return {'approved':True,'sha256':b['sha256'],'credits':b['credits'],
                'thread_id':'synthetic-thread','customer_confirmation':'确认此 PDF 和额度'}
    def test_only_pdf_required_and_uploaded(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'handoff';b=h.build(fixture.task(),root)
            (root/h.PLAN).unlink()
            b=h.inspect(root)
            self.assertEqual(set(b['sha256']),{'material'})
            with fitz.open(root/h.MATERIAL) as pdf:
                self.assertGreater(len(pdf),b['credits'])
                self.assertEqual(json.loads(pdf.embfile_get(h.TRANSPORT_INDEX))['page_count'],2)
            c=FakeClient(b);state=c.submit(root,self.approval(b))
            self.assertEqual(state['billing'],'settled')
            self.assertEqual([x for x in c.calls if x[1].endswith('/confirm')][0][2]['json'],{'expected_page_credits':2})
    def test_bad_quote_never_confirms(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'handoff';b=h.build(fixture.task(),root);c=FakeClient(b);c.mismatch=True
            with self.assertRaises(ValueError):c.submit(root,self.approval(b))
            self.assertFalse(any(r.endswith('/confirm') for _,r,_ in c.calls))
    def test_changed_pdf_requires_new_approval(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'handoff';b=h.build(fixture.task(),root);approval=self.approval(b)
            with fitz.open(root/h.MATERIAL) as pdf:
                pdf.set_metadata({'subject':'new version'});pdf.saveIncr()
            c=FakeClient(h.inspect(root))
            with self.assertRaises(ValueError):c.submit(root,approval)
            self.assertEqual(c.calls,[])
    def test_conflicting_index_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'handoff';h.build(fixture.task(),root)
            with fitz.open(root/h.MATERIAL) as pdf:
                index=json.loads(pdf.embfile_get(h.TRANSPORT_INDEX));index['page_count']=99
                pdf.embfile_del(h.TRANSPORT_INDEX);pdf.embfile_add(h.TRANSPORT_INDEX,json.dumps(index).encode());pdf.saveIncr()
            with self.assertRaises(ValueError):h.inspect(root)
    def test_legacy_receipt_can_be_checked_but_not_newly_uploaded(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'handoff';h.build(fixture.task(),root)
            with fitz.open(root/h.MATERIAL) as pdf:
                pdf.embfile_del(h.TRANSPORT_INDEX);pdf.saveIncr()
            b=h.inspect(root);self.assertEqual(b['upload_format'],'legacy_pptx_pdf')
            self.assertIn('pptx',b['sha256'])
            quote={'mode':'planned_deck','page_count':b['credits'],'price':{'amount':b['credits'],'unit':'ppt_page_credit'},
                   'files':{k:{'sha256':v,**({'page_count':2} if k=='pptx' else {})} for k,v in b['sha256'].items()}}
            transfer.Client(None,'synthetic').verify_quote(quote,b)
            c=FakeClient(b)
            with self.assertRaises(ValueError):c.submit(root,self.approval(b))
            self.assertEqual(c.calls,[])

if __name__=='__main__':unittest.main()
