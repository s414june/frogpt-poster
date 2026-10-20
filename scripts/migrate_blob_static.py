"""Explicit migration; preserves original binary bytes and never deletes old objects.
Run from repo root: PYTHONPATH=src python scripts/migrate_blob_static.py [--plan]
Requires a linked Store and usable OIDC or existing read-write credential.
"""
import argparse
import hashlib
import json
from pathlib import Path
from gpt_package.blob_storage import SDKBackend, StorageError
from gpt_package.font_registry import FONT_FAMILIES

ROOT=Path(__file__).resolve().parents[1]

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

def migrate(plan=False,backend=None):
    result=inventory()
    backend=backend or SDKBackend()
    for category in ("fonts","references"):
        for entry in result[category]:
            if not plan:
                try:
                    backend.head(entry["pathname"])
                except StorageError as exc:
                    if exc.code != "ASSET_NOT_FOUND": raise
                    backend.put(entry["pathname"],(ROOT/entry["source"]).read_bytes(),
                                "font/ttf" if category=="fonts" else "image/jpeg",31536000)
                data=backend.read(entry["pathname"],entry["size_bytes"]+1)
                if hashlib.sha256(data).hexdigest()!=entry["sha256"] or len(data)!=entry["size_bytes"]:
                    raise RuntimeError("Static verification failed")
                meta=backend.head(entry["pathname"])
                entry.update(verified=True,url=meta.url)
    target=ROOT/"assets/blob-manifest.json"
    temp=target.with_suffix(".part")
    temp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    temp.replace(target)
    print(json.dumps({"verified":not plan,"fonts":len(result["fonts"]),"references":len(result["references"]),
                      "source_bytes":sum(i["size_bytes"] for c in ("fonts","references") for i in result[c])}))
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--plan",action="store_true")
    migrate(p.parse_args().plan)
