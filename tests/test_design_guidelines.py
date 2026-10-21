import copy
import hashlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw
from gpt_package.design_rules import DesignRuleLoader, DesignTokenResolver, DesignRuleError, ROOT
from gpt_package.design_layout import LayoutPlanner, normalized_box, contrast, LayoutValidator
from gpt_package.glyph_metrics import GlyphMeasurer, coverage
from gpt_package.types import PosterRequest, PosterLayout
from gpt_package.openai_tool import handle_tool_call
from tests.test_composition import data
from tests.workflow_fixtures import approved_call
handle_tool_call = approved_call(handle_tool_call)


def intent(**extra):
    return dict(assetProvenance=dict(subject=dict(source='ai_generated',license='generated',posterTextFree=True)),**extra)


def layer(text='厚切三明治 Fresh',**extra):
    return dict(id='headline',text=text,role='headline',box=dict(x=.08,y=.08,width=.80,height=.18),fontSizeRelativeToShortSide=.08,**extra)


class RuleDataTests(unittest.TestCase):
    def setUp(self):self.rules=DesignRuleLoader().load()
    def test_all_51_rules_schema_and_document_drift(self):
        spec=importlib.util.spec_from_file_location('validate_rules',Path('scripts/validate_design_rules.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertEqual(module.validate_documents()['rules'],51)
        self.assertEqual(len(list(ROOT.glob('*.md'))),6)
        for rule in self.rules['rules']:
            with self.subTest(rule=rule['id']):
                self.assertTrue(rule['operator']);self.assertIn(rule['severity'],('hard','soft','advisory'))
                if rule['enforcement']=='experimental':self.assertTrue(rule['notAutomaticallyTestable'])
    def test_invalid_rules_fail_closed(self):
        mutations=[lambda d:d.update(schemaVersion='2.0.0'),lambda d:d['rules'][0].update(id='TYPO-999'),lambda d:d['rules'][0].update(unit='px'),lambda d:d['rules'][0].update(enabled=False),lambda d:d['rules'][3].update(range=dict(min=.2,max=.1)),lambda d:d['rules'][3].update(default=float('nan')),lambda d:d['rules'].__setitem__(1,copy.deepcopy(d['rules'][0]))]
        for mutate in mutations:
            value=copy.deepcopy(self.rules);mutate(value)
            with tempfile.TemporaryDirectory() as temp:
                path=Path(temp)/'bad.json';path.write_text(json.dumps(value))
                with self.assertRaises(DesignRuleError):DesignRuleLoader().load(path)
    def test_intent_dataclass_and_schema_do_not_drift(self):
        from dataclasses import fields
        from gpt_package.design_rules import DesignIntent
        schema=json.loads((ROOT/'design-intent.schema.json').read_text())
        self.assertEqual({f.name for f in fields(DesignIntent)},set(schema['properties']))
        resolved=DesignTokenResolver().resolve(self.rules,DesignIntent().to_dict())
        self.assertEqual(resolved.version,'1.0.0')

    def test_override_precedence_provenance_and_hard_gate(self):
        tokens=DesignTokenResolver().resolve(self.rules,dict(stylePreset='minimal',referenceOverrides={'TYPO-004':.12},userOverrides={'TYPO-004':.13}))
        self.assertEqual(tokens.values['TYPO-004'],.13);self.assertEqual(tokens.provenance['TYPO-004'],'user')
        self.assertEqual(len([c for c in tokens.history if c['ruleId']=='TYPO-004']),3)
        for override in ({'VAL-007':99},{'TYPO-999':.1},{'GRID-003':float('nan')},{'GRID-004':7}):
            with self.assertRaises(DesignRuleError):DesignTokenResolver().resolve(self.rules,dict(userOverrides=override))
    def test_soft_out_of_range_warns(self):
        tokens=DesignTokenResolver().resolve(self.rules,dict(userOverrides={'TYPO-004':.16}))
        self.assertEqual(tokens.values['TYPO-004'],.16);self.assertTrue(tokens.diagnostics)
    def test_normalized_units_invalid_hex_nonfinite(self):
        for value in (dict(x=-.1,y=0,width=.2,height=.2),dict(x=0,y=0,width=float('nan'),height=.2),dict(x=.9,y=0,width=.2,height=.2)):
            with self.assertRaises(DesignRuleError):normalized_box(value,1920,1080)
        with self.assertRaises(DesignRuleError):DesignTokenResolver().resolve(self.rules,dict(typography=[layer(color='blue')]))
    def test_safe_margins_and_columns_artboards(self):
        tokens=DesignTokenResolver().resolve(self.rules,{})
        for w,h in ((1200,1500),(1080,1080),(1920,1080),(2480,3508)):
            request=PosterRequest('Title','Body',layout=PosterLayout(w,h));grid=LayoutPlanner().grid(request,tokens)
            self.assertAlmostEqual(grid['safeX']*w,grid['safeY']*h)
            self.assertAlmostEqual(2*grid['safePx']+grid['columns']*grid['columnWidthPx']+(grid['columns']-1)*grid['gutterPx'],w)
            self.assertEqual(len(LayoutPlanner().candidates(request,{},tokens)),3)
    def test_contrast_is_linearized_srgb(self):
        self.assertAlmostEqual(contrast((255,255,255),(0,0,0)),21)
        self.assertAlmostEqual(contrast((255,255,255),(255,255,255)),1)
    def test_registered_cmap_and_fallback_runs(self):
        measurer=GlyphMeasurer('serif',400,24,['sans'])
        self.assertGreater(measurer.width('繁體中文 Fresh 123'),0)
        original=measurer.fonts[0];measurer.fonts[0]=(original[0],original[1],frozenset(ord(c) for c in 'Fresh 123'))
        self.assertTrue(measurer.runs('Fresh 中文'));self.assertIn('sans',measurer.fallback_used)
        with self.assertRaises(DesignRuleError):measurer.runs('\U0010ffff')
    def test_measured_wrapping_preserves_40_char_title(self):
        text='繁體中文標題，Mixed English! '*4
        measurer=GlyphMeasurer('sans',400,30,['sans']);lines=measurer.wrap(text,180,tracking=1)
        self.assertEqual(''.join(lines),text)
        self.assertTrue(all(not line.startswith('，') for line in lines))
        # Mixed CJK/Latin ink needs sufficient leading on the pinned Pillow 11 renderer.
        mask,metrics=measurer.raster(lines,1,1.4,'left');self.assertEqual(mask.size,(metrics['width'],metrics['height']))


class DesignPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'POSTER_OUTPUT_DIR':self.tmp.name,'FROGPT_BLOB_ENABLED':'false','FROGPT_FONT_SOURCE':'local','POSTER_DESIGN_RULES_V1':'false'});self.env.start()
    def tearDown(self):self.env.stop();self.tmp.cleanup()
    def run_poster(self,**extra):
        args=dict(title='厚切三明治 Fresh',body='每日現做，簡單美味。',width=480,height=600,subject_source='ai_generated',subject_image_base64=[data()],primary_color='#F5F1E8',design_rules_v1=True,design_intent=intent())
        args.update(extra);return handle_tool_call(args)
    def test_success_normalized_intent_deterministic_no_geometry(self):
        args=dict(design_intent=intent(typography=[layer()]))
        first=self.run_poster(**args);second=self.run_poster(**args)
        self.assertTrue(first['rendered'],first);self.assertEqual(first['output_image_sha256'],second['output_image_sha256'])
        self.assertFalse(first['composition']['geometry_used'])
        report=first['design_report'];self.assertEqual(report['candidate'],'explicit');self.assertTrue(report['hardRulesChecked'])
        self.assertTrue(report['scores']['experimental']);self.assertIn('salience',report['scores']['disabled'])
    def test_portrait_square_landscape_a4(self):
        for w,h in ((1200,1500),(1080,1080),(1920,1080),(2480,3508)):
            with self.subTest(size=(w,h)):
                result=self.run_poster(width=w,height=h)
                self.assertTrue(result['rendered'],result)
                with Image.open(io.BytesIO(__import__('base64').b64decode(result['output_image_base64']))) as image:self.assertEqual(image.size,(w,h))
                self.assertEqual(result['design_report']['candidatesEvaluated'],3)
    def test_long_title_has_diagnostics_and_no_lost_characters(self):
        text='繁體中文美味三明治今日限定每天新鮮製作歡迎一起享用簡單美好時光'*2
        result=self.run_poster(title=text)
        self.assertTrue(result['rendered'],result)
        headline=next(i for i in result['design_report']['measurements'] if i['role']=='headline')
        self.assertEqual(''.join(headline['measuredLines']),text)
        self.assertTrue(result['design_report']['diagnostics'])
    def test_low_contrast_repaired_and_reported(self):
        result=self.run_poster(primary_color='#F5F1E8',design_intent=intent(typography=[layer(color='#F5F1E8')]))
        self.assertTrue(result['rendered'],result)
        self.assertTrue(any(d['ruleId']=='COLOR-002' for d in result['design_report']['diagnostics']))
    def test_low_contrast_unrepairable_fails_with_code(self):
        result=self.run_poster(design_intent=intent(typography=[layer(color='#F5F1E8')],allowColorRepair=False))
        self.assertFalse(result['rendered']);self.assertEqual(result['error_code'],'TEXT_CONTRAST_LOW')
        self.assertTrue(result['diagnostics']);self.assertFalse(result['ok'])
    def test_reference_and_style_do_not_bypass_hard_rules(self):
        result=self.run_poster(design_reference=True,design_intent=intent(stylePreset='bold-commercial',userOverrides={'VAL-002':False}))
        self.assertFalse(result['rendered']);self.assertEqual(result['error_code'],'RULESET_INVALID')
    def test_unmeasurable_font_fails_without_success(self):
        with patch('gpt_package.glyph_metrics.materialize_font',side_effect=OSError('font unavailable')):
            result=self.run_poster()
        self.assertFalse(result['rendered']);self.assertEqual(result['error_code'],'FONT_UNAVAILABLE')
    def test_missing_glyph_fails(self):
        result=self.run_poster(title='\U0010ffff')
        self.assertFalse(result['rendered']);self.assertEqual(result['error_code'],'FONT_UNAVAILABLE')
    def test_unknown_license_and_burned_copy_require_evidence(self):
        for record,code in (({},'RULESET_INVALID'),(dict(source='user',license='unknown'),'ASSET_LICENSE_UNKNOWN'),(dict(source='user',license='own',rightsConfirmed=False),'ASSET_LICENSE_UNKNOWN'),(dict(source='user',license='own',rightsConfirmed=True),'ASSET_TEXT_UNVERIFIED')):
            result=self.run_poster(subject_source='user_upload',design_intent=dict(assetProvenance=dict(subject=record)))
            self.assertFalse(result['rendered']);self.assertEqual(result['error_code'],code)
    def test_collision_uses_visible_alpha_not_image_box(self):
        opaque=self.run_poster(design_intent=intent(subjectPosition=dict(x=.08,y=.08,width=.8,height=.8),typography=[layer()]))
        self.assertFalse(opaque['rendered']);self.assertEqual(opaque['error_code'],'TEXT_SUBJECT_COLLISION')
        # Actual alpha bbox occupies bottom half; upper half of source is transparent.
        image=Image.new('RGBA',(100,100));ImageDraw.Draw(image).rectangle((0,60,99,99),fill='red')
        buffer=io.BytesIO();image.save(buffer,'PNG');url='data:image/png;base64,'+__import__('base64').b64encode(buffer.getvalue()).decode()
        transparent=self.run_poster(subject_image_base64=[url],design_intent=intent(subjectPosition=dict(x=.08,y=.08,width=.8,height=.8),typography=[layer()]))
        self.assertTrue(transparent['rendered'],transparent)
    def test_overflow_and_out_of_bounds_fail(self):
        for box in (dict(x=.99,y=.1,width=.1,height=.1),dict(x=.08,y=.08,width=.001,height=.001)):
            l=layer();l['box']=box
            result=self.run_poster(design_intent=intent(typography=[l]))
            self.assertFalse(result['rendered']);self.assertIn(result['error_code'],('LAYOUT_OUT_OF_BOUNDS','TYPO_TEXT_OVERFLOW'))
    def test_feature_flag_off_preserves_baseline_png(self):
        baseline=self.run_poster(design_rules_v1=False)
        same=self.run_poster(design_rules_v1=False,design_intent={'unknown':'ignored while disabled'})
        self.assertTrue(baseline['rendered']);self.assertEqual(baseline['output_image_sha256'],same['output_image_sha256'])
        self.assertEqual(baseline['design_report'],{})
    def test_environment_enables_rules_and_flag_can_roll_back(self):
        args=dict(title='Title',body='Body',width=480,height=600,subject_image_base64=[data()],subject_source='ai_generated',design_intent=intent())
        with patch.dict(os.environ,{'POSTER_DESIGN_RULES_V1':'true'}):
            strict=handle_tool_call(args);legacy=handle_tool_call(dict(args,design_rules_v1=False))
        self.assertTrue(strict['design_report']['ok']);self.assertEqual(legacy['design_report'],{})
    def test_single_explicit_headline_is_legal(self):
        result=handle_tool_call(dict(width=480,height=600,subject_image_base64=[data()],subject_source='ai_generated',design_rules_v1=True,design_intent=intent(typography=[layer()])))
        self.assertTrue(result['rendered'],result)
    def test_invisible_subject_is_not_a_valid_required_layer(self):
        transparent=data((0,0,0,0))
        result=self.run_poster(subject_image_base64=[transparent])
        self.assertFalse(result['rendered']);self.assertEqual(result['error_code'],'POSTER_MISSING_LAYER')
    def test_composited_photo_backdrop_and_repair_budget(self):
        from gpt_package.design_rules import DesignTokenResolver
        request=PosterRequest('Title','Body',layout=PosterLayout(480,600))
        request.assets.subject_image_paths=[]
        tokens=DesignTokenResolver().resolve(DesignRuleLoader().load(),{})
        validator=LayoutValidator();image=Image.new('RGB',(480,600),'white')
        ImageDraw.Draw(image).rectangle((120,0,480,600),fill='black')
        # Worst contrast across both black and white cannot be repaired with color alone.
        item=dict(id='mixed',text='Mixed bright and dark background',box=dict(x=.08,y=.08,width=.84,height=.18),fontSizeRelativeToShortSide=.04,color='#888888')
        with tempfile.TemporaryDirectory() as root:
            subject=Path(root)/'subject.png';Image.new('RGBA',(10,10),'red').save(subject);request.assets.subject_image_paths=[str(subject)]
            from gpt_package.design_layout import LayoutCandidate
            candidate=LayoutCandidate('test',dict(x=.7,y=.6,width=.2,height=.2),[item])
            approved=validator.validate(image,candidate,request,tokens,dict(allowBackdrop=True))
            self.assertTrue(any(d['ruleId']=='COLOR-007' for d in approved.diagnostics))
            self.assertTrue(all(m['repairRounds']<=tokens.values['VAL-007'] for m in approved.measurements))
            for d in approved.diagnostics:
                self.assertTrue(set(('ruleId','severity','elementId','before','after','reason'))<=set(d))
    def test_important_lines_cannot_overlap(self):
        measure=GlyphMeasurer('sans',400,40,[])
        with self.assertRaises(DesignRuleError):measure.raster(['AAAA','AAAA'],0,.1,'left')
