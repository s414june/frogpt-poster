"""One-time static Blob migration tool for fonts/references.

Run from repo root:
  PYTHONPATH=src python scripts/migrate_blob_static.py --check-access
  PYTHONPATH=src python scripts/migrate_blob_static.py --apply

- This script is NOT for per-build execution.
- --apply uploads only missing static objects, then verifies byte-for-byte SHA-256.
- It writes verified URLs back to assets/blob-manifest.json atomically.
"""
import argparse
import hashlib
import io
import json
import time
import traceback
from pathlib import Path
from PIL import Image
from gpt_package.blob_storage import SDKBackend, StorageError
from gpt_package.font_registry import FONT_FAMILIES

ROOT=Path(__file__).resolve().parents[1]


def _head_with_retry(backend, pathname, attempts=5, delay=0.4):
    last = None
    for idx in range(attempts):
        try:
            return backend.head(pathname)
        except StorageError as exc:
            last = exc
            if exc.code != "ASSET_NOT_FOUND" or idx == attempts - 1:
                raise
            time.sleep(delay)
    raise last  # pragma: no cover


def _read_with_retry(backend, pathname, limit, attempts=5, delay=0.4):
    last = None
    for idx in range(attempts):
        try:
            return backend.read(pathname, limit)
        except StorageError as exc:
            last = exc
            if exc.code != "ASSET_NOT_FOUND" or idx == attempts - 1:
                raise
            time.sleep(delay)
    raise last  # pragma: no cover

def inventory():
    fonts=[]
    for family,files in FONT_FAMILIES.items():
        for i,source in enumerate(files):
            fonts.append(dict(family=family,weight=700 if i else 400,source="assets/fonts/"+source,
                              license="assets/fonts/"+source.split("/")[0]+"/OFL.txt"))
    refs=json.loads((ROOT/"assets/reference-library/pexels/manifest.json").read_text())["items"]
    references=[dict(item, source=item["local_path"].replace("\\","/")) for item in refs
                if item.get("photographer","").strip().lower() not in ("","unknown")]
    for category, entries in (("fonts",fonts),("references",references)):
        for item in entries:
            data=(ROOT/item["source"]).read_bytes()
            sha=hashlib.sha256(data).hexdigest()
            name=(f'{item["family"]}/{item["weight"]}/{sha[:20]}.ttf' if category=="fonts"
                  else f'pexels/{item["id"]}-{sha[:20]}.jpg')
            item.update(pathname=f"frogpt/v1/static/{category}/{name}",sha256=sha,size_bytes=len(data),verified=False,url=None)
    return dict(version=1,fonts=fonts,references=references)


def check_access(backend=None):
    backend=backend or SDKBackend()
    probe_pathname=f"frogpt/v1/temp/assets/probe-{hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]}.png"
    out=io.BytesIO()
    Image.new("RGBA",(4,4),(0,0,0,0)).save(out,format="PNG")
    data=out.getvalue()
    backend.put(probe_pathname,data,"image/png",60)
    try:
        meta=_head_with_retry(backend, probe_pathname)
        read=_read_with_retry(backend, probe_pathname, len(data)+1)
        if read != data:
            raise RuntimeError("Blob probe read mismatch")
        return {"ok":True,"pathname":meta.pathname}
    finally:
        try:
            backend.delete([probe_pathname])
        except Exception:
            pass


def migrate(backend=None):
    result=inventory()
    backend=backend or SDKBackend()
    for category in ("fonts","references"):
        for entry in result[category]:
            try:
                _head_with_retry(backend, entry["pathname"])
            except StorageError as exc:
                if exc.code != "ASSET_NOT_FOUND":
                    raise
                backend.put(entry["pathname"],(ROOT/entry["source"]).read_bytes(),
                            "font/ttf" if category=="fonts" else "image/jpeg",31536000)
            data=_read_with_retry(backend, entry["pathname"], entry["size_bytes"]+1)
            if hashlib.sha256(data).hexdigest()!=entry["sha256"] or len(data)!=entry["size_bytes"]:
                raise RuntimeError(f"Static verification failed: {entry['pathname']}")
            meta=_head_with_retry(backend, entry["pathname"])
            entry.update(verified=True,url=meta.url)
    target=ROOT/"assets/blob-manifest.json"
    temp=target.with_suffix(".part")
    temp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    temp.replace(target)
    print(json.dumps({"verified":True,"fonts":len(result["fonts"]),"references":len(result["references"]),
                      "source_bytes":sum(i["size_bytes"] for c in ("fonts","references") for i in result[c])}))
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--check-access",action="store_true",help="Verify Blob write/read/delete access with a tiny probe.")
    parser.add_argument("--apply",action="store_true",help="Upload missing static objects and write verified manifest.")
    args=parser.parse_args()
    try:
        if args.check_access:
            print(json.dumps(check_access(),ensure_ascii=False))
        if args.apply:
            migrate()
        if not args.check_access and not args.apply:
            parser.print_help()
    except Exception:
        traceback.print_exc()
        raise
