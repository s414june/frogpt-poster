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


if __name__ == "__main__":
    unittest.main()
