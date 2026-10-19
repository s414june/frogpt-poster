"""Poster generator entrypoint."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .image_pipeline import ImagePipeline
from .policy import PosterPolicy
from .types import PosterRequest, PosterResult
from .typography import TypographyEngine
from .validation import validate_request


class PosterGenerator:
    """High-level poster generation orchestrator."""

    def __init__(
        self,
        policy: PosterPolicy | None = None,
        image_pipeline: ImagePipeline | None = None,
        typography: TypographyEngine | None = None,
        output_dir: str | None = None,
    ) -> None:
        self.policy = policy or PosterPolicy()
        self.image_pipeline = image_pipeline or ImagePipeline()
        self.typography = typography or TypographyEngine()
        self.output_dir = Path(output_dir or self._default_output_dir())

    def generate(self, request: PosterRequest) -> PosterResult:
        validate_request(request)
        decision = self.policy.decide(request)
        background = self.image_pipeline.build_background(request, decision)
        typography_info = self.typography.apply(
            background,
            title=request.title,
            body=request.body,
            font_paths=request.assets.open_source_font_paths,
            style=request.style,
        )
        image_effects = self.image_pipeline.get_last_effects()
        output_path = self._save_image(background)

        selected_font = typography_info.get("selected_font")
        font_note = selected_font if selected_font else "default built-in font"
        return PosterResult(
            output_path=str(output_path),
            decision=decision,
            notes=[
                "Render completed.",
                "Validation passed.",
                f"Poster rendered at: {output_path}",
                f"Typography font: {font_note}",
                f"Subject mask applied: {image_effects.get('subject_mask_applied', False)}",
                f"Subject mask style: {image_effects.get('subject_mask_style')}",
                f"Decorative geometry applied: {image_effects.get('decorative_geometry_applied', False)}",
                f"Decorative geometry strategy: {image_effects.get('decorative_geometry_strategy')}",
                f"Decorative geometry shapes: {image_effects.get('decorative_geometry_shapes', 0)}",
            ],
        )

    def _default_output_dir(self) -> str:
        env_dir = os.getenv("POSTER_OUTPUT_DIR")
        if env_dir:
            return env_dir
        if os.getenv("VERCEL"):
            return "/tmp/posters"
        return str(Path("outputs") / "posters")

    def _save_image(self, image) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        filename = f"poster-{stamp}-{uuid4().hex[:8]}.png"
        path = self.output_dir / filename
        image.save(path, format="PNG", optimize=True)
        return path.resolve()
