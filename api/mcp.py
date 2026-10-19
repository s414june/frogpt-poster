"""Stateless Streamable HTTP MCP adapter for poster rendering."""
import json
import sys
import time
import uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gpt_package.openai_tool import handle_tool_call

NAME = "prepare_poster"
_INTAKE_SESSION_MAX = 512
_INTAKE_SESSION_TTL_SECONDS = 60 * 60 * 12
_INTAKE_SESSIONS: dict[str, dict] = {}
_MAX_REQUEST_BYTES = 16 * 1024 * 1024
SCHEMA = {
    "type": "object",
    "properties": {
        "intake_confirmed": {"type": "boolean"},
        "intake_session_token": {"type": "string", "minLength": 8, "maxLength": 128},
        "poster_request": {"type": "object"},
        "title": {"type": "string", "minLength": 1, "maxLength": 120},
        "body": {"type": "string", "minLength": 1, "maxLength": 4000},
        "width": {"type": "integer", "minimum": 256, "maximum": 4096},
        "height": {"type": "integer", "minimum": 256, "maximum": 4096},
        "primary_color": {"type": "string"},
        "secondary_color": {"type": "string"},
        "accent_color": {"type": "string"},
        "subject": {"type": "string"},
        "background_mode": {"type": "string", "enum": ["auto", "solid", "gradient", "reference"]},
        "image_role_mode": {"type": "string", "enum": ["auto", "subject", "background", "both"]},
        "geometry_enabled": {"type": "boolean"},
        "subject_mask_mode": {"type": "string", "enum": ["rounded", "feather"]},
        "subject_border_px": {"type": "integer", "minimum": 0, "maximum": 20},
        "background_color_hint": {"type": "string"},
        "creative_source_preference": {
            "type": "string",
            "enum": ["auto", "real_image_priority", "gpt_generate"],
        },
        "intake_answers": {"type": "object"},
        "reference_image_urls": {"type": "array", "items": {"type": "string"}},
        "reference_image_paths": {"type": "array", "items": {"type": "string"}},
        "reference_image_base64": {"type": "array", "items": {"type": "string"}},
        "generated_background_base64": {"type": "string"},
        "generated_background_text_free_confirmed": {"type": "boolean"},
        "pexels_query": {"type": "string"},
        "pexels_orientation": {"type": "string"},
        "pexels_per_page": {"type": "integer", "minimum": 1, "maximum": 10},
        "auto_pexels_fallback": {"type": "boolean"},
        "use_reference_as_fallback": {"type": "boolean"},
        "user_image_base64": {"type": "array", "items": {"type": "string"}},
        "user_image_urls": {"type": "array", "items": {"type": "string"}},
        "user_image_paths": {"type": "array", "items": {"type": "string"}},
        "subject_image_base64": {"type": "array", "items": {"type": "string"}},
        "subject_image_urls": {"type": "array", "items": {"type": "string"}},
        "subject_image_paths": {"type": "array", "items": {"type": "string"}},
        "regenerate_variant": {"type": "boolean"},
        "variation_token": {"type": "string"},
        "show_design_guide": {"type": "boolean"},
    },
    "required": [],
    "additionalProperties": False,
}
TOOL = {
    "name": NAME,
    "description": "Mandatory first-round intake poster tool. Ask intake once, then reuse intake_session_token for follow-up renders.",
    "inputSchema": SCHEMA,
    "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
}


def _compact_output(output: dict) -> dict:
    compact = dict(output)
    image_b64 = compact.pop("output_image_base64", None)
    preview_b64 = compact.pop("output_preview_base64", None)
    data_url = compact.pop("output_image_data_url", None)
    preview_data_url = compact.pop("output_preview_data_url", None)
    compact.pop("output_download_data_url", None)
    compact.pop("output_preview_markdown", None)
    if isinstance(image_b64, str):
        compact["output_image_base64_length"] = len(image_b64)
    if isinstance(preview_b64, str):
        compact["output_preview_base64_length"] = len(preview_b64)
    if isinstance(data_url, str):
        compact["output_image_data_url_length"] = len(data_url)
    if isinstance(preview_data_url, str):
        compact["output_preview_data_url_length"] = len(preview_data_url)
    request = compact.get("request")
    if isinstance(request, dict):
        compact["request"] = _compact_request(request)
    if compact.get("pipeline_stage") == "completed":
        compact.pop("intake_questions", None)
        compact.pop("result_json", None)
    return compact


def _compact_request(request: dict) -> dict:
    copy = dict(request)
    assets = copy.get("assets")
    if isinstance(assets, dict):
        assets_copy = dict(assets)
        font_paths = assets_copy.get("open_source_font_paths")
        if isinstance(font_paths, list):
            assets_copy["open_source_font_paths_count"] = len(font_paths)
            assets_copy["open_source_font_paths_sample"] = font_paths[:3]
            assets_copy.pop("open_source_font_paths", None)
        copy["assets"] = assets_copy
    return copy


def _has_render_brief(args: dict) -> bool:
    title = str(args.get("title", "")).strip()
    body = str(args.get("body", "")).strip()
    if title and body:
        return True
    payload = args.get("poster_request")
    if not isinstance(payload, dict):
        return False
    p_title = str(payload.get("title", "")).strip()
    p_body = str(payload.get("body", "")).strip()
    if p_title and p_body:
        return True
    copy = payload.get("copy")
    if isinstance(copy, dict):
        headline = str(copy.get("headline", "")).strip()
        subtitle = str(copy.get("subtitle", "")).strip()
        cta = str(copy.get("cta", "")).strip()
        return bool(headline and (subtitle or cta))
    return False


def _prune_intake_sessions(now_ts: float) -> None:
    expired = [
        token for token, meta in _INTAKE_SESSIONS.items()
        if (now_ts - float(meta.get("updated_at", 0.0))) > _INTAKE_SESSION_TTL_SECONDS
    ]
    for token in expired:
        _INTAKE_SESSIONS.pop(token, None)
    if len(_INTAKE_SESSIONS) <= _INTAKE_SESSION_MAX:
        return
    old_tokens = sorted(_INTAKE_SESSIONS.items(), key=lambda kv: float(kv[1].get("updated_at", 0.0)))
    overflow = len(_INTAKE_SESSIONS) - _INTAKE_SESSION_MAX
    for token, _meta in old_tokens[:overflow]:
        _INTAKE_SESSIONS.pop(token, None)


def _ensure_intake_session_token(args: dict, now_ts: float) -> tuple[str, dict, bool]:
    maybe = _resolve_intake_session_token(args)
    from_request = isinstance(maybe, str) and bool(maybe.strip())
    if isinstance(maybe, str) and maybe.strip():
        token = maybe.strip()
    else:
        token = f"intake_{uuid.uuid4().hex}"
    state = _INTAKE_SESSIONS.get(token)
    if not isinstance(state, dict):
        state = {"intake_completed": False, "created_at": now_ts, "updated_at": now_ts}
        _INTAKE_SESSIONS[token] = state
    else:
        state["updated_at"] = now_ts
    return token, state, from_request


def _resolve_intake_session_token(args: dict) -> str:
    top = args.get("intake_session_token")
    if isinstance(top, str) and top.strip():
        return top.strip()
    payload = args.get("poster_request")
    if isinstance(payload, dict):
        nested = payload.get("intake_session_token")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return ""


def _resolve_intake_confirmed(args: dict) -> bool:
    top = args.get("intake_confirmed")
    if isinstance(top, bool):
        return top
    payload = args.get("poster_request")
    if isinstance(payload, dict):
        nested = payload.get("intake_confirmed")
        if isinstance(nested, bool):
            return nested
    return False

def dispatch(message):
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
    if "id" not in message:
        return None
    result = {"jsonrpc": "2.0", "id": message["id"]}
    method = message["method"]
    params = message.get("params", {})
    if not isinstance(params, dict):
        result["error"] = {"code": -32602, "message": "params must be an object"}
        return result
    if method == "initialize":
        versions = ("2025-03-26", "2025-06-18", "2025-11-25")
        version = params.get("protocolVersion")
        result["result"] = {"protocolVersion": version if version in versions else versions[0], "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "FroGPT Poster", "version": "0.2.5"}, "instructions": "Always perform one intake round first. Reuse intake_session_token across calls; once brief is provided after intake, the token is remembered and follow-up renders no longer need intake_confirmed=true."}
    elif method == "ping":
        result["result"] = {}
    elif method == "tools/list":
        result["result"] = {"tools": [TOOL]}
    elif method == "tools/call":
        args = params.get("arguments", {})
        if params.get("name") != NAME:
            result["error"] = {"code": -32602, "message": "Unknown tool"}
        elif not isinstance(args, dict) or set(args) - set(SCHEMA["properties"]):
            result["error"] = {"code": -32602, "message": "Arguments shape not allowed by schema."}
        else:
            now_ts = time.time()
            _prune_intake_sessions(now_ts)
            intake_session_token, intake_state, token_from_request = _ensure_intake_session_token(args, now_ts)
            intake_confirmed = _resolve_intake_confirmed(args)
            remembered = bool(intake_state.get("intake_completed", False))
            auto_confirmed = token_from_request and _has_render_brief(args)
            intake_confirmed_effective = intake_confirmed or remembered or auto_confirmed
            call_args = dict(args)
            if intake_confirmed_effective and bool(call_args.get("regenerate_variant", False)):
                call_args.pop("variation_token", None)
            if not intake_confirmed_effective:
                call_args["request_intake_only"] = True
                call_args["show_design_guide"] = True
            output = handle_tool_call(call_args)
            output["intake_session_token"] = intake_session_token
            output["intake_session_state"] = {
                "intake_completed": bool(intake_state.get("intake_completed", False)),
                "ttl_seconds": _INTAKE_SESSION_TTL_SECONDS,
            }
            if not intake_confirmed_effective:
                output["next_request_hint"] = {
                    "intake_session_token": intake_session_token,
                    "intake_confirmed": True,
                }
            if not intake_confirmed_effective and output.get("status", {}).get("code") != "needs_input":
                output["status"] = {
                    "code": "needs_input",
                    "message": "intake_questions_required_before_render",
                }
                output["next_action"] = "ask_user_intake_questions"
                output["rendered"] = False
            if intake_confirmed_effective and output.get("status", {}).get("code") != "needs_input":
                intake_state["intake_completed"] = True
                intake_state["updated_at"] = now_ts
                output["intake_session_state"]["intake_completed"] = True
            content = []
            status_code = output.get("status", {}).get("code")
            if status_code == "needs_input":
                questions = output.get("intake_questions", [])
                question_lines = []
                for q in questions:
                    question_lines.append(f"- {q.get('question', '')}")
                content.append(
                    {
                        "type": "text",
                        "text": (
                            "尚未渲染海報。請先向使用者詢問以下問題並收集答案，再用同一個 intake_session_token 重新呼叫工具：\n"
                            + "\n".join(question_lines)
                        ),
                    }
                )
            if status_code == "needs_background_generation":
                prompt = output.get("background_generation_prompt", "")
                reqs = output.get("background_generation_requirements", {})
                required_flag = reqs.get("required_flag_on_retry", "generated_background_text_free_confirmed=true")
                content.append(
                    {
                        "type": "text",
                        "text": (
                            "目前需要『無字背景海報』才能繼續。請先用 GPT 生成無文字背景，並確認沒有字母/數字/logo/浮水印。\n"
                            f"重呼叫時請同時帶入: {required_flag}\n"
                            f"建議提示詞：{prompt}"
                        ),
                    }
                )
            preview_b64 = output.get("output_preview_base64") or output.get("output_image_base64")
            preview_mime = output.get("output_preview_mime_type", output.get("output_mime_type", "image/png"))
            if output.get("ok") and output.get("rendered") and preview_b64:
                # 1) Rendered image first for immediate preview
                content.append(
                    {
                        "type": "image",
                        "data": preview_b64,
                        "mimeType": preview_mime,
                    }
                )
                # 2) Download hint second
                filename = output.get("output_filename", "poster.png")
                sha = str(output.get("output_image_sha256", "")).strip()
                short_sha = sha[:12] if sha else ""
                content.append(
                    {
                        "type": "text",
                        "text": (
                            "已完成渲染，請優先顯示上方圖片。\n"
                            f"下載檔名: {filename}\n"
                            f"輸出指紋: {short_sha}"
                        ),
                    }
                )
                content.append(
                    {
                        "type": "text",
                        "text": (
                            "若客戶端不支援 image content，請改走 API `/api/poster` 讀取 `output_image_data_url`。"
                        ),
                    }
                )
            elif output.get("ok") and output.get("rendered"):
                output["ok"] = False
                output["status"] = {
                    "code": "failed",
                    "message": "render_completed_but_preview_missing",
                }
                output["next_action"] = "retry_render"
                output["rendered"] = False
                content.append(
                    {
                        "type": "text",
                        "text": "渲染完成但預覽圖遺失，請重試一次。",
                    }
                )
            # 3) Structured/text details last
            compact_output = _compact_output(output)
            content.append({"type": "text", "text": json.dumps(compact_output, ensure_ascii=False)})
            result["result"] = {
                "content": content,
                "structuredContent": compact_output,
                "isError": not output.get("ok", False),
            }
    else:
        result["error"] = {"code": -32601, "message": "Method not found"}
    return result


class handler(BaseHTTPRequestHandler):
    def reply(self, status, payload=None):
        body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        if status == 405:
            self.send_header("Allow", "POST")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.reply(405)

    def do_DELETE(self):
        self.reply(405)

    def do_POST(self):
        origin = self.headers.get("Origin")
        if origin and origin not in ("https://chatgpt.com", "https://frogpt-poster.vercel.app"):
            self.reply(403, {"error": "Origin not allowed"})
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            self.reply(415, {"error": "Expected application/json"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > _MAX_REQUEST_BYTES:
                if size > _MAX_REQUEST_BYTES:
                    self.reply(
                        413,
                        {
                            "error": "payload_too_large",
                            "max_bytes": _MAX_REQUEST_BYTES,
                            "hint": "Use image URLs or smaller/compressed base64 images.",
                        },
                    )
                else:
                    self.reply(400)
                return
            message = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeDecodeError):
            self.reply(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            return
        result = dispatch(message)
        self.reply(202 if result is None else 200, result)
