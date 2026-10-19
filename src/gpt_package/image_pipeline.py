"""Image preprocessing and fallback-background generation."""

from __future__ import annotations

import colorsys
import hashlib
import math
import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from .types import ImageSource, PosterDecision, PosterRequest


class ImagePipeline:
    """Builds poster background from user photo or generated fallback."""

    def __init__(self) -> None:
        self._min_geometry_bg_distance = 42.0
        self._last_effects = {
            "subject_mask_applied": False,
            "subject_mask_style": None,
            "decorative_geometry_applied": False,
            "decorative_geometry_strategy": None,
            "decorative_geometry_shapes": 0,
        }

    def get_last_effects(self) -> dict:
        return dict(self._last_effects)

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

        top = self._normalize_moderate_tone(
            self._parse_color(getattr(getattr(self, "_style", None), "primary_color", "#F6F1E8"))
        )
        bottom = self._normalize_moderate_tone(
            self._parse_color(getattr(getattr(self, "_style", None), "secondary_color", "#A8BFA8"))
        )
        tone = self._tone_hint(getattr(getattr(self, "_style", None), "background_color_hint", ""))
        if tone == "light":
            top = self._enforce_luma_floor(top, 250)
            bottom = self._enforce_luma_floor(bottom, 150)
        elif tone == "dark":
            top = self._enforce_luma_ceiling(top, 112)
            bottom = self._enforce_luma_ceiling(bottom, 126)
        if not self._is_monochrome_intent(
            hint_text=str(getattr(getattr(self, "_style", None), "background_color_hint", "")),
            colors=[top, bottom],
        ):
            top = self._boost_saturation(top, lift=0.10, min_sat=0.32)
            bottom = self._boost_saturation(bottom, lift=0.10, min_sat=0.30)
        accent = self._parse_color(getattr(getattr(self, "_style", None), "accent_color", "#6D8A72"))
        mode = str(getattr(getattr(self, "_style", None), "background_mode", "auto")).strip().lower()
        if mode == "solid":
            background = Image.new("RGB", size, top)
        else:
            # Default policy: auto prefers solid background unless user/GPT explicitly chooses gradient.
            use_gradient = mode == "gradient"
            if use_gradient:
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
            else:
                background = Image.new("RGB", size, top)

        shape_count = int(getattr(getattr(self, "_style", None), "background_shape_count", 0))
        shape_count = max(0, min(6, shape_count))
        if shape_count > 0:
            draw = ImageDraw.Draw(background)
            for _ in range(shape_count):
                radius = rng.randint(int(min(size) * 0.10), int(min(size) * 0.24))
                cx = rng.randint(0, width)
                cy = rng.randint(0, height)
                color = (
                    self._clamp_color(accent[0] + rng.randint(-24, 24)),
                    self._clamp_color(accent[1] + rng.randint(-24, 24)),
                    self._clamp_color(accent[2] + rng.randint(-24, 24)),
                )
                draw.ellipse([(cx - radius, cy - radius), (cx + radius, cy + radius)], fill=color)
        return background

    def build_background(self, request: PosterRequest, decision: PosterDecision) -> Image.Image:
        self._style = request.style
        self._last_effects = {
            "subject_mask_applied": False,
            "subject_mask_style": None,
            "decorative_geometry_applied": False,
            "decorative_geometry_strategy": None,
            "decorative_geometry_shapes": 0,
        }
        size = (request.layout.width, request.layout.height)
        if decision.image_source == ImageSource.USER_IMAGE:
            background = self._from_user_image(request.assets.user_image_paths[0], size)
        else:
            background = self._generated_fallback(
                size,
                seed_text=(
                    f"{request.title}\n{request.body}\n"
                    f"{request.style.subject}\n"
                    f"{request.style.primary_color}|{request.style.secondary_color}|{request.style.accent_color}\n"
                    f"{request.style.variation_token}"
                ),
            )
        background = self._apply_background_hint_variation(background, request, decision)

        planned_box = None
        if request.assets.subject_image_paths:
            planned_box = self._planned_subject_box(background.size, request.assets.subject_image_paths[0])
        request.style.subject_focus_box = list(planned_box) if planned_box else []

        if self._should_add_geometry(request, decision):
            geo_result = self._add_decorative_geometry(
                background=background,
                subject_box=planned_box,
                subject_path=request.assets.subject_image_paths[0] if request.assets.subject_image_paths else None,
                request=request,
            )
            if geo_result is not None:
                strategy, shape_count = geo_result
                self._last_effects["decorative_geometry_applied"] = True
                self._last_effects["decorative_geometry_strategy"] = strategy
                self._last_effects["decorative_geometry_shapes"] = shape_count

        if request.assets.subject_image_paths:
            mask_style = self._overlay_subject_with_single_mask(background, request.assets.subject_image_paths[0], request)
            self._last_effects["subject_mask_applied"] = mask_style is not None
            self._last_effects["subject_mask_style"] = mask_style

        return background

    def _apply_background_hint_variation(
        self,
        background: Image.Image,
        request: PosterRequest,
        decision: PosterDecision,
    ) -> Image.Image:
        hint_text = str(getattr(request.style, "background_color_hint", "")).strip()
        if not hint_text:
            return background

        parsed = self._parse_hint_hsv(hint_text)
        if parsed is None:
            return background
        hue, sat, val = parsed

        tone = self._tone_hint(hint_text)
        if tone == "light":
            sat = max(0.20, min(0.58, sat * 0.84))
            val = max(0.72, min(0.90, val + 0.06))
            top_val = min(0.94, val + 0.06)
            bottom_val = max(0.62, val - 0.08)
        elif tone == "dark":
            sat = max(0.24, min(0.64, sat * 1.06))
            val = max(0.36, min(0.68, val - 0.08))
            top_val = min(0.74, val + 0.04)
            bottom_val = max(0.28, val - 0.10)
        else:
            sat = max(0.22, min(0.62, sat))
            val = max(0.50, min(0.82, val))
            top_val = min(0.88, val + 0.05)
            bottom_val = max(0.42, val - 0.07)

        hash_key = f"{hint_text}|{request.title}|{request.body}"
        digest = hashlib.sha256(hash_key.encode("utf-8")).hexdigest()
        sign = -1.0 if (int(digest[:2], 16) % 2 == 0) else 1.0
        hue_shift = 0.018 * sign
        top_h = (hue - hue_shift) % 1.0
        bottom_h = (hue + hue_shift) % 1.0

        mode = str(getattr(request.style, "background_mode", "auto")).strip().lower()
        use_gradient_tint = mode == "gradient"

        top_rgb = self._hsv_to_rgb(top_h, sat, top_val)
        if use_gradient_tint:
            bottom_rgb = self._hsv_to_rgb(bottom_h, sat, bottom_val)
        else:
            # Keep solid/auto visually non-gradient: apply uniform tint.
            bottom_rgb = top_rgb
        overlay = self._vertical_gradient(background.size, top_rgb, bottom_rgb)

        alpha = 0.24
        if decision.image_source == ImageSource.USER_IMAGE:
            alpha = 0.16
        if mode == "solid":
            alpha += 0.04
        if mode == "gradient":
            alpha += 0.02
        alpha = max(0.08, min(0.26, alpha))

        base = background.convert("RGB")
        return Image.blend(base, overlay, alpha=alpha)

    def _vertical_gradient(
        self,
        size: tuple[int, int],
        top: tuple[int, int, int],
        bottom: tuple[int, int, int],
    ) -> Image.Image:
        width, height = size
        out = Image.new("RGB", size)
        draw = ImageDraw.Draw(out)
        for y in range(height):
            t = y / max(1, height - 1)
            color = (
                int(top[0] * (1.0 - t) + bottom[0] * t),
                int(top[1] * (1.0 - t) + bottom[1] * t),
                int(top[2] * (1.0 - t) + bottom[2] * t),
            )
            draw.line([(0, y), (width, y)], fill=color)
        return out

    def _parse_hint_hsv(self, hint_text: str) -> tuple[float, float, float] | None:
        raw = (hint_text or "").strip().lower()
        if not raw:
            return None
        if self._contains_mono_keyword(raw):
            return 0.0, 0.02, 0.72
        hue_map = {
            "red": 0.00, "紅": 0.00, "红": 0.00,
            "orange": 0.08, "橙": 0.08,
            "yellow": 0.15, "黃": 0.15, "黄": 0.15,
            "green": 0.33, "綠": 0.33, "绿": 0.33,
            "teal": 0.46, "cyan": 0.50, "青": 0.50,
            "blue": 0.62, "藍": 0.62, "蓝": 0.62,
            "purple": 0.77, "violet": 0.80, "紫": 0.77,
            "pink": 0.92, "粉": 0.92,
            "brown": 0.08, "咖啡": 0.08, "棕": 0.08,
            "gray": 0.0, "grey": 0.0, "灰": 0.0,
        }
        hue = None
        for key, value in hue_map.items():
            if key in raw:
                hue = value
                break
        if hue is None:
            return None

        sat = 0.62
        val = 0.72
        if any(k in raw for k in ("pastel", "柔和", "低彩", "淡")):
            sat = 0.42
            val = 0.80
        if any(k in raw for k in ("vivid", "高彩", "鮮", "亮彩")):
            sat = 0.74
            val = 0.74
        return hue, sat, val

    def _boost_saturation(self, rgb: tuple[int, int, int], lift: float, min_sat: float) -> tuple[int, int, int]:
        h, s, v = colorsys.rgb_to_hsv(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)
        boosted_s = max(min_sat, s + lift)
        boosted_s = max(0.0, min(0.84, boosted_s))
        r, g, b = colorsys.hsv_to_rgb(h, boosted_s, v)
        return (
            self._clamp_color(int(r * 255)),
            self._clamp_color(int(g * 255)),
            self._clamp_color(int(b * 255)),
        )

    def _contains_mono_keyword(self, text: str) -> bool:
        raw = (text or "").strip().lower()
        mono_keywords = ("black", "white", "gray", "grey", "黑", "白", "灰")
        return any(k in raw for k in mono_keywords)

    def _is_monochrome_intent(self, hint_text: str, colors: list[tuple[int, int, int]]) -> bool:
        if self._contains_mono_keyword(hint_text):
            return True
        if not colors:
            return False
        sats: list[float] = []
        for color in colors:
            _h, s, _v = colorsys.rgb_to_hsv(color[0] / 255.0, color[1] / 255.0, color[2] / 255.0)
            sats.append(s)
        return max(sats) <= 0.10

    def _is_light_design(self, top: tuple[int, int, int], bottom: tuple[int, int, int], tone: str) -> bool:
        if tone == "light":
            return True
        avg_luma = (self._luma(top) + self._luma(bottom)) / 2.0
        return avg_luma >= 152.0

    def _hsv_to_rgb(self, h: float, s: float, v: float) -> tuple[int, int, int]:
        r, g, b = colorsys.hsv_to_rgb(h, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
        return (
            self._clamp_color(int(r * 255)),
            self._clamp_color(int(g * 255)),
            self._clamp_color(int(b * 255)),
        )

    def _planned_subject_box(self, bg_size: tuple[int, int], subject_path: str) -> tuple[int, int, int, int] | None:
        try:
            with Image.open(Path(subject_path)) as subject:
                subject_h = subject.height
                subject_w = subject.width
        except OSError:
            return None
        width, height = bg_size
        target_h = int(height * 0.46)
        if target_h <= 0:
            return None
        ratio = target_h / max(1, subject_h)
        target_w = max(1, int(subject_w * ratio))
        pad = max(8, int(min(width, height) * 0.012))
        card_w = target_w + pad * 2
        card_h = target_h + pad * 2
        x = (width - card_w) // 2
        y = int(height * 0.24)
        if y + card_h > height:
            y = max(0, height - card_h - int(height * 0.04))
        return (x, y, x + card_w, y + card_h)

    def _overlay_subject_with_single_mask(self, background: Image.Image, subject_path: str, request: PosterRequest) -> str | None:
        try:
            subject = Image.open(Path(subject_path)).convert("RGBA")
        except OSError:
            return None
        width, height = background.size
        target_h = int(height * 0.46)
        if target_h <= 0:
            return None
        ratio = target_h / max(1, subject.height)
        target_w = max(1, int(subject.width * ratio))
        subject = subject.resize((target_w, target_h), Image.Resampling.LANCZOS)

        # remove semi-transparency from source alpha
        src_alpha = subject.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
        subject.putalpha(src_alpha)

        pad = max(8, int(min(width, height) * 0.012))
        card_w = target_w + pad * 2
        card_h = target_h + pad * 2
        radius = max(12, int(min(card_w, card_h) * 0.08))
        layer = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
        layer.alpha_composite(subject, (pad, pad))

        mask_style = str(getattr(request.style, "subject_mask_mode", "rounded")).strip().lower()
        if mask_style not in ("rounded", "feather"):
            mask_style = "rounded"

        if mask_style == "feather":
            alpha = layer.getchannel("A").filter(ImageFilter.GaussianBlur(radius=max(2, pad // 2)))
            alpha = alpha.point(lambda a: 255 if a >= 128 else 0)
            layer.putalpha(alpha)
        else:
            rounded = Image.new("L", (card_w, card_h), 0)
            mdraw = ImageDraw.Draw(rounded)
            mdraw.rounded_rectangle([(0, 0), (card_w - 1, card_h - 1)], radius=radius, fill=255)
            alpha = ImageChops.multiply(layer.getchannel("A"), rounded).point(lambda a: 255 if a >= 128 else 0)
            layer.putalpha(alpha)

        x = (width - card_w) // 2
        y = int(height * 0.24)
        if y + card_h > height:
            y = max(0, height - card_h - int(height * 0.04))

        base = background.convert("RGBA")
        base.alpha_composite(layer, (x, y))

        draw = ImageDraw.Draw(base)
        border_px = int(getattr(request.style, "subject_border_px", 0))
        if border_px >= 8:
            draw.rounded_rectangle(
                [(x, y), (x + card_w - 1, y + card_h - 1)],
                radius=radius,
                outline=(255, 255, 255, 255),
                width=border_px,
            )

        background.paste(base.convert("RGB"))
        return mask_style

    def _should_add_geometry(self, request: PosterRequest, decision: PosterDecision) -> bool:
        if not bool(getattr(request.style, "geometry_enabled", True)):
            return False
        mode = str(getattr(request.style, "background_mode", "auto")).strip().lower()
        # auto now renders as solid by default, so it should still be eligible for geometry.
        if mode not in ("auto", "solid", "gradient"):
            return False
        if len(request.assets.subject_image_paths) != 1:
            return False
        if decision.image_source != ImageSource.AI_FALLBACK:
            return False
        return True

    def _add_decorative_geometry(
        self,
        background: Image.Image,
        subject_box: tuple[int, int, int, int] | None,
        subject_path: str | None,
        request: PosterRequest,
    ) -> tuple[str, int] | None:
        width, height = background.size
        seed = int(
            hashlib.sha256(
                (
                    f"{request.title}|{request.body}|geo|"
                    f"{getattr(request.style, 'variation_token', '')}"
                ).encode("utf-8")
            ).hexdigest()[:8],
            16,
        )
        rng = random.Random(seed)
        strategy = "subject_near" if (subject_box and rng.random() < 0.65) else "edge_near"
        span = int(width * 0.82)
        subject_color = self._extract_subject_color(subject_path) if subject_path else None
        if subject_color is None:
            subject_color = self._parse_color(request.style.accent_color)
        color_pool = self._prepare_geometry_color_pool(background, subject_color, request, rng)

        draw = ImageDraw.Draw(background)
        shape_count = 0
        if strategy == "subject_near" and subject_box:
            x1, y1, x2, y2 = subject_box
            anchors = [
                (x1 - int(span * 0.18), (y1 + y2) // 2),
                (x2 + int(span * 0.18), (y1 + y2) // 2),
                ((x1 + x2) // 2, y1 - int(span * 0.14)),
                ((x1 + x2) // 2, y2 + int(span * 0.14)),
            ]
            for ax, ay in anchors:
                px = ax + rng.randint(-span // 5, span // 5)
                py = ay + rng.randint(-span // 6, span // 6)
                px = max(0, min(width - 1, px))
                py = max(0, min(height - 1, py))
                size = int(min(width, height) * rng.uniform(0.12, 0.22))
                color = self._geometry_color(background, (px, py), color_pool, rng)
                self._draw_shape(draw, rng.choice(self._shape_types()), px, py, size, color)
                shape_count += 1
            return (strategy, shape_count)

        edges = ["left", "right", "top", "bottom"]
        rng.shuffle(edges)
        for edge in edges[:2]:
            for _ in range(2):
                px, py = self._edge_anchor(edge, width, height, span, rng)
                size = int(min(width, height) * rng.uniform(0.12, 0.22))
                color = self._geometry_color(background, (px, py), color_pool, rng)
                self._draw_shape(draw, rng.choice(self._shape_types()), px, py, size, color)
                shape_count += 1
        if shape_count == 0:
            return None
        return (strategy, shape_count)

    def _extract_subject_color(self, subject_path: str | None) -> tuple[int, int, int] | None:
        if not subject_path:
            return None
        try:
            with Image.open(Path(subject_path)) as src:
                img = src.convert("RGBA").resize((64, 64))
        except OSError:
            return None
        pixels = list(img.getdata())
        candidates = [p[:3] for p in pixels if p[3] >= 128]
        if not candidates:
            return None
        avg = (
            sum(p[0] for p in candidates) // len(candidates),
            sum(p[1] for p in candidates) // len(candidates),
            sum(p[2] for p in candidates) // len(candidates),
        )
        return avg

    def _geometry_color(
        self,
        background: Image.Image,
        center: tuple[int, int],
        color_pool: list[tuple[int, int, int]],
        rng: random.Random,
    ) -> tuple[int, int, int]:
        cx, cy = center
        cx = max(0, min(background.width - 1, cx))
        cy = max(0, min(background.height - 1, cy))
        bg = background.getpixel((cx, cy))
        if not color_pool:
            color_pool = [bg]
        color = color_pool[rng.randint(0, len(color_pool) - 1)]
        color = self._nudge_color(color, rng, 10)
        color = self._match_saturation_to_background(color, bg, rng)
        bg_luma = self._luma(bg)
        target_luma = max(72, min(196, bg_luma + rng.randint(-14, 14)))
        color = self._with_target_luma(color, target_luma)
        if self._rgb_distance(color, bg) < 28:
            color = (color[1], color[2], color[0])
            color = self._with_target_luma(color, target_luma)
        if self._rgb_distance(color, bg) < 28:
            color = (
                self._clamp_color(color[0] + 36),
                self._clamp_color(color[1] - 24),
                self._clamp_color(color[2] + 20),
            )
            color = self._match_saturation_to_background(color, bg, rng)
            color = self._with_target_luma(color, target_luma)
        color = self._normalize_moderate_tone(color)
        color = self._match_saturation_to_background(color, bg, rng)
        return self._ensure_min_color_distance(color, bg, rng, self._min_geometry_bg_distance)

    def _prepare_geometry_color_pool(
        self,
        background: Image.Image,
        subject_color: tuple[int, int, int],
        request: PosterRequest,
        rng: random.Random,
    ) -> list[tuple[int, int, int]]:
        bg_sample = background.getpixel((background.width // 2, background.height // 2))
        bh, bs, bv = colorsys.rgb_to_hsv(bg_sample[0] / 255.0, bg_sample[1] / 255.0, bg_sample[2] / 255.0)
        sh, ss, _sv = colorsys.rgb_to_hsv(subject_color[0] / 255.0, subject_color[1] / 255.0, subject_color[2] / 255.0)
        wants_contrast = self._wants_contrast_geometry(request)

        hues: list[float] = [bh]
        if self._hue_delta(bh, sh) <= 0.14:
            hues.append(sh)
        else:
            hues.append((bh + (0.06 if rng.random() < 0.5 else -0.06)) % 1.0)

        if wants_contrast:
            hues.append((bh + 0.5) % 1.0)
        else:
            hues.append((bh + (0.10 if rng.random() < 0.5 else -0.10)) % 1.0)

        uniq_hues: list[float] = []
        for h in hues:
            if all(self._hue_delta(h, seen) > 0.045 for seen in uniq_hues):
                uniq_hues.append(h)
            if len(uniq_hues) >= 3:
                break
        if not uniq_hues:
            uniq_hues = [bh]

        pool: list[tuple[int, int, int]] = []
        base_sat = max(0.18, min(0.70, bs))
        for h in uniq_hues[:3]:
            if wants_contrast and self._hue_delta(h, (bh + 0.5) % 1.0) < 0.08:
                sat = max(0.32, min(0.78, base_sat + 0.14))
            else:
                sat = max(0.16, min(0.74, (base_sat * 0.72) + (ss * 0.28) + rng.uniform(-0.04, 0.04)))
            val = max(0.34, min(0.82, bv + rng.uniform(-0.06, 0.06)))
            r, g, b = colorsys.hsv_to_rgb(h, sat, val)
            pool.append((self._clamp_color(int(r * 255)), self._clamp_color(int(g * 255)), self._clamp_color(int(b * 255))))
        return pool[:3]

    def _shape_types(self) -> list[str]:
        return [
            "circle",
            "rounded_rect",
            "trapezoid",
            "diamond",
            "triangle",
            "spark_star",
            "flower",
        ]

    def _edge_anchor(
        self, edge: str, width: int, height: int, span: int, rng: random.Random
    ) -> tuple[int, int]:
        if edge == "left":
            return (rng.randint(0, max(1, span)), rng.randint(int(height * 0.10), int(height * 0.90)))
        if edge == "right":
            return (rng.randint(max(0, width - span), width - 1), rng.randint(int(height * 0.10), int(height * 0.90)))
        if edge == "top":
            return (rng.randint(int(width * 0.10), int(width * 0.90)), rng.randint(0, max(1, int(span * 0.65))))
        return (rng.randint(int(width * 0.10), int(width * 0.90)), rng.randint(max(0, height - int(span * 0.65)), height - 1))

    def _draw_shape(
        self,
        draw: ImageDraw.ImageDraw,
        shape: str,
        cx: int,
        cy: int,
        size: int,
        color: tuple[int, int, int],
    ) -> None:
        if shape == "circle":
            draw.ellipse([(cx - size, cy - size), (cx + size, cy + size)], fill=color)
            return
        if shape == "rounded_rect":
            draw.rounded_rectangle(
                [(cx - int(size * 1.2), cy - int(size * 0.8)), (cx + int(size * 1.2), cy + int(size * 0.8))],
                radius=max(8, size // 4),
                fill=color,
            )
            return
        if shape == "trapezoid":
            points = [
                (cx - int(size * 1.1), cy + size),
                (cx + int(size * 1.1), cy + size),
                (cx + int(size * 0.7), cy - size),
                (cx - int(size * 0.7), cy - size),
            ]
            draw.polygon(points, fill=color)
            return
        if shape == "diamond":
            points = [(cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy)]
            draw.polygon(points, fill=color)
            return
        if shape == "triangle":
            points = [(cx, cy - size), (cx + size, cy + size), (cx - size, cy + size)]
            draw.polygon(points, fill=color)
            return
        if shape == "spark_star":
            points: list[tuple[int, int]] = []
            for i in range(8):
                angle = math.radians(i * 45)
                r = size * (1.45 if i % 2 == 0 else 0.46)
                px = cx + int(math.cos(angle) * r)
                py = cy + int(math.sin(angle) * r)
                points.append((px, py))
            draw.polygon(points, fill=color)
            return
        if shape == "flower":
            petal = int(size * 0.62)
            for angle in range(0, 360, 45):
                rad = math.radians(angle)
                px = cx + int(math.cos(rad) * petal)
                py = cy + int(math.sin(rad) * petal)
                draw.ellipse(
                    [(px - petal // 2, py - petal // 2), (px + petal // 2, py + petal // 2)],
                    fill=color,
                )
            draw.ellipse([(cx - size // 2, cy - size // 2), (cx + size // 2, cy + size // 2)], fill=self._lighten(color, 32))

    def _rgb_distance(self, a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)

    def _luma(self, rgb: tuple[int, int, int]) -> float:
        return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722

    def _lighten(self, rgb: tuple[int, int, int], delta: int) -> tuple[int, int, int]:
        return (
            self._clamp_color(rgb[0] + delta),
            self._clamp_color(rgb[1] + delta),
            self._clamp_color(rgb[2] + delta),
        )

    def _with_target_luma(self, rgb: tuple[int, int, int], target_luma: float) -> tuple[int, int, int]:
        current = max(1.0, self._luma(rgb))
        scale = target_luma / current
        return (
            self._clamp_color(int(rgb[0] * scale)),
            self._clamp_color(int(rgb[1] * scale)),
            self._clamp_color(int(rgb[2] * scale)),
        )

    def _normalize_moderate_tone(self, rgb: tuple[int, int, int]) -> tuple[int, int, int]:
        l = self._luma(rgb)
        if l < 72:
            return self._with_target_luma(rgb, 86)
        if l > 196:
            return self._with_target_luma(rgb, 182)
        return rgb

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

    def _match_saturation_to_background(
        self,
        color: tuple[int, int, int],
        background: tuple[int, int, int],
        rng: random.Random,
    ) -> tuple[int, int, int]:
        ch, cs, cv = colorsys.rgb_to_hsv(color[0] / 255.0, color[1] / 255.0, color[2] / 255.0)
        _bh, bs, _bv = colorsys.rgb_to_hsv(background[0] / 255.0, background[1] / 255.0, background[2] / 255.0)
        target_s = max(0.18, min(0.72, bs + rng.uniform(-0.06, 0.06)))
        mixed_s = (cs * 0.30) + (target_s * 0.70)
        r, g, b = colorsys.hsv_to_rgb(ch, max(0.0, min(1.0, mixed_s)), cv)
        return (
            self._clamp_color(int(r * 255)),
            self._clamp_color(int(g * 255)),
            self._clamp_color(int(b * 255)),
        )

    def _nudge_color(self, rgb: tuple[int, int, int], rng: random.Random, delta: int) -> tuple[int, int, int]:
        return (
            self._clamp_color(rgb[0] + rng.randint(-delta, delta)),
            self._clamp_color(rgb[1] + rng.randint(-delta, delta)),
            self._clamp_color(rgb[2] + rng.randint(-delta, delta)),
        )

    def _hue_delta(self, a: float, b: float) -> float:
        d = abs(a - b)
        return min(d, 1.0 - d)

    def _ensure_min_color_distance(
        self,
        color: tuple[int, int, int],
        bg: tuple[int, int, int],
        rng: random.Random,
        minimum: float,
    ) -> tuple[int, int, int]:
        if self._rgb_distance(color, bg) >= minimum:
            return color
        ch, cs, cv = colorsys.rgb_to_hsv(color[0] / 255.0, color[1] / 255.0, color[2] / 255.0)
        bh, bs, bv = colorsys.rgb_to_hsv(bg[0] / 255.0, bg[1] / 255.0, bg[2] / 255.0)
        attempts = [
            ((ch + 0.08) % 1.0, max(cs, min(0.80, bs + 0.10)), min(0.88, cv + 0.08)),
            ((ch - 0.08) % 1.0, max(cs, min(0.80, bs + 0.10)), max(0.24, cv - 0.08)),
            ((bh + 0.12) % 1.0, max(0.24, min(0.82, bs + 0.12)), min(0.88, bv + 0.10)),
            ((bh - 0.12) % 1.0, max(0.24, min(0.82, bs + 0.12)), max(0.24, bv - 0.10)),
        ]
        best = color
        best_distance = self._rgb_distance(color, bg)
        for h, s, v in attempts:
            rr, gg, bb = colorsys.hsv_to_rgb(h, s, v)
            candidate = (
                self._clamp_color(int(rr * 255)),
                self._clamp_color(int(gg * 255)),
                self._clamp_color(int(bb * 255)),
            )
            candidate = self._nudge_color(candidate, rng, 4)
            d = self._rgb_distance(candidate, bg)
            if d > best_distance:
                best = candidate
                best_distance = d
            if d >= minimum:
                return candidate
        return best

    def _wants_contrast_geometry(self, request: PosterRequest) -> bool:
        text = (
            f"{request.title} {request.body} "
            f"{getattr(request.style, 'background_color_hint', '')} "
            f"{getattr(request.style, 'subject', '')}"
        ).lower()
        keywords = ("跳色", "撞色", "對比色", "高對比", "contrast", "complementary")
        return any(k in text for k in keywords)

    def _tone_hint(self, raw: str) -> str:
        text = (raw or "").strip().lower()
        if any(k in text for k in ("light", "淺", "亮", "pastel", "柔和", "淡")):
            return "light"
        if any(k in text for k in ("dark", "深", "暗")):
            return "dark"
        return ""

    def _enforce_luma_floor(self, rgb: tuple[int, int, int], floor: float) -> tuple[int, int, int]:
        l = self._luma(rgb)
        if l >= floor:
            return rgb
        return self._with_target_luma(rgb, floor)

    def _enforce_luma_ceiling(self, rgb: tuple[int, int, int], ceiling: float) -> tuple[int, int, int]:
        l = self._luma(rgb)
        if l <= ceiling:
            return rgb
        return self._with_target_luma(rgb, ceiling)
