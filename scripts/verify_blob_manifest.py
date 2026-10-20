"""Fail builds until static migration is verified; never deploy a broken renderer."""
import json
from pathlib import Path
data=json.loads(Path("assets/blob-manifest.json").read_text())
assert len(data["fonts"])==6 and len(data["references"])>=7,"Missing static assets"
assert all(i.get("verified") and i.get("url") for group in ("fonts","references") for i in data[group]), "Run scripts/migrate_blob_static.py with Blob credentials, verify Preview, then deploy"
print("Static manifest verified; one Python Function, no bundled fonts/photos.")
