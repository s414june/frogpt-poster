import base64
import hashlib
import io
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
from api.mcp import dispatch
from gpt_package.typography import TypographyEngine


def call(**args):
    return dispatch({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                     'params': {'name': 'prepare_poster', 'arguments': {'intake_confirmed': True, **args}}})['result']


def image_data():
    buffer = io.BytesIO()
    Image.new('RGB', (480, 640), '#e8d6b9').save(buffer, 'JPEG')
    return 'data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode()


class StagedWorkflowTests(unittest.TestCase):
    def test_image_only_draft_pauses_without_invoking_renderer(self):
        with patch('api.mcp.handle_tool_call') as renderer:
            result = call(generated_background_base64=image_data(), generated_background_text_free_confirmed=True)
        renderer.assert_not_called()
        output = result['structuredContent']
        self.assertEqual(output['status']['code'], 'awaiting_typography_confirmation')
        self.assertFalse(output['rendered'])
        self.assertEqual(result['content'][0]['type'], 'image')
        self.assertTrue(output['relay_payload']['preview_available'])
        self.assertIn('停止', result['content'][1]['text'])

    def test_intake_and_copy_do_not_imply_typography_approval(self):
        result = call(title='Title', body='Body', generated_background_base64=image_data(),
                      generated_background_text_free_confirmed=True)
        self.assertEqual(result['structuredContent']['status']['code'], 'awaiting_typography_confirmation')

    def test_approval_without_matching_draft_still_pauses(self):
        for sha in (None, 'wrong-image'):
            args = {} if sha is None else {'approved_draft_sha256': sha}
            result = call(title='Title', body='Body', typography_confirmed=True,
                          generated_background_base64=image_data(),
                          generated_background_text_free_confirmed=True, **args)
            self.assertEqual(result['structuredContent']['status']['code'], 'awaiting_typography_confirmation')

    def test_explicit_approval_returns_decodable_png(self):
        result = call(title='Title', body='Body', generated_background_base64=image_data(),
                      generated_background_text_free_confirmed=True, typography_confirmed=True,
                      approved_draft_sha256=hashlib.sha256(base64.b64decode(image_data().split(",")[1])).hexdigest())
        output = result['structuredContent']
        self.assertEqual(output['status']['code'], 'completed')
        raw = base64.b64decode(output['relay_payload']['fullsize_base64'], validate=True)
        image = Image.open(io.BytesIO(raw))
        self.assertEqual(image.format, 'PNG')
        self.assertEqual(image.size, (480, 640))
        self.assertEqual(output['request']['style']['image_role_mode'], 'both')
        self.assertFalse(output['request']['style']['geometry_enabled'])

    def test_generation_without_copy_has_centered_subject_prompt(self):
        result = call(subject='三明治')
        output = result['structuredContent']
        self.assertEqual(output['status']['code'], 'needs_background_generation')
        prompt = output['background_generation_prompt']
        self.assertIn('(50%, 50%)', prompt)
        self.assertIn('50% of canvas width', prompt)
        self.assertIn('50% of canvas height', prompt)
        self.assertIn('480x640', prompt)

    def test_invalid_image_is_not_shown_as_draft(self):
        result = call(generated_background_base64='data:image/jpeg;base64,bm90IGFuIGltYWdl',
                      generated_background_text_free_confirmed=True)
        self.assertEqual(result['structuredContent']['status']['code'], 'needs_input')
        self.assertFalse(any(c['type'] == 'image' for c in result['content']))

    def test_approval_requires_copy_and_survives_fresh_server_instance(self):
        from api.mcp import _INTAKE_SESSIONS
        _INTAKE_SESSIONS.clear()
        result = call(typography_confirmed=True,
                      approved_draft_sha256=hashlib.sha256(base64.b64decode(image_data().split(",")[1])).hexdigest(), generated_background_base64=image_data(),
                      generated_background_text_free_confirmed=True)
        self.assertEqual(result['structuredContent']['status']['message'], 'copy_required')

    def test_both_layout_modes_use_one_text_fill_on_mixed_background(self):
        from types import SimpleNamespace
        for mode in ('both', 'auto'):
            image = Image.new('RGB', (480, 640), 'white')
            ImageDraw.Draw(image).rectangle((0, 320, 480, 640), fill='black')
            fills = []
            original = ImageDraw.ImageDraw.text
            def record(draw, xy, text, *args, **kwargs):
                fills.append(kwargs.get('fill'))
                return original(draw, xy, text, *args, **kwargs)
            with patch.object(ImageDraw.ImageDraw, 'text', record):
                TypographyEngine().apply(image, 'Fresh sandwich', 'Made fresh\nEvery day', [],
                                         SimpleNamespace(image_role_mode=mode))
            self.assertTrue(fills)
            self.assertEqual(len(set(fills)), 1)
