"""OpenAI Apps/Tools compatible tool definition and handler."""

import base64
import json
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from .client import PosterGenerator
from .errors import PosterError
from .errors import ValidationError
from .font_discovery import discover_open_source_fonts
from .text_input import load_request_from_text_file
from .types import PosterAssetSet, PosterLayout, PosterRequest

TOOL_NAME = "generate_poster_with_real_image_priority"


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
                "title": {"type": "string"},
                "body": {"type": "string"},
                "user_image_paths": {"type": "array", "items": {"type": "string"}},
                "user_image_urls": {"type": "array", "items": {"type": "string"}},
                "user_image_base64": {"type": "array", "items": {"type": "string"}},
                "open_source_font_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "width": {"type": "integer", "minimum": 256, "maximum": 4096},
                "height": {"type": "integer", "minimum": 256, "maximum": 4096},
                "allow_ai_fallback": {"type": "boolean"},
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
    if not request.assets.open_source_font_paths:
        request.assets.open_source_font_paths = discover_open_source_fonts()
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

    return request


def _from_inline_request(payload: dict) -> PosterRequest:
    if not isinstance(payload, dict):
        raise ValidationError("poster_request must be an object")
    assets = payload.get("assets", {})
    layout = payload.get("layout", {})
    return PosterRequest(
        title=str(payload.get("title", "")),
        body=str(payload.get("body", "")),
        assets=PosterAssetSet(
            user_image_paths=[str(item) for item in assets.get("user_image_paths", [])],
            open_source_font_paths=[
                str(item) for item in assets.get("open_source_font_paths", [])
            ],
        ),
        layout=PosterLayout(
            width=int(layout.get("width", 1080)),
            height=int(layout.get("height", 1350)),
        ),
        allow_ai_fallback=bool(payload.get("allow_ai_fallback", True)),
    )


def _download_image(url: str, output_path: Path) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValidationError(f"user image url must be http/https: {url}")
    with urlopen(url, timeout=20) as response:
        content = response.read()
    if not content:
        raise ValidationError(f"empty image content from url: {url}")
    output_path.write_bytes(content)


def _decode_base64_image(data: str, output_path: Path) -> None:
    token = data.strip()
    if token.startswith("data:"):
        _, token = token.split(",", 1)
    try:
        content = base64.b64decode(token, validate=True)
    except Exception as exc:
        raise ValidationError("user_image_base64 contains invalid base64") from exc
    if not content:
        raise ValidationError("user_image_base64 contains empty image data")
    output_path.write_bytes(content)


def _materialize_remote_images(arguments: dict, request: PosterRequest) -> str | None:
    urls = arguments.get("user_image_urls", [])
    b64_images = arguments.get("user_image_base64", [])
    if urls and not isinstance(urls, list):
        raise ValidationError("user_image_urls must be an array of strings")
    if b64_images and not isinstance(b64_images, list):
        raise ValidationError("user_image_base64 must be an array of strings")
    if not urls and not b64_images:
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

    request.assets.user_image_paths = materialized + request.assets.user_image_paths
    return str(temp_dir)


def _encode_output_image(path: str | None) -> str | None:
    if not path:
        return None
    file_path = Path(path)
    if not file_path.is_file():
        return None
    return base64.b64encode(file_path.read_bytes()).decode("ascii")


def _safe_json_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def handle_tool_call(arguments: dict) -> dict:
    temp_dir: str | None = None
    try:
        request = _build_request(arguments)
        temp_dir = _materialize_remote_images(arguments, request)
        generator = PosterGenerator()
        result = generator.generate(request)
        return {
            "ok": True,
            "tool_name": TOOL_NAME,
            "decision": {
                "image_source": result.decision.image_source.value,
                "reason": result.decision.reason,
            },
            "request": request.to_dict(),
            "output_path": result.output_path,
            "output_mime_type": "image/png",
            "output_image_base64": _encode_output_image(result.output_path),
            "notes": result.notes,
            "result_json": _safe_json_dumps(
                {
                    "decision": {
                        "image_source": result.decision.image_source.value,
                        "reason": result.decision.reason,
                    },
                    "output_path": result.output_path,
                }
            ),
        }
    except PosterError as exc:
        return {
            "ok": False,
            "tool_name": TOOL_NAME,
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
