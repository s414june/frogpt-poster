"""Explicit runtime font families; never silently substitute a requested font."""
from pathlib import Path
from .errors import ValidationError

FONT_FAMILIES = {
    'sans': ['Noto_Sans_TC/static/NotoSansTC-Regular.ttf', 'Noto_Sans_TC/static/NotoSansTC-Bold.ttf'],
    'serif': ['Noto_Serif_TC/static/NotoSerifTC-Regular.ttf', 'Noto_Serif_TC/static/NotoSerifTC-Bold.ttf'],
    'kai': ['LXGW_WenKai_TC/LXGWWenKaiTC-Regular.ttf'],
    'rounded': ['Chiron_GoRound_TC/static/ChironGoRoundTC-Regular.ttf'],
}
ALIASES = {'黑體': 'sans', '明體': 'serif', '宋體': 'serif', '思源宋體': 'serif',
           'noto serif tc': 'serif', '楷體': 'kai', '霞鶩文楷': 'kai', '圓體': 'rounded'}


def resolve_font_family(value):
    if not isinstance(value, str):
        raise ValidationError('font_family must be a string')
    name = value.strip().lower()
    name = ALIASES.get(name, name)
    if name not in FONT_FAMILIES:
        raise ValidationError('Unsupported font_family. Available: sans (黑體), serif (明體), kai (楷體), rounded (圓體).')
    paths = [str(Path('assets/fonts') / p) for p in FONT_FAMILIES[name]]
    if not all(Path(p).is_file() for p in paths):
        raise ValidationError(f'Requested font family is not deployed: {name}; do not substitute another font.')
    return name, paths


def resolve_font_weight(family, weight=400):
    """Resolve actual deployed weights, never simulate bold by thickening strokes."""
    aliases = {'normal': 400, 'regular': 400, 'bold': 700}
    if isinstance(weight, str):
        weight = aliases.get(weight.lower(), weight)
    if isinstance(weight, bool) or weight not in (400, 700):
        raise ValidationError('font_weight must be 400 or 700 (normal, bold)')
    name, paths = resolve_font_family(family)
    if name not in ('sans', 'serif') and weight != 400:
        raise ValidationError(f'{name} only has font_weight=400 deployed; choose sans/serif for bold')
    index = {400: 0, 700: 1}[weight] if name in ('sans', 'serif') else 0
    return weight, paths[index]
