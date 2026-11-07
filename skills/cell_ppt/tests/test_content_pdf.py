"""End-to-end checks for the ordered planning PDF."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import fitz
from pptx import Presentation
from pypdf import PdfReader

loader = importlib.util.spec_from_file_location('content_handoff', Path(__file__).resolve().parents[1]/'scripts/handoff.py')
h = importlib.util.module_from_spec(loader)
loader.loader.exec_module(h)

def task():
    return {'questions_locked':True,
        'questions':[{'field':k,'asked':True,'question':f'请确认 {k}？','answer':'采用推荐','state':'confirmed','response_source':'用户回复：采用推荐'} for k in sorted(h.REQUIRED_QUESTIONS)],
        'design':{'style':'清晰学术','language':'中文','aspect_ratio':'16:9','palette':'深蓝、白色','page_count':2},
        'template_notes':'无模板；按蓝白学术风格排版',
        'timing':{'total':120,'talk':120,'qa':0,'includes_qa':False},'sources':[],
        'original_request':'示例资料，供离线检查使用。',
        'pages':[{'kind':'content','title':f'测试标题 {n}','story':'说明主要观点','evidence':'用户提供的示例资料','visual':'使用用户原图，不生图',
                  'content':f'第 {n} 页真实上屏正文。','layout':'左侧原图占 60%，右侧要点占 40%；统一蓝白配色。',
                  'notes':'这是制作注释，不应作为正文上屏。','seconds':60} for n in (1,2)]}

class ContentPdfTests(unittest.TestCase):
    def test_visible_roles_story_and_source_locations(self):
        spec=task()
        roles=['cover','overview','content','chapter','thanks']
        spec['pages']=[dict(spec['pages'][0], page_role=role,
                           story_guide='问题：谁支持生长？\n观察：原图结果。\n结论：有功能贡献。\n转场：机制是什么？',
                           source_locator='R1，原PDF第4页，Fig.2h–i；共培养实验。') for role in roles]
        spec['design']['page_count']=len(roles)
        spec['timing'].update(total=300,talk=300)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'bundle'
            result=h.build(spec,root)
            deck=Presentation(root/h.PLAN)
            with fitz.open(root/h.MATERIAL) as pdf:
                for role,slide,record in zip(roles,deck.slides,result['index']['content_pages']):
                    visible='\n'.join(shape.text for shape in slide.shapes if shape.has_text_frame)
                    self.assertIn(h.ROLE_LABELS[role],visible)
                    self.assertIn('问题：谁支持生长？',visible)
                    self.assertIn('Fig.2h–i',visible)
                    self.assertIn(h.ROLE_LABELS[role],pdf[record['first']-1].get_text())

    def test_own_figures_are_visible_preserved_and_do_not_add_credits(self):
        spec=task()
        with tempfile.TemporaryDirectory() as directory:
            d=Path(directory)
            with fitz.open() as source:
                page=source.new_page(width=160,height=100)
                page.draw_rect(fitz.Rect(10,10,150,90),color=(0,0,1),fill=(0,0,1))
                page.get_pixmap().save(d/'own.png')
            spec['pages'][0]['assets']=[{'path':str(d/'own.png'),'caption':'U1 自有实验图，支持第一页观察','source_id':'U1'}]
            spec['pages'][0]['story_guide']='详细故事\n'*80+'完整故事结束标记'
            result=h.build(spec,d/'bundle')
            self.assertEqual(result['credits'],2)
            self.assertEqual(len(Presentation(d/'bundle'/h.PLAN).slides),2)
            record=result['index']['content_pages'][0]
            with fitz.open(d/'bundle'/h.MATERIAL) as pdf:
                self.assertGreater(record['last'],record['first'])
                self.assertTrue(pdf[record['last']-1].get_images())
                self.assertEqual(pdf.embfile_get(record['assets'][0]['attachment']),(d/'own.png').read_bytes())
                self.assertIn('完整故事结束标记',''.join(p.get_text() for p in pdf))

    def test_default_parameters_do_not_require_or_fabricate_questions(self):
        spec=task()
        spec['intake']={'mode':'default','response_source':'选择默认'}
        spec['questions']=[{'field':item['field'],'asked':False,'state':'defaulted','answer':'按本次资料拟定'}
                           for item in spec['questions']]
        spec['questions'][0].update(state='provided',answer='16:9',response_source='用户原始要求')
        with tempfile.TemporaryDirectory() as directory:
            bundle=Path(directory)/'bundle'
            h.build(spec,bundle)
            with fitz.open(bundle/h.MATERIAL) as doc:
                text=doc[0].get_text()
                self.assertIn('参数模式：默认',text)
                self.assertIn('客户已提供',text)
                self.assertIn('按默认拟定',text)
                self.assertNotIn('答复出处',text)
            self.assertEqual(h.inspect(bundle)['credits'],2)
        del spec['intake']['response_source']
        with self.assertRaisesRegex(ValueError,'选择'):
            h.validate_spec(spec)
        spec['intake']={'mode':'personalized','response_source':'选择个性化'}
        with self.assertRaisesRegex(ValueError,'实际提问'):
            h.validate_spec(spec)

    def test_first_line_count_must_match_and_old_heading_remains_readable(self):
        original_wrap = h.wrap
        for heading, accepted in [('PPT 总页数：3 页', False),
                                   ('说明\nPPT 总页数：2 页', False),
                                   ('PPT内容共 2 页', True)]:
            def replace_title(lines):
                return original_wrap([heading if line == 'PPT 总页数：2 页' else line for line in lines])
            with self.subTest(heading=heading), tempfile.TemporaryDirectory() as d:
                with patch.object(h, 'wrap', side_effect=replace_title):
                    if accepted:
                        self.assertEqual(h.build(task(), Path(d)/'bundle')['plan_pages'], 2)
                    else:
                        with self.assertRaisesRegex(ValueError, '第一行'):
                            h.build(task(), Path(d)/'bundle')

    def test_sections_long_content_and_no_template(self):
        spec=task();spec['pages'][0]['content']='长正文用于验证自动续页。\n'*100+'正文末尾唯一标记'
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'bundle';r=h.build(spec,root)
            self.assertEqual(r['credits'],2)
            # The server uses pypdf, whose CJK extraction differs from PyMuPDF.
            self.assertEqual(PdfReader(root/h.MATERIAL).pages[0].extract_text().splitlines()[0],
                             'PPT 总页数：2 页')
            with fitz.open(root/h.MATERIAL) as doc:
                sections=r['index']['sections']
                self.assertEqual([x[1] for x in doc.get_toc() if x[0]==1],['问答','模板','资料','PPT内容'])
                self.assertEqual('PPT 总页数：2 页',doc[0].get_text().splitlines()[0])
                self.assertIn('模板：无模板',doc[0].get_text())
                records=r['index']['content_pages']
                self.assertGreater(records[0]['last'],records[0]['first'])
                text=''.join(p.get_text() for p in doc)
                for value in ['正文末尾唯一标记','排版：','注释（供制作参考，不直接上屏）：','# 第 2 页：']:
                    self.assertIn(value,text)
                for p in doc:
                    for b in p.get_text('blocks'):
                        self.assertLessEqual(b[2],p.rect.width)
                        self.assertLessEqual(b[3],p.rect.height)
            self.assertTrue((root/'outline.json').exists())

    def test_template_preview_and_original_material_are_embedded_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);spec=task();ppt=Presentation();ppt.slides.add_slide(ppt.slide_layouts[6]);ppt.save(d/'template.pptx')
            with fitz.open() as doc:
                doc.new_page().insert_text((60,60),'TEMPLATE PREVIEW');doc.save(d/'template.pdf')
            with fitz.open() as doc:
                doc.new_page().insert_text((60,60),'ORIGINAL MATERIAL');doc.save(d/'source.pdf')
            spec['template_notes']='模板：测试模板一号';spec['template_id']='test-1'
            spec['template']={'path':str(d/'template.pptx'),'readable_pdf':str(d/'template.pdf'),'rendered_from_sha256':h.sha(d/'template.pptx'),
                              'picks':[{'page':1,'kind':'content','style':'example'}]}
            spec['sources']=[{'title':'原始资料','path':str(d/'source.pdf')}]
            r=h.build(spec,d/'bundle')
            self.assertEqual(r['credits'],2)
            with fitz.open(d/'bundle'/h.MATERIAL) as doc:
                s=r['index']['sections']
                self.assertIn('TEMPLATE PREVIEW',doc[s[1]['last']-1].get_text())
                self.assertIn('ORIGINAL MATERIAL',doc[s[2]['first']-1].get_text())
                self.assertTrue(doc[s[3]['first']-1].get_text().startswith('# 第 1 页'))
            spec['template']['rendered_from_sha256']='outdated'
            with self.assertRaises(ValueError):h.build(spec,d/'rejected')

    def test_wrong_total_or_missing_content_layout_notes_rejected(self):
        for field in ['content','layout','notes']:
            spec=task();spec['pages'][0][field]=''
            with self.subTest(field=field),self.assertRaises(ValueError):h.validate_spec(spec)
        spec=task();spec['design']['page_count']=3
        with self.assertRaises(ValueError):h.validate_spec(spec)

if __name__=='__main__':unittest.main()
