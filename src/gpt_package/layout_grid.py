"""Bounded baseline-grid placement using measured ink rectangles."""
import math
from .errors import ValidationError


def grid_spec(width, height):
    unit = max(4, round(min(width, height) / 100))
    margin = math.ceil(min(width, height) * .05 / unit) * unit
    return dict(unit=unit, margin=margin, columns=12, gutter=2 * unit,
                column_width=(width - 2 * margin - 22 * unit) / 12,
                minimum_gap=2 * unit, max_auto_shift=8 * unit)


def validate_regions(regions, width, height):
    if not isinstance(regions, list) or len(regions) > 24:
        raise ValidationError('protected_regions must be an array of at most 24 rectangles')
    for r in regions:
        if not isinstance(r, dict) or any(isinstance(r.get(k), bool) or
            not isinstance(r.get(k), (int, float)) or not math.isfinite(r[k]) for k in ('x','y','width','height')):
            raise ValidationError('protected_regions require finite x/y/width/height in canvas pixels')
        if not (r['x'] >= 0 and r['y'] >= 0 and r['width'] > 0 and r['height'] > 0 and
                r['x'] + r['width'] <= width and r['y'] + r['height'] <= height):
            raise ValidationError('protected region must fit canvas')
    return regions


def _near(a, b, gap):
    return a[0] < b[2] + gap and a[2] + gap > b[0] and a[1] < b[3] + gap and a[3] + gap > b[1]


def place_ink_boxes(measured, width, height, protected_regions):
    """Keep font size fixed; snap and move only within eight grid units."""
    spec = grid_spec(width, height)
    unit, margin, gap = spec['unit'], spec['margin'], spec['minimum_gap']
    occupied = [(r['x'],r['y'],r['x']+r['width'],r['y']+r['height']) for r in protected_regions]
    placements, report = [], {'grid': spec, 'adjustments': [], 'warnings': []}
    if not protected_regions:
        report['warnings'].append(dict(code='protected_regions_missing', message='Subject clearance was not checked; supply visually identified protected_regions'))
    offsets = sorted(((dx,dy) for dx in range(-8,9) for dy in range(-8,9)),
                     key=lambda v: (v[0]*v[0]+v[1]*v[1], abs(v[0]),v[1],v[0]))
    for index, (item, original_x, original_y, w, h) in enumerate(measured):
        x, y = round(original_x/unit)*unit, round(original_y/unit)*unit
        found = None
        for dx,dy in offsets:
            nx,ny=x+dx*unit,y+dy*unit
            if math.hypot(nx-original_x,ny-original_y) > spec['max_auto_shift']:
                continue
            rect=(nx,ny,nx+w,ny+h)
            if nx < margin or ny < margin or nx+w > width-margin or ny+h > height-margin:
                continue
            if not item.get('allow_overlap', False) and any(_near(rect,r,gap) for r in occupied):
                continue
            found=rect
            break
        if found is None:
            raise ValidationError(f'Layer {index}: cannot maintain safe margin and subject/text spacing within eight grid units; revise layout or protected_regions')
        placements.append(found)
        occupied.append(found)
        if found[:2] != (original_x,original_y):
            report['adjustments'].append(dict(layer=index,from_xy=[original_x,original_y],to_xy=list(found[:2])))
    # Large gaps may be intentional. Flag only consecutive blocks in the same explicit group.
    for index in range(1,len(measured)):
        item=measured[index][0]; prev=measured[index-1][0]
        if item.get('group') and item.get('group') == prev.get('group'):
            distance=placements[index][1]-placements[index-1][3]
            if distance > max(item['font_size'],prev['font_size'])*2:
                report['warnings'].append(dict(layer=index,code='large_group_gap',gap=distance))
    return placements, report
