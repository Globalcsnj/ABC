"""
ABC MoneyLoan — Layer 1 automation: auto-import Bravo CSV exports.

Watches a folder for CSV files exported from Bravo and uploads each one to the
inventory app (http://localhost:8000/api/import). The app cleans the data on
import (recovers UPC/barcode digits from Excel scientific notation), so no
Excel macro is needed. Processed files are moved to a dated 'processed'
subfolder so they aren't imported twice.

USAGE
  python auto_import.py            # process every CSV in the folder once, then exit
  python auto_import.py --watch    # keep running, process files as they appear

Run it on a schedule with Windows Task Scheduler (see README.md), or launch
run-auto-import.bat. This runs on the STORE PC, alongside the inventory app.
"""

import os
import sys
import time
import json
import shutil
import mimetypes
import urllib.request
import urllib.parse
import http.cookiejar
from datetime import datetime

# ── Configuration — edit these to match the store PC ─────────────────────────
# Folder where Bravo's printed/exported CSVs land:
WATCH_DIR = os.environ.get("ABC_WATCH_DIR", r"C:\Users\DELL\Desktop\BRAVO DOWNLOADS")
# The running inventory app:
APP_URL = os.environ.get("ABC_APP_URL", "http://localhost:8000")
# How to decide each file's report type ("source"): first matching substring
# in the FILE NAME wins (case-insensitive). Adjust to your export names.
SOURCE_RULES = [
    ("layaway", "layaway"),
    ("loan", "loan"),
    ("redemption", "loan"),
    ("renew", "loan"),
    ("retail", "retail"),
    ("manufacture", "retail"),
]
DEFAULT_SOURCE = "retail"
# Import mode: "add" (merge, keeps sold/manual data) or "replace".
IMPORT_MODE = "add"
# Staff password (same one you type to sign in to the app):
APP_PASSWORD = os.environ.get("ABC_APP_PASSWORD", "GCS2026")
POLL_SECONDS = 10          # how often --watch rescans the folder
STABLE_SECONDS = 3         # wait for a file to stop growing before importing
# ─────────────────────────────────────────────────────────────────────────────

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auto_import.log")


def log(msg):
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# Shared opener with a cookie jar so the login cookie carries to the upload.
_opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def login():
    """Sign in so the import request is authorized (the app requires login)."""
    data = urllib.parse.urlencode({"password": APP_PASSWORD}).encode()
    req = urllib.request.Request(APP_URL.rstrip("/") + "/login", data=data, method="POST")
    _opener.open(req, timeout=30).read()


def source_for(filename):
    low = filename.lower()
    for needle, src in SOURCE_RULES:
        if needle in low:
            return src
    return DEFAULT_SOURCE


def _encode_multipart(fields, filename, filebytes):
    """Build a multipart/form-data body with stdlib only (no 'requests' dep)."""
    boundary = "----abcAutoImport" + datetime.now().strftime("%H%M%S%f")
    parts = []
    for k, v in fields.items():
        parts.append(b"--" + boundary.encode())
        parts.append(f'Content-Disposition: form-data; name="{k}"'.encode())
        parts.append(b"")
        parts.append(str(v).encode())
    ctype = mimetypes.guess_type(filename)[0] or "text/csv"
    parts.append(b"--" + boundary.encode())
    parts.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode())
    parts.append(f"Content-Type: {ctype}".encode())
    parts.append(b"")
    parts.append(filebytes)
    parts.append(b"--" + boundary.encode() + b"--")
    parts.append(b"")
    return b"\r\n".join(parts), boundary


def upload(path):
    filename = os.path.basename(path)
    source = source_for(filename)
    with open(path, "rb") as f:
        data = f.read()
    body, boundary = _encode_multipart(
        {"source": source, "product_type": "auto", "mode": IMPORT_MODE}, filename, data)
    req = urllib.request.Request(
        APP_URL.rstrip("/") + "/api/import", data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with _opener.open(req, timeout=120) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return source, result


def archive(path):
    dest_dir = os.path.join(os.path.dirname(path), "processed")
    os.makedirs(dest_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = os.path.basename(path)
    shutil.move(path, os.path.join(dest_dir, f"{stamp}__{base}"))


def is_stable(path):
    """True if the file size hasn't changed over STABLE_SECONDS (finished writing)."""
    try:
        s1 = os.path.getsize(path)
        time.sleep(STABLE_SECONDS)
        return s1 == os.path.getsize(path)
    except OSError:
        return False


def process_once():
    if not os.path.isdir(WATCH_DIR):
        log(f"⚠️ Watch folder not found: {WATCH_DIR}")
        return
    files = [f for f in os.listdir(WATCH_DIR)
             if f.lower().endswith((".csv", ".txt")) and os.path.isfile(os.path.join(WATCH_DIR, f))]
    if not files:
        log("No CSV files to import.")
        return
    for name in sorted(files):
        path = os.path.join(WATCH_DIR, name)
        if not is_stable(path):
            log(f"… {name} still being written, skipping this pass")
            continue
        try:
            source, result = upload(path)
            if result.get("error"):
                log(f"❌ {name} [{source}] — {result['error']}")
                continue
            msg = f"✅ {name} [{source}] — {result.get('imported',0)} new"
            if result.get("updated"):
                msg += f", {result['updated']} updated"
            if result.get("skipped"):
                msg += f", {result['skipped']} skipped"
            log(msg)
            archive(path)
        except Exception as e:
            log(f"❌ {name} — upload failed: {e}")


def main():
    watch = "--watch" in sys.argv
    log(f"Auto-import started (watch={watch}) · folder={WATCH_DIR} · app={APP_URL}")
    try:
        login()
    except Exception as e:
        log(f"❌ Could not sign in to {APP_URL} — is the app running? ({e})")
        return
    if watch:
        while True:
            try:
                login()
            except Exception:
                pass  # keep looping; upload will report if it's really down
            process_once()
            time.sleep(POLL_SECONDS)
    else:
        process_once()
        log("Done.")


if __name__ == "__main__":
    main()
