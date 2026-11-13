from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile
from lxml import etree
from pptx import Presentation
from pptx.util import Inches, Pt

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import playback


class PlaybackOrderTests(unittest.TestCase):
    def test_windows_and_mac_use_visual_rows_preserve_layers_and_groups(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pres = Presentation()
            slide = pres.slides.add_slide(pres.slide_layouts[6])
            def box(x, y, label):
                s = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(1), Inches(.4))
                s.text = label
                return s
            bottom_right = box(6, 3, 'bottom right')
            top_right = box(6, 1, 'top right')
            group = slide.shapes.add_group_shape()
            group.shapes.add_textbox(Inches(1), Inches(3), Inches(1), Inches(.4)).text = 'group child'
            # Left element is 2pt lower, but remains on the same visual row.
            top_left = box(1, 1 + 2/72, 'top left')
            hidden = box(0, 0, 'hidden')
            hidden._element[0].find(playback.p('cNvPr')).set('hidden', '1')
            source = root / 'source.pptx'
            pres.save(source)
            original_bytes = source.read_bytes()
            expected = [top_left.shape_id, top_right.shape_id, group.shape_id, bottom_right.shape_id]
            windows = playback.prepare(source, root / 'windows.pptx')
            mac = playback.prepare(source, root / 'mac.pptx', macos=True)
            self.assertEqual(list(windows.values())[0], expected)
            self.assertEqual([int(item['name'].split('_')[-1]) for item in mac['1']], expected)
            self.assertEqual(source.read_bytes(), original_bytes)
            for name in ['windows.pptx', 'mac.pptx']:
                with ZipFile(root / name) as z:
                    xml = etree.fromstring(z.read('ppt/slides/slide1.xml'))
                    tree = xml.find(f"{playback.p('cSld')}/{playback.p('spTree')}")
                    actual_ids = [int(el[0].find(playback.p('cNvPr')).get('id')) for el in tree
                                  if etree.QName(el).localname in playback.SHAPES]
                    self.assertEqual(actual_ids, [s.shape_id for s in slide.shapes])
                    self.assertEqual(len(xml.findall('.//' + playback.p('grpSp'))), 1)

    def test_mac_compatibility_delay(self):
        scripts = Path(playback.__file__).parent
        mac = (scripts / 'run_element_playback.applescript').read_text(encoding='utf-8')
        self.assertIn('delay 0.2\n            if pendingItems', mac)
        self.assertNotIn('delay 0.5', mac)


if __name__ == '__main__':
    unittest.main()
