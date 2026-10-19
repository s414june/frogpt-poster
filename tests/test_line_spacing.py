import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
from gpt_package.typography import TypographyEngine
from gpt_package.types import PosterStyle


class LineSpacingTests(unittest.TestCase):
    def test_half_em_gap_for_each_font_in_both_layout_modes(self):
        engine = TypographyEngine()
        for mode in ('both', 'background'):
            rows = []
            original = ImageDraw.ImageDraw.text
            def record(draw, xy, text, *args, **kwargs):
                rows.append((xy[1], kwargs['font'].size, text))
                return original(draw, xy, text, *args, **kwargs)
            with patch.object(ImageDraw.ImageDraw, 'text', record):
                engine.apply(Image.new('RGB', (480, 640), 'beige'), '厚切\n三明治。',
                    '新鮮現做\n每天供應\n歡迎品嚐',
                    ['assets/fonts/Noto_Sans_TC/static/NotoSansTC-Regular.ttf'],
                    PosterStyle(image_role_mode=mode, headline_source='title'))
            self.assertEqual(rows[1][0]-rows[0][0], round(rows[0][1]*1.5))
            # Last two details use the same minor font in both layout modes.
            self.assertEqual(rows[-1][1], rows[-2][1])
            self.assertEqual(rows[-1][0]-rows[-2][0], round(rows[-1][1]*1.5))

    def test_block_height_matches_drawing_advance_without_grid_snapping(self):
        engine = TypographyEngine()
        for size in (19, 24, 31, 48):
            self.assertEqual(engine._line_step(size), round(size*1.5))
            self.assertEqual(engine._lines_height(size, 3), round(size*1.5)*3)
