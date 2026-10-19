"""Local open-source font discovery helpers."""

from pathlib import Path

DEFAULT_FONT_DIR = Path("assets") / "fonts"
_EXTENSIONS = {".ttf", ".otf", ".ttc"}


def discover_open_source_fonts(base_dir: str | None = None) -> list[str]:
    root = Path(base_dir) if base_dir else DEFAULT_FONT_DIR
    if not root.is_dir():
        return []
    result: list[str] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in _EXTENSIONS:
            result.append(str(path))
    return sorted(result)

