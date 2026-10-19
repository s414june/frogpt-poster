import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
from gpt_package.types import PosterStyle
from gpt_package.typography import TypographyEngine
from gpt_package.openai_tool import _build_request


class CopyControlTests(unittest.TestCase):
    def test_inline_controls_preserve_multiline_title_and_align_all_copy(self):
        request = _build_request({'poster_request': {'title': '厚切\n三明治。',
            'body': '把新鮮，夾進日常\n新鮮食材・現點現做',
            'style': {'image_role_mode': 'both', 'headline_source': 'title',
                      'text_align': 'left', 'body_y_ratio': 0.64}}})
        image = Image.new('RGB', (480, 640), 'beige')
        engine = TypographyEngine()
        drawn = []
        original = ImageDraw.ImageDraw.text
        def record(draw, xy, text, *args, **kwargs):
            box = draw.textbbox((0, 0), text, font=kwargs['font'])
            drawn.append((xy[0] + box[0], xy[1], text, kwargs['fill']))
            return original(draw, xy, text, *args, **kwargs)
        with patch.object(ImageDraw.ImageDraw, 'text', record):
            info = engine.apply(image, request.title, request.body,
                ['assets/fonts/Noto_Sans_TC/static/NotoSansTC-Regular.ttf'], request.style)
        self.assertEqual(info['hero_lines'], ['厚切', '三明治。'])
        self.assertEqual(info['minor_lines'][0], '把新鮮，夾進日常')
        self.assertEqual(len({row[0] for row in drawn}), 1)
        self.assertEqual(len({row[3] for row in drawn}), 1)
        self.assertEqual(info['minor_region'][1], int(640 * 0.64))
        self.assertGreater(info['hero_font_size'], info['minor_font_size'])

    def test_body_position_stays_inside_canvas(self):
        engine = TypographyEngine()
        image = Image.new('RGB', (480, 640), 'beige')
        style = PosterStyle(image_role_mode='both', headline_source='title', body_y_ratio=1)
        info = engine.apply(image, 'Title', 'Subtitle\nDetails', [], style)
        self.assertLessEqual(info['minor_region'][3], 640)

    def test_reject_invalid_controls(self):
        for controls in ({'text_align': 'diagonal'}, {'headline_source': 'invalid'},
                         {'body_y_ratio': -1}, {'body_y_ratio': True}):
            with self.assertRaises(Exception):
                _build_request({'title': 'Title', 'body': 'Body', **controls})
