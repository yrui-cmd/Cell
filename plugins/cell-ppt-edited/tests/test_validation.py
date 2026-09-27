import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from studio_engine import StudioEngine,EditError,utf16,validate_gradient
from server import dispatch

class Guards(unittest.TestCase):
    def setUp(self):self.e=StudioEngine()
    def bad(self,action,params):
        with self.assertRaises(EditError):self.e._validate_operation({'action':action,'params':params})
    def test_duplicate_group(self):self.bad('group',{'names':['a','a'],'name':'g'})
    def test_empty_group_name(self):self.bad('group',{'names':['a','b'],'name':''})
    def test_invalid_group_flag(self):self.bad('group',{'names':['a','b'],'name':'g','allow_z_order_change':'false'})
    def test_empty_member_name(self):self.bad('group',{'names':['','b'],'name':'g'})
    def test_delete_guard(self):self.bad('delete',{'names':['a'],'confirm':False})
    def test_delete_duplicates(self):self.bad('delete',{'names':['a','a'],'confirm':True})
    def test_nonfinite_geometry(self):self.bad('create',{'name':'x','kind':'shape','left':0,'top':0,'width':float('nan'),'height':1})
    def test_bad_cubic(self):self.bad('create',{'name':'p','kind':'freeform','start':[0,0],'segments':[{'type':'cubic','points':[1,2]}]})
    def test_bad_gradient_order(self):self.bad('gradient',{'targets':['a'],'stops':[{'position':1,'color':'#FFFFFF'},{'position':0,'color':'#000000'}]})
    def test_bad_gradient_opacity(self):self.bad('gradient',{'targets':['a'],'stops':[{'position':0,'color':'#FFFFFF','transparency':2},{'position':1,'color':'#000000'}]})
    def test_bad_node_index(self):self.bad('nodes',{'target':'a','expected_count':5,'edits':[{'op':'move','index':0,'x':1,'y':1}]})
    def test_bad_insert_curve(self):self.bad('nodes',{'target':'a','expected_count':5,'edits':[{'op':'insert','index':1,'segment':'curve','points':[1,2]}]})
    def test_overlap_text(self):self.bad('rich_text',{'target':'t','mode':'replace_ranges','expected_text':'abcd','edits':[{'start':0,'length':3,'runs':[{'text':'x'}]},{'start':2,'length':1,'runs':[{'text':'x'}]}]})
    def test_cross_paragraph_text(self):self.bad('rich_text',{'target':'t','mode':'replace_ranges','expected_text':'a\rb','edits':[{'start':0,'length':2,'runs':[{'text':'x'}]}]})
    def test_text_range_bounds(self):self.bad('rich_text',{'target':'t','mode':'replace_ranges','expected_text':'a','edits':[{'start':1,'length':2,'runs':[{'text':'x'}]}]})
    def test_no_paragraph_breaks_in_run(self):self.bad('rich_text',{'target':'t','mode':'set_paragraphs','expected_text':'a','paragraphs':[{'runs':[{'text':'a\nb'}]}]})
    def test_utf16_nonbmp(self):self.assertEqual(utf16('A🧬中'),4)
    def test_valid_cubic(self):self.e._validate_operation({'action':'create','params':{'name':'p','kind':'freeform','start':[0,0],'segments':[{'type':'cubic','points':[1,2,3,4,5,6]}]}})
    def test_unknown_argument_mcp(self):
        r=dispatch(self.e,{'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'cell_ppt_edited_status','arguments':{'unknown':1}}})
        self.assertTrue(r['result']['isError'])
    def test_unknown_operation(self):self.bad('execute_arbitrary_code',{})

if __name__=='__main__':unittest.main()
