"""Poster generator entrypoint."""

from .policy import PosterPolicy
from .types import PosterRequest, PosterResult
from .validation import validate_request


class PosterGenerator:
    """High-level poster generation orchestrator."""

    def __init__(self, policy: PosterPolicy | None = None) -> None:
        self.policy = policy or PosterPolicy()

    def generate(self, request: PosterRequest) -> PosterResult:
        validate_request(request)
        decision = self.policy.decide(request)
        return PosterResult(
            output_path=None,
            decision=decision,
            notes=[
                "Validation passed.",
                "Rendering pipeline is not implemented yet (skeleton mode).",
            ],
        )
