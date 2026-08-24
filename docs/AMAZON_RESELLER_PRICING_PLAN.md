# Amazon Reseller Pricing Plan — ABC MoneyLoan

Goal: sell pawnshop items on **Amazon** as a third sales channel (alongside the
in-store shop, the website, and the planned eBay integration) **without losing
money**. Amazon takes a bigger and more layered cut than eBay, so the price we
list at has to be worked *backwards* from the fees and a target profit margin —
not just "cost + a bit."

This doc explains exactly what Amazon charges, gives the formula that guarantees
a **minimum 30% margin** (aim higher when you can), and flags which pawnshop
inventory Amazon will and won't let us sell.

> **Companion tool:** `docs/amazon-reseller-pricing-calculator.html` — open it in
> a browser (double-click), type in an item's cost, and it tells you the minimum
> Amazon price to hit your margin. No install, works offline.

---

## Step 1 — What Amazon actually charges

There are costs that hit **every item**, and one that hits **every month**:

| Cost | How much | Charged |
|------|----------|---------|
| **Professional selling plan** | **$40 / month** (flat) | **Per month** — not per item. Whether you sell 1 or 1,000 |
| **Referral fee (commission)** | **8%–15% of the sale price** | **Per item.** % depends on the category |
| **FBA fulfillment fee** | **flat ~$3–5 per item** for small/standard items (2026) | **Per item**, only if Amazon ships it (FBA). Covers pick, pack & shipping to the buyer |
| **FBA storage fee** | **~$0.87 / ft³ per month** (Jan–Sep), **~$2.40 / ft³** in Q4 (Oct–Dec) | **Per month**, only under FBA, from the day it arrives until it sells |

> **Important:** the **$40 is monthly overhead**, not a per-item cost. We do **not**
> bake it into each item's price. Instead we price each item on its own costs +
> margin, then check how many items we need to sell to cover the $40. See Step 3.

Plus **our own costs** per item:

- **Product cost** — what the item is worth to us / booked at (COGS).
- **Transportation** — see the next section; this one confuses people.

### Transportation — who pays, and for which leg

There are two shipping legs and Amazon treats them differently:

- **Outbound (Amazon → buyer): included.** Under FBA, shipping the item to the
  customer is already inside the FBA fulfillment fee. You don't pay it separately.
- **Inbound (our shop → Amazon's warehouse): we pay.** Either through Amazon's
  discounted **Partnered Carrier** program or our own UPS/FedEx. There can also be
  an **inbound placement fee (~$0.27–$1.58/unit)** if we don't spread stock across
  several warehouses.

So in the calculator, "shipping you pay" = **inbound** cost under FBA. Under **FBM**
(we ship it ourselves) it's our **outbound postage + box** to the buyer instead.

### FBM vs FBA

- **FBM (Fulfilled By Merchant)** — *we* store the item and ship it when it sells.
  No FBA fee, **no storage fee**, but we pay our own postage. **Lowest risk for a
  pawnshop** — nothing is shipped away, nothing racks up storage.
- **FBA (Fulfilled By Amazon)** — we send items in; Amazon stores, packs, ships,
  and handles returns. Convenient and Prime-eligible, but adds the fulfillment fee
  **and** monthly storage (below). Best for items we're confident sell fast.

### When storage is charged (matters for a pawnshop)

Under FBA, storage is billed **every month the item sits**, from arrival:

- **Monthly storage:** ~$0.87/ft³ (Jan–Sep 2026), rising to ~$2.40/ft³ in Q4.
- **Aged-inventory surcharge** now starts at **180 days** (used to be 271):
  +$1.50/ft³/mo at 180–270 days, then **$0.30/unit** at 12–15 months, **$0.35/unit**
  at 15+ months (whichever is greater). For small items the per-unit fee usually
  wins.

⚠️ Pawn items are one-offs. If a unique item doesn't sell on FBA, storage + aged
fees pile up month after month and quietly eat the margin. **Start with FBM** and
only move fast sellers to FBA.

---

## Step 2 — The margin formula (per item)

We want profit to be **at least 30% of the sale price** (margin on revenue), and
we compute this **per item** — the $40/month is handled separately in Step 3.

**If Amazon's FBA fee is entered as a % (rough):**

```
                 Product cost + Shipping we pay + Storage
Min price  =  ────────────────────────────────────────────────
              1  −  Referral %  −  FBA %  −  Target margin %
```

**If the FBA fee is a flat $ (accurate — recommended):**

```
                 Product cost + Shipping + Storage + FBA fee ($)
Min price  =  ──────────────────────────────────────────────────
                        1  −  Referral %  −  Target margin %
```

Why divide? The referral fee (and the FBA fee, when entered as a %) are slices of
the **final price**, which we don't know yet. The division solves for the price
that makes the fees and our profit all come out right at once.

### Worked example (FBA fee as 10%)

Item cost **$10**, shipping **$2**, no storage, referral **15%**, **FBA (10%)**,
target margin **30%**:

```
Min price = (10 + 2) / (1 − 0.15 − 0.10 − 0.30)
          = 12.00 / 0.45
          = $26.67   →  list at $26.99
```

Check it back:

| Line | Amount |
|------|--------|
| Sale price | **$26.67** |
| − Referral fee (15%) | − $4.00 |
| − FBA fee (10%) | − $2.67 |
| − Product cost | − $10.00 |
| − Shipping | − $2.00 |
| **= Profit per item** | **$8.00** |
| **Margin (profit ÷ price)** | **30.0%** ✅ |

> Use the calculator's **"$ / item" FBA mode** and enter Amazon's real fulfillment
> fee (often ~$3–5, i.e. more than 10% on a cheap item) for a true number before
> going live.

---

## Step 3 — Covering the $40/month (this is where the monthly fee lives)

The $40 doesn't change any single item's price — it's a fixed monthly bill we
cover out of total profit. The only question is **how many items pay for it**:

```
Items needed to cover the $40  =  $40  ÷  profit per item
```

From the example above ($8.00 profit/item): **$40 ÷ $8.00 = 5 items/month** just to
break even on the plan. Every item after the 5th is real profit.

**Net monthly profit** = (profit per item × items sold) − $40.
At 100 items/month: (100 × $8.00) − $40 = **$760/month**.

> **Low volume is the trap.** At $8/item you need 5 sales/month to cover the plan.
> If you'll sell fewer than ~**40 items/month**, compare Amazon's **Individual plan**
> (no $40, but ~$0.99 per item sold): set the monthly plan to $0 in the calculator
> and add $0.99 to shipping to model it.

---

## Step 4 — Price cheat-sheet (item $10, shipping $2, 30% margin, per item)

Round the calculator's number **up** to a tidy price — never down.

| Scenario | Referral | Fulfillment | Min price |
|----------|:--------:|:-----------:|:---------:|
| Best case (low-fee category, we ship) | 8% | FBM | **$19.35** |
| Low-fee category, Amazon ships | 8% | FBA (10%) | **$23.08** |
| Typical category, we ship | 15% | FBM | **$21.82**\* |
| Typical category, Amazon ships | 15% | FBA (10%) | **$26.67** |

\* FBM shows a lower price only because the FBA fee is gone — but your own postage
is now inside "shipping," so bump that number up for FBM.

---

## Step 5 — Pawnshop reality check: what Amazon lets us sell used

Amazon has **no rule against pawnshops**. Anyone can sell used goods if they grade
condition honestly (Like New / Very Good / Good / Acceptable) and meet Amazon's
performance standards. **But some categories are new-only** — and two of them are
core pawn stock:

**❌ New only — don't list used:**
- **Jewelry** (fine *and* fashion) — must be new.
- **Watches** — new only. (Narrow "Certified Pre-Owned" exception exists but needs
  third-party certification — impractical for us to start.)
- Beauty, Health & personal care, Grocery, Baby (except apparel), Toys & Games.

**✅ Used is fine (good Amazon fit):**
- **Electronics, cameras, PC** — allowed used, but often **"gated"** (need Amazon's
  approval to list the category/brand first).
- **Tools, musical instruments.**
- **Video games, books, movies, music.**
- Most general merchandise.

**Takeaway:** keep **jewelry and watches** — our biggest pawn categories — **in-store
or on eBay**, not Amazon. Point Amazon at allowed, liquid used goods (electronics,
tools, instruments, media). Keep proof of purchase for branded items — used branded
goods can draw authenticity/IP complaints.

---

## Step 6 — Rules of thumb before we list anything

1. **Check the item's real market price first.** The calculator gives the *floor*.
   If similar items on Amazon sell for **less** than our floor, don't list it — sell
   it in-store or on eBay. The calculator flags this when you enter a market price.
2. **Start FBM.** Lower risk, no storage clock, nothing shipped away. Move only
   proven fast sellers to FBA.
3. **Know your category's referral %.** Electronics ≈ 8%, most general goods ≈ 15%.
   Look it up per category before pricing.
4. **30% is the floor, not the target.** Aim higher (35%+) on fragile or
   high-return items — returns and damage aren't in the model.
5. **Round prices up**, to psychological price points ($26.67 → $26.99).

---

## Step 7 — What's done / what's next

- ✅ This plan + the interactive calculator (works offline, no account needed).
- ⬜ Confirm the referral % for the categories ABC actually sells.
- ⬜ Pull **real FBA per-item fulfillment fees** for a few sample items (Amazon's
  Revenue Calculator) and use the calculator's "$ / item" mode.
- ⬜ Get **ungated** in Electronics/Camera if that's where our sellable stock is.
- ⬜ Decide FBA vs FBM as the default (recommend **FBM to start**).
- ⬜ Later: wire Amazon in as a `sold_channel` like eBay, so an item sold on Amazon
  is marked sold here and protected from the Bravo re-import.

No Amazon API work happens until we've validated a handful of items are actually
profitable using the calculator.

---

### Sources (Amazon fee & policy figures, 2026)

- [Amazon FBA fees 2026 breakdown — AMZ Prep](https://amzprep.com/amazon-fba-fees/)
- [Amazon FBA storage fees 2026 — ConversionPerk](https://www.conversionperk.com/amazon-fba-storage-fees-2026/)
- [Amazon inbound placement fees 2026 — AMZ Prep](https://amzprep.com/amazon-inbound-placement-fees/)
- [Amazon condition guidelines — Sell on Amazon](https://sell.amazon.com/blog/amazon-condition-guidelines)
- [Marketplace items condition guidelines — Amazon](https://www.amazon.com/gp/help/customer/display.html?nodeId=201889720)
- [Guide to selling used products on Amazon — Threecolts](https://www.threecolts.com/blog/selling-used-products-amazon/)

*Fees change often and vary by item size/weight and category — treat these as
planning estimates and confirm the exact numbers in Seller Central before listing.*
