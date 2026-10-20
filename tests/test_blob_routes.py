import http.client
import json
import subprocess
import sys
import threading
import unittest
from http.server import HTTPServer
from unittest.mock import patch
from api.index import handler

class RoutesTests(unittest.TestCase):
    def setUp(self):
        self.server=HTTPServer(("127.0.0.1",0),handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
    def request(self,path,body=None,method=None,headers=None):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port)
        conn.request(method or ("POST" if body else "GET"),path,
                     json.dumps(body) if body else None,headers or {"Content-Type":"application/json"})
        response=conn.getresponse();data=response.read();conn.close()
        return response.status,json.loads(data) if data else None
    def test_health_and_mcp_aliases(self):
        for path in ("/health","/api/health"):
            code,data=self.request(path);self.assertEqual(code,200);self.assertEqual(data["service"],"poster-tool-api")
        for path in ("/mcp","/api/mcp","/mcp/","/api/index","/api/index.py"):
            code,data=self.request(path,{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}})
            self.assertEqual(code,200);self.assertIn("protocolVersion",data["result"])
            code,data=self.request(path,{"jsonrpc":"2.0","id":2,"method":"tools/list"})
            self.assertEqual({t["name"] for t in data["result"]["tools"]},{"prepare_poster","store_poster_asset"})
        self.assertEqual(self.request("/mcp")[0],405)
        self.assertEqual(self.request("/mcp",method="OPTIONS")[0],204)
    def test_cleanup_auth_and_upload_disabled(self):
        with patch.dict("os.environ",{"CRON_SECRET":""}):
            self.assertEqual(self.request("/api/internal/blob-cleanup")[0],401)
        with patch.dict("os.environ",{"FROGPT_UPLOAD_ENABLED":"false"}):
            _,data=self.request("/mcp",{"jsonrpc":"2.0","id":1,"method":"tools/call",
                                      "params":{"name":"store_poster_asset","arguments":{"image_data_url":"x","role":"user","source":"user"}}})
            self.assertEqual(data["result"]["structuredContent"]["status"]["code"],"UPLOAD_DISABLED")
        with patch.dict("os.environ",{"CRON_SECRET":"test"}),patch("gpt_package.blob_cleanup.cleanup",return_value={"deleted":0}):
            self.assertEqual(self.request("/api/internal/blob-cleanup",headers={"Authorization":"Bearer test"})[1],{"deleted":0})
    def test_health_import_is_light(self):
        result=subprocess.run([sys.executable,"-c","import api.index,sys; assert 'PIL' not in sys.modules; assert 'vercel.blob' not in sys.modules"],capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_rest_rejects_arbitrary_urls(self):
        status,result=self.request("/api/poster",{"arguments":{"user_image_urls":["http://127.0.0.1/private"]}})
        self.assertEqual(status,422);self.assertEqual(result["status"]["code"],"INVALID_ASSET_REF")

    def test_rest_rejects_non_data_url_base64(self):
        status,result=self.request("/api/poster",{"arguments":{"user_image_base64":["iVBORw0KGgo="]}})
        self.assertEqual(status,422)
        self.assertEqual(result["status"]["code"],"INVALID_IMAGE")

    def test_api_assets_requires_bearer_and_calls_store(self):
        self.assertEqual(self.request("/api/assets",{"image_data_url":"x","role":"user","source":"user"})[0],401)
        with patch.dict("os.environ",{"FROGPT_ASSET_UPLOAD_TOKEN":"secret"}),patch(
            "gpt_package.blob_workflow.store_asset",
            return_value={"ok":True,"asset_ref":"frogpt/v1/temp/assets/2026/10/20/fake-user.png","http_status":200},
        ):
            code,data=self.request("/api/assets",{"image_data_url":"x","role":"user","source":"user"},
                                   headers={"Content-Type":"application/json","Authorization":"Bearer secret"})
            self.assertEqual(code,200)
            self.assertTrue(data["ok"])
