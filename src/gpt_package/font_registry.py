"""Explicit runtime font families; never silently substitute a requested font."""
from pathlib import Path
from .errors import ValidationError

FONT_FAMILIES = {
    'sans': ['Noto_Sans_TC/static/NotoSansTC-Regular.ttf', 'Noto_Sans_TC/static/NotoSansTC-Medium.ttf'],
    'serif': ['Noto_Serif_TC/static/NotoSerifTC-Regular.ttf', 'Noto_Serif_TC/static/NotoSerifTC-Medium.ttf'],
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
