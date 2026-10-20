import base64
import io
import unittest
from PIL import Image
from gpt_package.openai_tool import handle_tool_call
from gpt_package.text_layers import render_text_layers, validate_text_layers
from gpt_package.errors import ValidationError


class DesignReferenceTests(unittest.TestCase):
    def layer(self, **changes):
        return dict(text='測試', font_family='serif', font_size=24, color='#1255AA',
                    x=20, y=20, width=200, height=80, **changes)

    def test_reference_requests_new_visual(self):
        output=handle_tool_call(dict(title='測試',body='活動',design_reference=True,reference_style_description='藍色紙張'))
        self.assertEqual(output['status']['code'],'needs_subject_generation')
        self.assertEqual(output['next_action'],'generate_subject_then_retry')
        self.assertFalse(output['rendered'])

    def test_full_render_uses_only_generated_image(self):
        buf = io.BytesIO()
        Image.new('RGB', (480, 640), '#EEEEEE').save(buf, format='PNG')
        output = handle_tool_call(dict(title='測試', body='活動', design_reference=True,
            width=480, height=640, text_layers=[self.layer()],
            reference_image_base64=['not renderable inspiration'],
            generated_background_base64='data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode(),
            generated_background_text_free_confirmed=True))
        self.assertTrue(output['rendered'], output)
        rendered = Image.open(io.BytesIO(base64.b64decode(output['output_image_base64'])))
        self.assertEqual(rendered.getpixel((470, 630)), (238, 238, 238))
        self.assertNotEqual(rendered.crop((20, 20, 100, 60)).getextrema(), ((238,238),)*3)

    def test_overflow_rejected(self):
        with self.assertRaises(ValidationError):
            render_text_layers(Image.new('RGB', (480,640)), [dict(self.layer(), width=1)])

    def test_invalid_coordinates_and_color(self):
        for patch in [dict(x=float('nan')), dict(color='red'), dict(height=1000)]:
            with self.assertRaises(ValidationError):
                validate_text_layers([dict(self.layer(), **patch)],480,640)

    def test_reference_typography_can_use_different_sizes_weights_and_spacing(self):
        from gpt_package.font_registry import resolve_font_weight
        layers = [dict(self.layer(), font_size=48, font_weight=700, height=120, line_spacing=18),
                  dict(self.layer(), y=160, font_size=20, font_weight=400, line_spacing=6)]
        checked = validate_text_layers(layers, 480, 640)
        self.assertEqual([x['font_size'] for x in checked], [48, 20])
        self.assertEqual([x['line_spacing'] for x in checked], [18, 6])
        self.assertTrue(resolve_font_weight('sans', 700)[1].endswith('-Bold.ttf'))
        image = Image.new('RGB', (480, 640), 'white')
        render_text_layers(image, layers)
        with self.assertRaises(ValidationError):
            validate_text_layers([dict(self.layer(), font_family='kai', font_weight=700)], 480, 640)
