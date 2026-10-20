import unittest
from PIL import Image
from gpt_package.layout_grid import grid_spec, place_ink_boxes, validate_regions
from gpt_package.errors import ValidationError
from gpt_package.types import PosterStyle
from gpt_package.text_layers import render_text_layers
from gpt_package.openai_tool import handle_tool_call


class LayoutGridTests(unittest.TestCase):
    def item(self, **kw):
        return dict(font_size=24,**kw)

    def test_repairs_edge_and_subject_collision_with_bounded_grid_move(self):
        measured=[(self.item(),12,100,120,28)]
        protected=[dict(x=0,y=140,width=300,height=150)]
        positions,report=place_ink_boxes(measured,800,1000,protected)
        x,y,x2,y2=positions[0]
        self.assertGreaterEqual(x,40)
        self.assertLessEqual(y2+16,140)
        self.assertEqual(x%8,0)
        self.assertEqual(y%8,0)
        self.assertLessEqual(((x-12)**2+(y-100)**2)**.5,64)
        self.assertTrue(report['adjustments'])

    def test_impossible_layout_fails_instead_of_drawing_on_subject(self):
        with self.assertRaises(ValidationError):
            place_ink_boxes([(self.item(),200,300,300,80)],800,1000,
                           [dict(x=0,y=0,width=800,height=1000)])

    def test_only_explicit_group_warns_for_large_gap(self):
        measured=[(self.item(group='copy'),80,100,200,24),
                  (self.item(group='copy'),80,300,200,24)]
        _,r=place_ink_boxes(measured,800,1000,[])
        self.assertIn('large_group_gap',[x['code'] for x in r['warnings']])
        self.assertIn('protected_regions_missing',[x['code'] for x in r['warnings']])
        measured[1]=(self.item(),80,300,200,24)
        _,r=place_ink_boxes(measured,800,1000,[])
        self.assertNotIn('large_group_gap',[x['code'] for x in r['warnings']])

    def test_tracking_and_grid_reach_real_render(self):
        style=PosterStyle(typography_grid=True,protected_regions=[dict(x=40,y=400,width=600,height=300)])
        image=Image.new('RGB',(800,1000),'white')
        layer=dict(text='三明治，剛剛好。\nFresh & simple.',font_size=32,font_family='sans',
                   font_weight=700,letter_spacing=1.5,color='#123456',x=42,y=100,
                   width=650,height=150,line_spacing=12)
        result=render_text_layers(image,[layer],style=style)
        self.assertEqual(result['layout_report'],style.layout_report)
        self.assertNotEqual(image.crop((40,90,700,300)).getextrema(),((255,255),)*3)

    def test_bad_protected_coordinates_rejected(self):
        for r in [dict(x=float('nan'),y=0,width=1,height=1),dict(x=0,y=0,width=900,height=1)]:
            with self.assertRaises(ValidationError): validate_regions([r],800,1000)

    def test_variant_modes_have_different_generation_instructions(self):
        from gpt_package.composition import DesignResolver
        from gpt_package.types import PosterRequest
        for variant in ('reinterpret','faithful'):
            result=DesignResolver().resolve(PosterRequest('Title','Body'),dict(design_reference=True,design_variant=variant))
            self.assertEqual(result['variant'],variant)
            self.assertEqual(result['source'],'user_reference')
