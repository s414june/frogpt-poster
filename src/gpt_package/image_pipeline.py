"""Image preprocessing and fallback-background generation."""

from __future__ import annotations

import hashlib
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .types import ImageSource, PosterDecision, PosterRequest


class ImagePipeline:
    """Builds poster background from user photo or generated fallback."""

    def _from_user_image(self, image_path: str, size: tuple[int, int]) -> Image.Image:
        image = Image.open(Path(image_path)).convert("RGBA")
        image = self.remove_background(image)
        image = self.crop_to_fill(image, size)
        return image.convert("RGB")

    def crop_to_fill(self, image: Image.Image, size: tuple[int, int]) -> Image.Image:
        return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))

    def remove_background(self, image: Image.Image) -> Image.Image:
        if image.mode != "RGBA":
            return image
        background = Image.new("RGBA", image.size, (247, 247, 247, 255))
        return Image.alpha_composite(background, image)

    def _generated_fallback(self, size: tuple[int, int], seed_text: str) -> Image.Image:
        width, height = size
        digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
        seed = int(digest[:8], 16)
        rng = random.Random(seed)

        top = self._parse_color(getattr(getattr(self, "_style", None), "primary_color", "#F6F1E8"))
        bottom = self._parse_color(getattr(getattr(self, "_style", None), "secondary_color", "#A8BFA8"))
        accent = self._parse_color(getattr(getattr(self, "_style", None), "accent_color", "#6D8A72"))
        background = Image.new("RGB", size)
        draw = ImageDraw.Draw(background)
        for y in range(height):
            ratio = y / max(1, height - 1)
            color = (
                int(top[0] * (1 - ratio) + bottom[0] * ratio),
                int(top[1] * (1 - ratio) + bottom[1] * ratio),
                int(top[2] * (1 - ratio) + bottom[2] * ratio),
            )
            draw.line([(0, y), (width, y)], fill=color)

        shape_count = int(getattr(getattr(self, "_style", None), "background_shape_count", 0))
        shape_count = max(0, min(6, shape_count))
        alpha_min = int(getattr(getattr(self, "_style", None), "background_shape_alpha_min", 10))
        alpha_max = int(getattr(getattr(self, "_style", None), "background_shape_alpha_max", 28))
        alpha_min = max(0, min(120, alpha_min))
        alpha_max = max(alpha_min, min(140, alpha_max))

        composited = background.convert("RGBA")
        if shape_count > 0:
            overlay = Image.new("RGBA", size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            for _ in range(shape_count):
                radius = rng.randint(int(min(size) * 0.10), int(min(size) * 0.28))
                cx = rng.randint(0, width)
                cy = rng.randint(0, height)
                color = (
                    self._clamp_color(accent[0] + rng.randint(-28, 32)),
                    self._clamp_color(accent[1] + rng.randint(-28, 32)),
                    self._clamp_color(accent[2] + rng.randint(-28, 32)),
                    rng.randint(alpha_min, alpha_max),
                )
                overlay_draw.ellipse(
                    [(cx - radius, cy - radius), (cx + radius, cy + radius)],
                    fill=color,
                )
            composited = Image.alpha_composite(composited, overlay)
        composited = composited.filter(ImageFilter.GaussianBlur(radius=0.6))

        subject_text = getattr(getattr(self, "_style", None), "subject", "")
        subject_blob = f"{subject_text} {seed_text}".lower()
        if "hamster" in subject_blob or "倉鼠" in subject_blob:
            self._draw_hamster(composited, accent, rng)
        return composited.convert("RGB")

    def build_background(self, request: PosterRequest, decision: PosterDecision) -> Image.Image:
        self._style = request.style
        size = (request.layout.width, request.layout.height)
        if decision.image_source == ImageSource.USER_IMAGE:
            return self._from_user_image(request.assets.user_image_paths[0], size)
        return self._generated_fallback(
            size,
            seed_text=(
                f"{request.title}\n{request.body}\n"
                f"{request.style.subject}\n{request.style.preset}\n"
                f"{request.style.primary_color}|{request.style.secondary_color}|{request.style.accent_color}\n"
                f"{request.style.variation_token}"
            ),
        )

    def _draw_hamster(self, image: Image.Image, accent: tuple[int, int, int], rng: random.Random) -> None:
        width, height = image.size
        draw = ImageDraw.Draw(image, "RGBA")
        center_x = int(width * (0.53 + rng.uniform(-0.03, 0.03)))
        center_y = int(height * (0.42 + rng.uniform(-0.03, 0.03)))
        body_r = int(min(width, height) * 0.18)
        ear_r = int(body_r * 0.42)
        fur = (227, 196, 150, 255)
        fur_dark = (198, 160, 112, 255)
        belly = (247, 236, 219, 255)
        ear_inner = (238, 193, 184, 255)
        shadow = (accent[0], accent[1], accent[2], 60)

        draw.ellipse(
            [(center_x - body_r - 12, center_y + body_r - 8), (center_x + body_r + 18, center_y + body_r + 48)],
            fill=shadow,
        )
        draw.ellipse([(center_x - body_r, center_y - body_r), (center_x + body_r, center_y + body_r)], fill=fur)
        draw.ellipse(
            [(center_x - int(body_r * 0.78), center_y - int(body_r * 0.18)), (center_x + int(body_r * 0.78), center_y + int(body_r * 0.92))],
            fill=belly,
        )
        draw.ellipse(
            [(center_x - body_r + 16, center_y - body_r - ear_r + 10), (center_x - body_r + 16 + ear_r * 2, center_y - body_r + ear_r + 10)],
            fill=fur,
        )
        draw.ellipse(
            [(center_x + body_r - ear_r * 2 - 16, center_y - body_r - ear_r + 10), (center_x + body_r - 16, center_y - body_r + ear_r + 10)],
            fill=fur,
        )
        draw.ellipse(
            [(center_x - body_r + 28, center_y - body_r - ear_r + 22), (center_x - body_r + 28 + int(ear_r * 1.4), center_y - body_r + int(ear_r * 1.4) + 22)],
            fill=ear_inner,
        )
        draw.ellipse(
            [(center_x + body_r - int(ear_r * 1.4) - 28, center_y - body_r - ear_r + 22), (center_x + body_r - 28, center_y - body_r + int(ear_r * 1.4) + 22)],
            fill=ear_inner,
        )
        eye_r = max(4, body_r // 16)
        draw.ellipse([(center_x - body_r // 3 - eye_r, center_y - eye_r), (center_x - body_r // 3 + eye_r, center_y + eye_r)], fill=(40, 40, 40, 255))
        draw.ellipse([(center_x + body_r // 3 - eye_r, center_y - eye_r), (center_x + body_r // 3 + eye_r, center_y + eye_r)], fill=(40, 40, 40, 255))
        nose_w = max(8, body_r // 8)
        draw.polygon(
            [(center_x, center_y + body_r // 8), (center_x - nose_w, center_y + body_r // 6 + nose_w), (center_x + nose_w, center_y + body_r // 6 + nose_w)],
            fill=(203, 114, 115, 255),
        )
        draw.arc(
            [(center_x - body_r // 4, center_y + body_r // 6), (center_x, center_y + body_r // 2)],
            start=220,
            end=320,
            fill=fur_dark,
            width=3,
        )
        draw.arc(
            [(center_x, center_y + body_r // 6), (center_x + body_r // 4, center_y + body_r // 2)],
            start=220,
            end=320,
            fill=fur_dark,
            width=3,
        )

    def _parse_color(self, raw: str) -> tuple[int, int, int]:
        text = (raw or "").strip().lstrip("#")
        if len(text) == 6:
            try:
                return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
            except ValueError:
                pass
        return (246, 241, 232)

    def _clamp_color(self, value: int) -> int:
        return max(0, min(255, value))
