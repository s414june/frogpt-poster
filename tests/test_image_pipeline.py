import random
import sys
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.gpt_package.image_pipeline import ImagePipeline
from src.gpt_package.types import PosterRequest


def _hue(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    mx = max(r, g, b)
    mn = min(r, g, b)
    if mx == mn:
        return 0.0
    if mx == r:
        h = (g - b) / (mx - mn) % 6
    elif mx == g:
        h = (b - r) / (mx - mn) + 2
    else:
        h = (r - g) / (mx - mn) + 4
    return (h / 6.0) % 1.0


def _hue_delta(a: float, b: float) -> float:
    d = abs(a - b)
    return min(d, 1.0 - d)


class ImagePipelineColorPoolTests(unittest.TestCase):
    def test_geometry_pool_default_is_harmonized_and_limited(self) -> None:
        pipe = ImagePipeline()
        req = PosterRequest(
            title="溫暖關懷",
            body="自然柔和",
        )
        bg = Image.new("RGB", (800, 1000), (186, 142, 126))
        pool = pipe._prepare_geometry_color_pool(bg, (152, 134, 120), req, random.Random(7))
        self.assertGreaterEqual(len(pool), 1)
        self.assertLessEqual(len(pool), 3)
        bg_h = _hue((186, 142, 126))
        for color in pool:
            self.assertLessEqual(_hue_delta(_hue(color), bg_h), 0.18)

    def test_geometry_pool_can_enable_contrast_when_requested(self) -> None:
        pipe = ImagePipeline()
        req = PosterRequest(
            title="希望有跳色",
            body="整體想要撞色設計",
        )
        bg = Image.new("RGB", (800, 1000), (186, 142, 126))
        pool = pipe._prepare_geometry_color_pool(bg, (152, 134, 120), req, random.Random(9))
        self.assertGreaterEqual(len(pool), 1)
        self.assertLessEqual(len(pool), 3)
        bg_h = _hue((186, 142, 126))
        self.assertTrue(any(_hue_delta(_hue(color), bg_h) >= 0.40 for color in pool))

    def test_geometry_shapes_do_not_include_leaf_oval(self) -> None:
        pipe = ImagePipeline()
        shapes = pipe._shape_types()
        self.assertNotIn("leaf", shapes)
        self.assertIn("circle", shapes)

    def test_geometry_color_keeps_min_distance_from_background(self) -> None:
        pipe = ImagePipeline()
        bg = Image.new("RGB", (320, 320), (186, 142, 126))
        rng = random.Random(13)
        color = pipe._geometry_color(bg, (160, 160), [(188, 144, 128)], rng)
        dist = pipe._rgb_distance(color, (186, 142, 126))
        self.assertGreaterEqual(dist, 42.0)


if __name__ == "__main__":
    unittest.main()
