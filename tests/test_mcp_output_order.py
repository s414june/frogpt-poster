import json
import hashlib
import sys
import unittest
import base64
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gpt_package.mcp_http import dispatch
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
        self.assertIn("image_input_contract", structured)
        self.assertIn("assistant_execution_contract", structured)
        self.assertTrue(structured.get("assistant_execution_contract", {}).get("must_use_tool_for_final_poster"))
        self.assertEqual(
            structured.get("assistant_execution_contract", {}).get("delegate_phrase_mapping", {}).get("phrase"),
            "全部交給你",
        )
        self.assertIn("user_image_base64", structured.get("image_input_contract", {}).get("accepted_fields", []))
        self.assertNotIn("user_image_urls", structured.get("image_input_contract", {}).get("accepted_fields", []))
        self.assertTrue(str(structured.get("intake_session_token", "")).startswith("intake_"))
        self.assertIn("尚未渲染海報", result["content"][0]["text"])

    def test_initialize_instructions_define_delegate_phrase_workflow(self) -> None:
        message = {
            "jsonrpc": "2.0",
            "id": 40,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        }
        response = dispatch(message)
        self.assertIsNotNone(response)
        instructions = response.get("result", {}).get("instructions", "")
        self.assertIn("全部交給你", instructions)
        self.assertIn("generated_background_base64", instructions)

    def test_tools_call_still_requires_intake_without_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bg_path = Path(tmp_dir) / "bg.png"
            Image.new("RGB", (1080, 1350), (245, 239, 228)).save(bg_path)
            bg_b64 = "data:image/png;base64," + base64.b64encode(bg_path.read_bytes()).decode("ascii")
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
            bg_b64 = "data:image/png;base64," + base64.b64encode(bg_path.read_bytes()).decode("ascii")
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
                    "generated_background_base64": bg_b64,
                    "generated_background_text_free_confirmed": True,
                    "typography_confirmed": True,
                    "approved_draft_sha256": hashlib.sha256(base64.b64decode(bg_b64.split(",", 1)[1])).hexdigest(),
                },
            },
        }
        response = dispatch(message)
        self.assertIsNotNone(response)
        result = response["result"]
        self.assertIn("content", result)
        content = result["content"]
        self.assertGreaterEqual(len(content), 4)
        self.assertEqual(content[0]["type"], "image")
        self.assertEqual(content[1]["type"], "text")
        self.assertIn("縮圖預覽", content[1]["text"])
        structured = result.get("structuredContent", {})
        self.assertEqual(structured.get("status", {}).get("code"), "completed")
        self.assertTrue(structured.get("rendered"))
        self.assertIn("final_delivery_contract", structured)
        self.assertTrue(structured.get("final_delivery_contract", {}).get("must_include_preview_thumbnail"))
        self.assertTrue(structured.get("final_delivery_contract", {}).get("must_include_fullsize_download"))
        self.assertNotIn("output_image_base64", structured)
        self.assertIn("output_image_base64_length", structured)
        relay = structured.get("relay_payload", {})
        self.assertTrue(relay.get("preview_available"))
        self.assertIsInstance(relay.get("preview_base64"), str)
        self.assertGreater(len(relay.get("preview_base64", "")), 100)
        if structured.get("final_delivery_contract", {}).get("fullsize_embedded"):
            self.assertEqual(content[2]["type"], "image")
            self.assertIn("若客戶端不支援 image content", content[4]["text"])
            self.assertIn("relay_payload", content[5]["text"])
        else:
            self.assertIn("若客戶端不支援 image content", content[3]["text"])
            self.assertIn("relay_payload", content[4]["text"])
        self.assertNotIn("data:image/png;base64,", content[1]["text"])
        target_text_idx = 4 if structured.get("final_delivery_contract", {}).get("fullsize_embedded") else 3
        self.assertNotIn("data:image/png;base64,", content[target_text_idx]["text"])
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

    def test_tools_call_solid_mode_without_images_still_needs_background_generation(self) -> None:
        message = {
            "jsonrpc": "2.0",
            "id": 34,
            "method": "tools/call",
            "params": {
                "name": "prepare_poster",
                "arguments": {
                    "intake_confirmed": True,
                    "title": "三明治海報",
                    "body": "請直接渲染",
                    "background_mode": "solid",
                },
            },
        }
        response = dispatch(message)
        self.assertIsNotNone(response)
        structured = response["result"].get("structuredContent", {})
        self.assertEqual(structured.get("status", {}).get("code"), "needs_background_generation")
        self.assertFalse(structured.get("rendered"))

    def test_tools_call_rejects_path_style_image_inputs_with_friendly_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            img_path = Path(tmp_dir) / "from-mcp-schema.png"
            Image.new("RGB", (1080, 1350), (210, 220, 235)).save(img_path)
            message = {
                "jsonrpc": "2.0",
                "id": 31,
                "method": "tools/call",
                "params": {
                    "name": "prepare_poster",
                    "arguments": {
                        "intake_confirmed": True,
                        "title": "Schema receive test",
                        "body": "Should render directly with provided image path",
                        "image_role_mode": "both",
                        "user_image_paths": [str(img_path)],
                    },
                },
            }
            response = dispatch(message)
        self.assertIsNotNone(response)
        structured = response["result"].get("structuredContent", {})
        self.assertEqual(structured.get("status", {}).get("code"), "needs_input")
        self.assertEqual(structured.get("next_action"), "reupload_image_as_base64_only")
        hint = structured.get("user_friendly_hint", {})
        self.assertIn("user_image_base64", hint.get("accepted_fields", []))
        self.assertIn("user_image_paths", hint.get("not_accepted_fields", []))
        self.assertIn("user_image_urls", hint.get("not_accepted_fields", []))
        self.assertIn("image_input_contract", structured)
        self.assertIn("data:image/jpeg;base64,...", structured.get("image_input_contract", {}).get("required_data_url_prefix_examples", []))

    def test_tools_call_rewrites_failed_output_to_recoverable_needs_input(self) -> None:
        message = {
            "jsonrpc": "2.0",
            "id": 32,
            "method": "tools/call",
            "params": {
                "name": "prepare_poster",
                "arguments": {
                    "intake_confirmed": True,
                    "title": "base64 格式錯誤測試",
                    "body": "請重試",
                    "user_image_base64": ["not-base64"],
                },
            },
        }
        response = dispatch(message)
        self.assertIsNotNone(response)
        result = response["result"]
        self.assertFalse(result["isError"])
        structured = result.get("structuredContent", {})
        self.assertEqual(structured.get("status", {}).get("code"), "needs_input")
        self.assertEqual(structured.get("next_action"), "retry_with_base64_only")
        self.assertIn("user_friendly_hint", structured)
        self.assertNotIn("error", structured)
        self.assertNotIn("error_type", structured)

    def test_tools_call_rejects_url_style_image_inputs_with_base64_only_hint(self) -> None:
        message = {
            "jsonrpc": "2.0",
            "id": 33,
            "method": "tools/call",
            "params": {
                "name": "prepare_poster",
                "arguments": {
                    "intake_confirmed": True,
                    "title": "URL 圖片測試",
                    "body": "請改成 base64",
                    "user_image_urls": ["https://example.com/demo.jpg"],
                },
            },
        }
        response = dispatch(message)
        self.assertIsNotNone(response)
        structured = response["result"].get("structuredContent", {})
        self.assertEqual(structured.get("status", {}).get("code"), "needs_input")
        self.assertEqual(structured.get("next_action"), "reupload_image_as_base64_only")
        self.assertIn("user_image_urls", structured.get("user_friendly_hint", {}).get("not_accepted_fields", []))

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
            bg_b64 = "data:image/png;base64," + base64.b64encode(bg_path.read_bytes()).decode("ascii")

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
                        "generated_background_text_free_confirmed": True,
                        "typography_confirmed": True,
                        "approved_draft_sha256": hashlib.sha256(base64.b64decode(bg_b64.split(",", 1)[1])).hexdigest(),
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
        self.assertEqual(second_structured.get("request", {}).get("style", {}).get("variation_token"), "")

    def test_mcp_default_does_not_auto_regenerate_variation_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bg_path = Path(tmp_dir) / "bg.png"
            Image.new("RGB", (1080, 1350), (245, 239, 228)).save(bg_path)
            bg_b64 = "data:image/png;base64," + base64.b64encode(bg_path.read_bytes()).decode("ascii")

            first = {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {
                    "name": "prepare_poster",
                    "arguments": {
                        "intake_confirmed": True,
                        "title": "變體測試",
                        "body": "第一次",
                        "generated_background_base64": bg_b64,
                        "generated_background_text_free_confirmed": True,
                        "typography_confirmed": True,
                        "approved_draft_sha256": hashlib.sha256(base64.b64decode(bg_b64.split(",", 1)[1])).hexdigest(),
                    },
                },
            }
            first_response = dispatch(first)
            first_structured = first_response["result"].get("structuredContent", {})
            first_token = first_structured.get("request", {}).get("style", {}).get("variation_token")
            self.assertEqual(first_token, "")

            second = {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {
                    "name": "prepare_poster",
                    "arguments": {
                        "intake_confirmed": True,
                        "title": "變體測試",
                        "body": "第二次",
                        "variation_token": "stale-token",
                        "generated_background_base64": bg_b64,
                        "generated_background_text_free_confirmed": True,
                        "typography_confirmed": True,
                        "approved_draft_sha256": hashlib.sha256(base64.b64decode(bg_b64.split(",", 1)[1])).hexdigest(),
                    },
                },
            }
            second_response = dispatch(second)

        second_structured = second_response["result"].get("structuredContent", {})
        second_token = second_structured.get("request", {}).get("style", {}).get("variation_token")
        self.assertEqual(second_token, "stale-token")

    def test_mcp_regenerate_true_also_overrides_stale_variation_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bg_path = Path(tmp_dir) / "bg.png"
            Image.new("RGB", (1080, 1350), (245, 239, 228)).save(bg_path)
            bg_b64 = "data:image/png;base64," + base64.b64encode(bg_path.read_bytes()).decode("ascii")
            stale = "stale-token-123"

            message = {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {
                    "name": "prepare_poster",
                    "arguments": {
                        "intake_confirmed": True,
                        "title": "變體測試",
                        "body": "第三次",
                        "regenerate_variant": True,
                        "variation_token": stale,
                        "generated_background_base64": bg_b64,
                        "generated_background_text_free_confirmed": True,
                        "typography_confirmed": True,
                        "approved_draft_sha256": hashlib.sha256(base64.b64decode(bg_b64.split(",", 1)[1])).hexdigest(),
                    },
                },
            }
            response = dispatch(message)
        structured = response["result"].get("structuredContent", {})
        token = structured.get("request", {}).get("style", {}).get("variation_token")
        self.assertTrue(isinstance(token, str) and len(token) > 0)
        self.assertNotEqual(token, stale)

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
            bg_b64 = "data:image/png;base64," + base64.b64encode(bg_path.read_bytes()).decode("ascii")

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
                        "generated_background_text_free_confirmed": True,
                        "typography_confirmed": True,
                        "approved_draft_sha256": hashlib.sha256(base64.b64decode(bg_b64.split(",", 1)[1])).hexdigest(),
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
