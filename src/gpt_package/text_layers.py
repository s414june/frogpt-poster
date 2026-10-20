"""Validated, explicit typography for GPT-directed poster compositions."""
import math
import re
from PIL import ImageDraw, ImageFont
from .errors import ValidationError
from .font_registry import resolve_font_family, resolve_font_weight


def validate_text_layers(layers, width, height):
    if not isinstance(layers, list) or len(layers) > 24:
        raise ValidationError('text_layers must be an array with at most 24 layers')
    result = []
    for layer in layers:
        if not isinstance(layer, dict):
            raise ValidationError('Each text layer must be an object')
        item = dict(layer)
        text = item.get('text')
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValidationError('Layer text must contain 1–4000 characters')
        for key in ('x', 'y', 'width', 'height', 'font_size'):
            value = item.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValidationError(f'Layer {key} must be a finite number')
        if not (0 <= item['x'] < width and 0 <= item['y'] < height and
                0 < item['width'] <= width - item['x'] and
                0 < item['height'] <= height - item['y'] and 1 <= item['font_size'] <= 512):
            raise ValidationError('Text layer box must fit canvas; font_size must be 1–512')
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', str(item.get('color', ''))):
            raise ValidationError('Layer color must be #RRGGBB')
        item.setdefault('align', 'left')
        if item['align'] not in ('left', 'center', 'right'):
            raise ValidationError('Layer align must be left, center or right')
        item.setdefault('line_spacing', 4)
        spacing = item['line_spacing']
        if isinstance(spacing, bool) or not isinstance(spacing, (int, float)) or not math.isfinite(spacing) or not 0 <= spacing <= 512:
            raise ValidationError('Layer line_spacing must be 0–512')
        item['font_family'], _ = resolve_font_family(item.get('font_family', 'sans'))
        item['font_weight'], _ = resolve_font_weight(item['font_family'], item.get('font_weight', 400))
        tracking = item.setdefault('letter_spacing', 0)
        if isinstance(tracking, bool) or not isinstance(tracking, (int, float)) or not math.isfinite(tracking) or not 0 <= tracking <= item['font_size'] * .25:
            raise ValidationError('letter_spacing must be 0–0.25 em in pixels')
        if not isinstance(item.get('allow_overlap', False), bool):
            raise ValidationError('allow_overlap must be boolean')
        result.append(item)
    return result


def _tracked_glyphs(draw, item, font):
    lines = item['text'].split('\n')
    widths = [font.getlength(line) + max(0,len(line)-1)*item['letter_spacing'] for line in lines]
    maximum = max(widths)
    asc,desc=font.getmetrics()
    glyphs=[]; boxes=[]
    for row,line in enumerate(lines):
        offset={'left':0,'center':(maximum-widths[row])/2,'right':maximum-widths[row]}[item['align']]
        baseline=row*(asc+desc+item['line_spacing'])
        for i,char in enumerate(line):
            x=offset+font.getlength(line[:i])+i*item['letter_spacing']
            glyphs.append((char,x,baseline))
            boxes.append(draw.textbbox((x,baseline),char,font=font,anchor='ls'))
    box=(min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes))
    return glyphs,box


def render_text_layers(image, layers, style=None):
    layers = validate_text_layers(layers, *image.size)
    draw = ImageDraw.Draw(image)
    planned, measured = [], []
    for item in layers:
        _, path = resolve_font_weight(item['font_family'], item['font_weight'])
        from .font_provider import materialize_font
        font = ImageFont.truetype(materialize_font(path), round(item['font_size']))
        tracking = item['letter_spacing']
        if tracking:
            glyphs, box = _tracked_glyphs(draw,item,font)
            width,height=box[2]-box[0],box[3]-box[1]
        else:
            box = draw.multiline_textbbox((0, 0), item['text'], font=font,
                                          spacing=item['line_spacing'], align=item['align'])
            width, height = box[2]-box[0], box[3]-box[1]
        if width > item['width'] or height > item['height']:
            raise ValidationError('Text overflows layer box; reduce font_size, enlarge box or insert newlines')
        offset = {'left':0, 'center':(item['width']-width)/2, 'right':item['width']-width}[item['align']]
        measured.append((item,item['x']+offset,item['y'],width,height))
        planned.append((item,font,box))
    report = {}
    if getattr(style, 'typography_grid', False):
        from .layout_grid import place_ink_boxes
        placements, report = place_ink_boxes(measured,*image.size,style.protected_regions)
    else:
        placements = [(x,y,x+w,y+h) for _,x,y,w,h in measured]
    for (item,font,box), rect in zip(planned,placements):
        x,y = rect[:2]
        if not item['letter_spacing']:
            draw.multiline_text((x-box[0],y-box[1]),item['text'],font=font,fill=item['color'],
                                spacing=item['line_spacing'],align=item['align'])
        else:
            glyphs,_ = _tracked_glyphs(draw,item,font)
            for char,gx,gy in glyphs:
                draw.text((x-box[0]+gx,y-box[1]+gy),char,font=font,fill=item['color'],anchor='ls')
    if style is not None:
        style.layout_report = report
    return {'selected_font':'per-layer registered fonts','layout_mode':'explicit_text_layers',
            'layout_variant':None,'layout_report':report}
