import random
import sys
import unittest
import colorsys
import tempfile
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


def _sat(rgb: tuple[int, int, int]) -> float:
    _h, s, _v = colorsys.rgb_to_hsv(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)
    return s


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
        self.assertNotIn("diamond", shapes)
        self.assertNotIn("triangle", shapes)

    def test_geometry_color_keeps_min_distance_from_background(self) -> None:
        pipe = ImagePipeline()
        bg = Image.new("RGB", (320, 320), (186, 142, 126))
        rng = random.Random(13)
        color = pipe._geometry_color(bg, (160, 160), [(188, 144, 128)], rng)
        dist = pipe._rgb_distance(color, (186, 142, 126))
        self.assertGreaterEqual(dist, 42.0)

    def test_geometry_brand_pair_uses_at_most_two_hues(self) -> None:
        pipe = ImagePipeline()
        bg = (232, 190, 198)
        pair = pipe._build_geometry_brand_pair(
            color_pool=[(168, 132, 196)],
            bg_sample=bg,
            rng=random.Random(5),
        )
        self.assertEqual(len(pair), 2)
        h0 = _hue(pair[0])
        h1 = _hue(pair[1])
        self.assertLessEqual(_hue_delta(h0, h1), 0.24)
        l0 = pair[0][0] * 0.2126 + pair[0][1] * 0.7152 + pair[0][2] * 0.0722
        l1 = pair[1][0] * 0.2126 + pair[1][1] * 0.7152 + pair[1][2] * 0.0722
        self.assertGreater(abs(l0 - l1), 14.0)
        _bh, bs, _bv = colorsys.rgb_to_hsv(bg[0] / 255.0, bg[1] / 255.0, bg[2] / 255.0)
        for color in pair:
            _h, s, _v = colorsys.rgb_to_hsv(color[0] / 255.0, color[1] / 255.0, color[2] / 255.0)
            self.assertGreater(s, bs + 0.14)

    def test_geometry_luma_is_lower_on_bright_background(self) -> None:
        pipe = ImagePipeline()
        bg = (240, 228, 222)
        pair = pipe._build_geometry_brand_pair(
            color_pool=[(182, 132, 202)],
            bg_sample=bg,
            rng=random.Random(11),
        )
        bg_luma = bg[0] * 0.2126 + bg[1] * 0.7152 + bg[2] * 0.0722
        for color in pair:
            luma = color[0] * 0.2126 + color[1] * 0.7152 + color[2] * 0.0722
            self.assertLess(luma, bg_luma - 34.0)

    def test_geometry_luma_is_higher_on_dark_background(self) -> None:
        pipe = ImagePipeline()
        bg = (36, 40, 48)
        pair = pipe._build_geometry_brand_pair(
            color_pool=[(126, 110, 188)],
            bg_sample=bg,
            rng=random.Random(12),
        )
        bg_luma = bg[0] * 0.2126 + bg[1] * 0.7152 + bg[2] * 0.0722
        for color in pair:
            luma = color[0] * 0.2126 + color[1] * 0.7152 + color[2] * 0.0722
            self.assertGreater(luma, bg_luma + 42.0)

    def test_geometry_yellow_is_boosted_not_muddy(self) -> None:
        pipe = ImagePipeline()
        bg = (236, 226, 206)
        pair = pipe._build_geometry_brand_pair(
            color_pool=[(182, 152, 54)],
            bg_sample=bg,
            rng=random.Random(23),
        )
        for color in pair:
            h, s, v = colorsys.rgb_to_hsv(color[0] / 255.0, color[1] / 255.0, color[2] / 255.0)
            if 0.11 <= h <= 0.22:
                self.assertGreaterEqual(s, 0.52)
                self.assertGreaterEqual(v, 0.80)

    def test_geometry_guard_reduces_green_harsh_saturation(self) -> None:
        pipe = ImagePipeline()
        bg = (236, 232, 224)
        pair = pipe._build_geometry_brand_pair(
            color_pool=[(98, 214, 124)],
            bg_sample=bg,
            rng=random.Random(21),
        )
        sats = [_sat(color) for color in pair]
        self.assertLessEqual(max(sats), 0.76)
        _bh, bs, _bv = colorsys.rgb_to_hsv(bg[0] / 255.0, bg[1] / 255.0, bg[2] / 255.0)
        for s in sats:
            self.assertGreater(s, bs + 0.14)

    def test_geometry_guard_reduces_fluorescent_purple_saturation(self) -> None:
        pipe = ImagePipeline()
        bg = (246, 236, 242)
        pr, pg, pb = colorsys.hsv_to_rgb(0.83, 0.95, 0.92)
        vivid_purple = (int(pr * 255), int(pg * 255), int(pb * 255))
        pair = pipe._build_geometry_brand_pair(
            color_pool=[vivid_purple],
            bg_sample=bg,
            rng=random.Random(22),
        )
        sats = [_sat(color) for color in pair]
        self.assertLessEqual(max(sats), 0.78)
        _bh, bs, _bv = colorsys.rgb_to_hsv(bg[0] / 255.0, bg[1] / 255.0, bg[2] / 255.0)
        for s in sats:
            self.assertGreater(s, bs + 0.14)

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
        self.assertLessEqual(top_dist, plain_top_dist + 0.01)
        self.assertLessEqual(bottom_dist, plain_top_dist + 0.01)

    def test_generated_background_saturation_is_boosted_for_non_mono_palette(self) -> None:
        pipe = ImagePipeline()
        req = PosterRequest(title="活動海報", body="色彩測試")
        req.style.primary_color = "#9BB5A0"
        req.style.secondary_color = "#A8C0AA"
        req.style.background_mode = "gradient"
        req.style.background_color_hint = ""
        image = pipe.build_background(req, PosterDecision(image_source=ImageSource.AI_FALLBACK, reason="test"))
        self.assertGreater(_avg_sat(image), 0.20)

    def test_green_background_is_softened_to_reduce_glare(self) -> None:
        pipe = ImagePipeline()
        req = PosterRequest(title="綠色主題", body="背景不要刺眼")
        req.style.primary_color = "#7DF376"
        req.style.secondary_color = "#72EA6E"
        req.style.background_mode = "solid"
        req.style.background_color_hint = ""
        image = pipe.build_background(req, PosterDecision(image_source=ImageSource.AI_FALLBACK, reason="test"))
        avg_sat = _avg_sat(image)
        self.assertLess(avg_sat, 0.34)
        self.assertGreater(avg_sat, 0.18)

    def test_green_light_hint_is_softened(self) -> None:
        pipe = ImagePipeline()
        req = PosterRequest(title="綠色提示", body="green light")
        req.style.primary_color = "#CDEBCB"
        req.style.secondary_color = "#BDE3BA"
        req.style.background_mode = "gradient"
        req.style.background_color_hint = "green light"
        image = pipe.build_background(req, PosterDecision(image_source=ImageSource.AI_FALLBACK, reason="test"))
        self.assertLess(_avg_sat(image), 0.30)

    def test_bright_purple_background_is_softened(self) -> None:
        pipe = ImagePipeline()
        req = PosterRequest(title="紫色主題", body="背景避免刺眼")
        req.style.primary_color = "#D488E6"
        req.style.secondary_color = "#CC7FE0"
        req.style.background_mode = "solid"
        req.style.background_color_hint = ""
        image = pipe.build_background(req, PosterDecision(image_source=ImageSource.AI_FALLBACK, reason="test"))
        sample = image.resize((48, 48)).convert("RGB")
        avg_sat = _avg_sat(sample)
        avg_luma = sum((p[0] * 0.2126 + p[1] * 0.7152 + p[2] * 0.0722) for p in sample.getdata()) / (48 * 48)
        self.assertLess(avg_sat, 0.46)
        self.assertGreater(avg_sat, 0.30)
        self.assertGreater(avg_luma, 150.0)
        self.assertLess(avg_luma, 178.0)

    def test_yellow_background_is_bright_and_vivid(self) -> None:
        pipe = ImagePipeline()
        req = PosterRequest(title="黃色主題", body="避免暗黃髒色")
        req.style.primary_color = "#C0A248"
        req.style.secondary_color = "#B7932E"
        req.style.background_mode = "solid"
        req.style.background_color_hint = ""
        image = pipe.build_background(req, PosterDecision(image_source=ImageSource.AI_FALLBACK, reason="test"))
        sample = image.resize((48, 48)).convert("RGB")
        h, s, v = colorsys.rgb_to_hsv(*[x / 255.0 for x in sample.getpixel((24, 24))])
        self.assertTrue(0.11 <= h <= 0.22)
        self.assertGreaterEqual(s, 0.50)
        self.assertGreaterEqual(v, 0.87)
        avg_luma = sum((p[0] * 0.2126 + p[1] * 0.7152 + p[2] * 0.0722) for p in sample.getdata()) / (48 * 48)
        self.assertGreater(avg_luma, 200.0)

    def test_orange_background_keeps_saturation_and_not_muddy(self) -> None:
        pipe = ImagePipeline()
        req = PosterRequest(title="橘色主題", body="維持彩度不要髒")
        req.style.primary_color = "#D58A3A"
        req.style.secondary_color = "#CC7C2A"
        req.style.background_mode = "solid"
        req.style.background_color_hint = ""
        image = pipe.build_background(req, PosterDecision(image_source=ImageSource.AI_FALLBACK, reason="test"))
        sample = image.resize((48, 48)).convert("RGB")
        h, s, v = colorsys.rgb_to_hsv(*[x / 255.0 for x in sample.getpixel((24, 24))])
        self.assertTrue(0.06 <= h < 0.11)
        self.assertGreaterEqual(s, 0.60)
        self.assertGreaterEqual(v, 0.76)

    def test_purple_can_be_more_saturated_than_green_but_still_controlled(self) -> None:
        pipe = ImagePipeline()
        green_req = PosterRequest(title="綠色背景", body="防刺眼")
        green_req.style.primary_color = "#7DF376"
        green_req.style.secondary_color = "#72EA6E"
        green_req.style.background_mode = "solid"
        green_req.style.background_color_hint = ""
        green_image = pipe.build_background(green_req, PosterDecision(image_source=ImageSource.AI_FALLBACK, reason="test"))
        green_sat = _avg_sat(green_image)

        purple_req = PosterRequest(title="紫色背景", body="可比綠色彩一點")
        purple_req.style.primary_color = "#D488E6"
        purple_req.style.secondary_color = "#CC7FE0"
        purple_req.style.background_mode = "solid"
        purple_req.style.background_color_hint = ""
        purple_image = pipe.build_background(purple_req, PosterDecision(image_source=ImageSource.AI_FALLBACK, reason="test"))
        purple_sat = _avg_sat(purple_image)

        self.assertGreater(purple_sat, green_sat)
        self.assertLess(purple_sat, 0.46)

    def test_monochrome_hint_keeps_background_low_saturation(self) -> None:
        pipe = ImagePipeline()
        req = PosterRequest(title="單色海報", body="黑灰白測試")
        req.style.primary_color = "#888888"
        req.style.secondary_color = "#B0B0B0"
        req.style.background_mode = "gradient"
        req.style.background_color_hint = "gray light"
        image = pipe.build_background(req, PosterDecision(image_source=ImageSource.AI_FALLBACK, reason="test"))
        self.assertLess(_avg_sat(image), 0.10)

    def test_white_light_hint_produces_neutral_white_background(self) -> None:
        pipe = ImagePipeline()
        req = PosterRequest(title="白色主題", body="white light")
        req.style.primary_color = "#F6F1E8"  # warm default that used to drift to beige
        req.style.secondary_color = "#E8DFD0"
        req.style.background_mode = "solid"
        req.style.background_color_hint = "white light"
        image = pipe.build_background(req, PosterDecision(image_source=ImageSource.AI_FALLBACK, reason="test"))
        sample = image.resize((48, 48)).convert("RGB")
        pixels = list(sample.getdata())
        avg_sat = _avg_sat(sample)
        avg_luma = sum((p[0] * 0.2126 + p[1] * 0.7152 + p[2] * 0.0722) for p in pixels) / max(1, len(pixels))
        avg_rg_gap = sum(abs(p[0] - p[1]) + abs(p[1] - p[2]) + abs(p[0] - p[2]) for p in pixels) / max(1, len(pixels))
        self.assertLess(avg_sat, 0.06)
        self.assertGreater(avg_luma, 238.0)
        self.assertLess(avg_rg_gap, 6.0)

    def test_black_hint_produces_neutral_dark_background(self) -> None:
        pipe = ImagePipeline()
        req = PosterRequest(title="黑色主題", body="black dark")
        req.style.primary_color = "#F6F1E8"
        req.style.secondary_color = "#E8DFD0"
        req.style.background_mode = "solid"
        req.style.background_color_hint = "black dark"
        image = pipe.build_background(req, PosterDecision(image_source=ImageSource.AI_FALLBACK, reason="test"))
        sample = image.resize((48, 48)).convert("RGB")
        pixels = list(sample.getdata())
        avg_sat = _avg_sat(sample)
        avg_luma = sum((p[0] * 0.2126 + p[1] * 0.7152 + p[2] * 0.0722) for p in pixels) / max(1, len(pixels))
        avg_rg_gap = sum(abs(p[0] - p[1]) + abs(p[1] - p[2]) + abs(p[0] - p[2]) for p in pixels) / max(1, len(pixels))
        self.assertLess(avg_sat, 0.05)
        self.assertLess(avg_luma, 40.0)
        self.assertLess(avg_rg_gap, 5.0)

    def test_gray_hint_produces_neutral_gray_background(self) -> None:
        pipe = ImagePipeline()
        req = PosterRequest(title="灰色主題", body="gray light")
        req.style.primary_color = "#F6F1E8"
        req.style.secondary_color = "#E8DFD0"
        req.style.background_mode = "solid"
        req.style.background_color_hint = "gray light"
        image = pipe.build_background(req, PosterDecision(image_source=ImageSource.AI_FALLBACK, reason="test"))
        sample = image.resize((48, 48)).convert("RGB")
        pixels = list(sample.getdata())
        avg_sat = _avg_sat(sample)
        avg_luma = sum((p[0] * 0.2126 + p[1] * 0.7152 + p[2] * 0.0722) for p in pixels) / max(1, len(pixels))
        avg_rg_gap = sum(abs(p[0] - p[1]) + abs(p[1] - p[2]) + abs(p[0] - p[2]) for p in pixels) / max(1, len(pixels))
        self.assertLess(avg_sat, 0.05)
        self.assertGreater(avg_luma, 145.0)
        self.assertLess(avg_luma, 185.0)
        self.assertLess(avg_rg_gap, 6.0)

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

    def test_solid_mode_with_color_hint_keeps_non_gradient_tint(self) -> None:
        pipe = ImagePipeline()
        req = PosterRequest(title="色調測試", body="solid + blue light")
        req.style.primary_color = "#D4E0D4"
        req.style.secondary_color = "#A8C0A8"
        req.style.background_mode = "solid"
        req.style.background_color_hint = "blue light"
        image = pipe.build_background(req, PosterDecision(image_source=ImageSource.AI_FALLBACK, reason="test"))
        top = image.getpixel((image.width // 2, int(image.height * 0.15)))
        bottom = image.getpixel((image.width // 2, int(image.height * 0.85)))
        self.assertEqual(top, bottom)

    def test_auto_mode_still_allows_geometry_with_single_subject(self) -> None:
        pipe = ImagePipeline()
        with tempfile.TemporaryDirectory() as tmp_dir:
            subject_path = Path(tmp_dir) / "subject.png"
            Image.new("RGBA", (260, 260), (230, 150, 170, 255)).save(subject_path)
            req = PosterRequest(title="主體海報", body="自動背景也要有向量裝飾")
            req.style.background_mode = "auto"
            req.style.geometry_enabled = True
            req.assets.subject_image_paths = [str(subject_path)]
            image = pipe.build_background(req, PosterDecision(image_source=ImageSource.AI_FALLBACK, reason="test"))
            self.assertEqual(image.mode, "RGB")
            effects = pipe.get_last_effects()
            self.assertTrue(effects.get("decorative_geometry_applied"))
            self.assertGreater(int(effects.get("decorative_geometry_shapes", 0)), 0)


if __name__ == "__main__":
    unittest.main()
