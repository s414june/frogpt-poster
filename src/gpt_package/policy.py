"""Decision policy: prefer real user images over AI generation."""

from .types import ImageSource, PosterDecision, PosterRequest


class PosterPolicy:
    """Enforces image-source policy for anti-AI-look output."""

    def decide(self, request: PosterRequest) -> PosterDecision:
        if request.assets.user_image_paths:
            return PosterDecision(
                image_source=ImageSource.USER_IMAGE,
                reason="User provided real photos; prioritize authenticity.",
            )
        return PosterDecision(
            image_source=ImageSource.AI_FALLBACK,
            reason="No usable user images provided; AI fallback enabled.",
        )

