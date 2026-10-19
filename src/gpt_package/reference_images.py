"""Reference image helpers, including Pexels API access and palette extraction."""

from __future__ import annotations

import colorsys
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


def apply_style_from_reference(
    request: PosterRequest,
    reference_image_path: str,
    color_hint: str | None = None,
) -> bool:
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

    base = _select_base_color_from_hint(palette, color_hint or "")
    secondary = _adjust_sv(base, s_scale=0.82, v_shift=-0.04)
    accent = _adjust_sv(base, s_scale=1.18, v_shift=0.08)

    request.style.primary_color = _to_hex(base)
    request.style.secondary_color = _to_hex(secondary)
    request.style.accent_color = _to_hex(accent)
    return True


def _luma(rgb: tuple[int, int, int]) -> float:
    return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722


def _to_hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def _select_base_color_from_hint(palette: list[tuple[int, int, int]], hint_text: str) -> tuple[int, int, int]:
    if not palette:
        return (246, 241, 232)
    hint = _parse_color_hint(hint_text)
    tone_only = _parse_tone_hint(hint_text)
    if not hint:
        by_luma = sorted(palette, key=_luma, reverse=True)
        base = by_luma[0]
        if tone_only:
            sat_scale, val_shift = tone_only
            tuned = _adjust_sv(base, s_scale=sat_scale, v_shift=val_shift)
            if _is_light_tone(hint_text):
                return _enforce_luma_floor(tuned, 156)
            if _is_dark_tone(hint_text):
                return _enforce_luma_ceiling(tuned, 122)
            return tuned
        return base

    target_h, sat_bias, val_bias = hint
    best = min(palette, key=lambda rgb: _hue_distance(_rgb_to_hsv(rgb)[0], target_h))
    matched = _hue_distance(_rgb_to_hsv(best)[0], target_h) <= 0.10
    if matched:
        return _adjust_sv(best, s_scale=sat_bias, v_shift=val_bias)

    # No close hue in image: keep nearest image hue, then tune saturation/value.
    return _adjust_sv(best, s_scale=sat_bias, v_shift=val_bias)


def _parse_color_hint(text: str) -> tuple[float, float, float] | None:
    raw = (text or "").strip().lower()
    if not raw:
        return None
    hue_map = {
        "red": 0.0, "紅": 0.0, "红": 0.0,
        "orange": 0.08, "橙": 0.08,
        "yellow": 0.15, "黃": 0.15, "黄": 0.15,
        "green": 0.33, "綠": 0.33, "绿": 0.33,
        "teal": 0.46, "cyan": 0.50, "青": 0.50,
        "blue": 0.62, "藍": 0.62, "蓝": 0.62,
        "purple": 0.77, "violet": 0.80, "紫": 0.77,
        "pink": 0.92, "粉": 0.92,
        "brown": 0.08, "咖啡": 0.08, "棕": 0.08,
        "gray": 0.0, "grey": 0.0, "灰": 0.0,
    }
    hue = None
    for key, val in hue_map.items():
        if key in raw:
            hue = val
            break
    if hue is None:
        return None

    sat_scale = 1.0
    val_shift = 0.0
    if any(k in raw for k in ("pastel", "柔和", "低彩", "淡")):
        sat_scale = 0.72
        val_shift = 0.06
    if any(k in raw for k in ("vivid", "高彩", "鮮", "亮彩")):
        sat_scale = 1.20
    if any(k in raw for k in ("dark", "深", "暗")):
        val_shift -= 0.08
    if any(k in raw for k in ("light", "淺", "亮")):
        val_shift += 0.08
    return (hue, sat_scale, val_shift)


def _parse_tone_hint(text: str) -> tuple[float, float] | None:
    raw = (text or "").strip().lower()
    if not raw:
        return None
    sat_scale = 1.0
    val_shift = 0.0
    has_tone = False
    if any(k in raw for k in ("pastel", "柔和", "低彩", "淡")):
        sat_scale = 0.72
        val_shift = max(val_shift, 0.10)
        has_tone = True
    if any(k in raw for k in ("vivid", "高彩", "鮮", "亮彩")):
        sat_scale = 1.20
        has_tone = True
    if any(k in raw for k in ("dark", "深", "暗")):
        val_shift -= 0.12
        has_tone = True
    if any(k in raw for k in ("light", "淺", "亮")):
        val_shift += 0.16
        sat_scale = min(sat_scale, 0.92)
        has_tone = True
    return (sat_scale, val_shift) if has_tone else None


def _adjust_sv(rgb: tuple[int, int, int], s_scale: float, v_shift: float) -> tuple[int, int, int]:
    h, s, v = _rgb_to_hsv(rgb)
    s = max(0.16, min(0.86, s * s_scale))
    v = max(0.24, min(0.88, v + v_shift))
    return _hsv_to_rgb((h, s, v))


def _rgb_to_hsv(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = rgb
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    return (h, s, v)


def _hsv_to_rgb(hsv: tuple[float, float, float]) -> tuple[int, int, int]:
    h, s, v = hsv
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))


def _hue_distance(a: float, b: float) -> float:
    d = abs(a - b)
    return min(d, 1.0 - d)


def _is_light_tone(text: str) -> bool:
    raw = (text or "").strip().lower()
    return any(k in raw for k in ("light", "淺", "亮", "pastel", "柔和", "淡"))


def _is_dark_tone(text: str) -> bool:
    raw = (text or "").strip().lower()
    return any(k in raw for k in ("dark", "深", "暗"))


def _enforce_luma_floor(rgb: tuple[int, int, int], floor: float) -> tuple[int, int, int]:
    l = _luma(rgb)
    if l >= floor:
        return rgb
    return _with_target_luma(rgb, floor)


def _enforce_luma_ceiling(rgb: tuple[int, int, int], ceiling: float) -> tuple[int, int, int]:
    l = _luma(rgb)
    if l <= ceiling:
        return rgb
    return _with_target_luma(rgb, ceiling)


def _with_target_luma(rgb: tuple[int, int, int], target_luma: float) -> tuple[int, int, int]:
    current = max(1.0, _luma(rgb))
    scale = target_luma / current
    return (
        max(0, min(255, int(rgb[0] * scale))),
        max(0, min(255, int(rgb[1] * scale))),
        max(0, min(255, int(rgb[2] * scale))),
    )


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
