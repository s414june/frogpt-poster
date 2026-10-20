import base64
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from gpt_package.openai_tool import handle_tool_call
from gpt_package.mcp_http import dispatch, _materialize_attachment_file_inputs


def data(color='red', mode='RGBA', size=(80, 100)):
    buf=io.BytesIO(); Image.new(mode,size,color).save(buf,'PNG')
    return 'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ, {'POSTER_OUTPUT_DIR':self.tmp.name,'FROGPT_BLOB_ENABLED':'false','FROGPT_FONT_SOURCE':'local'})
        self.env.start()
    def tearDown(self):
        self.env.stop(); self.tmp.cleanup()
    def render(self, **args):
        return handle_tool_call(dict(title='Hello',body='Daily',width=480,height=640,**args))
    def test_acceptance_a_to_f_actual_png(self):
        # Stock paths and design metadata are local fixtures: no live API required.
        bg=Path(self.tmp.name)/'bg.png'; Image.new('RGB',(480,640),'blue').save(bg)
        stock=[(bg,dict(id='stock',photographer='Artist',credit_label='Artist/Pexels',page_url='https://pexels.com/photo/1'))]
        design=dict(id='design',credit_required=True,credit_label='Designer/Studio')
        geometry=[dict(shape='circle',x=10,y=280,width=40,height=40,fill='#000000',opacity=1,stroke_width=2)]
        cases=[
            dict(background_mode='solid',subject_source='ai_generated'),
            dict(reference_library_id='stock',subject_source='ai_generated'),
            dict(user_image_base64=[data('blue')],image_role_mode='background',geometry_enabled=False),
            dict(background_mode='gradient',design_reference=True,reference_style_description='blue asymmetric',subject_source='ai_generated'),
            dict(reference_library_id='stock',design_reference_ids=['design'],geometry_layers=geometry,geometry_enabled=True),
            dict(background_mode='solid',subject_source='ai_generated',geometry_enabled=False,geometry_layers=geometry),
        ]
        with patch('gpt_package.openai_tool._local_library_items',return_value=stock), patch('gpt_package.openai_tool.load_design_references',return_value=[design]):
            for label,args in zip('ABCDEF',cases):
                with self.subTest(case=label):
                    result=self.render(subject_image_base64=[data()],**args)
                    self.assertTrue(result['rendered'],result)
                    self.assertEqual(result['poster_status'],'completed')
                    with Image.open(io.BytesIO(base64.b64decode(result['output_image_base64']))) as image:
                        self.assertEqual(image.format,'PNG'); self.assertEqual(image.size,(480,640))
                        self.assertGreater(image.getpixel((240,320))[0],200) # foreground survives
                    self.assertEqual(result['composition']['geometry_used'],label=='E')
                    if label in 'BE': self.assertIn('Artist/Pexels',result['source_credit_overlay_text'])
    def test_background_never_replaces_subject(self):
        result=self.render(user_image_base64=[data('blue')],image_role_mode='background')
        self.assertFalse(result['rendered']); self.assertEqual(result['status']['code'],'needs_subject_generation')
    def test_no_assets_returns_generation_not_confirmation(self):
        result=self.render()
        self.assertEqual(result['next_action'],'generate_subject_then_retry')
        self.assertNotIn('intake_questions',result)
    def test_subject_position_is_used_by_renderer(self):
        result=self.render(subject_image_base64=[data()],primary_color='#FFFFFF', subject_position=dict(x=20,y=250,width=40,height=50))
        self.assertTrue(result['rendered'],result)
        image=Image.open(io.BytesIO(base64.b64decode(result['output_image_base64'])))
        self.assertEqual(image.getpixel((40,270)),(255,0,0))
        self.assertNotEqual(image.getpixel((240,320)),(255,0,0))
    def test_invalid_subject_position_fails_before_render(self):
        result=self.render(subject_image_base64=[data()],subject_position=dict(x=470,y=0,width=80,height=80))
        self.assertFalse(result['rendered']); self.assertEqual(result['error_type'],'ValidationError')
    def test_independent_typography_without_reference(self):
        layers=[dict(text='Hello',font_size=26,color='#112233',x=24,y=24,width=400,height=50),dict(text='Daily',font_size=18,color='#663311',x=24,y=540,width=400,height=50)]
        result=self.render(subject_image_base64=[data()],text_layers=layers)
        self.assertTrue(result['rendered'],result)
        self.assertEqual([x['color'] for x in result['request']['style']['text_layers']],['#112233','#663311'])
    def test_formal_attachment_dispatch_auto_completes(self):
        args=dict(title='Hello',body='Daily',subject_source='ai_generated',subject_image=dict(file_id='file-x',download_url='https://files.oaiusercontent.com/x'))
        with patch('gpt_package.mcp_http._download_attachment_as_data_url',return_value=data()):
            result=dispatch(dict(jsonrpc='2.0',id=1,method='tools/call',params=dict(name='prepare_poster',arguments=args)))['result']['structuredContent']
        self.assertTrue(result['rendered'],result); self.assertEqual(result['composition']['subject_source'],'ai_generated')
    def test_background_attachment_marks_role(self):
        with patch('gpt_package.mcp_http._download_attachment_as_data_url',return_value=data()):
            args=_materialize_attachment_file_inputs(dict(background_image=dict(file_id='x',download_url='https://files.oaiusercontent.com/x')))
        self.assertEqual(args['image_role_mode'],'background')

    def test_preview_only_separate_layers_requires_same_visual_approval(self):
        args=dict(subject_image_base64=[data()],preview_only=True)
        first=self.render(**args)
        self.assertFalse(first['rendered']); self.assertEqual(first['status']['code'],'awaiting_typography_confirmation')
        wrong=self.render(**args,typography_confirmed=True,approved_draft_sha256='bad')
        self.assertFalse(wrong['rendered'])
        done=self.render(**args,typography_confirmed=True,approved_draft_sha256=first['draft_image_sha256'])
        self.assertTrue(done['rendered'],done)
    def test_ai_disabled_requires_upload(self):
        result=self.render(allow_ai_fallback=False)
        self.assertEqual(result['next_action'],'upload_subject_then_retry'); self.assertFalse(result['rendered'])
    def test_user_background_wins_over_saved_stock(self):
        result=self.render(user_image_base64=[data('blue')],image_role_mode='background',subject_image_base64=[data()],reference_library_id='invalid-unused-id')
        self.assertTrue(result['rendered'],result)
        self.assertEqual(result['composition']['background_source'],'user_upload')
    def test_blob_subject_provenance_and_no_duplicate_upload(self):
        from tests.test_blob_storage import Memory
        from gpt_package.blob_storage import BlobRepository
        from gpt_package.blob_workflow import prepare_inputs
        from datetime import datetime,timezone
        clock=lambda:datetime.now(timezone.utc)
        backend=Memory(clock);repo=BlobRepository(backend,clock)
        args,refs=prepare_inputs(dict(subject_image_base64=[data()],subject_source='ai_generated'),repo)
        count=backend.puts
        reused,_=prepare_inputs(dict(asset_refs=refs),repo)
        self.assertEqual(reused['subject_source'],'ai_generated')
        self.assertEqual(backend.puts,count)
