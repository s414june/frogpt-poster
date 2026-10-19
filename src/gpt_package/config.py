"""Runtime configuration placeholders."""

from dataclasses import dataclass


@dataclass(slots=True)
class PosterConfig:
    default_width: int = 1080
    default_height: int = 1350
    enable_ai_fallback: bool = True
