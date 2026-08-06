# Office Supplies Logistics System — Design Document

**Purpose:** a shareable system to control office/store **supplies** across
multiple locations. A central catalog (the "universe of items"), stock held at
**warehouses and at each store**, store **requests**, and a **scan-to-issue**
flow on a computer / tablet / phone that records the quantity taken (by **box and
by unit**) and the destination store. Built on the proven ABC inventory
foundation but **adjusted for consumable, replenishable, multi-location stock**.

> This document stands alone so it can be handed off and built as a **module
> embedded inside another system** (sharing that system's database and login).

---

## Confirmed decisions

1. **Locations & stock:** each **store holds its own stock**. There are **two
   warehouses** — the **Office warehouse** (the source that **fulfills** stores)
   and a **Receiving warehouse** (whose job is to **receive** incoming supplies).
   Stock is tracked **per location** (each warehouse and each store).
2. **No approval step:** the **warehouse fulfills directly** — a request goes
   straight to scan-to-issue; requests are a convenience/queue, not a gate.
3. **Embedded:** this is a **module of another system** and uses that system's
   **database and authentication** (not a standalone login).
4. **Units:** every item is tracked by **box and by unit** (a box contains N
   units). Users can scan/issue whole boxes or loose units; the system converts.
5. **Devices:** must work on **computer, tablet, and cellphone** (responsive,
   camera scanning on mobile).
6. **Store Card (scan to start):** each store has a printed **QR "store card."**
   From a phone/tablet you **scan the store card to open the app already scoped
   to that store**, then add supplies to a **cart** and confirm — the quantities
   are **deducted from the Office warehouse** and added to that store. No manual
   store-picking or login needed at the counter.

---

## 1. How it differs from ABC retail inventory

| ABC retail/pawn inventory | Office supplies logistics |
|---|---|
| Each item is **unique** (one row = one physical item, sold once) | Each item is a **stocked product** with an **on-hand quantity per location**, replenished |
| Lifecycle: In stock → **Sold** | Flow: **Received** → warehouse → **Issued/transferred** to a store → consumed |
| Single store's own inventory | **Two warehouses + every store**, each with its own stock |
| "Sold report" drives out-movement | **Requests + scan-to-issue transfers** drive movement |
| Counted in single units | Counted in **boxes and units** (pack conversion) |

**Reused from ABC (proven):** barcode/UPC/QR generation & scanning, the camera
scan page, CSV import, categories, the multi-store concept, counts/reconcile,
and the FastAPI + SQLite + Jinja patterns.

---

## 2. Data model

**Location** (`locations`) — warehouses and stores in one table
- `id`, `name`, `code`, `type` (`office_warehouse` / `receiving_warehouse` /
  `store`), `address`, `contact`, `active`.
- Exactly one `office_warehouse` (fulfills) and one `receiving_warehouse`
  (receives) plus N `store` locations.

**Catalog item** (`supply_items`) — the universe of supplies
- `id`, `sku`, `name`, `description`, `category`, `barcode`, `qr_code`, `image`,
  `unit_cost`, **`units_per_box`** (pack size), `reorder_level`, `active`.
- No single on-hand field — stock lives per location (below).

**Stock by location** (`stock`) — the on-hand table
- `item_id`, `location_id`, `qty_units` (always stored in **base units**).
- Boxes are display/entry only: `boxes = qty_units // units_per_box`,
  `loose = qty_units % units_per_box`. Reorder level compares in units.

**Supply request** (`requests`)
- `id`, `store_id` (the requesting store/location), `requested_by`, `status`
  (`open → fulfilled → received`; **no approval state**), `created_at`,
  `needed_by`, `notes`.

**Request line** (`request_lines`)
- `request_id`, `item_id`, `qty_units_requested`, `qty_units_fulfilled`.

**Movement** (`movements`) — the audit trail; every scan lands here
- `id`, `item_id`, `from_location_id`, `to_location_id`,
  `direction` (`receive` / `transfer` / `issue` / `adjust`),
  `qty_units`, `entered_as` (`box` | `unit`), `qty_entered`, `request_id?`,
  `user`, `device`, `created_at`, `note`.
- On-hand per location = opening + Σ(in) − Σ(out) from movements; `stock` is the
  cached running total, reconciled against the log.

**Users/roles** come from the **host system** (embedded). We only add a role tag
(`admin` / `warehouse` / `store`) and, for store users, their `location_id`.

---

## 3. Movement flows

```
SUPPLIER
   │  (a) RECEIVE — scan items into the Receiving warehouse
   ▼
RECEIVING WAREHOUSE ──(b) TRANSFER──▶ OFFICE WAREHOUSE
                                          │
Store sends a REQUEST (choose items+qty)  │
        │                                 │
        ▼                                 ▼
   assign the STORE ───────▶ (c) SCAN-TO-ISSUE  (warehouse fulfills directly)
                                 • scan item QR/barcode
                                 • enter qty by BOX or UNIT
                                 • confirm destination STORE (from request)
                                 • Office warehouse stock ↓, Store stock ↑
                                 • movement logged, request → fulfilled
        │
        ▼
   Store marks RECEIVED  (its own stock is now official)
   Store CONSUMES supplies over time (adjust/usage)
```

- **(a) Receive:** scan supplier deliveries into the **Receiving warehouse**
  (by box or unit).
- **(b) Transfer:** move stock Receiving → Office warehouse (scan or bulk).
- **(c) Issue:** the **Office warehouse fulfills a store request directly** (no
  approval) — scan → qty (box/unit) → store → done. Stock leaves the office
  warehouse and lands in that store's stock.
- **Ad-hoc issue** without a request is allowed: scan → qty → pick store → issue.
- **Store consumption:** stores draw down their own stock (a simple "use"/adjust
  or their own scan), so each store's on-hand stays real.

---

## 3a. Store Card — scan to start a pick (preferred flow)

Each **store** has a printed **QR "store card."** It encodes a link like
`/scan?store=<store_token>` that opens the app on a phone/tablet **already set to
that store**. This becomes the everyday flow:

```
1. Scan the STORE CARD QR  ──▶  app opens, scoped to that store (a "cart" starts)
2. ADD SUPPLIES to the cart ──▶  scan each item's QR/barcode, enter qty (box/unit)
3. Review the cart (items + quantities for this store)
4. CONFIRM  ──▶  each line deducts from the OFFICE WAREHOUSE and adds to the STORE
                 one movement per line, logged (who/device/time)
```

- The store card is a **launcher + identity**: no manual store-picking, no login
  at the counter (it carries a store token; the host session still authorizes).
- The **cart / pick session** holds the lines until **Confirm**, so a whole pick
  commits at once (and can be abandoned before confirming).
- A store card can also be tied to an **open request** so scanning it pre-loads
  the requested items to check off.
- Rotate/revoke a store's token to invalidate a lost card.

**Data for this:** `pick_sessions` (`id`, `store_id`, `user`, `device`,
`status: open|committed|void`, `created_at`) and `pick_lines` (`session_id`,
`item_id`, `qty_units`, `entered_as`, `qty_entered`). On **Confirm**, each
`pick_line` becomes an `issue` movement (Office warehouse → store).

## 4. Scanning on computer / tablet / phone

- A responsive **/scan** screen: big touch targets on mobile, keyboard/USB
  scanner friendly on the computer.
- **Scan** the item's **QR or barcode** with the device camera (reuse ABC's
  `camera.js` + decode); manual code entry as fallback.
- On a hit: show item + image + on-hand at the working location → pick **mode**
  (Receive / Transfer / Issue) → **enter quantity as boxes or units** →
  **confirm the store/location** → **Confirm**.
- Each confirm writes a `movement` and updates both locations' `stock` live.
- **Labels:** print **QR/barcode labels** per item for shelves/bins (reuse ABC's
  `/barcode` and `/qr`).
- Phase 2: offline scan queue that syncs when back online.

---

## 5. Screens

1. **Catalog** — the universe of items; search/filter; add/edit; `units_per_box`;
   print labels; CSV import (reuse ABC import).
2. **Requests** — by store & status; store creates a request; warehouse opens it
   and fulfills (scan-to-issue). No approval gate.
3. **Scan** (computer/tablet/phone) — Receive / Transfer / Issue (§4).
4. **Locations** — the 2 warehouses + stores, each with its on-hand and history.
5. **Reports / Dashboard** — usage by store, by item, by period; reorder list
   (any location where units ≤ reorder level); movement audit; supply spend
   (unit_cost × units) per store. Reuse ABC dashboard patterns (date range,
   chips, drill-down).

---

## 6. Roles & sharing (via the host system)

- **Admin:** catalog, locations, reorder levels, everything.
- **Warehouse:** receive, transfer, fulfill/issue.
- **Store:** create requests for their location, mark received, see their own
  stock & history only.
- Authentication/users come from **the host system**; we scope views by role +
  `location_id`. Any device (computer/tablet/phone) with a valid host session.

---

## 7. Reporting & control

- **Reorder alerts** per location (units ≤ reorder level; office warehouse and
  stores).
- **Consumption by store** (what each store draws, per period) → right-size
  future orders.
- **Item velocity** across the network → what to buy more of.
- **Full audit:** every unit/box moved, from/to which location, by whom, when,
  on which device.
- **Cost:** unit_cost × issued units = supply spend per store/period.

---

## 8. Suggested API (mirrors ABC style; uses host DB/auth)

- Catalog: `GET/POST /api/supply-items`, CSV `POST /api/supply-import`,
  `GET /barcode/{code}`, `GET /qr/{code}`
- Stock: `GET /api/stock?location=&item=`
- Requests: `POST /api/requests` `{store_id, lines[]}`,
  `GET /api/requests?store=&status=`
- **Store card / pick session:**
  `GET /scan?store=<token>` → resolve store, open (or resume) a `pick_session`,
  render the mobile cart scoped to that store.
  `POST /api/pick/{session}/add` `{code, qty, unit: box|each}` → add a line.
  `POST /api/pick/{session}/commit` → turn every line into an `issue` movement
  (Office warehouse → store), update stock, close the session.
  `GET /store-card/{store}` → printable QR store card.
- Scan (single move, no cart): `POST /api/scan` `{code, mode:
  receive|transfer|issue, qty, unit: box|each, from_location?, to_location,
  request_id?}` → convert to base units, write movement, update stock.
- Reports: `GET /api/reports/reorder`, `GET /api/reports/usage?store=&from=&to=`

**Unit conversion (single rule):** everything is stored in **base units**;
`box → units = qty × units_per_box`. Display shows both (`3 boxes + 5`).

---

## 9. Build phases

1. **Catalog + labels** — items with `units_per_box`, categories, QR/barcode
   labels, CSV import; printable **store cards**.
2. **Locations + stock** — 2 warehouses + stores, per-location on-hand.
3. **Store-card scan → cart → commit** — scan the store card to open a session
   scoped to that store, add items (box/unit), confirm to deduct from the Office
   warehouse into the store. Plus single Receive / Transfer moves.
4. **Requests** — store requests, warehouse fulfills directly (a card can
   pre-load a request).
5. **Reports & reorder** — dashboards, reorder alerts, usage & spend by store.
6. **Polish** — offline scan queue, supplier receiving, exports.

---

## 10. Embedding notes (for the host system)

- Uses the **host system's database** (add the tables above) and its
  **authentication/session** — no separate login.
- Ships as a set of **routes + templates + a `/scan` mobile view** that mount
  under the host app, plus the shared barcode/QR label endpoints from ABC.
- Keep the **movement log** as the single source of truth; `stock` is a cache.
