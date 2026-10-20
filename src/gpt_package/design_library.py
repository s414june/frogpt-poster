"""Local inspiration catalog; never used as finished background assets."""
import base64
import io
import json
from pathlib import Path
from PIL import Image
from .errors import ValidationError

DESIGN_LIBRARY_ROOT = Path(__file__).resolve().parents[2] / 'assets' / 'design-references'


def load_design_references(root=None):
    """Reload JSON on every request so additions need no process restart."""
    root = Path(root or DESIGN_LIBRARY_ROOT)
    entries = []
    for category, credit_required in (('attributed', True), ('original', False)):
        folder = root / category
        manifest = folder / 'manifest.json'
        if not manifest.exists():
            continue
        try:
            payload = json.loads(manifest.read_text(encoding='utf-8'))
            items = payload['items']
            if not isinstance(items, list):
                raise ValueError('items must be an array')
        except (OSError, ValueError, KeyError) as exc:
            raise ValidationError(f'Invalid design reference manifest: {category}') from exc
        # Scan image files on demand; JSON supplies attribution and optional labels.
        registered = {str(item.get('file', '')).replace('\\', '/') for item in items if isinstance(item, dict)}
        for image_path in sorted(folder.rglob('*')):
            if image_path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'} or not image_path.is_file():
                continue
            relative = image_path.relative_to(folder).as_posix()
            if relative not in registered:
                if credit_required:
                    raise ValidationError(f'Add author metadata to attributed/manifest.json for: {relative}')
                items.append({'id': str(Path(relative).with_suffix('')), 'file': relative})
        for item in items:
            if not isinstance(item, dict) or not item.get('id') or not item.get('file'):
                raise ValidationError('Design reference requires id and file')
            path = (folder / str(item['file']).replace('\\', '/')).resolve()
            if not path.is_relative_to(folder.resolve()):
                raise ValidationError('Design reference file must remain inside its category folder')
            if not path.is_file():
                raise ValidationError(f'Missing design reference file: {item["id"]}')
            author = str(item.get('author', '')).strip()
            if credit_required and (not author or author.lower() == 'unknown'):
                raise ValidationError('Attributed design references require a real author')
            reference_id = f'{category}/{item["id"]}'
            if any(entry['id'] == reference_id for entry in entries):
                raise ValidationError('Duplicate design reference id')
            entries.append({'id': reference_id, 'category': category, 'title': item.get('title', item['id']),
                'tags': item.get('tags', []), 'author': author, 'source_url': item.get('source_url', ''),
                'credit_required': credit_required,
                'credit_label': (str(item.get('credit_label', '')).strip() or author) if credit_required else '',
                'path': str(path)})
    return entries


def design_catalog():
    result = []
    for entry in load_design_references():
        item = {k: v for k, v in entry.items() if k != 'path'}
        try:
            with Image.open(entry['path']) as source:
                source.load()
                preview = source.convert('RGB')
                preview.thumbnail((320, 320))
                buf = io.BytesIO()
                preview.save(buf, format='JPEG', quality=65)
                item['preview_data_url'] = 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()
        except OSError as exc:
            raise ValidationError(f'Unreadable design reference: {entry["id"]}') from exc
        result.append(item)
    return result


def join_credit_labels(labels):
    """One unlabeled row, stable order, deduplicated, no line breaks."""
    labels = [' '.join(str(label).split()) for label in labels if label]
    return ' · '.join(dict.fromkeys(label for label in labels if label))
