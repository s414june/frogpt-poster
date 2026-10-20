"""Bounded, deterministic candidate planning and measurable design validation.

No image generation, uploads, semantic aesthetics scoring, or OCR claims.
The same registered fonts and image pipeline feed preview and final output.
"""
import copy
import math
from dataclasses import dataclass
from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageOps
from .design_rules import DesignRuleError, DesignRuleLoader, DesignTokenResolver, diagnostic
from .glyph_metrics import GlyphMeasurer
from .types import PosterResult


@dataclass
class LayoutCandidate:
    id: str
    subject: dict
    typography: list


@dataclass
class ValidatedComposition:
    candidate: LayoutCandidate
    image: object
    diagnostics: list
    measurements: list
    score: dict


def normalized_box(box, width, height):
    if not isinstance(box,dict) or set(box)!=set(('x','y','width','height')):
        raise DesignRuleError('LAYOUT_OUT_OF_BOUNDS','GRID-001','Invalid normalized bbox')
    for value in box.values():
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=1:
            raise DesignRuleError('LAYOUT_OUT_OF_BOUNDS','GRID-001','Expected finite normalized coordinate')
    if box['width']<=0 or box['height']<=0 or box['x']+box['width']>1 or box['y']+box['height']>1:
        raise DesignRuleError('LAYOUT_OUT_OF_BOUNDS','GRID-002','Important content extends outside canvas')
    return dict(x=box['x']*width,y=box['y']*height,width=box['width']*width,height=box['height']*height)


class CompositionAdapter:
    @staticmethod
    def to_normalized(layer,width,height):
        item=dict(id=str(layer.get('id','text')),role=layer.get('role','body'),text=layer['text'],
            box={k:layer[k]/(width if k in ('x','width') else height) for k in ('x','y','width','height')},
            fontFamily=layer.get('font_family','sans'),fontWeight=layer.get('font_weight',400),
            fontSizeRelativeToShortSide=layer['font_size']/min(width,height),
            color=layer['color'],align=layer.get('align','left'))
        # Legacy line_spacing is a pixel gap between baseline metrics, not a multiplier.
        item['_legacy_line_spacing']=layer.get('line_spacing',4)
        item['letterSpacingEm']=layer.get('letter_spacing',0)/layer['font_size']
        return item

    @staticmethod
    def render_subject(request,position):
        request.style.subject_position=normalized_box(position,request.layout.width,request.layout.height)


class LayoutPlanner:
    def grid(self,request,tokens):
        w,h=request.layout.width,request.layout.height;s=min(w,h)
        safe=tokens.values['GRID-003']*s;gutter=tokens.values['GRID-005']*s;count=int(tokens.values['GRID-004'])
        column=(w-2*safe-(count-1)*gutter)/count
        if column<=0:raise DesignRuleError('LAYOUT_OUT_OF_BOUNDS','GRID-001','Grid has no usable column width')
        return dict(safePx=safe,safeX=safe/w,safeY=safe/h,columns=count,gutterPx=gutter,columnWidthPx=column,keyLinesPx=[safe+i*(column+gutter) for i in range(count)])

    def candidates(self,request,intent,tokens):
        w,h=request.layout.width,request.layout.height;s=min(w,h)
        grid=self.grid(request,tokens);safe=grid['safePx'];mx,my=grid['safeX'],grid['safeY']
        half=grid['columns']//2;right_x=grid['keyLinesPx'][half]/w
        left_width=(half*grid['columnWidthPx']+(half-1)*grid['gutterPx'])/w
        explicit=intent.get('typography')
        if not explicit and request.style.text_layers:
            explicit=[CompositionAdapter.to_normalized(layer,w,h) for layer in request.style.text_layers]
        supplied_subject=intent.get('subjectPosition')
        if request.style.explicit_subject_position and not supplied_subject:
            supplied_subject={k:v/(w if k in ('x','width') else h) for k,v in request.style.subject_position.items()}
        if explicit:
            return [LayoutCandidate('explicit',supplied_subject or copy.deepcopy(tokens.runtime['defaultSubjectPosition']),copy.deepcopy(explicit))]
        anchors=dict(safeX=mx,safeY=my,rightX=right_x,rightWidth=1-mx-right_x,leftWidth=left_width,fullWidth=1-2*mx,leftTextHeight=tokens.runtime['leftTextBottom']-my)
        templates=[(template['id'],{k:anchors[v] if isinstance(v,str) else v for k,v in template['subject'].items()},
                    {k:anchors[v] if isinstance(v,str) else v for k,v in template['text'].items()}) for template in tokens.runtime['layoutTemplates']]
        result=[]
        for name,subject,area in templates[:tokens.runtime['candidateCount']]:
            texts=[]
            headline=request.title;body=request.body
            # Explicit typography metadata can have duplicated legacy title/body.
            entries=[('headline',headline),('body',body)] if body and body!=headline else [('headline',headline)]
            split=tokens.runtime['textSplit']['headlineHeightRatio'] if len(entries)>1 else 1
            for index,(role,text) in enumerate(entries):
                box=dict(area)
                if len(entries)>1:
                    box['y']=area['y']+(area['height']*tokens.runtime['textSplit']['bodyOffsetRatio'] if index else 0)
                    box['height']=area['height']*(tokens.runtime['textSplit']['bodyHeightRatio'] if index else split)
                texts.append(dict(id=role,role=role,text=text,box=box))
            result.append(LayoutCandidate(name,copy.deepcopy(supplied_subject or subject),texts))
        if tokens.values['HIER-001']=='headline':
            result.sort(key=lambda item:item.id!='top-copy')
        return result


def luminance(rgb):
    values=[v/255 for v in rgb[:3]]
    linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
    return sum(v*k for v,k in zip(linear,(.2126,.7152,.0722)))


def contrast(a,b):
    x,y=sorted((luminance(a),luminance(b)))
    return (y+.05)/(x+.05)


class LayoutValidator:
    def assets(self,request,spec,intent):
        if spec.legacy_draft:raise DesignRuleError('POSTER_MISSING_LAYER','COMP-001','Strict mode requires independent background and subject; use vNext asset fields')
        if not request.assets.subject_image_paths:raise DesignRuleError('POSTER_MISSING_LAYER','COMP-001','Missing subject')
        records=copy.deepcopy(intent.get('assetProvenance',{}));credits=[]
        if spec.subject['source']=='ai_generated':records.setdefault('subject',dict(source='ai_generated',license='generated'))
        if spec.background['source']=='pexels_library':records.setdefault('background',dict(source='pexels_library',license='Pexels',attribution=request.style.source_credit_text))
        paths={'subject':request.assets.subject_image_paths[0]}
        if request.assets.user_image_paths:paths['background']=request.assets.user_image_paths[0]
        if request.style.geometry_enabled and request.assets.geometry_image_path:paths['geometry']=request.assets.geometry_image_path
        for role,path in paths.items():
            record=records.get(role)
            if not record or not record.get('license') or record['license'].lower() in ('unknown','unverified'):
                raise DesignRuleError('ASSET_LICENSE_UNKNOWN','COMP-010','Missing asset rights provenance',role)
            known_stock=role=='background' and spec.background['source']=='pexels_library' and record['source']=='pexels_library'
            known_ai=role=='subject' and spec.subject['source']=='ai_generated' and record['source']=='ai_generated'
            if not (known_stock or known_ai) and record.get('rightsConfirmed') is not True:
                raise DesignRuleError('ASSET_LICENSE_UNKNOWN','VAL-004','User must confirm rights; upload/intake flags do not establish licensing',role)
            if role=='subject' and record.get('posterTextFree') is not True:
                raise DesignRuleError('ASSET_TEXT_UNVERIFIED','COMP-004','Declare no newly burned-in poster copy; existing product labels may remain',role)
            try:
                with Image.open(path) as image:image.load()
            except Exception as exc:raise DesignRuleError('ASSET_UNREADABLE','COMP-008',str(exc),role) from exc
            if record.get('attribution'):credits.append(record['attribution'])
        if credits:
            from .design_library import join_credit_labels
            request.style.source_credit_text=join_credit_labels([request.style.source_credit_text,*credits])
        return records

    def subject_mask(self,request,position,tokens,intent):
        w,h=request.layout.width,request.layout.height
        result=Image.new('L',(w,h));box=normalized_box(position,w,h)
        with Image.open(request.assets.subject_image_paths[0]) as source:
            image=ImageOps.contain(source.convert('RGBA'),(max(1,round(box['width'])),max(1,round(box['height']))),Image.Resampling.LANCZOS)
        result.paste(image.getchannel('A'),(round(box['x']+(box['width']-image.width)/2),round(box['y']+(box['height']-image.height)/2)))
        if result.getbbox() is None:
            raise DesignRuleError('POSTER_MISSING_LAYER','COMP-001','Subject has no visible alpha pixels')
        threshold=tokens.runtime['alphaProtectionThreshold']
        result=result.point(lambda a:255 if a>=threshold else 0)
        draw=ImageDraw.Draw(result)
        zones=[normalized_box(zone,w,h) for zone in intent.get('protectionZones',[])]
        zones+=request.style.protected_regions
        for z in zones:
            if min(z.values())<0 or z['x']+z['width']>w or z['y']+z['height']>h:
                raise DesignRuleError('LAYOUT_OUT_OF_BOUNDS','GRID-002','Protection zone exceeds canvas')
            draw.rectangle((z['x'],z['y'],z['x']+z['width'],z['y']+z['height']),fill=255)
        return result

    def measure(self,layer,request,tokens):
        element=layer.get('id','text');w,h=request.layout.width,request.layout.height;s=min(w,h)
        text=layer.get('text','')
        if not isinstance(text,str) or not text.strip():raise DesignRuleError('POSTER_MISSING_LAYER','TYPO-001','Valid text is required',element)
        if len(text)>tokens.runtime['maxTextLength']:raise DesignRuleError('TYPO_TEXT_OVERFLOW','TYPO-003','Text length exceeds supported limit',element)
        box=normalized_box(layer['box'],w,h);role=layer.get('role','body')
        size=layer.get('fontSizeRelativeToShortSide',tokens.values['TYPO-004']*(1 if role=='headline' else tokens.values['TYPO-005']['secondary' if role=='secondary' else 'body'][1]))*s
        family=layer.get('fontFamily',request.style.font_family);weight=layer.get('fontWeight',tokens.runtime['fontWeight']['headline' if role=='headline' else 'body'])
        if family in ('kai','rounded') and 'fontWeight' not in layer:weight=400
        color=layer.get('color',tokens.runtime['defaultTextColor'])
        try:
            if not isinstance(color,str) or len(color)!=7 or not color.startswith('#'):raise ValueError('Expected #RRGGBB')
            ImageColor.getrgb(color)
        except Exception as exc:raise DesignRuleError('RULESET_INVALID','COLOR-001',str(exc),element) from exc
        align=layer.get('align','left')
        if align not in ('left','center','right'):raise DesignRuleError('RULESET_INVALID','GRID-001','Invalid text alignment',element)
        diagnostics=[];original_size=size
        # Two bounded correction rounds: wrapping, then a finite search over smaller sizes.
        for correction in range(tokens.values['VAL-007']+1):
            attempts=1 if correction==0 else tokens.runtime['fitAttemptsPerRound']
            for attempt in range(attempts):
                factor=1 if correction==0 else 1-(attempt+1)/(attempts+1)
                trial=size*factor
                if trial<s*tokens.runtime['minimumFontSizeRelativeToShortSide']:continue
                measurer=GlyphMeasurer(family,weight,trial,tokens.runtime['fallbackFamilies'])
                tracking=layer.get('letterSpacingEm',0)*trial
                if '_legacy_line_spacing' in layer:
                    font=measurer.fonts[0][1];line_height=(sum(font.getmetrics())+layer['_legacy_line_spacing'])/font.size
                else:
                    key='headline' if role=='headline' else 'body'
                    preferred=tokens.values['TYPO-006'][key]
                    line_height=layer.get('lineHeight',min(preferred[1],max(preferred[0],tokens.runtime['defaultLineHeight'][key])))
                try:
                    lines=measurer.wrap(text,box['width'],tracking)
                    mask,metrics=measurer.raster(lines,tracking,line_height,align)
                except DesignRuleError as exc:
                    if exc.code!='TYPO_TEXT_OVERFLOW':raise
                    continue
                if mask.width<=box['width'] and mask.height<=box['height']:
                    if lines!=text.split('\n'):diagnostics.append(diagnostic('TYPO-002','info',element,text,'\n'.join(lines),'Measured wrapping; all original characters retained'))
                    if round(trial)!=round(original_size):diagnostics.append(diagnostic('TYPO-004','info',element,original_size,round(trial),'Font reduced after wrapping within bounded correction loop'))
                    if measurer.fallback_used:diagnostics.append(diagnostic('TYPO-009','info',element,family,sorted(measurer.fallback_used),'Registered cmap-verified fallback runs'))
                    x=round(box['x']+{'left':0,'center':(box['width']-mask.width)/2,'right':box['width']-mask.width}[align]);y=round(box['y'])
                    full=Image.new('L',(w,h));full.paste(mask,(x,y))
                    safe=round(s*tokens.values['GRID-003'])
                    if x<safe or y<safe or x+mask.width>w-safe or y+mask.height>h-safe:
                        raise DesignRuleError('LAYOUT_OUT_OF_BOUNDS','TYPO-003','Measured glyph ink outside resolved text safe area',element)
                    return dict(id=element,role=role,mask=full,color=color,fontSize=round(trial),fontWeight=weight,lineHeight=line_height,repairRounds=correction,metrics=metrics,measuredLines=lines,requestedFont=family,resolvedFont=sorted(measurer.used_fonts),bbox=dict(x=x,y=y,width=mask.width,height=mask.height),text=text),diagnostics
            if correction>0:size*=.5
        raise DesignRuleError('TYPO_TEXT_OVERFLOW','TYPO-003','Cannot fit complete text after two correction rounds',element,original_size,None)

    def contrast_min(self,background,mask,color):
        bbox=mask.getbbox()
        if bbox is None:raise DesignRuleError('POSTER_MISSING_LAYER','TYPO-001','Invisible text')
        region=background.convert('RGB').crop(bbox);ink=mask.crop(bbox)
        foreground=Image.new('RGB',region.size,color);composited=Image.composite(foreground,region,ink)
        # Core ink pixels avoid declaring anti-alias edge blends to be separate text colors.
        samples=(contrast(fg,bg) for fg,bg,a in zip(composited.getdata(),region.getdata(),ink.getdata()) if a>=250)
        minimum=min(samples,default=None)
        if minimum is None:raise DesignRuleError('FONT_UNAVAILABLE','TYPO-009','Text raster has no measurable core ink')
        return minimum

    def validate(self,background,candidate,request,tokens,intent):
        protection=self.subject_mask(request,candidate.subject,tokens,intent)
        occupied=Image.new('L',background.size);diagnostics=list(tokens.diagnostics);measurements=[]
        if not candidate.typography:raise DesignRuleError('POSTER_MISSING_LAYER','TYPO-001','No typography')
        result=background.copy()
        for layer in candidate.typography:
            measured,changes=self.measure(layer,request,tokens);diagnostics+=changes
            mask=measured['mask'];element=measured['id']
            if ImageChops.multiply(mask,protection).getbbox():raise DesignRuleError('TEXT_SUBJECT_COLLISION','VAL-002','Glyph ink intersects visible subject/protection zone',element)
            if ImageChops.multiply(mask,occupied).getbbox():raise DesignRuleError('TEXT_COLLISION','VAL-002','Typography glyph masks overlap',element)
            minimum=tokens.values['COLOR-002']['large' if measured['fontSize']/min(background.size)>=tokens.runtime['largeTextRelativeToShortSide'] else 'normal']
            ratio=self.contrast_min(result,mask,measured['color'])
            repair_rounds=measured['repairRounds']
            if ratio<minimum and intent.get('allowColorRepair',True) and repair_rounds<tokens.values['VAL-007']:
                repair_rounds+=1
                candidates=[(self.contrast_min(result,mask,color),color) for color in tokens.runtime['repairColorChoices']]
                best,color=max(candidates)
                if best>=minimum:
                    diagnostics.append(diagnostic('COLOR-002','info',element,measured['color'],color,'Changed text color against composited glyph region'))
                    measured['color']=color;ratio=best
            if ratio<minimum and intent.get('allowBackdrop',False) and repair_rounds<tokens.values['VAL-007']:
                repair_rounds+=1
                bounds=mask.getbbox();pad=round(min(background.size)*tokens.runtime['backdropPaddingRelativeToShortSide'])
                rect=(max(0,bounds[0]-pad),max(0,bounds[1]-pad),min(result.width,bounds[2]+pad),min(result.height,bounds[3]+pad))
                plate_mask=Image.new('L',result.size);ImageDraw.Draw(plate_mask).rectangle((rect[0],rect[1],rect[2]-1,rect[3]-1),fill=255)
                if not ImageChops.multiply(plate_mask,protection).getbbox() and not ImageChops.multiply(plate_mask,occupied).getbbox():
                    for panel_color,text_color in zip(tokens.runtime['repairColorChoices'],reversed(tokens.runtime['repairColorChoices'])):
                        alpha_mask=plate_mask.point(lambda a:round(a*tokens.runtime['backdropAlpha']))
                        repaired=Image.composite(Image.new('RGB',result.size,panel_color),result,alpha_mask)
                        repaired_ratio=self.contrast_min(repaired,mask,text_color)
                        if repaired_ratio>=minimum:
                            diagnostics.append(diagnostic('COLOR-007','info',element,dict(color=measured['color'],backdrop=None),dict(color=text_color,backdrop=panel_color,alpha=tokens.runtime['backdropAlpha'],bbox=rect),'Explicitly allowed local backdrop verified after alpha compositing'))
                            result=repaired;measured['color']=text_color;ratio=repaired_ratio
                            break
            measured['repairRounds']=repair_rounds
            if ratio<minimum:raise DesignRuleError('TEXT_CONTRAST_LOW','COLOR-002',f'Measured worst contrast {ratio:.3f} below {minimum}',element,ratio,minimum)
            result.paste(Image.new('RGB',result.size,measured['color']),(0,0),mask)
            occupied=ImageChops.lighter(occupied,mask)
            measured['contrast']=ratio;measured.pop('mask')
            measurements.append(measured)
        if not any(item['bbox']['width'] for item in measurements):raise DesignRuleError('POSTER_MISSING_LAYER','TYPO-001','No valid text')
        diagnostics+=self.soft_diagnostics(measurements,request,tokens,candidate)
        score=LayoutScorer().score(measurements,occupied,protection,tokens)
        return ValidatedComposition(candidate,result,diagnostics,measurements,score)

    def soft_diagnostics(self,measured,request,tokens,candidate):
        result=[];short=min(request.layout.width,request.layout.height)
        for item in measured:
            if item['role']=='headline' and not tokens.runtime['headlinePreferredRange'][0]<=item['fontSize']/short<=tokens.runtime['headlinePreferredRange'][1]:
                result.append(diagnostic('TYPO-004','warning',item['id'],item['fontSize']/short,tokens.values['TYPO-004'],'Headline outside preferred range; content preserved'))
        headlines=[item for item in measured if item['role']=='headline']
        for item in measured:
            key='headline' if item['role']=='headline' else 'body'
            preferred=tokens.values['TYPO-006'][key]
            if not preferred[0]<=item['lineHeight']<=preferred[1]:
                result.append(diagnostic('TYPO-006','warning',item['id'],item['lineHeight'],preferred,'Explicit line height outside soft range; glyph collision gate still applies'))
            if headlines and item['role'] in ('secondary','body'):
                ratio=item['fontSize']/headlines[0]['fontSize'];limits=tokens.values['TYPO-005'][item['role']]
                if not limits[0]<=ratio<=limits[1]:result.append(diagnostic('TYPO-005','warning',item['id'],ratio,limits,'Measured text hierarchy outside soft preference'))
        families={f for item in measured for f in item['resolvedFont']}
        if len(families)>tokens.values['TYPO-007']['families']:
            result.append(diagnostic('TYPO-007','warning','typography',len(families),tokens.values['TYPO-007']['families'],'Font family preference exceeded'))
        preferred_count=tokens.values['TYPO-008']
        if not preferred_count[0]<=len({item['role'] for item in measured})<=preferred_count[1]:
            result.append(diagnostic('TYPO-008','warning','typography',len(measured),preferred_count,'Text layer preference is soft; a single headline remains valid'))
        if len({item['fontWeight'] for item in measured})>tokens.values['TYPO-007']['weights']:
            result.append(diagnostic('TYPO-007','warning','typography',len({item['fontWeight'] for item in measured}),tokens.values['TYPO-007']['weights'],'Weight preference exceeded'))
        width=candidate.subject['width'];preferred=tokens.values['COMP-005']
        if not preferred[0]<=width<=preferred[1]:result.append(diagnostic('COMP-005','warning','subject',width,preferred,'Subject width outside soft preference'))
        return result


class LayoutScorer:
    def score(self,measurements,occupied,protection,tokens):
        # Measured coverage is not semantic whitespace, salience or objective beauty.
        union=ImageChops.lighter(occupied,protection)
        occupied_fraction=sum(1 for a in union.getdata() if a>0)/(union.width*union.height)
        components=dict(color=min(1,min(item['contrast'] for item in measurements)/tokens.values['COLOR-002']['normal']),interaction=1)
        weights=tokens.values['VAL-005'];denominator=sum(weights[k] for k in components)
        score=sum(weights[k]*v for k,v in components.items())/denominator if denominator else 0
        return dict(experimental=True,measuredScore=round(score,4),components=components,foregroundPixelCoverage=round(occupied_fraction,4),
                    disabled=['hierarchy','whitespace','alignment','reference','opticalBalance','salience'],weightsUsed={k:weights[k] for k in components})


class DesignCompositionPipeline:
    def generate(self,request,spec,render_copy=True):
        from .client import PosterGenerator
        from .validation import validate_request
        validate_request(request)
        data=DesignRuleLoader().load();intent=request.style.design_intent
        tokens=DesignTokenResolver().resolve(data,intent);validator=LayoutValidator()
        provenance=validator.assets(request,spec,intent)
        if request.layout.width*request.layout.height>tokens.runtime['maxCanvasPixels']:
            raise DesignRuleError('LAYOUT_OUT_OF_BOUNDS','GRID-002','Canvas pixel budget exceeded')
        # Invalid colors fail before existing renderer color parsing can substitute a default.
        for color in (request.style.primary_color,request.style.secondary_color,request.style.accent_color):
            try:ImageColor.getrgb(color)
            except Exception as exc:raise DesignRuleError('RULESET_INVALID','COLOR-001','Invalid input color') from exc
        from .font_provider import manifest
        font_records=manifest().get('fonts',[])
        families={layer.get('fontFamily',request.style.font_family) for layer in intent.get('typography',[])} | {request.style.font_family} | set(tokens.runtime['fallbackFamilies'])
        licenses=[{k:record[k] for k in ('family','source','license')} for record in font_records if record.get('family') in families and record.get('license')]
        if families-set(record['family'] for record in licenses):
            raise DesignRuleError('ASSET_LICENSE_UNKNOWN','VAL-004','Registered font license provenance is incomplete')
        generator=PosterGenerator();decision=generator.policy.decide(request)
        planner=LayoutPlanner()
        candidates=planner.candidates(request,intent,tokens)
        if request.style.source_credit_text:
            short=min(request.layout.width,request.layout.height);grid=planner.grid(request,tokens)
            credit_h=short*tokens.runtime['creditBoxHeightRelativeToShortSide']/request.layout.height
            for candidate in candidates:
                candidate.typography.append(dict(id='source-credit',role='body',text=request.style.source_credit_text,fontFamily='sans',fontWeight=400,
                    fontSizeRelativeToShortSide=tokens.runtime['creditFontSizeRelativeToShortSide'],
                    box=dict(x=grid['safeX'],y=1-grid['safeY']-credit_h,width=1-2*grid['safeX'],height=credit_h)))
        valid=[];rejected=[]
        for candidate in candidates:
            try:
                CompositionAdapter.render_subject(request,candidate.subject)
                base=generator.image_pipeline.build_background(request,decision)
                composition=validator.validate(base,candidate,request,tokens,intent)
                valid.append(composition)
            except DesignRuleError as exc:
                rejected.append(dict(candidate=candidate.id,code=exc.code,diagnostics=exc.diagnostics))
        if not valid:
            failure=DesignRuleError(rejected[0]['code'] if rejected else 'LAYOUT_OUT_OF_BOUNDS','VAL-001','No candidate passed the hard gate')
            failure.diagnostics=[item for result in rejected for item in result['diagnostics']]
            raise failure
        selected=max(valid,key=lambda item:(item.score['measuredScore'],-sum(max(0,len(m['measuredLines'])-len(m['text'].split('\n'))) for m in item.measurements),-len([d for d in item.diagnostics if d['original']!=d['resolved']])))
        # Stable ties preserve template order. No random regeneration/candidate loop.
        CompositionAdapter.render_subject(request,selected.candidate.subject)
        result=selected.image if render_copy else generator.image_pipeline.build_background(request,decision)
        report=dict(ok=True,designVersion=tokens.version,feature='design-rules-v1',candidate=selected.candidate.id,
            candidatesEvaluated=len(candidates),grid=planner.grid(request,tokens),scores=selected.score,diagnostics=tokens.history+selected.diagnostics+[diagnostic('GRID-006','info','subject', {k:v/(request.layout.width if k in ('x','width') else request.layout.height) for k,v in spec.subject['position'].items()}, selected.candidate.subject, 'Resolved candidate placement; explicit subject positions are retained')],
            measurements=selected.measurements,errors=[],rejectedCandidates=rejected,
            resolvedDesignTokens=dict(values=tokens.values,provenance=tokens.provenance,history=tokens.history),assetProvenance=provenance,
            fontProvenance=dict(source='registered project font manifest',license='SIL Open Font License',validation='cmap coverage and actual Pillow metrics; registered font license references',entries=licenses),
            visualReview=dict(enabled=True,requiredForAestheticJudgment=True),hardRulesChecked=[r['id'] for r in data['rules'] if r['severity']=='hard'])
        request.style.design_report=report
        return PosterResult(str(generator._save_image(result)),decision,['Design rules v1 hard gate passed; aesthetic heuristics remain experimental.'])
