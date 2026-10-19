"""Typography and text layout for poster rendering."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont


class TypographyEngine:
    """Applies title/body text on poster image."""

    def select_font(self, font_paths: list[str], sample_text: str = "") -> str | None:
        if not font_paths:
            return None
        ranked = sorted(font_paths, key=lambda path: self._font_priority(path, sample_text))
        return ranked[0]

    def apply(self, image: Image.Image, title: str, body: str, font_paths: list[str], style=None) -> dict:
        width, height = image.size
        margin = max(36, int(width * 0.06))
        panel_ratio = float(getattr(style, "panel_ratio", 0.24)) if style else 0.24
        panel_ratio = max(0.18, min(0.35, panel_ratio))
        panel_height = int(height * panel_ratio)

        draw = ImageDraw.Draw(image, "RGBA")
        draw.rectangle(
            [(margin // 2, height - panel_height), (width - margin // 2, height)],
            fill=(0, 0, 0, 120),
        )

        sample_text = f"{title}\n{body}"
        title_font = self._load_font(font_paths, size=max(38, int(width * 0.06)), sample_text=sample_text)
        body_font = self._load_font(font_paths, size=max(24, int(width * 0.032)), sample_text=sample_text)

        text_width = width - margin * 2
        title_lines = self._wrap_text(draw, title.strip(), title_font, text_width)
        body_lines = self._wrap_text(draw, body.strip(), body_font, text_width)

        y = height - panel_height + max(24, int(width * 0.03))
        title_max_lines = int(getattr(style, "title_max_lines", 2)) if style else 2
        body_max_lines = int(getattr(style, "body_max_lines", 4)) if style else 4
        title_max_lines = max(1, min(4, title_max_lines))
        body_max_lines = max(2, min(8, body_max_lines))

        for line in title_lines[:title_max_lines]:
            draw.text((margin, y), line, fill=(255, 255, 255, 255), font=title_font)
            y += int(title_font.size * 1.22)
        y += max(6, int(width * 0.01))
        for line in body_lines[:body_max_lines]:
            draw.text((margin, y), line, fill=(237, 237, 237, 255), font=body_font)
            y += int(body_font.size * 1.35)

        return {"selected_font": self.select_font(font_paths, sample_text=sample_text)}

    def _load_font(
        self,
        font_paths: list[str],
        size: int,
        sample_text: str,
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        for path in sorted(font_paths, key=lambda item: self._font_priority(item, sample_text)):
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

    def _font_priority(self, path: str, sample_text: str) -> tuple[int, str]:
        name = path.lower()
        has_han = any("\u4e00" <= ch <= "\u9fff" for ch in sample_text)
        cjk_hits = (
            "noto-sans-tc",
            "noto-sans-sc",
            "noto-sans-hk",
            "noto-sans-jp",
            "noto-sans-kr",
            "noto-serif-tc",
            "noto-serif-sc",
            "noto-serif-jp",
            "noto-serif-kr",
            "sourcehan",
            "source-han",
            "cjk",
            "han",
            "nanum",
            "mplus",
            "m-plus",
        )
        if has_han and any(token in name for token in ("tc", "sc", "hk", "sourcehan", "source-han", "cjk", "han")):
            return (0, name)
        if any(token in name for token in cjk_hits):
            return (1, name)
        if "noto" in name:
            return (2, name)
        return (9, name)
