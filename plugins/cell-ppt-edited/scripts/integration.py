"""Live PowerPoint/MCP acceptance tests on a new, disposable presentation."""
import json
from pathlib import Path
import sys
import time
import uuid
import zipfile
import xml.etree.ElementTree as ET
from client import Client
from studio_engine import StudioEngine

def main():
    out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False)
    engine=StudioEngine();app=engine.app(create=True)
    original=app.ActiveWindow if app.Windows.Count else None
    doc=app.Presentations.Add();doc.PageSetup.SlideWidth=960;doc.PageSetup.SlideHeight=540
    slide=doc.Slides.Add(1,12)
    sentinel=slide.Shapes.AddShape(1,850,470,60,30);sentinel.Name="untouched";sentinel.Fill.ForeColor.RGB=0x332211
    doc.SaveAs(str(out/'acceptance.pptx'),24)
    # Optional second argument tests the exact packaged executable.
    command=[str(Path(sys.argv[2]).resolve())] if len(sys.argv)>2 else [sys.executable,'-u',str(Path(__file__).with_name('server.py'))]
    client=Client(command)
    checks=[];timings=[]
    def check(name,condition):
        assert condition,name
        checks.append(name);print('PASS '+name,flush=True)
    try:
        sid=client.call('ppt_turbo_bind',{'path':str(out/'acceptance.pptx'),'mode':'in_place'})['session_id']
        base={'session_id':sid,'slide_index':1}
        def edit(ops,**kw):
            started=time.perf_counter()
            result=client.call('cell_ppt_edited_edit',{**base,'operations':ops,'request_id':uuid.uuid4().hex,**kw})
            assert result['status']=='applied',result
            timings.append({'actions':[o['action'] for o in ops],'roundtrip_ms':round((time.perf_counter()-started)*1000,3),'server_ms':result['server_ms']})
            return result
        def inspect(name,*details):return client.call('cell_ppt_edited_inspect_object',{**base,'target':name,'details':list(details)})
        def op(action,**params):return {'action':action,'params':params}
        check('11 MCP tools and capability contracts',len(client.request('tools/list')['tools'])==11 and len(client.call('cell_ppt_edited_capabilities')['actions'])==7)
        creates=[op('create',name=f'cell{i}',kind='shape',shape_type='ellipse',left=50+i*130,top=50,width=100,height=80,fill_color='#7030A0',line_width=0) for i in range(5)]
        r=edit(creates)
        check('batch create five native objects',r['shape_count']==6)
        basic=client.call('ppt_turbo_patch',{**base,'patches':[{'name':'cell0','set':{'fill_color':'#FFD966','left':55,'line_color':'#334455','line_width':2}}],'request_id':uuid.uuid4().hex})
        check('legacy basic edits share the advanced session',basic['status']=='applied' and inspect('cell0')['shape']['left']==55)
        check('completion footer returned verbatim',basic['completion_footer']=='感谢抖音：木纹')
        client.call('ppt_studio_patch',{**base,'patches':[{'name':'cell0','set':{'fill_color':'#7030A0','left':50,'line_width':0}}],'request_id':uuid.uuid4().hex})
        check('both legacy tool sets use same document',inspect('cell0')['shape']['left']==50)
        ids={f'cell{i}':slide.Shapes.Item(f'cell{i}').Id for i in range(5)}
        edit([op('group',names=['cell0','cell1','cell2'],name='group1')])
        check('group is editable native group',slide.Shapes.Item('group1').Type==6 and slide.Shapes.Item('group1').GroupItems.Count==3)
        check('inspect grouped child by path',inspect({'path':['group1','cell1']})['shape']['id']==ids['cell1'])
        edit([op('ungroup',target='group1')])
        check('ungroup preserves object IDs and geometry',all(slide.Shapes.Item(n).Id==i for n,i in ids.items()) and abs(slide.Shapes.Item('cell1').Left-180)<0.01)
        args={**base,'operations':[op('delete',names=['cell3','cell4'],confirm=True)],'request_id':uuid.uuid4().hex}
        r=client.call('cell_ppt_edited_edit',args);again=client.call('cell_ppt_edited_edit',args)
        check('delete and idempotent replay',r['shape_count']==4 and again['replayed'] and slide.Shapes.Count==4)
        bad=client.call('cell_ppt_edited_edit',{**base,'operations':[op('create',name='should_not_exist',kind='shape',left=0,top=0,width=20,height=20),op('delete',names=['missing'],confirm=True)],'request_id':uuid.uuid4().hex},allow_error=True)
        check('whole-batch preflight prevents preceding create',bool(bad.get('error')) and slide.Shapes.Count==4)
        stops=[{'position':0,'color':'#FFF2CC'},{'position':0.4,'color':'#A65BC4','transparency':0.2},{'position':1,'color':'#512173'}]
        for name,kind in [('cell0','linear'),('cell1','radial'),('cell2','corner')]:
            edit([op('gradient',targets=[name],kind=kind,angle=35,stops=stops)])
            g=inspect(name,'gradient')['gradient']
            check(kind+' native multi-stop gradient',len(g['stops'])==3 and g['stops'][1]['color']=='#A65BC4')
        edit([op('create',name='curve',kind='freeform',start=[60,280],segments=[{'type':'cubic','points':[100,180,210,350,260,250]},{'type':'line','points':[310,290]}],line_color='#7030A0',line_width=4)])
        n=inspect('curve','nodes')['path_nodes'];check('native cubic path with control handles',n['count']==5)
        edit([op('nodes',target='curve',expected_count=n['count'],expected_hash=n['hash'],edits=[{'op':'move','index':2,'x':110,'y':190}])])
        n2=inspect('curve','nodes')['path_nodes'];check('move Bezier handle',n2['nodes'][1]['points'][0]==[110.0,190.0])
        bad=client.call('cell_ppt_edited_edit',{**base,'operations':[op('nodes',target='curve',expected_count=n['count'],expected_hash=n['hash'],edits=[{'op':'move','index':2,'x':1,'y':1}])],'request_id':uuid.uuid4().hex},allow_error=True)
        check('stale path hash rejected',bool(bad.get('error')) and inspect('curve','nodes')['path_nodes']['hash']==n2['hash'])
        edit([op('nodes',target='curve',expected_count=5,edits=[{'op':'insert','index':5,'segment':'line','points':[340,250]}])])
        check('insert native path node',inspect('curve','nodes')['path_nodes']['count']==6)
        edit([op('nodes',target='curve',expected_count=6,edits=[{'op':'delete','index':6}])])
        check('delete native path node',inspect('curve','nodes')['path_nodes']['count']==5)
        edit([op('nodes',target='curve',expected_count=5,edits=[{'op':'editing','index':4,'editing':'corner'}])])
        check('set native node editing mode',inspect('curve','nodes')['path_nodes']['nodes'][3]['editing_type']==1)
        edit([op('create',name='convert_path',kind='freeform',start=[400,230],segments=[{'type':'line','points':[460,260]},{'type':'line','points':[520,230]}],line_color='#3388AA',line_width=3)])
        edit([op('nodes',target='convert_path',expected_count=3,edits=[{'op':'segment','index':2,'segment':'curve'}])])
        check('line converted to cubic segment',inspect('convert_path','nodes')['path_nodes']['count']>3)
        edit([op('create',name='label',kind='textbox',left=50,top=350,width=790,height=100,text='A🧬中H2O — marker',font={'name':'Arial','name_far_east':'Microsoft YaHei','size':24,'color':'#334455'})])
        edit([op('rich_text',target='label',mode='replace_ranges',expected_text='A🧬中H2O — marker',edits=[{'start':4,'length':1,'runs':[{'text':'2','font':{'baseline':-0.25,'color':'#7030A0'}}]},{'start':9,'length':6,'runs':[{'text':'阳性','font':{'bold':True}},{'text':' RNA','font':{'italic':True,'color':'#007799'}}]}])])
        rich=inspect('label','rich_text')['rich_text']
        check('Unicode rich replacement after emoji',rich['text']=='A🧬中H2O — 阳性 RNA')
        tr=slide.Shapes.Item('label').TextFrame.TextRange
        check('subscript and untouched prefix preserved',abs(tr.Characters(6,1).Font.BaselineOffset+0.25)<0.001 and tr.Characters(1,1).Font.Color.RGB==0x554433)
        edit([op('rich_text',target='label',mode='set_paragraphs',expected_text=rich['text'],paragraphs=[{'runs':[{'text':'H','font':{'size':26,'baseline':0}},{'text':'2','font':{'baseline':-0.25}},{'text':'O  ·  Ca','font':{'baseline':0}},{'text':'2+','font':{'baseline':0.3,'color':'#7030A0'}},{'text':'  🧬 DNA','font':{'baseline':0,'italic':True}}],'alignment':'left','bullet':False},{'runs':[{'text':'中文 / English  ','font':{'name':'Arial','name_far_east':'Microsoft YaHei','baseline':0,'italic':False}},{'text':'link','font':{'hyperlink':'https://example.com','underline':True}}],'bullet':True,'space_before':8,'level':1}])])
        rich=inspect('label','rich_text')['rich_text']
        check('mixed paragraphs and bullet formatting',len(rich['paragraphs'])==2 and rich['paragraphs'][1]['bullet'])
        check('hyperlink retained as native text formatting',any(r['font']['hyperlink'].rstrip('/')=='https://example.com' for r in rich['runs']))
        old=rich['text']
        edit([op('rich_text',target='label',mode='replace_ranges',expected_text=old,edits=[{'start':len(old),'length':0,'runs':[{'text':' ✓','font':{'hyperlink':''}}]}])])
        check('zero-length append range',inspect('label','rich_text')['rich_text']['text']==old+' ✓')
        edit([op('create',name='transient',kind='line',x1=1,y1=1,x2=20,y2=20),op('delete',names=['transient'],confirm=True)],checkpoint_path=str(out/'checkpoint.pptx'),save=True)
        check('checkpoint and save', (out/'checkpoint.pptx').exists())
        check('untargeted sentinel unchanged',sentinel.Name=='untouched' and sentinel.Fill.ForeColor.RGB==0x332211 and sentinel.Left==850)
        client.call('cell_ppt_edited_export',{**base,'output_path':str(out/'acceptance.png'),'width':1440})
        with zipfile.ZipFile(out/'acceptance.pptx') as z:
            xml=z.read('ppt/slides/slide1.xml');root=ET.fromstring(xml)
        ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main'}
        check('saved OOXML keeps gradients curves and text native',len(root.findall('.//a:gradFill',ns))>=3 and len(root.findall('.//a:cubicBezTo',ns))>=2 and len(root.findall('.//a:r',ns))>=6 and not root.findall('.//p:pic',ns))
        (out/'acceptance.json').write_text(json.dumps({'passed':len(checks),'checks':checks,'timings':timings,'artifact':str(out/'acceptance.pptx')},ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'passed':len(checks),'output':str(out)},ensure_ascii=False))
    finally:
        client.close()
        if original:
            try:original.Activate()
            except Exception:pass
        engine.shutdown()

if __name__=='__main__':main()
