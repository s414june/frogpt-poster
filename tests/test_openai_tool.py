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
                self.assertEqual(result["decision"]["image_source"], "ai_fallback")
                self.assertTrue(Path(result["output_path"]).is_file())
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
        self.assertEqual(result["error_type"], "ValidationError")

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


if __name__ == "__main__":
    unittest.main()
