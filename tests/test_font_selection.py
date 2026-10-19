import unittest
from unittest.mock import patch
from PIL import Image
from gpt_package.openai_tool import _build_request
from gpt_package.typography import TypographyEngine
from gpt_package.font_registry import resolve_font_family
from gpt_package.errors import ValidationError


class FontSelectionTests(unittest.TestCase):
    def test_default_is_only_sans(self):
        request = _build_request({'title': '厚切', 'body': '三明治'})
        self.assertEqual(request.style.font_family, 'sans')
        self.assertTrue(all('Noto_Sans_TC' in p for p in request.assets.open_source_font_paths))

    def test_explicit_family_and_alias_reach_rendered_font(self):
        for family, expected in [('明體', 'Noto_Serif_TC'), ('serif', 'Noto_Serif_TC'),
                                 ('楷體', 'LXGW_WenKai_TC'), ('圓體', 'Chiron_GoRound_TC')]:
            request = _build_request({'title': '厚切', 'body': '三明治',
                'poster_request': {'style': {'image_role_mode': 'both', 'font_family': family}}})
            info = TypographyEngine().apply(Image.new('RGB', (480, 640), 'beige'),
                request.title, request.body, request.assets.open_source_font_paths, request.style)
            self.assertIn(expected, info['body_font'])
            self.assertIn(expected, info['title_font'])

    def test_unknown_or_missing_font_does_not_silently_fallback(self):
        with self.assertRaises(ValidationError):
            resolve_font_family('not-a-real-font')
        with patch('gpt_package.font_registry.Path.is_file', return_value=False):
            with self.assertRaises(ValidationError):
                resolve_font_family('serif')

    def test_top_level_overrides_nested_font(self):
        request = _build_request({'title': 'Title', 'body': 'Body', 'font_family': 'serif',
            'poster_request': {'style': {'font_family': 'sans'}}})
        self.assertEqual(request.style.font_family, 'serif')
