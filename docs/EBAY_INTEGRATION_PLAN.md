# eBay Integration Plan — ABC MoneyLoan

Goal: from this system, **list an item on eBay (photo + details) with one click**,
and when it sells on eBay, **mark it sold here automatically** so it leaves the
shop and the Bravo re-import can't resurrect it. eBay becomes a sales *channel*
alongside the in-store shop and the website.

This is a real API integration and can't be built without an eBay developer
account. This doc is what to hand to whoever sets that up, plus the build plan.

---

## Step 1 — Get eBay API access (the part ABC must do)

1. Create a free **eBay Developer account**: https://developer.ebay.com → Register.
2. In the developer portal, create an **application keyset**. You'll get:
   - **App ID (Client ID)**, **Cert ID (Client Secret)**, **Dev ID**.
   - Start in the **Sandbox** (test) environment, then switch to **Production**.
3. Authorize the **seller account** (the store's real eBay account) via
   **OAuth "user token"** with these scopes (Sell APIs):
   - `sell.inventory` (create/manage listings)
   - `sell.account` (business policies: payment, return, shipping)
   - `sell.fulfillment` (read orders → know when something sold)
4. Set up **business policies** on the eBay account (payment, return, shipping) —
   eBay requires these to publish fixed-price listings.
5. Give me (securely): App ID, Cert ID, Dev ID, the OAuth refresh token, and the
   store's eBay username. These get stored **only on the store PC** (encrypted /
   in a local config file, never committed to git).

> Reality check: eBay's Sell API onboarding (keyset + production access +
> business policies) usually takes a bit of back-and-forth with eBay. Sandbox
> first lets us build and demo before the real account is fully approved.

## Step 2 — What I build here (once keys exist)

**a. "List on eBay" button** on the item Edit page (and optionally bulk from a
campaign / aged-stock list). It sends the item to eBay via the **Inventory API**:
- Title = description (trimmed to eBay's 80-char limit)
- Price = retail_price
- Condition = our `condition` / "Used"
- Category = mapped from our category → eBay category ID (a lookup table we build)
- Photos = the item's photo (eBay needs a hosted image URL; we expose the
  item's `/uploads/...` image, or upload to eBay's picture service)
- Specs = jewelry (metal/purity/weight/diamond) or electronics (brand/model)
  mapped to eBay item aspects.

**b. Listing status tracking**: store the eBay listing ID + status on the item
(new columns: `ebay_listing_id`, `ebay_status`). Show a badge in inventory
("Listed on eBay").

**c. Auto-sold sync**: a scheduled job (like the Layer-1 auto-import) polls the
eBay **Fulfillment API** for new orders; when an item sells on eBay it's marked
`sold`, `sold_channel='eBay'`, removed from the shop, and protected from the
next Bravo re-import (already handled by the sold guard).

**d. Guardrails**: never list an item that's already sold; don't double-list;
respect quantity for bulk items; a "Remove from eBay" (end listing) action.

## Step 3 — What already exists (groundwork done)

- `sold_channel` field + eBay shows as a channel on the Sales Dashboard.
- Every item already has photo, description, price, condition, and category.
- The customer website + `/api/products/` feed prove the field mapping works.
- The auto-import scheduler pattern is reusable for the eBay order-sync job.

## Open decisions (answer when we start)

1. **Sandbox demo first, or wait for production approval?** (Recommend sandbox.)
2. **Which items go to eBay** — manual per-item, or auto-list a category / the
   aged-stock offers?
3. **Photos** — use the images we already store, or require a real photo before
   listing (eBay rejects listings without an image)?
4. **Pricing** — list at retail_price as-is, or apply an eBay markup for fees?

No code will be written for this until an eBay developer keyset is available.
