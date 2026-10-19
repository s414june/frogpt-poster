"""Reference image helpers, including Pexels API access and palette extraction."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from PIL import Image

from .errors import ValidationError
from .types import PosterRequest


def fetch_pexels_references(
    query: str,
    api_key: str,
    per_page: int = 3,
    orientation: str = "portrait",
) -> list[dict]:
    token = (api_key or "").strip()
    if not token:
        raise ValidationError("PEXELS_API_KEY is required when pexels_query is used")
    q = query.strip()
    if not q:
        raise ValidationError("pexels_query must not be empty")
    per_page = max(1, min(10, per_page))
    orientation = orientation if orientation in ("landscape", "portrait", "square") else "portrait"

    url = (
        "https://api.pexels.com/v1/search?"
        f"query={quote_plus(q)}&per_page={per_page}&orientation={orientation}"
    )
    req = Request(url, headers={"Authorization": token, "User-Agent": "frogpt-poster/1.0"})
    with urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    photos = payload.get("photos", [])
    result: list[dict] = []
    for photo in photos:
        src = photo.get("src", {})
        image_url = src.get("large2x") or src.get("large") or src.get("original")
        if not image_url:
            continue
        result.append(
            {
                "source": "pexels",
                "photo_id": photo.get("id"),
                "url": image_url,
                "page_url": photo.get("url"),
                "photographer": photo.get("photographer"),
                "photographer_url": photo.get("photographer_url"),
            }
        )
    return result


def apply_style_from_reference(request: PosterRequest, reference_image_path: str) -> bool:
    path = Path(reference_image_path)
    if not path.is_file():
        return False
    try:
        img = Image.open(path).convert("RGB").resize((64, 64))
    except OSError:
        return False

    colors = img.getcolors(maxcolors=64 * 64) or []
    if not colors:
        return False
    ranked = sorted(colors, key=lambda item: item[0], reverse=True)[:8]
    palette = [rgb for _, rgb in ranked]
    if len(palette) < 3:
        return False

    by_luma = sorted(palette, key=_luma, reverse=True)
    request.style.primary_color = _to_hex(by_luma[0])
    request.style.secondary_color = _to_hex(by_luma[min(1, len(by_luma) - 1)])
    request.style.accent_color = _to_hex(by_luma[-1])
    return True


def _luma(rgb: tuple[int, int, int]) -> float:
    return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722


def _to_hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"

