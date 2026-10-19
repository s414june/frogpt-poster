"""Typography and text layout for poster rendering."""

from __future__ import annotations

import hashlib

from PIL import Image, ImageDraw, ImageFont


class TypographyEngine:
    """Applies title/body text on poster image."""

    def select_font(self, font_paths: list[str], sample_text: str = "") -> str | None:
        return self.select_font_by_role(font_paths, sample_text=sample_text, role="body")

    def select_font_by_role(self, font_paths: list[str], sample_text: str, role: str) -> str | None:
        if not font_paths:
            return None
        ranked = sorted(font_paths, key=lambda path: self._font_priority(path, sample_text, role=role))
        return ranked[0]

    def apply(self, image: Image.Image, title: str, body: str, font_paths: list[str], style=None) -> dict:
        role_mode = str(getattr(style, "image_role_mode", "auto")).strip().lower() if style else "auto"
        if role_mode == "both":
            return self._apply_focus_aware_two_size(image, title, body, font_paths, style=style)

        width, height = image.size
        margin = max(36, int(width * 0.06))
        sample_text = f"{title}\n{body}"
        variant_token = str(getattr(style, "variation_token", ""))
        variant_index = self._variant_index(variant_token, modulo=17)
        title_jitter = self._variant_jitter(variant_token, salt="title", max_abs=0.028)
        body_jitter = self._variant_jitter(variant_token, salt="body", max_abs=0.032)
        body_font_path = self.select_font_by_role(font_paths, sample_text=sample_text, role="body")
        heading_font_path = self._find_heading_font_from_body_family(
            font_paths=font_paths,
            body_font_path=body_font_path,
            sample_text=sample_text,
        )
        title_font = self._load_font(
            [heading_font_path] if heading_font_path else font_paths,
            size=max(48, int(width * 0.078)),
            sample_text=sample_text,
            role="heading",
        )
        subtitle_font = self._load_font(
            [heading_font_path] if heading_font_path else font_paths,
            size=max(32, int(width * 0.046)),
            sample_text=sample_text,
            role="heading",
        )
        body_font = self._load_font(
            [body_font_path] if body_font_path else font_paths,
            size=max(24, int(width * 0.032)),
            sample_text=sample_text,
            role="body",
        )

        text_width = width - margin * 2
        draw = ImageDraw.Draw(image, "RGBA")
        title_lines = self._wrap_text(draw, title.strip(), title_font, text_width)
        body_lines = self._wrap_text(draw, body.strip(), body_font, text_width)

        title_max_lines = int(getattr(style, "title_max_lines", 2)) if style else 2
        body_max_lines = int(getattr(style, "body_max_lines", 4)) if style else 4
        title_max_lines = max(1, min(4, title_max_lines))
        body_max_lines = max(2, min(8, body_max_lines))

        title_region = (margin, max(8, int(height * 0.05)), width - margin, int(height * 0.35))
        body_region = (margin, int(height * 0.70), width - margin, int(height * 0.97))
        title_color = self._pick_text_color(image, title_region)
        body_color = self._pick_text_color(image, body_region)

        title_y_candidates = [0.10, 0.12, 0.14, 0.16]
        body_y_candidates = [0.70, 0.72, 0.74, 0.76]
        title_base = title_y_candidates[variant_index % len(title_y_candidates)]
        body_base = body_y_candidates[variant_index % len(body_y_candidates)]
        title_ratio = max(0.06, min(0.22, title_base + title_jitter))
        body_ratio = max(0.66, min(0.84, body_base + body_jitter))
        y = max(24, int(height * title_ratio))
        for line in title_lines[:title_max_lines]:
            box = draw.textbbox((0, 0), line, font=title_font)
            line_w = box[2] - box[0]
            x = max(margin, (width - line_w) // 2)
            draw.text((x, y), line, fill=title_color, font=title_font)
            y += int(title_font.size * 1.22)

        y = int(height * body_ratio)
        subtitle_line = body_lines[0] if body_lines else ""
        rest_lines = body_lines[1:] if len(body_lines) > 1 else []
        if subtitle_line:
            box = draw.textbbox((0, 0), subtitle_line, font=subtitle_font)
            line_w = box[2] - box[0]
            x = max(margin, (width - line_w) // 2)
            draw.text((x, y), subtitle_line, fill=body_color, font=subtitle_font)
            y += int(subtitle_font.size * 1.30)
        for line in rest_lines[: max(1, body_max_lines - 1)]:
            box = draw.textbbox((0, 0), line, font=body_font)
            line_w = box[2] - box[0]
            x = max(margin, (width - line_w) // 2)
            draw.text((x, y), line, fill=body_color, font=body_font)
            y += int(body_font.size * 1.32)

        credit_text = str(getattr(style, "source_credit_text", "")).strip() if style else ""
        if credit_text:
            self.apply_source_credit_overlay(image, credit_text, font_paths)

        return {
            "selected_font": body_font_path or self.select_font(font_paths, sample_text=sample_text),
            "title_font": heading_font_path or body_font_path,
            "body_font": body_font_path,
            "layout_mode": "default",
            "layout_variant": variant_index,
        }

    def _apply_focus_aware_two_size(self, image: Image.Image, title: str, body: str, font_paths: list[str], style=None) -> dict:
        width, height = image.size
        margin = max(36, int(width * 0.06))
        sample_text = f"{title}\n{body}"

        body_font_path = self.select_font_by_role(font_paths, sample_text=sample_text, role="body")
        heading_font_path = self._find_heading_font_from_body_family(
            font_paths=font_paths,
            body_font_path=body_font_path,
            sample_text=sample_text,
        )

        hero_font = self._load_font(
            [heading_font_path] if heading_font_path else font_paths,
            size=max(48, int(width * 0.072)),
            sample_text=sample_text,
            role="heading",
        )
        minor_font = self._load_font(
            [body_font_path] if body_font_path else font_paths,
            size=max(24, int(width * 0.034)),
            sample_text=sample_text,
            role="body",
        )

        draw = ImageDraw.Draw(image, "RGBA")
        text_width = width - margin * 2
        raw_title_lines = self._wrap_text(draw, title.strip(), minor_font, text_width)
        raw_body_lines = self._wrap_text(draw, body.strip(), minor_font, text_width)
        if raw_body_lines and raw_body_lines[0].strip():
            hero_text = raw_body_lines[0].strip()
            hero_lines = self._wrap_text(draw, hero_text, hero_font, text_width)
            minor_lines = [line for line in (raw_title_lines + raw_body_lines[1:]) if line.strip()]
        else:
            hero_text = title.strip()
            hero_lines = self._wrap_text(draw, hero_text, hero_font, text_width)
            minor_lines = [line for line in raw_body_lines if line.strip()]

        if not hero_lines:
            hero_lines = [title.strip() or body.strip() or ""]
        if not minor_lines:
            minor_lines = [line for line in raw_title_lines if line.strip()]

        hero_height = self._lines_height(hero_font.size, len(hero_lines), 1.20)
        minor_height = self._lines_height(minor_font.size, len(minor_lines), 1.30)
        focus_box = self._estimate_focus_box(image)
        variant_token = str(getattr(style, "variation_token", ""))
        variant_index = self._variant_index(variant_token, modulo=29)
        hero_shift = self._variant_jitter(variant_token, salt="hero", max_abs=0.05)
        minor_shift = self._variant_jitter(variant_token, salt="minor", max_abs=0.05)
        hero_region, minor_region = self._pick_two_block_regions(
            image=image,
            margin=margin,
            hero_height=hero_height,
            minor_height=minor_height,
            focus_box=focus_box,
            variant_index=variant_index,
            hero_shift=hero_shift,
            minor_shift=minor_shift,
        )

        hero_color = self._pick_text_color(image, hero_region)
        minor_color = self._pick_text_color(image, minor_region)
        hero_start_y = hero_region[1]
        for line in hero_lines:
            box = draw.textbbox((0, 0), line, font=hero_font)
            line_w = box[2] - box[0]
            x = max(margin, (width - line_w) // 2)
            draw.text((x, hero_start_y), line, fill=hero_color, font=hero_font)
            hero_start_y += int(hero_font.size * 1.20)

        minor_start_y = minor_region[1]
        for line in minor_lines:
            box = draw.textbbox((0, 0), line, font=minor_font)
            line_w = box[2] - box[0]
            x = max(margin, (width - line_w) // 2)
            draw.text((x, minor_start_y), line, fill=minor_color, font=minor_font)
            minor_start_y += int(minor_font.size * 1.30)

        credit_text = str(getattr(style, "source_credit_text", "")).strip() if style else ""
        if credit_text:
            self.apply_source_credit_overlay(image, credit_text, font_paths)

        return {
            "selected_font": body_font_path or self.select_font(font_paths, sample_text=sample_text),
            "title_font": heading_font_path or body_font_path,
            "body_font": body_font_path,
            "layout_mode": "both_focus_aware",
            "layout_variant": variant_index,
            "hero_font_size": hero_font.size,
            "minor_font_size": minor_font.size,
            "focus_box": focus_box,
            "hero_region": hero_region,
            "minor_region": minor_region,
        }

    def apply_source_credit_overlay(self, image: Image.Image, credit_text: str, font_paths: list[str]) -> None:
        text = credit_text.strip()
        if not text:
            return
        width, _height = image.size
        draw = ImageDraw.Draw(image, "RGBA")
        font = self._load_font(font_paths, size=max(14, int(width * 0.018)), sample_text=text, role="body")
        margin = max(12, int(width * 0.018))
        box = draw.textbbox((0, 0), text, font=font)
        text_w = box[2] - box[0]
        text_h = box[3] - box[1]
        x = width - margin - text_w
        y = margin
        pad_x = max(8, int(width * 0.008))
        pad_y = max(5, int(width * 0.005))
        draw.rounded_rectangle(
            [(x - pad_x, y - pad_y), (x + text_w + pad_x, y + text_h + pad_y)],
            radius=max(6, int(width * 0.01)),
            fill=(0, 0, 0, 125),
        )
        draw.text((x, y), text, fill=(245, 245, 245, 235), font=font)

    def _load_font(
        self,
        font_paths: list[str],
        size: int,
        sample_text: str,
        role: str = "body",
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        for path in sorted(font_paths, key=lambda item: self._font_priority(item, sample_text, role=role)):
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
        return ImageFont.load_default()

    def _wrap_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
    ) -> list[str]:
        if not text:
            return [""]

        text = text.replace("\r\n", "\n")
        lines: list[str] = []
        current = ""
        for ch in text:
            if ch == "\n":
                if current:
                    lines.append(current.rstrip())
                current = ""
                continue
            candidate = current + ch
            box = draw.textbbox((0, 0), candidate, font=font)
            if (box[2] - box[0]) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current.rstrip())
                current = ch
        if current:
            lines.append(current.rstrip())
        return lines if lines else [text]

    def _font_priority(self, path: str, sample_text: str, role: str = "body") -> tuple[int, int, str]:
        name = path.lower()
        has_han = any("\u4e00" <= ch <= "\u9fff" for ch in sample_text)
        cjk_hits = (
            "noto-sans-tc",
            "noto-sans-sc",
            "noto-sans-hk",
            "noto-sans-jp",
            "noto-sans-kr",
            "sourcehan",
            "source-han",
            "cjk",
            "han",
            "nanum",
            "mplus",
            "m-plus",
        )
        sans_hits = ("sans", "gothic", "heiti", "hei")
        serif_hits = ("serif", "ming", "song")
        heading_weight_hits = ("black", "bold", "semibold", "demi", "medium")
        regular_weight_hits = ("regular", "book", "normal", "medium")

        cjk_rank = 3
        if has_han and any(token in name for token in ("tc", "sc", "hk", "sourcehan", "source-han", "cjk", "han")):
            cjk_rank = 0
        elif any(token in name for token in cjk_hits):
            cjk_rank = 1
        elif "noto" in name:
            cjk_rank = 2

        sans_rank = 0 if any(token in name for token in sans_hits) else 2
        if any(token in name for token in serif_hits):
            sans_rank = 4

        if role == "heading":
            weight_rank = 0 if any(token in name for token in heading_weight_hits) else 2
        else:
            weight_rank = 0 if any(token in name for token in regular_weight_hits) else 2
            if any(token in name for token in ("black", "bold")):
                weight_rank = max(weight_rank, 1)

        variable_rank = 1 if ("variablefont" in name or "[wght]" in name) else 0

        return (cjk_rank, sans_rank + weight_rank + variable_rank, name)

    def _find_heading_font_from_body_family(
        self,
        font_paths: list[str],
        body_font_path: str | None,
        sample_text: str,
    ) -> str | None:
        if not body_font_path:
            return self.select_font_by_role(font_paths, sample_text=sample_text, role="heading")
        family = self._font_family_key(body_font_path)
        same_family = [p for p in font_paths if self._font_family_key(p) == family]
        if same_family:
            return self.select_font_by_role(same_family, sample_text=sample_text, role="heading")
        return body_font_path

    def _lines_height(self, font_size: int, line_count: int, line_ratio: float) -> int:
        count = max(1, line_count)
        return int(font_size * line_ratio * count)

    def _estimate_focus_box(self, image: Image.Image) -> tuple[int, int, int, int]:
        width, height = image.size
        small = image.convert("L").resize((96, 96), Image.Resampling.BILINEAR)
        pix = small.load()
        total = 0.0
        sum_x = 0.0
        sum_y = 0.0
        for y in range(1, 95):
            for x in range(1, 95):
                gx = abs(int(pix[x + 1, y]) - int(pix[x - 1, y]))
                gy = abs(int(pix[x, y + 1]) - int(pix[x, y - 1]))
                w = float(gx + gy)
                total += w
                sum_x += x * w
                sum_y += y * w
        if total <= 0.0:
            cx = width // 2
            cy = height // 2
        else:
            cx = int((sum_x / total) / 95.0 * width)
            cy = int((sum_y / total) / 95.0 * height)
        box_w = int(width * 0.34)
        box_h = int(height * 0.30)
        x1 = max(0, min(width - box_w, cx - box_w // 2))
        y1 = max(0, min(height - box_h, cy - box_h // 2))
        return (x1, y1, x1 + box_w, y1 + box_h)

    def _pick_two_block_regions(
        self,
        image: Image.Image,
        margin: int,
        hero_height: int,
        minor_height: int,
        focus_box: tuple[int, int, int, int],
        variant_index: int = 0,
        hero_shift: float = 0.0,
        minor_shift: float = 0.0,
    ) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
        width, height = image.size
        candidates = [
            (0.10, 0.80),
            (0.13, 0.74),
            (0.18, 0.78),
            (0.70, 0.16),
            (0.76, 0.22),
        ]
        if candidates:
            offset = variant_index % len(candidates)
            candidates = candidates[offset:] + candidates[:offset]
        best: tuple[tuple[int, int, int, int], tuple[int, int, int, int]] | None = None
        best_score = float("inf")
        for hero_r, minor_r in candidates:
            hero_y = int(height * max(0.06, min(0.86, hero_r + hero_shift)))
            minor_y = int(height * max(0.06, min(0.90, minor_r + minor_shift)))
            hero_region = (margin, hero_y, width - margin, hero_y + hero_height)
            minor_region = (margin, minor_y, width - margin, minor_y + minor_height)
            score = 0.0
            score += self._overlap_area(hero_region, focus_box) * 6.0
            score += self._overlap_area(minor_region, focus_box) * 4.0
            score += self._overlap_area(hero_region, minor_region) * 8.0
            score += self._out_of_bounds_penalty(hero_region, width, height)
            score += self._out_of_bounds_penalty(minor_region, width, height)
            if score < best_score:
                best_score = score
                best = (hero_region, minor_region)
        if best is None:
            top = (margin, int(height * 0.12), width - margin, int(height * 0.12) + hero_height)
            bottom = (margin, int(height * 0.76), width - margin, int(height * 0.76) + minor_height)
            return top, bottom
        return best

    def _overlap_area(self, a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
        x1 = max(a[0], b[0])
        y1 = max(a[1], b[1])
        x2 = min(a[2], b[2])
        y2 = min(a[3], b[3])
        if x2 <= x1 or y2 <= y1:
            return 0
        return (x2 - x1) * (y2 - y1)

    def _out_of_bounds_penalty(self, region: tuple[int, int, int, int], width: int, height: int) -> float:
        x1, y1, x2, y2 = region
        p = 0.0
        if x1 < 0:
            p += abs(x1) * 20.0
        if y1 < 0:
            p += abs(y1) * 20.0
        if x2 > width:
            p += abs(x2 - width) * 20.0
        if y2 > height:
            p += abs(y2 - height) * 20.0
        return p

    def _variant_index(self, token: str, modulo: int) -> int:
        text = (token or "").strip()
        if not text or modulo <= 0:
            return 0
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % modulo

    def _variant_jitter(self, token: str, salt: str, max_abs: float) -> float:
        text = (token or "").strip()
        if not text or max_abs <= 0:
            return 0.0
        digest = hashlib.sha256(f"{text}|{salt}".encode("utf-8")).hexdigest()
        raw = int(digest[:8], 16) / 0xFFFFFFFF
        centered = (raw * 2.0) - 1.0
        return centered * max_abs

    def _font_family_key(self, path: str) -> str:
        stem = path.lower().replace("\\", "/").split("/")[-1]
        base = stem.split(".")[0]
        for token in ("-bold", "_bold", "-black", "_black", "-regular", "_regular", "-medium", "_medium"):
            base = base.replace(token, "")
        return base

    def _pick_text_color(self, image: Image.Image, region: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        dark = (18, 18, 18, 240)
        light = (248, 248, 248, 240)
        bg_luma = self._region_luma(image, region)
        dark_ratio = self._contrast_ratio(bg_luma, self._rgb_luma(dark[:3]))
        light_ratio = self._contrast_ratio(bg_luma, self._rgb_luma(light[:3]))
        return light if light_ratio >= dark_ratio else dark

    def _region_luma(self, image: Image.Image, region: tuple[int, int, int, int]) -> float:
        x1, y1, x2, y2 = region
        x1 = max(0, min(image.width - 1, x1))
        y1 = max(0, min(image.height - 1, y1))
        x2 = max(x1 + 1, min(image.width, x2))
        y2 = max(y1 + 1, min(image.height, y2))
        crop = image.convert("RGB").crop((x1, y1, x2, y2)).resize((1, 1), Image.Resampling.BILINEAR)
        rgb = crop.getpixel((0, 0))
        return self._rgb_luma(rgb)

    def _rgb_luma(self, rgb: tuple[int, int, int]) -> float:
        def to_lin(v: int) -> float:
            c = v / 255.0
            if c <= 0.04045:
                return c / 12.92
            return ((c + 0.055) / 1.055) ** 2.4

        r, g, b = rgb
        return 0.2126 * to_lin(r) + 0.7152 * to_lin(g) + 0.0722 * to_lin(b)

    def _contrast_ratio(self, a_luma: float, b_luma: float) -> float:
        hi = max(a_luma, b_luma)
        lo = min(a_luma, b_luma)
        return (hi + 0.05) / (lo + 0.05)
