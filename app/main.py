from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import aiosqlite
import csv
import io
import os
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


# ── Helpers ──────────────────────────────────────────────────────────────────

def classify_scan(code: str):
    """Determine if a scan is a location, sublocation, or item.

    Location:    matches \d{3}  e.g. 001
    Sublocation: matches \d{3}-\d+  e.g. 001-1
    Item:        anything else
    """
    import re
    if re.fullmatch(r"\d{3}", code.strip()):
        return "location"
    if re.fullmatch(r"\d{3}-\d+", code.strip()):
        return "sublocation"
    return "item"


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db=Depends(get_db)):
    async with db.execute("SELECT * FROM audit_sessions ORDER BY created_at DESC") as cur:
        sessions = await cur.fetchall()
    return templates.TemplateResponse("index.html", {"request": request, "sessions": sessions})


@app.get("/audit/{session_id}", response_class=HTMLResponse)
async def audit_page(request: Request, session_id: int, db=Depends(get_db)):
    async with db.execute("SELECT * FROM audit_sessions WHERE id = ?", (session_id,)) as cur:
        session = await cur.fetchone()
    if not session:
        raise HTTPException(404, "Session not found")
    async with db.execute("SELECT * FROM locations ORDER BY id") as cur:
        locations = await cur.fetchall()
    return templates.TemplateResponse("audit.html", {
        "request": request,
        "session": session,
        "locations": locations,
    })


@app.get("/report/{session_id}", response_class=HTMLResponse)
async def report_page(request: Request, session_id: int, db=Depends(get_db)):
    async with db.execute("SELECT * FROM audit_sessions WHERE id = ?", (session_id,)) as cur:
        session = await cur.fetchone()
    async with db.execute("""
        SELECT s.full_ref, s.item_code, s.description, s.scanned_at,
               s.location_id, s.sublocation_id
        FROM audit_scans s
        WHERE s.session_id = ?
        ORDER BY s.location_id, s.sublocation_id, s.scanned_at
    """, (session_id,)) as cur:
        scans = await cur.fetchall()
    async with db.execute("""
        SELECT location_id, sublocation_id, COUNT(*) as cnt
        FROM audit_scans WHERE session_id = ?
        GROUP BY location_id, sublocation_id
        ORDER BY location_id, sublocation_id
    """, (session_id,)) as cur:
        summary = await cur.fetchall()
    return templates.TemplateResponse("report.html", {
        "request": request,
        "session": session,
        "scans": scans,
        "summary": summary,
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
    return templates.TemplateResponse("locations.html", {"request": request, "locations": locations})


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
        # Auto-create location if new
        await db.execute(
            "INSERT OR IGNORE INTO locations (id, name) VALUES (?, ?)",
            (code, f"SalesFloor {code}")
        )
        await db.commit()
        return JSONResponse({
            "type": "location",
            "location_id": code,
            "sublocation_id": "",
            "message": f"📍 Location set: SalesFloor {code}"
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
            "message": f"📦 Sublocation set: {code}"
        })

    # It's an item
    if not current_location:
        return JSONResponse({"type": "error", "message": "⚠️ Scan a location first (e.g. 001)"}, status_code=400)

    full_ref = f"{current_location}-{current_sublocation}-{code}" if current_sublocation else f"{current_location}-{code}"

    # Look up item description from imported items
    async with db.execute("SELECT description FROM items WHERE code = ?", (code,)) as cur:
        item = await cur.fetchone()
    description = item["description"] if item else None

    await db.execute("""
        INSERT INTO audit_scans (session_id, location_id, sublocation_id, item_code, full_ref, description)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (session_id, current_location or None, current_sublocation or None, code, full_ref, description))
    await db.commit()

    return JSONResponse({
        "type": "item",
        "item_code": code,
        "full_ref": full_ref,
        "description": description or "Unknown item",
        "message": f"✅ {full_ref}"
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
    query += " ORDER BY scanned_at DESC LIMIT 50"
    async with db.execute(query, params) as cur:
        scans = await cur.fetchall()
    return [dict(s) for s in scans]


@app.post("/api/import")
async def import_items(file: UploadFile = File(...), source: str = Form(default="bravo"), db=Depends(get_db)):
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    inserted = 0
    for row in reader:
        # Try common Bravo column names
        code = row.get("Item #") or row.get("ItemNumber") or row.get("SKU") or row.get("Barcode") or ""
        desc = row.get("Description") or row.get("Item Description") or ""
        cat = row.get("Category") or row.get("Type") or ""
        price = row.get("Price") or row.get("Retail Price") or "0"
        if not code:
            continue
        try:
            price_val = float(str(price).replace("$", "").replace(",", ""))
        except ValueError:
            price_val = 0.0
        await db.execute("""
            INSERT OR REPLACE INTO items (code, description, category, price, source)
            VALUES (?, ?, ?, ?, ?)
        """, (code.strip().upper(), desc.strip(), cat.strip(), price_val, source))
        inserted += 1
    await db.commit()
    return JSONResponse({"imported": inserted})


@app.post("/api/locations")
async def create_location(location_id: str = Form(...), name: str = Form(...), db=Depends(get_db)):
    await db.execute("INSERT OR REPLACE INTO locations (id, name) VALUES (?, ?)", (location_id.upper(), name))
    await db.commit()
    return RedirectResponse("/locations", status_code=303)
