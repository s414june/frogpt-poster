import json
import os
import tempfile
import unittest
import sys
import base64
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gpt_package.openai_tool import TOOL_NAME, build_tool_definition, handle_tool_call
from PIL import Image


class OpenAIToolTests(unittest.TestCase):
    def test_schema_contains_tool_name(self) -> None:
        schema = build_tool_definition()
        self.assertEqual(schema["name"], TOOL_NAME)

    def test_handle_tool_call_accepts_valid_text_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["POSTER_OUTPUT_DIR"] = tmp_dir
            try:
                input_file = Path(tmp_dir) / "poster.json"
                input_file.write_text(
                    json.dumps(
                        {
                            "title": "Event",
                            "body": "Join us this weekend",
                            "assets": {
                                "user_image_paths": [],
                                "open_source_font_paths": [],
                            },
                            "layout": {"width": 1080, "height": 1350},
                            "allow_ai_fallback": True,
                        }
                    ),
                    encoding="utf-8",
                )
                bg_path = Path(tmp_dir) / "bg.png"
                Image.new("RGB", (1080, 1350), (245, 239, 228)).save(bg_path)
                bg_b64 = base64.b64encode(bg_path.read_bytes()).decode("ascii")
                result = handle_tool_call(
                    {
                        "poster_text_file": str(input_file),
                        "generated_background_base64": bg_b64,
                        "generated_background_text_free_confirmed": True,
                    }
                )
                self.assertTrue(result["ok"])
                self.assertEqual(result["status"]["code"], "completed")
                self.assertTrue(result["rendered"])
                self.assertEqual(result["decision"]["image_source"], "user_image")
                self.assertTrue(Path(result["output_path"]).is_file())
                self.assertTrue(result["output_image_data_url"].startswith("data:image/png;base64,"))
                self.assertEqual(
                    result["output_download_data_url"],
                    result["output_image_data_url"],
                )
                self.assertTrue(str(result.get("output_preview_markdown", "")).startswith("![poster-preview](data:image/png;base64,"))
                self.assertTrue(result["output_filename"].endswith(".png"))
                self.assertEqual(result["display_priority"], ["image", "download", "text"])
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)

    def test_handle_tool_call_rejects_ai_disabled_without_images(self) -> None:
        result = handle_tool_call(
            {
                "title": "Event",
                "body": "Join us this weekend",
                "allow_ai_fallback": False,
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"]["code"], "needs_background_generation")
        self.assertFalse(result["rendered"])

    def test_handle_tool_call_returns_intake_on_missing_inputs(self) -> None:
        result = handle_tool_call({})
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"]["code"], "needs_input")
        self.assertFalse(result["rendered"])
        self.assertIn("intake_questions", result)
        self.assertGreaterEqual(len(result["intake_questions"]), 4)
        self.assertTrue(any(q.get("id") == "background_mode" for q in result["intake_questions"]))
        self.assertTrue(any(q.get("id") == "image_role_mode" for q in result["intake_questions"]))

    def test_handle_tool_call_returns_design_guide_when_requested(self) -> None:
        result = handle_tool_call({"request_intake_only": True, "show_design_guide": True})
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"]["code"], "needs_input")
        self.assertIn("design_guide", result)
        self.assertIn("principles", result["design_guide"])

    def test_handle_tool_call_accepts_inline_request_and_base64_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["POSTER_OUTPUT_DIR"] = tmp_dir
            try:
                image_path = Path(tmp_dir) / "inline.png"
                Image.new("RGB", (320, 320), (64, 120, 192)).save(image_path)
                image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
                result = handle_tool_call(
                    {
                        "poster_request": {
                            "title": "Inline Request",
                            "body": "Body from inline payload",
                            "layout": {"width": 800, "height": 1000},
                            "image_role_mode": "background",
                            "allow_ai_fallback": True,
                            "assets": {"open_source_font_paths": []},
                        },
                        "user_image_base64": [image_b64],
                    }
                )
                self.assertTrue(result["ok"])
                self.assertEqual(result["status"]["code"], "completed")
                self.assertTrue(result["rendered"])
                self.assertEqual(result["decision"]["image_source"], "user_image")
                self.assertIsInstance(result.get("output_image_base64"), str)
                self.assertGreater(len(result["output_image_base64"]), 100)
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)

    def test_handle_tool_call_uses_user_image_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["POSTER_OUTPUT_DIR"] = tmp_dir
            try:
                image_path = Path(tmp_dir) / "source.png"
                Image.new("RGB", (600, 400), (200, 80, 80)).save(image_path)
                result = handle_tool_call(
                    {
                        "title": "Event",
                        "body": "Join us this weekend",
                        "user_image_paths": [str(image_path)],
                        "allow_ai_fallback": True,
                    }
                )
                self.assertTrue(result["ok"])
                self.assertEqual(result["decision"]["image_source"], "user_image")
                self.assertTrue(Path(result["output_path"]).is_file())
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)

    def test_image_role_mode_both_disables_geometry_and_overlays_text_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["POSTER_OUTPUT_DIR"] = tmp_dir
            try:
                image_path = Path(tmp_dir) / "source.png"
                Image.new("RGB", (1080, 1350), (214, 168, 178)).save(image_path)
                result = handle_tool_call(
                    {
                        "title": "Both mode",
                        "body": "Use image as both",
                        "user_image_paths": [str(image_path)],
                        "image_role_mode": "both",
                        "allow_ai_fallback": True,
                    }
                )
                self.assertTrue(result["ok"])
                self.assertTrue(result["rendered"])
                self.assertEqual(result["resolved_image_role_mode"], "both")
                self.assertFalse(result["request"]["style"]["geometry_enabled"])
                self.assertEqual(result["request"]["assets"]["subject_image_paths"], [])
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)

    def test_pexels_query_requires_api_key(self) -> None:
        old = os.environ.pop("PEXELS_API_KEY", None)
        try:
            result = handle_tool_call(
                {
                    "title": "Event",
                    "body": "Join us",
                    "pexels_query": "hamster charity poster",
                }
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["error_type"], "ValidationError")
        finally:
            if old is not None:
                os.environ["PEXELS_API_KEY"] = old

    def test_auto_pexels_disabled_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["POSTER_OUTPUT_DIR"] = tmp_dir
            old = os.environ.get("PEXELS_API_KEY")
            os.environ["PEXELS_API_KEY"] = "dummy-key-for-test"
            try:
                result = handle_tool_call(
                    {
                        "title": "No external image",
                        "body": "Manual library phase",
                    }
                )
                self.assertTrue(result["ok"])
                self.assertFalse(result["rendered"])
                self.assertEqual(result["status"]["code"], "needs_background_generation")
                self.assertIsNone(result.get("auto_pexels_query_used"))
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)
                if old is None:
                    os.environ.pop("PEXELS_API_KEY", None)
                else:
                    os.environ["PEXELS_API_KEY"] = old

    def test_gradient_mode_without_any_visual_assets_still_requires_background_generation(self) -> None:
        result = handle_tool_call(
            {
                "title": "番茄義大利麵海報主角",
                "body": "溫暖義式風格",
                "background_mode": "gradient",
                "allow_ai_fallback": True,
            }
        )
        self.assertTrue(result["ok"])
        self.assertFalse(result["rendered"])
        self.assertEqual(result["status"]["code"], "needs_background_generation")

    def test_generated_background_base64_is_used_as_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["POSTER_OUTPUT_DIR"] = tmp_dir
            try:
                image_path = Path(tmp_dir) / "bg.png"
                img = Image.new("RGB", (540, 720), (233, 241, 228))
                for x in range(180):
                    for y in range(720):
                        img.putpixel((x, y), (227, 236, 224))
                for x in range(180, 360):
                    for y in range(720):
                        img.putpixel((x, y), (168, 191, 168))
                for x in range(360, 540):
                    for y in range(720):
                        img.putpixel((x, y), (109, 138, 114))
                img.save(image_path)
                bg_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
                result = handle_tool_call(
                    {
                        "title": "Ref test",
                        "body": "Using generated background as reference",
                        "generated_background_base64": bg_b64,
                        "generated_background_text_free_confirmed": True,
                    }
                )
                self.assertTrue(result["ok"])
                self.assertTrue(result["rendered"])
                self.assertTrue(result["reference_images_used"])
                self.assertTrue(result["style_from_reference_applied"])
                self.assertEqual(result["decision"]["image_source"], "user_image")
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)

    def test_generated_background_base64_inside_poster_request_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["POSTER_OUTPUT_DIR"] = tmp_dir
            try:
                image_path = Path(tmp_dir) / "bg-nested.png"
                img = Image.new("RGB", (540, 720), (228, 236, 245))
                img.save(image_path)
                bg_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
                result = handle_tool_call(
                    {
                        "poster_request": {
                            "title": "Nested bg",
                            "body": "Using nested generated background",
                            "generated_background_base64": bg_b64,
                            "generated_background_text_free_confirmed": True,
                        }
                    }
                )
                self.assertTrue(result["ok"])
                self.assertTrue(result["rendered"])
                self.assertTrue(result["reference_images_used"])
                self.assertEqual(result["decision"]["image_source"], "user_image")
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)

    def test_generated_background_requires_text_free_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["POSTER_OUTPUT_DIR"] = tmp_dir
            try:
                image_path = Path(tmp_dir) / "bg.png"
                Image.new("RGB", (540, 720), (233, 241, 228)).save(image_path)
                bg_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
                result = handle_tool_call(
                    {
                        "title": "Ref test",
                        "body": "Needs confirmation",
                        "generated_background_base64": bg_b64,
                    }
                )
                self.assertTrue(result["ok"])
                self.assertFalse(result["rendered"])
                self.assertEqual(result["status"]["code"], "needs_background_generation")
                self.assertIn("background_generation_requirements", result)
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)

    def test_reference_image_path_applies_source_credit_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["POSTER_OUTPUT_DIR"] = tmp_dir
            try:
                ref_path = Path(tmp_dir) / "my-author-sample.png"
                Image.new("RGB", (1080, 1350), (210, 216, 226)).save(ref_path)
                result = handle_tool_call(
                    {
                        "title": "Reference path test",
                        "body": "Overlay source credit in corner",
                        "reference_image_paths": [str(ref_path)],
                        "use_reference_as_fallback": True,
                    }
                )
                self.assertTrue(result["ok"])
                self.assertTrue(result["rendered"])
                self.assertTrue(result["reference_images_used"])
                self.assertTrue(result["source_credit_overlay_applied"])
                self.assertEqual(result["source_credit_overlay_text"], "my-author-sample/Source")
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)

    def test_reference_background_can_compose_subject_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["POSTER_OUTPUT_DIR"] = tmp_dir
            try:
                ref_path = Path(tmp_dir) / "reference.png"
                Image.new("RGB", (1080, 1350), (214, 228, 220)).save(ref_path)
                subject_path = Path(tmp_dir) / "subject.png"
                subject = Image.new("RGBA", (420, 420), (0, 0, 0, 0))
                for x in range(60, 360):
                    for y in range(80, 380):
                        subject.putpixel((x, y), (222, 176, 122, 255))
                subject.save(subject_path)
                subject_b64 = base64.b64encode(subject_path.read_bytes()).decode("ascii")

                result = handle_tool_call(
                    {
                        "title": "Compose subject",
                        "body": "Reference background with foreground object",
                        "reference_image_paths": [str(ref_path)],
                        "subject_image_base64": [subject_b64],
                        "use_reference_as_fallback": True,
                    }
                )
                self.assertTrue(result["ok"])
                self.assertTrue(result["rendered"])
                self.assertEqual(result["decision"]["image_source"], "user_image")
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)

    def test_background_mode_solid_renders_without_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["POSTER_OUTPUT_DIR"] = tmp_dir
            try:
                result = handle_tool_call(
                    {
                        "title": "Solid mode",
                        "body": "No reference should still render",
                        "background_mode": "solid",
                        "allow_ai_fallback": True,
                    }
                )
                self.assertTrue(result["ok"])
                self.assertEqual(result["status"]["code"], "completed")
                self.assertEqual(result["decision"]["image_source"], "ai_fallback")
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)

    def test_solid_single_subject_adds_geometry_and_subject_mask(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["POSTER_OUTPUT_DIR"] = tmp_dir
            try:
                subject = Path(tmp_dir) / "subject.png"
                rgba = Image.new("RGBA", (420, 420), (0, 0, 0, 0))
                for x in range(80, 340):
                    for y in range(70, 360):
                        rgba.putpixel((x, y), (230, 180, 130, 255))
                rgba.save(subject)
                result = handle_tool_call(
                    {
                        "title": "Geometry check",
                        "body": "solid bg single subject",
                        "background_mode": "solid",
                        "subject_image_paths": [str(subject)],
                    }
                )
                self.assertTrue(result["ok"])
                notes_text = "\n".join(result.get("notes", []))
                self.assertIn("Subject mask applied: True", notes_text)
                self.assertIn("Decorative geometry applied: True", notes_text)
                self.assertRegex(
                    notes_text,
                    r"Subject mask style: (feather|rounded)",
                )
                self.assertRegex(
                    notes_text,
                    r"Decorative geometry strategy: (subject_near|edge_near)",
                )
                self.assertRegex(
                    notes_text,
                    r"Decorative geometry shapes: [1-9][0-9]*",
                )
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)

    def test_gradient_single_subject_adds_geometry_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["POSTER_OUTPUT_DIR"] = tmp_dir
            try:
                subject = Path(tmp_dir) / "subject.png"
                rgba = Image.new("RGBA", (420, 420), (0, 0, 0, 0))
                for x in range(80, 340):
                    for y in range(70, 360):
                        rgba.putpixel((x, y), (120, 170, 210, 255))
                rgba.save(subject)
                result = handle_tool_call(
                    {
                        "title": "Gradient geometry",
                        "body": "default geometry on",
                        "background_mode": "gradient",
                        "subject_image_paths": [str(subject)],
                    }
                )
                self.assertTrue(result["ok"])
                notes_text = "\n".join(result.get("notes", []))
                self.assertIn("Decorative geometry applied: True", notes_text)
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)

    def test_can_disable_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["POSTER_OUTPUT_DIR"] = tmp_dir
            try:
                subject = Path(tmp_dir) / "subject.png"
                Image.new("RGBA", (320, 320), (220, 150, 150, 255)).save(subject)
                result = handle_tool_call(
                    {
                        "title": "No geometry",
                        "body": "disabled",
                        "background_mode": "gradient",
                        "geometry_enabled": False,
                        "subject_image_paths": [str(subject)],
                    }
                )
                self.assertTrue(result["ok"])
                notes_text = "\n".join(result.get("notes", []))
                self.assertIn("Decorative geometry applied: False", notes_text)
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)

    def test_subject_border_px_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["POSTER_OUTPUT_DIR"] = tmp_dir
            try:
                subject = Path(tmp_dir) / "subject.png"
                Image.new("RGBA", (320, 320), (220, 150, 150, 255)).save(subject)
                result = handle_tool_call(
                    {
                        "title": "Border too small",
                        "body": "should fail",
                        "background_mode": "gradient",
                        "subject_image_paths": [str(subject)],
                        "subject_border_px": 4,
                    }
                )
                self.assertFalse(result["ok"])
                self.assertEqual(result["error_type"], "ValidationError")
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)

    def test_background_mode_reference_needs_reference_when_missing(self) -> None:
        result = handle_tool_call(
            {
                "title": "Reference mode",
                "body": "Need reference input",
                "background_mode": "reference",
                "allow_ai_fallback": True,
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"]["code"], "needs_background_generation")

    def test_background_mode_invalid_returns_validation_error(self) -> None:
        result = handle_tool_call(
            {
                "title": "Invalid mode",
                "body": "Should fail validation",
                "background_mode": "texture",
            }
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "ValidationError")

    def test_palette_is_derived_from_subject_image_when_no_explicit_colors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["POSTER_OUTPUT_DIR"] = tmp_dir
            try:
                subject = Path(tmp_dir) / "subject.png"
                img = Image.new("RGB", (360, 360), (242, 178, 102))
                img.save(subject)
                result = handle_tool_call(
                    {
                        "title": "Palette from subject",
                        "body": "Use subject image colors",
                        "background_mode": "gradient",
                        "subject_image_paths": [str(subject)],
                    }
                )
                self.assertTrue(result["ok"])
                self.assertTrue(result["style_from_reference_applied"])
                self.assertEqual(result["palette_source_path"], str(subject))
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)

    def test_explicit_palette_wins_over_auto_palette_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["POSTER_OUTPUT_DIR"] = tmp_dir
            try:
                subject = Path(tmp_dir) / "subject.png"
                Image.new("RGB", (360, 360), (242, 178, 102)).save(subject)
                result = handle_tool_call(
                    {
                        "title": "Explicit palette",
                        "body": "Should not auto override",
                        "background_mode": "gradient",
                        "subject_image_paths": [str(subject)],
                        "primary_color": "#101010",
                        "secondary_color": "#202020",
                        "accent_color": "#303030",
                    }
                )
                self.assertTrue(result["ok"])
                self.assertFalse(result["style_from_reference_applied"])
                self.assertIsNone(result["palette_source_path"])
                self.assertEqual(result["request"]["style"]["primary_color"], "#101010")
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)

    def test_background_color_hint_prefers_requested_hue_from_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["POSTER_OUTPUT_DIR"] = tmp_dir
            try:
                ref = Path(tmp_dir) / "ref.png"
                img = Image.new("RGB", (300, 300), (90, 160, 95))
                for x in range(180, 300):
                    for y in range(300):
                        img.putpixel((x, y), (70, 110, 200))
                img.save(ref)
                result = handle_tool_call(
                    {
                        "title": "Color hinted",
                        "body": "希望藍色系",
                        "background_mode": "gradient",
                        "reference_image_paths": [str(ref)],
                        "use_reference_as_fallback": False,
                        "background_color_hint": "blue light",
                    }
                )
                self.assertTrue(result["ok"])
                primary = result["request"]["style"]["primary_color"].lstrip("#")
                r = int(primary[0:2], 16)
                g = int(primary[2:4], 16)
                b = int(primary[4:6], 16)
                self.assertGreater(b, r)
                self.assertGreater(b, g)
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)

    def test_background_color_hint_light_without_hue_still_brightens_palette(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["POSTER_OUTPUT_DIR"] = tmp_dir
            try:
                ref = Path(tmp_dir) / "ref-dark.png"
                Image.new("RGB", (280, 280), (56, 74, 92)).save(ref)
                result = handle_tool_call(
                    {
                        "title": "Tone hinted",
                        "body": "整體偏亮",
                        "background_mode": "gradient",
                        "reference_image_paths": [str(ref)],
                        "use_reference_as_fallback": False,
                        "background_color_hint": "light",
                    }
                )
                self.assertTrue(result["ok"])
                primary = result["request"]["style"]["primary_color"].lstrip("#")
                r = int(primary[0:2], 16)
                g = int(primary[2:4], 16)
                b = int(primary[4:6], 16)
                luma = r * 0.2126 + g * 0.7152 + b * 0.0722
                self.assertGreater(luma, 138.0)
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)

    def test_background_color_hint_forces_requested_hue_when_image_lacks_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["POSTER_OUTPUT_DIR"] = tmp_dir
            try:
                ref = Path(tmp_dir) / "ref-brown.png"
                Image.new("RGB", (280, 280), (142, 106, 88)).save(ref)
                result = handle_tool_call(
                    {
                        "title": "Hue steer",
                        "body": "希望藍色調",
                        "background_mode": "gradient",
                        "reference_image_paths": [str(ref)],
                        "use_reference_as_fallback": False,
                        "background_color_hint": "blue light",
                    }
                )
                self.assertTrue(result["ok"])
                primary = result["request"]["style"]["primary_color"].lstrip("#")
                r = int(primary[0:2], 16)
                g = int(primary[2:4], 16)
                b = int(primary[4:6], 16)
                self.assertGreater(b, r)
                self.assertGreater(b, g)
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)


if __name__ == "__main__":
    unittest.main()
