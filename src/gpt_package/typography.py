"""Typography and text layout for poster rendering."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont


class TypographyEngine:
    """Applies title/body text on poster image."""

    def select_font(self, font_paths: list[str]) -> str | None:
        if not font_paths:
            return None
        return font_paths[0]

    def apply(self, image: Image.Image, title: str, body: str, font_paths: list[str]) -> dict:
        width, height = image.size
        margin = max(36, int(width * 0.06))
        panel_height = int(height * 0.34)

        draw = ImageDraw.Draw(image, "RGBA")
        draw.rectangle(
            [(margin // 2, height - panel_height), (width - margin // 2, height)],
            fill=(0, 0, 0, 120),
        )

        title_font = self._load_font(font_paths, size=max(38, int(width * 0.06)))
        body_font = self._load_font(font_paths, size=max(24, int(width * 0.032)))

        text_width = width - margin * 2
        title_lines = self._wrap_text(draw, title.strip(), title_font, text_width)
        body_lines = self._wrap_text(draw, body.strip(), body_font, text_width)

        y = height - panel_height + max(24, int(width * 0.03))
        for line in title_lines[:3]:
            draw.text((margin, y), line, fill=(255, 255, 255, 255), font=title_font)
            y += int(title_font.size * 1.22)
        y += max(6, int(width * 0.01))
        for line in body_lines[:7]:
            draw.text((margin, y), line, fill=(237, 237, 237, 255), font=body_font)
            y += int(body_font.size * 1.35)

        return {"selected_font": self.select_font(font_paths)}

    def _load_font(self, font_paths: list[str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        for path in font_paths:
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

        words = text.replace("\n", " \n ").split()
        lines: list[str] = []
        current = ""
        for word in words:
            if word == "\n":
                if current:
                    lines.append(current)
                current = ""
                continue
            candidate = word if not current else f"{current} {word}"
            box = draw.textbbox((0, 0), candidate, font=font)
            if (box[2] - box[0]) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines if lines else [text]
