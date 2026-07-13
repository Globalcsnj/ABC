from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import aiosqlite
import barcode
from barcode.writer import SVGWriter
try:
    import segno
except ImportError:
    segno = None
import asyncio
import csv
import io
import json
import os
import re
import shutil
import socket
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from .database import init_db, get_db, DB_PATH

BASE_DIR = os.path.dirname(os.path.dirname(__file__))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


UPLOAD_DIR = os.path.join(BASE_DIR, "data", "uploads")
BACKUP_DIR = os.path.join(BASE_DIR, "data", "backups")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

# Bump when deploying so /diagnostics confirms the store PC pulled the update
APP_VERSION = "2026-07-13 · UPC + bulk-qty + leading-zero match"

# ── Admin authentication ────────────────────────────────────────────────────
ADMIN_PASSWORD = "GCS2026"          # staff login for the admin app
AUTH_COOKIE = "abc_auth"
AUTH_TOKEN = "abc-authed-ok"        # opaque cookie value set on login
# Paths the public (customers) can reach without logging in
PUBLIC_PREFIXES = ("/shop", "/welcome", "/hold", "/qr", "/barcode", "/static",
                   "/uploads", "/login", "/api/shop", "/favicon", "/offer",
                   "/storefront", "/api/products", "/.image-slots")


def get_lan_ip():
    """Best-effort local network IP so phones on the same WiFi can connect."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def make_daily_backup():
    """Copy the DB into data/backups with a timestamp; keep the newest 14."""
    try:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(DB_PATH, os.path.join(BACKUP_DIR, f"inventory-{stamp}.db"))
        backups = sorted(f for f in os.listdir(BACKUP_DIR) if f.endswith(".db"))
        for old in backups[:-14]:
            os.remove(os.path.join(BACKUP_DIR, old))
    except Exception:
        pass  # never let a backup failure break an import


app = FastAPI(lifespan=lifespan, title="ABC Pawnshop Inventory")


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if path == "/" or not any(path == p or path.startswith(p + "/") or path.startswith(p)
                              for p in PUBLIC_PREFIXES):
        if request.cookies.get(AUTH_COOKIE) != AUTH_TOKEN:
            return RedirectResponse("/login")
    return await call_next(request)


app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# ── Auth & backup routes ────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@app.post("/login")
async def login_submit(password: str = Form(...)):
    if password.strip() == ADMIN_PASSWORD:
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie(AUTH_COOKIE, AUTH_TOKEN, httponly=True, max_age=60 * 60 * 12)
        return resp
    return RedirectResponse("/login?error=1", status_code=303)


@app.get("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(AUTH_COOKIE)
    return resp


@app.get("/backup")
async def backup_download():
    """Download a zip of the whole database + uploaded photos."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if os.path.exists(DB_PATH):
            z.write(DB_PATH, "inventory.db")
        for root, _, files in os.walk(UPLOAD_DIR):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.join("uploads", f))
    buf.seek(0)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return Response(
        content=buf.getvalue(), media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="abc-backup-{stamp}.zip"'},
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def classify_scan(code: str):
    """Location: 3 digits. Sublocation: 3 digits dash number. Item: everything else."""
    if re.fullmatch(r"\d{3}", code.strip()):
        return "location"
    if re.fullmatch(r"\d{3}-\d+", code.strip()):
        return "sublocation"
    return "item"


def expand_code(v) -> str:
    """Normalize a scanned/imported code. Excel often mangles long numeric
    codes (UPC/barcode) into scientific notation like '1.94252192559E+11' or
    wraps them as ="123". Recover the full integer string when possible."""
    if v is None:
        return ""
    s = str(v).strip().lstrip("=").strip().strip('"').strip("'").strip()
    if not s:
        return ""
    # Scientific notation → full integer digits (only when it round-trips
    # without losing precision, i.e. Excel exported the full mantissa).
    if re.fullmatch(r"[0-9]*\.?[0-9]+[eE][+-]?[0-9]+", s):
        try:
            from decimal import Decimal
            s = format(Decimal(s), "f").split(".")[0]
        except Exception:
            pass
    # Trailing ".0" from float-formatted integers
    if re.fullmatch(r"[0-9]+\.0+", s):
        s = s.split(".")[0]
    return s


def clean_money(val: str) -> float:
    try:
        return float(str(val).replace("$", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0.0


def find_column(row: dict, *candidates):
    """Return first matching column value (case-insensitive).

    Guards against None keys/values, which csv.DictReader produces when a
    row has more fields than headers or a header cell is blank.
    """
    row_lower = {}
    for k, v in row.items():
        if k is None:
            continue
        row_lower[str(k).lower().strip()] = v
    for c in candidates:
        v = row_lower.get(c.lower().strip())
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


async def save_photo(photo, prefix: str) -> str:
    """Save an uploaded image and return its stored filename, or '' if none/invalid."""
    if photo is None or not getattr(photo, "filename", ""):
        return ""
    ext = os.path.splitext(photo.filename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        return ""
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", prefix)
    fname = f"{safe}{ext}"
    with open(os.path.join(UPLOAD_DIR, fname), "wb") as f:
        f.write(await photo.read())
    return fname


# ── Reference-image suggestions (Openverse: openly/CC-licensed images) ─────────
OPENVERSE_URL = "https://api.openverse.org/v1/images/"


def _fetch_openverse(query: str, n: int = 8):
    """Blocking call to Openverse; run in a thread. Returns a list of candidates
    or raises. Only CC-licensed / public-domain images so they're safe to reuse."""
    params = urllib.parse.urlencode({
        "q": query, "page_size": n, "mature": "false",
    })
    req = urllib.request.Request(
        OPENVERSE_URL + "?" + params,
        headers={"User-Agent": "ABC-Pawnshop-Inventory/1.0"},
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    out = []
    for r in data.get("results", []):
        url = r.get("url")
        if not url:
            continue
        out.append({
            "url": url,
            "thumb": r.get("thumbnail") or url,
            "title": (r.get("title") or "")[:80],
            "source": r.get("source") or "",
            "license": (r.get("license") or "").upper(),
            "creator": r.get("creator") or "",
        })
    return out


def _download_image(url: str, prefix: str) -> str:
    """Download a remote image into uploads/ so it serves offline. Returns the
    stored filename or '' on failure."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ABC-Pawnshop-Inventory/1.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            data = resp.read()
        ext = ".jpg"
        for c, e in ((".png", ".png"), ("png", ".png"), ("webp", ".webp"),
                     ("gif", ".gif"), ("jpeg", ".jpg"), ("jpg", ".jpg")):
            if c in ctype:
                ext = e
                break
        if len(data) > 8_000_000 or len(data) < 100:
            return ""
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", prefix)
        fname = f"{safe}{ext}"
        with open(os.path.join(UPLOAD_DIR, fname), "wb") as f:
            f.write(data)
        return fname
    except Exception:
        return ""


@app.get("/api/images/suggest")
async def suggest_images(q: str = "", db=Depends(get_db)):
    """Return CC-licensed candidate images for staff to review/approve."""
    query = q.strip()
    if not query:
        return JSONResponse({"error": "Nothing to search for", "results": []})
    try:
        results = await asyncio.to_thread(_fetch_openverse, query)
        return JSONResponse({"results": results, "query": query})
    except Exception as e:
        return JSONResponse({
            "error": "Could not reach the image service (is the store PC online?).",
            "detail": str(e)[:120], "results": [],
        })


@app.post("/api/images/approve")
async def approve_image(item_number: str = Form(...), url: str = Form(...),
                        db=Depends(get_db)):
    """Staff approves a suggested image → download it locally and set it on the item."""
    async with db.execute("SELECT item_number FROM items WHERE item_number=?", (item_number,)) as cur:
        if not await cur.fetchone():
            return JSONResponse({"error": "Item not found"}, status_code=404)
    fname = await asyncio.to_thread(_download_image, url, f"item_{item_number}")
    if not fname:
        return JSONResponse({"error": "Could not download that image. Try another."}, status_code=400)
    await db.execute("UPDATE items SET photo=? WHERE item_number=?", (fname, item_number))
    await db.commit()
    return JSONResponse({"ok": True, "photo": fname})


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db=Depends(get_db)):
    async with db.execute("SELECT * FROM audit_sessions ORDER BY created_at DESC") as cur:
        sessions = await cur.fetchall()
    async with db.execute("SELECT COUNT(*) as cnt FROM items") as cur:
        item_count = (await cur.fetchone())["cnt"]
    # Most recent upload per report type
    async with db.execute("""
        SELECT source, filename, item_count, MAX(uploaded_at) as uploaded_at
        FROM imports GROUP BY source ORDER BY uploaded_at DESC
    """) as cur:
        last_uploads = await cur.fetchall()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "sessions": sessions,
        "last_uploads": last_uploads,
        "item_count": item_count,
        "lan_url": f"{'https' if os.path.exists(os.path.join(BASE_DIR, 'data', 'certs', 'cert.pem')) else 'http'}://{get_lan_ip()}:8000",
    })


@app.get("/audit/{session_id}", response_class=HTMLResponse)
async def audit_page(request: Request, session_id: int, db=Depends(get_db)):
    async with db.execute("SELECT * FROM audit_sessions WHERE id = ?", (session_id,)) as cur:
        session = await cur.fetchone()
    if not session:
        raise HTTPException(404, "Session not found")

    # Expected item count for this count's scope (for the progress bar)
    where = ["COALESCE(sold,0) = 0"]
    params = []
    sess_source = session["source"] if "source" in session.keys() else ""
    sess_cats = session["categories"] if "categories" in session.keys() else ""
    if sess_source:
        where.append("source = ?")
        params.append(sess_source)
    if sess_cats:
        cats = [c for c in sess_cats.split(",") if c]
        if cats:
            ph = ",".join("?" for _ in cats)
            where.append(f"COALESCE(NULLIF(category,''),'Uncategorized') IN ({ph})")
            params.extend(cats)
    async with db.execute(f"SELECT COUNT(*) FROM items WHERE {' AND '.join(where)}", params) as cur:
        expected = (await cur.fetchone())[0]
    # How many distinct expected items already found in this session
    async with db.execute(
        "SELECT COUNT(*) FROM audit_scans WHERE session_id=? AND match_status='found'", (session_id,)
    ) as cur:
        already_found = (await cur.fetchone())[0]

    # Store name for the header so the counter knows exactly where they are
    store_name = ""
    sess_store = session["store_id"] if "store_id" in session.keys() else None
    if sess_store:
        async with db.execute("SELECT name FROM stores WHERE id=?", (sess_store,)) as cur:
            row = await cur.fetchone()
            store_name = row["name"] if row else ""
    if not store_name:
        async with db.execute("SELECT name FROM stores ORDER BY id LIMIT 1") as cur:
            row = await cur.fetchone()
            store_name = row["name"] if row else ""

    return templates.TemplateResponse("audit.html", {
        "request": request, "session": session,
        "expected": expected, "already_found": already_found,
        "store_name": store_name,
    })


JEWELRY_KEYWORDS = ("gold", "silver", "diamond", "ring", "chain", "charm", "earring",
                    "bracelet", "necklace", "pendant", "stone", "jewel", "wristwatch", "watch")


def classify_category(category: str, product_type: str = "", overrides: dict = None) -> str:
    """Return 'Jewelry' or 'Manufactured' for a category, honoring manual overrides."""
    cat = (category or "").strip()
    if overrides and cat in overrides:
        return overrides[cat]
    if product_type == "jewelry":
        return "Jewelry"
    if product_type == "manufactured":
        return "Manufactured"
    if any(k in cat.lower() for k in JEWELRY_KEYWORDS):
        return "Jewelry"
    return "Manufactured"


def big_group(row, overrides=None) -> str:
    pt = (row["product_type"] if "product_type" in row.keys() else "") or ""
    cat = (row["category"] if "category" in row.keys() else "") or ""
    return classify_category(cat, pt, overrides)


async def load_group_overrides(db) -> dict:
    async with db.execute("SELECT category, big_group FROM category_overrides") as cur:
        return {r["category"]: r["big_group"] for r in await cur.fetchall()}


async def get_missing_items(session_id, session, db):
    """Items expected for this count (respecting list + category filters) not scanned."""
    query = """
        SELECT i.item_number, i.barcode, i.description, i.category, i.item_status,
               i.cost, i.retail_price, i.source, i.product_type,
               i.metal_type, i.metal_purity, i.total_diamond, i.total_stone_size
        FROM items i
        WHERE i.item_number NOT IN (
            SELECT item_number FROM audit_scans
            WHERE session_id = ? AND match_status = 'found' AND item_number IS NOT NULL
        ) AND COALESCE(i.sold,0) = 0
    """
    params = [session_id]
    sess_source = session["source"] if "source" in session.keys() else ""
    sess_cats = session["categories"] if "categories" in session.keys() else ""
    if sess_source:
        query += " AND i.source = ?"
        params.append(sess_source)
    if sess_cats:
        cat_list = [c for c in sess_cats.split(",") if c]
        if cat_list:
            ph = ",".join("?" for _ in cat_list)
            query += f" AND COALESCE(NULLIF(i.category,''),'Uncategorized') IN ({ph})"
            params.extend(cat_list)
    query += " ORDER BY i.category, i.item_number"
    async with db.execute(query, params) as cur:
        return await cur.fetchall()


@app.get("/report/{session_id}", response_class=HTMLResponse)
async def report_page(request: Request, session_id: int, db=Depends(get_db)):
    async with db.execute("SELECT * FROM audit_sessions WHERE id = ?", (session_id,)) as cur:
        session = await cur.fetchone()
    if not session:
        raise HTTPException(404)

    async with db.execute("""
        SELECT s.*, i.item_number as bravo_number, i.retail_price as retail_price,
               i.product_type as product_type
        FROM audit_scans s
        LEFT JOIN items i ON i.item_number = s.item_number
        WHERE s.session_id = ?
        ORDER BY s.location_id, s.sublocation_id, s.scanned_at
    """, (session_id,)) as cur:
        scans = await cur.fetchall()

    async with db.execute("""
        SELECT s.location_id, s.sublocation_id, COUNT(*) as total,
               SUM(CASE WHEN s.match_status IN ('found','extra') THEN 1 ELSE 0 END) as found,
               SUM(CASE WHEN s.match_status='unknown' THEN 1 ELSE 0 END) as unknown,
               l.name as location_name, sl.name as sublocation_name
        FROM audit_scans s
        LEFT JOIN locations l ON l.id = s.location_id
        LEFT JOIN sublocations sl ON sl.id = s.sublocation_id
        WHERE s.session_id = ?
        GROUP BY s.location_id, s.sublocation_id
        ORDER BY s.location_id, s.sublocation_id
    """, (session_id,)) as cur:
        summary = await cur.fetchall()

    missing_raw = await get_missing_items(session_id, session, db)
    overrides = await load_group_overrides(db)

    # Annotate each missing item with its group so the report can filter/sort
    missing = []
    group_summary = {}
    for m in missing_raw:
        g = big_group(m, overrides)
        d = dict(m)
        d["group"] = g
        missing.append(d)
        if g not in group_summary:
            group_summary[g] = {"count": 0, "cost": 0.0, "retail": 0.0}
        group_summary[g]["count"] += 1
        group_summary[g]["cost"] += (m["cost"] or 0)
        group_summary[g]["retail"] += (m["retail_price"] or 0)
    group_summary = sorted(group_summary.items(), key=lambda kv: kv[1]["count"], reverse=True)

    found_count = sum(1 for s in scans if s["match_status"] in ("found", "extra"))
    unknown_count = sum(1 for s in scans if s["match_status"] == "unknown")

    # Found-by-group metrics (count, cost, retail) — mirrors Missing by Group
    found_group = {}
    found_cost = found_retail = 0.0
    found_items = []
    for s in scans:
        if s["match_status"] not in ("found", "extra"):
            continue
        g = big_group(s, overrides)
        d = dict(s)
        d["group"] = g
        d["location"] = " › ".join(x for x in (s["location_id"], s["sublocation_id"]) if x)
        found_items.append(d)
        found_group.setdefault(g, {"count": 0, "cost": 0.0, "retail": 0.0})
        found_group[g]["count"] += 1
        found_group[g]["cost"] += (s["cost"] or 0)
        found_group[g]["retail"] += (s["retail_price"] or 0)
        found_cost += (s["cost"] or 0)
        found_retail += (s["retail_price"] or 0)
    found_group = sorted(found_group.items(), key=lambda kv: kv[1]["count"], reverse=True)

    # Breakdown of FOUND items by their Bravo status (Inventory / Layaway / Redeemed / …)
    status_summary = {}
    for s in scans:
        if s["match_status"] not in ("found", "extra"):
            continue
        st = (s["item_status"] or "Unspecified").strip() or "Unspecified"
        status_summary[st] = status_summary.get(st, 0) + 1
    status_summary = sorted(status_summary.items(), key=lambda kv: kv[1], reverse=True)

    # Which categories have missing items (so the user knows what's incomplete)
    missing_by_cat = {}
    for m in missing:
        cat = m["category"] or "Uncategorized"
        missing_by_cat[cat] = missing_by_cat.get(cat, 0) + 1
    missing_by_cat = sorted(missing_by_cat.items(), key=lambda kv: kv[1], reverse=True)

    store_name = ""
    sess_store = session["store_id"] if "store_id" in session.keys() else None
    if sess_store:
        async with db.execute("SELECT name FROM stores WHERE id=?", (sess_store,)) as cur:
            row = await cur.fetchone()
            store_name = row["name"] if row else ""

    return templates.TemplateResponse("report.html", {
        "request": request,
        "session": session,
        "store_name": store_name,
        "scans": scans,
        "summary": summary,
        "missing": missing,
        "missing_by_cat": missing_by_cat,
        "group_summary": group_summary,
        "status_summary": status_summary,
        "found_group": found_group,
        "found_items": found_items,
        "found_cost": found_cost,
        "found_retail": found_retail,
        "found_count": found_count,
        "unknown_count": unknown_count,
        "missing_count": len(missing),
    })


@app.get("/report/{session_id}/missing.csv")
async def report_missing_csv(session_id: int, group: str = "", db=Depends(get_db)):
    async with db.execute("SELECT * FROM audit_sessions WHERE id = ?", (session_id,)) as cur:
        session = await cur.fetchone()
    if not session:
        raise HTTPException(404)
    missing = await get_missing_items(session_id, session, db)
    overrides = await load_group_overrides(db)
    if group in ("Jewelry", "Manufactured"):
        missing = [m for m in missing if big_group(m, overrides) == group]

    # Group contrast
    groups = {}
    for m in missing:
        g = big_group(m, overrides)
        groups.setdefault(g, {"count": 0, "cost": 0.0, "retail": 0.0})
        groups[g]["count"] += 1
        groups[g]["cost"] += (m["cost"] or 0)
        groups[g]["retail"] += (m["retail_price"] or 0)

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([f"Missing Items Report - {session['name']}"])
    w.writerow(["Generated", datetime.now().strftime("%Y-%m-%d %H:%M")])
    w.writerow([])
    w.writerow(["SUMMARY BY GROUP"])
    w.writerow(["Group", "Items Missing", "Cost Value", "Retail Value"])
    for g, v in sorted(groups.items(), key=lambda kv: kv[1]["count"], reverse=True):
        w.writerow([g, v["count"], f"{v['cost']:.2f}", f"{v['retail']:.2f}"])
    w.writerow(["TOTAL", len(missing),
                f"{sum(g['cost'] for g in groups.values()):.2f}",
                f"{sum(g['retail'] for g in groups.values()):.2f}"])
    w.writerow([])
    w.writerow(["MISSING ITEMS DETAIL"])
    w.writerow(["Group", "Item #", "Barcode", "Description", "Category", "Status",
                "Cost", "Retail Price", "Metal", "Purity", "Total Diamond", "Total Stone"])
    for m in missing:
        w.writerow([
            big_group(m, overrides), m["item_number"], m["barcode"], m["description"], m["category"],
            m["item_status"], m["cost"], m["retail_price"], m["metal_type"],
            m["metal_purity"], m["total_diamond"], m["total_stone_size"],
        ])

    filename = f"missing_report_{session_id}.csv"
    return Response(
        content=out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _csv_response(rows_writer, filename):
    out = io.StringIO()
    rows_writer(csv.writer(out))
    return Response(content=out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


async def _scans_for(session_id, db, match_status=None):
    q = "SELECT * FROM audit_scans WHERE session_id=?"
    params = [session_id]
    if match_status:
        q += " AND match_status=?"
        params.append(match_status)
    q += " ORDER BY location_id, sublocation_id, scanned_at"
    async with db.execute(q, params) as cur:
        return await cur.fetchall()


@app.get("/report/{session_id}/found.csv")
async def report_found_csv(session_id: int, db=Depends(get_db)):
    scans = await _scans_for(session_id, db, "found")

    def write(w):
        w.writerow(["FOUND ITEMS", datetime.now().strftime("%Y-%m-%d %H:%M")])
        w.writerow(["Reference", "Item #", "Barcode", "Description", "Category",
                    "Status", "Cost", "Location", "Sublocation", "Scanned At"])
        for s in scans:
            w.writerow([s["full_ref"], s["item_number"], s["barcode"], s["description"],
                        s["category"], s["item_status"], s["cost"], s["location_id"],
                        s["sublocation_id"], s["scanned_at"]])
    return _csv_response(write, f"found_{session_id}.csv")


@app.get("/report/{session_id}/findings.csv")
async def report_findings_csv(session_id: int, db=Depends(get_db)):
    scans = await _scans_for(session_id, db, "unknown") + await _scans_for(session_id, db, "extra")

    def write(w):
        w.writerow(["FINDINGS (scanned, not on list / extra units)", datetime.now().strftime("%Y-%m-%d %H:%M")])
        w.writerow(["Barcode", "Reference", "Location", "Sublocation", "Scanned At"])
        for s in scans:
            w.writerow([s["barcode"], s["full_ref"], s["location_id"],
                        s["sublocation_id"], s["scanned_at"]])
    return _csv_response(write, f"findings_{session_id}.csv")


@app.get("/report/{session_id}/full.csv")
async def report_full_csv(session_id: int, db=Depends(get_db)):
    scans = await _scans_for(session_id, db)

    def write(w):
        w.writerow(["FULL REPORT — ALL SCANS", datetime.now().strftime("%Y-%m-%d %H:%M")])
        w.writerow(["Status", "Reference", "Item #", "Barcode", "Description", "Category",
                    "Item Status", "Cost", "Location", "Sublocation", "Scanned At"])
        for s in scans:
            w.writerow([s["match_status"], s["full_ref"], s["item_number"], s["barcode"],
                        s["description"], s["category"], s["item_status"], s["cost"],
                        s["location_id"], s["sublocation_id"], s["scanned_at"]])
    return _csv_response(write, f"full_report_{session_id}.csv")


# ── Customer-facing catalog (public) ────────────────────────────────────────

SHOP_SORTS = {
    "featured": "category, description",
    "price_low": "CASE WHEN retail_price IS NULL THEN 1 ELSE 0 END, retail_price ASC",
    "price_high": "retail_price DESC",
    "name": "description ASC",
}


@app.get("/shop", response_class=HTMLResponse)
async def shop_page(
    request: Request, q: str = "", category: str = "",
    sort: str = "featured", max_price: str = "", db=Depends(get_db)
):
    # Only retail items flagged for sale and not sold — never loan/layaway.
    # Layaway items can appear in a retail export with a LAYAWAY status → exclude.
    where = ["source = 'retail'", "COALESCE(for_sale,1) = 1", "COALESCE(sold,0) = 0",
             "UPPER(COALESCE(item_status,'')) NOT LIKE '%LAYAWAY%'"]
    params = []
    if q:
        like = f"%{q}%"
        where.append("(description LIKE ? OR category LIKE ? OR item_number LIKE ?)")
        params += [like, like, like]
    if category:
        where.append("COALESCE(NULLIF(category,''),'Uncategorized') = ?")
        params.append(category)
    if max_price.replace(".", "", 1).isdigit():
        where.append("retail_price IS NOT NULL AND retail_price <= ?")
        params.append(float(max_price))
    clause = " AND ".join(where)
    order = SHOP_SORTS.get(sort, SHOP_SORTS["featured"])
    async with db.execute(
        f"SELECT item_number, description, category, item_status, photo, retail_price "
        f"FROM items WHERE {clause} ORDER BY {order} LIMIT 500", params
    ) as cur:
        products = await cur.fetchall()
    async with db.execute("""
        SELECT COALESCE(NULLIF(category,''),'Uncategorized') as category, COUNT(*) as cnt
        FROM items WHERE source = 'retail' AND COALESCE(for_sale,1) = 1 AND COALESCE(sold,0)=0
        GROUP BY category ORDER BY cnt DESC
    """) as cur:
        categories = [dict(r) for r in await cur.fetchall()]
    # Total in-store count + store info for the hero
    total_in_store = sum(c["cnt"] for c in categories)
    async with db.execute("SELECT name, address FROM stores ORDER BY id LIMIT 1") as cur:
        store = await cur.fetchone()
    # Only show the hero/category tiles on the landing view (no search/filter)
    landing = not (q or category or max_price)
    return templates.TemplateResponse("shop.html", {
        "request": request, "products": products, "categories": categories,
        "q": q, "category": category, "sort": sort, "max_price": max_price,
        "count": len(products), "store": store, "total_in_store": total_in_store,
        "landing": landing,
    })


@app.get("/welcome", response_class=HTMLResponse)
async def welcome_page(request: Request, db=Depends(get_db)):
    # Top categories to feature (retail, for sale, not sold)
    async with db.execute("""
        SELECT COALESCE(NULLIF(category,''),'Uncategorized') as category, COUNT(*) as cnt
        FROM items WHERE source='retail' AND COALESCE(for_sale,1)=1 AND COALESCE(sold,0)=0
        GROUP BY category ORDER BY cnt DESC LIMIT 6
    """) as cur:
        categories = [dict(r) for r in await cur.fetchall()]
    async with db.execute("SELECT name, address FROM stores ORDER BY id LIMIT 1") as cur:
        store = await cur.fetchone()
    return templates.TemplateResponse("welcome.html", {
        "request": request, "categories": categories, "store": store,
    })


@app.get("/shop/item/{item_number:path}", response_class=HTMLResponse)
async def shop_item_page(request: Request, item_number: str, db=Depends(get_db)):
    async with db.execute(
        "SELECT * FROM items WHERE item_number = ? AND source='retail'", (item_number,)
    ) as cur:
        product = await cur.fetchone()
    if not product:
        raise HTTPException(404, "Product not found")
    async with db.execute("""
        SELECT item_number, description, category, photo, retail_price FROM items
        WHERE source='retail' AND COALESCE(for_sale,1)=1 AND COALESCE(sold,0)=0
          AND category = ? AND item_number != ?
        ORDER BY description LIMIT 6
    """, (product["category"], item_number)) as cur:
        related = await cur.fetchall()
    return templates.TemplateResponse("shop_item.html", {
        "request": request, "p": product, "related": related,
    })


@app.get("/shop/cart", response_class=HTMLResponse)
async def shop_cart_page(request: Request):
    return templates.TemplateResponse("shop_cart.html", {"request": request})


STOREFRONT_HTML = os.path.join(BASE_DIR, "storefront", "ABC-MoneyLoan-Storefront.html")


@app.get("/diagnostics", response_class=HTMLResponse)
async def diagnostics(request: Request, code: str = "", db=Depends(get_db)):
    """Confirm the running build + look up any code exactly as scanning does."""
    async def scalar(sql, params=()):
        async with db.execute(sql, params) as cur:
            row = await cur.fetchone()
            return row[0] if row and row[0] is not None else 0
    total = await scalar("SELECT COUNT(*) FROM items")
    with_upc = await scalar("SELECT COUNT(*) FROM items WHERE COALESCE(upc,'')!=''")

    # Sample of stored UPCs — reveals at a glance if Excel mangled them
    # (e.g. shows 6.44E+11 or a rounded 644000000000 instead of the real code).
    async with db.execute(
        "SELECT item_number, upc FROM items WHERE COALESCE(upc,'')!='' ORDER BY imported_at DESC LIMIT 8"
    ) as cur:
        sample = [dict(r) for r in await cur.fetchall()]
    sample_html = "".join(f"<tr><td>{s['item_number']}</td><td><code>{s['upc']}</code></td></tr>" for s in sample)
    sample_block = (f"<div class='card mt'><h2>Recently-imported UPCs (sample)</h2>"
                    f"<p class='card-subtitle'>These should look like full 11–13 digit numbers. "
                    f"If you see <code>E+</code> or suspiciously round endings, Excel corrupted them "
                    f"on save — reformat that column as Number/Text and re-upload.</p>"
                    f"<table class='table'><thead><tr><th>Item #</th><th>Stored UPC</th></tr></thead>"
                    f"<tbody>{sample_html}</tbody></table></div>") if sample else ""

    result = ""
    c = code.strip().upper()
    if c:
        cz = c.lstrip("0") or c
        async with db.execute(
            "SELECT item_number, barcode, upc, COALESCE(sold,0) sold, quantity, description "
            "FROM items WHERE barcode=? OR upc=? OR item_number=? "
            "OR ltrim(barcode,'0')=? OR ltrim(upc,'0')=? OR ltrim(item_number,'0')=? LIMIT 25",
            (c, c, c, cz, cz, cz)
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
        if rows:
            body = "".join(
                f"<tr><td>{r['item_number']}</td><td>{r['barcode'] or '—'}</td>"
                f"<td><b>{r['upc'] or '—'}</b></td><td>{r['quantity'] or '1'}</td>"
                f"<td>{'SOLD' if r['sold'] else 'in stock'}</td><td>{r['description'] or ''}</td></tr>"
                for r in rows)
            result = (f"<p style='color:#166534'><b>✓ FOUND {len(rows)} match(es)</b> — this code "
                      f"would scan successfully.</p><table class='table'><thead><tr><th>Item #</th>"
                      f"<th>Barcode</th><th>UPC</th><th>Qty</th><th>Status</th><th>Description</th>"
                      f"</tr></thead><tbody>{body}</tbody></table>")
        else:
            result = (f"<p style='color:#991b1b'><b>✗ NOT FOUND</b> — no item has "
                      f"<code>{c}</code> as its barcode, UPC, or item number. If it's in your "
                      f"file, either the app wasn't updated before you uploaded, or the UPC column "
                      f"didn't import (check the number below).</p>")

    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1'>
    <title>Diagnostics</title><link rel='stylesheet' href='/static/css/style.css'></head>
    <body><main class='container'>
    <div class='page-header'><h1>Diagnostics</h1><a href='/' class='btn btn-outline'>← Home</a></div>
    <div class='card'>
      <p><b>App version:</b> <code>{APP_VERSION}</code></p>
      <p><b>Items in database:</b> {total:,} &nbsp;·&nbsp; <b>with a UPC:</b> {with_upc:,}
      {"<span style='color:#991b1b'> ← 0 means the UPC column has not imported yet</span>" if with_upc == 0 and total else ""}</p>
      <button class='btn btn-outline' onclick='repairCodes(this)'>🔧 Repair scientific-notation codes</button>
      <span id='repairMsg' class='card-subtitle'></span>
      <script>
      async function repairCodes(btn){{
        btn.disabled=true; document.getElementById('repairMsg').textContent=' working…';
        const r=await fetch('/api/diagnostics/repair-codes',{{method:'POST'}});
        const j=await r.json();
        document.getElementById('repairMsg').textContent =
          ` fixed ${{j.fixed}} of ${{j.scanned}} scientific-notation codes.`;
        btn.disabled=false;
      }}
      </script>
    </div>
    <div class='card mt'>
      <h2>Look up a code (barcode / UPC / item #)</h2>
      <p class='card-subtitle'>Type or scan a code — this checks it exactly the way the count screen does.</p>
      <form method='GET' action='/diagnostics'>
        <input type='text' name='code' value='{c}' placeholder='e.g. 643620045336' autofocus
               style='padding:10px;min-width:280px;font-size:16px' autocomplete='off'>
        <button class='btn btn-primary' type='submit'>Look up</button>
      </form>
      <div class='mt'>{result}</div>
    </div>
    {sample_block}
    </main></body></html>"""
    return HTMLResponse(html)


@app.post("/api/diagnostics/repair-codes")
async def repair_codes(db=Depends(get_db)):
    """Normalize UPC/barcode values already stored as scientific notation
    (e.g. '8.10059432376E+11' → '810059432376') so scans match, without
    re-uploading. Cannot recover values Excel already rounded (e.g. 8.1E+11)."""
    async with db.execute(
        "SELECT item_number, upc, barcode FROM items "
        "WHERE upc LIKE '%E+%' OR upc LIKE '%e+%' OR barcode LIKE '%E+%' OR barcode LIKE '%e+%'"
    ) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    fixed = 0
    for r in rows:
        new_upc = expand_code(r["upc"]) if r["upc"] else r["upc"]
        new_bc = expand_code(r["barcode"]) if r["barcode"] else r["barcode"]
        if new_upc != r["upc"] or new_bc != r["barcode"]:
            await db.execute(
                "UPDATE items SET upc=?, barcode=? WHERE item_number=?",
                (new_upc, new_bc, r["item_number"])
            )
            fixed += 1
    await db.commit()
    return JSONResponse({"ok": True, "scanned": len(rows), "fixed": fixed})


@app.get("/.image-slots.state.json")
async def image_slots_sidecar():
    """The storefront's <image-slot> components fetch this sidecar on load.
    Served empty (slots are read-only once the design is exported), so they
    fall back to their placeholders instead of the fetch bouncing to /login."""
    return JSONResponse({})


@app.get("/storefront")
async def storefront_page():
    """Serve the standalone storefront from the same origin as the API so the
    JSON feed connects with zero CORS. The HTML probes /api/products/ itself."""
    if not os.path.exists(STOREFRONT_HTML):
        raise HTTPException(404, "Storefront file not found")
    return FileResponse(STOREFRONT_HTML, media_type="text/html")


def _clean(v):
    """Return a trimmed string or None (so blank Bravo cells map to null)."""
    if v is None:
        return None
    s = str(v).strip()
    return s or None


@app.get("/api/products/")
@app.get("/api/products")
async def products_api(db=Depends(get_db)):
    """Live product feed for the storefront. Same items as the customer shop:
    retail, flagged for sale, not sold, not layaway."""
    async with db.execute("""
        SELECT item_number, barcode, description, category, item_status, product_type,
               retail_price, condition, quantity, photo,
               metal_type, metal_purity, total_jewelry_weight, total_diamond,
               total_stone_size, quality, manufacturer, model, serial_number
        FROM items
        WHERE source='retail' AND COALESCE(for_sale,1)=1 AND COALESCE(sold,0)=0
          AND UPPER(COALESCE(item_status,'')) NOT LIKE '%LAYAWAY%'
        ORDER BY description
    """) as cur:
        rows = await cur.fetchall()

    products = []
    for r in rows:
        qty_raw = re.sub(r"[^0-9]", "", str(r["quantity"] or ""))
        products.append({
            "id": r["item_number"],
            "name": _clean(r["description"]) or r["item_number"],
            "category": _clean(r["category"]) or "Uncategorized",
            "price": r["retail_price"] if r["retail_price"] is not None else "",
            "condition": _clean(r["condition"]),
            "barcode": _clean(r["barcode"]),
            "quantity": int(qty_raw) if qty_raw else 1,
            "image": f"/uploads/{r['photo']}" if r["photo"] else None,
            # Jewelry specs (blank for manufactured goods)
            "metal": _clean(r["metal_type"]),
            "purity": _clean(r["metal_purity"]),
            "weight": _clean(r["total_jewelry_weight"]),
            "diamond": _clean(r["total_diamond"]),
            "stone": _clean(r["total_stone_size"]),
            "quality": _clean(r["quality"]),
            # Electronics specs (blank for jewelry)
            "manufacturer": _clean(r["manufacturer"]),
            "model": _clean(r["model"]),
            "serial": _clean(r["serial_number"]),
        })
    return JSONResponse(products)


@app.get("/api/shop/items")
async def shop_items_api(codes: str = "", db=Depends(get_db)):
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        return []
    placeholders = ",".join("?" for _ in code_list)
    async with db.execute(
        f"SELECT item_number, description, category, photo, retail_price "
        f"FROM items WHERE item_number IN ({placeholders})", code_list
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


HOLD_CUTOFF_HOUR = 16  # 4 PM


def compute_hold_expiry(now: datetime) -> datetime:
    """Hold until 4 PM today. If it's already past 4 PM, hold until 4 PM the
    next business day (skipping Sat/Sun)."""
    cutoff = now.replace(hour=HOLD_CUTOFF_HOUR, minute=0, second=0, microsecond=0)
    if now < cutoff:
        return cutoff
    nxt = now + timedelta(days=1)
    while nxt.weekday() >= 5:  # Saturday=5, Sunday=6
        nxt += timedelta(days=1)
    return nxt.replace(hour=HOLD_CUTOFF_HOUR, minute=0, second=0, microsecond=0)


@app.post("/api/shop/inquiry")
async def create_inquiry(
    customer_name: str = Form(...), phone: str = Form(...),
    email: str = Form(default=""), items: str = Form(...), db=Depends(get_db)
):
    expires = compute_hold_expiry(datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    async with db.execute(
        "INSERT INTO inquiries (customer_name, phone, email, items, status, hold_expires) "
        "VALUES (?, ?, ?, ?, 'holding', ?)",
        (customer_name.strip(), phone.strip(), email.strip(), items, expires)
    ) as cur:
        inquiry_id = cur.lastrowid
    await db.commit()
    return JSONResponse({"ok": True, "id": inquiry_id})


@app.get("/hold/{inquiry_id}", response_class=HTMLResponse)
async def hold_page(request: Request, inquiry_id: int, db=Depends(get_db)):
    async with db.execute("SELECT * FROM inquiries WHERE id=?", (inquiry_id,)) as cur:
        inq = await cur.fetchone()
    if not inq:
        raise HTTPException(404)
    # Resolve item details
    try:
        cart = json.loads(inq["items"] or "{}")
    except Exception:
        cart = {}
    products = []
    if cart:
        placeholders = ",".join("?" for _ in cart)
        async with db.execute(
            f"SELECT item_number, description, category, photo, retail_price "
            f"FROM items WHERE item_number IN ({placeholders})", list(cart.keys())
        ) as cur:
            for r in await cur.fetchall():
                d = dict(r)
                d["qty"] = cart.get(r["item_number"], 1)
                products.append(d)
    # Store address (first store)
    async with db.execute("SELECT name, address FROM stores ORDER BY id LIMIT 1") as cur:
        store = await cur.fetchone()
    return templates.TemplateResponse("hold.html", {
        "request": request, "inq": inq, "products": products, "store": store,
    })


@app.get("/qr")
async def generate_qr(data: str):
    """Return an SVG QR code encoding the given data (e.g. a hold URL)."""
    if segno is None:
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="170" height="170">'
               '<rect width="170" height="170" fill="#f3f4f6"/>'
               '<text x="85" y="85" text-anchor="middle" font-size="11" fill="#9ca3af">QR unavailable</text></svg>')
        return Response(content=svg, media_type="image/svg+xml")
    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="svg", scale=5, border=2)
    return Response(content=buf.getvalue(), media_type="image/svg+xml")


@app.get("/inquiries", response_class=HTMLResponse)
async def inquiries_page(request: Request, db=Depends(get_db)):
    async with db.execute("SELECT * FROM inquiries ORDER BY created_at DESC") as cur:
        rows = await cur.fetchall()
    # Resolve item numbers → descriptions for a readable, linkable list
    enriched = []
    for r in rows:
        d = dict(r)
        try:
            cart = json.loads(r["items"] or "{}")
        except Exception:
            cart = {}
        line = []
        for code, qty in cart.items():
            async with db.execute("SELECT description FROM items WHERE item_number=?", (code,)) as c2:
                row2 = await c2.fetchone()
            desc = row2["description"] if row2 else ""
            line.append({"code": code, "qty": qty, "description": desc})
        d["item_list"] = line
        enriched.append(d)
    return templates.TemplateResponse("inquiries.html", {"request": request, "inquiries": enriched})


@app.get("/inventory/{item_number}/edit", response_class=HTMLResponse)
async def edit_item_page(request: Request, item_number: str, db=Depends(get_db)):
    async with db.execute("SELECT * FROM items WHERE item_number = ?", (item_number,)) as cur:
        item = await cur.fetchone()
    if not item:
        raise HTTPException(404)
    return templates.TemplateResponse("edit_item.html", {"request": request, "item": item})


@app.post("/api/items/{item_number}/edit")
async def edit_item(
    item_number: str,
    retail_price: str = Form(default=""),
    for_sale: str = Form(default=""),
    stage: str = Form(default=""),
    product_type: str = Form(default=""),
    photo: UploadFile = File(default=None),
    db=Depends(get_db)
):
    price = float(retail_price) if retail_price.replace(".", "", 1).isdigit() else None
    sale_flag = 1 if for_sale == "on" else 0
    ptype = product_type if product_type in ("jewelry", "manufactured", "general") else ""
    photo_name = await save_photo(photo, f"item_{item_number}")
    if photo_name:
        await db.execute(
            "UPDATE items SET retail_price=?, for_sale=?, stage=?, product_type=COALESCE(NULLIF(?,''), product_type), photo=? WHERE item_number=?",
            (price, sale_flag, stage, ptype, photo_name, item_number)
        )
    else:
        await db.execute(
            "UPDATE items SET retail_price=?, for_sale=?, stage=?, product_type=COALESCE(NULLIF(?,''), product_type) WHERE item_number=?",
            (price, sale_flag, stage, ptype, item_number)
        )
    await db.commit()
    return RedirectResponse("/inventory", status_code=303)


@app.post("/api/items/{item_number}/delete")
async def delete_item(item_number: str, override: str = Form(...), db=Depends(get_db)):
    """Permanently remove an item from inventory (junk rows, duplicates)."""
    if override.strip() != OVERRIDE_CODE:
        return JSONResponse({"error": "Invalid override code"}, status_code=403)
    await db.execute("DELETE FROM items WHERE item_number = ?", (item_number,))
    await db.commit()
    return JSONResponse({"ok": True})


@app.post("/api/items/stage-bulk")
async def set_stage_bulk(codes: str = Form(...), stage: str = Form(...), db=Depends(get_db)):
    """Set the lifecycle stage for a pasted list of item numbers/barcodes."""
    tokens = [t.strip().upper() for t in re.split(r"[\s,;]+", codes or "") if t.strip()]
    updated = 0
    for c in tokens:
        async with db.execute(
            "UPDATE items SET stage=? WHERE item_number=? OR barcode=?", (stage, c, c)
        ) as cur:
            updated += cur.rowcount
    await db.commit()
    return JSONResponse({"ok": True, "updated": updated})


# ── Sold / reconciliation workflow ──────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, db=Depends(get_db)):
    async def scalar(sql, params=()):
        async with db.execute(sql, params) as cur:
            row = await cur.fetchone()
            return row[0] if row and row[0] is not None else 0

    in_stock = await scalar("SELECT COUNT(*) FROM items WHERE COALESCE(sold,0)=0")
    sold_total = await scalar("SELECT COUNT(*) FROM items WHERE sold=1")
    sold_value = await scalar("SELECT SUM(retail_price) FROM items WHERE sold=1 AND retail_price IS NOT NULL")
    sold_7 = await scalar("SELECT COUNT(*) FROM items WHERE sold=1 AND sold_at >= datetime('now','-7 days')")
    sold_30 = await scalar("SELECT COUNT(*) FROM items WHERE sold=1 AND sold_at >= datetime('now','-30 days')")
    stock_value = await scalar("SELECT SUM(retail_price) FROM items WHERE COALESCE(sold,0)=0 AND retail_price IS NOT NULL")

    # Sold per day, last 14 days
    async with db.execute("""
        SELECT date(sold_at) as d, COUNT(*) as cnt
        FROM items WHERE sold=1 AND sold_at >= datetime('now','-14 days')
        GROUP BY date(sold_at) ORDER BY d
    """) as cur:
        per_day = [dict(r) for r in await cur.fetchall()]

    # Top categories by units sold
    async with db.execute("""
        SELECT COALESCE(NULLIF(category,''),'Uncategorized') as category,
               COUNT(*) as cnt, SUM(COALESCE(retail_price,0)) as value
        FROM items WHERE sold=1
        GROUP BY category ORDER BY cnt DESC LIMIT 12
    """) as cur:
        top_cats = [dict(r) for r in await cur.fetchall()]

    # Sell-through per category (sold vs in stock)
    async with db.execute("""
        SELECT COALESCE(NULLIF(category,''),'Uncategorized') as category,
               SUM(CASE WHEN sold=1 THEN 1 ELSE 0 END) as sold,
               SUM(CASE WHEN COALESCE(sold,0)=0 THEN 1 ELSE 0 END) as stock
        FROM items GROUP BY category
        HAVING sold > 0 ORDER BY sold DESC LIMIT 10
    """) as cur:
        sellthrough = [dict(r) for r in await cur.fetchall()]

    # Best-selling products (reorder candidates). Each item_number is unique
    # stock, so we group sold items by their description to see which products
    # sell repeatedly — the ones worth sourcing more of.
    async with db.execute("""
        SELECT UPPER(TRIM(description)) as pkey,
               MAX(description) as description,
               MAX(COALESCE(NULLIF(category,''),'Uncategorized')) as category,
               COUNT(*) as sold_cnt,
               SUM(CASE WHEN sold_at >= datetime('now','-90 days') THEN 1 ELSE 0 END) as sold_90,
               SUM(COALESCE(retail_price,0)) as revenue,
               AVG(retail_price) as avg_price
        FROM items
        WHERE sold=1 AND TRIM(COALESCE(description,'')) != ''
        GROUP BY pkey
        ORDER BY sold_cnt DESC, revenue DESC
        LIMIT 20
    """) as cur:
        best_sellers = [dict(r) for r in await cur.fetchall()]

    # How many of each best-seller are still in stock (0 → definitely reorder)
    if best_sellers:
        keys = [b["pkey"] for b in best_sellers]
        ph = ",".join("?" for _ in keys)
        async with db.execute(
            f"""SELECT UPPER(TRIM(description)) as pkey, COUNT(*) as stock
                FROM items WHERE COALESCE(sold,0)=0 AND UPPER(TRIM(description)) IN ({ph})
                GROUP BY pkey""", keys
        ) as cur:
            stock_map = {r["pkey"]: r["stock"] for r in await cur.fetchall()}
        for b in best_sellers:
            b["in_stock"] = stock_map.get(b["pkey"], 0)

    max_day = max([d["cnt"] for d in per_day], default=1) or 1
    max_cat = max([c["cnt"] for c in top_cats], default=1) or 1
    max_seller = max([b["sold_cnt"] for b in best_sellers], default=1) or 1

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "in_stock": in_stock, "sold_total": sold_total, "sold_value": sold_value,
        "sold_7": sold_7, "sold_30": sold_30, "stock_value": stock_value,
        "per_day": per_day, "top_cats": top_cats, "sellthrough": sellthrough,
        "best_sellers": best_sellers, "max_seller": max_seller,
        "max_day": max_day, "max_cat": max_cat,
    })


@app.get("/analysis", response_class=HTMLResponse)
async def analysis_page(request: Request, session_id: int = 0, db=Depends(get_db)):
    async def scalar(sql, params=()):
        async with db.execute(sql, params) as cur:
            row = await cur.fetchone()
            return row[0] if row and row[0] is not None else 0

    total = await scalar("SELECT COUNT(*) FROM items")
    in_stock = await scalar("SELECT COUNT(*) FROM items WHERE COALESCE(sold,0)=0")
    cost_value = await scalar("SELECT SUM(cost) FROM items WHERE COALESCE(sold,0)=0 AND cost IS NOT NULL")
    retail_value = await scalar("SELECT SUM(retail_price) FROM items WHERE COALESCE(sold,0)=0 AND retail_price IS NOT NULL")
    priced = await scalar("SELECT COUNT(*) FROM items WHERE COALESCE(sold,0)=0 AND retail_price IS NOT NULL")
    unpriced = await scalar("SELECT COUNT(*) FROM items WHERE COALESCE(sold,0)=0 AND retail_price IS NULL")
    margin = (retail_value or 0) - await scalar(
        "SELECT SUM(cost) FROM items WHERE COALESCE(sold,0)=0 AND retail_price IS NOT NULL AND cost IS NOT NULL")

    # Value + count by category (in stock)
    async with db.execute("""
        SELECT COALESCE(NULLIF(category,''),'Uncategorized') as category,
               COUNT(*) as cnt,
               SUM(COALESCE(retail_price,0)) as retail,
               SUM(COALESCE(cost,0)) as cost
        FROM items WHERE COALESCE(sold,0)=0
        GROUP BY category ORDER BY retail DESC, cnt DESC LIMIT 20
    """) as cur:
        by_cat = [dict(r) for r in await cur.fetchall()]

    async with db.execute("""
        SELECT COALESCE(NULLIF(product_type,''),'general') as t, COUNT(*) as cnt
        FROM items WHERE COALESCE(sold,0)=0 GROUP BY t ORDER BY cnt DESC
    """) as cur:
        by_type = [dict(r) for r in await cur.fetchall()]

    async with db.execute("""
        SELECT COALESCE(NULLIF(source,''),'unspecified') as s, COUNT(*) as cnt,
               SUM(COALESCE(retail_price,0)) as retail
        FROM items WHERE COALESCE(sold,0)=0 GROUP BY s ORDER BY cnt DESC
    """) as cur:
        by_source = [dict(r) for r in await cur.fetchall()]

    # Inventory aging buckets (from Inventory Age column, days)
    aging = {"0–30 days": 0, "31–60 days": 0, "61–90 days": 0, "90+ days": 0, "Unknown": 0}
    async with db.execute(
        "SELECT inventory_age FROM items WHERE COALESCE(sold,0)=0"
    ) as cur:
        for r in await cur.fetchall():
            raw = re.sub(r"[^0-9]", "", (r["inventory_age"] or ""))
            if not raw:
                aging["Unknown"] += 1
                continue
            d = int(raw)
            if d <= 30:
                aging["0–30 days"] += 1
            elif d <= 60:
                aging["31–60 days"] += 1
            elif d <= 90:
                aging["61–90 days"] += 1
            else:
                aging["90+ days"] += 1
    aging_max = max(aging.values()) or 1

    # Aged stock: in-stock items 90+ days old — candidates for offers/markdowns
    async with db.execute("""
        SELECT item_number, barcode, description, category, cost, retail_price,
               inventory_age, item_status
        FROM items WHERE COALESCE(sold,0)=0 AND inventory_age IS NOT NULL AND inventory_age != ''
    """) as cur:
        aged_rows = [dict(r) for r in await cur.fetchall()]
    aged_items = []
    for r in aged_rows:
        raw = re.sub(r"[^0-9]", "", r["inventory_age"] or "")
        if raw and int(raw) > 90:
            r["age_days"] = int(raw)
            aged_items.append(r)
    aged_items.sort(key=lambda r: r["age_days"], reverse=True)
    aged_retail = sum(r["retail_price"] or 0 for r in aged_items)

    max_cat = max([c["retail"] for c in by_cat], default=1) or 1
    wb = await load_workbench_data(db, session_id)
    return templates.TemplateResponse("analysis.html", {
        "request": request, "total": total, "in_stock": in_stock,
        "cost_value": cost_value, "retail_value": retail_value, "margin": margin,
        "priced": priced, "unpriced": unpriced,
        "by_cat": by_cat, "by_type": by_type, "by_source": by_source, "max_cat": max_cat,
        "aging": aging, "aging_max": aging_max,
        "aged_items": aged_items, "aged_count": len(aged_items), "aged_retail": aged_retail,
        **wb,
    })


@app.get("/analysis/aged.csv")
async def aged_stock_csv(db=Depends(get_db)):
    """Items in stock 90+ days — the offers/markdown candidate list."""
    async with db.execute("""
        SELECT item_number, barcode, description, category, cost, retail_price,
               inventory_age, item_status
        FROM items WHERE COALESCE(sold,0)=0 AND inventory_age IS NOT NULL AND inventory_age != ''
    """) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    aged = []
    for r in rows:
        raw = re.sub(r"[^0-9]", "", r["inventory_age"] or "")
        if raw and int(raw) > 90:
            r["age_days"] = int(raw)
            aged.append(r)
    aged.sort(key=lambda r: r["age_days"], reverse=True)

    def write(w):
        w.writerow(["AGED STOCK 90+ DAYS — OFFER CANDIDATES", datetime.now().strftime("%Y-%m-%d %H:%M")])
        w.writerow(["Days in Stock", "Item #", "Barcode", "Description", "Category",
                    "Status", "Cost", "Retail Price"])
        for r in aged:
            w.writerow([r["age_days"], r["item_number"], r["barcode"], r["description"],
                        r["category"], r["item_status"], r["cost"], r["retail_price"]])
    return _csv_response(write, "aged_stock_offers.csv")


# ── Campaigns (offers built from aged stock) ──────────────────────────────────
def _offer_price(retail, discount_pct):
    if retail is None:
        return None
    return round(retail * (1 - (discount_pct or 0) / 100.0), 2)


@app.get("/campaigns", response_class=HTMLResponse)
async def campaigns_page(request: Request, db=Depends(get_db)):
    async with db.execute("""
        SELECT c.*, COUNT(ci.item_number) as item_count
        FROM campaigns c LEFT JOIN campaign_items ci ON ci.campaign_id = c.id
        GROUP BY c.id ORDER BY c.created_at DESC
    """) as cur:
        campaigns = [dict(r) for r in await cur.fetchall()]
    # Category list for the "create from aged stock" filter
    async with db.execute("""
        SELECT COALESCE(NULLIF(category,''),'Uncategorized') as category, COUNT(*) as cnt
        FROM items WHERE COALESCE(sold,0)=0 GROUP BY category ORDER BY cnt DESC
    """) as cur:
        categories = [dict(r) for r in await cur.fetchall()]
    return templates.TemplateResponse("campaigns.html", {
        "request": request, "campaigns": campaigns, "categories": categories,
    })


@app.post("/campaigns/create")
async def create_campaign(name: str = Form(...), blurb: str = Form(default=""),
                          discount_pct: float = Form(default=0), min_age: int = Form(default=90),
                          category: str = Form(default=""), db=Depends(get_db)):
    async with db.execute(
        "INSERT INTO campaigns (name, blurb, discount_pct) VALUES (?, ?, ?)",
        (name.strip(), blurb.strip(), discount_pct)
    ) as cur:
        cid = cur.lastrowid

    where = ["COALESCE(sold,0)=0", "inventory_age IS NOT NULL", "inventory_age != ''"]
    params = []
    if category:
        where.append("COALESCE(NULLIF(category,''),'Uncategorized') = ?")
        params.append(category)
    async with db.execute(
        f"SELECT item_number, inventory_age FROM items WHERE {' AND '.join(where)}", params
    ) as cur:
        rows = await cur.fetchall()
    added = 0
    for r in rows:
        raw = re.sub(r"[^0-9]", "", r["inventory_age"] or "")
        if raw and int(raw) >= min_age:
            await db.execute(
                "INSERT OR IGNORE INTO campaign_items (campaign_id, item_number) VALUES (?, ?)",
                (cid, r["item_number"])
            )
            added += 1
    await db.commit()
    return RedirectResponse(f"/campaigns/{cid}", status_code=303)


@app.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
async def campaign_detail(request: Request, campaign_id: int, db=Depends(get_db)):
    async with db.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)) as cur:
        campaign = await cur.fetchone()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    async with db.execute("""
        SELECT i.item_number, i.description, i.category, i.photo, i.retail_price, i.inventory_age
        FROM campaign_items ci JOIN items i ON i.item_number = ci.item_number
        WHERE ci.campaign_id = ? ORDER BY i.category, i.description
    """, (campaign_id,)) as cur:
        items = [dict(r) for r in await cur.fetchall()]
    disc = campaign["discount_pct"] or 0
    for it in items:
        it["offer_price"] = _offer_price(it["retail_price"], disc)
    with_img = sum(1 for it in items if it["photo"])
    return templates.TemplateResponse("campaign_detail.html", {
        "request": request, "c": campaign, "items": items,
        "with_img": with_img, "total_items": len(items),
    })


@app.post("/campaigns/{campaign_id}/remove-item")
async def campaign_remove_item(campaign_id: int, item_number: str = Form(...), db=Depends(get_db)):
    await db.execute(
        "DELETE FROM campaign_items WHERE campaign_id=? AND item_number=?",
        (campaign_id, item_number)
    )
    await db.commit()
    return JSONResponse({"ok": True})


@app.post("/campaigns/{campaign_id}/status")
async def campaign_set_status(campaign_id: int, status: str = Form(...), db=Depends(get_db)):
    if status not in ("active", "ended"):
        return JSONResponse({"error": "bad status"}, status_code=400)
    await db.execute("UPDATE campaigns SET status=? WHERE id=?", (status, campaign_id))
    await db.commit()
    return RedirectResponse(f"/campaigns/{campaign_id}", status_code=303)


@app.post("/campaigns/{campaign_id}/delete")
async def campaign_delete(campaign_id: int, override: str = Form(...), db=Depends(get_db)):
    if override.strip() != OVERRIDE_CODE:
        return JSONResponse({"error": "Invalid override code"}, status_code=403)
    await db.execute("DELETE FROM campaign_items WHERE campaign_id=?", (campaign_id,))
    await db.execute("DELETE FROM campaigns WHERE id=?", (campaign_id,))
    await db.commit()
    return RedirectResponse("/campaigns", status_code=303)


@app.get("/offer/{campaign_id}", response_class=HTMLResponse)
async def public_offer_page(request: Request, campaign_id: int, db=Depends(get_db)):
    """Customer-facing campaign/offer page (public)."""
    async with db.execute(
        "SELECT * FROM campaigns WHERE id=? AND status='active'", (campaign_id,)
    ) as cur:
        campaign = await cur.fetchone()
    if not campaign:
        raise HTTPException(404, "This offer is no longer available")
    async with db.execute("""
        SELECT i.item_number, i.description, i.category, i.photo, i.retail_price
        FROM campaign_items ci JOIN items i ON i.item_number = ci.item_number
        WHERE ci.campaign_id = ? AND COALESCE(i.sold,0)=0
        ORDER BY i.category, i.description
    """, (campaign_id,)) as cur:
        items = [dict(r) for r in await cur.fetchall()]
    disc = campaign["discount_pct"] or 0
    for it in items:
        it["offer_price"] = _offer_price(it["retail_price"], disc)
    async with db.execute("SELECT name, address FROM stores ORDER BY id LIMIT 1") as cur:
        store = await cur.fetchone()
    return templates.TemplateResponse("offer.html", {
        "request": request, "c": campaign, "items": items, "store": store,
    })


@app.get("/categories", response_class=HTMLResponse)
async def categories_page(request: Request, db=Depends(get_db)):
    # Every category with counts + value + representative product type
    async with db.execute("""
        SELECT COALESCE(NULLIF(category,''),'Uncategorized') as category,
               COUNT(*) as cnt,
               SUM(COALESCE(retail_price,0)) as retail,
               SUM(COALESCE(cost,0)) as cost,
               MAX(product_type) as product_type
        FROM items GROUP BY category ORDER BY cnt DESC
    """) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    overrides = await load_group_overrides(db)
    groups = {"Jewelry": [], "Manufactured": []}
    for r in rows:
        g = classify_category(r["category"], r["product_type"] or "", overrides)
        r["group"] = g
        r["overridden"] = r["category"] in overrides
        groups.setdefault(g, []).append(r)
    return templates.TemplateResponse("categories.html", {
        "request": request, "groups": groups,
        "jewelry_keywords": ", ".join(JEWELRY_KEYWORDS),
    })


@app.post("/api/categories/group")
async def set_category_group(category: str = Form(...), group: str = Form(...), db=Depends(get_db)):
    if group in ("Jewelry", "Manufactured"):
        await db.execute(
            "INSERT OR REPLACE INTO category_overrides (category, big_group) VALUES (?, ?)",
            (category, group)
        )
        await db.commit()
    return RedirectResponse("/categories", status_code=303)


@app.get("/explore")
async def explore_redirect():
    # Explore is merged into Inventory Analysis
    return RedirectResponse("/analysis")


async def load_workbench_data(db, session_id: int = 0):
    """Items + filter option lists for the analysis workbench. When a count
    session is given, each item is tagged Found/Missing for that count."""
    async with db.execute("""
        SELECT item_number, barcode, upc, description, category, item_status, source, product_type,
               cost, retail_price, metal_type, metal_purity, total_jewelry_weight,
               metal_weight, total_diamond, total_stone_size, quality,
               manufacturer, model, vendor, item_date, date_to_inventory, sold_at,
               COALESCE(NULLIF(stage,''),'Inventory') as stage,
               COALESCE(sold,0) as sold
        FROM items ORDER BY category, item_number
    """) as cur:
        items = [dict(r) for r in await cur.fetchall()]
    overrides = await load_group_overrides(db)

    def _year(*vals):
        """First 4-digit year (19xx/20xx) found in the given date strings."""
        for v in vals:
            if not v:
                continue
            m = re.search(r"(19|20)\d{2}", str(v))
            if m:
                return m.group(0)
        return ""

    for it in items:
        it["group"] = classify_category(it.get("category") or "", it.get("product_type") or "", overrides)
        # Year an item entered inventory — drives the "measure by year" views
        it["year"] = _year(it.get("date_to_inventory"), it.get("item_date"))

    session_name = ""
    if session_id:
        async with db.execute("SELECT name FROM audit_sessions WHERE id=?", (session_id,)) as cur:
            row = await cur.fetchone()
            session_name = row["name"] if row else ""
        async with db.execute(
            "SELECT item_number FROM audit_scans WHERE session_id=? AND match_status='found' "
            "AND item_number IS NOT NULL",
            (session_id,)
        ) as cur:
            found = {r["item_number"] for r in await cur.fetchall()}
        for it in items:
            it["count_result"] = "Found" if (it.get("item_number") or "") in found else "Missing"

    def distinct(field):
        return sorted({(it.get(field) or "").strip() for it in items if (it.get(field) or "").strip()})

    return {
        "items_json": json.dumps(items),
        "wb_categories": distinct("category"),
        "wb_metals": distinct("metal_type"),
        "wb_purities": distinct("metal_purity"),
        "wb_statuses": distinct("item_status"),
        "wb_years": sorted({it["year"] for it in items if it["year"]}, reverse=True),
        "wb_session_id": session_id,
        "wb_session_name": session_name,
    }


@app.get("/reconcile", response_class=HTMLResponse)
async def reconcile_page(request: Request, frm: str = "", to: str = "",
                         status: str = "", db=Depends(get_db)):
    async with db.execute("""
        SELECT item_number, barcode, description, category, cost, retail_price, source
        FROM items WHERE missing=1 AND sold=0 ORDER BY source, category, item_number
    """) as cur:
        missing = await cur.fetchall()
    async with db.execute("""
        SELECT item_number, barcode, description, category, sold_at
        FROM items WHERE sold=1 ORDER BY sold_at DESC LIMIT 200
    """) as cur:
        sold = await cur.fetchall()
    return await _render_reconcile(request, db, missing, sold, frm, to, status)


async def _render_reconcile(request, db, missing, sold, frm="", to="", status=""):
    query = "SELECT * FROM reconcile_log WHERE 1=1"
    params = []
    if frm:
        query += " AND date(flagged_at) >= ?"
        params.append(frm)
    if to:
        query += " AND date(flagged_at) <= ?"
        params.append(to)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY flagged_at DESC, id DESC LIMIT 800"
    async with db.execute(query, params) as cur:
        log = await cur.fetchall()
    return templates.TemplateResponse("reconcile.html", {
        "request": request, "missing": missing, "sold": sold, "log": log,
        "frm": frm, "to": to, "log_status": status,
    })


@app.get("/reconcile/log.csv")
async def reconcile_log_csv(frm: str = "", to: str = "", status: str = "", db=Depends(get_db)):
    query = "SELECT * FROM reconcile_log WHERE 1=1"
    params = []
    if frm:
        query += " AND date(flagged_at) >= ?"; params.append(frm)
    if to:
        query += " AND date(flagged_at) <= ?"; params.append(to)
    if status:
        query += " AND status = ?"; params.append(status)
    query += " ORDER BY flagged_at DESC, id DESC"
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Flagged At", "Group", "Item #", "Barcode", "Description", "Category",
                "Source", "Cost", "Retail", "Status", "Resolved At"])
    for r in rows:
        w.writerow([r["flagged_at"], r["big_group"], r["item_number"], r["barcode"],
                    r["description"], r["category"], r["source"], r["cost"], r["retail_price"],
                    r["status"], r["resolved_at"] or ""])
    return Response(content=out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="reconcile_log.csv"'})


@app.post("/api/items/{item_number}/sold")
async def mark_sold(item_number: str, db=Depends(get_db)):
    await db.execute(
        "UPDATE items SET sold=1, sold_at=CURRENT_TIMESTAMP, missing=0, for_sale=0 WHERE item_number=?",
        (item_number,)
    )
    await db.execute(
        "UPDATE reconcile_log SET status='sold', resolved_at=CURRENT_TIMESTAMP "
        "WHERE item_number=? AND status='missing'", (item_number,)
    )
    await db.commit()
    return RedirectResponse("/reconcile", status_code=303)


@app.get("/sell", response_class=HTMLResponse)
async def sell_page(request: Request, db=Depends(get_db)):
    # Today's sales
    async with db.execute("""
        SELECT item_number, description, category, retail_price, sold_at
        FROM items WHERE sold=1 AND date(sold_at)=date('now','localtime')
        ORDER BY sold_at DESC
    """) as cur:
        today = await cur.fetchall()
    total_today = sum((r["retail_price"] or 0) for r in today)
    return templates.TemplateResponse("sell.html", {
        "request": request, "today": today, "total_today": total_today,
    })


@app.post("/api/sell")
async def record_sale(code: str = Form(...), db=Depends(get_db)):
    """Record a single daily sale by scanning/typing an item number or barcode."""
    c = code.strip().upper()
    # Sell ONE unit: pick the first UNSOLD item matching the code (a barcode
    # may cover several identical units — scan once per unit sold).
    async with db.execute(
        "SELECT item_number, description, retail_price FROM items "
        "WHERE (item_number = ? OR barcode = ? OR upc = ?) AND COALESCE(sold,0)=0 "
        "ORDER BY item_number LIMIT 1", (c, c, c)
    ) as cur:
        item = await cur.fetchone()
    if not item:
        async with db.execute(
            "SELECT COUNT(*) FROM items WHERE item_number = ? OR barcode = ? OR upc = ?", (c, c, c)
        ) as cur:
            known = (await cur.fetchone())[0]
        if known:
            return JSONResponse({"ok": False, "message": f"🔁 All units of {c} are already sold"})
        return JSONResponse({"ok": False, "message": f"⚠️ {c} not found in inventory"})
    await db.execute(
        "UPDATE items SET sold=1, sold_at=CURRENT_TIMESTAMP, missing=0, for_sale=0 "
        "WHERE item_number = ?", (item["item_number"],)
    )
    await db.execute(
        "UPDATE reconcile_log SET status='sold', resolved_at=CURRENT_TIMESTAMP "
        "WHERE item_number=? AND status='missing'", (item["item_number"],)
    )
    await db.commit()
    price = f"${item['retail_price']:.2f}" if item["retail_price"] else "—"
    return JSONResponse({
        "ok": True,
        "message": f"✅ SOLD — {item['item_number']} · {item['description'] or ''} · {price}",
    })


@app.post("/api/items/sold-list")
async def mark_sold_from_list(
    codes: str = Form(default=""),
    file: UploadFile = File(default=None),
    db=Depends(get_db)
):
    """Deduct a list of pre-sold items: match by item number or barcode and mark sold."""
    raw = codes or ""
    if file is not None and getattr(file, "filename", ""):
        try:
            content = await file.read()
            text = content.decode("utf-8-sig", errors="replace")
            # Take the first column of each CSV line, or the whole line
            for line in text.splitlines():
                raw += "\n" + line.split(",")[0]
        except Exception:
            pass
    tokens = [t.strip().upper() for t in re.split(r"[\s,;]+", raw) if t.strip()]

    sold, notfound = 0, []
    for code in tokens:
        # Sell ONE unsold unit per listed code (list a barcode twice to sell 2 units)
        async with db.execute(
            "SELECT item_number FROM items WHERE (item_number = ? OR barcode = ? OR upc = ?) "
            "AND COALESCE(sold,0)=0 ORDER BY item_number LIMIT 1", (code, code, code)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            notfound.append(code)
            continue
        await db.execute(
            "UPDATE items SET sold=1, sold_at=CURRENT_TIMESTAMP, missing=0, for_sale=0 "
            "WHERE item_number = ?", (row["item_number"],)
        )
        sold += 1
    await db.commit()
    return JSONResponse({"ok": True, "sold": sold, "not_found": notfound})


@app.post("/api/items/{item_number}/keep")
async def mark_keep(item_number: str, db=Depends(get_db)):
    await db.execute("UPDATE items SET missing=0 WHERE item_number=?", (item_number,))
    await db.execute(
        "UPDATE reconcile_log SET status='kept', resolved_at=CURRENT_TIMESTAMP "
        "WHERE item_number=? AND status='missing'", (item_number,)
    )
    await db.commit()
    return RedirectResponse("/reconcile", status_code=303)


@app.post("/api/items/{item_number}/unsold")
async def mark_unsold(item_number: str, db=Depends(get_db)):
    await db.execute(
        "UPDATE items SET sold=0, sold_at=NULL, for_sale=1 WHERE item_number=?", (item_number,)
    )
    await db.commit()
    return RedirectResponse("/reconcile", status_code=303)


@app.get("/locations", response_class=HTMLResponse)
async def locations_page(request: Request, db=Depends(get_db)):
    async with db.execute("""
        SELECT l.*, COUNT(s.id) as sublocation_count
        FROM locations l
        LEFT JOIN sublocations s ON s.location_id = l.id
        GROUP BY l.id ORDER BY l.id
    """) as cur:
        locations = await cur.fetchall()
    async with db.execute("SELECT * FROM sublocations ORDER BY id") as cur:
        sublocations = await cur.fetchall()
    return templates.TemplateResponse("locations.html", {
        "request": request,
        "locations": locations,
        "sublocations": sublocations,
    })


INV_SORTS = {
    "number": "item_number ASC",
    "desc": "description ASC",
    "cat": "category ASC, item_number ASC",
    "price_low": "CASE WHEN retail_price IS NULL THEN 1 ELSE 0 END, retail_price ASC",
    "price_high": "retail_price DESC",
    "cost_high": "cost DESC",
}


@app.get("/inventory", response_class=HTMLResponse)
async def inventory_page(
    request: Request, q: str = "", category: str = "", source: str = "",
    ptype: str = "", status: str = "", item_status: str = "", sort: str = "number",
    db=Depends(get_db)
):
    where = []
    params = []
    if q:
        like = f"%{q}%"
        where.append("(item_number LIKE ? OR barcode LIKE ? OR description LIKE ? OR category LIKE ?)")
        params += [like, like, like, like]
    if category:
        where.append("COALESCE(NULLIF(category,''),'Uncategorized') = ?")
        params.append(category)
    if source:
        where.append("source = ?")
        params.append(source)
    if item_status:
        where.append("item_status = ?")
        params.append(item_status)
    if ptype:
        where.append("product_type = ?")
        params.append(ptype)
    if status == "sold":
        where.append("sold = 1")
    elif status == "instock":
        where.append("COALESCE(sold,0) = 0")
    elif status == "for_sale":
        where.append("COALESCE(for_sale,1) = 1 AND COALESCE(sold,0) = 0")
    elif status == "missing":
        where.append("missing = 1 AND sold = 0")

    clause = (" WHERE " + " AND ".join(where)) if where else ""
    order = INV_SORTS.get(sort, INV_SORTS["number"])
    async with db.execute(f"SELECT * FROM items{clause} ORDER BY {order} LIMIT 800", params) as cur:
        items = await cur.fetchall()
    async with db.execute("SELECT COUNT(*) as cnt FROM items") as cur:
        total = (await cur.fetchone())["cnt"]
    async with db.execute("""
        SELECT COALESCE(NULLIF(category,''), 'Uncategorized') as category, COUNT(*) as cnt
        FROM items GROUP BY category ORDER BY cnt DESC
    """) as cur:
        categories = [dict(r) for r in await cur.fetchall()]
    async with db.execute(
        "SELECT DISTINCT source FROM items WHERE source IS NOT NULL AND source != '' ORDER BY source"
    ) as cur:
        sources = [r["source"] for r in await cur.fetchall()]
    async with db.execute(
        "SELECT DISTINCT item_status FROM items WHERE item_status IS NOT NULL AND item_status != '' ORDER BY item_status"
    ) as cur:
        item_statuses = [r["item_status"] for r in await cur.fetchall()]
    async with db.execute(
        "SELECT id FROM audit_sessions WHERE status='active' ORDER BY created_at DESC LIMIT 1"
    ) as cur:
        active = await cur.fetchone()
    return templates.TemplateResponse("inventory.html", {
        "request": request, "items": items, "total": total, "showing": len(items),
        "q": q, "category": category, "source": source, "ptype": ptype,
        "status": status, "item_status": item_status, "sort": sort,
        "categories": categories, "sources": sources, "item_statuses": item_statuses,
        "active_session": active["id"] if active else None,
    })


@app.get("/new-count", response_class=HTMLResponse)
async def new_count_page(request: Request, db=Depends(get_db)):
    # Lists (sources) with item counts
    async with db.execute("""
        SELECT COALESCE(NULLIF(source,''), 'unspecified') as source, COUNT(*) as cnt
        FROM items GROUP BY source ORDER BY cnt DESC
    """) as cur:
        lists = [dict(r) for r in await cur.fetchall()]
    # Categories with counts
    async with db.execute("""
        SELECT COALESCE(NULLIF(category,''), 'Uncategorized') as category, COUNT(*) as cnt
        FROM items GROUP BY category ORDER BY cnt DESC
    """) as cur:
        categories = [dict(r) for r in await cur.fetchall()]
    async with db.execute("SELECT COUNT(*) as cnt FROM items") as cur:
        total = (await cur.fetchone())["cnt"]
    async with db.execute("SELECT * FROM stores ORDER BY id") as cur:
        stores = await cur.fetchall()
    return templates.TemplateResponse("new_count.html", {
        "request": request,
        "lists": lists,
        "categories": categories,
        "total": total,
        "stores": stores,
    })


@app.get("/labels", response_class=HTMLResponse)
async def labels_page(request: Request, db=Depends(get_db)):
    async with db.execute("SELECT * FROM locations ORDER BY id") as cur:
        locations = await cur.fetchall()
    async with db.execute("SELECT * FROM sublocations ORDER BY id") as cur:
        sublocations = await cur.fetchall()
    return templates.TemplateResponse("labels.html", {
        "request": request,
        "locations": locations,
        "sublocations": sublocations,
    })


# ── API ───────────────────────────────────────────────────────────────────────

@app.post("/api/sessions")
async def create_session(
    name: str = Form(...),
    source: str = Form(default=""),
    categories: list[str] = Form(default=[]),
    store_id: str = Form(default=""),
    db=Depends(get_db)
):
    cats = ",".join(c for c in categories if c)
    store = int(store_id) if store_id.isdigit() else None
    async with db.execute(
        "INSERT INTO audit_sessions (name, source, categories, store_id) VALUES (?, ?, ?, ?)",
        (name, source, cats, store)
    ) as cur:
        session_id = cur.lastrowid
    await db.commit()
    return RedirectResponse(f"/audit/{session_id}", status_code=303)


@app.get("/stores", response_class=HTMLResponse)
async def stores_page(request: Request, db=Depends(get_db)):
    async with db.execute("""
        SELECT s.*, COUNT(a.id) as count_sessions
        FROM stores s LEFT JOIN audit_sessions a ON a.store_id = s.id
        GROUP BY s.id ORDER BY s.id
    """) as cur:
        stores = await cur.fetchall()
    return templates.TemplateResponse("stores.html", {"request": request, "stores": stores})


@app.post("/api/stores")
async def create_store(name: str = Form(...), address: str = Form(default=""), db=Depends(get_db)):
    name = name.strip()
    if name:
        await db.execute("INSERT INTO stores (name, address) VALUES (?, ?)", (name, address.strip()))
        await db.commit()
    return RedirectResponse("/stores", status_code=303)


@app.post("/api/stores/{store_id}/address")
async def update_store_address(store_id: int, address: str = Form(...), db=Depends(get_db)):
    await db.execute("UPDATE stores SET address=? WHERE id=?", (address.strip(), store_id))
    await db.commit()
    return RedirectResponse("/stores", status_code=303)


@app.post("/api/stores/{store_id}/rename")
async def rename_store(store_id: int, name: str = Form(...), db=Depends(get_db)):
    name = name.strip()
    if name:
        await db.execute("UPDATE stores SET name=? WHERE id=?", (name, store_id))
        await db.commit()
    return RedirectResponse("/stores", status_code=303)


@app.post("/api/stores/{store_id}/delete")
async def delete_store(store_id: int, db=Depends(get_db)):
    await db.execute("DELETE FROM stores WHERE id=?", (store_id,))
    await db.commit()
    return RedirectResponse("/stores", status_code=303)


OVERRIDE_CODE = "GCS2026"


@app.post("/api/sessions/{session_id}/close")
async def close_session(session_id: int, db=Depends(get_db)):
    await db.execute(
        "UPDATE audit_sessions SET status='closed', closed_at=CURRENT_TIMESTAMP WHERE id=?",
        (session_id,)
    )
    await db.commit()
    return RedirectResponse(f"/report/{session_id}", status_code=303)


@app.post("/api/sessions/{session_id}/reopen")
async def reopen_session(session_id: int, override: str = Form(...), db=Depends(get_db)):
    if override.strip() != OVERRIDE_CODE:
        return JSONResponse({"error": "Invalid override code"}, status_code=403)
    await db.execute(
        "UPDATE audit_sessions SET status='active', closed_at=NULL WHERE id=?", (session_id,)
    )
    await db.commit()
    return JSONResponse({"ok": True})


@app.post("/api/scans/{scan_id}/delete")
async def delete_scan(scan_id: int, override: str = Form(...), db=Depends(get_db)):
    if override.strip() != OVERRIDE_CODE:
        return JSONResponse({"error": "Invalid override code"}, status_code=403)
    await db.execute("DELETE FROM audit_scans WHERE id=?", (scan_id,))
    await db.commit()
    return JSONResponse({"ok": True})


@app.post("/api/sessions/{session_id}/findings/delete")
async def delete_all_findings(session_id: int, override: str = Form(...), db=Depends(get_db)):
    """Delete every 'unknown' (findings) scan in this count — for clearing junk scans."""
    if override.strip() != OVERRIDE_CODE:
        return JSONResponse({"error": "Invalid override code"}, status_code=403)
    async with db.execute(
        "DELETE FROM audit_scans WHERE session_id=? AND match_status IN ('unknown','extra')", (session_id,)
    ) as cur:
        deleted = cur.rowcount
    await db.commit()
    return JSONResponse({"ok": True, "deleted": deleted})


@app.post("/api/sessions/{session_id}/rename")
async def rename_session(session_id: int, name: str = Form(...), db=Depends(get_db)):
    name = name.strip()
    if name:
        await db.execute(
            "UPDATE audit_sessions SET name=? WHERE id=?", (name, session_id)
        )
        await db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/api/sessions/{session_id}/delete")
async def delete_session(session_id: int, db=Depends(get_db)):
    # Remove the count and all of its scans
    await db.execute("DELETE FROM audit_scans WHERE session_id=?", (session_id,))
    await db.execute("DELETE FROM audit_sessions WHERE id=?", (session_id,))
    await db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/api/scan")
async def process_scan(
    session_id: int = Form(...),
    code: str = Form(...),
    current_location: str = Form(default=""),
    current_sublocation: str = Form(default=""),
    force_extra: str = Form(default=""),
    units: str = Form(default=""),
    db=Depends(get_db)
):
    code = code.strip().upper()
    kind = classify_scan(code)

    if kind == "location":
        await db.execute(
            "INSERT OR IGNORE INTO locations (id, name) VALUES (?, ?)",
            (code, f"SalesFloor {code}")
        )
        await db.commit()
        async with db.execute("SELECT name FROM locations WHERE id=?", (code,)) as cur:
            row = await cur.fetchone()
        loc_name = (row["name"] if row else "") or f"SalesFloor {code}"
        return JSONResponse({
            "type": "location",
            "location_id": code,
            "location_name": loc_name,
            "sublocation_id": "",
            "message": f"📍 Location {code} — {loc_name}"
        })

    if kind == "sublocation":
        loc_id = code.split("-")[0]
        await db.execute(
            "INSERT OR IGNORE INTO locations (id, name) VALUES (?, ?)",
            (loc_id, f"SalesFloor {loc_id}")
        )
        await db.execute(
            "INSERT OR IGNORE INTO sublocations (id, location_id, name) VALUES (?, ?, ?)",
            (code, loc_id, f"Section {code}")
        )
        await db.commit()
        async with db.execute("SELECT name FROM locations WHERE id=?", (loc_id,)) as cur:
            row = await cur.fetchone()
        loc_name = (row["name"] if row else "") or f"SalesFloor {loc_id}"
        async with db.execute("SELECT name FROM sublocations WHERE id=?", (code,)) as cur:
            row = await cur.fetchone()
        sub_name = (row["name"] if row else "") or f"Section {code}"
        return JSONResponse({
            "type": "sublocation",
            "location_id": loc_id,
            "location_name": loc_name,
            "sublocation_id": code,
            "sublocation_name": sub_name,
            "message": f"📦 {loc_name} › {code}{(' — ' + sub_name) if sub_name != 'Section ' + code else ''}"
        })

    # ── Item scan ─────────────────────────────────────────────────────────────
    if not current_location:
        return JSONResponse({"type": "error", "message": "⚠️ Scan a location first (e.g. 001)"}, status_code=400)

    # Match the scanned code against the Bravo barcode, the UPC, or the item
    # number. Handle both "multiple unit" shapes at once:
    #   • several item rows sharing one barcode/UPC (each row = 1 unit), and
    #   • one bulk row carrying a Quantity of N (N identical physical units).
    # Capacity = sum of Quantity across all matching rows; each scan claims the
    # next unit until capacity is reached, then we prompt to review.
    # Match on barcode / UPC / item number. Also match ignoring leading zeros
    # so a 13-digit EAN scan (leading 0) finds a 12-digit UPC in the file and
    # vice-versa.
    code_z = code.lstrip("0") or code
    async with db.execute(
        "SELECT * FROM items WHERE barcode = ? OR upc = ? OR item_number = ? "
        "OR ltrim(barcode,'0') = ? OR ltrim(upc,'0') = ? OR ltrim(item_number,'0') = ? "
        "ORDER BY item_number",
        (code, code, code, code_z, code_z, code_z)
    ) as cur:
        matches_all = await cur.fetchall()
    # Count only unsold units — the expected population excludes sold items.
    matches = [r for r in matches_all if not (r["sold"] if "sold" in r.keys() else 0)]
    # Known but every matching unit is already sold → flag, don't count as found.
    if not matches and matches_all:
        return JSONResponse({
            "type": "duplicate",
            "barcode": code,
            "message": f"⚠️ {code} is marked SOLD in Bravo — not counted. "
                       f"Un-sell it on the item page if it's still on the floor.",
        })

    def _qty(row):
        raw = re.sub(r"[^0-9]", "", str(row["quantity"] or ""))
        return max(1, int(raw)) if raw else 1

    capacity = sum(_qty(r) for r in matches)
    match_numbers = [r["item_number"] for r in matches]

    # Units of this product already counted (found) in this session
    scanned_so_far = 0
    if match_numbers:
        ph = ",".join("?" for _ in match_numbers)
        async with db.execute(
            f"SELECT COUNT(*) FROM audit_scans WHERE session_id=? AND match_status='found' "
            f"AND item_number IN ({ph})",
            [session_id] + match_numbers
        ) as cur:
            scanned_so_far = (await cur.fetchone())[0]

    # Which catalog row this scan is attributed to — fill each row's quantity
    # before moving on to the next matching row.
    def _attributed_row(n):
        acc = 0
        for r in matches:
            acc += _qty(r)
            if n < acc:
                return r
        return None

    units_n = int(units) if str(units).strip().isdigit() else 0

    # First scan of a multi-unit product → ask how many units they're counting,
    # so bulk items aren't silently double-counted (and duplicate scans can't
    # slip through). Single-unit items skip this and record straight away.
    if matches and capacity > 1 and scanned_so_far == 0 and units_n == 0 and not force_extra:
        return JSONResponse({
            "type": "quantity",
            "barcode": code,
            "description": matches[0]["description"] or code,
            "capacity": capacity,
        })

    # Record N units at once (from the "how many?" prompt).
    if matches and units_n > 0:
        full_ref = "-".join(filter(None, [current_location, current_sublocation, code]))
        found_ct = extra_ct = 0
        for i in range(units_n):
            pos = scanned_so_far + i
            row = _attributed_row(pos)
            if row is not None:
                ms, itn = "found", row["item_number"]
                found_ct += 1
            else:  # beyond catalog quantity → extra units on hand
                row, ms, itn = matches[0], "extra", None
                extra_ct += 1
            await db.execute("""
                INSERT INTO audit_scans
                  (session_id, location_id, sublocation_id, barcode, item_number,
                   full_ref, match_status, description, category, item_status, cost, item_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (session_id, current_location or None, current_sublocation or None, code, itn,
                  full_ref, ms, row["description"], row["category"], row["item_status"],
                  row["cost"], row["item_date"]))
        await db.commit()
        desc = matches[0]["description"] or code
        msg = f"✅ Counted {units_n} × {desc}"
        if extra_ct:
            msg += f" — {extra_ct} beyond catalog of {capacity}"
        return JSONResponse({
            "type": "bulk", "barcode": code, "counted": units_n,
            "found": found_ct, "extra": extra_ct, "message": msg,
        })

    item = None
    extra_unit = False
    if matches:
        if scanned_so_far < capacity:
            item = _attributed_row(scanned_so_far)
        elif force_extra:
            item = matches[0]
            extra_unit = True
        else:
            # Every counted unit is accounted for → prompt to review / add extra
            async with db.execute(
                f"SELECT location_id, sublocation_id FROM audit_scans "
                f"WHERE session_id = ? AND item_number IN ({ph}) ORDER BY id DESC LIMIT 1",
                [session_id] + match_numbers
            ) as cur:
                existing = await cur.fetchone()
            where = (existing["sublocation_id"] or existing["location_id"] or "") if existing else ""
            unit_note = f"all {capacity} units" if capacity > 1 else "already"
            return JSONResponse({
                "type": "review",
                "barcode": code,
                "total_units": capacity,
                "message": f"🔁 {unit_note} scanned in this count{(' (at ' + where + ')') if where else ''}",
            })
    else:
        # Unknown code (not in Bravo): block repeat unknown scans of the same code
        async with db.execute(
            "SELECT location_id, sublocation_id FROM audit_scans WHERE session_id = ? AND barcode = ?",
            (session_id, code)
        ) as cur:
            existing = await cur.fetchone()
        if existing:
            where = existing["sublocation_id"] or existing["location_id"] or "?"
            return JSONResponse({
                "type": "duplicate",
                "barcode": code,
                "message": f"🔁 Already scanned in this count (at {where}) — skipped",
            })

    full_ref = "-".join(filter(None, [current_location, current_sublocation, code]))

    if item is not None and extra_unit:
        # Extra physical unit beyond the catalog quantity — record as a finding
        # tied to this code, without claiming a catalog unit.
        match_status = "extra"
        description = item["description"]
        category = item["category"]
        item_status = item["item_status"]
        cost = item["cost"]
        item_date = item["item_date"]
        item_number = None
        msg = f"➕ EXTRA UNIT recorded — {code} | {description}"
    elif item is not None:
        match_status = "found"
        description = item["description"]
        category = item["category"]
        item_status = item["item_status"]
        cost = item["cost"]
        item_date = item["item_date"]
        item_number = item["item_number"]
        unit_suffix = f" (unit {scanned_so_far + 1} of {capacity})" if capacity > 1 else ""
        msg = f"✅ FOUND — {item['item_number']} | {description}{unit_suffix}"
    else:
        match_status = "unknown"
        description = None
        category = None
        item_status = None
        cost = None
        item_date = None
        item_number = None
        msg = f"⚠️ NOT IN BRAVO — {code}"

    async with db.execute("""
        INSERT INTO audit_scans
          (session_id, location_id, sublocation_id, barcode, item_number,
           full_ref, match_status, description, category, item_status, cost, item_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id,
        current_location or None,
        current_sublocation or None,
        code,
        item_number,
        full_ref,
        match_status,
        description,
        category,
        item_status,
        cost,
        item_date,
    )) as cur:
        scan_id = cur.lastrowid
    await db.commit()

    return JSONResponse({
        "type": "item",
        "scan_id": scan_id,
        "match_status": match_status,
        "barcode": code,
        "item_number": item_number,
        "full_ref": full_ref,
        "description": description or "Not in Bravo",
        "category": category or "",
        "item_status": item_status or "",
        "cost": cost,
        "item_date": item_date or "",
        "message": msg,
    })


@app.get("/api/sessions/{session_id}/scans")
async def get_scans(session_id: int, location_id: str = "", sublocation_id: str = "", db=Depends(get_db)):
    query = "SELECT * FROM audit_scans WHERE session_id = ?"
    params = [session_id]
    if location_id:
        query += " AND location_id = ?"
        params.append(location_id)
    if sublocation_id:
        query += " AND sublocation_id = ?"
        params.append(sublocation_id)
    query += " ORDER BY scanned_at DESC LIMIT 100"
    async with db.execute(query, params) as cur:
        scans = await cur.fetchall()
    return [dict(s) for s in scans]


def parse_bool(val: str) -> int:
    """Interpret a cell as a yes/no flag."""
    return 1 if str(val).strip().lower() in ("yes", "y", "true", "1", "x", "checked", "authentic") else 0


def detect_product_type(chosen: str, jewelry_signal: bool, mfg_signal: bool) -> str:
    if chosen in ("jewelry", "manufactured", "general"):
        return chosen
    if jewelry_signal:
        return "jewelry"
    if mfg_signal:
        return "manufactured"
    return "general"


@app.post("/api/import")
async def import_items(
    file: UploadFile = File(...),
    source: str = Form(default="retail"),
    mode: str = Form(default="add"),
    product_type: str = Form(default="auto"),
    db=Depends(get_db)
):
    try:
        content = await file.read()
    except Exception as e:
        return JSONResponse({"error": f"Could not read file: {e}"}, status_code=400)

    # Reject PDFs and other non-text files up front with a clear message
    if content[:5] == b"%PDF-":
        return JSONResponse({
            "error": "That's a PDF. Please export the Bravo report as CSV or Excel "
                     "(File/Export → CSV) and upload that instead."
        }, status_code=400)
    if content[:2] == b"PK":  # xlsx/zip
        return JSONResponse({
            "error": "That looks like an Excel (.xlsx) file. Please 'Save As' CSV "
                     "in Excel and upload the .csv, or export CSV from Bravo."
        }, status_code=400)

    # Replace mode: clear the existing items for THIS list before importing,
    # so re-uploading a fresh Bravo export doesn't leave stale items behind.
    if mode == "replace":
        await db.execute("DELETE FROM items WHERE source = ?", (source,))
        await db.commit()

    # Bravo exports are usually Windows-1252, not UTF-8. Try encodings in order.
    text = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = content.decode("utf-8", errors="replace")

    # Bravo can export tab-, comma-, or semicolon-separated. Detect which.
    first_line = text.split("\n", 1)[0]
    if "\t" in first_line:
        delimiter = "\t"
    elif ";" in first_line and first_line.count(";") >= first_line.count(","):
        delimiter = ";"
    else:
        delimiter = ","

    try:
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        columns_found = reader.fieldnames or []
        inserted = 0     # new items
        updated = 0      # existing items refreshed
        skipped = 0
        seen_codes = []  # item numbers present in this file
        barcode_conflicts = []  # rows imported without barcode (already taken)

        for row in reader:
            item_number = find_column(row, "Number", "Item #", "Item Number", "ItemNumber")
            barcode = find_column(row, "Barcode", "Barcode Number", "SKU")
            # UPC is a distinct code (bulk-uploaded items may carry a UPC and no
            # Bravo barcode). Kept separate so scanning can match either.
            upc = find_column(row, "UPC", "UPC Code", "UPCCode", "UPC Number", "GTIN", "EAN")
            if not upc:
                # Fallback: any header that contains "upc"/"gtin"/"ean"
                # (e.g. "UPC #", "Item UPC", "Product UPC Code").
                for k, v in row.items():
                    if k and any(t in str(k).lower() for t in ("upc", "gtin", "ean")) and str(v).strip():
                        upc = str(v).strip()
                        break
            # Recover full digits from Excel scientific notation / quoting.
            # (Alphanumeric item numbers like AB1007081 pass through unchanged.)
            item_number = expand_code(item_number)
            upc = expand_code(upc)
            barcode = expand_code(barcode)
            # A row with no item number (e.g. a UPC-only bulk line) still needs a
            # stable primary key so re-imports merge instead of inserting NULL-PK
            # duplicates. Fall back to the barcode, then the UPC.
            if not item_number:
                item_number = barcode or upc or ""
            description = find_column(row, "Description", "Item Description", "Desc")
            category = find_column(row, "Category", "Cat")
            item_type = find_column(row, "Type")
            item_status = find_column(row, "Status")
            cost_raw = find_column(row, "Cost", "Amount")
            price_raw = find_column(
                row, "Price", "Retail Price", "Sale Price", "Selling Price",
                "Retail", "List Price", "List", "Sell Price", "Asking Price",
                "Ask", "Tag Price", "Price Each"
            )
            item_date = find_column(row, "Date", "Date In", "Created")

            # Jewelry fields (match exact Bravo headers)
            total_diamond = find_column(row, "Total Diamond Size", "Total Diamond", "Total Diamonds", "Diamond")
            metal_type = find_column(row, "Metal Type/Color", "Metal Type", "Metal", "MetalType")
            metal_color = find_column(row, "Metal Color", "Color Metal", "MetalColor")
            total_stone_size = find_column(row, "Total Stone Size", "Stone Size", "TotalStoneSize")
            condition = find_column(row, "Condition", "Cond", "Quality")
            metal_purity = find_column(row, "Metal Purity", "Purity")
            total_jewelry_weight = find_column(row, "Total Jewelry Weight", "Jewelry Weight")
            metal_weight = find_column(row, "Metal Weight")
            quality = find_column(row, "Quality")
            diamond_auth_raw = find_column(row, "Authentic-Diamond Jewelry", "Authentic Diamond Color",
                                           "Diamond Authentic", "Authentic Diamond")
            stone_auth_raw = find_column(row, "Authentic-Stone Jewelry", "Authentic Stone", "Stone Authentic")
            # Manufactured fields
            serial_number = find_column(row, "Serial Number", "Serial", "SerialNumber", "S/N")
            manufacturer = find_column(row, "Manufacturer", "Manufacture", "Maker", "Brand")
            model = find_column(row, "Model", "Model Number", "Model No")
            quantity = find_column(row, "Quantity", "Qty")
            vendor = find_column(row, "Vendor", "Supplier")
            inventory_age = find_column(row, "Inventory Age", "Age", "Days in Inventory")
            date_to_inventory = find_column(row, "Date to Inventory", "Date In", "Received")

            if not item_number and not barcode and not upc:
                skipped += 1
                continue

            # Skip report footer/header junk rows (e.g. "REPORT PRINTED ON ...",
            # "Page 1 of 13"). Real item numbers have no spaces and aren't sentences.
            junk = item_number and (
                " " in item_number
                or item_number.upper().startswith(("REPORT", "TOTAL", "PAGE", "PRINTED"))
            )
            if junk:
                skipped += 1
                continue

            item_number_u = item_number.upper() if item_number else None
            cost_val = clean_money(cost_raw)
            # Sale price comes from the CSV "Price" column; None if blank so a
            # manually-set price is preserved on re-upload.
            retail_val = clean_money(price_raw) if price_raw else None
            diamond_authentic = parse_bool(diamond_auth_raw)
            authentic_stone = parse_bool(stone_auth_raw)

            jewelry_signal = bool(total_diamond or metal_type or metal_color or total_stone_size
                                  or metal_purity or total_jewelry_weight or metal_weight)
            mfg_signal = bool(serial_number or manufacturer or model)
            ptype = detect_product_type(product_type, jewelry_signal, mfg_signal)

            if item_number_u:
                seen_codes.append(item_number_u)

            # Does it already exist? (decides new vs updated, and preserves admin fields)
            async with db.execute("SELECT item_number FROM items WHERE item_number = ?", (item_number_u,)) as cur:
                exists = await cur.fetchone() is not None

            # Derive a barcode from the item number ONLY for brand-new items —
            # never overwrite an existing item's real barcode with derived digits.
            if not barcode and item_number and not exists:
                barcode = re.sub(r"[^0-9]", "", item_number)
            barcode_u = barcode.upper() if barcode else None

            # NOTE: multiple units of the same product may share one barcode —
            # that's allowed. Each unit keeps its own item number.

            # UPSERT as a MERGE: on an existing item, only overwrite a field when
            # the new file actually has a value for it — blanks never wipe data.
            # Admin fields (retail_price, photo, for_sale, sold, product_type once
            # set) are preserved. Status/date DO refresh when provided.
            cost_in = cost_val if cost_raw else None
            dia_auth_in = diamond_authentic if diamond_auth_raw else None
            stone_auth_in = authentic_stone if stone_auth_raw else None
            await db.execute("""
                INSERT INTO items
                  (item_number, barcode, upc, description, category, item_type, item_status,
                   cost, retail_price, item_date, source, product_type, total_diamond, metal_type,
                   metal_color, total_stone_size, condition, diamond_authentic,
                   serial_number, manufacturer, model, metal_purity, total_jewelry_weight,
                   metal_weight, quality, authentic_stone, quantity, vendor,
                   inventory_age, date_to_inventory, missing)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(item_number) DO UPDATE SET
                   barcode=COALESCE(NULLIF(excluded.barcode,''), items.barcode),
                   upc=COALESCE(NULLIF(excluded.upc,''), items.upc),
                   description=COALESCE(NULLIF(excluded.description,''), items.description),
                   category=COALESCE(NULLIF(excluded.category,''), items.category),
                   item_type=COALESCE(NULLIF(excluded.item_type,''), items.item_type),
                   item_status=COALESCE(NULLIF(excluded.item_status,''), items.item_status),
                   cost=COALESCE(excluded.cost, items.cost),
                   retail_price=COALESCE(excluded.retail_price, items.retail_price),
                   item_date=COALESCE(NULLIF(excluded.item_date,''), items.item_date),
                   source=COALESCE(NULLIF(excluded.source,''), items.source),
                   product_type=COALESCE(NULLIF(items.product_type,''), excluded.product_type),
                   total_diamond=COALESCE(NULLIF(excluded.total_diamond,''), items.total_diamond),
                   metal_type=COALESCE(NULLIF(excluded.metal_type,''), items.metal_type),
                   metal_color=COALESCE(NULLIF(excluded.metal_color,''), items.metal_color),
                   total_stone_size=COALESCE(NULLIF(excluded.total_stone_size,''), items.total_stone_size),
                   condition=COALESCE(NULLIF(excluded.condition,''), items.condition),
                   diamond_authentic=COALESCE(excluded.diamond_authentic, items.diamond_authentic),
                   serial_number=COALESCE(NULLIF(excluded.serial_number,''), items.serial_number),
                   manufacturer=COALESCE(NULLIF(excluded.manufacturer,''), items.manufacturer),
                   model=COALESCE(NULLIF(excluded.model,''), items.model),
                   metal_purity=COALESCE(NULLIF(excluded.metal_purity,''), items.metal_purity),
                   total_jewelry_weight=COALESCE(NULLIF(excluded.total_jewelry_weight,''), items.total_jewelry_weight),
                   metal_weight=COALESCE(NULLIF(excluded.metal_weight,''), items.metal_weight),
                   quality=COALESCE(NULLIF(excluded.quality,''), items.quality),
                   authentic_stone=COALESCE(excluded.authentic_stone, items.authentic_stone),
                   quantity=COALESCE(NULLIF(excluded.quantity,''), items.quantity),
                   vendor=COALESCE(NULLIF(excluded.vendor,''), items.vendor),
                   inventory_age=COALESCE(NULLIF(excluded.inventory_age,''), items.inventory_age),
                   date_to_inventory=COALESCE(NULLIF(excluded.date_to_inventory,''), items.date_to_inventory),
                   missing=0
            """, (
                item_number_u, barcode_u, (upc.upper() if upc else None), description, category, item_type, item_status,
                cost_in, retail_val, item_date, source, ptype, total_diamond, metal_type,
                metal_color, total_stone_size, condition, dia_auth_in,
                serial_number, manufacturer, model, metal_purity, total_jewelry_weight,
                metal_weight, quality, stone_auth_in, quantity, vendor,
                inventory_age, date_to_inventory,
            ))
            if exists:
                updated += 1
            else:
                inserted += 1

        # Record this upload first so we can tie the reconciliation log to it
        async with db.execute(
            "INSERT INTO imports (source, filename, item_count, mode) VALUES (?, ?, ?, ?)",
            (source, file.filename or "", inserted + updated, mode)
        ) as cur:
            import_id = cur.lastrowid

        # Reconciliation: items in this list not in the file and not already sold.
        missing_count = 0
        newly_missing_groups = {"Jewelry": 0, "Manufactured": 0}
        if seen_codes:
            placeholders = ",".join("?" for _ in seen_codes)
            # Newly-disappeared items (were present before, missing=0) → log them
            async with db.execute(
                f"SELECT item_number, barcode, description, category, cost, retail_price, "
                f"       product_type FROM items "
                f"WHERE source=? AND sold=0 AND COALESCE(missing,0)=0 "
                f"AND item_number NOT IN ({placeholders})",
                [source] + seen_codes
            ) as cur:
                newly_missing = await cur.fetchall()
            overrides = await load_group_overrides(db)
            flagged_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for m in newly_missing:
                g = big_group(m, overrides)
                newly_missing_groups[g] = newly_missing_groups.get(g, 0) + 1
                await db.execute(
                    "INSERT INTO reconcile_log (import_id, item_number, barcode, description, "
                    "category, big_group, cost, retail_price, source, flagged_at, status) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'missing')",
                    (import_id, m["item_number"], m["barcode"], m["description"], m["category"],
                     g, m["cost"], m["retail_price"], source, flagged_at)
                )
            # Flag all not-in-file as missing (count = total currently missing this list)
            await db.execute(
                f"UPDATE items SET missing=1 WHERE source=? AND sold=0 "
                f"AND item_number NOT IN ({placeholders})",
                [source] + seen_codes
            )
            async with db.execute(
                f"SELECT COUNT(*) FROM items WHERE source=? AND sold=0 "
                f"AND item_number NOT IN ({placeholders})",
                [source] + seen_codes
            ) as cur:
                missing_count = (await cur.fetchone())[0]

        await db.commit()
    except Exception as e:
        return JSONResponse({
            "error": f"Could not read this file as a spreadsheet. Make sure it's a "
                     f"CSV exported from Bravo (not a PDF or Word doc). Details: {e}"
        }, status_code=400)

    # Automatic daily backup tied to each upload
    make_daily_backup()

    # Category breakdown of everything currently in the database
    async with db.execute("""
        SELECT COALESCE(NULLIF(category,''), 'Uncategorized') as category, COUNT(*) as cnt
        FROM items GROUP BY category ORDER BY cnt DESC
    """) as cur:
        categories = [dict(r) for r in await cur.fetchall()]

    return JSONResponse({
        "imported": inserted,
        "updated": updated,
        "missing": missing_count,
        "newly_missing": sum(newly_missing_groups.values()),
        "newly_missing_groups": newly_missing_groups,
        "skipped": skipped,
        "barcode_conflicts": barcode_conflicts,
        "columns_found": columns_found,
        "categories": categories,
    })


@app.get("/barcode/{code}")
async def generate_barcode(code: str, height: int = 40, text: int = 1, mw: float = 0.0):
    """Return an SVG barcode image for any code string.

    mw = module width in mm (bar thickness). Larger = wider, easier to scan.
    Defaults to 0.5mm which is comfortably scannable when printed at 100%.
    """
    code = code.strip().upper()
    buf = io.BytesIO()
    module_width = mw if mw > 0 else 0.5
    options = {
        "module_width": module_width,
        "module_height": height,
        "font_size": 8 if text else 0,
        "text_distance": 3 if text else 0,
        "quiet_zone": 6,
        "write_text": bool(text),
    }
    cache = {"Cache-Control": "public, max-age=604800, immutable"}
    try:
        Code128 = barcode.get_barcode_class("code128")
        bc = Code128(code, writer=SVGWriter())
        bc.write(buf, options=options)
    except Exception:
        # Fallback: plain text if barcode generation fails
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="50"><text y="30" font-size="12">{code}</text></svg>'
        return Response(content=svg, media_type="image/svg+xml", headers=cache)

    return Response(content=buf.getvalue(), media_type="image/svg+xml", headers=cache)


@app.post("/api/locations")
async def create_location(
    location_id: str = Form(...),
    name: str = Form(...),
    photo: UploadFile = File(default=None),
    db=Depends(get_db)
):
    location_id = location_id.upper()
    photo_name = await save_photo(photo, f"loc_{location_id}")

    if photo_name:
        await db.execute(
            "INSERT OR REPLACE INTO locations (id, name, photo) VALUES (?, ?, ?)",
            (location_id, name, photo_name)
        )
    else:
        # Preserve existing photo if updating without a new upload
        await db.execute(
            """INSERT INTO locations (id, name, photo) VALUES (?, ?, '')
               ON CONFLICT(id) DO UPDATE SET name=excluded.name""",
            (location_id, name)
        )
    await db.commit()
    return RedirectResponse("/locations", status_code=303)


@app.post("/api/sublocations")
async def create_sublocation(
    location_id: str = Form(...),
    section: str = Form(...),
    name: str = Form(default=""),
    photo: UploadFile = File(default=None),
    db=Depends(get_db)
):
    location_id = location_id.strip().upper()
    section = section.strip()
    sub_id = f"{location_id}-{section}"
    photo_name = await save_photo(photo, f"sub_{sub_id}")
    # Make sure the parent location exists
    await db.execute(
        "INSERT OR IGNORE INTO locations (id, name) VALUES (?, ?)",
        (location_id, f"SalesFloor {location_id}")
    )
    await db.execute(
        "INSERT OR REPLACE INTO sublocations (id, location_id, name, photo) VALUES (?, ?, ?, ?)",
        (sub_id, location_id, name or f"Section {sub_id}", photo_name)
    )
    await db.commit()
    return RedirectResponse("/locations", status_code=303)


async def _rebuild_full_refs(db, session_ids=None):
    """Recompute full_ref for scans from location_id, sublocation_id, barcode."""
    async with db.execute("SELECT id, location_id, sublocation_id, barcode FROM audit_scans") as cur:
        rows = await cur.fetchall()
    for r in rows:
        ref = "-".join(x for x in (r["location_id"], r["sublocation_id"], r["barcode"]) if x)
        await db.execute("UPDATE audit_scans SET full_ref=? WHERE id=?", (ref, r["id"]))


# ── Location edit ───────────────────────────────────────────────────────────

@app.get("/locations/{location_id}/edit", response_class=HTMLResponse)
async def edit_location_page(request: Request, location_id: str, db=Depends(get_db)):
    async with db.execute("SELECT * FROM locations WHERE id=?", (location_id,)) as cur:
        loc = await cur.fetchone()
    if not loc:
        raise HTTPException(404)
    return templates.TemplateResponse("edit_location.html", {"request": request, "loc": loc})


@app.post("/api/locations/{location_id}/edit")
async def edit_location(
    location_id: str,
    name: str = Form(...),
    new_id: str = Form(default=""),
    photo: UploadFile = File(default=None),
    db=Depends(get_db)
):
    name = name.strip()
    new_id = (new_id or location_id).strip().upper()

    # If the ID (barcode) changed, cascade to sublocations and scans
    if new_id != location_id:
        await db.execute("UPDATE locations SET id=? WHERE id=?", (new_id, location_id))
        # Sublocations: update parent + their id prefix (001-1 -> 002-1)
        async with db.execute("SELECT id FROM sublocations WHERE location_id=?", (location_id,)) as cur:
            subs = await cur.fetchall()
        for s in subs:
            new_sub = new_id + s["id"][len(location_id):]
            await db.execute("UPDATE sublocations SET id=?, location_id=? WHERE id=?",
                             (new_sub, new_id, s["id"]))
            await db.execute("UPDATE audit_scans SET sublocation_id=? WHERE sublocation_id=?",
                             (new_sub, s["id"]))
        await db.execute("UPDATE audit_scans SET location_id=? WHERE location_id=?", (new_id, location_id))
        await _rebuild_full_refs(db)

    photo_name = await save_photo(photo, f"loc_{new_id}")
    if photo_name:
        await db.execute("UPDATE locations SET name=?, photo=? WHERE id=?", (name, photo_name, new_id))
    else:
        await db.execute("UPDATE locations SET name=? WHERE id=?", (name, new_id))
    await db.commit()
    return RedirectResponse("/locations", status_code=303)


@app.post("/api/locations/{location_id}/delete")
async def delete_location(location_id: str, db=Depends(get_db)):
    await db.execute("DELETE FROM sublocations WHERE location_id=?", (location_id,))
    await db.execute("DELETE FROM locations WHERE id=?", (location_id,))
    await db.commit()
    return RedirectResponse("/locations", status_code=303)


# ── Sublocation edit ────────────────────────────────────────────────────────

@app.get("/sublocations/{sub_id:path}/edit", response_class=HTMLResponse)
async def edit_sublocation_page(request: Request, sub_id: str, db=Depends(get_db)):
    async with db.execute("SELECT * FROM sublocations WHERE id=?", (sub_id,)) as cur:
        sub = await cur.fetchone()
    if not sub:
        raise HTTPException(404)
    return templates.TemplateResponse("edit_sublocation.html", {"request": request, "sub": sub})


@app.post("/api/sublocations/{sub_id:path}/edit")
async def edit_sublocation(
    sub_id: str,
    name: str = Form(...),
    new_section: str = Form(default=""),
    photo: UploadFile = File(default=None),
    db=Depends(get_db)
):
    name = name.strip()
    async with db.execute("SELECT location_id FROM sublocations WHERE id=?", (sub_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404)
    loc_id = row["location_id"]

    new_id = sub_id
    if new_section.strip():
        new_id = f"{loc_id}-{new_section.strip()}"
    if new_id != sub_id:
        await db.execute("UPDATE sublocations SET id=? WHERE id=?", (new_id, sub_id))
        await db.execute("UPDATE audit_scans SET sublocation_id=? WHERE sublocation_id=?", (new_id, sub_id))
        await _rebuild_full_refs(db)

    photo_name = await save_photo(photo, f"sub_{new_id}")
    if photo_name:
        await db.execute("UPDATE sublocations SET name=?, photo=? WHERE id=?", (name, photo_name, new_id))
    else:
        await db.execute("UPDATE sublocations SET name=? WHERE id=?", (name, new_id))
    await db.commit()
    return RedirectResponse("/locations", status_code=303)


@app.post("/api/sublocations/{sub_id:path}/delete")
async def delete_sublocation(sub_id: str, db=Depends(get_db)):
    await db.execute("DELETE FROM sublocations WHERE id=?", (sub_id,))
    await db.commit()
    return RedirectResponse("/locations", status_code=303)
