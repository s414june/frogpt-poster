"""Load poster request from a text file (JSON)."""

import json
from pathlib import Path

from .errors import ValidationError
from .font_discovery import discover_open_source_fonts
from .types import PosterAssetSet, PosterLayout, PosterRequest, PosterStyle


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
    style = payload.get("style", {})
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
        style=PosterStyle(
            primary_color=str(style.get("primary_color", "#F6F1E8")),
            secondary_color=str(style.get("secondary_color", "#A8BFA8")),
            accent_color=str(style.get("accent_color", "#6D8A72")),
            subject=str(style.get("subject", "")),
            panel_ratio=float(style.get("panel_ratio", 0.24)),
            title_max_lines=int(style.get("title_max_lines", 2)),
            body_max_lines=int(style.get("body_max_lines", 4)),
            background_shape_count=int(style.get("background_shape_count", 0)),
            background_shape_alpha_min=int(style.get("background_shape_alpha_min", 10)),
            background_shape_alpha_max=int(style.get("background_shape_alpha_max", 28)),
            variation_token=str(style.get("variation_token", "")),
        ),
        allow_ai_fallback=bool(payload.get("allow_ai_fallback", True)),
    )
    if not request.assets.open_source_font_paths:
        request.assets.open_source_font_paths = discover_open_source_fonts()
    return request
