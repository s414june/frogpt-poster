"""Typography and text layout for poster rendering."""

from __future__ import annotations

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
        width, height = image.size
        margin = max(36, int(width * 0.06))
        sample_text = f"{title}\n{body}"
        body_font_path = self.select_font_by_role(font_paths, sample_text=sample_text, role="body")
        heading_font_path = self._find_heading_font_from_body_family(
            font_paths=font_paths,
            body_font_path=body_font_path,
            sample_text=sample_text,
        )
        title_font = self._load_font(
            [heading_font_path] if heading_font_path else font_paths,
            size=max(38, int(width * 0.06)),
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

        y = max(24, int(height * 0.08))
        for line in title_lines[:title_max_lines]:
            draw.text((margin, y), line, fill=title_color, font=title_font)
            y += int(title_font.size * 1.22)

        y = int(height * 0.76)
        for line in body_lines[:body_max_lines]:
            draw.text((margin, y), line, fill=body_color, font=body_font)
            y += int(body_font.size * 1.35)

        credit_text = str(getattr(style, "source_credit_text", "")).strip() if style else ""
        if credit_text:
            self.apply_source_credit_overlay(image, credit_text, font_paths)

        return {
            "selected_font": body_font_path or self.select_font(font_paths, sample_text=sample_text),
            "title_font": heading_font_path or body_font_path,
            "body_font": body_font_path,
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

        return (cjk_rank, sans_rank + weight_rank, name)

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
