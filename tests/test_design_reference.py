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
        output = handle_tool_call(dict(title='測試', body='活動', design_reference=True,
                                       reference_image_base64=['invalid inspiration bytes'],
                                       reference_style_description='藍色紙張與非對稱構圖'))
        self.assertEqual(output['pipeline_stage'], 'needs_background_generation')
        self.assertTrue(output['reference_is_inspiration_only'])
        self.assertIn('藍色紙張', output['background_generation_prompt'])

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
