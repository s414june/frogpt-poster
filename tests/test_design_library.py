import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw
from gpt_package.design_library import load_design_references, design_catalog, join_credit_labels
from gpt_package.typography import TypographyEngine
from gpt_package.openai_tool import handle_tool_call
from gpt_package.errors import ValidationError


class DesignLibraryTests(unittest.TestCase):
    def setup_library(self, root):
        for category in ('attributed', 'original'):
            folder = root / category
            folder.mkdir()
            Image.new('RGB', (30, 40), 'red').save(folder / 'design.png')
            (folder / 'manifest.json').write_text(json.dumps({'items': [
                {'id': 'one', 'file': 'design.png', 'author': 'Designer', 'credit_label': 'Designer/Studio'}
            ]}))

    def test_categories_reload_and_preview(self):
        with tempfile.TemporaryDirectory() as temp, patch('gpt_package.design_library.DESIGN_LIBRARY_ROOT', Path(temp)):
            root = Path(temp)
            self.setup_library(root)
            items = load_design_references()
            self.assertEqual([i['credit_required'] for i in items], [True, False])
            self.assertEqual(items[1]['credit_label'], '')
            self.assertTrue(design_catalog()[0]['preview_data_url'].startswith('data:image/jpeg;base64,'))
            (root/'original/manifest.json').write_text('{"items": []}')
            self.assertIn("original/design", [item["id"] for item in load_design_references()])

    def test_original_images_are_discovered_by_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.setup_library(root)
            Image.new('RGB', (10, 10)).save(root/'original/new.png')
            self.assertIn('original/new', [item['id'] for item in load_design_references(root)])
            Image.new('RGB', (10, 10)).save(root/'attributed/missing.png')
            with self.assertRaises(ValidationError): load_design_references(root)

    def test_untrusted_paths_and_missing_authors_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.setup_library(root)
            for entry in ({'id':'bad','file':'../outside.png','author':'A'},
                          {'id':'bad','file':'design.png','author':'Unknown'}):
                (root/'attributed/manifest.json').write_text(json.dumps({'items':[entry]}))
                with self.assertRaises(ValidationError): load_design_references(root)

    def test_photo_and_design_credits_share_one_row(self):
        with tempfile.TemporaryDirectory() as temp, patch('gpt_package.design_library.DESIGN_LIBRARY_ROOT', Path(temp)), patch.dict('os.environ', {'POSTER_OUTPUT_DIR': temp}):
            self.setup_library(Path(temp))
            result = handle_tool_call({'title':'Pure','body':'Daily', 'width':480,'height':640,
                'poster_request':{'reference_library_id':'pexels-167699',
                    'design_reference_ids':['attributed/one','original/one','attributed/one']}})
            self.assertTrue(result['rendered'],result)
            self.assertEqual(result['source_credit_overlay_text'], 'Lum3n/Pexels · Designer/Studio')
            self.assertEqual(join_credit_labels([' A\nB ', 'A B', 'C']), 'A B · C')

    def test_credit_box_is_translucent_flush_and_matches_ink_bounds(self):
        image = Image.new('RGB', (400,200), (0,0,255))
        engine = TypographyEngine()
        fonts = ['assets/fonts/Noto_Sans_TC/static/NotoSansTC-Regular.ttf']
        engine.apply_source_credit_overlay(image,'Author/Pexels',fonts)
        font = engine._load_font(fonts,14,'Author/Pexels','body')
        box = ImageDraw.Draw(image).textbbox((0,0),'Author/Pexels',font=font)
        w,h=box[2]-box[0],box[3]-box[1]
        region=image.crop((400-w,0,400,h))
        self.assertEqual(region.size,(w,h))
        self.assertEqual(image.getpixel((400-w,0)),(56,56,161))
        self.assertEqual(image.getpixel((400-w-1,0)),(0,0,255))
