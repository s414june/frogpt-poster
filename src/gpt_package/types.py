"""Core data models for poster generation plugin."""

from dataclasses import asdict, dataclass, field
from enum import Enum


class ImageSource(str, Enum):
    USER_IMAGE = "user_image"
    AI_FALLBACK = "ai_fallback"


@dataclass(slots=True)
class PosterAssetSet:
    user_image_paths: list[str] = field(default_factory=list)
    subject_image_paths: list[str] = field(default_factory=list)
    open_source_font_paths: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PosterLayout:
    width: int = 1080
    height: int = 1350


@dataclass(slots=True)
class PosterStyle:
    typography_grid: bool = False
    protected_regions: list[dict] = field(default_factory=list)
    layout_report: dict = field(default_factory=dict)
    text_layers: list[dict] = field(default_factory=list)
    background_mode: str = "auto"
    image_role_mode: str = "auto"
    geometry_layers: list[dict] = field(default_factory=list)
    geometry_enabled: bool = True
    subject_mask_mode: str = "rounded"
    subject_border_px: int = 0
    background_color_hint: str = ""
    primary_color: str = "#F6F1E8"
    secondary_color: str = "#A8BFA8"
    accent_color: str = "#6D8A72"
    subject: str = ""
    panel_ratio: float = 0.24
    font_family: str = "sans"
    text_align: str = "center"
    headline_source: str = "body_first"
    body_y_ratio: float | None = None
    title_max_lines: int = 2
    body_max_lines: int = 4
    background_shape_count: int = 0
    background_shape_alpha_min: int = 10
    background_shape_alpha_max: int = 28
    variation_token: str = ""
    source_credit_text: str = ""
    subject_focus_box: list[int] = field(default_factory=list)


@dataclass(slots=True)
class PosterRequest:
    title: str
    body: str
    assets: PosterAssetSet = field(default_factory=PosterAssetSet)
    layout: PosterLayout = field(default_factory=PosterLayout)
    style: PosterStyle = field(default_factory=PosterStyle)
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
