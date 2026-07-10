# Connecting ABC MoneyLoan storefront to your backend (`localhost:8000`)

The storefront reads a **JSON product feed**. `http://localhost:8000/shop` is an HTML page — the storefront needs a URL that returns **JSON**, e.g. `http://localhost:8000/api/products/`.

## 1. How the frontend finds your data
On load it resolves the feed in this order (first wins):
1. `?api=<url>` in the page URL — e.g. open `.../storefront.html?api=http://localhost:8000/api/products/`
2. `window.ABC_API_URL = 'http://localhost:8000/api/products/'` (set before the app boots)
3. Otherwise it **probes** these paths on the current origin (or `localhost:8000`):
   `/api/products/`, `/api/inventory/`, `/api/items/`, `/shop/api/products/`, `/api/products`, `/products/?format=json`, `/shop.json`
   — the first that returns a JSON array of items wins.

When connected, a green **"Live inventory connected"** badge appears (bottom-left) and the console logs the URL + item count. Otherwise it silently uses sample data.

> **CORS:** if the storefront is served from a different origin than the API, the browser blocks the fetch. Easiest fix: **serve the storefront from the same origin** (`localhost:8000`) — then no CORS needed. Otherwise enable CORS on the API (snippet below).

## 2. JSON shape the frontend expects
An array of items (or `{ "results": [...] }` / `{ "items": [...] }` — DRF pagination works). Field names are flexible — the mapper accepts these aliases:

```jsonc
[
  {
    "id": "8843771",                 // id | sku | barcode | itemId
    "name": "Lady's Diamond Fashion Ring",   // name | title
    "category": "Lady's Diamond Fashion Ring", // category | cat | categoryName
    "price": 1250,                   // number, or "" / "Ask in store" / null → "Ask in store"
    "condition": "Excellent",        // condition | grade
    "barcode": "8843771",            // barcode | sku | upc
    "quantity": 1,                   // qty <= 1 ⇒ shown as "One of a kind"
    "image": "https://.../ring.jpg", // image | photo | imageUrl | thumbnail
    // jewelry specs (only for jewelry categories):
    "metal": "White Gold", "purity": "14K", "weight": "4.1 g",
    "diamond": "0.75 ct", "stone": "0.20 ct", "quality": "VS / near-colorless"
    // electronics specs instead (manufactured items):
    // "manufacturer": "Sony", "model": "PS4 / CUSA", "serial": "...", "condition": "Good"
  }
]
```
Jewelry vs. electronics is auto-detected from the category name (gold/diamond/chain/ring… ⇒ jewelry). A non-empty `diamond`/`stone` value auto-shows the "Authentic Diamond/Stone — Verified" badges.

## 3. Django example — expose `/api/products/`

**Plain Django view** (`views.py`):
```python
from django.http import JsonResponse
from .models import Product  # your existing model

def products_api(request):
    items = []
    for p in Product.objects.all():
        items.append({
            "id": p.pk,
            "name": p.name,
            "category": p.category,          # or p.category.name
            "price": float(p.price) if p.price is not None else None,
            "condition": p.condition,
            "barcode": p.barcode,
            "quantity": p.quantity,
            "image": request.build_absolute_uri(p.image.url) if p.image else None,
            # include whichever specs you store:
            "metal": getattr(p, "metal", None),
            "purity": getattr(p, "purity", None),
            "weight": getattr(p, "weight", None),
            "diamond": getattr(p, "diamond_size", None),
            "stone": getattr(p, "stone_size", None),
            "quality": getattr(p, "quality", None),
            "manufacturer": getattr(p, "manufacturer", None),
            "model": getattr(p, "model", None),
            "serial": getattr(p, "serial", None),
        })
    return JsonResponse(items, safe=False)
```
`urls.py`:
```python
from django.urls import path
from . import views
urlpatterns = [
    path("api/products/", views.products_api, name="products_api"),
    # ... your existing /shop route ...
]
```

## 4. CORS (only if storefront is on a different origin)
```bash
pip install django-cors-headers
```
`settings.py`:
```python
INSTALLED_APPS += ["corsheaders"]
MIDDLEWARE = ["corsheaders.middleware.CorsMiddleware", *MIDDLEWARE]
CORS_ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]  # your storefront origin
# For local dev only, you may use: CORS_ALLOW_ALL_ORIGINS = True
```

## 5. Fastest path to "functional"
- **Recommended:** do this in **Claude Code** with the handoff package. Rebuild the storefront in your app (or drop the standalone HTML into your Django `static/`/`templates/`), serving it from `localhost:8000` so it shares the API origin — then it connects with zero CORS setup.
- **Quick test now:** add the `/api/products/` view above, then open the storefront with `?api=http://localhost:8000/api/products/`. If your API allows the origin, the green badge appears and live products fill the shop.

Tell me your exact endpoint URL + one real product record and I'll pin the field mapping to your data precisely.
