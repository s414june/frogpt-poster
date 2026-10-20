"""Build precheck: verify static manifest only.

Static migration is a one-time manual step:
  PYTHONPATH=src python scripts/migrate_blob_static.py --check-access
  PYTHONPATH=src python scripts/migrate_blob_static.py --apply
"""
import traceback
from pathlib import Path

try:
    exec(Path("scripts/verify_blob_manifest.py").read_text())
except Exception:
    traceback.print_exc()
    raise
