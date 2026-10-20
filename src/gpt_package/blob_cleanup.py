"""Bounded daily cleanup. Finish enumeration before deleting to preserve cursors."""
import hmac
import os
import time
from datetime import timedelta
from .blob_storage import ASSETS, POSTERS, BlobRepository, StorageError, ttl, utc, validate_ref

def authorized(header):
    secret=os.getenv("CRON_SECRET","")
    return bool(secret) and hmac.compare_digest(header or "", "Bearer "+secret)

def cleanup(repo=None, max_scan=2000, seconds=45):
    repo=repo or BlobRepository()
    start=time.monotonic()
    report=dict(scanned=0,expired=0,deleted=0,failed=0,partial=False,duration_ms=0)
    pending=[]
    try:
        for prefix in (ASSETS,POSTERS):
            for item in repo.backend.listing(prefix):
                report["scanned"]+=1
                validate_ref(item.pathname,prefix)
                if utc(item.uploaded_at)+timedelta(seconds=ttl(prefix)) <= repo.now():
                    pending.append(item.pathname)
                if report["scanned"] >= max_scan or time.monotonic()-start >= seconds-10:
                    report["partial"]=True
                    break
            if report["partial"]:
                break
        # Iterator is no longer consumed after this point, even on partial scans.
        report["expired"]=len(pending)
        for i in range(0,len(pending),100):
            if time.monotonic()-start >= seconds-5:
                report["partial"]=True
                break
            batch=pending[i:i+100]
            for attempt in range(2):
                try:
                    repo.delete_many(batch)
                    report["deleted"]+=len(batch)
                    break
                except StorageError:
                    if attempt == 1: report["failed"]+=len(batch)
                    else: time.sleep(.1)
    except StorageError:
        report["partial"]=True
        report["failed"]+=1
    report["duration_ms"]=round((time.monotonic()-start)*1000)
    if report["partial"]:
        report["resume"]="Restart enumeration from beginning on next daily run; already deleted objects are absent."
    return report
