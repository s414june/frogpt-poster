"""Domain errors for poster generation pipeline."""


class PosterError(Exception):
    """Base error for this package."""


class ValidationError(PosterError):
    """Raised when request data is invalid."""


class AssetError(PosterError):
    """Raised when required assets are missing or incompatible."""
