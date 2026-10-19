"""Validation for poster tool input."""

from pathlib import Path

from .errors import ValidationError
from .types import PosterRequest

_TITLE_MAX_LEN = 120
_BODY_MAX_LEN = 4000
_MIN_SIZE = 256
_MAX_SIZE = 4096


def validate_request(request: PosterRequest) -> None:
    title = request.title.strip()
    body = request.body.strip()
    if not title:
        raise ValidationError("title is required")
    if not body:
        raise ValidationError("body is required")
    if len(title) > _TITLE_MAX_LEN:
        raise ValidationError(f"title must be <= {_TITLE_MAX_LEN} characters")
    if len(body) > _BODY_MAX_LEN:
        raise ValidationError(f"body must be <= {_BODY_MAX_LEN} characters")

    width = request.layout.width
    height = request.layout.height
    if width < _MIN_SIZE or width > _MAX_SIZE:
        raise ValidationError(f"width must be between {_MIN_SIZE} and {_MAX_SIZE}")
    if height < _MIN_SIZE or height > _MAX_SIZE:
        raise ValidationError(f"height must be between {_MIN_SIZE} and {_MAX_SIZE}")

    if not request.allow_ai_fallback and not request.assets.user_image_paths:
        raise ValidationError(
            "user_image_paths is required when allow_ai_fallback is false"
        )

    for path in request.assets.user_image_paths:
        if not Path(path).is_file():
            raise ValidationError(f"user image does not exist: {path}")
    for path in request.assets.open_source_font_paths:
        if not Path(path).is_file():
            raise ValidationError(f"open-source font does not exist: {path}")

