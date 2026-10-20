"""Public Blob storage; references are server-owned paths, never client URLs."""
from __future__ import annotations
import base64
import hashlib
import io
import logging
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from .errors import PosterError

ASSETS = "frogpt/v1/temp/assets/"
POSTERS = "frogpt/v1/temp/posters/"
ROLES = ("background", "subject", "geometry", "reference", "draft", "user")
REF = re.compile(r"frogpt/v1/temp/(assets|posters)/\d{4}/\d{2}/\d{2}/[0-9a-f]{32}(?:-(background|subject|geometry|reference|draft|user))?\.(png|jpeg|webp)")
log = logging.getLogger(__name__)

class StorageError(PosterError):
    def __init__(self, code, status=503):
        super().__init__(code)
        self.code, self.status = code, status
    def result(self, rendered=False):
        return dict(ok=False, rendered=rendered, stored=False, http_status=self.status,
                    status={"code": self.code, "message": self.code})

def enabled():
    return os.getenv("FROGPT_BLOB_ENABLED", "false").lower() == "true"

def ttl(prefix):
    name, default = ("FROGPT_ASSET_TTL_SECONDS", 86400) if prefix == ASSETS else ("FROGPT_POSTER_TTL_SECONDS", 259200)
    return max(1, min(default, int(os.getenv(name, str(default)))))

def utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise StorageError("BLOB_UNAVAILABLE")
    return value.astimezone(timezone.utc)

def validate_ref(ref, prefix=ASSETS):
    if not isinstance(ref, str) or not REF.fullmatch(ref) or not ref.startswith(prefix):
        raise StorageError("INVALID_ASSET_REF", 422)
    if prefix == ASSETS and not REF.fullmatch(ref).group(2):
        raise StorageError("INVALID_ASSET_REF", 422)
    if prefix == POSTERS and (REF.fullmatch(ref).group(2) or not ref.endswith(".png")):
        raise StorageError("INVALID_ASSET_REF", 422)
    return ref

def validate_image(raw, role="user"):
    from PIL import Image, ImageOps
    maximum = min(5242880, int(os.getenv("FROGPT_MAX_IMAGE_BYTES", "5242880")))
    if not raw or len(raw) > maximum:
        raise StorageError("FILE_TOO_LARGE" if raw else "INVALID_IMAGE", 413 if raw else 400)
    try:
        with Image.open(io.BytesIO(raw)) as img:
            if img.format not in ("PNG", "JPEG", "WEBP") or getattr(img, "n_frames", 1) != 1:
                raise StorageError("INVALID_IMAGE", 400)
            if max(img.size) > 4096 or img.width * img.height > min(16000000, int(os.getenv("FROGPT_MAX_IMAGE_PIXELS", "16000000"))):
                raise StorageError("FILE_TOO_LARGE", 413)
            if role == "geometry" and (img.format != "PNG" or "A" not in img.getbands()):
                raise StorageError("INVALID_IMAGE", 400)
            img.load()
            if role == "geometry" and img.getchannel("A").getextrema()[0] == 255:
                raise StorageError("INVALID_IMAGE", 400)
            fmt = img.format
            clean = ImageOps.exif_transpose(img).convert("RGBA" if "A" in img.getbands() else "RGB")
            clean.info.clear()
            out = io.BytesIO()
            clean.save(out, format=fmt, **({"quality": 95} if fmt in ("JPEG", "WEBP") else {}))
            data = out.getvalue()
            if len(data) > maximum:
                raise StorageError("FILE_TOO_LARGE", 413)
            return data, {"PNG":"png","JPEG":"jpeg","WEBP":"webp"}[fmt]
    except StorageError:
        raise
    except Exception:
        raise StorageError("INVALID_IMAGE", 400) from None

def decode_data_url(value):
    if not isinstance(value, str) or len(value) > 7_000_000:
        raise StorageError("FILE_TOO_LARGE", 413)
    match = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=\r\n]+)", value)
    if not match:
        raise StorageError("INVALID_IMAGE", 400)
    try:
        return base64.b64decode(match[2], validate=True)
    except ValueError:
        raise StorageError("INVALID_IMAGE", 400) from None

@dataclass
class StoredAsset:
    asset_ref: str
    url: str
    download_url: str
    uploaded_at: str
    expires_at: str
    ttl_seconds: int
    content_type: str
    size_bytes: int
    sha256: str
    def to_dict(self):
        return asdict(self)

def sdk_session():
    from vercel.api import session
    import httpx
    return session(httpx_client_factory=lambda: httpx.Client(timeout=httpx.Timeout(8,connect=3),follow_redirects=False))

class SDKBackend:
    """Official vercel 0.12 / vercel-blob 0.5 synchronous API."""
    def _call(self, method, *args, **kwargs):
        from vercel.blob import sync
        try:
            with sdk_session():
                return getattr(sync, method)(*args, **kwargs)
        except Exception as exc:
            name = type(exc).__name__
            code, status = ("ASSET_NOT_FOUND", 404) if "NotFound" in name else ("BLOB_UNAVAILABLE", 503)
            if "Suspended" in name or "Quota" in name or "LimitReached" in name:
                code = "STORAGE_LIMIT_REACHED"
            if "RateLimited" in name:
                code, status = "RATE_LIMITED", 429
            raise StorageError(code, status) from None
    def head(self, ref):
        return self._call("head_blob", ref)
    def put(self, ref, data, content_type, cache):
        return self._call("put_blob", ref, data, access="public", content_type=content_type,
                          add_random_suffix=False, allow_overwrite=False, cache_control_max_age=cache)
    def read(self, ref, limit):
        from vercel.blob import sync
        try:
            with sdk_session(), sync.stream_blob(ref, access="public") as download:
                if download.metadata.size and download.metadata.size > limit:
                    raise StorageError("FILE_TOO_LARGE", 413)
                buf = bytearray()
                for chunk in download:
                    buf.extend(chunk)
                    if len(buf) > limit:
                        raise StorageError("FILE_TOO_LARGE", 413)
                return bytes(buf)
        except StorageError:
            raise
        except Exception:
            raise StorageError("BLOB_UNAVAILABLE") from None
    def listing(self, prefix):
        from vercel.blob import sync
        try:
            with sdk_session():
                yield from sync.query_blobs(prefix=prefix, page_size=100)
        except Exception:
            raise StorageError("BLOB_UNAVAILABLE") from None
    def delete(self, refs):
        return self._call("delete_blob", refs)

class BlobRepository:
    def __init__(self, backend=None, now=None):
        self.backend = backend or SDKBackend()
        self.now = now or (lambda: datetime.now(timezone.utc))
    def put_asset(self, image_bytes, role="user", source="user"):
        if role not in ROLES or source not in ("user", "gpt"):
            raise StorageError("INVALID_IMAGE", 400)
        raw, ext = validate_image(image_bytes, role)
        path = f"{ASSETS}{self.now():%Y/%m/%d}/{uuid.uuid4().hex}-{role}.{ext}"
        return self._put(path, raw, "image/"+ext, ASSETS)
    def put_poster(self, png_bytes):
        # A final independently flattened PNG is allowed to exceed the input limit.
        from PIL import Image
        with Image.open(io.BytesIO(png_bytes)) as img:
            if img.format != "PNG":
                raise StorageError("INVALID_IMAGE", 400)
            img.load()
        if len(png_bytes) > 64 * 1024 * 1024:
            raise StorageError("FILE_TOO_LARGE", 413)
        return self._put(f"{POSTERS}{self.now():%Y/%m/%d}/{uuid.uuid4().hex}.png", png_bytes, "image/png", POSTERS)
    def _put(self, ref, raw, mime, prefix):
        start=time.monotonic()
        self.backend.put(ref, raw, mime, 60)
        meta=self.backend.head(ref)  # PUT does not include authoritative uploaded_at.
        uploaded=utc(meta.uploaded_at)
        log.info("storage.put bytes=%d duration_ms=%d",len(raw),(time.monotonic()-start)*1000)
        return StoredAsset(ref,meta.url,meta.download_url,uploaded.isoformat(),
                           (uploaded+timedelta(seconds=ttl(prefix))).isoformat(),ttl(prefix),
                           mime,len(raw),hashlib.sha256(raw).hexdigest())
    def get_asset(self, asset_ref, verify_ttl=True):
        validate_ref(asset_ref)
        meta=self.metadata(asset_ref)
        raw=self.backend.read(asset_ref, 5242880)
        log.info("storage.get bytes=%d", len(raw))
        return raw
    def metadata(self, ref, prefix=ASSETS):
        validate_ref(ref,prefix)
        meta=self.backend.head(ref)
        if meta.pathname != ref:
            raise StorageError("INVALID_ASSET_REF",422)
        if self.now() >= utc(meta.uploaded_at)+timedelta(seconds=ttl(prefix)):
            raise StorageError("ASSET_EXPIRED" if prefix == ASSETS else "POSTER_EXPIRED",410)
        return meta
    def delete_many(self, refs):
        for ref in refs:
            validate_ref(ref,ASSETS if ref.startswith(ASSETS) else POSTERS)
        self.backend.delete(refs)
