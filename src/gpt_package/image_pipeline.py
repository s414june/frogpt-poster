"""Image preprocessing and fallback-background generation."""

from __future__ import annotations

import hashlib
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .types import ImageSource, PosterDecision, PosterRequest


class ImagePipeline:
    """Builds poster background from user photo or generated fallback."""

    def build_background(self, request: PosterRequest, decision: PosterDecision) -> Image.Image:
        size = (request.layout.width, request.layout.height)
        if decision.image_source == ImageSource.USER_IMAGE:
            return self._from_user_image(request.assets.user_image_paths[0], size)
        return self._generated_fallback(size, seed_text=f"{request.title}\n{request.body}")

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

        top = (rng.randint(18, 42), rng.randint(36, 72), rng.randint(84, 130))
        bottom = (rng.randint(6, 24), rng.randint(10, 30), rng.randint(36, 66))
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

        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        for _ in range(6):
            radius = rng.randint(int(min(size) * 0.10), int(min(size) * 0.28))
            cx = rng.randint(0, width)
            cy = rng.randint(0, height)
            color = (
                rng.randint(120, 230),
                rng.randint(120, 230),
                rng.randint(120, 230),
                rng.randint(26, 64),
            )
            overlay_draw.ellipse(
                [(cx - radius, cy - radius), (cx + radius, cy + radius)],
                fill=color,
            )
        composited = Image.alpha_composite(background.convert("RGBA"), overlay)
        return composited.filter(ImageFilter.GaussianBlur(radius=1.0)).convert("RGB")
