"""Reproducible, test-only comparison with the installed competitor, never a runtime dependency."""
import argparse, hashlib, json, statistics, sys, time, uuid
from pathlib import Path
from client import Client
from studio_engine import StudioEngine

def main():
    p=argparse.ArgumentParser();p.add_argument('--competitor',required=True);p.add_argument('--output',required=True);p.add_argument('--trials',type=int,default=3);args=p.parse_args()
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False)
    competitor=Path(args.competitor);engine=StudioEngine();app=engine.app(create=True)
    original=app.ActiveWindow if app.Windows.Count else None
    source=app.Presentations.Add();source.PageSetup.SlideWidth=960;source.PageSetup.SlideHeight=540
    slide=source.Slides.Add(1,12);s=slide.Shapes.AddShape(1,800,450,30,30);s.Name='sentinel';s.Fill.ForeColor.RGB=0x332211
    source.SaveAs(str(out/'fixture.pptx'),24)
    source_hash=hashlib.sha256((out/'fixture.pptx').read_bytes()).hexdigest()
    decks={};clients={};rows=[]
    report={'trials_per_case':args.trials,'protocol':'Same native 960x540 fixture, 5 objects, exact named targets, persistent MCP stdio, one untimed warmup, alternating engine order. Baseline fast pacing, zero pause. Timed edit and edit+save+1200px PowerPoint PNG export including inline image. No deliberate delays. Setup/bind/agent reasoning excluded. Each operation read back through native COM; matching A/B rendered pixels verified.','competitor_version':json.loads((competitor/'.codex-plugin/plugin.json').read_text(encoding='utf-8-sig'))['version'],'competitor_server_sha256':hashlib.sha256((competitor/'scripts/powerpoint-server.mjs').read_bytes()).hexdigest(),'rows':rows}
    try:
        for kind in ['studio','scientific_illustrator']:
            b=engine.bind(str(out/'fixture.pptx'),'copy',str(out/f'{kind}.pptx'));decks[kind]=engine.sessions[b['session_id']]['doc']
            cmd=[sys.executable,'-u',str(Path(__file__).with_name('server.py'))] if kind=='studio' else ['node',str(competitor/'scripts/powerpoint-server.mjs')]
            clients[kind]=Client(cmd,cwd=str(Path(__file__).resolve().parents[1] if kind=='studio' else competitor),stderr_path=out/f'{kind}.stderr.txt')
        sid=clients['studio'].call('cell_ppt_edited_bind',{'path':str(out/'studio.pptx'),'mode':'in_place'})['session_id'];base={'session_id':sid,'slide_index':1}
        decks['scientific_illustrator'].Windows.Item(1).Activate()
        status=clients['scientific_illustrator'].call('powerpoint_status')
        assert Path(status['presentation']['presentation_path']).resolve()==out/'scientific_illustrator.pptx'
        for trial in range(-1,args.trials):
            names=[f'trial{trial}_shape{i}' for i in range(5)];group=f'trial{trial}_group'
            for case in ['create_five','group_five','ungroup_five','delete_five']:
                for kind in (['studio','scientific_illustrator'] if trial%2 else ['scientific_illustrator','studio']):
                    deck=decks[kind];deck.Windows.Item(1).Activate();c=clients[kind]
                    t=time.perf_counter()
                    if kind=='studio':
                        if case=='create_five':ops=[{'action':'create','params':{'name':n,'kind':'shape','shape_type':'rectangle','left':50+i*130,'top':100,'width':100,'height':100,'fill_color':'#7030A0','line_color':'#223344','line_width':1}} for i,n in enumerate(names)]
                        elif case=='group_five':ops=[{'action':'group','params':{'names':names,'name':group}}]
                        elif case=='ungroup_five':ops=[{'action':'ungroup','params':{'target':group}}]
                        else:ops=[{'action':'delete','params':{'names':names,'confirm':True}}]
                        c.call('cell_ppt_edited_edit',{**base,'operations':ops,'request_id':uuid.uuid4().hex})
                    else:
                        if case=='create_five':
                            c.call('powerpoint_draw_sequence',{'operations':[{'type':'add_shape','slide_index':1,'name':n,'shape':'rectangle','left':50+i*130,'top':100,'width':100,'height':100,'fill_color':'#7030A0','line_color':'#223344','line_width':1} for i,n in enumerate(names)],'pacing_mode':'fast','step_delay_ms':0})
                        elif case=='group_five':c.call('powerpoint_group_shapes',{'slide_index':1,'shape_names':names,'name':group,'pause_after_ms':0})
                        elif case=='ungroup_five':c.call('powerpoint_ungroup_shape',{'slide_index':1,'shape_name':group,'pause_after_ms':0})
                        else:
                            for n in names:c.call('powerpoint_delete_shape',{'slide_index':1,'shape_name':n,'confirm':True,'pause_after_ms':0})
                    edit_ms=(time.perf_counter()-t)*1000
                    if kind=='studio':
                        c.call('cell_ppt_edited_save',{'session_id':sid});c.call('cell_ppt_edited_export',{**base,'output_path':str(out/f'{kind}.png'),'width':1200,'overwrite':True,'include_image':True})
                    else:
                        c.call('powerpoint_save');c.call('powerpoint_export_slide_image',{'slide_index':1,'output_path':str(out/f'{kind}.png'),'width':1200,'overwrite':True})
                    total_ms=(time.perf_counter()-t)*1000
                    shapes=deck.Slides(1).Shapes
                    assert shapes.Count==({'group_five':2,'delete_five':1}.get(case,6))
                    if case=='group_five':assert shapes.Item(group).GroupItems.Count==5
                    if case in ['create_five','ungroup_five']:
                        for i,n in enumerate(names):
                            item=shapes.Item(n);assert abs(item.Left-(50+i*130))<.01 and abs(item.Width-100)<.01 and item.Fill.ForeColor.RGB==0xA03070
                    assert shapes.Item('sentinel').Fill.ForeColor.RGB==0x332211
                    row={'trial':trial+1,'case':case,'engine':kind,'edit_ms':round(edit_ms,3),'total_ms':round(total_ms,3),'native_verified':True}
                    if trial>=0:rows.append(row)
                    print(json.dumps(row),flush=True)
                    (out/'partial.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
                from PIL import Image,ImageChops
                diff=ImageChops.difference(Image.open(out/'studio.png').convert('RGB'),Image.open(out/'scientific_illustrator.png').convert('RGB'))
                assert diff.getbbox() is None,case+' different A/B pixels'
        report['summary']={}
        for case in ['create_five','group_five','ungroup_five','delete_five']:
            a=[r['total_ms'] for r in rows if r['case']==case and r['engine']=='scientific_illustrator'];b=[r['total_ms'] for r in rows if r['case']==case and r['engine']=='studio']
            report['summary'][case]={'baseline_median_ms':round(statistics.median(a),3),'studio_median_ms':round(statistics.median(b),3),'median_speedup':round(statistics.median(a)/statistics.median(b),2),'conservative_min_baseline_over_max_studio':round(min(a)/max(b),2),'at_least_2x':min(a)/max(b)>=2}
        report['pixel_equivalence']=True;report['source_unchanged']=hashlib.sha256((out/'fixture.pptx').read_bytes()).hexdigest()==source_hash
        report['all_shared_cases_at_least_2x']=all(v['at_least_2x'] for v in report['summary'].values())
        report['unsupported_comparisons']='The competitor exposes no equivalent native path-node, multistop gradient, or per-range rich-text operation; those features have independent functional tests, no fabricated SI speed ratio.'
        (out/'benchmark.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report['summary'],indent=2),flush=True)
        assert report['all_shared_cases_at_least_2x']
    finally:
        for c in clients.values():c.close()
        if original:
            try:original.Activate()
            except Exception:pass
        engine.shutdown()

if __name__=='__main__':main()
