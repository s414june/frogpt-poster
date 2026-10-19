"""OpenAI Apps/Tools compatible tool definition and handler."""

from .client import PosterGenerator
from .errors import PosterError
from .errors import ValidationError
from .font_discovery import discover_open_source_fonts
from .text_input import load_request_from_text_file
from .types import PosterRequest

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
                "title": {"type": "string"},
                "body": {"type": "string"},
                "user_image_paths": {"type": "array", "items": {"type": "string"}},
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
    if arguments.get("poster_text_file"):
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


def handle_tool_call(arguments: dict) -> dict:
    try:
        request = _build_request(arguments)
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
            "notes": result.notes,
        }
    except PosterError as exc:
        return {
            "ok": False,
            "tool_name": TOOL_NAME,
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }
