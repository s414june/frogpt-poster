import random
import sys
import unittest
import colorsys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.gpt_package.image_pipeline import ImagePipeline
from src.gpt_package.types import ImageSource, PosterDecision, PosterRequest


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


def _avg_sat(image: Image.Image) -> float:
    sample = image.resize((48, 48)).convert("RGB")
    values = []
    for r, g, b in sample.getdata():
        _h, s, _v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        values.append(s)
    return sum(values) / max(1, len(values))


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

    def test_background_color_hint_adds_subtle_hue_and_tone_variation(self) -> None:
        pipe = ImagePipeline()
        req_plain = PosterRequest(
            title="社群市集活動",
            body="本週六 14:00-20:00",
        )
        req_plain.style.background_mode = "gradient"
        plain = pipe.build_background(req_plain, PosterDecision(image_source=ImageSource.AI_FALLBACK, reason="test"))
        plain_top = plain.getpixel((plain.width // 2, int(plain.height * 0.18)))

        req = PosterRequest(
            title="社群市集活動",
            body="本週六 14:00-20:00",
        )
        req.style.background_color_hint = "blue light"
        req.style.background_mode = "gradient"
        decision = PosterDecision(image_source=ImageSource.AI_FALLBACK, reason="test")
        image = pipe.build_background(req, decision)
        top = image.getpixel((image.width // 2, int(image.height * 0.18)))
        bottom = image.getpixel((image.width // 2, int(image.height * 0.82)))
        self.assertNotEqual(top, bottom)
        blue_hue = 0.62
        plain_top_dist = _hue_delta(_hue(plain_top), blue_hue)
        top_dist = _hue_delta(_hue(top), blue_hue)
        bottom_dist = _hue_delta(_hue(bottom), blue_hue)
        self.assertLess(top_dist, plain_top_dist)
        self.assertLess(bottom_dist, plain_top_dist)

    def test_generated_background_saturation_is_boosted_for_non_mono_palette(self) -> None:
        pipe = ImagePipeline()
        req = PosterRequest(title="活動海報", body="色彩測試")
        req.style.primary_color = "#9BB5A0"
        req.style.secondary_color = "#A8C0AA"
        req.style.background_mode = "gradient"
        req.style.background_color_hint = ""
        image = pipe.build_background(req, PosterDecision(image_source=ImageSource.AI_FALLBACK, reason="test"))
        self.assertGreater(_avg_sat(image), 0.20)

    def test_monochrome_hint_keeps_background_low_saturation(self) -> None:
        pipe = ImagePipeline()
        req = PosterRequest(title="單色海報", body="黑灰白測試")
        req.style.primary_color = "#888888"
        req.style.secondary_color = "#B0B0B0"
        req.style.background_mode = "gradient"
        req.style.background_color_hint = "gray light"
        image = pipe.build_background(req, PosterDecision(image_source=ImageSource.AI_FALLBACK, reason="test"))
        self.assertLess(_avg_sat(image), 0.10)

    def test_light_design_background_is_brighter(self) -> None:
        pipe = ImagePipeline()
        req = PosterRequest(title="春季市集", body="柔和淺色設計")
        req.style.primary_color = "#C8D7C8"
        req.style.secondary_color = "#D1DDD1"
        req.style.background_mode = "gradient"
        req.style.background_color_hint = "light"
        image = pipe.build_background(req, PosterDecision(image_source=ImageSource.AI_FALLBACK, reason="test"))
        sample = image.resize((48, 48)).convert("RGB")
        lumas = [(p[0] * 0.2126 + p[1] * 0.7152 + p[2] * 0.0722) for p in sample.getdata()]
        avg_luma = sum(lumas) / max(1, len(lumas))
        self.assertGreater(avg_luma, 168.0)

    def test_auto_mode_defaults_to_solid_not_gradient(self) -> None:
        pipe = ImagePipeline()
        req = PosterRequest(title="預設背景", body="不要漸層")
        req.style.primary_color = "#D4E0D4"
        req.style.secondary_color = "#A8C0A8"
        req.style.background_mode = "auto"
        image = pipe.build_background(req, PosterDecision(image_source=ImageSource.AI_FALLBACK, reason="test"))
        top = image.getpixel((image.width // 2, int(image.height * 0.15)))
        bottom = image.getpixel((image.width // 2, int(image.height * 0.85)))
        self.assertEqual(top, bottom)


if __name__ == "__main__":
    unittest.main()
