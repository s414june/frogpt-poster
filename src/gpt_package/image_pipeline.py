"""Image preprocessing extension points."""


class ImagePipeline:
    """Placeholder image pipeline for crop/remove-background steps."""

    def crop(self, image_path: str) -> str:
        return image_path

    def remove_background(self, image_path: str) -> str:
        return image_path

