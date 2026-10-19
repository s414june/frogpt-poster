"""Load poster request from a text file (JSON)."""

import json
from pathlib import Path

from .errors import ValidationError
from .font_discovery import discover_open_source_fonts
from .types import PosterAssetSet, PosterLayout, PosterRequest


def load_request_from_text_file(path: str) -> PosterRequest:
    file_path = Path(path)
    if not file_path.is_file():
        raise ValidationError(f"text input file does not exist: {path}")
    try:
        raw = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValidationError(f"failed reading text input file: {path}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "text input must be valid JSON with title/body/assets/layout"
        ) from exc

    assets = payload.get("assets", {})
    layout = payload.get("layout", {})
    request = PosterRequest(
        title=str(payload.get("title", "")),
        body=str(payload.get("body", "")),
        assets=PosterAssetSet(
            user_image_paths=list(assets.get("user_image_paths", [])),
            open_source_font_paths=list(assets.get("open_source_font_paths", [])),
        ),
        layout=PosterLayout(
            width=int(layout.get("width", 1080)),
            height=int(layout.get("height", 1350)),
        ),
        allow_ai_fallback=bool(payload.get("allow_ai_fallback", True)),
    )
    if not request.assets.open_source_font_paths:
        request.assets.open_source_font_paths = discover_open_source_fonts()
    return request
