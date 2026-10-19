"""Vercel Python serverless entrypoint without FastAPI dependency."""

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gpt_package.openai_tool import TOOL_NAME, build_tool_definition, handle_tool_call


sys.path.insert(0, str(Path(__file__).resolve().parent))
from mcp import handler as MCPHandler


class handler(MCPHandler):
    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _path(self) -> str:
        return urlparse(self.path).path.rstrip("/")

    def do_GET(self) -> None:
        path = self._path()
        if path in ("", "/"):
            self._json(
                200,
                {
                    "ok": True,
                    "service": "poster-tool-api",
                    "mcp_endpoint": "/mcp",
                    "note": "Use POST JSON-RPC for MCP calls.",
                },
            )
            return
        if path in ("/mcp", "/api/mcp", "/api/mcp.py"):
            self.reply(405)
            return
        if path in ("/api/health", "/health"):
            self._json(200, {"ok": True, "service": "poster-tool-api"})
            return
        if path in ("/api/tool", "/tool"):
            self._json(200, build_tool_definition())
            return
        self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        path = self._path()
        if path in ("", "/", "/mcp", "/api/mcp", "/api/mcp.py"):
            super().do_POST()
            return
        if path not in ("/api/poster", "/poster"):
            self._json(404, {"ok": False, "error": "not_found"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            self._json(400, {"ok": False, "error": "invalid_json"})
            return

        arguments = payload.get("arguments", {})
        result = handle_tool_call(arguments)
        self._json(200, {"tool_name": TOOL_NAME, "result": result})
