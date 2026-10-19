import sys
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gpt_package.typography import TypographyEngine


class TypographyPriorityTests(unittest.TestCase):
    def test_prefers_static_cjk_over_variable_when_han_text(self) -> None:
        engine = TypographyEngine()
        sample = "讓小小生命，被好好愛著"
        static_font = r"assets\fonts\Noto_Sans_TC\static\NotoSansTC-Regular.ttf"
        variable_font = r"assets\fonts\noto-sans-tc\NotoSansTC[wght].ttf"
        chosen = engine.select_font_by_role([variable_font, static_font], sample_text=sample, role="body")
        self.assertEqual(chosen, static_font)

    def test_both_mode_uses_two_font_sizes_and_focus_aware_layout(self) -> None:
        engine = TypographyEngine()
        image = Image.new("RGB", (1080, 1350), (236, 143, 171))
        draw = ImageDraw.Draw(image)
        draw.rectangle([(390, 430), (700, 980)], fill=(245, 230, 228))
        draw.ellipse([(470, 420), (620, 560)], fill=(60, 50, 50))

        class _Style:
            image_role_mode = "both"
            source_credit_text = ""

        info = engine.apply(
            image=image,
            title="愛鼠協會",
            body="小小的牠，值得大大的愛\n認養代替購買・陪伴不離不棄",
            font_paths=[r"assets\fonts\Noto_Sans_TC\static\NotoSansTC-Regular.ttf"],
            style=_Style(),
        )
        self.assertEqual(info.get("layout_mode"), "both_focus_aware")
        self.assertGreater(int(info.get("hero_font_size", 0)), int(info.get("minor_font_size", 0)))
        hero_region = tuple(info.get("hero_region", (0, 0, 0, 0)))
        focus_box = tuple(info.get("focus_box", (0, 0, 0, 0)))
        overlap = engine._overlap_area(hero_region, focus_box)
        self.assertEqual(overlap, 0)

    def test_variation_token_changes_default_layout_variant(self) -> None:
        engine = TypographyEngine()
        tokens = ["token-a", "token-b", "token-c", "token-d", "token-e"]
        variants = [(t, engine._variant_index(t, 4)) for t in tokens]
        distinct = {}
        for t, v in variants:
            distinct.setdefault(v, t)
        self.assertGreaterEqual(len(distinct), 2)
        picked = list(distinct.values())[:2]

        class _StyleA:
            image_role_mode = "background"
            source_credit_text = ""
            variation_token = picked[0]

        class _StyleB:
            image_role_mode = "background"
            source_credit_text = ""
            variation_token = picked[1]

        img_a = Image.new("RGB", (1080, 1350), (226, 226, 226))
        info_a = engine.apply(
            image=img_a,
            title="主標題",
            body="副標題\n單位資訊",
            font_paths=[r"assets\fonts\Noto_Sans_TC\static\NotoSansTC-Regular.ttf"],
            style=_StyleA(),
        )
        img_b = Image.new("RGB", (1080, 1350), (226, 226, 226))
        info_b = engine.apply(
            image=img_b,
            title="主標題",
            body="副標題\n單位資訊",
            font_paths=[r"assets\fonts\Noto_Sans_TC\static\NotoSansTC-Regular.ttf"],
            style=_StyleB(),
        )
        self.assertNotEqual(info_a.get("layout_variant"), info_b.get("layout_variant"))

    def test_default_layout_uses_two_size_policy(self) -> None:
        engine = TypographyEngine()

        class _Style:
            image_role_mode = "background"
            source_credit_text = ""
            variation_token = "two-size-check"

        image = Image.new("RGB", (1080, 1350), (220, 220, 220))
        info = engine.apply(
            image=image,
            title="讓小小生命，被好好愛著",
            body="愛鼠協會｜倉鼠關懷宣傳\n認養代替購買・尊重生命・不棄養",
            font_paths=[r"assets\fonts\Noto_Sans_TC\static\NotoSansTC-Regular.ttf"],
            style=_Style(),
        )
        self.assertEqual(info.get("layout_mode"), "default")
        self.assertIn("major_font_size", info)
        self.assertIn("minor_font_size", info)
        self.assertGreater(int(info.get("major_font_size", 0)), int(info.get("minor_font_size", 0)))


if __name__ == "__main__":
    unittest.main()
