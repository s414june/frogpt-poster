"""Reference image helpers, including Pexels API access and palette extraction."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from urllib.parse import quote_plus, urlparse
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


def resolve_reference_url(url: str) -> dict:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if "pexels.com" not in host or "/photo/" not in parsed.path:
        return {"source": "url", "url": url, "page_url": url}

    metadata = {}
    try:
        metadata = _fetch_pexels_page_metadata(url)
    except Exception:
        metadata = {"photo_id": _extract_photo_id(url), "page_url": url}
    photo_id = metadata.get("photo_id")
    image_url = metadata.get("content_url") or metadata.get("og_image") or _fallback_pexels_image_url(photo_id) or url
    photographer = metadata.get("photographer") or "Unknown"
    return {
        "source": "pexels",
        "photo_id": photo_id,
        "url": image_url,
        "page_url": metadata.get("page_url") or url,
        "photographer": photographer,
        "credit_label": build_credit_label(
            {
                "source": "pexels",
                "photographer": photographer,
            }
        ),
    }


def build_credit_label(source_credit: dict) -> str:
    source = str(source_credit.get("source", "")).strip().lower()
    if source == "pexels":
        name = str(source_credit.get("photographer", "")).strip() or "Unknown"
        return f"{name}/Pexels"
    if source == "generated_or_uploaded_base64":
        return ""
    if source == "local_reference_path":
        name = str(source_credit.get("label", "")).strip() or "Reference"
        return f"{name}/Source"
    return str(source_credit.get("label", "")).strip()


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
    if len(palette) == 1:
        palette = [palette[0], palette[0], palette[0]]
    elif len(palette) == 2:
        palette = [palette[0], palette[1], palette[1]]

    by_luma = sorted(palette, key=_luma, reverse=True)
    request.style.primary_color = _to_hex(by_luma[0])
    request.style.secondary_color = _to_hex(by_luma[min(1, len(by_luma) - 1)])
    request.style.accent_color = _to_hex(by_luma[-1])
    return True


def _luma(rgb: tuple[int, int, int]) -> float:
    return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722


def _to_hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def _fetch_pexels_page_metadata(page_url: str) -> dict:
    req = Request(page_url, headers={"User-Agent": "frogpt-poster/1.0"})
    with urlopen(req, timeout=30) as response:
        html_text = response.read().decode("utf-8", errors="replace")

    metadata = {
        "page_url": page_url,
        "content_url": "",
        "og_image": "",
        "photographer": "",
        "photo_id": _extract_photo_id(page_url),
    }
    metadata["og_image"] = _extract_meta_content(html_text, "og:image")
    image_object = _extract_image_object_from_json_ld(html_text)
    if image_object:
        metadata["content_url"] = str(image_object.get("contentUrl", "")).replace("\\/", "/")
        creator = image_object.get("creator") or {}
        if isinstance(creator, dict):
            metadata["photographer"] = str(creator.get("name", "")).strip()
        metadata["page_url"] = str(image_object.get("acquireLicensePage", "")).replace("\\/", "/") or page_url
    if not metadata["photographer"]:
        title = _extract_meta_content(html_text, "og:title")
        m = re.search(r"由\s*(.+?)\s*拍攝", title)
        if m:
            metadata["photographer"] = m.group(1).strip()
    return metadata


def _extract_meta_content(html_text: str, property_name: str) -> str:
    pattern = rf'<meta\s+property="{re.escape(property_name)}"\s+content="([^"]+)"'
    m = re.search(pattern, html_text, flags=re.IGNORECASE)
    if not m:
        return ""
    return html.unescape(m.group(1))


def _extract_image_object_from_json_ld(html_text: str) -> dict | None:
    blocks = re.findall(
        r'<script\s+type="application/ld\+json"[^>]*>(.*?)</script>',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for raw in blocks:
        text = html.unescape(raw).strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        candidates = payload if isinstance(payload, list) else [payload]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            if str(item.get("@type", "")).lower() == "imageobject" and item.get("contentUrl"):
                return item
    return None


def _extract_photo_id(page_url: str) -> int | None:
    m = re.search(r"/photo/(?:[^/]*-)?(\d+)/?$", page_url)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _fallback_pexels_image_url(photo_id: int | None) -> str:
    if not photo_id:
        return ""
    return f"https://images.pexels.com/photos/{photo_id}/pexels-photo-{photo_id}.jpeg"
