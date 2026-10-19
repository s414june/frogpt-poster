"""Stateless Streamable HTTP MCP adapter for poster rendering."""
import json
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gpt_package.openai_tool import handle_tool_call

NAME = "prepare_poster"
SCHEMA = {
    "type": "object",
    "properties": {
        "intake_confirmed": {"type": "boolean"},
        "poster_request": {"type": "object"},
        "title": {"type": "string", "minLength": 1, "maxLength": 120},
        "body": {"type": "string", "minLength": 1, "maxLength": 4000},
        "width": {"type": "integer", "minimum": 256, "maximum": 4096},
        "height": {"type": "integer", "minimum": 256, "maximum": 4096},
        "primary_color": {"type": "string"},
        "secondary_color": {"type": "string"},
        "accent_color": {"type": "string"},
        "subject": {"type": "string"},
        "user_image_base64": {"type": "array", "items": {"type": "string"}},
        "show_design_guide": {"type": "boolean"},
    },
    "required": [],
    "additionalProperties": False,
}
TOOL = {
    "name": NAME,
    "description": "Intake-first poster tool. Ask intake questions first; render only when intake_confirmed=true.",
    "inputSchema": SCHEMA,
    "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
}

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
        result["result"] = {"protocolVersion": version if version in versions else versions[0], "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "FroGPT Poster", "version": "0.2.1"}, "instructions": "Always run intake first. If intake_confirmed is not true, call the tool to get intake_questions and ask the user. Only render after user confirms and intake_confirmed=true."}
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
            intake_confirmed = bool(args.get("intake_confirmed", False))
            call_args = dict(args)
            if not intake_confirmed:
                call_args["request_intake_only"] = True
                call_args["show_design_guide"] = True
            output = handle_tool_call(call_args)
            if not intake_confirmed and output.get("status", {}).get("code") != "needs_input":
                output["status"] = {
                    "code": "needs_input",
                    "message": "intake_questions_required_before_render",
                }
                output["next_action"] = "ask_user_intake_questions"
                output["rendered"] = False
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
                            "尚未渲染海報。請先向使用者詢問以下問題並收集答案，再以 intake_confirmed=true 重新呼叫工具：\n"
                            + "\n".join(question_lines)
                        ),
                    }
                )
            if output.get("ok") and output.get("rendered") and output.get("output_image_base64"):
                # 1) Rendered image first for immediate preview
                content.append(
                    {
                        "type": "image",
                        "data": output["output_image_base64"],
                        "mimeType": output.get("output_mime_type", "image/png"),
                    }
                )
                # 2) Download hint second
                filename = output.get("output_filename", "poster.png")
                download_url = output.get("output_download_data_url", output.get("output_image_data_url", ""))
                content.append(
                    {
                        "type": "text",
                        "text": (
                            f"下載檔名: {filename}\n"
                            f"下載連結(data URL): {download_url}"
                        ),
                    }
                )
            # 3) Structured/text details last
            content.append({"type": "text", "text": json.dumps(output, ensure_ascii=False)})
            result["result"] = {
                "content": content,
                "structuredContent": output,
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
            if size <= 0 or size > 65536:
                self.reply(413 if size > 65536 else 400)
                return
            message = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeDecodeError):
            self.reply(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            return
        result = dispatch(message)
        self.reply(202 if result is None else 200, result)
