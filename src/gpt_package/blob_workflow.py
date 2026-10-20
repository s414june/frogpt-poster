"""Transport bridge: refs resolve to existing rendering inputs; approval stays in MCP."""
import base64
import copy
import hashlib
import threading
import time
import os
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from .blob_storage import BlobRepository, StorageError, enabled, decode_data_url, validate_ref

PUBLIC_NOTICE="Public Blob 連結持有者均可查看；素材可編輯 24 小時，成品可下載 72 小時。每日清理不保證 URL 到期立即失效，敏感照片不適用。"
_semaphore=threading.BoundedSemaphore(2)
_lock=threading.Lock()
_recent=deque()

@contextmanager
def write_guard():
    if not enabled() or os.getenv("FROGPT_UPLOAD_ENABLED","true" if os.getenv("VERCEL_ENV")=="preview" else "false").lower()!="true":
        raise StorageError("UPLOAD_DISABLED",403)
    with _lock:
        now=time.monotonic()
        while _recent and _recent[0]<now-60: _recent.popleft()
        if len(_recent)>=10: raise StorageError("RATE_LIMITED",429)
        _recent.append(now)
    if not _semaphore.acquire(blocking=False): raise StorageError("RATE_LIMITED",429)
    try: yield
    finally: _semaphore.release()

STORE_TOOL={
    "name":"store_poster_asset",
    "description":"Store actual PNG/JPEG/WebP bytes for 24h and reuse asset_ref. "+PUBLIC_NOTICE+" 無法取得附件 bytes 時停止，回報附件讀取失敗，尚未傳入套件；不可假造 Base64。",
    "inputSchema":{"type":"object","properties":{
        "image_data_url":{"type":"string"},
        "role":{"type":"string","enum":["background","subject","geometry","reference","draft","user"]},
        "source":{"type":"string","enum":["user","gpt"]}},
        "required":["image_data_url","role","source"],"additionalProperties":False},
    "annotations":{"readOnlyHint":False,"destructiveHint":False,"idempotentHint":False,"openWorldHint":True}
}
ASSET_REFS_SCHEMA={"type":"object","properties":{
    "background":{"type":"string"},"subjects":{"type":"array","maxItems":4,"items":{"type":"string"}},
    "geometry":{"type":"string"},"references":{"type":"array","maxItems":4,"items":{"type":"string"}},
    "draft":{"type":"string"}},"additionalProperties":False}

def store_asset(args):
    try:
        if not isinstance(args,dict) or set(args)!=set(("image_data_url","role","source")):
            raise StorageError("INVALID_IMAGE",400)
        with write_guard():
            item=BlobRepository().put_asset(decode_data_url(args["image_data_url"]),args["role"],args["source"])
        return dict(ok=True,stored=True,**item.to_dict(),public_notice=PUBLIC_NOTICE)
    except StorageError as exc:
        return exc.result()

def prepare_inputs(arguments,repo):
    args=copy.deepcopy(arguments)
    payload=args.setdefault("poster_request",{})
    refs=args.get("asset_refs",payload.get("asset_refs",{}))
    if not isinstance(refs,dict) or set(refs)-set(ASSET_REFS_SCHEMA["properties"]):
        raise StorageError("INVALID_ASSET_REF",422)
    assets=payload.get("assets") or {}
    # Nested generated/reference fields live on poster_request, user/subject/geometry under assets.
    fields={"background":"user_image_base64","subjects":"subject_image_base64",
            "geometry":"geometry_image_base64","references":"reference_image_base64",
            "draft":"generated_background_base64"}
    roles={"background":"background","subjects":"subject","geometry":"geometry","references":"reference","draft":"draft"}
    # Validate the entire batch before any upload/download.
    total=0
    for role,field in fields.items():
        nested=payload if role in ("references","draft") else assets
        direct=args.get(field)
        embedded=nested.get(field)
        refvalue=refs.get(role)
        if (direct and embedded) or (refvalue and (direct or embedded)):
            raise StorageError("AMBIGUOUS_IMAGE_SOURCE",422)
        value=direct or embedded
        if role in ("subjects","references") and refvalue is not None and not isinstance(refvalue,list):
            raise StorageError("INVALID_ASSET_REF",422)
        if role in ("background","geometry","draft") and refvalue is not None and not isinstance(refvalue,str):
            raise StorageError("INVALID_ASSET_REF",422)
        ids=refvalue if role in ("subjects","references") else ([refvalue] if refvalue else [])
        for ref in ids or []: validate_ref(ref)
        values=value if role in ("background","subjects","references") else ([value] if value else [])
        if values and not isinstance(values,list): raise StorageError("INVALID_IMAGE",400)
        if len(values or [])>4 or len(ids or [])>4: raise StorageError("FILE_TOO_LARGE",413)
        total+=len(values or [])+len(ids or [])
    if total>8: raise StorageError("FILE_TOO_LARGE",413)
    if (refs.get("draft") or args.get("generated_background_base64") or payload.get("generated_background_base64")) and (refs.get("background") or args.get("user_image_base64") or assets.get("user_image_base64")):
        raise StorageError("AMBIGUOUS_IMAGE_SOURCE",422)
    result_refs={}
    count=0
    for role,field in fields.items():
        nested=payload if role in ("references","draft") else assets
        value=args.get(field,nested.get(field))
        refvalue=refs.get(role)
        if value and refvalue:
            raise StorageError("AMBIGUOUS_IMAGE_SOURCE",422)
        many=role in ("background","subjects","references")
        values=(value if many else [value]) if value else []
        ids=(refvalue if role in ("subjects","references") else [refvalue]) if refvalue else []
        if not isinstance(values,list) or not isinstance(ids,list) or len(values)>4 or len(ids)>4:
            raise StorageError("INVALID_IMAGE",400)
        count+=len(values)+len(ids)
        if count>8: raise StorageError("FILE_TOO_LARGE",413)
        resolved=[]
        saved=[]
        for ref in ids:
            validate_ref(ref)
            raw=repo.get_asset(ref)
            resolved.append("data:image/"+ref.rsplit(".",1)[-1]+";base64,"+base64.b64encode(raw).decode())
            saved.append(ref)
        for value in values:
            item=repo.put_asset(decode_data_url(value),roles[role],"gpt" if role in ("geometry","draft") or (role=="subjects" and args.get("subject_source")=="ai_generated") else "user")
            # Reload sanitized bytes, so approved digest matches future ref reuse.
            raw=repo.get_asset(item.asset_ref)
            resolved.append("data:"+item.content_type+";base64,"+base64.b64encode(raw).decode())
            saved.append(item.asset_ref)
        if resolved:
            if role == "background":
                args["image_role_mode"] = "background"
            if role == "subjects" and ids and "-gpt-subject." in ids[0]:
                args["subject_source"] = "ai_generated"
            args[field]=resolved if many else resolved[0]
            if role=="background" and len(saved)>1:
                raise StorageError("INVALID_IMAGE",400)
            result_refs[role]=saved if role in ("subjects","references") else saved[0]
    if result_refs.get("draft") and result_refs.get("background"):
        raise StorageError("AMBIGUOUS_IMAGE_SOURCE",422)
    # No refs are passed to generic local path handling.
    args.pop("asset_refs",None)
    payload.pop("asset_refs",None)
    return args,result_refs

def run_with_storage(args,intake_completed,render):
    if not enabled():
        if args.get("asset_refs") or (args.get("poster_request") or {}).get("asset_refs"):
            return StorageError("BLOB_UNAVAILABLE").result()
        return render(args,intake_completed)
    if not intake_completed:
        return render(args,intake_completed)
    output=None
    try:
        with write_guard():
            repo=BlobRepository()
            resolved,refs=prepare_inputs(args,repo)
            start=time.monotonic()
            output=render(resolved,intake_completed)
            output["asset_refs"]=refs
            output["stored"]=False
            if output.get("pipeline_stage")=="awaiting_typography_confirmation":
                ref=refs.get("draft")
                if ref:
                    meta=repo.metadata(ref)
                    output.update(draft_ref=ref,image_url=meta.url,download_url=meta.download_url,stored=True,
                                  expires_at=(meta.uploaded_at+__import__("datetime").timedelta(seconds=86400)).isoformat())
                    output["retry_arguments_hint"]={"asset_refs":{"draft":ref},
                        "generated_background_text_free_confirmed":True,"typography_confirmed":True,
                        "approved_draft_sha256":output["draft_image_sha256"]}
            elif output.get("rendered"):
                path=Path(output["output_path"])
                try:
                    poster=repo.put_poster(path.read_bytes())
                finally:
                    path.unlink(missing_ok=True)
                info=poster.to_dict()
                output.update(stored=True,poster_ref=info.pop("asset_ref"),image_url=info.pop("url"),**info)
            if output.get("stored"):
                output["public_notice"]=PUBLIC_NOTICE
                for key in ("output_image_base64","output_image_data_url","output_download_data_url",
                            "output_preview_data_url","output_preview_markdown","result_json"):
                    output.pop(key,None)
                preview=output.get("output_preview_base64","")
                if len(preview)>200_000: output.pop("output_preview_base64",None)
            return output
    except StorageError as exc:
        result=exc.result(rendered=bool(output and output.get("rendered")))
        # Never leak input URLs, credentials or full bytes through errors.
        return result
