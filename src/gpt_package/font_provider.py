"""Manifest-only lazy font/reference downloads with hash-addressed atomic cache."""
import hashlib
import json
import logging
import os
import time
import uuid
from pathlib import Path
from .blob_storage import SDKBackend, StorageError

ROOT=Path(__file__).resolve().parents[2]
MANIFEST=ROOT/"assets/blob-manifest.json"
log=logging.getLogger(__name__)

def blob_fonts():
    source=os.getenv("FROGPT_FONT_SOURCE", "blob" if os.getenv("VERCEL") else "local")
    if os.getenv("VERCEL_ENV") == "production" and source != "blob":
        raise StorageError("FONT_UNAVAILABLE")
    return source == "blob"

def manifest():
    try:
        return json.loads(MANIFEST.read_text())
    except (OSError,ValueError):
        raise StorageError("FONT_UNAVAILABLE") from None

def font_uri(original):
    return "blobfont://"+original

def materialize_font(value):
    if not str(value).startswith("blobfont://"):
        return value
    original=value.removeprefix("blobfont://")
    entries=manifest().get("fonts",[])
    entry=next((e for e in entries if e["source"] == "assets/fonts/"+original),None)
    if not entry:
        raise StorageError("FONT_UNAVAILABLE")
    return cached_static(entry,"fonts")

def cached_static(entry, category, backend=None, cache_root=None):
    code="FONT_UNAVAILABLE" if category == "fonts" else "BLOB_UNAVAILABLE"
    prefix="frogpt/v1/static/"+category+"/"
    pathname=entry.get("pathname","")
    sha=entry.get("sha256","")
    import re
    if (not pathname.startswith(prefix) or ".." in pathname or not re.fullmatch("[a-f0-9]{64}",sha)
            or not entry.get("verified") or not entry.get("url")):
        raise StorageError(code)
    # Cache by content, never by user-provided path. No CDN URL accepted from requests.
    root=Path(cache_root or "/tmp/frogpt")/category
    path=root/(sha+(".ttf" if category=="fonts" else ".jpg"))
    size=entry["size_bytes"]
    if path.is_file() and path.stat().st_size == size:
        log.info("%s_cache.hit bytes=%d",category,size)
        return str(path)
    start=time.monotonic()
    backend=backend or SDKBackend()
    try:
        raw=backend.read(pathname,min(40*1024*1024,size+1))
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != sha:
            raise StorageError(code)
        root.mkdir(parents=True,exist_ok=True)
        part=path.with_name(path.name+".part-"+uuid.uuid4().hex)
        try:
            part.write_bytes(raw)
            os.replace(part,path)
        finally:
            part.unlink(missing_ok=True)
        log.info("%s_cache.miss bytes=%d duration_ms=%d",category,size,(time.monotonic()-start)*1000)
        return str(path)
    except Exception:
        raise StorageError(code) from None

class FontProvider:
    def get_path(self,family,weight=400):
        from .font_registry import resolve_font_weight
        _,path=resolve_font_weight(family,weight)
        return materialize_font(path)

def reference_entry(identifier):
    return next((e for e in manifest().get("references",[]) if e["id"]==identifier),None)

def reference_path(identifier):
    entry=reference_entry(identifier)
    if not entry:
        raise StorageError("ASSET_NOT_FOUND",404)
    return cached_static(entry,"references")
