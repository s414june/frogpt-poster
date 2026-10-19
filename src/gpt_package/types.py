"""Core data models for poster generation plugin."""

from dataclasses import asdict, dataclass, field
from enum import Enum


class ImageSource(str, Enum):
    USER_IMAGE = "user_image"
    AI_FALLBACK = "ai_fallback"


@dataclass(slots=True)
class PosterAssetSet:
    user_image_paths: list[str] = field(default_factory=list)
    open_source_font_paths: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PosterLayout:
    width: int = 1080
    height: int = 1350


@dataclass(slots=True)
class PosterRequest:
    title: str
    body: str
    assets: PosterAssetSet = field(default_factory=PosterAssetSet)
    layout: PosterLayout = field(default_factory=PosterLayout)
    allow_ai_fallback: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class PosterDecision:
    image_source: ImageSource
    reason: str


@dataclass(slots=True)
class PosterResult:
    output_path: str | None
    decision: PosterDecision
    notes: list[str] = field(default_factory=list)
