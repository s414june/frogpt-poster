import base64
import hashlib
import io
import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image,ImageDraw,ImageFont
from gpt_package.blob_storage import *
from gpt_package.blob_cleanup import cleanup,authorized
from gpt_package.blob_workflow import prepare_inputs,run_with_storage,_recent
from gpt_package.font_provider import cached_static

def png(alpha=False):
    out=io.BytesIO()
    img=Image.new("RGBA" if alpha else "RGB",(480,640),(0,0,0,0) if alpha else "white")
    if alpha: ImageDraw.Draw(img).rectangle((0,0,100,100),fill=(0,0,0,100))
    img.save(out,format="PNG");return out.getvalue()

class Memory:
    def __init__(self,now):
        self.now=now;self.objects={};self.reads=0;self.puts=0;self.deleted=[];self.listing_done=False
    def put(self,ref,raw,mime,cache):
        self.puts+=1
        self.objects[ref]=(raw,SimpleNamespace(pathname=ref,uploaded_at=self.now(),size=len(raw),
                           url="https://test.public.blob.vercel-storage.com/"+ref,download_url="https://test/download",content_type=mime))
    def head(self,ref):
        if ref not in self.objects: raise StorageError("ASSET_NOT_FOUND",404)
        return self.objects[ref][1]
    def read(self,ref,limit):
        self.reads+=1;return self.objects[ref][0]
    def listing(self,prefix):
        self.listing_done=False
        for raw,m in list(self.objects.values()):
            if m.pathname.startswith(prefix): yield m
        self.listing_done=True
    def delete(self,refs):
        for ref in refs: self.objects.pop(ref,None);self.deleted.append(ref)

class BlobTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,20,tzinfo=timezone.utc)
        self.backend=Memory(lambda:self.now)
        self.repo=BlobRepository(self.backend,lambda:self.now)
        _recent.clear()
    def test_expiry_uses_uploaded_time_not_path_and_poster_is_independent(self):
        item=self.repo.put_asset(png())
        poster=self.repo.put_poster(png())
        self.now+=timedelta(hours=24)
        with self.assertRaises(StorageError) as e:self.repo.get_asset(item.asset_ref)
        self.assertEqual(e.exception.code,"ASSET_EXPIRED")
        self.repo.delete_many([item.asset_ref])
        self.assertEqual(self.repo.metadata(poster.asset_ref,POSTERS).pathname,poster.asset_ref)
        self.assertTrue(self.backend.read(poster.asset_ref,100000))
        self.now+=timedelta(hours=48)
        with self.assertRaises(StorageError) as e:self.repo.metadata(poster.asset_ref,POSTERS)
        self.assertEqual(e.exception.code,"POSTER_EXPIRED")
    def test_rejects_ssrf_and_static_refs_before_io(self):
        for ref in ("https://example.com/a.png","../x",ASSETS+"%2e", "frogpt/v1/static/fonts/x.ttf"):
            with self.assertRaises(StorageError):self.repo.get_asset(ref)
        self.assertEqual(self.backend.reads,0)
    def test_sanitize_and_geometry_alpha(self):
        raw,ext=validate_image(png(True),"geometry")
        img=Image.open(io.BytesIO(raw))
        self.assertEqual(img.getpixel((0,0)),(0,0,0,100))
        self.assertEqual(img.getpixel((200,200)),(0,0,0,0))
        with self.assertRaises(StorageError):validate_image(png(),"geometry")
        with self.assertRaises(StorageError):validate_image(b"not png")
        with self.assertRaises(StorageError):validate_image(b"x"*5242881)
    def test_ref_reuse_does_not_put_or_renew_and_conflicts_reject(self):
        item=self.repo.put_asset(png(),"background")
        before=self.backend.puts
        args,refs=prepare_inputs({"asset_refs":{"background":item.asset_ref}},self.repo)
        self.assertEqual(self.backend.puts,before)
        self.assertEqual(refs["background"],item.asset_ref)
        self.assertTrue(args["user_image_base64"][0].startswith("data:image/png"))
        with self.assertRaises(StorageError) as e:
            prepare_inputs({"asset_refs":refs,"user_image_base64":["data:image/png;base64,AAAA"]},self.repo)
        self.assertEqual(e.exception.code,"AMBIGUOUS_IMAGE_SOURCE")
    def test_cleanup_pagination_and_static_protection(self):
        old=[self.repo.put_asset(png()).asset_ref for _ in range(205)]
        static="frogpt/v1/static/fonts/test.ttf";self.backend.put(static,b"x","font/ttf",0)
        self.now+=timedelta(hours=25)
        fresh=self.repo.put_asset(png()).asset_ref
        out=cleanup(self.repo)
        self.assertEqual(out["deleted"],205)
        self.assertIn(static,self.backend.objects);self.assertIn(fresh,self.backend.objects)
        self.assertEqual(cleanup(self.repo)["deleted"],0)
    def test_cleanup_failure_partial_and_auth_fail_closed(self):
        self.repo.put_asset(png());self.now+=timedelta(days=2)
        with patch.object(self.backend,"delete",side_effect=StorageError("BLOB_UNAVAILABLE")):
            self.assertEqual(cleanup(self.repo)["failed"],1)
        self.assertTrue(cleanup(self.repo,max_scan=1)["partial"])
        with patch.dict("os.environ",{"CRON_SECRET":""}):self.assertFalse(authorized("Bearer "))
        with patch.dict("os.environ",{"CRON_SECRET":"test"}):
            self.assertTrue(authorized("Bearer test"));self.assertFalse(authorized("Bearer wrong"))
    def test_font_hash_cache_and_corruption_rejection(self):
        raw=b"font fixture";sha=hashlib.sha256(raw).hexdigest()
        e=dict(pathname="frogpt/v1/static/fonts/sans/400/"+sha[:20]+".ttf",sha256=sha,size_bytes=len(raw),verified=True,url="test")
        self.backend.put(e["pathname"],raw,"font/ttf",0)
        with tempfile.TemporaryDirectory() as tmp:
            a=cached_static(e,"fonts",self.backend,tmp);b=cached_static(e,"fonts",self.backend,tmp)
            self.assertEqual(a,b);self.assertEqual(self.backend.reads,1)
            Path(a).unlink();self.backend.objects[e["pathname"]]=(b"bad",None)
            with self.assertRaises(StorageError) as err:cached_static(e,"fonts",self.backend,tmp)
            self.assertEqual(err.exception.code,"FONT_UNAVAILABLE")
    def test_staged_refs_require_digest_approval_and_deliver_url(self):
        from gpt_package.mcp_http import _run_staged_call
        env={"FROGPT_BLOB_ENABLED":"true","FROGPT_UPLOAD_ENABLED":"true","FROGPT_FONT_SOURCE":"local"}
        with patch.dict("os.environ",env),patch("gpt_package.blob_workflow.BlobRepository",return_value=self.repo):
            first=_run_staged_call(dict(preview_only=True,generated_background_base64="data:image/png;base64,"+base64.b64encode(png()).decode(),
                    generated_background_text_free_confirmed=True,title="Pure",body="Daily"),True)
            self.assertEqual(first["status"]["code"],"awaiting_typography_confirmation")
            self.assertTrue(first["stored"])
            count=self.backend.puts
            second=_run_staged_call(dict(preview_only=True,asset_refs={"draft":first["draft_ref"]},title="Pure",body="Daily",
                       generated_background_text_free_confirmed=True,typography_confirmed=True,approved_draft_sha256="bad"),True)
            self.assertEqual(second["status"]["code"],"awaiting_typography_confirmation")
            self.assertEqual(self.backend.puts,count)
            done=_run_staged_call(dict(preview_only=True,asset_refs={"draft":first["draft_ref"]},title="Pure",body="Daily",
                       generated_background_text_free_confirmed=True,typography_confirmed=True,approved_draft_sha256=first["draft_image_sha256"]),True)
            self.assertTrue(done["rendered"],done);self.assertTrue(done["stored"],done)
            self.assertNotIn("output_image_base64",done)
            self.assertEqual(done["ttl_seconds"],259200)
            self.assertEqual(self.backend.puts,count+1)
    def test_storage_failure_never_claims_stored(self):
        with patch.dict("os.environ",{"FROGPT_BLOB_ENABLED":"true","FROGPT_UPLOAD_ENABLED":"true"}),patch("gpt_package.blob_workflow.BlobRepository",return_value=self.repo):
            with patch.object(self.repo,"put_asset",side_effect=StorageError("STORAGE_LIMIT_REACHED")):
                result=run_with_storage({"generated_background_base64":"data:image/png;base64,"+base64.b64encode(png()).decode()},True,lambda a,b:None)
        self.assertFalse(result["stored"]);self.assertEqual(result["status"]["code"],"STORAGE_LIMIT_REACHED")
