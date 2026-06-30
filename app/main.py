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


app = FastAPI(lifespan=lifespan, title="ABC Pawnshop Inventory")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
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


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db=Depends(get_db)):
    async with db.execute("SELECT * FROM audit_sessions ORDER BY created_at DESC") as cur:
        sessions = await cur.fetchall()
    async with db.execute("SELECT COUNT(*) as cnt FROM items") as cur:
        item_count = (await cur.fetchone())["cnt"]
    return templates.TemplateResponse("index.html", {
        "request": request,
        "sessions": sessions,
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

    # Items in Bravo that were NOT scanned in this session
    async with db.execute("""
        SELECT i.item_number, i.barcode, i.description, i.category, i.item_status, i.cost
        FROM items i
        WHERE i.barcode NOT IN (
            SELECT barcode FROM audit_scans WHERE session_id = ? AND match_status = 'found'
        )
        ORDER BY i.item_number
    """, (session_id,)) as cur:
        missing = await cur.fetchall()

    found_count = sum(1 for s in scans if s["match_status"] == "found")
    unknown_count = sum(1 for s in scans if s["match_status"] == "unknown")

    return templates.TemplateResponse("report.html", {
        "request": request,
        "session": session,
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
async def create_session(name: str = Form(...), db=Depends(get_db)):
    async with db.execute("INSERT INTO audit_sessions (name) VALUES (?)", (name,)) as cur:
        session_id = cur.lastrowid
    await db.commit()
    return RedirectResponse(f"/audit/{session_id}", status_code=303)


@app.post("/api/sessions/{session_id}/close")
async def close_session(session_id: int, db=Depends(get_db)):
    await db.execute(
        "UPDATE audit_sessions SET status='closed', closed_at=CURRENT_TIMESTAMP WHERE id=?",
        (session_id,)
    )
    await db.commit()
    return RedirectResponse(f"/report/{session_id}", status_code=303)


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
    db=Depends(get_db)
):
    content = await file.read()
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
    reader = csv.DictReader(io.StringIO(text))
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
        # Bravo pattern: AB1007081 → barcode contains 1007081 → padded as 2000007081
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

    await db.commit()
    return JSONResponse({"imported": inserted, "skipped": skipped})


@app.get("/barcode/{code}")
async def generate_barcode(code: str, height: int = 40, text: int = 1):
    """Return an SVG barcode image for any code string."""
    code = code.strip().upper()
    buf = io.BytesIO()
    options = {
        "module_height": height,
        "font_size": 8 if text else 0,
        "text_distance": 3 if text else 0,
        "quiet_zone": 3,
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
async def create_location(location_id: str = Form(...), name: str = Form(...), db=Depends(get_db)):
    await db.execute(
        "INSERT OR REPLACE INTO locations (id, name) VALUES (?, ?)",
        (location_id.upper(), name)
    )
    await db.commit()
    return RedirectResponse("/locations", status_code=303)


@app.post("/api/sublocations")
async def create_sublocation(
    location_id: str = Form(...),
    section: str = Form(...),
    name: str = Form(default=""),
    db=Depends(get_db)
):
    location_id = location_id.strip().upper()
    section = section.strip()
    sub_id = f"{location_id}-{section}"
    # Make sure the parent location exists
    await db.execute(
        "INSERT OR IGNORE INTO locations (id, name) VALUES (?, ?)",
        (location_id, f"SalesFloor {location_id}")
    )
    await db.execute(
        "INSERT OR REPLACE INTO sublocations (id, location_id, name) VALUES (?, ?, ?)",
        (sub_id, location_id, name or f"Section {sub_id}")
    )
    await db.commit()
    return RedirectResponse("/locations", status_code=303)
