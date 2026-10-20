"""Generate four reproducible examples using project-drawn product and saved stock.

No image model, network, uploads, or newly copied third-party assets.
"""
import base64
import io
import json
import os
from pathlib import Path
from PIL import Image, ImageDraw
from gpt_package.openai_tool import handle_tool_call

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'examples/design-rules-v1'


def fixture_subject():
    image=Image.new('RGBA',(400,600));draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((90,100,310,540),radius=32,fill='#12646A',outline='#063E43',width=6)
    draw.rounded_rectangle((145,35,255,130),radius=10,fill='#173844')
    draw.rounded_rectangle((112,235,288,408),radius=8,fill='#ECDFB8')
    draw.line((145,280,255,280),fill='#12646A',width=12)
    draw.line((145,330,230,330),fill='#12646A',width=8)
    return image


def data_url(image):
    buf=io.BytesIO();image.save(buf,'PNG')
    return 'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()


def generate():
    OUT.mkdir(parents=True,exist_ok=True)
    subject=fixture_subject();subject.save(OUT/'subject-original.png')
    common=dict(width=720,height=900,title='把日常，\n留給美好。',body='A SIMPLE DAILY RITUAL\n簡單配方，清爽生活。',
        subject_image_base64=[data_url(subject)],subject_source='user_upload',primary_color='#F5F1E8',
        design_rules_v1=True,geometry_enabled=False)
    rights={'source':'project_original','license':'FroGPT original test fixture','rightsConfirmed':True,'posterTextFree':True}
    variants={
        'product':dict(design_intent=dict(stylePreset='editorial',subjectPosition=dict(x=.56,y=.25,width=.36,height=.50),assetProvenance={'subject':rights},typography=[
            dict(id='headline',role='headline',text='把日常，\n留給美好。',fontSizeRelativeToShortSide=.08,box=dict(x=.08,y=.08,width=.42,height=.32)),
            dict(id='body',role='body',text='A SIMPLE DAILY RITUAL\n簡單配方，清爽生活。',fontSizeRelativeToShortSide=.033,box=dict(x=.08,y=.50,width=.40,height=.15))])),
        'type-led':dict(title='LESS,\nBUT BETTER.',body='少一點，剛剛好。',design_intent=dict(stylePreset='bold-commercial',subjectPosition=dict(x=.63,y=.54,width=.25,height=.30),assetProvenance={'subject':rights})),
        'photo-background':dict(reference_library_id='pexels-167699',design_intent=dict(stylePreset='minimal',allowBackdrop=True,assetProvenance={'subject':rights})),
        'no-geometry':dict(title='剛剛好的日常',body='MAKE ROOM FOR SIMPLE THINGS',primary_color='#DBE9EA',design_intent=dict(stylePreset='minimal',assetProvenance={'subject':rights})),
    }
    index=[]
    os.environ['FROGPT_FONT_SOURCE']='local';os.environ['FROGPT_BLOB_ENABLED']='false'
    os.environ['POSTER_OUTPUT_DIR']=str(OUT/'temporary')
    for name,patch in variants.items():
        args={**common,**patch}
        result=handle_tool_call(args)
        if not result.get('rendered'):raise RuntimeError(f'{name}: '+json.dumps(result,ensure_ascii=False))
        target=OUT/(name+'.png');target.write_bytes(base64.b64decode(result['output_image_base64']))
        Path(result['output_path']).unlink(missing_ok=True)
        report=result['design_report']
        (OUT/(name+'.diagnostics.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        request={k:v for k,v in args.items() if k!='subject_image_base64'}
        request['fixtureSubject']='subject-original.png; script encodes actual bytes at runtime'
        (OUT/(name+'.request.json')).write_text(json.dumps(request,ensure_ascii=False,indent=2)+'\n')
        bad=dict(args,design_intent=dict(args['design_intent'],typography=[dict(id='impossible',text='重要文字',box=dict(x=.99,y=.1,width=.1,height=.2))]))
        failure=handle_tool_call(bad)
        if failure.get('rendered'):raise AssertionError('Hard violation rendered')
        (OUT/(name+'.failure.json')).write_text(json.dumps({k:v for k,v in failure.items() if k in ('ok','rendered','error_code','diagnostics','errors','designVersion')},ensure_ascii=False,indent=2)+'\n')
        index.append(dict(name=name,image=target.name,candidate=report['candidate'],sha256=result['output_image_sha256'],source_credits=result['source_credits'],rendered=True))
    (OUT/'index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n')
    for temporary in (OUT/'temporary').glob('*.png'):temporary.unlink()
    (OUT/'temporary').rmdir()
    print(json.dumps(index,ensure_ascii=False))
    return index

if __name__=='__main__':generate()
