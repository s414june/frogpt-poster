import json
import sys
import unittest
import base64
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.mcp import dispatch
from PIL import Image


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
        self.assertTrue(str(structured.get("intake_session_token", "")).startswith("intake_"))
        self.assertIn("尚未渲染海報", result["content"][0]["text"])

    def test_tools_call_still_requires_intake_without_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bg_path = Path(tmp_dir) / "bg.png"
            Image.new("RGB", (1080, 1350), (245, 239, 228)).save(bg_path)
            bg_b64 = base64.b64encode(bg_path.read_bytes()).decode("ascii")
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
                    "generated_background_base64": bg_b64,
                },
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

    def test_tools_call_returns_image_first_then_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bg_path = Path(tmp_dir) / "bg.png"
            Image.new("RGB", (1080, 1350), (245, 239, 228)).save(bg_path)
            bg_b64 = base64.b64encode(bg_path.read_bytes()).decode("ascii")
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
                    ,
                    "generated_background_base64": bg_b64
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
        self.assertNotIn("output_image_base64", structured)
        self.assertIn("output_image_base64_length", structured)
        self.assertIn("若客戶端不支援 image content", content[2]["text"])
        # The last item remains machine-readable JSON text
        json.loads(content[-1]["text"])

    def test_tools_call_needs_background_generation_without_images(self) -> None:
        message = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "prepare_poster",
                "arguments": {
                    "intake_confirmed": True,
                    "title": "讓小小生命，被好好愛著",
                    "body": "愛鼠協會｜倉鼠關懷宣傳",
                },
            },
        }
        response = dispatch(message)
        self.assertIsNotNone(response)
        result = response["result"]
        structured = result.get("structuredContent", {})
        self.assertEqual(structured.get("status", {}).get("code"), "needs_background_generation")
        self.assertFalse(structured.get("rendered"))

    def test_tools_call_can_reuse_token_without_intake_confirmed(self) -> None:
        first = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "prepare_poster", "arguments": {}},
        }
        first_response = dispatch(first)
        self.assertIsNotNone(first_response)
        first_structured = first_response["result"].get("structuredContent", {})
        token = first_structured.get("intake_session_token")
        self.assertTrue(isinstance(token, str) and token.startswith("intake_"))

        with tempfile.TemporaryDirectory() as tmp_dir:
            bg_path = Path(tmp_dir) / "bg.png"
            Image.new("RGB", (1080, 1350), (245, 239, 228)).save(bg_path)
            bg_b64 = base64.b64encode(bg_path.read_bytes()).decode("ascii")

            second = {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "prepare_poster",
                    "arguments": {
                        "intake_session_token": token,
                        "title": "讓小小生命，被好好愛著",
                        "body": "愛鼠協會｜倉鼠關懷宣傳\n認養代替購買・尊重生命・不棄養",
                        "width": 1080,
                        "height": 1350,
                        "generated_background_base64": bg_b64,
                    },
                },
            }
            second_response = dispatch(second)

        self.assertIsNotNone(second_response)
        second_structured = second_response["result"].get("structuredContent", {})
        self.assertEqual(second_structured.get("status", {}).get("code"), "completed")
        self.assertTrue(second_structured.get("rendered"))
        self.assertEqual(second_structured.get("intake_session_token"), token)
        self.assertTrue(second_structured.get("intake_session_state", {}).get("intake_completed"))

    def test_tools_call_accepts_intake_fields_inside_poster_request(self) -> None:
        first = {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "prepare_poster", "arguments": {}},
        }
        first_response = dispatch(first)
        self.assertIsNotNone(first_response)
        token = first_response["result"].get("structuredContent", {}).get("intake_session_token")
        self.assertTrue(isinstance(token, str) and token.startswith("intake_"))

        with tempfile.TemporaryDirectory() as tmp_dir:
            bg_path = Path(tmp_dir) / "bg.png"
            Image.new("RGB", (1080, 1350), (245, 239, 228)).save(bg_path)
            bg_b64 = base64.b64encode(bg_path.read_bytes()).decode("ascii")

            second = {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "prepare_poster",
                    "arguments": {
                        "poster_request": {
                            "intake_session_token": token,
                            "intake_confirmed": True,
                            "title": "讓小小生命，被好好愛著",
                            "body": "愛鼠協會｜倉鼠關懷宣傳\n認養代替購買・尊重生命・不棄養",
                            "layout": {"width": 1080, "height": 1350},
                            "allow_ai_fallback": True,
                            "assets": {"open_source_font_paths": []},
                        },
                        "generated_background_base64": bg_b64,
                    },
                },
            }
            second_response = dispatch(second)

        self.assertIsNotNone(second_response)
        second_structured = second_response["result"].get("structuredContent", {})
        self.assertEqual(second_structured.get("status", {}).get("code"), "completed")
        self.assertTrue(second_structured.get("rendered"))
        self.assertEqual(second_structured.get("intake_session_token"), token)


if __name__ == "__main__":
    unittest.main()
