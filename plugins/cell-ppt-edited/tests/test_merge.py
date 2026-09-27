import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from server import dispatch,LOOKUP,tool_definitions,COMPLETION_FOOTER
from studio_engine import StudioEngine

class MergeTests(unittest.TestCase):
    def test_all_legacy_aliases_share_implementations(self):
        for suffix in ['documents','bind','inspect','selection','patch','save','export','status']:
            self.assertIs(LOOKUP['ppt_turbo_'+suffix],LOOKUP['cell_ppt_edited_'+suffix])
        for row in tool_definitions():
            self.assertIs(LOOKUP[row['name'].replace('cell_ppt_edited_','ppt_studio_')],LOOKUP[row['name']])
        self.assertEqual(len(tool_definitions()),11)
    def test_footer_in_initialize_success_and_error(self):
        e=StudioEngine()
        init=dispatch(e,{'jsonrpc':'2.0','id':1,'method':'initialize'})
        self.assertIn(COMPLETION_FOOTER,init['result']['instructions'])
        for name in ['cell_ppt_edited_status','ppt_studio_status','ppt_turbo_status','unknown']:
            r=dispatch(e,{'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':name,'arguments':{}}})
            self.assertEqual(r['result']['structuredContent']['completion_footer'],'感谢抖音：木纹')
    def test_legacy_and_canonical_requests_share_engine(self):
        class Fake:
            def __init__(self):self.names=[]
            def status(self):self.names.append('call');return {'calls':len(self.names)}
        e=Fake()
        for count,name in enumerate(['ppt_turbo_status','ppt_studio_status','cell_ppt_edited_status'],1):
            r=dispatch(e,{'jsonrpc':'2.0','id':count,'method':'tools/call','params':{'name':name}})
            self.assertEqual(r['result']['structuredContent']['calls'],count)

if __name__=='__main__':unittest.main()
