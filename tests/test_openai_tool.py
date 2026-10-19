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
                result = handle_tool_call({"poster_text_file": str(input_file)})
                self.assertTrue(result["ok"])
                self.assertEqual(result["status"]["code"], "completed")
                self.assertTrue(result["rendered"])
                self.assertEqual(result["decision"]["image_source"], "ai_fallback")
                self.assertTrue(Path(result["output_path"]).is_file())
                self.assertTrue(result["output_image_data_url"].startswith("data:image/png;base64,"))
                self.assertEqual(
                    result["output_download_data_url"],
                    result["output_image_data_url"],
                )
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
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"]["code"], "failed")
        self.assertFalse(result["rendered"])
        self.assertEqual(result["error_type"], "ValidationError")

    def test_handle_tool_call_returns_intake_on_missing_inputs(self) -> None:
        result = handle_tool_call({})
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"]["code"], "needs_input")
        self.assertFalse(result["rendered"])
        self.assertIn("intake_questions", result)
        self.assertGreaterEqual(len(result["intake_questions"]), 4)

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

    def test_style_preset_minimal_charity_tw_applies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["POSTER_OUTPUT_DIR"] = tmp_dir
            try:
                result = handle_tool_call(
                    {
                        "poster_request": {
                            "title": "讓小小生命，被好好愛著",
                            "body": "愛鼠協會｜倉鼠關懷宣傳\n認養代替購買・尊重生命・不棄養",
                            "style": {"preset": "minimal-charity-tw", "subject": "hamster"},
                            "layout": {"width": 1080, "height": 1350},
                            "assets": {"open_source_font_paths": []},
                        }
                    }
                )
                self.assertTrue(result["ok"])
                self.assertEqual(result["status"]["code"], "completed")
                self.assertEqual(
                    result["request"]["style"]["primary_color"],
                    "#F7F2E9",
                )
                self.assertEqual(result["request"]["style"]["panel_ratio"], 0.24)
                self.assertTrue(result["output_image_data_url"].startswith("data:image/png;base64,"))
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
                self.assertTrue(result["rendered"])
                self.assertIsNone(result.get("auto_pexels_query_used"))
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)
                if old is None:
                    os.environ.pop("PEXELS_API_KEY", None)
                else:
                    os.environ["PEXELS_API_KEY"] = old

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
                    }
                )
                self.assertTrue(result["ok"])
                self.assertTrue(result["rendered"])
                self.assertTrue(result["reference_images_used"])
                self.assertTrue(result["style_from_reference_applied"])
                self.assertEqual(result["decision"]["image_source"], "user_image")
            finally:
                os.environ.pop("POSTER_OUTPUT_DIR", None)


if __name__ == "__main__":
    unittest.main()
