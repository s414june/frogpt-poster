"""Stateless Streamable HTTP MCP adapter for the existing poster scaffold."""
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
        "title": {"type": "string", "minLength": 1, "maxLength": 120},
        "body": {"type": "string", "minLength": 1, "maxLength": 4000},
        "width": {"type": "integer", "minimum": 256, "maximum": 4096},
        "height": {"type": "integer", "minimum": 256, "maximum": 4096},
    },
    "required": ["title", "body"],
    "additionalProperties": False,
}
TOOL = {
    "name": NAME,
    "description": "Prepare and validate a poster brief. Returns dimensions and image-source policy only. Rendering is not implemented: this tool does not generate an image or download URL. User attachments are not uploaded by this tool.",
    "inputSchema": SCHEMA,
    "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
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
        result["result"] = {"protocolVersion": version if version in versions else versions[0], "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "FroGPT Poster", "version": "0.1.0"}, "instructions": "Poster scaffold: prepare_poster validates a brief but does not render an image. Never claim an image was created."}
    elif method == "ping":
        result["result"] = {}
    elif method == "tools/list":
        result["result"] = {"tools": [TOOL]}
    elif method == "tools/call":
        args = params.get("arguments", {})
        if params.get("name") != NAME:
            result["error"] = {"code": -32602, "message": "Unknown tool"}
        elif (not isinstance(args, dict) or set(args) - set(SCHEMA["properties"])
              or any(not isinstance(args.get(k), str) for k in ("title", "body"))
              or any(type(args[k]) is not int for k in ("width", "height") if k in args)):
            result["error"] = {"code": -32602, "message": "Expected title/body strings and optional integer width/height; no file paths accepted."}
        else:
            output = handle_tool_call(args)
            output["rendered"] = False
            output["status"] = "brief_validated" if output["ok"] else "validation_failed"
            result["result"] = {"content": [{"type": "text", "text": json.dumps(output, ensure_ascii=False)}], "isError": not output["ok"]}
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
