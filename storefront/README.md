# Handoff: ABC MoneyLoan Storefront + Marketing Landing Page

## Overview
Customer-facing storefront and marketing site for **ABC MoneyLoan Pawnshop** (146 E. State Street, Trenton, NJ 08608, 609-777-5500 — "America's Pawnshop"). Customers browse one-of-a-kind in-store inventory online, then **Request a Hold** and pick up/pay in store. It is **not** a full checkout.

It covers, as a single-page app with client-side view switching:
1. **Landing** — animated story hero (crossfading photo scenes + floating category chips), trust strip, shop-by-category tiles (real photos), "Just in on the floor" grid, **Other Services** band (Western Union, Check Cashing, Money Orders, Bill Payment Center, We Buy Gift Cards), and a **Visit Us** block with clickable Google Maps directions.
2. **Shop / catalog** — search, category sidebar, sort (featured / price / name), max-price slider, responsive product grid.
3. **Product detail** — jewelry variant (metal/purity/weight/diamond/stone/quality + authenticity badges) and electronics variant (manufacturer/model/serial/condition); availability, barcode, related items.
4. **Cart + Request a Hold** — name / phone / email reserve form (no payment).
5. **Hold confirmation** — live countdown to 4 PM today (or next business day if after 4 PM/weekend), store address with directions, and a QR + hold code.

---

## About the Design Files
The files in this bundle are **design references authored in HTML** — working prototypes that show the intended look, layout, and behavior. They are **not** meant to be shipped as-is into production.

The task is to **recreate these designs in the target codebase's environment** (e.g. React, Next.js, Vue, etc.) using its established components, routing, and data layer. If no codebase exists yet, choose an appropriate stack (a React + Vite or Next.js app is a natural fit) and implement the designs there.

> **Note on the authoring format:** the `.dc.html` files are "Design Components" — a custom template runtime (`support.js`) with a `<x-dc>` template + a `class Component extends DCLogic` logic block. This runtime is proprietary to the design tool; **do not port `support.js`**. Read the `.dc.html` files as a precise spec (markup, inline styles, and the logic class that computes data/handlers) and re-express them in the target framework. The logic class methods (filtering, sorting, cart, countdown, live-inventory adapter) translate directly to hooks/state.

### How to open the design right now
- Easiest: open **`ABC-MoneyLoan-Storefront.html`** directly in any browser — it is fully self-contained (all CSS/JS/images inlined) and works offline. Use this as the visual source of truth.
- The `.dc.html` source files require the design tool's runtime and won't render standalone; read them for structure/logic.

---

## Fidelity
**High-fidelity (hifi).** Final colors, typography, spacing, and interactions are specified. Recreate the UI pixel-for-pixel using the codebase's libraries, matching the tokens below.

---

## Design Tokens

### Colors
| Token | Hex | Use |
|---|---|---|
| Ink / navy (primary dark) | `#0B1421` / `#0E1A2B` | Headers band, footer, dark sections, headings |
| Gold accent (gradient) | `#E8C06A` → `#B07E22` | Primary buttons, accents, hero highlights |
| Gold text accent | `#C08A2D` / `#B07E22` | Eyebrows, links on light |
| Cream surface (page bg) | `#F5F2EC` | Page background |
| White surface | `#FFFFFF` | Header bar, cards, panels |
| Price red | `#A4262C` | Prices |
| Available / verified green | `#1F9D5B` (text `#127a45`, mint bg `#e8f6ee`) | Availability, verified badges, cart count |
| Muted text | `#6b7a8c` / `#9fb0c4` / `#8ea0b5` | Secondary text |
| Card border | `#e6e0d3` / `#e3ddd0` | Card & panel borders |
| Search field (light) | bg `#f4f1ea`, border `#e0d9cb` | Header search |

### Typography
- **Display / headings:** `'Cormorant Garamond'`, serif — weights 500/600/700. Used for H1/H2, product titles, prices contexts. Sizes: hero H1 `clamp(38px,6vw,62px)`; section H2 `32–40px`; product title `40px`.
- **Body / UI:** `'Public Sans'`, sans-serif — weights 400–800. Body `14–18px`; eyebrows `11–13px` uppercase, `letter-spacing:2.5–3px`, weight 700.
- **Poster/hero word (carousel variant only):** `'Anton'`, sans-serif.
- Google Fonts import: `Cormorant Garamond` + `Public Sans` (+ `Anton` for the carousel version).

### Spacing / radius / shadow
- Content max-width: **1240px**, side padding **22px**.
- Radius: cards **14–16px**, tiles **16px**, buttons **9–12px**, pills/badges **20px**, big panels **18–22px**.
- Card hover: `translateY(-3 to -4px)` + `box-shadow: 0 14–16px 34–38px rgba(14,26,43,.14–.15)`.
- Primary button: gold gradient, `box-shadow: 0 8px 22–26px rgba(192,138,45,.3–.4)`.
- Header: sticky, white, `border-bottom:1px solid #e6e0d3`, height **70px**.

---

## Screens / Views

### 1. Header (persistent)
White sticky bar, 70px. Left: **logo** (`logo-cut.png`, height 40px). Center: search field (rounded, cream). Right nav: **Shop**, **Visit Us**, and a gold **Cart** button with a green count badge (top-right, `#1F9D5B`, white 2px border). All nav actions switch the active view (client state), not real routes.

### 2. Landing
- **Hero (story):** full-bleed section, min-height ~640px, dark base `#09101A`. A background photo (`hero-bg.png`) crossfades across 3 scenes (opacity transition ~1.1s, auto-advances every 5s) with a subtle brightness/saturation boost and a left-to-right dark gradient for text legibility. Left column: eyebrow + H1 (Cormorant) + subhead + two CTAs (**Browse the Shop** gold, **Visit Us in Trenton** ghost) + 3 scene dots. Floating **category chips** (rounded 66–78px tiles with a product photo, gold border, animated shine sweep + gentle float) are positioned over the hero and each click-filters a category. A "LIVE · REAL FLOOR INVENTORY" pill sits top-left. Chips hidden below 880px.
- **Trust strip:** dark band, 4 items (icon chip + title + subtitle).
- **Shop by category:** grid `repeat(auto-fill,minmax(220px,1fr))`, 180px tiles. Each tile = real photo + bottom gradient scrim + title (Cormorant 23px) + gold subtitle. 6 tiles: Fine Gold, Diamonds, Gaming, Laptops & Cameras, Watches, Audio.
- **Just in on the floor:** "NEW" badge + product-card grid (`minmax(240px,1fr)`).
- **Other Services:** navy band. Header eyebrow "More than a pawnshop" + H2 + "Call 609-777-5500" gold button. Grid `repeat(auto-fill,minmax(320px,1fr))` of service cards (gold icon chip + title + green tag + description). Services: Western Union (Authorized agent), Check Cashing (Cash on the spot), Money Orders (Lowest prices), Bill Payment Center (One-stop counter), We Buy Gift Cards (Cash today). Bottom strip: "BUY · SELL · TRADE · PAWN · No credit check · Confidential collateral loans · Cash for gold & silver".
- **Visit Us:** navy rounded panel, 2-col grid. Left: "Family-run since 1998" eyebrow, H2, copy, address + hours rows (gold pin/clock icons), a **Get directions** link, and a "Start browsing" button. Right: a stylized map panel that is a **link to Google Maps directions** (`https://www.google.com/maps/dir/?api=1&destination=146+E+State+St,+Trenton,+NJ+08608`, `target=_blank`) with a gold pin and a white "Get directions on Google Maps" button.

### 3. Shop / Catalog
2-col grid `238px 1fr`. **Sidebar** (sticky, top 88px): Categories list (active item = navy bg, white text) with per-category counts, and a **Max price** range slider (0–1300, accent `#C08A2D`) showing "No limit" at max. **Main:** results count + a **Sort** `<select>` (Featured / Price low→high / Price high→low / Name A–Z), then product grid `minmax(230px,1fr)`. Empty state: dashed card with "Clear filters".

### 4. Product Card (`ProductCard.dc.html`)
White card, radius 16. Square image (real photo if `item.image`, else a monogram placeholder on a gold gradient for jewelry / dark grid gradient for electronics). "✦ ONE OF A KIND" pill top-left (shown when `oneOfKind`). Body: category eyebrow (gold), title (700, 15.5px), green "Available · {condition}" line, then price row: price (`#A4262C`, 21px, 800) or "Ask in store", and a 42px gold **add-to-cart** icon button. Whole card click → product detail; add button click stops propagation and adds to cart. Hover: lift + shadow.

### 5. Product Detail
Breadcrumb (Shop / category / title). 2-col `1fr 1fr`, image sticky (top 88px). Image = real photo, or jewelry gold-gradient shimmer placeholder / electronics dark-grid placeholder with monogram. Barcode caption below. Right: "ONE OF A KIND · ONLY 1 IN STOCK" pill, category eyebrow, H1 (Cormorant 40px), price (red 38px) or "Ask in store", green availability + condition line, then:
- **Authenticity badges** (jewelry only, when applicable): "💎 Authentic Diamond — Verified" and "✨ Authentic Stone — Verified" (gold-tinted pills).
- **Add to cart** (gold, full-width) + **Ask a question** (outline).
- **Specifications panel:** navy header bar + rows. Jewelry: Metal Type/Color, Metal Purity, Total Jewelry Weight, Total Diamond Size, Total Stone Size, Quality. Electronics: Manufacturer, Model, Serial Number, Condition.
- Trust row (checkmarks): Inspected in-house · Photographed as-is · No obligation to buy.
- **You might also like:** related grid (same group).

### 6. Cart + Request a Hold
2-col `1fr 360px`. Left: line items (thumb + category + title + condition; price + Remove). Right (sticky): items count, est. in-store total (red), then the reserve form — **Full name**, **Phone**, **Email** inputs (focus border `#C08A2D`). Validation: require name AND (phone OR email); else show error. Submit = **Request a Hold**. Note: "Held until 4 PM today." Empty state: "Browse the shop".

### 7. Hold Confirmation
Centered check icon (green). H1 "Your hold is confirmed" + "Thanks, {name}". **Countdown** card (navy): HH : MM : SS, tabular-nums, ticking each second, to the computed deadline; label "pick up by {today/weekday} at 4:00 PM". 2-col: left = on-hold items list + est. total + store address card (with **Get directions** link, photo ID note); right = **QR** (a 21×21 rendered module grid placeholder) + hold code `ABC-XXXXXX` + "Keep browsing".

---

## Interactions & Behavior
- **View switching:** single-page; a `view` state ∈ {landing, shop, product, cart, confirm} controls which screen renders. Nav/logo/CTA clicks set `view` and `window.scrollTo(0,0)`. In a real app, make these **routes** (`/`, `/shop`, `/product/:id`, `/cart`, `/hold/confirmation`).
- **Hero:** scene index auto-advances every 5s (pause on the confirm view); dots jump to a scene; chips call category filter then go to shop.
- **Search:** header input filters by title/category; submit → shop view.
- **Filter/sort:** category (exact category or `group:<group>`), max-price slider, and sort applied in the shop list computation.
- **Cart:** add/remove by id; cart count badge; totals sum numeric prices (null price = "Ask in store", excluded from total).
- **Countdown deadline logic:** next 4:00 PM; if already ≥ 4 PM, roll to next day; skip Sat/Sun. Recompute display every second.
- **Google Maps:** address/map elements link to `https://www.google.com/maps/dir/?api=1&destination=146+E+State+St,+Trenton,+NJ+08608` (new tab).
- **Animations:** CSS keyframes — `floatin` (view enter), scene crossfade (opacity), chip `floaty` + `chipshine`, `sheen`, `twinkle`, `pulsering`. Durations 2–7s, `ease`/`ease-in-out`.
- **Responsive:** grids use `auto-fill`/`auto-fit minmax`; hero chips hidden < 880px; the shop 2-col and detail 2-col should collapse to single column on narrow screens (add breakpoints in the port).

## State Management
- `view`, `search`, `sort`, `maxPrice`, `activeFilter`, `currentId` (open product), `cart` (array of ids), `holdName/holdPhone/holdEmail`, `formError`, `held` (submitted hold snapshot: items, total, name, deadline, code), `now` (ticking clock), `heroScene`.
- Derived per render: filtered+sorted `shopItems`, sidebar categories with counts, decorated `current` product (specs list + badges by type), `related`, cart items + total, countdown parts, hero scenes.

## Live Inventory Adapter (important)
The logic class already contains a **live-data hook** to connect the real in-house catalogue:
- `API_URL` getter (currently `''` → uses bundled sample data). Set it to the in-house inventory feed URL.
- `loadInventory()` fetches JSON (`[]` or `{items|data:[]}`), maps each row via `mapItem()`, and if valid replaces the sample data app-wide; on failure it logs and falls back to samples.
- `mapItem()` accepts aliased keys: `id|sku|barcode`, `name|title`, `category|cat`, `price|amount|salePrice` (number, `""`/"Ask in store" → null), `condition`, `quantity` (≤1 ⇒ one-of-a-kind), `image|photo|imageUrl`, jewelry specs (`metal, purity, weight, diamond, stone, quality`), electronics specs (`manufacturer, model, serial`). `guessType()`/`groupFor()` infer jewelry vs. electronics and the category group from the category name.
- Port this as a data-fetching layer (React Query/SWR/loader). Two follow-ups the client wants: **wire this API URL**, and build a **staff "holds" dashboard** (holds currently end at the confirmation screen).

## Design Tokens — see the "Design Tokens" section above.

## Assets
- `logo-cut.png` — ABC MoneyLoan wordmark ("America's Pawnshop"), white background removed → transparent. Use in header (on white) and footer (on a white chip because the mark is dark blue/green).
- `hero-bg.png` — hero background collage (cash / gold & watches / guitars). Client-supplied; replaceable.
- **Category tile & card photos** are **Unsplash placeholders** (URLs embedded in the logic class `catPhotos` map and on sample items). Replace with the store's own merchandise photography; if you keep any Unsplash images in production, add the required photographer attribution per the Unsplash license.
- Icons are inline SVG (no icon-font dependency).

## Files
- `ABC MoneyLoan (story hero).dc.html` — **primary design** (this is the current, approved version: story hero, real logo, real category/card photos, Other Services, Google Maps).
- `ProductCard.dc.html` — the reusable product card (used by landing, shop, related).
- `ABC-MoneyLoan-Storefront.html` — **self-contained build** you can open in a browser as the visual source of truth.
- `logo-cut.png`, `hero-bg.png` — image assets.
- `support.js`, `image-slot.js` — design-tool runtime/helper (reference only; **do not port** `support.js`).

> There is also a `carousel hero` variant (`ABC MoneyLoan.dc.html`) in the original project — an alternate hero treatment. Not included here; the story-hero version above is the approved one.
