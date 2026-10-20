from tests.test_composition import data as subject_data
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from gpt_package.geometry import validate_geometry_layers, render_geometry
from gpt_package.errors import ValidationError
from gpt_package.openai_tool import handle_tool_call
from gpt_package.types import PosterRequest, PosterStyle
from gpt_package.image_pipeline import ImagePipeline
from gpt_package.types import PosterDecision, ImageSource


class GeometryTests(unittest.TestCase):
    def test_validation_rejects_invalid_shapes_and_values(self):
        base={'shape':'circle','x':0,'y':0,'width':10,'height':10,'fill':'#000000'}
        for changes in ({'opacity':float('nan')},{'width':-1},{'shape':'text'},{'height':11},{'fill':'bad'}):
            with self.assertRaises(ValidationError): validate_geometry_layers([{**base,**changes}],100,100)

    def test_alpha_blends_with_photo(self):
        image=Image.new('RGB',(100,100),'white')
        layers=validate_geometry_layers([{'shape':'rectangle','x':20,'y':20,'width':30,'height':30,'fill':'#000000','opacity':.5}],100,100)
        render_geometry(image,layers)
        self.assertEqual(image.getpixel((30,30)),(127,127,127))
        self.assertEqual(image.getpixel((0,0)),(255,255,255))

    def test_photo_geometry_and_foreground_remain_visible_with_text_layers(self):
        with tempfile.TemporaryDirectory() as temp:
            photo=Path(temp)/'photo.png';subject=Path(temp)/'subject.png'
            Image.new('RGB',(400,600),'white').save(photo)
            Image.new('RGBA',(100,200),(255,0,0,255)).save(subject)
            req=PosterRequest(title='Title',body='Body')
            req.layout.width=400;req.layout.height=600
            req.assets.user_image_paths=[str(photo)];req.assets.subject_image_paths=[str(subject)]
            req.style=PosterStyle(background_mode='reference',image_role_mode='background',text_layers=[{'text':'Title'}],geometry_layers=validate_geometry_layers([
                {'shape':'rectangle','x':0,'y':0,'width':400,'height':600,'fill':'#0000ff','opacity':1}],400,600))
            pipeline=ImagePipeline()
            result=pipeline.build_background(req,PosterDecision(ImageSource.USER_IMAGE,'test'))
            self.assertEqual(result.getpixel((0,0)),(0,0,255))
            self.assertEqual(result.getpixel((200,250)),(255,0,0))
            self.assertEqual(pipeline.get_last_effects()['decorative_geometry_strategy'],'explicit_gpt_layers')
            req.style.geometry_enabled=False
            result=pipeline.build_background(req,PosterDecision(ImageSource.USER_IMAGE,'test'))
            self.assertEqual(result.getpixel((0,0)),(255,255,255))
            self.assertFalse(pipeline.get_last_effects()['decorative_geometry_applied'])

    def test_geometry_top_level_reaches_tool_renderer(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ',{'POSTER_OUTPUT_DIR':temp}):
            result=handle_tool_call({'title':'Pure','body':'Daily','width':480,'height':640,
                'subject_image_base64':[subject_data()],
                'poster_request':{'reference_library_id':'pexels-1527934'},
                'geometry_layers':[{'shape':'circle','x':10,'y':300,'width':80,'height':80,'stroke':'#000000','opacity':.3}]})
            self.assertTrue(result['rendered'],result)
            self.assertIn('Decorative geometry applied: True',result['notes'])

    def test_gpt_png_preserves_alpha_and_sits_below_subject(self):
        import base64, io, shutil
        from gpt_package.openai_tool import _materialize_remote_images
        with tempfile.TemporaryDirectory() as temp:
            photo=Path(temp)/'photo.png'; subject=Path(temp)/'subject.png'
            Image.new('RGB',(400,600),'white').save(photo)
            Image.new('RGBA',(100,200),(255,0,0,255)).save(subject)
            overlay=Image.new('RGBA',(400,600),(0,0,0,0))
            from PIL import ImageDraw
            ImageDraw.Draw(overlay).rectangle((10,10,390,590),fill=(0,0,0,128))
            buf=io.BytesIO();overlay.save(buf,format='PNG')
            encoded=base64.b64encode(buf.getvalue()).decode()
            for args in ({'geometry_image_base64':encoded}, {'poster_request':{'assets':{'geometry_image_base64':encoded}}}):
                req=PosterRequest(title='Title',body='Body')
                req.layout.width=400;req.layout.height=600
                req.assets.user_image_paths=[str(photo)];req.assets.subject_image_paths=[str(subject)]
                req.style=PosterStyle(background_mode='reference',image_role_mode='background')
                folder=_materialize_remote_images(args,req)
                try:
                    pipe=ImagePipeline()
                    result=pipe.build_background(req,PosterDecision(ImageSource.USER_IMAGE,'test'))
                    self.assertEqual(result.getpixel((0,0)),(255,255,255))
                    self.assertEqual(result.getpixel((20,20)),(127,127,127))
                    self.assertEqual(result.getpixel((200,250)),(255,0,0))
                    self.assertEqual(pipe.get_last_effects()['decorative_geometry_strategy'],'gpt_image_overlay')
                    req.assets.subject_image_paths=[]
                    req.style.text_layers=[{'text':'Title'}]
                    result=pipe.build_background(req,PosterDecision(ImageSource.USER_IMAGE,'test'))
                    self.assertEqual(result.getpixel((20,20)),(127,127,127))
                    req.style.geometry_enabled=False
                    result=pipe.build_background(req,PosterDecision(ImageSource.USER_IMAGE,'test'))
                    self.assertEqual(result.getpixel((20,20)),(255,255,255))
                finally:
                    shutil.rmtree(folder)

    def test_gpt_png_rejects_opaque_wrong_size_and_bad_data(self):
        import base64, io
        from gpt_package.openai_tool import _materialize_remote_images
        req=PosterRequest(title='Title',body='Body')
        for img in (Image.new('RGB',(1080,1350)),Image.new('RGBA',(1080,1350),(0,0,0,255)),Image.new('RGBA',(10,10))):
            buf=io.BytesIO();img.save(buf,format='PNG')
            with self.assertRaises(ValidationError):
                _materialize_remote_images({'geometry_image_base64':base64.b64encode(buf.getvalue()).decode()},req)
        for value in ('', [], 'bad'):
            with self.assertRaises(ValidationError):
                _materialize_remote_images({'geometry_image_base64':value},req)
