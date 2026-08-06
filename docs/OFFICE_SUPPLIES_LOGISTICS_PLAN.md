# Office Supplies Logistics System — Design Document

**Purpose:** a shareable system to control office/store **supplies** across
multiple stores. A central catalog (the "universe of items"), stores that
**request** supplies, and a **scan-to-issue** flow on a phone/tablet that records
the quantity taken and the store it's for. Built on the proven ABC inventory
foundation but **adjusted for consumable, replenishable stock** rather than
unique retail/pawn items.

> This document is written to stand alone so it can be handed off and built as a
> module of another system. It defines the data model, workflows, screens,
> scanning, roles, APIs, and what is reused from ABC vs. what is new.

---

## 1. How it differs from ABC retail inventory

| ABC retail/pawn inventory | Office supplies logistics |
|---|---|
| Each item is **unique** (one row = one physical item, sold once) | Each item is a **stocked product** with an **on-hand quantity** that is replenished |
| Lifecycle: In stock → **Sold** | Lifecycle: In stock → **Issued to a store** → replenished; consumables recur |
| Single store's own inventory | **Central store** issues to **many branch stores** |
| "Sold report" drives out-movement | **Supply requests + scan-to-issue** drive out-movement |
| Value = retail price | Value = unit cost; focus on **usage & reorder**, not margin |

**Reused from ABC (proven):** barcode/UPC/QR generation & scanning, camera scan
page, CSV import, categories, per-store concept, counts/reconcile, the FastAPI +
SQLite + Jinja stack, and the login/roles pattern.

---

## 2. Core concepts / data model

**Catalog item** (`supply_items`) — the universe of supplies
- `id`, `sku`, `name`, `description`, `category`, `unit` (each / box / ream…),
  `pack_size`, `barcode`, `qr_code`, `image`, `unit_cost`,
  `on_hand_qty` (central stock), `reorder_level`, `active`.

**Store / branch** (reuse ABC `stores`)
- `id`, `name`, `code`, `address`, `contact`, `active`.

**Supply request** (`requests`)
- `id`, `store_id`, `requested_by`, `status`
  (`requested → approved → picking → fulfilled → received`),
  `created_at`, `needed_by`, `notes`.

**Request line** (`request_lines`)
- `request_id`, `item_id`, `qty_requested`, `qty_fulfilled`.

**Stock movement / issue** (`movements`) — the audit trail (every scan lands here)
- `id`, `item_id`, `store_id`, `request_id` (nullable),
  `direction` (`issue` out to store / `receive` restock in / `adjust`),
  `qty`, `scanned_by` (user), `device`, `created_at`, `note`.

**User / role** (`users`)
- `id`, `name`, `role` (`admin` / `warehouse` / `store`), `store_id` (for store
  users), `pin_or_token`.

`on_hand_qty` is always **derived from / reconciled against** the sum of
movements, so the scan log is the source of truth.

---

## 3. The main workflow (exactly the flow requested)

```
Universe of items (catalog)                     ← admin maintains
        │
1. A store SENDS A REQUEST for supplies         ← store user (or phone)
        │   picks items + quantities
        ▼
2. CHOOSE / ASSIGN THE STORE                    ← the request is tied to that store
        │   request appears in the warehouse queue
        ▼
3. SCAN TO ISSUE on tablet / cellphone          ← warehouse user
        │   • scan the item's QR/barcode
        │   • enter the QUANTITY being taken
        │   • confirm the STORE it's going to (from the request)
        ▼
4. STOCK DEDUCTS from central, ALLOCATES to store
        │   movement row logged (who, what, qty, store, time, device)
        ▼
5. Request status → fulfilled → store marks RECEIVED
```

**Ad-hoc issue (no request):** the warehouse can also just scan → enter qty →
**pick the store** → issue, without a formal request. Same movement log.

---

## 4. Scanning on phone / tablet (mobile-first)

- A **/scan** page optimized for touch. Big buttons, one item at a time.
- **Scan** the item's **QR or barcode** with the device camera (reuse ABC's
  `camera.js` + barcode decode). Manual code entry as fallback.
- On a hit: show item name + image + current on-hand → **enter quantity** →
  **choose store** (pre-selected if working a specific request) → **Confirm**.
- Each confirm writes a `movement` and decrements `on_hand_qty` live.
- Works offline-tolerant: queue scans and sync when back online (phase 2).
- **Labels:** generate printable **QR/barcode labels** per item (reuse ABC's
  `/barcode` and `/qr` endpoints) so every shelf/bin is scannable.

---

## 5. Screens

1. **Catalog** — the universe of items; search, filter by category, on-hand,
   reorder flags; add/edit item; print labels; CSV import (reuse ABC import).
2. **Requests** — list by store & status; create a request (store picks items +
   qty); approve; open a request to fulfill.
3. **Scan-to-Issue** (phone/tablet) — the flow in §4.
4. **Stores** — branches, their open requests and consumption.
5. **Reports / Dashboard** — usage by store, by item, by period; reorder list
   (on-hand ≤ reorder level); movement history; cost of supplies per store.
   (Reuse the ABC dashboard patterns: date range, chips, drill-down tables.)
6. **Receiving** — restock central stock (scan in / import a supplier invoice).

---

## 6. Roles & sharing

- **Admin:** manage catalog, stores, users, reorder levels, see everything.
- **Warehouse:** fulfill requests, scan-to-issue, receive stock.
- **Store user:** create requests for their store, mark received, see their own
  history only.
- **Shareable access:** each store gets a login (or a per-store share link/QR)
  so staff can request from any device. Central sees all stores. Same
  cookie-auth pattern as ABC; add role + `store_id` scoping.

---

## 7. Reporting & control

- **Reorder alerts:** items where `on_hand_qty ≤ reorder_level`.
- **Consumption by store:** who's using the most of what, per period.
- **Item velocity:** fast-moving supplies → order more.
- **Full audit:** every unit that left, when, to which store, scanned by whom.
- **Cost tracking:** unit_cost × issued qty = supply spend per store/period.

---

## 8. Suggested API (FastAPI, mirrors ABC style)

- `GET /api/supply-items` · `POST /api/supply-items` · CSV `POST /api/supply-import`
- `POST /api/requests` (store_id, lines) · `GET /api/requests?store=&status=`
- `POST /api/requests/{id}/approve`
- `POST /api/scan-issue` `{code, qty, store_id, request_id?}` → look up item,
  write movement, decrement on-hand, return updated item
- `POST /api/receive` `{code, qty}` → restock
- `GET /api/reports/reorder` · `GET /api/reports/usage?store=&from=&to=`
- `GET /barcode/{code}` · `GET /qr/{code}` (reuse ABC label generators)

Data store: SQLite (same as ABC) or the DB of the "other system" it plugs into.

---

## 9. Build phases

1. **Catalog + labels** — items, categories, on-hand, QR/barcode labels, CSV import.
2. **Scan-to-Issue** — the phone/tablet flow, movement log, live on-hand, store pick.
3. **Requests** — store requests, approve, fulfill against a request.
4. **Roles & sharing** — store logins/links, scoping.
5. **Reports & reorder** — dashboards, reorder alerts, usage by store.
6. **Polish** — offline scan queue, receiving/supplier invoices, exports.

---

## 10. Open questions (to confirm before building)

1. **Central model:** one central supply room issuing to all stores, or does each
   store also hold its own stock (store-to-store transfers)?
2. **Approvals:** do store requests need approval, or can warehouse fulfill
   directly?
3. **Units/packs:** track by each, or by box/pack with conversions?
4. **Where it lives:** a standalone module, or embedded in "the other system"
   (which DB/auth does it share)?
5. **Devices:** company tablets/phones only, or personal phones via a share link?
6. **Costing:** do you need supply spend per store, or just quantities?
