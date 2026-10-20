"""Stateless Streamable HTTP MCP adapter for poster rendering."""
import json
import base64
import io
import hashlib
import re
import os
import logging
import traceback
from urllib.parse import urlparse
from urllib.request import build_opener, HTTPRedirectHandler
from urllib.error import URLError

from PIL import Image, UnidentifiedImageError
import sys
import time
import uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler


from gpt_package.openai_tool import handle_tool_call, _get_generated_background_base64, _is_generated_background_text_free_confirmed
from gpt_package.errors import ValidationError
from gpt_package.workflow import ASSISTANT_INSTRUCTIONS, assistant_execution_contract
from gpt_package.blob_workflow import STORE_TOOL, ASSET_REFS_SCHEMA, store_asset, run_with_storage

NAME = "prepare_poster"
_INTAKE_SESSION_MAX = 512
_INTAKE_SESSION_TTL_SECONDS = 60 * 60 * 12
_INTAKE_SESSIONS: dict[str, dict] = {}
_MAX_REQUEST_BYTES = 16 * 1024 * 1024
_MAX_EMBED_FULLSIZE_BASE64 = 5_500_000
_MAX_STRUCTURED_PREVIEW_BASE64 = 2_000_000
_MAX_STRUCTURED_FULLSIZE_BASE64 = 5_500_000
_DATA_URL_IMAGE_PREFIX = re.compile(r"^data:image/(jpeg|png|webp);base64,", re.IGNORECASE)
_ATTACHMENT_MAX_BYTES = 8 * 1024 * 1024
_ATTACHMENT_ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp"}
FILE_SCHEMA = {
    "type": "object",
    "properties": {key: {"type": "string"} for key in
                   ("download_url", "file_id", "mime_type", "file_name")},
    "required": ["download_url", "file_id"],
    "additionalProperties": False,
}

class _NoAttachmentRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValidationError("attachment redirect rejected; request a fresh file reference")


# File download URLs are host-issued and should not require redirects.
urlopen = build_opener(_NoAttachmentRedirects()).open
SCHEMA = {
    "type": "object",
    "properties": {
        "preview_only": {"type": "boolean", "description": "Only true when the user asks to preview a draft before adding copy."},
        "request_intake_only": {"type": "boolean"},
        "subject_source": {"type": "string", "enum": ["user_upload", "ai_generated"]},
        "subject_position": {"type": "object", "description": "x/y/width/height in final canvas pixels; image fits preserving aspect ratio."},
        "asset_refs": ASSET_REFS_SCHEMA,
        "intake_confirmed": {"type": "boolean"},
        "typography_confirmed": {"type": "boolean", "description": "For preview_only: explicit approval after the same draft preview. Not an upload authorization."},
        "approved_draft_sha256": {"type": "string", "description": "Copy draft_image_sha256 from the previously displayed text-free preview; must match the same image when approving typography."},
        "intake_session_token": {"type": "string", "minLength": 8, "maxLength": 128},
        "poster_request": {"type": "object"},
        "design_variant": {"type": "string", "enum": ["reinterpret", "faithful"], "description": "Default reinterpret: new palette for colorful references, rearrange at least two structural decisions; faithful only when explicitly requested."},
        "typography_grid": {"type": "boolean", "description": "Default true in reference mode: snap measured text to baseline grid, enforce 5% margin and 2-unit text/subject gaps, bounded repair; report large gaps within group."},
        "protected_regions": {"type": "array", "maxItems": 24, "items": {"type": "object"}, "description": "GPT visually identifies subject/photo rectangles on the generated visual, in canvas pixels: x, y, width, height. Not automatic detection."},
        "design_reference": {"type": "boolean", "description": "Use the user poster as inspiration only; resolve an independent subject/background and optional text_layers."},
        "reference_style_description": {"type": "string", "description": "GPT visual analysis: palette, composition, texture, lighting, hierarchy and reserved text space."},
        "text_layers": {"type": "array", "maxItems": 24, "items": {"type": "object"}, "description": "Exact text overlay definitions in canvas pixels: text, font_family, font_weight (400/700; kai/rounded only 400), font_size (independent per layer), color (#RRGGBB), x, y, width, height, align, line_spacing. Infer weight and spacing visually from reference; defaults only when unknown. Overflow fails explicitly."},
        "font_family": {"type": "string", "description": "Default sans (黑體). Request serif (明體/宋體), kai (楷體), rounded (圓體). Also accepted in poster_request.style.font_family. Unsupported names fail explicitly."},
        "text_align": {"type": "string", "enum": ["left", "center", "right"], "description": "Alignment for every copy block."},
        "headline_source": {"type": "string", "enum": ["title", "body_first"], "description": "Use title to preserve the supplied headline and its explicit newlines as the large heading."},
        "body_y_ratio": {"type": "number", "minimum": 0, "maximum": 1, "description": "Top of subtitle/body block as canvas height ratio; clamped to keep text inside canvas. E.g. 0.64 moves copy closer to vertical center."},
        "title": {"type": "string", "minLength": 1, "maxLength": 120},
        "body": {"type": "string", "minLength": 1, "maxLength": 4000},
        "width": {"type": "integer", "minimum": 256, "maximum": 4096},
        "height": {"type": "integer", "minimum": 256, "maximum": 4096},
        "primary_color": {"type": "string"},
        "secondary_color": {"type": "string"},
        "accent_color": {"type": "string"},
        "subject": {"type": "string"},
        "background_mode": {"type": "string", "enum": ["auto", "solid", "gradient", "reference"]},
        "image_role_mode": {"type": "string", "enum": ["auto", "subject", "background", "both"]},
        "geometry_image_base64": {"type": "string", "description": "GPT-drawn transparent PNG at final canvas size; background → geometry → subject. Preferred in GPT; no recoloring or cropping."},
        "geometry_layers": {"type": "array", "maxItems": 24, "items": {"type": "object"}, "description": "GPT geometry behind subject on any background: shape circle|rectangle|line, canvas x/y/width/height, fill/stroke #RRGGBB, opacity 0–1, stroke_width."},
        "geometry_enabled": {"type": "boolean"},
        "subject_mask_mode": {"type": "string", "enum": ["rounded", "feather"]},
        "subject_border_px": {"type": "integer", "minimum": 0, "maximum": 20},
        "background_color_hint": {"type": "string"},
        "creative_source_preference": {
            "type": "string",
            "enum": ["auto", "real_image_priority", "gpt_generate"],
        },
        "intake_answers": {"type": "object"},
        "reference_image_urls": {"type": "array", "items": {"type": "string"}},
        "reference_image_paths": {"type": "array", "items": {"type": "string"}},
        "reference_image_base64": {"type": "array", "items": {"type": "string"}},
        "generated_background_base64": {"type": "string"},
        "generated_background_text_free_confirmed": {"type": "boolean"},
        "list_design_references": {"type": "boolean", "description": "List local design inspiration previews and attribution metadata, separate from background photos."},
        "design_reference_ids": {"type": "array", "items": {"type": "string"}, "description": "Selected inspiration catalog IDs. Required credits merge into a single row with Pexels photo credits."},
        "use_local_reference_library": {"type": "boolean", "description": "Use saved Pexels library without API; omit ID to list available author-credited photos."},
        "reference_library_id": {"type": "string", "description": "Select a saved manifest photo ID, independent of Pexels API. Foreground product goes in subject_image_base64."},
        "pexels_query": {"type": "string", "description": "Online API search only, not saved photos."},
        "pexels_orientation": {"type": "string"},
        "pexels_per_page": {"type": "integer", "minimum": 1, "maximum": 10},
        "auto_pexels_fallback": {"type": "boolean"},
        "use_reference_as_fallback": {"type": "boolean"},
        "user_image_base64": {"type": "array", "items": {"type": "string"}},
        "user_image_urls": {"type": "array", "items": {"type": "string"}},
        "user_image_paths": {"type": "array", "items": {"type": "string"}},
        "subject_image_base64": {"type": "array", "items": {"type": "string"}},
        "subject_image_urls": {"type": "array", "items": {"type": "string"}},
        "subject_image_paths": {"type": "array", "items": {"type": "string"}},
        "regenerate_variant": {"type": "boolean"},
        "variation_token": {"type": "string"},
        "show_design_guide": {"type": "boolean"},
        "subject_image": {**FILE_SCHEMA, "description": "Original product attachment; host supplies the file reference. No Base64 conversion tool needed."},
        "background_image": {**FILE_SCHEMA, "description": "Background photo attachment."},
        "reference_image": {**FILE_SCHEMA, "description": "Design inspiration attachment."},
        "draft_image": {**FILE_SCHEMA, "description": "Legacy complete text-free draft including background and subject. Separate from background_image/subject_image."},
        "geometry_image": {**FILE_SCHEMA, "description": "Transparent PNG geometry at final canvas size."},
    },
    "required": [],
    "additionalProperties": False,
}
TOOL = {
    "name": NAME,
    "description": ASSISTANT_INSTRUCTIONS,
    "inputSchema": SCHEMA,
    "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
    "_meta": {"openai/fileParams": ["subject_image", "background_image", "reference_image", "draft_image", "geometry_image"]},
}


def _local_path_inputs_allowed() -> bool:
    raw = os.getenv("FROGPT_ALLOW_LOCAL_IMAGE_PATHS")
    if raw is None:
        return not bool(os.getenv("VERCEL") or os.getenv("VERCEL_ENV"))
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _image_input_contract() -> dict:
    allow_local_paths = _local_path_inputs_allowed()
    accepted_fields = [
        "asset_refs",
        "geometry_image_base64",
        "user_image_base64",
        "subject_image_base64",
        "reference_image_base64",
        "generated_background_base64",
    ]
    if allow_local_paths:
        accepted_fields.extend(["user_image_paths", "subject_image_paths", "reference_image_paths"])
    accepted_fields.extend(TOOL["_meta"]["openai/fileParams"])
    not_accepted = [
        "user_image_urls",
        "subject_image_urls",
        "reference_image_urls",
    ]
    if not allow_local_paths:
        not_accepted = ["user_image_paths", "subject_image_paths", "reference_image_paths", *not_accepted]
    rule = "Prefer top-level attachment file parameters directly on prepare_poster; the host supplies download_url/file_id. Reuse returned asset_refs. store_poster_asset is optional; base64 data URLs remain supported."
    if allow_local_paths:
        rule += " Local image paths are also accepted because FROGPT_ALLOW_LOCAL_IMAGE_PATHS is enabled. URLs are still rejected."
    else:
        rule += " No arbitrary paths or URLs."
    return {
        "accepted_fields": accepted_fields,
        "not_accepted_fields": not_accepted,
        "required_data_url_prefix_examples": [
            "data:image/jpeg;base64,...",
            "data:image/png;base64,...",
        ],
        "rule": rule,
    }


def _image_input_contract_text() -> str:
    if _local_path_inputs_allowed():
        return (
            "圖片輸入規則：優先直接傳 subject_image/background_image 等附件欄位，之後重用 asset_refs；store_poster_asset 為可選，也接受實際 base64（data URL）。\n"
            "目前已啟用本機路徑輸入（FROGPT_ALLOW_LOCAL_IMAGE_PATHS=true），可傳 *_image_paths；圖片網址（URL）仍不接受。"
        )
    return (
        "圖片輸入規則：優先直接傳 subject_image/background_image 等附件欄位，之後重用 asset_refs；store_poster_asset 為可選，也接受實際 base64（data URL）。\n"
        "不要傳本機/沙箱路徑，也不要傳圖片網址（URL）。\n"
        "正確示例：subject_image_base64: [\"data:image/jpeg;base64,...\"]"
    )


def _assistant_execution_contract() -> dict:
    return assistant_execution_contract()


def _compact_output(output: dict) -> dict:
    compact = dict(output)
    code = (output.get("status") or {}).get("code", "failed")
    compact.setdefault("poster_status", {"needs_input":"needs_user_input", "awaiting_typography_confirmation":"needs_user_input", "needs_background_generation":"needs_user_input"}.get(code, code if code in ("completed", "failed", "needs_subject_generation", "ready_to_render") else "needs_user_input"))
    if output.get("stored") and output.get("image_url"):
        for key in list(compact):
            if "base64" in key or "data_url" in key: compact.pop(key,None)
        compact.pop("request",None)
        compact.pop("output_path",None)
        return compact
    image_b64 = compact.pop("output_image_base64", None)
    preview_b64 = compact.pop("output_preview_base64", None)
    data_url = compact.pop("output_image_data_url", None)
    preview_data_url = compact.pop("output_preview_data_url", None)
    compact.pop("output_download_data_url", None)
    compact.pop("output_preview_markdown", None)
    if isinstance(image_b64, str):
        compact["output_image_base64_length"] = len(image_b64)
    if isinstance(preview_b64, str):
        compact["output_preview_base64_length"] = len(preview_b64)
    if isinstance(data_url, str):
        compact["output_image_data_url_length"] = len(data_url)
    if isinstance(preview_data_url, str):
        compact["output_preview_data_url_length"] = len(preview_data_url)
    # Relay-safe payloads for clients/channels that cannot forward image blocks.
    relay: dict = {
        "preview_available": False,
        "fullsize_available": False,
        "preview_limit_base64_bytes": _MAX_STRUCTURED_PREVIEW_BASE64,
        "fullsize_limit_base64_bytes": _MAX_STRUCTURED_FULLSIZE_BASE64,
    }
    if isinstance(preview_b64, str) and preview_b64:
        if len(preview_b64) <= _MAX_STRUCTURED_PREVIEW_BASE64:
            relay["preview_available"] = True
            relay["preview_base64"] = preview_b64
            relay["preview_mime_type"] = output.get("output_preview_mime_type", "image/jpeg")
    if isinstance(image_b64, str) and image_b64:
        if len(image_b64) <= _MAX_STRUCTURED_FULLSIZE_BASE64:
            relay["fullsize_available"] = True
            relay["fullsize_base64"] = image_b64
            relay["fullsize_mime_type"] = output.get("output_mime_type", "image/png")
            relay["fullsize_filename"] = output.get("output_filename", "poster.png")
    compact["relay_payload"] = relay
    request = compact.get("request")
    if isinstance(request, dict):
        compact["request"] = _compact_request(request)
    if compact.get("pipeline_stage") == "completed":
        compact.pop("intake_questions", None)
        compact.pop("result_json", None)
    return compact


def _compact_request(request: dict) -> dict:
    copy = dict(request)
    assets = copy.get("assets")
    if isinstance(assets, dict):
        assets_copy = dict(assets)
        font_paths = assets_copy.get("open_source_font_paths")
        if isinstance(font_paths, list):
            assets_copy["open_source_font_paths_count"] = len(font_paths)
            assets_copy["open_source_font_paths_sample"] = font_paths[:3]
            assets_copy.pop("open_source_font_paths", None)
        copy["assets"] = assets_copy
    return copy


def _has_render_brief(args: dict) -> bool:
    title = str(args.get("title", "")).strip()
    body = str(args.get("body", "")).strip()
    if title and body:
        return True
    payload = args.get("poster_request")
    if not isinstance(payload, dict):
        return False
    p_title = str(payload.get("title", "")).strip()
    p_body = str(payload.get("body", "")).strip()
    if p_title and p_body:
        return True
    copy = payload.get("copy")
    if isinstance(copy, dict):
        headline = str(copy.get("headline", "")).strip()
        subtitle = str(copy.get("subtitle", "")).strip()
        cta = str(copy.get("cta", "")).strip()
        return bool(headline and (subtitle or cta))
    return False


def _prune_intake_sessions(now_ts: float) -> None:
    expired = [
        token for token, meta in _INTAKE_SESSIONS.items()
        if (now_ts - float(meta.get("updated_at", 0.0))) > _INTAKE_SESSION_TTL_SECONDS
    ]
    for token in expired:
        _INTAKE_SESSIONS.pop(token, None)
    if len(_INTAKE_SESSIONS) <= _INTAKE_SESSION_MAX:
        return
    old_tokens = sorted(_INTAKE_SESSIONS.items(), key=lambda kv: float(kv[1].get("updated_at", 0.0)))
    overflow = len(_INTAKE_SESSIONS) - _INTAKE_SESSION_MAX
    for token, _meta in old_tokens[:overflow]:
        _INTAKE_SESSIONS.pop(token, None)


def _ensure_intake_session_token(args: dict, now_ts: float) -> tuple[str, dict, bool]:
    maybe = _resolve_intake_session_token(args)
    from_request = isinstance(maybe, str) and bool(maybe.strip())
    if isinstance(maybe, str) and maybe.strip():
        token = maybe.strip()
    else:
        token = f"intake_{uuid.uuid4().hex}"
    state = _INTAKE_SESSIONS.get(token)
    if not isinstance(state, dict):
        state = {"intake_completed": False, "created_at": now_ts, "updated_at": now_ts}
        _INTAKE_SESSIONS[token] = state
    else:
        state["updated_at"] = now_ts
    return token, state, from_request


def _resolve_intake_session_token(args: dict) -> str:
    top = args.get("intake_session_token")
    if isinstance(top, str) and top.strip():
        return top.strip()
    payload = args.get("poster_request")
    if isinstance(payload, dict):
        nested = payload.get("intake_session_token")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return ""


def _resolve_intake_confirmed(args: dict) -> bool:
    top = args.get("intake_confirmed")
    if isinstance(top, bool):
        return top
    payload = args.get("poster_request")
    if isinstance(payload, dict):
        nested = payload.get("intake_confirmed")
        if isinstance(nested, bool):
            return nested
    return False


def _has_non_base64_image_inputs(args: dict) -> bool:
    allow_local_paths = _local_path_inputs_allowed()
    disallowed_keys = (
        "user_image_urls",
        "subject_image_urls",
        "reference_image_urls",
    )
    if not allow_local_paths:
        disallowed_keys = ("user_image_paths", "subject_image_paths", "reference_image_paths", *disallowed_keys)
    if any(bool(args.get(k)) for k in disallowed_keys):
        return True
    payload = args.get("poster_request")
    if isinstance(payload, dict):
        if bool(payload.get("reference_image_urls")):
            return True
        if not allow_local_paths and bool(payload.get("reference_image_paths")):
            return True
        assets = payload.get("assets")
        if isinstance(assets, dict):
            if (
                bool(assets.get("user_image_urls"))
                or bool(assets.get("subject_image_urls"))
            ):
                return True
            if not allow_local_paths and (
                bool(assets.get("user_image_paths"))
                or bool(assets.get("subject_image_paths"))
            ):
                return True
    return False


def _has_invalid_image_data_url_inputs(args: dict) -> bool:
    def _invalid_data_url(value) -> bool:
        return not isinstance(value, str) or not _DATA_URL_IMAGE_PREFIX.match(value.strip())

    payload = args.get("poster_request")
    payload_assets = payload.get("assets", {}) if isinstance(payload, dict) and isinstance(payload.get("assets"), dict) else {}
    checks = [
        _as_list(args.get("user_image_base64", payload_assets.get("user_image_base64"))),
        _as_list(args.get("subject_image_base64", payload_assets.get("subject_image_base64"))),
        _as_list(args.get("reference_image_base64", payload.get("reference_image_base64") if isinstance(payload, dict) else None)),
        _as_list(args.get("generated_background_base64", payload.get("generated_background_base64") if isinstance(payload, dict) else None)),
        _as_list(args.get("geometry_image_base64", payload_assets.get("geometry_image_base64"))),
    ]
    for group in checks:
        for item in group:
            if item and _invalid_data_url(item):
                return True
    return False


def _download_attachment_as_data_url(item: dict) -> str:
    if not isinstance(item, dict):
        raise ValidationError("attachment object must be a JSON object")
    url = str(item.get("download_url", "")).strip()
    if not url:
        raise ValidationError("attachment download_url is required")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    allowed = (host == "chatgpt.com" or host.endswith(".chatgpt.com")
               or host.endswith(".oaiusercontent.com")
               or (host.startswith(("oaisdmntpr", "oaisdsorpr")) and host.endswith(".blob.core.windows.net"))
               or (host.startswith("oaisdmntpr") and ".s3." in host and host.endswith(".amazonaws.com")))
    if parsed.scheme != "https" or not allowed or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValidationError("attachment download_url must be a host-issued HTTPS file URL")
    mime_hint = str(item.get("mime_type", "")).strip().lower()
    if mime_hint and mime_hint not in _ATTACHMENT_ALLOWED_MIME:
        raise ValidationError("attachment mime_type must be PNG/JPEG/WebP")
    try:
        with urlopen(url, timeout=20) as response:
            content = response.read(_ATTACHMENT_MAX_BYTES + 1)
    except (URLError, OSError, TimeoutError) as exc:
        # Do not expose signed URLs or network exception strings.
        raise ValidationError("attachment download failed; request a fresh file reference") from exc
    if not content:
        raise ValidationError("attachment bytes are empty")
    if len(content) > _ATTACHMENT_MAX_BYTES:
        raise ValidationError("attachment image exceeds size limit")
    try:
        with Image.open(io.BytesIO(content)) as img:
            fmt = str(img.format or "").upper()
            if max(img.size) > 4096 or img.width * img.height > 16_000_000 or getattr(img, "n_frames", 1) != 1:
                raise ValidationError("attachment dimensions or frame count exceed limits")
            img.verify()
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError("attachment is not a valid image payload") from exc
    mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}.get(fmt)
    if not mime:
        raise ValidationError("attachment image format must be PNG/JPEG/WebP")
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


def _materialize_attachment_file_inputs(args: dict) -> dict:
    prepared = dict(args)
    payload = prepared.get("poster_request")
    payload = payload if isinstance(payload, dict) else {}
    assets = payload.get("assets")
    assets = assets if isinstance(assets, dict) else {}
    refs = prepared.get("asset_refs", payload.get("asset_refs"))
    refs = refs if isinstance(refs, dict) else {}
    mapping = (
        ("subject_image", "subject_image_base64", "subjects"),
        ("background_image", "user_image_base64", "background"),
        ("reference_image", "reference_image_base64", "references"),
        ("draft_image", "generated_background_base64", "draft"),
        ("geometry_image", "geometry_image_base64", "geometry"),
    )
    for attachment_key, target_key, ref_key in mapping:
        direct = prepared.get(attachment_key)
        nested = payload.get(attachment_key)
        if direct and nested:
            raise ValidationError(f"{attachment_key} provided twice")
        raw_value = direct or nested
        if not raw_value:
            continue
        if prepared.get(target_key) or payload.get(target_key) or assets.get(target_key):
            raise ValidationError(f"{attachment_key} conflicts with {target_key}")
        if refs.get(ref_key):
            raise ValidationError(f"{attachment_key} conflicts with asset_refs.{ref_key}")
        items = _as_list(raw_value)
        data_urls = [_download_attachment_as_data_url(item) for item in items]
        if len(data_urls) != 1:
            raise ValidationError(f"{attachment_key} accepts exactly one file")
        prepared[target_key] = data_urls[0] if ref_key in ("draft", "geometry") else data_urls
        if attachment_key == "background_image":
            prepared["image_role_mode"] = "background"
        if attachment_key == "reference_image":
            prepared["design_reference"] = True
        # File objects contain signed URLs, which must not leak into render results.
        prepared.pop(attachment_key, None)
        if attachment_key in payload:
            payload = dict(payload)
            payload.pop(attachment_key)
            prepared["poster_request"] = payload
    return prepared


def _build_attachment_input_rejection(token: str, intake_completed: bool, message: str) -> dict:
    contract = _image_input_contract()
    return {
        "ok": True,
        "tool_name": NAME,
        "pipeline_stage": "attachment_preflight",
        "status": {
            "code": "needs_input",
            "message": "attachment_download_failed_or_invalid",
        },
        "next_action": "reattach_or_use_base64_or_store_tool",
        "rendered": False,
        "intake_session_token": token,
        "intake_session_state": {
            "intake_completed": bool(intake_completed),
            "ttl_seconds": _INTAKE_SESSION_TTL_SECONDS,
        },
        "user_friendly_hint": {
            "what_happened": message,
            "please_do": [
                "請重新附上同一張圖片，或改用 store_poster_asset 後傳 asset_refs",
                "也可改用 data URL base64 欄位",
            ],
            "accepted_fields": contract["accepted_fields"],
            "not_accepted_fields": contract["not_accepted_fields"],
        },
        "image_input_contract": contract,
    }


def _build_non_base64_input_rejection(token: str, intake_completed: bool) -> dict:
    contract = _image_input_contract()
    return {
        "ok": True,
        "tool_name": NAME,
        "pipeline_stage": "intake",
        "status": {
            "code": "needs_input",
            "message": "image_upload_required_use_data_url_base64",
        },
        "next_action": "reupload_image_as_base64_only",
        "rendered": False,
        "intake_session_token": token,
        "intake_session_state": {
            "intake_completed": bool(intake_completed),
            "ttl_seconds": _INTAKE_SESSION_TTL_SECONDS,
        },
        "user_friendly_hint": {
            "what_happened": "收到的圖片格式不是 base64（data URL）。",
            "please_do": [
                "請改用圖片上傳（base64 data URL）",
                "不要使用圖片路徑，也不要使用圖片網址（URL）",
            ],
            "accepted_fields": contract["accepted_fields"],
            "not_accepted_fields": contract["not_accepted_fields"],
            "required_data_url_prefix_examples": contract["required_data_url_prefix_examples"],
        },
        "image_input_contract": contract,
    }


def _rewrite_failed_output_for_retry(output: dict) -> dict:
    status = output.get("status", {})
    if str(status.get("code", "")).strip() != "failed":
        return output
    contract = _image_input_contract()
    error_text = str(output.get("error", "")).strip().lower()
    # Never relabel renderer/runtime failures as invalid base64 or claim recovery.
    is_image_validation = output.get("error_type") == "ValidationError" and any(
        term in error_text for term in ("base64", "image path", "image url", "reference image path")
    )
    if not is_image_validation:
        failed = dict(output)
        failed["failure_stage"] = "server_processing"
        failed["next_action"] = "inspect_server_diagnostics_do_not_blame_attachment_or_retry_blindly"
        failed["user_friendly_hint"] = {
            "what_happened": "套件處理未完成；請依伺服器診斷確認原因，不要推定為附件或 base64 問題。"
        }
        return failed
    hint_message = "工具執行暫時失敗，請使用 base64 圖片（data URL）重試。"
    if "base64" in error_text:
        hint_message = "圖片 base64 格式可能無效，請重新上傳完整的 data URL。"
    elif "url" in error_text:
        hint_message = "目前只接受 base64 圖片，請將圖片轉為 data URL 後重試。"
    elif "path" in error_text:
        hint_message = "收到的是圖片路徑，雲端環境通常無法讀取。請改用 base64（data URL）。"

    rewritten = dict(output)
    rewritten["ok"] = True
    rewritten["pipeline_stage"] = "needs_retry_input"
    rewritten["failure_stage"] = "image_input_validation"
    rewritten["status"] = {
        "code": "needs_input",
        "message": "retry_with_supported_image_input",
    }
    rewritten["next_action"] = "retry_with_base64_only"
    rewritten["rendered"] = False
    rewritten["user_friendly_hint"] = {
        "what_happened": hint_message,
        "please_do": [
            "使用同一個對話上下文再呼叫一次工具",
            "使用 user_image_base64 / subject_image_base64（data URL）",
        ],
        "accepted_fields": contract["accepted_fields"],
        "not_accepted_fields": contract["not_accepted_fields"],
        "required_data_url_prefix_examples": contract["required_data_url_prefix_examples"],
    }
    rewritten["diagnostics"] = {
        "original_status_code": "failed",
        "error_type": str(output.get("error_type", "")),
        "reason": hint_message,
    }
    rewritten["next_action"] = "retry_with_attachment_or_asset_ref_or_base64"
    rewritten.pop("error", None)
    rewritten.pop("error_type", None)
    return rewritten


def _run_staged_call(args: dict, intake_completed: bool) -> dict:
    return run_with_storage(args, intake_completed, _run_staged_call_legacy)


def _run_staged_call_legacy(args: dict, intake_completed: bool) -> dict:
    args = dict(args)
    payload = args.get("poster_request") or {}
    layout = payload.get("layout") or {}
    args.setdefault("width", layout.get("width", 480))
    args.setdefault("height", layout.get("height", 640))
    if not args.get("preview_only", payload.get("preview_only", False)):
        return handle_tool_call(args)
    args = dict(args)
    payload = args.get("poster_request") or {}
    confirmed = args.get("typography_confirmed", payload.get("typography_confirmed", False))
    if not isinstance(confirmed, bool):
        return {"ok": False, "rendered": False, "status": {"code": "failed", "message": "typography_confirmed_must_be_boolean"}}
    # Mobile test defaults, while preserving explicit dimensions and aspect ratios.
    layout = payload.get("layout") or {}
    args.setdefault("width", layout.get("width", 480))
    args.setdefault("height", layout.get("height", 640))
    generated = _get_generated_background_base64(args)
    if generated:
        if not _is_generated_background_text_free_confirmed(args):
            return {"ok": True, "rendered": False, "status": {"code": "needs_input", "message": "confirm_text_free_image_first"}, "next_action": "inspect_image_and_confirm_no_poster_copy_or_watermark"}
        try:
            if not generated.startswith(("data:image/jpeg;base64,", "data:image/png;base64,")):
                raise ValueError("expected JPEG/PNG base64 data URL")
            raw = base64.b64decode(generated.split(",", 1)[1], validate=True)
            with Image.open(io.BytesIO(raw)) as source:
                source.load()
                draft = source.convert("RGB")
            draft.thumbnail((640, 640), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            draft.save(buffer, format="JPEG", quality=65, optimize=True)
            preview = base64.b64encode(buffer.getvalue()).decode("ascii")
        except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
            return {"ok": True, "rendered": False, "status": {"code": "needs_input", "message": "invalid_generated_image_base64"}, "next_action": "reencode_actual_image_bytes_as_jpeg_or_png_data_url"}
        draft_sha = hashlib.sha256(raw).hexdigest()
        approved_sha = args.get("approved_draft_sha256", payload.get("approved_draft_sha256"))
        if not confirmed or approved_sha != draft_sha:
            return {
                "ok": True, "rendered": False, "pipeline_stage": "awaiting_typography_confirmation",
                "status": {"code": "awaiting_typography_confirmation", "message": "text_free_draft_ready_wait_for_user"},
                "next_action": "show_draft_ask_ready_for_copy_then_stop",
                "confirmation_question": "無字海報已準備好，是否準備好加上文案？",
                "draft_image_sha256": draft_sha,
                "output_preview_base64": preview, "output_preview_mime_type": "image/jpeg",
                "retry_arguments_hint": {"typography_confirmed": True, "generated_background_text_free_confirmed": True, "reuse_same_generated_background_base64": True, "approved_draft_sha256": draft_sha},
            }
        if not _has_render_brief(args):
            return {"ok": True, "rendered": False, "status": {"code": "needs_input", "message": "copy_required"}, "next_action": "ask_user_for_copy"}
        # Use the complete approved composition unchanged; typography is the only overlay.
        has_geometry_image = bool(args.get("geometry_image_base64") or (payload.get("assets") or {}).get("geometry_image_base64"))
        args.update(image_role_mode="background" if has_geometry_image else "both", background_mode="reference")
        if not has_geometry_image:
            args["geometry_enabled"] = False
    elif confirmed and not _has_render_brief(args):
        return {"ok": True, "rendered": False, "status": {"code": "needs_input", "message": "copy_required"}, "next_action": "ask_user_for_copy"}
    assets = payload.get("assets") or {}
    if not _has_render_brief(args) and any(args.get(key) or assets.get(key) for key in (
        "user_image_base64", "subject_image_base64", "reference_image_base64", "user_image_paths", "subject_image_paths"
    )):
        return {"ok": True, "rendered": False, "status": {"code": "needs_input", "message": "copy_required"}, "next_action": "ask_user_for_copy"}
    if not _has_render_brief(args) and not confirmed:
        # Internal placeholders allow generating a visual brief before any copy exists.
        # These never reach the renderer: no-image requests return a generation prompt.
        args.setdefault("title", str(args.get("subject") or "無字海報設計"))
        args.setdefault("body", "文案待使用者確認後加入")
    return handle_tool_call(args)


def dispatch(message):
    try:
        return _dispatch(message)
    except Exception:
        diagnostic_id = uuid.uuid4().hex
        # Never log exception messages/locals: SDK failures can contain signed URLs.
        exc_type, _, tb = sys.exc_info()
        frames = [(Path(f.filename).name, f.lineno, f.name) for f in traceback.extract_tb(tb)]
        logging.getLogger(__name__).error("MCP internal failure diagnostic_id=%s type=%s frames=%s",
                                         diagnostic_id, exc_type.__name__, frames)
        return {"jsonrpc": "2.0", "id": message.get("id") if isinstance(message, dict) else None,
                "error": {"code": -32603, "message": "Internal error",
                          "data": {"diagnostic_id": diagnostic_id}}}


def _dispatch(message):
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
    if "id" not in message:
        return None
    result = {"jsonrpc": "2.0", "id": message["id"]}
    method = message["method"]
    params = message.get("params", {})
    if not isinstance(params, dict):
        result["error"] = {"code": -32602, "message": "params must be an object"}
        return result
    if method == "initialize":
        versions = ("2025-03-26", "2025-06-18", "2025-11-25")
        version = params.get("protocolVersion")
        result["result"] = {"protocolVersion": version if version in versions else versions[0], "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "FroGPT Poster", "version": "0.4.0"}, "instructions": ASSISTANT_INSTRUCTIONS}
    elif method == "ping":
        result["result"] = {}
    elif method == "tools/list":
        result["result"] = {"tools": [TOOL, STORE_TOOL]}
    elif method == "tools/call":
        args = params.get("arguments", {})
        if params.get("name") == "store_poster_asset":
            output=store_asset(args)
            result["result"]={"content":[{"type":"text","text":json.dumps(output,ensure_ascii=False)}],
                              "structuredContent":output,"isError":not output.get("ok")}
            return result
        if params.get("name") != NAME:
            result["error"] = {"code": -32602, "message": "Unknown tool"}
        elif not isinstance(args, dict) or set(args) - set(SCHEMA["properties"]):
            result["error"] = {"code": -32602, "message": "Arguments shape not allowed by schema."}
        else:
            now_ts = time.time()
            _prune_intake_sessions(now_ts)
            intake_session_token, intake_state, token_from_request = _ensure_intake_session_token(args, now_ts)
            try:
                args = _materialize_attachment_file_inputs(args)
            except ValidationError as exc:
                output = _build_attachment_input_rejection(
                    token=intake_session_token,
                    intake_completed=bool(intake_state.get("intake_completed", False)),
                    message=str(exc),
                )
                output["assistant_execution_contract"] = _assistant_execution_contract()
                content = [
                    {"type": "text", "text": json.dumps(_compact_output(output), ensure_ascii=False)},
                ]
                result["result"] = {
                    "content": content,
                    "structuredContent": _compact_output(output),
                    "isError": False,
                }
                return result
            if _has_non_base64_image_inputs(args):
                output = _build_non_base64_input_rejection(
                    token=intake_session_token,
                    intake_completed=bool(intake_state.get("intake_completed", False)),
                )
                output["assistant_execution_contract"] = _assistant_execution_contract()
                content = [
                    {
                        "type": "text",
                        "text": (
                            "目前只接受 base64 圖片（data URL）。\n"
                            "請改用圖片上傳（base64）後重試，不要使用 paths 或 URLs。\n"
                            + _image_input_contract_text()
                            + "\n\n禁止直接用 GPT 產生有字成品；修正圖片格式後依分段流程繼續。"
                        ),
                    },
                    {"type": "text", "text": json.dumps(_compact_output(output), ensure_ascii=False)},
                ]
                result["result"] = {
                    "content": content,
                    "structuredContent": _compact_output(output),
                    "isError": False,
                }
                return result
            if _has_invalid_image_data_url_inputs(args):
                output = _build_non_base64_input_rejection(
                    token=intake_session_token,
                    intake_completed=bool(intake_state.get("intake_completed", False)),
                )
                output["assistant_execution_contract"] = _assistant_execution_contract()
                content = [
                    {
                        "type": "text",
                        "text": (
                            "收到的圖片不是 data URL base64。\n"
                            "請改用 data:image/jpeg;base64,... 或 data:image/png;base64,... 格式重試。\n"
                            + _image_input_contract_text()
                            + "\n\n禁止直接用 GPT 產生有字成品；修正圖片格式後依分段流程繼續。"
                        ),
                    },
                    {"type": "text", "text": json.dumps(_compact_output(output), ensure_ascii=False)},
                ]
                result["result"] = {
                    "content": content,
                    "structuredContent": _compact_output(output),
                    "isError": False,
                }
                return result
            intake_confirmed_effective = not args.get("request_intake_only", False)
            call_args = dict(args)
            if intake_confirmed_effective and bool(call_args.get("regenerate_variant", False)):
                call_args.pop("variation_token", None)
            if not intake_confirmed_effective:
                call_args["request_intake_only"] = True
                call_args["show_design_guide"] = True
            output = _run_staged_call(call_args, intake_confirmed_effective)
            if output.get("stored") and output.get("image_url"):
                compact_output=_compact_output(output)
                preview=output.get("output_preview_base64")
                content=[]
                if preview:
                    content.append({"type":"image","data":preview,"mimeType":"image/jpeg"})
                content.append({"type":"text","text":json.dumps(compact_output,ensure_ascii=False)})
                result["result"]={"content":content,"structuredContent":compact_output,"isError":not output.get("ok")}
                compact_output["intake_session_token"]=intake_session_token
                if output.get("pipeline_stage")=="awaiting_typography_confirmation":
                    content.append({"type":"text","text":"無字海報已準備好，是否準備好加上文案？停止並等待使用者明確同意。"})
                return result
            output = _rewrite_failed_output_for_retry(output)
            output["image_input_contract"] = _image_input_contract()
            output["assistant_execution_contract"] = _assistant_execution_contract()
            output["intake_session_token"] = intake_session_token
            output["intake_session_state"] = {
                "intake_completed": bool(intake_state.get("intake_completed", False)),
                "ttl_seconds": _INTAKE_SESSION_TTL_SECONDS,
            }
            if not intake_confirmed_effective:
                output["next_request_hint"] = {
                    "intake_session_token": intake_session_token,
                    "intake_confirmed": True,
                }
            if not intake_confirmed_effective and output.get("status", {}).get("code") != "needs_input":
                output["status"] = {
                    "code": "needs_input",
                    "message": "intake_questions_required_before_render",
                }
                output["next_action"] = "ask_user_intake_questions"
                output["rendered"] = False
            if intake_confirmed_effective and output.get("status", {}).get("code") != "needs_input":
                intake_state["intake_completed"] = True
                intake_state["updated_at"] = now_ts
                output["intake_session_state"]["intake_completed"] = True
            content = []
            status_code = output.get("status", {}).get("code")
            if status_code == "needs_input":
                questions = output.get("intake_questions", [])
                question_lines = []
                for q in questions:
                    question_lines.append(f"- {q.get('question', '')}")
                content.append(
                    {
                        "type": "text",
                        "text": (
                            "尚未渲染海報。請依 next_action 補齊必要內容並沿用原需求；僅缺必要使用者資料或授權時提問：\n"
                            + "\n".join(question_lines)
                            + "\n\n"
                            + _image_input_contract_text()
                            + "\n\n海報文案由 API 排版；預設繼續完成，只有 preview_only 才等草稿確認。"
                        ),
                    }
                )
            if status_code == "needs_background_generation":
                content.append({"type":"text", "text":"舊版完整底稿尚未通過無海報文案檢查；依 next_action 檢視同一張圖。預設不需使用者確認；不得將背景當獨立主體。"})
            if status_code == "awaiting_typography_confirmation":
                content.append({"type": "image", "data": output["output_preview_base64"], "mimeType": "image/jpeg"})
                content.append({"type": "text", "text": "無字海報已準備好，是否準備好加上文案？\n停止本輪工具呼叫，等待使用者下一則明確同意後才可設定 typography_confirmed=true。"})
            preview_b64 = output.get("output_preview_base64") or output.get("output_image_base64")
            preview_mime = output.get("output_preview_mime_type", output.get("output_mime_type", "image/png"))
            if output.get("ok") and output.get("rendered") and preview_b64:
                full_b64 = output.get("output_image_base64")
                full_mime = output.get("output_mime_type", "image/png")
                full_embedded = False
                # 1) Rendered image first for immediate preview
                content.append(
                    {
                        "type": "image",
                        "data": preview_b64,
                        "mimeType": preview_mime,
                    }
                )
                # 2) Delivery contract for GPT response behavior
                output["final_delivery_contract"] = {
                    "must_include_preview_thumbnail": True,
                    "must_include_fullsize_download": True,
                    "preview_field": "output_preview_base64",
                    "fullsize_field": "output_image_base64",
                }
                content.append(
                    {
                        "type": "text",
                        "text": (
                            "最終回覆請務必同時提供：\n"
                            "1) 縮圖預覽\n"
                            "2) 正式大小海報圖（可下載）"
                        ),
                    }
                )
                # 3) Embed full-size image when payload is still reasonable.
                if isinstance(full_b64, str) and full_b64 and len(full_b64) <= _MAX_EMBED_FULLSIZE_BASE64:
                    content.append(
                        {
                            "type": "image",
                            "data": full_b64,
                            "mimeType": full_mime,
                        }
                    )
                    full_embedded = True
                output["final_delivery_contract"]["fullsize_embedded"] = full_embedded
                output["final_delivery_contract"]["fullsize_embed_limit_base64_bytes"] = _MAX_EMBED_FULLSIZE_BASE64
                # 4) Download hint
                filename = output.get("output_filename", "poster.png")
                sha = str(output.get("output_image_sha256", "")).strip()
                short_sha = sha[:12] if sha else ""
                content.append(
                    {
                        "type": "text",
                        "text": (
                            "已完成渲染，請優先顯示上方圖片。\n"
                            f"下載檔名: {filename}\n"
                            f"輸出指紋: {short_sha}"
                        ),
                    }
                )
                content.append(
                    {
                        "type": "text",
                        "text": (
                            "若客戶端不支援 image content，請改走 API `/api/poster` 讀取 `output_image_data_url`。"
                        ),
                    }
                )
                content.append(
                    {
                        "type": "text",
                        "text": (
                            "對話模式轉送失敗時，請改用 structuredContent.relay_payload：\n"
                            "- relay_payload.preview_base64\n"
                            "- relay_payload.fullsize_base64（若 available）"
                        ),
                    }
                )
            elif output.get("ok") and output.get("rendered"):
                output["ok"] = False
                output["status"] = {
                    "code": "failed",
                    "message": "render_completed_but_preview_missing",
                }
                output["next_action"] = "retry_render"
                output["rendered"] = False
                content.append(
                    {
                        "type": "text",
                        "text": "渲染完成但預覽圖遺失，請重試一次。",
                    }
                )
            # 3) Structured/text details last
            compact_output = _compact_output(output)
            content.append({"type": "text", "text": json.dumps(compact_output, ensure_ascii=False)})
            result["result"] = {
                "content": content,
                "structuredContent": compact_output,
                "isError": not output.get("ok", False),
            }
    else:
        result["error"] = {"code": -32601, "message": "Method not found"}
    return result


class handler(BaseHTTPRequestHandler):
    def reply(self, status, payload=None):
        body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        if status == 405:
            self.send_header("Allow", "POST")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.reply(405)

    def do_DELETE(self):
        self.reply(405)

    def do_POST(self):
        origin = self.headers.get("Origin")
        if origin and origin not in ("https://chatgpt.com", "https://frogpt-poster.vercel.app"):
            self.reply(403, {"error": "Origin not allowed"})
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            self.reply(415, {"error": "Expected application/json"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > _MAX_REQUEST_BYTES:
                if size > _MAX_REQUEST_BYTES:
                    self.reply(
                        413,
                        {
                            "error": "payload_too_large",
                            "max_bytes": _MAX_REQUEST_BYTES,
                            "hint": "Use smaller/compressed base64 data URL images only; never paths or URLs.",
                        },
                    )
                else:
                    self.reply(400)
                return
            message = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeDecodeError):
            self.reply(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            return
        result = dispatch(message)
        self.reply(202 if result is None else 200, result)
