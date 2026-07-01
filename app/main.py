from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import aiosqlite
import barcode
from barcode.writer import SVGWriter
import segno
import csv
import io
import json
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
        "found_count": found_count,
        "unknown_count": unknown_count,
        "missing_count": len(missing),
    })


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
    # Only retail items flagged for sale and not sold — never loan/layaway
    where = ["source = 'retail'", "COALESCE(for_sale,1) = 1", "COALESCE(sold,0) = 0"]
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
        FROM items WHERE source = 'retail' AND COALESCE(for_sale,1) = 1
        GROUP BY category ORDER BY cnt DESC
    """) as cur:
        categories = [dict(r) for r in await cur.fetchall()]
    return templates.TemplateResponse("shop.html", {
        "request": request, "products": products, "categories": categories,
        "q": q, "category": category, "sort": sort, "max_price": max_price,
        "count": len(products),
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


HOLD_HOURS = 4


@app.post("/api/shop/inquiry")
async def create_inquiry(
    customer_name: str = Form(...), phone: str = Form(...),
    email: str = Form(default=""), items: str = Form(...), db=Depends(get_db)
):
    async with db.execute(
        f"INSERT INTO inquiries (customer_name, phone, email, items, status, hold_expires) "
        f"VALUES (?, ?, ?, ?, 'holding', datetime('now', '+{HOLD_HOURS} hours'))",
        (customer_name.strip(), phone.strip(), email.strip(), items)
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
        "request": request, "inq": inq, "products": products,
        "store": store, "hold_hours": HOLD_HOURS,
    })


@app.get("/qr")
async def generate_qr(data: str):
    """Return an SVG QR code encoding the given data (e.g. a hold URL)."""
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
    photo: UploadFile = File(default=None),
    db=Depends(get_db)
):
    price = float(retail_price) if retail_price.replace(".", "", 1).isdigit() else None
    sale_flag = 1 if for_sale == "on" else 0
    photo_name = await save_photo(photo, f"item_{item_number}")
    if photo_name:
        await db.execute(
            "UPDATE items SET retail_price=?, for_sale=?, photo=? WHERE item_number=?",
            (price, sale_flag, photo_name, item_number)
        )
    else:
        await db.execute(
            "UPDATE items SET retail_price=?, for_sale=? WHERE item_number=?",
            (price, sale_flag, item_number)
        )
    await db.commit()
    return RedirectResponse("/inventory", status_code=303)


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

    max_day = max([d["cnt"] for d in per_day], default=1) or 1
    max_cat = max([c["cnt"] for c in top_cats], default=1) or 1

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "in_stock": in_stock, "sold_total": sold_total, "sold_value": sold_value,
        "sold_7": sold_7, "sold_30": sold_30, "stock_value": stock_value,
        "per_day": per_day, "top_cats": top_cats, "sellthrough": sellthrough,
        "max_day": max_day, "max_cat": max_cat,
    })


@app.get("/reconcile", response_class=HTMLResponse)
async def reconcile_page(request: Request, db=Depends(get_db)):
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
    return templates.TemplateResponse("reconcile.html", {
        "request": request, "missing": missing, "sold": sold,
    })


@app.post("/api/items/{item_number}/sold")
async def mark_sold(item_number: str, db=Depends(get_db)):
    await db.execute(
        "UPDATE items SET sold=1, sold_at=CURRENT_TIMESTAMP, missing=0, for_sale=0 WHERE item_number=?",
        (item_number,)
    )
    await db.commit()
    return RedirectResponse("/reconcile", status_code=303)


@app.post("/api/items/{item_number}/keep")
async def mark_keep(item_number: str, db=Depends(get_db)):
    await db.execute("UPDATE items SET missing=0 WHERE item_number=?", (item_number,))
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

        for row in reader:
            item_number = find_column(row, "Number", "Item #", "Item Number", "ItemNumber")
            barcode = find_column(row, "Barcode", "Barcode Number", "UPC", "SKU")
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

            if not item_number and not barcode:
                skipped += 1
                continue

            # Skip report footer/header junk rows (e.g. "REPORT PRINTED ON ...").
            # Real item numbers have no spaces and aren't sentences.
            junk = item_number and (
                " " in item_number
                or item_number.upper().startswith(("REPORT", "TOTAL", "PAGE", "PRINTED"))
            )
            if junk and not barcode:
                skipped += 1
                continue

            if not barcode and item_number:
                digits = re.sub(r"[^0-9]", "", item_number)
                barcode = digits

            item_number_u = item_number.upper() if item_number else None
            barcode_u = barcode.upper() if barcode else None
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

            # UPSERT: refresh Bravo-sourced fields, but PRESERVE admin/sale fields
            # (retail_price, photo, for_sale, sold, sold_at) on conflict.
            await db.execute("""
                INSERT INTO items
                  (item_number, barcode, description, category, item_type, item_status,
                   cost, retail_price, item_date, source, product_type, total_diamond, metal_type,
                   metal_color, total_stone_size, condition, diamond_authentic,
                   serial_number, manufacturer, model, metal_purity, total_jewelry_weight,
                   metal_weight, quality, authentic_stone, quantity, vendor, missing)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(item_number) DO UPDATE SET
                   barcode=excluded.barcode, description=excluded.description,
                   category=excluded.category, item_type=excluded.item_type,
                   item_status=excluded.item_status, cost=excluded.cost,
                   retail_price=COALESCE(excluded.retail_price, items.retail_price),
                   item_date=excluded.item_date, source=excluded.source,
                   product_type=excluded.product_type, total_diamond=excluded.total_diamond,
                   metal_type=excluded.metal_type, metal_color=excluded.metal_color,
                   total_stone_size=excluded.total_stone_size, condition=excluded.condition,
                   diamond_authentic=excluded.diamond_authentic,
                   serial_number=excluded.serial_number, manufacturer=excluded.manufacturer,
                   model=excluded.model, metal_purity=excluded.metal_purity,
                   total_jewelry_weight=excluded.total_jewelry_weight,
                   metal_weight=excluded.metal_weight, quality=excluded.quality,
                   authentic_stone=excluded.authentic_stone, quantity=excluded.quantity,
                   vendor=excluded.vendor, missing=0
            """, (
                item_number_u, barcode_u, description, category, item_type, item_status,
                cost_val, retail_val, item_date, source, ptype, total_diamond, metal_type,
                metal_color, total_stone_size, condition, diamond_authentic,
                serial_number, manufacturer, model, metal_purity, total_jewelry_weight,
                metal_weight, quality, authentic_stone, quantity, vendor,
            ))
            if exists:
                updated += 1
            else:
                inserted += 1

        # Reconciliation: items in this list that were NOT in the file and are not
        # already sold → flag as missing (possibly sold). Re-appearing items cleared above.
        missing_count = 0
        if seen_codes:
            placeholders = ",".join("?" for _ in seen_codes)
            async with db.execute(
                f"SELECT COUNT(*) FROM items WHERE source=? AND sold=0 "
                f"AND item_number NOT IN ({placeholders})",
                [source] + seen_codes
            ) as cur:
                missing_count = (await cur.fetchone())[0]
            await db.execute(
                f"UPDATE items SET missing=1 WHERE source=? AND sold=0 "
                f"AND item_number NOT IN ({placeholders})",
                [source] + seen_codes
            )

        await db.execute(
            "INSERT INTO imports (source, filename, item_count, mode) VALUES (?, ?, ?, ?)",
            (source, file.filename or "", inserted + updated, mode)
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
        "updated": updated,
        "missing": missing_count,
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
