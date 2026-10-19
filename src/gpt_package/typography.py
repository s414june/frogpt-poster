"""Typography extension points for open-source fonts."""


class TypographyEngine:
    """Placeholder typography engine for layout and style tuning."""

    def select_font(self, font_paths: list[str]) -> str | None:
        if not font_paths:
            return None
        return font_paths[0]

