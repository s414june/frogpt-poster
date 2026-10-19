import json
import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gpt_package.openai_tool import TOOL_NAME, build_tool_definition, handle_tool_call


class OpenAIToolTests(unittest.TestCase):
    def test_schema_contains_tool_name(self) -> None:
        schema = build_tool_definition()
        self.assertEqual(schema["name"], TOOL_NAME)

    def test_handle_tool_call_accepts_valid_text_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
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


if __name__ == "__main__":
    unittest.main()
