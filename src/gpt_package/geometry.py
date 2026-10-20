"""Explicit GPT-authored geometry in final-canvas pixels, behind the subject."""
import math
import re
from PIL import Image, ImageDraw
from .errors import ValidationError


def validate_geometry_layers(layers, width, height):
    if not isinstance(layers, list) or len(layers) > 24:
        raise ValidationError('geometry_layers must be an array with at most 24 shapes')
    result = []
    for raw in layers:
        if not isinstance(raw, dict):
            raise ValidationError('Each geometry layer must be an object')
        item = dict(raw)
        if item.get('shape') not in ('circle', 'rectangle', 'line'):
            raise ValidationError('Geometry shape must be circle, rectangle or line')
        for key in ('x', 'y', 'width', 'height'):
            v = item.get(key)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise ValidationError(f'Geometry {key} must be finite')
        if not (0 <= item['x'] < width and 0 <= item['y'] < height and
                0 < item['width'] <= width-item['x'] and 0 < item['height'] <= height-item['y']):
            raise ValidationError('Geometry box must fit canvas')
        if item['shape'] == 'circle' and item['width'] != item['height']:
            raise ValidationError('Circle width and height must match')
        item.setdefault('fill', None)
        item.setdefault('stroke', None)
        for key in ('fill', 'stroke'):
            if item[key] is not None and not re.fullmatch(r'#[0-9a-fA-F]{6}', str(item[key])):
                raise ValidationError('Geometry colors must be #RRGGBB or null')
        if item['shape'] == 'line' and not item['stroke']:
            raise ValidationError('Line requires stroke')
        if not item['fill'] and not item['stroke']:
            raise ValidationError('Geometry requires fill or stroke')
        opacity = item.setdefault('opacity', .3)
        if isinstance(opacity, bool) or not isinstance(opacity, (int, float)) or not math.isfinite(opacity) or not 0 <= opacity <= 1:
            raise ValidationError('Geometry opacity must be 0–1')
        stroke = item.setdefault('stroke_width', 2)
        if isinstance(stroke, bool) or not isinstance(stroke, (int, float)) or not math.isfinite(stroke) or not 1 <= stroke <= 64:
            raise ValidationError('Geometry stroke_width must be 1–64')
        result.append(item)
    return result


def render_geometry(image, layers):
    for item in layers:
        overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        def color(value):
            return tuple(int(value[i:i+2],16) for i in (1,3,5)) + (round(item['opacity']*255),) if value else None
        x,y,w,h = (item[k] for k in ('x','y','width','height'))
        box = (x,y,x+w-1,y+h-1)
        if item['shape'] == 'line':
            draw.line(box,fill=color(item['stroke']),width=round(item['stroke_width']))
        else:
            method = draw.ellipse if item['shape']=='circle' else draw.rectangle
            method(box,fill=color(item['fill']),outline=color(item['stroke']),width=round(item['stroke_width']))
        composited = Image.alpha_composite(image.convert('RGBA'), overlay)
        image.paste(composited if image.mode=='RGBA' else composited.convert(image.mode))
