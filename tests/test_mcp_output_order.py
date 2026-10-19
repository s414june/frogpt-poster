import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.mcp import dispatch


class MCPOutputOrderTests(unittest.TestCase):
    def test_tools_call_requires_intake_first_without_confirmation(self) -> None:
        message = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "prepare_poster",
                "arguments": {},
            },
        }
        response = dispatch(message)
        self.assertIsNotNone(response)
        result = response["result"]
        self.assertFalse(result["isError"])
        structured = result.get("structuredContent", {})
        self.assertEqual(structured.get("status", {}).get("code"), "needs_input")
        self.assertFalse(structured.get("rendered"))
        self.assertEqual(structured.get("next_action"), "ask_user_intake_questions")
        self.assertIn("intake_questions", structured)
        self.assertIn("尚未渲染海報", result["content"][0]["text"])

    def test_tools_call_renders_when_brief_complete_without_confirmation(self) -> None:
        message = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "prepare_poster",
                "arguments": {
                    "title": "讓小小生命，被好好愛著",
                    "body": "愛鼠協會｜倉鼠關懷宣傳\n認養代替購買・尊重生命・不棄養",
                    "width": 1080,
                    "height": 1350,
                },
            },
        }
        response = dispatch(message)
        self.assertIsNotNone(response)
        result = response["result"]
        self.assertFalse(result["isError"])
        structured = result.get("structuredContent", {})
        self.assertEqual(structured.get("status", {}).get("code"), "completed")
        self.assertTrue(structured.get("rendered"))

    def test_tools_call_returns_image_first_then_text(self) -> None:
        message = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "prepare_poster",
                "arguments": {
                    "intake_confirmed": True,
                    "poster_request": {
                        "title": "讓小小生命，被好好愛著",
                        "body": "愛鼠協會｜倉鼠關懷宣傳\n認養代替購買・尊重生命・不棄養",
                        "layout": {"width": 1080, "height": 1350},
                        "assets": {"open_source_font_paths": []},
                        "allow_ai_fallback": True,
                    }
                },
            },
        }
        response = dispatch(message)
        self.assertIsNotNone(response)
        result = response["result"]
        self.assertIn("content", result)
        content = result["content"]
        self.assertGreaterEqual(len(content), 2)
        self.assertEqual(content[0]["type"], "image")
        self.assertEqual(content[1]["type"], "text")
        structured = result.get("structuredContent", {})
        self.assertEqual(structured.get("status", {}).get("code"), "completed")
        self.assertTrue(structured.get("rendered"))
        # The last item remains machine-readable JSON text
        json.loads(content[-1]["text"])


if __name__ == "__main__":
    unittest.main()
