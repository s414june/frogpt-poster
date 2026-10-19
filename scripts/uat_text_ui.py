import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gpt_package.openai_tool import handle_tool_call


def _ask(prompt: str, default: str = "") -> str:
    if default:
        text = input(f"{prompt} [{default}]: ").strip()
        return text if text else default
    return input(f"{prompt}: ").strip()


def _split_csv(value: str) -> list[str]:
    if not value.strip():
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> int:
    print("=== Poster Tool UAT Text UI ===")
    print("You can test by text file or by direct fields.")
    mode = _ask("Mode (file/manual)", "file").lower()

    arguments: dict = {}
    if mode == "file":
        arguments["poster_text_file"] = _ask(
            "Path to JSON text file", "examples\\uat\\poster-input.json"
        )
        override = _ask("Override fields after file load? (y/n)", "n").lower()
        if override == "y":
            title = _ask("Title (optional)", "")
            body = _ask("Body (optional)", "")
            if title:
                arguments["title"] = title
            if body:
                arguments["body"] = body
    else:
        arguments["title"] = _ask("Title")
        arguments["body"] = _ask("Body")
        arguments["user_image_paths"] = _split_csv(
            _ask("User image paths (comma-separated, optional)", "")
        )
        arguments["open_source_font_paths"] = _split_csv(
            _ask("Open-source font paths (comma-separated, optional)", "")
        )
        arguments["width"] = int(_ask("Width", "1080"))
        arguments["height"] = int(_ask("Height", "1350"))
        arguments["allow_ai_fallback"] = (
            _ask("Allow AI fallback? (true/false)", "true").lower() == "true"
        )

    print("\n--- Calling tool ---")
    result = handle_tool_call(arguments)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("--- End ---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

