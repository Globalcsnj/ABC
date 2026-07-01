from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import aiosqlite
import barcode
from barcode.writer import SVGWriter
import csv
import io
import os
import re
from contextlib import asynccontextmanager
from .database import init_db, get_db, DB_PATH

BASE_DIR = os.path.dirname(os.path.dirname(__file__))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


UPLOAD_DIR = os.path.join(BASE_DIR, "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(lifespan=lifespan, title="ABC Pawnshop Inventory")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def classify_scan(code: str):
    """Location: 3 digits. Sublocation: 3 digits dash number. Item: everything else."""
    if re.fullmatch(r"\d{3}", code.strip()):
        return "location"
    if re.fullmatch(r"\d{3}-\d+", code.strip()):
        return "sublocation"
    return "item"


def clean_money(val: str) -> float:
    try:
        return float(str(val).replace("$", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0.0


def find_column(row: dict, *candidates):
    """Return first matching column value (case-insensitive)."""
    row_lower = {k.lower().strip(): v for k, v in row.items()}
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
    })


@app.get("/audit/{session_id}", response_class=HTMLResponse)
async def audit_page(request: Request, session_id: int, db=Depends(get_db)):
    async with db.execute("SELECT * FROM audit_sessions WHERE id = ?", (session_id,)) as cur:
        session = await cur.fetchone()
    if not session:
        raise HTTPException(404, "Session not found")
    return templates.TemplateResponse("audit.html", {"request": request, "session": session})


@app.get("/report/{session_id}", response_class=HTMLResponse)
async def report_page(request: Request, session_id: int, db=Depends(get_db)):
    async with db.execute("SELECT * FROM audit_sessions WHERE id = ?", (session_id,)) as cur:
        session = await cur.fetchone()
    if not session:
        raise HTTPException(404)

    async with db.execute("""
        SELECT s.*, i.item_number as bravo_number
        FROM audit_scans s
        LEFT JOIN items i ON i.barcode = s.barcode
        WHERE s.session_id = ?
        ORDER BY s.location_id, s.sublocation_id, s.scanned_at
    """, (session_id,)) as cur:
        scans = await cur.fetchall()

    async with db.execute("""
        SELECT location_id, sublocation_id, COUNT(*) as total,
               SUM(CASE WHEN match_status='found' THEN 1 ELSE 0 END) as found,
               SUM(CASE WHEN match_status='unknown' THEN 1 ELSE 0 END) as unknown
        FROM audit_scans WHERE session_id = ?
        GROUP BY location_id, sublocation_id
        ORDER BY location_id, sublocation_id
    """, (session_id,)) as cur:
        summary = await cur.fetchall()

    # Items expected for this count (respecting the session's list + categories)
    # that were NOT scanned. session may have source and categories filters.
    missing_query = """
        SELECT i.item_number, i.barcode, i.description, i.category, i.item_status, i.cost
        FROM items i
        WHERE i.barcode NOT IN (
            SELECT barcode FROM audit_scans WHERE session_id = ? AND match_status = 'found'
        )
    """
    missing_params = [session_id]
    sess_source = session["source"] if "source" in session.keys() else ""
    sess_cats = session["categories"] if "categories" in session.keys() else ""
    if sess_source:
        missing_query += " AND i.source = ?"
        missing_params.append(sess_source)
    if sess_cats:
        cat_list = [c for c in sess_cats.split(",") if c]
        if cat_list:
            placeholders = ",".join("?" for _ in cat_list)
            # Match by category, treating empty category as 'Uncategorized'
            missing_query += f" AND COALESCE(NULLIF(i.category,''),'Uncategorized') IN ({placeholders})"
            missing_params.extend(cat_list)
    missing_query += " ORDER BY i.item_number"
    async with db.execute(missing_query, missing_params) as cur:
        missing = await cur.fetchall()

    found_count = sum(1 for s in scans if s["match_status"] == "found")
    unknown_count = sum(1 for s in scans if s["match_status"] == "unknown")

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
        "found_count": found_count,
        "unknown_count": unknown_count,
        "missing_count": len(missing),
    })


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


@app.get("/inventory", response_class=HTMLResponse)
async def inventory_page(request: Request, q: str = "", db=Depends(get_db)):
    if q:
        like = f"%{q}%"
        query = """
            SELECT * FROM items
            WHERE item_number LIKE ? OR barcode LIKE ? OR description LIKE ? OR category LIKE ?
            ORDER BY item_number LIMIT 500
        """
        params = [like, like, like, like]
    else:
        query = "SELECT * FROM items ORDER BY item_number LIMIT 500"
        params = []
    async with db.execute(query, params) as cur:
        items = await cur.fetchall()
    async with db.execute("SELECT COUNT(*) as cnt FROM items") as cur:
        total = (await cur.fetchone())["cnt"]
    async with db.execute("""
        SELECT COALESCE(NULLIF(category,''), 'Uncategorized') as category, COUNT(*) as cnt
        FROM items GROUP BY category ORDER BY cnt DESC
    """) as cur:
        categories = [dict(r) for r in await cur.fetchall()]
    # Latest active session so the user can jump straight into scanning
    async with db.execute(
        "SELECT id FROM audit_sessions WHERE status='active' ORDER BY created_at DESC LIMIT 1"
    ) as cur:
        active = await cur.fetchone()
    return templates.TemplateResponse("inventory.html", {
        "request": request,
        "items": items,
        "total": total,
        "showing": len(items),
        "q": q,
        "categories": categories,
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
async def create_store(name: str = Form(...), db=Depends(get_db)):
    name = name.strip()
    if name:
        await db.execute("INSERT INTO stores (name) VALUES (?)", (name,))
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


@app.post("/api/sessions/{session_id}/close")
async def close_session(session_id: int, db=Depends(get_db)):
    await db.execute(
        "UPDATE audit_sessions SET status='closed', closed_at=CURRENT_TIMESTAMP WHERE id=?",
        (session_id,)
    )
    await db.commit()
    return RedirectResponse(f"/report/{session_id}", status_code=303)


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
        return JSONResponse({
            "type": "location",
            "location_id": code,
            "sublocation_id": "",
            "message": f"📍 Location: SalesFloor {code}"
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
        return JSONResponse({
            "type": "sublocation",
            "location_id": loc_id,
            "sublocation_id": code,
            "message": f"📦 Sublocation: {code}"
        })

    # ── Item scan ─────────────────────────────────────────────────────────────
    if not current_location:
        return JSONResponse({"type": "error", "message": "⚠️ Scan a location first (e.g. 001)"}, status_code=400)

    # Prevent duplicate scans of the same item within this count
    async with db.execute(
        "SELECT location_id, sublocation_id FROM audit_scans WHERE session_id = ? AND barcode = ?",
        (session_id, code)
    ) as cur:
        existing = await cur.fetchone()
    if existing:
        where = existing["location_id"] or "?"
        if existing["sublocation_id"]:
            where = existing["sublocation_id"]
        return JSONResponse({
            "type": "duplicate",
            "barcode": code,
            "message": f"🔁 Already scanned in this count (at {where}) — skipped",
        })

    # Lookup by barcode in items table
    async with db.execute(
        "SELECT * FROM items WHERE barcode = ?", (code,)
    ) as cur:
        item = await cur.fetchone()

    full_ref = "-".join(filter(None, [current_location, current_sublocation, code]))

    if item:
        match_status = "found"
        description = item["description"]
        category = item["category"]
        item_status = item["item_status"]
        cost = item["cost"]
        item_date = item["item_date"]
        item_number = item["item_number"]
        msg = f"✅ FOUND — {item['item_number']} | {description}"
    else:
        match_status = "unknown"
        description = None
        category = None
        item_status = None
        cost = None
        item_date = None
        item_number = None
        msg = f"⚠️ NOT IN BRAVO — {code}"

    await db.execute("""
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
    ))
    await db.commit()

    return JSONResponse({
        "type": "item",
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


@app.post("/api/import")
async def import_items(
    file: UploadFile = File(...),
    source: str = Form(default="retail"),
    mode: str = Form(default="add"),
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
        inserted = 0
        skipped = 0

        for row in reader:
            # Bravo column names from the screenshot
            item_number = find_column(row, "Number", "Item #", "Item Number", "ItemNumber")
            barcode = find_column(row, "Barcode", "Barcode Number", "UPC", "SKU")
            description = find_column(row, "Description", "Item Description", "Desc")
            category = find_column(row, "Category", "Cat")
            item_type = find_column(row, "Type")
            item_status = find_column(row, "Status")
            cost_raw = find_column(row, "Cost", "Price", "Retail Price", "Amount")
            item_date = find_column(row, "Date", "Date In", "Created")

            if not item_number and not barcode:
                skipped += 1
                continue

            # If no barcode column, try to derive from item number
            # Bravo pattern: AB1007081 → barcode contains 1007081
            if not barcode and item_number:
                digits = re.sub(r"[^0-9]", "", item_number)
                barcode = digits  # store raw digits; scanner will send full barcode

            cost_val = clean_money(cost_raw)

            await db.execute("""
                INSERT OR REPLACE INTO items
                  (item_number, barcode, description, category, item_type, item_status, cost, item_date, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item_number.upper() if item_number else None,
                barcode.upper() if barcode else None,
                description,
                category,
                item_type,
                item_status,
                cost_val,
                item_date,
                source,
            ))
            inserted += 1

        # Record this upload in the import history
        await db.execute(
            "INSERT INTO imports (source, filename, item_count, mode) VALUES (?, ?, ?, ?)",
            (source, file.filename or "", inserted, mode)
        )
        await db.commit()
    except Exception as e:
        return JSONResponse({
            "error": f"Could not read this file as a spreadsheet. Make sure it's a "
                     f"CSV exported from Bravo (not a PDF or Word doc). Details: {e}"
        }, status_code=400)

    # Category breakdown of everything currently in the database
    async with db.execute("""
        SELECT COALESCE(NULLIF(category,''), 'Uncategorized') as category, COUNT(*) as cnt
        FROM items GROUP BY category ORDER BY cnt DESC
    """) as cur:
        categories = [dict(r) for r in await cur.fetchall()]

    return JSONResponse({
        "imported": inserted,
        "skipped": skipped,
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
    try:
        Code128 = barcode.get_barcode_class("code128")
        bc = Code128(code, writer=SVGWriter())
        bc.write(buf, options=options)
    except Exception:
        # Fallback: plain text if barcode generation fails
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="50"><text y="30" font-size="12">{code}</text></svg>'
        return Response(content=svg, media_type="image/svg+xml")

    return Response(content=buf.getvalue(), media_type="image/svg+xml")


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
