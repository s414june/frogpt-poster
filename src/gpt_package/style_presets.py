"""Style preset application for consistent poster aesthetics."""

from .types import PosterRequest


def apply_style_preset(request: PosterRequest) -> None:
    preset = (request.style.preset or "").strip().lower()
    if preset != "minimal-charity-tw":
        return

    request.style.primary_color = "#F7F2E9"
    request.style.secondary_color = "#DFE8DD"
    request.style.accent_color = "#6D8A72"
    request.style.panel_ratio = 0.24
    request.style.title_max_lines = 2
    request.style.body_max_lines = 4
    request.style.background_shape_count = 3
    request.style.background_shape_alpha_min = 8
    request.style.background_shape_alpha_max = 18

