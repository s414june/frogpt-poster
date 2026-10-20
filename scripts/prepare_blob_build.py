"""Preview-only migration smoke test; production requires a verified manifest."""
import json
import os
from pathlib import Path
from migrate_blob_static import migrate
from gpt_package.blob_storage import BlobRepository
data=json.loads(Path("assets/blob-manifest.json").read_text())
ready=all(e.get("verified") for c in ("fonts","references") for e in data[c])
if not ready:
    if os.getenv("VERCEL_ENV")!="preview":
        raise SystemExit("STATIC_MIGRATION_REQUIRED: verify assets in Preview before production")
    # Only a newly created, synthetic test asset is removed. Never old/static blobs.
    import io
    from PIL import Image
    out=io.BytesIO();Image.new("RGBA",(8,8),(0,0,0,0)).save(out,format="PNG")
    repo=BlobRepository()
    item=repo.put_asset(out.getvalue(),"user","gpt")
    try:
        assert repo.get_asset(item.asset_ref)
    finally:
        repo.delete_many([item.asset_ref])
    data=migrate()
    # Static font/reference metadata only. Never log temp URLs, credentials or bytes.
    print("FROGPT_STATIC_MANIFEST="+json.dumps(data,ensure_ascii=False,separators=(",",":")))
exec(Path("scripts/verify_blob_manifest.py").read_text())
