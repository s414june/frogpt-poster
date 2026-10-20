"""OpenAI Apps/Tools compatible tool definition and handler."""

import base64
import hashlib
import json
import os
import shutil
import tempfile
import uuid
import io
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from PIL import Image

from .client import PosterGenerator
from .errors import PosterError
from .errors import ValidationError
from .font_discovery import discover_open_source_fonts
from .font_registry import resolve_font_family
from .guidance import build_design_guide, build_intake_questions
from .reference_images import apply_style_from_reference, build_credit_label, fetch_pexels_references, resolve_reference_url
from .text_input import load_request_from_text_file
from .types import PosterAssetSet, PosterLayout, PosterRequest, PosterStyle
from .validation import validate_request

TOOL_NAME = "generate_poster_with_real_image_priority"
_BACKGROUND_MODES = {"auto", "solid", "gradient", "reference"}
_IMAGE_ROLE_MODES = {"auto", "subject", "background", "both"}
_CREATIVE_SOURCE_MODES = {"auto", "real_image_priority", "gpt_generate"}
_DEFAULT_PRIMARY_COLOR = "#F6F1E8"
_DEFAULT_SECONDARY_COLOR = "#A8BFA8"
_DEFAULT_ACCENT_COLOR = "#6D8A72"
_LOCAL_REFERENCE_MANIFEST = Path(__file__).resolve().parents[2] / "assets" / "reference-library" / "pexels" / "manifest.json"
_LOCAL_REFERENCE_INDEX: dict[str, dict] | None = None


def _env_flag_enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _is_pexels_enabled() -> bool:
    return _env_flag_enabled("FROGPT_ENABLE_PEXELS", default=False)


def _has_pexels_api_key() -> bool:
    return bool(os.getenv("PEXELS_API_KEY", "").strip())


def _is_pexels_available() -> bool:
    return _is_pexels_enabled() and _has_pexels_api_key()


def build_tool_definition() -> dict:
    return {
        "type": "function",
        "name": TOOL_NAME,
        "description": (
            "Generate a poster request result with real-image-first policy. "
            "Use user-provided photos if available; AI image is fallback only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "poster_text_file": {
                    "type": "string",
                    "description": (
                        "Path to UTF-8 JSON text file containing poster input."
                    ),
                },
                "poster_request": {
                    "type": "object",
                    "description": (
                        "Inline request object for web/mobile usage (no local file path)."
                    ),
                },
                "intake_confirmed": {
                    "type": "boolean",
                    "description": "Compatibility field for MCP intake flow.",
                },
                "intake_session_token": {
                    "type": "string",
                    "description": "Compatibility field for MCP intake flow.",
                },
                "font_family": {"type": "string", "description": "Default sans/黑體. Explicit serif/明體, kai/楷體, rounded/圓體; unsupported names fail instead of silently using sans."},
                "text_align": {"type": "string", "enum": ["left", "center", "right"]},
                "headline_source": {"type": "string", "enum": ["title", "body_first"]},
                "body_y_ratio": {"type": "number", "minimum": 0, "maximum": 1},
                "title": {"type": "string"},
                "body": {"type": "string"},
                "user_image_paths": {"type": "array", "items": {"type": "string"}},
                "user_image_urls": {"type": "array", "items": {"type": "string"}},
                "user_image_base64": {"type": "array", "items": {"type": "string"}},
                "subject_image_paths": {"type": "array", "items": {"type": "string"}},
                "subject_image_urls": {"type": "array", "items": {"type": "string"}},
                "subject_image_base64": {"type": "array", "items": {"type": "string"}},
                "reference_image_urls": {"type": "array", "items": {"type": "string"}},
                "reference_image_paths": {"type": "array", "items": {"type": "string"}},
                "reference_image_base64": {"type": "array", "items": {"type": "string"}},
                "design_variant": {"type": "string", "enum": ["reinterpret", "faithful"], "description": "Default reinterpret: new palette for colorful references, rearrange at least two structural decisions; faithful only when explicitly requested."},
                "typography_grid": {"type": "boolean", "description": "Default true in reference mode: snap measured text to baseline grid, enforce 5% margin and 2-unit text/subject gaps, bounded repair; report large gaps within group."},
                "protected_regions": {"type": "array", "maxItems": 24, "items": {"type": "object"}, "description": "GPT visually identifies subject/photo rectangles on the generated visual, in canvas pixels: x, y, width, height. Not automatic detection."},
                "design_reference": {"type": "boolean"},
                "reference_style_description": {"type": "string"},
                "text_layers": {"type": "array", "maxItems": 24, "items": {"type": "object"}},
                "generated_background_base64": {"type": "string"},
                "generated_background_text_free_confirmed": {
                    "type": "boolean",
                    "description": "Set true only when the generated background is confirmed text-free (no letters/numbers/logo/watermark).",
                },
                "use_local_reference_library": {"type": "boolean", "description": "Use saved Pexels photos without API/network. Omit reference_library_id to list available photos."},
                "reference_library_id": {"type": "string", "description": "Saved photo ID from the local library manifest; independent of Pexels API."},
                "pexels_query": {"type": "string", "description": "Online Pexels API search only; not the saved library."},
                "pexels_orientation": {"type": "string"},
                "pexels_per_page": {"type": "integer", "minimum": 1, "maximum": 10},
                "auto_pexels_fallback": {
                    "type": "boolean",
                    "description": "Opt-in auto Pexels query when no image/reference is provided.",
                },
                "use_reference_as_fallback": {"type": "boolean"},
                "open_source_font_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "width": {"type": "integer", "minimum": 256, "maximum": 4096},
                "height": {"type": "integer", "minimum": 256, "maximum": 4096},
                "allow_ai_fallback": {"type": "boolean"},
                "subject": {"type": "string"},
                "background_mode": {
                    "type": "string",
                    "enum": ["auto", "solid", "gradient", "reference"],
                },
                "image_role_mode": {
                    "type": "string",
                    "enum": ["auto", "subject", "background", "both"],
                },
                "geometry_enabled": {"type": "boolean"},
                "subject_mask_mode": {
                    "type": "string",
                    "enum": ["rounded", "feather"],
                },
                "subject_border_px": {"type": "integer", "minimum": 0, "maximum": 20},
                "background_color_hint": {"type": "string"},
                "creative_source_preference": {
                    "type": "string",
                    "enum": ["auto", "real_image_priority", "gpt_generate"],
                    "description": "Set gpt_generate to let GPT choose design path deterministically unless user customizes settings.",
                },
                "intake_answers": {
                    "type": "object",
                    "description": "Optional intake answers keyed by question id.",
                },
                "variation_token": {"type": "string"},
                "regenerate_variant": {
                    "type": "boolean",
                    "description": "Generate a new visual variant for same brief.",
                },
                "primary_color": {"type": "string"},
                "secondary_color": {"type": "string"},
                "accent_color": {"type": "string"},
                "request_intake_only": {
                    "type": "boolean",
                    "description": "Return intake questions only, without rendering.",
                },
                "show_design_guide": {
                    "type": "boolean",
                    "description": "Include the poster design guide in response.",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    }


def _build_request(arguments: dict) -> PosterRequest:
    if arguments.get("poster_request"):
        request = _from_inline_request(arguments["poster_request"])
    elif arguments.get("poster_text_file"):
        request = load_request_from_text_file(arguments["poster_text_file"])
    else:
        request = PosterRequest(title="", body="")

    if "title" in arguments:
        if not isinstance(arguments["title"], str):
            raise ValidationError("title must be a string")
        request.title = arguments["title"]
    if "body" in arguments:
        if not isinstance(arguments["body"], str):
            raise ValidationError("body must be a string")
        request.body = arguments["body"]
    if "user_image_paths" in arguments:
        if not isinstance(arguments["user_image_paths"], list):
            raise ValidationError("user_image_paths must be an array of strings")
        request.assets.user_image_paths = [str(item) for item in arguments["user_image_paths"]]
    if "open_source_font_paths" in arguments:
        if not isinstance(arguments["open_source_font_paths"], list):
            raise ValidationError("open_source_font_paths must be an array of strings")
        request.assets.open_source_font_paths = [
            str(item) for item in arguments["open_source_font_paths"]
        ]
    if "subject_image_paths" in arguments:
        if not isinstance(arguments["subject_image_paths"], list):
            raise ValidationError("subject_image_paths must be an array of strings")
        request.assets.subject_image_paths = [str(item) for item in arguments["subject_image_paths"]]
    payload = arguments.get("poster_request") or {}
    font_family = arguments.get("font_family", (payload.get("style") or {}).get("font_family", payload.get("font_family")))
    if font_family is not None or not request.assets.open_source_font_paths:
        request.style.font_family, request.assets.open_source_font_paths = resolve_font_family(
            font_family if font_family is not None else "sans"
        )
    else:
        request.style.font_family = "custom"
    if "width" in arguments:
        if not isinstance(arguments["width"], int):
            raise ValidationError("width must be an integer")
        request.layout.width = arguments["width"]
    if "height" in arguments:
        if not isinstance(arguments["height"], int):
            raise ValidationError("height must be an integer")
        request.layout.height = arguments["height"]
    if "allow_ai_fallback" in arguments:
        if not isinstance(arguments["allow_ai_fallback"], bool):
            raise ValidationError("allow_ai_fallback must be a boolean")
        request.allow_ai_fallback = arguments["allow_ai_fallback"]
    for key in ("text_align", "headline_source", "body_y_ratio"):
        if key in arguments:
            setattr(request.style, key, arguments[key])
    if request.style.text_align not in ("left", "center", "right"):
        raise ValidationError("text_align must be left, center or right")
    if request.style.headline_source not in ("title", "body_first"):
        raise ValidationError("headline_source must be title or body_first")
    if request.style.body_y_ratio is not None:
        ratio = request.style.body_y_ratio
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not 0 <= ratio <= 1:
            raise ValidationError("body_y_ratio must be a number from 0 to 1")
    if "subject" in arguments:
        request.style.subject = str(arguments["subject"])
    if "background_mode" in arguments:
        request.style.background_mode = _normalize_background_mode(arguments["background_mode"])
    if "image_role_mode" in arguments:
        request.style.image_role_mode = _normalize_image_role_mode(arguments["image_role_mode"])
    if "geometry_enabled" in arguments:
        if not isinstance(arguments["geometry_enabled"], bool):
            raise ValidationError("geometry_enabled must be a boolean")
        request.style.geometry_enabled = arguments["geometry_enabled"]
    if "subject_mask_mode" in arguments:
        request.style.subject_mask_mode = _normalize_subject_mask_mode(arguments["subject_mask_mode"])
    if "subject_border_px" in arguments:
        if not isinstance(arguments["subject_border_px"], int):
            raise ValidationError("subject_border_px must be an integer")
        request.style.subject_border_px = arguments["subject_border_px"]
    if "background_color_hint" in arguments:
        request.style.background_color_hint = str(arguments["background_color_hint"]).strip()
    if "variation_token" in arguments:
        request.style.variation_token = str(arguments["variation_token"])
    if "primary_color" in arguments:
        request.style.primary_color = str(arguments["primary_color"])
    if "secondary_color" in arguments:
        request.style.secondary_color = str(arguments["secondary_color"])
    if "accent_color" in arguments:
        request.style.accent_color = str(arguments["accent_color"])

    grid = arguments.get("typography_grid", (payload.get("style") or {}).get("typography_grid", bool(arguments.get("design_reference"))))
    if not isinstance(grid, bool):
        raise ValidationError("typography_grid must be boolean")
    request.style.typography_grid = grid
    from .layout_grid import validate_regions
    request.style.protected_regions = validate_regions(arguments.get("protected_regions", (payload.get("style") or {}).get("protected_regions", [])), request.layout.width, request.layout.height)
    from .text_layers import validate_text_layers
    request.style.text_layers = validate_text_layers(arguments.get("text_layers", (payload.get("style") or {}).get("text_layers", [])), request.layout.width, request.layout.height)
    return request


def _from_inline_request(payload: dict) -> PosterRequest:
    if not isinstance(payload, dict):
        raise ValidationError("poster_request must be an object")
    assets = payload.get("assets", {})
    layout = payload.get("layout", {})
    style = payload.get("style", {})
    copy = payload.get("copy", {})
    if copy and not isinstance(copy, dict):
        raise ValidationError("copy must be an object when provided")

    title = str(copy.get("headline", payload.get("title", ""))).strip()
    subtitle = str(copy.get("subtitle", "")).strip()
    organization = str(copy.get("organization", "")).strip()
    cta = str(copy.get("cta", "")).strip()
    if subtitle or organization or cta:
        body_lines = [line for line in [subtitle, organization, cta] if line]
        body = "\n".join(body_lines)
    else:
        body = str(payload.get("body", ""))

    return PosterRequest(
        title=title,
        body=body,
        assets=PosterAssetSet(
            user_image_paths=[str(item) for item in assets.get("user_image_paths", [])],
            subject_image_paths=[str(item) for item in assets.get("subject_image_paths", [])],
            open_source_font_paths=[
                str(item) for item in assets.get("open_source_font_paths", [])
            ],
        ),
        layout=PosterLayout(
            width=int(layout.get("width", 1080)),
            height=int(layout.get("height", 1350)),
        ),
        style=PosterStyle(
            background_mode=_normalize_background_mode(
                style.get("background_mode", payload.get("background_mode", "auto"))
            ),
            image_role_mode=_normalize_image_role_mode(
                style.get("image_role_mode", payload.get("image_role_mode", "auto"))
            ),
            geometry_enabled=bool(style.get("geometry_enabled", payload.get("geometry_enabled", True))),
            subject_mask_mode=_normalize_subject_mask_mode(
                style.get("subject_mask_mode", payload.get("subject_mask_mode", "rounded"))
            ),
            subject_border_px=int(style.get("subject_border_px", payload.get("subject_border_px", 0))),
            background_color_hint=str(
                style.get("background_color_hint", payload.get("background_color_hint", ""))
            ).strip(),
            primary_color=str(style.get("primary_color", payload.get("primary_color", _DEFAULT_PRIMARY_COLOR))),
            secondary_color=str(style.get("secondary_color", payload.get("secondary_color", _DEFAULT_SECONDARY_COLOR))),
            accent_color=str(style.get("accent_color", payload.get("accent_color", _DEFAULT_ACCENT_COLOR))),
            subject=str(style.get("subject", payload.get("subject", ""))),
            panel_ratio=float(style.get("panel_ratio", payload.get("panel_ratio", 0.24))),
            text_align=style.get("text_align", payload.get("text_align", "center")),
            headline_source=style.get("headline_source", payload.get("headline_source", "body_first")),
            body_y_ratio=style.get("body_y_ratio", payload.get("body_y_ratio")),
            title_max_lines=int(style.get("title_max_lines", payload.get("title_max_lines", 2))),
            body_max_lines=int(style.get("body_max_lines", payload.get("body_max_lines", 4))),
            background_shape_count=int(
                style.get("background_shape_count", payload.get("background_shape_count", 3))
            ),
            background_shape_alpha_min=int(
                style.get(
                    "background_shape_alpha_min",
                    payload.get("background_shape_alpha_min", 10),
                )
            ),
            background_shape_alpha_max=int(
                style.get(
                    "background_shape_alpha_max",
                    payload.get("background_shape_alpha_max", 28),
                )
            ),
            variation_token=str(style.get("variation_token", payload.get("variation_token", ""))),
        ),
        allow_ai_fallback=bool(payload.get("allow_ai_fallback", True)),
    )


def _download_image(url: str, output_path: Path) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValidationError(f"user image url must be http/https: {url}")
    try:
        with urlopen(url, timeout=20) as response:
            content = response.read()
    except Exception as exc:
        raise ValidationError(f"failed downloading image url: {url}") from exc
    if not content:
        raise ValidationError(f"empty image content from url: {url}")
    output_path.write_bytes(content)


def _decode_base64_image(data: str, output_path: Path) -> None:
    token = data.strip()
    if token.lower().startswith("data:"):
        if "," not in token:
            raise ValidationError("user_image_base64 data URL is missing payload")
        _, token = token.split(",", 1)
    token = "".join(token.split())
    try:
        content = base64.b64decode(token, validate=True)
    except Exception as exc:
        raise ValidationError("user_image_base64 contains invalid base64") from exc
    if not content:
        raise ValidationError("user_image_base64 contains empty image data")
    try:
        with Image.open(io.BytesIO(content)) as img:
            img.verify()
    except Exception as exc:
        raise ValidationError("user_image_base64 is not a valid image payload") from exc
    output_path.write_bytes(content)


def _materialize_remote_images(arguments: dict, request: PosterRequest) -> str | None:
    payload = arguments.get("poster_request")
    payload_assets = payload.get("assets", {}) if isinstance(payload, dict) and isinstance(payload.get("assets"), dict) else {}

    urls = arguments.get("user_image_urls", payload_assets.get("user_image_urls", []))
    b64_images = arguments.get("user_image_base64", payload_assets.get("user_image_base64", []))
    subject_urls = arguments.get("subject_image_urls", payload_assets.get("subject_image_urls", []))
    subject_b64_images = arguments.get("subject_image_base64", payload_assets.get("subject_image_base64", []))
    nested_user_paths = payload_assets.get("user_image_paths", [])
    nested_subject_paths = payload_assets.get("subject_image_paths", [])
    if urls and not isinstance(urls, list):
        raise ValidationError("user_image_urls must be an array of strings")
    if b64_images and not isinstance(b64_images, list):
        raise ValidationError("user_image_base64 must be an array of strings")
    if subject_urls and not isinstance(subject_urls, list):
        raise ValidationError("subject_image_urls must be an array of strings")
    if subject_b64_images and not isinstance(subject_b64_images, list):
        raise ValidationError("subject_image_base64 must be an array of strings")
    if nested_user_paths and not isinstance(nested_user_paths, list):
        raise ValidationError("poster_request.assets.user_image_paths must be an array of strings")
    if nested_subject_paths and not isinstance(nested_subject_paths, list):
        raise ValidationError("poster_request.assets.subject_image_paths must be an array of strings")

    if not urls and not b64_images and not subject_urls and not subject_b64_images and not nested_user_paths and not nested_subject_paths:
        return None

    temp_dir = Path(tempfile.mkdtemp(prefix="poster-images-"))
    materialized: list[str] = []
    for idx, url in enumerate(urls):
        path = temp_dir / f"url-{idx}.img"
        _download_image(str(url), path)
        materialized.append(str(path))
    for idx, content in enumerate(b64_images):
        path = temp_dir / f"b64-{idx}.img"
        _decode_base64_image(str(content), path)
        materialized.append(str(path))
    subject_materialized: list[str] = []
    for idx, url in enumerate(subject_urls):
        path = temp_dir / f"subject-url-{idx}.img"
        _download_image(str(url), path)
        subject_materialized.append(str(path))
    for idx, content in enumerate(subject_b64_images):
        path = temp_dir / f"subject-b64-{idx}.img"
        _decode_base64_image(str(content), path)
        subject_materialized.append(str(path))

    request.assets.user_image_paths = (
        materialized
        + [str(item) for item in nested_user_paths]
        + request.assets.user_image_paths
    )
    request.assets.subject_image_paths = (
        subject_materialized
        + [str(item) for item in nested_subject_paths]
        + request.assets.subject_image_paths
    )
    return str(temp_dir)


def _materialize_reference_images(arguments: dict, request: PosterRequest) -> dict:
    references = arguments.get("reference_image_urls", [])
    reference_paths = list(arguments.get("reference_image_paths", []))
    library_id = str(arguments.get("reference_library_id", "")).strip()
    if library_id:
        matches = [(path, item) for path, item in _local_library_items() if item.get("id") == library_id]
        if not matches:
            raise ValidationError("Unknown or unavailable reference_library_id; list the saved library first")
        reference_paths.insert(0, str(matches[0][0]))
    reference_b64 = arguments.get("reference_image_base64", [])
    generated_background_b64 = _get_generated_background_base64(arguments)
    if references and not isinstance(references, list):
        raise ValidationError("reference_image_urls must be an array of strings")
    if reference_paths and not isinstance(reference_paths, list):
        raise ValidationError("reference_image_paths must be an array of strings")
    if reference_b64 and not isinstance(reference_b64, list):
        raise ValidationError("reference_image_base64 must be an array of strings")
    if generated_background_b64 and not isinstance(generated_background_b64, str):
        raise ValidationError("generated_background_base64 must be a string")
    refs = [resolve_reference_url(str(item)) for item in references]
    ref_b64_items = [str(item) for item in reference_b64]
    if generated_background_b64.strip():
        ref_b64_items.insert(0, generated_background_b64.strip())

    pexels_query = str(arguments.get("pexels_query", "")).strip() if _is_pexels_available() else ""
    if pexels_query:
        refs.extend(
            fetch_pexels_references(
                query=pexels_query,
                api_key=os.getenv("PEXELS_API_KEY", ""),
                per_page=int(arguments.get("pexels_per_page", 3)),
                orientation=str(arguments.get("pexels_orientation", "portrait")),
            )
        )

    local_ref_paths = [str(item) for item in reference_paths]
    if not refs and not ref_b64_items and not local_ref_paths:
        return {
            "temp_dir": None,
            "downloaded_paths": [],
            "source_credits": [],
            "used_as_fallback": False,
            "style_from_reference_applied": False,
            "attribution_label": "",
        }

    temp_dir = Path(tempfile.mkdtemp(prefix="poster-refs-"))
    downloaded_paths: list[str] = []
    source_credits: list[dict] = []

    for idx, item in enumerate(ref_b64_items):
        path = temp_dir / f"ref-b64-{idx}.img"
        _decode_base64_image(item, path)
        downloaded_paths.append(str(path))
        source_credits.append({"source": "generated_or_uploaded_base64", "url": None})

    for idx, ref in enumerate(refs):
        path = temp_dir / f"ref-{idx}.img"
        _download_image(ref["url"], path)
        downloaded_paths.append(str(path))
        if ref.get("source") == "pexels" and not ref.get("credit_label"):
            ref["credit_label"] = build_credit_label(ref)
        source_credits.append(ref)

    for raw in local_ref_paths:
        path = Path(raw)
        if not path.is_file():
            raise ValidationError(f"reference image path does not exist: {raw}")
        downloaded_paths.append(str(path))
        local_credit = _lookup_local_reference_credit(path)
        if local_credit:
            source_credits.append(local_credit)
        else:
            source_credits.append(
                {
                    "source": "local_reference_path",
                    "url": None,
                    "path": str(path),
                    "label": path.stem,
                    "credit_label": f"{path.stem}/Source",
                }
            )

    used_as_fallback = False
    background_mode = (request.style.background_mode or "auto").strip().lower()
    use_reference_as_fallback = bool(arguments.get("use_reference_as_fallback", True))
    force_reference_mode = background_mode == "reference"
    if (use_reference_as_fallback or force_reference_mode) and not request.assets.user_image_paths and downloaded_paths:
        request.assets.user_image_paths = downloaded_paths + request.assets.user_image_paths
        used_as_fallback = True

    attribution_label = ""
    if used_as_fallback and source_credits:
        attribution_label = str(source_credits[0].get("credit_label", "")).strip()

    return {
        "temp_dir": str(temp_dir),
        "downloaded_paths": downloaded_paths,
        "source_credits": source_credits,
        "used_as_fallback": used_as_fallback,
        "style_from_reference_applied": False,
        "attribution_label": attribution_label,
    }


def _auto_pexels_query(arguments: dict, request: PosterRequest) -> str:
    if not _is_pexels_available():
        return ""
    if not bool(arguments.get("auto_pexels_fallback", False)):
        return ""
    explicit = str(arguments.get("pexels_query", "")).strip()
    if explicit:
        return explicit
    has_refs = bool(arguments.get("reference_image_urls")) or bool(arguments.get("reference_image_paths")) or bool(arguments.get("reference_image_base64")) or bool(
        str(arguments.get("generated_background_base64", "")).strip()
    )
    if has_refs:
        return ""
    has_user_image = bool(request.assets.user_image_paths) or bool(arguments.get("user_image_urls")) or bool(
        arguments.get("user_image_base64")
    )
    if has_user_image:
        return ""
    subject = (request.style.subject or "").strip()
    title = (request.title or "").strip()
    if subject:
        return f"{subject} soft natural light portrait"
    if title:
        return f"{title} editorial portrait"
    return ""


def _encode_output_image(path: str | None) -> str | None:
    if not path:
        return None
    file_path = Path(path)
    if not file_path.is_file():
        return None
    return base64.b64encode(file_path.read_bytes()).decode("ascii")


def _encode_preview_image(path: str | None, max_side: int = 1024) -> str | None:
    if not path:
        return None
    file_path = Path(path)
    if not file_path.is_file():
        return None
    try:
        with Image.open(file_path) as img:
            img = img.convert("RGB")
            w, h = img.size
            if max(w, h) > max_side:
                ratio = max_side / float(max(w, h))
                img = img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=84, optimize=True)
            return base64.b64encode(buf.getvalue()).decode("ascii")
    except OSError:
        return None


def _safe_json_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _normalize_background_mode(value: object) -> str:
    mode = str(value or "auto").strip().lower()
    if mode not in _BACKGROUND_MODES:
        raise ValidationError("background_mode must be one of: auto, solid, gradient, reference")
    return mode


def _normalize_subject_mask_mode(value: object) -> str:
    mode = str(value or "rounded").strip().lower()
    if mode not in {"rounded", "feather"}:
        raise ValidationError("subject_mask_mode must be one of: rounded, feather")
    return mode


def _normalize_image_role_mode(value: object) -> str:
    mode = str(value or "auto").strip().lower()
    if mode not in _IMAGE_ROLE_MODES:
        raise ValidationError("image_role_mode must be one of: auto, subject, background, both")
    return mode


def _normalize_creative_source_preference(value: object) -> str:
    mode = str(value or "auto").strip().lower()
    if mode not in _CREATIVE_SOURCE_MODES:
        raise ValidationError("creative_source_preference must be one of: auto, real_image_priority, gpt_generate")
    return mode


def _extract_intake_answers(arguments: dict) -> dict:
    top = arguments.get("intake_answers")
    if isinstance(top, dict):
        return top
    payload = arguments.get("poster_request")
    if isinstance(payload, dict):
        nested = payload.get("intake_answers")
        if isinstance(nested, dict):
            return nested
    return {}


def _extract_intake_answer_text(arguments: dict, key: str) -> str:
    answers = _extract_intake_answers(arguments)
    value = answers.get(key)
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, dict):
        candidate = value.get("value")
        if isinstance(candidate, str):
            return candidate.strip().lower()
    return ""


def _resolve_creative_source_preference(arguments: dict) -> str:
    top = arguments.get("creative_source_preference")
    if top is not None:
        return _normalize_creative_source_preference(top)
    payload = arguments.get("poster_request")
    if isinstance(payload, dict) and "creative_source_preference" in payload:
        return _normalize_creative_source_preference(payload.get("creative_source_preference"))

    intake_source = _extract_intake_answer_text(arguments, "creative_source_preference")
    if intake_source:
        if "自訂" in intake_source or "custom" in intake_source:
            return "real_image_priority"
        if "gpt" in intake_source or "ai" in intake_source or "自動判斷" in intake_source:
            return "gpt_generate"

    image_ready = _extract_intake_answer_text(arguments, "image_ready")
    if image_ready and ("ai" in image_ready or "生成" in image_ready):
        return "gpt_generate"
    return "auto"


def _has_user_design_customization(arguments: dict, request: PosterRequest) -> bool:
    explicit_keys = {
        "background_mode",
        "background_color_hint",
        "geometry_enabled",
        "subject_mask_mode",
        "subject_border_px",
        "primary_color",
        "secondary_color",
        "accent_color",
        "image_role_mode",
        "pexels_query",
        "reference_image_urls",
        "reference_image_paths",
        "reference_image_base64",
        "generated_background_base64",
        "use_reference_as_fallback",
        "auto_pexels_fallback",
    }
    if any(k in arguments for k in explicit_keys):
        return True
    payload = arguments.get("poster_request")
    if isinstance(payload, dict):
        if any(k in payload for k in explicit_keys):
            return True
        style = payload.get("style")
        if isinstance(style, dict) and any(k in style for k in explicit_keys):
            return True
    if _normalize_background_mode(getattr(request.style, "background_mode", "auto")) != "auto":
        return True
    if str(getattr(request.style, "background_color_hint", "")).strip():
        return True
    return False


def _choose_gpt_autopilot_design_path(arguments: dict, request: PosterRequest) -> str:
    if _wants_explicit_visual_subject(request):
        return "generated_background"

    hint = str(getattr(request.style, "background_color_hint", "")).strip().lower()
    if hint:
        if any(k in hint for k in ("solid", "單色", "純色", "flat")):
            return "solid"
        return "gradient"

    if _is_pexels_available():
        return "pexels_reference"
    return "gradient"


def _apply_gpt_design_autopilot(arguments: dict, request: PosterRequest) -> dict:
    preference = _resolve_creative_source_preference(arguments)
    custom = _has_user_design_customization(arguments, request)
    active = preference == "gpt_generate" and not custom
    if not active:
        return {
            "active": False,
            "preference": preference,
            "customized": custom,
            "design_path": None,
        }

    request.style.background_mode = "auto"
    request.style.geometry_enabled = True
    request.style.variation_token = ""
    arguments.pop("variation_token", None)

    design_path = _choose_gpt_autopilot_design_path(arguments, request)
    if design_path == "pexels_reference":
        arguments["auto_pexels_fallback"] = True
        arguments["use_reference_as_fallback"] = True
        request.style.background_mode = "reference"
    elif design_path == "solid":
        request.style.background_mode = "solid"
    elif design_path == "gradient":
        request.style.background_mode = "gradient"
    else:
        request.style.background_mode = "auto"
        arguments["auto_pexels_fallback"] = False

    return {
        "active": True,
        "preference": preference,
        "customized": custom,
        "design_path": design_path,
    }


def _resolve_image_role_mode(request: PosterRequest) -> tuple[str, str]:
    chosen = _normalize_image_role_mode(request.style.image_role_mode)
    if chosen != "auto":
        return chosen, "user_selected"

    text_blob = f"{request.title} {request.body} {request.style.subject} {request.style.background_color_hint}".lower()
    if any(k in text_blob for k in ("兩者", "同時", "both", "直接加字", "只加文字")):
        return "both", "keyword_both"
    if any(k in text_blob for k in ("主體", "去背", "subject", "foreground", "cutout")):
        return "subject", "keyword_subject"
    if any(k in text_blob for k in ("背景", "底圖", "background")):
        return "background", "keyword_background"

    if request.assets.subject_image_paths and not request.assets.user_image_paths:
        return "subject", "subject_images_provided"
    if request.assets.user_image_paths and request.assets.subject_image_paths:
        return "background", "both_sources_already_provided"
    if not request.assets.user_image_paths:
        return "background", "no_user_image"

    first = Path(request.assets.user_image_paths[0])
    try:
        with Image.open(first) as img:
            width, height = img.size
            if "A" in img.getbands():
                alpha = img.getchannel("A").resize((64, 64))
                values = list(alpha.getdata())
                transparent = sum(1 for v in values if v < 250)
                if transparent / max(1, len(values)) >= 0.05:
                    return "subject", "alpha_transparency_detected"
    except OSError:
        return "background", "unreadable_image_default_background"

    ratio = width / max(1, height)
    poster_ratio = request.layout.width / max(1, request.layout.height)
    if 0.86 <= ratio <= 1.14:
        return "subject", "near_square_image"
    if abs(ratio - poster_ratio) <= 0.18:
        return "background", "matches_poster_ratio"
    if ratio < 0.72:
        return "subject", "narrow_portrait_image"
    return "background", "default_background_photo"


def _apply_image_role_mode(request: PosterRequest, role_mode: str) -> None:
    role = _normalize_image_role_mode(role_mode)
    if role == "subject":
        if request.assets.user_image_paths and not request.assets.subject_image_paths:
            request.assets.subject_image_paths = [request.assets.user_image_paths[0]]
            request.assets.user_image_paths = request.assets.user_image_paths[1:]
        return
    if role == "background":
        return
    if role == "both":
        if not request.assets.user_image_paths and request.assets.subject_image_paths:
            request.assets.user_image_paths = [request.assets.subject_image_paths[0]]
        request.assets.subject_image_paths = []
        request.style.geometry_enabled = False


def _has_explicit_palette(arguments: dict, request: PosterRequest) -> bool:
    if any(key in arguments for key in ("primary_color", "secondary_color", "accent_color")):
        return True
    payload = arguments.get("poster_request")
    if isinstance(payload, dict):
        style = payload.get("style")
        if isinstance(style, dict) and any(
            key in style for key in ("primary_color", "secondary_color", "accent_color")
        ):
            return True
        if any(key in payload for key in ("primary_color", "secondary_color", "accent_color")):
            return True
    return not (
        request.style.primary_color == _DEFAULT_PRIMARY_COLOR
        and request.style.secondary_color == _DEFAULT_SECONDARY_COLOR
        and request.style.accent_color == _DEFAULT_ACCENT_COLOR
    )


def _apply_palette_from_assets(arguments: dict, request: PosterRequest, reference_context: dict) -> tuple[bool, str | None]:
    if _has_explicit_palette(arguments, request):
        return False, None
    color_hint = _resolve_background_color_hint(request)
    candidates: list[str] = []
    candidates.extend(request.assets.user_image_paths)
    candidates.extend(request.assets.subject_image_paths)
    candidates.extend(reference_context.get("downloaded_paths", []))
    seen: set[str] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        if apply_style_from_reference(request, path, color_hint=color_hint):
            return True, path
    return False, None


def _resolve_background_color_hint(request: PosterRequest) -> str:
    explicit = (request.style.background_color_hint or "").strip()
    if explicit:
        return explicit
    text = f"{request.title} {request.body}".lower()
    keywords = [
        "紅", "橙", "黃", "綠", "青", "藍", "紫", "粉", "棕", "咖啡", "灰",
        "red", "orange", "yellow", "green", "teal", "cyan", "blue", "purple", "pink", "brown", "gray", "grey",
        "深", "淺", "暗", "亮", "pastel", "vivid", "light", "dark",
    ]
    hints = [k for k in keywords if k in text]
    return " ".join(hints[:4])


def _lookup_local_reference_credit(path: Path) -> dict | None:
    index = _load_local_reference_index()
    if not index:
        return None
    key = str(path.resolve()).replace("/", "\\").lower()
    item = index.get(key)
    if not item:
        return None
    return {
        "source": item.get("source", "pexels"),
        "photo_id": item.get("photo_id"),
        "url": item.get("image_url"),
        "page_url": item.get("page_url"),
        "photographer": item.get("photographer", "Unknown"),
        "credit_label": item.get("credit_label") or build_credit_label(item),
        "path": str(path),
    }


def _load_local_reference_index() -> dict[str, dict]:
    global _LOCAL_REFERENCE_INDEX
    if _LOCAL_REFERENCE_INDEX is not None:
        return _LOCAL_REFERENCE_INDEX
    if not _LOCAL_REFERENCE_MANIFEST.is_file():
        _LOCAL_REFERENCE_INDEX = {}
        return _LOCAL_REFERENCE_INDEX
    try:
        payload = json.loads(_LOCAL_REFERENCE_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _LOCAL_REFERENCE_INDEX = {}
        return _LOCAL_REFERENCE_INDEX
    items = payload.get("items", [])
    index: dict[str, dict] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        local_path = str(item.get("local_path", "")).strip()
        if not local_path:
            continue
        resolved = str((Path(__file__).resolve().parents[2] / local_path.replace("\\", "/")).resolve()).replace("/", "\\").lower()
        index[resolved] = item
    _LOCAL_REFERENCE_INDEX = index
    return _LOCAL_REFERENCE_INDEX


def _local_library_items() -> list[tuple[Path, dict]]:
    # Resolve only manifest entries, never arbitrary client-supplied paths.
    result = []
    for item in _load_local_reference_index().values():
        path = Path(__file__).resolve().parents[2] / str(item["local_path"]).replace("\\", "/")
        author = str(item.get("photographer", "")).strip()
        if path.is_file() and author and author.lower() != "unknown":
            result.append((path, item))
    return result


def _output_filename(path: str | None) -> str:
    if not path:
        return "poster.png"
    return Path(path).name or "poster.png"


def _output_sha256(path: str | None) -> str | None:
    if not path:
        return None
    file_path = Path(path)
    if not file_path.is_file():
        return None
    digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
    return digest


def _needs_intake(arguments: dict) -> bool:
    if bool(arguments.get("request_intake_only", False)):
        return True
    has_text_file = bool(arguments.get("poster_text_file"))
    has_inline = isinstance(arguments.get("poster_request"), dict)
    has_title = bool(str(arguments.get("title", "")).strip())
    has_body = bool(str(arguments.get("body", "")).strip())
    return not (has_text_file or has_inline or (has_title and has_body))


def _needs_background_generation(arguments: dict, request: PosterRequest, reference_context: dict) -> bool:
    has_user_image = bool(request.assets.user_image_paths)
    has_subject_image = bool(request.assets.subject_image_paths)
    has_reference = bool(reference_context.get("downloaded_paths"))
    if has_user_image or has_subject_image or has_reference:
        return False
    # Hard lock: when no visual input is available, force GPT to generate a text-free
    # background first, then call back with generated_background_base64.
    return True


def _wants_explicit_visual_subject(request: PosterRequest) -> bool:
    if str(request.style.subject or "").strip():
        return True
    blob = f"{request.title} {request.body}".lower()
    keywords = (
        "主角", "主視覺", "主圖", "餐點", "料理", "食物", "商品", "人像", "人物", "動物",
        "hero", "main visual", "subject", "food", "dish", "product", "portrait", "character",
    )
    return any(k in blob for k in keywords)


def _validate_pre_render_request(request: PosterRequest) -> None:
    try:
        validate_request(request)
    except ValidationError as exc:
        if str(exc).strip() == "user_image_paths is required when allow_ai_fallback is false":
            return
        raise


def _needs_text_free_background_confirmation(arguments: dict, request: PosterRequest) -> bool:
    generated_background = str(_get_generated_background_base64(arguments)).strip()
    if not generated_background:
        return False
    if _is_generated_background_text_free_confirmed(arguments):
        return False
    return True


def _get_generated_background_base64(arguments: dict) -> str:
    top = arguments.get("generated_background_base64", "")
    if isinstance(top, str) and top.strip():
        return top
    payload = arguments.get("poster_request")
    if isinstance(payload, dict):
        nested = payload.get("generated_background_base64", "")
        if isinstance(nested, str) and nested.strip():
            return nested
    return str(top or "")


def _is_generated_background_text_free_confirmed(arguments: dict) -> bool:
    if bool(arguments.get("generated_background_text_free_confirmed", False)):
        return True
    payload = arguments.get("poster_request")
    if isinstance(payload, dict):
        return bool(payload.get("generated_background_text_free_confirmed", False))
    return False


def _build_background_generation_prompt(request: PosterRequest) -> str:
    subject = request.style.subject.strip() if request.style.subject else "main subject"
    return (
        f"Create a text-free presentation-style poster background, portrait {request.layout.width}x{request.layout.height}. "
        f"Foreground subject: {subject}, with optional simple habitat/supporting prop only when needed. "
        "Generate both background and subject together as one text-free design. "
        "Center the entire subject bounding box at canvas center (50%, 50%). "
        "Subject width MUST NOT exceed 50% of canvas width; subject height MUST NOT exceed 50% of canvas height. "
        f"Palette: primary {request.style.primary_color}, secondary {request.style.secondary_color}, accent {request.style.accent_color}. "
        "Use mostly solid color or soft gradient background; avoid complex textures. "
        "Geometric elements should be minimal and only if composition needs balance. "
        "No letters, no numbers, no logo, no watermark, no typography. "
        "Keep clean negative space in top area for headline and bottom area for CTA text."
    )


def handle_tool_call(arguments: dict) -> dict:
    temp_dirs: list[str] = []
    try:
        arguments = dict(arguments)
        payload = arguments.get("poster_request") or {}
        for key in ("use_local_reference_library", "reference_library_id"):
            if key not in arguments and key in payload:
                arguments[key] = payload[key]
        library_requested = bool(arguments.get("use_local_reference_library")) or bool(arguments.get("reference_library_id"))
        if library_requested:
            # Saved files never need an API key, and cannot trigger a remote search.
            for key in ("pexels_query", "auto_pexels_fallback", "pexels_orientation", "pexels_per_page"):
                arguments.pop(key, None)
            if not arguments.get("reference_library_id"):
                return {
                    "ok": True, "rendered": False, "pipeline_stage": "image_selection",
                    "status": {"code": "needs_input", "message": "select_saved_reference"},
                    "next_action": "select_reference_library_id_then_retry_with_foreground_subject",
                    "reference_library": [{"id": item["id"], "photographer": item["photographer"],
                        "page_url": item.get("page_url"), "credit_label": item.get("credit_label") or build_credit_label(item)}
                        for _, item in _local_library_items()],
                    "message": "選擇已存圖庫背景；需要商品前景時另傳 subject_image_base64。作者不明的圖片暫不列入。",
                }
            request_style = dict(payload.get("style") or {})
            request_style.update(background_mode="reference", image_role_mode="background")
            arguments["poster_request"] = {**payload, "style": request_style}
            arguments.update(background_mode="reference", image_role_mode="background", use_reference_as_fallback=True)
        # An explicit stock-photo request must never silently become AI generation.
        wants_pexels = bool(str(arguments.get("pexels_query", "")).strip()) or bool(
            arguments.get("auto_pexels_fallback", False)
        )
        if wants_pexels and not _is_pexels_available():
            missing = []
            if not _is_pexels_enabled():
                missing.append("FROGPT_ENABLE_PEXELS=true")
            if not _has_pexels_api_key():
                missing.append("PEXELS_API_KEY")
            return {
                "ok": False, "rendered": False,
                "pipeline_stage": "configuration",
                "status": {"code": "pexels_unavailable", "message": "pexels_configuration_required"},
                "next_action": "configure_pexels_then_retry_same_request",
                "missing_configuration": missing,
                "message": "Pexels 尚未設定完成；請設定缺少的環境變數，不要改用 AI 背景。",
            }
        show_design_guide = bool(arguments.get("show_design_guide", False))
        if _needs_intake(arguments):
            payload = {
                "ok": True,
                "tool_name": TOOL_NAME,
                "pipeline_stage": "intake",
                "status": {
                    "code": "needs_input",
                    "message": "intake_questions_required_before_render",
                },
                "next_action": "ask_user_intake_questions",
                "rendered": False,
                "intake_questions": build_intake_questions(),
            }
            if show_design_guide or bool(arguments.get("request_intake_only", False)):
                payload["design_guide"] = build_design_guide()
            return payload

        request = _build_request(arguments)
        if arguments.get("design_reference"):
            variant = arguments.get("design_variant", "reinterpret")
            if variant not in ("reinterpret", "faithful"):
                raise ValidationError("design_variant must be reinterpret or faithful")
            description = str(arguments.get("reference_style_description", "")).strip()
            from .layout_grid import grid_spec
            variant_instruction = (
                "Create a distinct variant: change at least two structural decisions (photo placement/scale, headline alignment, secondary block arrangement). For colorful references change the dominant and accent hues while retaining contrast relationships, drawing palette inspiration from the NEW subject image. For neutral references retain restraint but change composition. Never just replace the subject in the same template. "
                if variant == "reinterpret" else "Keep the user-requested palette and overall composition. "
            )
            if not _get_generated_background_base64(arguments):
                return {
                    "ok": True, "rendered": False, "pipeline_stage": "needs_background_generation",
                    "next_action": "analyze_reference_generate_text_free_visual_then_define_text_layers",
                    "layout_grid": grid_spec(request.layout.width, request.layout.height),
                    "protected_regions_required_on_retry": "GPT must visually identify subject/photo rectangles from the GENERATED visual; provide x/y/width/height in final canvas pixels. No automatic subject detection is performed.",
                    "design_variant": variant,
                    "background_generation_prompt": (
                        f"Create an original text-free poster {request.layout.width}x{request.layout.height} for {request.style.subject or request.title}. "
                        f"Visual direction from the user reference: {description}. "
                        + variant_instruction +
                        "Preserve the reference visual rhythm, texture and hierarchy. "
                        "Adapt composition to the new subject; reserve negative space for the planned text layers. "
                        "Do not reproduce original copy, logos or watermarks. No text, letters or numbers."
                    ),
                    "text_layer_contract": "text_layers: [{text, font_family: sans|serif|kai|rounded, font_weight: 400|700, font_size: pixels (per-layer reference hierarchy), color: #RRGGBB, x, y, width, height: pixels, align: left|center|right, line_spacing: pixels (visually inferred from reference, else 4)}]. No equal-size constraint. Use reference weight/spacing before defaults. Explicit newlines are preserved; overflow is rejected.",
                    "reference_is_inspiration_only": True,
                }
            # Only the new text-free image reaches the renderer, never the inspiration poster.
            for key in list(arguments):
                if key.startswith(("reference_image_", "user_image_", "subject_image_")):
                    arguments.pop(key)
            request.assets.user_image_paths = []
            request.assets.subject_image_paths = []
            request.style.background_mode = "reference"
            request.style.image_role_mode = "both"
            request.style.geometry_enabled = False
            if not request.style.text_layers:
                raise ValidationError("design_reference requires text_layers for final typography")
        design_autopilot = _apply_gpt_design_autopilot(arguments, request)
        if bool(arguments.get("regenerate_variant", False)):
            request.style.variation_token = uuid.uuid4().hex[:12]
        auto_query = _auto_pexels_query(arguments, request)
        if auto_query:
            arguments["pexels_query"] = auto_query
            arguments["use_reference_as_fallback"] = True
        temp_dir = _materialize_remote_images(arguments, request)
        if temp_dir:
            temp_dirs.append(temp_dir)
        reference_context = _materialize_reference_images(arguments, request)
        if reference_context["temp_dir"]:
            temp_dirs.append(reference_context["temp_dir"])
        if arguments.get("pexels_query") and not reference_context["downloaded_paths"]:
            return {
                "ok": True, "rendered": False,
                "pipeline_stage": "image_selection",
                "status": {"code": "needs_input", "message": "pexels_no_results"},
                "next_action": "adjust_pexels_query_then_retry",
                "pexels_query": arguments["pexels_query"],
                "message": "Pexels 未找到可用圖片，請調整搜尋詞；不會自動改用 AI 背景。",
            }
        resolved_image_role_mode, image_role_resolution_reason = _resolve_image_role_mode(request)
        _apply_image_role_mode(request, resolved_image_role_mode)
        _validate_pre_render_request(request)
        palette_from_assets_applied, palette_source_path = _apply_palette_from_assets(
            arguments, request, reference_context
        )
        reference_context["style_from_reference_applied"] = palette_from_assets_applied
        if _needs_background_generation(arguments, request, reference_context):
            return {
                "ok": True,
                "tool_name": TOOL_NAME,
                "pipeline_stage": "needs_background_generation",
                "status": {
                    "code": "needs_background_generation",
                    "message": "generate_text_free_background_then_retry",
                },
                "next_action": "generate_background_then_retry",
                "rendered": False,
                "background_generation_prompt": _build_background_generation_prompt(request),
                "background_generation_requirements": {
                    "must_be_text_free": True,
                    "forbidden_elements": ["letters", "numbers", "logo", "watermark", "existing slogan"],
                    "required_flag_on_retry": "generated_background_text_free_confirmed=true",
                },
                "retry_arguments_hint": {
                    "generated_background_base64": "data:image/png;base64,...",
                    "generated_background_text_free_confirmed": True,
                    "poster_request": request.to_dict(),
                },
                "text_overlay_plan": {
                    "headline_box": {"x": 0.10, "y": 0.08, "w": 0.80, "h": 0.26},
                    "subject_focus_box": {"x": 0.25, "y": 0.25, "w": 0.50, "h": 0.50},
                    "cta_box": {"x": 0.12, "y": 0.78, "w": 0.76, "h": 0.12},
                },
                "intake_questions": build_intake_questions(),
                "palette_from_assets_applied": palette_from_assets_applied,
                "palette_source_path": palette_source_path,
                "resolved_image_role_mode": resolved_image_role_mode,
                "image_role_resolution_reason": image_role_resolution_reason,
                "design_autopilot": design_autopilot,
            }
        if _needs_text_free_background_confirmation(arguments, request):
            return {
                "ok": True,
                "tool_name": TOOL_NAME,
                "pipeline_stage": "needs_background_generation",
                "status": {
                    "code": "needs_background_generation",
                    "message": "generated_background_requires_text_free_confirmation",
                },
                "next_action": "regenerate_or_confirm_text_free_background",
                "rendered": False,
                "background_generation_prompt": _build_background_generation_prompt(request),
                "background_generation_requirements": {
                    "must_be_text_free": True,
                    "forbidden_elements": ["letters", "numbers", "logo", "watermark", "existing slogan"],
                    "required_flag_on_retry": "generated_background_text_free_confirmed=true",
                },
                "retry_arguments_hint": {
                    "generated_background_base64": "data:image/png;base64,...",
                    "generated_background_text_free_confirmed": True,
                    "poster_request": request.to_dict(),
                },
                "intake_questions": build_intake_questions(),
                "palette_from_assets_applied": palette_from_assets_applied,
                "palette_source_path": palette_source_path,
                "resolved_image_role_mode": resolved_image_role_mode,
                "image_role_resolution_reason": image_role_resolution_reason,
                "design_autopilot": design_autopilot,
            }
        request.style.source_credit_text = str(reference_context.get("attribution_label", "")).strip()
        generator = PosterGenerator()
        result = generator.generate(request)
        output_image_base64 = _encode_output_image(result.output_path)
        if not output_image_base64:
            raise ValidationError("render output image is missing or unreadable")
        preview_image_base64 = _encode_preview_image(result.output_path) or output_image_base64
        output_image_data_url = f"data:image/png;base64,{output_image_base64}"
        preview_image_data_url = f"data:image/jpeg;base64,{preview_image_base64}"
        payload = {
            "ok": True,
            "tool_name": TOOL_NAME,
            "pipeline_stage": "completed",
            "status": {
                "code": "completed",
                "message": "poster_render_completed",
            },
            "next_action": "deliver_image_then_text",
            "decision": {
                "image_source": result.decision.image_source.value,
                "reason": result.decision.reason,
            },
            "layout_report": request.style.layout_report,
            "request": request.to_dict(),
            "output_path": result.output_path,
            "output_mime_type": "image/png",
            "output_filename": _output_filename(result.output_path),
            "output_image_base64": output_image_base64,
            "output_image_data_url": output_image_data_url,
            "output_download_data_url": output_image_data_url,
            "output_preview_markdown": f"![poster-preview]({output_image_data_url})",
            "output_preview_base64": preview_image_base64,
            "output_preview_data_url": preview_image_data_url,
            "output_preview_mime_type": "image/jpeg",
            "output_image_sha256": _output_sha256(result.output_path),
            "output_image_bytes": Path(result.output_path).stat().st_size if result.output_path else None,
            "rendered": True,
            "display_priority": ["image", "download", "text"],
            "notes": result.notes,
            "reference_images_used": reference_context["used_as_fallback"],
            "style_from_reference_applied": reference_context["style_from_reference_applied"],
            "palette_source_path": palette_source_path,
            "resolved_image_role_mode": resolved_image_role_mode,
            "image_role_resolution_reason": image_role_resolution_reason,
            "source_credits": reference_context["source_credits"],
            "source_credit_overlay_applied": bool(request.style.source_credit_text),
            "source_credit_overlay_text": request.style.source_credit_text or None,
            "auto_pexels_query_used": auto_query or None,
            "design_autopilot": design_autopilot,
            "compliance_notes": [
                "Pexels content should be requested via official API; avoid scraping.",
                "Do not redistribute source images on a standalone basis.",
                "Keep prominent link/credit to Pexels and photographer when possible.",
            ],
            "result_json": _safe_json_dumps(
                {
                    "status": {"code": "completed", "message": "poster_render_completed"},
                    "decision": {
                        "image_source": result.decision.image_source.value,
                        "reason": result.decision.reason,
                    },
                    "output_path": result.output_path,
                    "output_filename": _output_filename(result.output_path),
                }
            ),
        }
        if show_design_guide:
            payload["design_guide"] = build_design_guide()
        return payload
    except PosterError as exc:
        payload = {
            "ok": False,
            "tool_name": TOOL_NAME,
            "status": {
                "code": "failed",
                "message": "poster_render_failed",
            },
            "next_action": "fix_input_and_retry",
            "rendered": False,
            "error_type": exc.__class__.__name__,
            "error": str(exc),
            "intake_questions": build_intake_questions(),
        }
        if bool(arguments.get("show_design_guide", False)):
            payload["design_guide"] = build_design_guide()
        return payload
    except Exception as exc:  # pragma: no cover - safety net for unexpected runtime failures
        payload = {
            "ok": False,
            "tool_name": TOOL_NAME,
            "status": {
                "code": "failed",
                "message": "poster_render_failed_internal",
            },
            "next_action": "retry_or_check_server_logs",
            "rendered": False,
            "error_type": exc.__class__.__name__,
            "error": str(exc) or "unexpected internal error",
            "intake_questions": build_intake_questions(),
        }
        if bool(arguments.get("show_design_guide", False)):
            payload["design_guide"] = build_design_guide()
        return payload
    finally:
        for temp_dir in temp_dirs:
            shutil.rmtree(temp_dir, ignore_errors=True)
