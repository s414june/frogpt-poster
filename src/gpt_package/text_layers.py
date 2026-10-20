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
        result.append(item)
    return result


def render_text_layers(image, layers):
    layers = validate_text_layers(layers, *image.size)
    draw = ImageDraw.Draw(image)
    planned = []
    for item in layers:
        _, path = resolve_font_weight(item['font_family'], item['font_weight'])
        font = ImageFont.truetype(path, round(item['font_size']))
        box = draw.multiline_textbbox((0, 0), item['text'], font=font,
                                      spacing=item['line_spacing'], align=item['align'])
        width, height = box[2] - box[0], box[3] - box[1]
        if width > item['width'] or height > item['height']:
            raise ValidationError('Text overflows layer box; reduce font_size, enlarge box or insert newlines')
        offset = {'left': 0, 'center': (item['width'] - width) / 2,
                  'right': item['width'] - width}[item['align']]
        planned.append((item, font, (item['x'] + offset - box[0], item['y'] - box[1])))
    for item, font, position in planned:
        draw.multiline_text(position, item['text'], font=font, fill=item['color'],
                            spacing=item['line_spacing'], align=item['align'])
    return {'selected_font': 'per-layer registered fonts', 'layout_mode': 'explicit_text_layers',
            'layout_variant': None}
