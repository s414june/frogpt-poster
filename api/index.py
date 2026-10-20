"""The only deployed Python Function. Health imports no Pillow, fonts or Blob SDK."""
import json
import hmac
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))

class handler(BaseHTTPRequestHandler):
    def _json(self,status,payload):
        data=json.dumps(payload,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def reply(self,status,payload=None):
        from gpt_package.mcp_http import handler as MCPHandler
        return MCPHandler.reply(self,status,payload)
    def _path(self):
        return urlparse(self.path).path.rstrip("/")
    def _authorized_asset_upload(self):
        expected=os.getenv("FROGPT_ASSET_UPLOAD_TOKEN","").strip()
        if not expected:
            return False
        auth=(self.headers.get("Authorization") or "").strip()
        if not auth.startswith("Bearer "):
            return False
        token=auth[7:].strip()
        return hmac.compare_digest(token, expected)
    def do_GET(self):
        path=self._path()
        if path=="":
            self.send_response(307);self.send_header("Location","/mcp")
            self.send_header("Content-Length","0");self.end_headers()
        elif path in ("/health","/api/health"):
            self._json(200,{"ok":True,"service":"poster-tool-api"})
        elif path in ("/tool","/api/tool"):
            from gpt_package.openai_tool import build_tool_definition
            self._json(200,build_tool_definition())
        elif path in ("/mcp","/api/mcp","/api/mcp.py","/api/index","/api/index.py"):
            self.reply(405)
        elif path=="/api/internal/blob-cleanup":
            from gpt_package.blob_cleanup import authorized,cleanup
            if not authorized(self.headers.get("Authorization")):
                self._json(401,{"ok":False,"status":{"code":"UNAUTHORIZED"}})
                return
            self._json(200,cleanup())
        else:
            self._json(404,{"ok":False,"error":"not_found"})
    def do_POST(self):
        path=self._path()
        if path in ("","/mcp","/api/mcp","/api/mcp.py","/api/index","/api/index.py"):
            from gpt_package.mcp_http import handler as MCPHandler
            return MCPHandler.do_POST(self)
        if path=="/api/assets":
            if not self._authorized_asset_upload():
                return self._json(401,{"ok":False,"status":{"code":"UNAUTHORIZED"}})
            try:
                size=int(self.headers.get("Content-Length","0"))
                if size<1 or size>16*1024*1024:
                    return self._json(413 if size>0 else 400,{"ok":False,"error":"invalid_body_size"})
                payload=json.loads(self.rfile.read(size))
                if not isinstance(payload,dict):
                    raise ValueError()
            except (ValueError,AttributeError,UnicodeDecodeError):
                return self._json(400,{"ok":False,"error":"invalid_json"})
            from gpt_package.blob_workflow import store_asset
            result=store_asset(payload)
            return self._json(result.get("http_status",200),result)
        if path not in ("/poster","/api/poster"):
            return self._json(404,{"ok":False,"error":"not_found"})
        try:
            size=int(self.headers.get("Content-Length","0"))
            if size<1 or size>16*1024*1024:
                return self._json(413 if size>0 else 400,{"ok":False,"error":"invalid_body_size"})
            payload=json.loads(self.rfile.read(size))
            args=payload.get("arguments",{})
            if not isinstance(args,dict): raise ValueError()
        except (ValueError,AttributeError,UnicodeDecodeError):
            return self._json(400,{"ok":False,"error":"invalid_json"})
        from gpt_package.mcp_http import _has_non_base64_image_inputs,_has_invalid_image_data_url_inputs,_run_staged_call,_compact_output
        if _has_non_base64_image_inputs(args):
            return self._json(422,{"ok":False,"status":{"code":"INVALID_ASSET_REF"}})
        if _has_invalid_image_data_url_inputs(args):
            return self._json(422,{"ok":False,"status":{"code":"INVALID_IMAGE"}})
        result=_run_staged_call(args,True)
        if result.get("stored"): result=_compact_output(result)
        self._json(result.get("http_status",200),{"tool_name":"prepare_poster","result":result})
    def do_DELETE(self):
        self.reply(405)
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow","GET, POST, OPTIONS")
        self.send_header("Content-Length","0")
        self.end_headers()
