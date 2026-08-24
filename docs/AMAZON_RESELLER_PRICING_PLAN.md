# Amazon Reseller Pricing Plan — ABC MoneyLoan

Goal: sell pawnshop items on **Amazon** as a third sales channel (alongside the
in-store shop, the website, and the planned eBay integration) **without losing
money**. Amazon takes a bigger and more layered cut than eBay, so the price we
list at has to be worked *backwards* from the fees and a target profit margin —
not just "cost + a bit."

This doc explains exactly what Amazon charges, gives the formula that guarantees
a **minimum 30% margin**, and points to the interactive calculator that does the
math per item.

> **Companion tool:** `docs/amazon-reseller-pricing-calculator.html` — open it in
> a browser (double-click), type in an item's cost, and it tells you the minimum
> Amazon price to hit your margin. No install, works offline.

---

## Step 1 — What Amazon actually charges

There are **three separate costs**, and they stack on every sale:

| # | Cost | How much | When |
|---|------|----------|------|
| 1 | **Professional selling plan** | **$40 / month** (flat) | Every month, whether you sell 1 item or 1,000 |
| 2 | **Referral fee (commission)** | **8%–15% of the sale price** | Taken out of every item sold. The exact % depends on the category |
| 3 | **Fulfillment** | **+ ~10% of the sale price** if Amazon ships it (FBA) | Only if you let Amazon store & ship |

On top of Amazon's fees, **our own costs** per item:

- **Product cost** — what the item is worth to us / what it's booked at (COGS).
- **Transportation** — shipping the item (inbound to Amazon for FBA, or the box +
  postage you pay to the buyer for FBM). This is easy to forget and it eats margin.

### FBM vs FBA — quick clarification

- **FBM (Fulfilled By Merchant)** = *we* store the item and ship it ourselves when
  it sells. No 10% Amazon fulfillment fee, **but** we pay our own box + postage
  (put that in "transportation").
- **FBA (Fulfilled By Amazon)** = we send items to Amazon; Amazon stores, packs,
  and ships them, handles returns/support. Convenient, but that's the **~10%** on
  top of the referral fee.

> **Reality note:** real FBA fees are a *flat per-item fee* based on the item's
> size and weight (plus monthly storage), not a clean 10%. For planning we use the
> **10% approximation you gave** — it's close for small/medium items and keeps the
> math simple. Before going live on FBA, check the real fee for a sample item in
> Amazon's FBA calculator and plug the exact dollar amount into "transportation."

---

## Step 2 — The margin formula (this is the whole plan)

We want profit to be **at least 30% of the sale price** (margin on revenue).
Working backwards from the fees gives the **minimum price** to list at:

```
                 Product cost + Transportation + (Monthly $40 ÷ units sold per month)
Min price  =  ─────────────────────────────────────────────────────────────────────
                       1  −  Referral %  −  Fulfillment %  −  Target margin %
```

In plain words: add up everything the item costs us (including its slice of the
$40 monthly fee), then divide by "what's left of each dollar after Amazon's cut
and our profit."

Why divide? Because the referral fee, the FBA fee, and our profit are all
percentages **of the final price** — which we don't know yet. The division solves
for the price that makes all of them come out right at once.

**The $40 is a *fixed* cost**, so we spread it over how many items we expect to
sell that month. Sell more → each item carries less of the $40. Example: 100
items/month = **$0.40 per item**; 10 items/month = **$4.00 per item**. Low volume
is punished hard — see the warning in Step 4.

### Worked example

Item cost **$10**, transportation **$2**, expecting **100 sales/month**,
referral **15%**, **FBA (+10%)**, target margin **30%**:

```
Min price = (10 + 2 + 0.40) / (1 − 0.15 − 0.10 − 0.30)
          = 12.40 / 0.45
          = $27.56
```

Check it back:

| Line | Amount |
|------|--------|
| Sale price | **$27.56** |
| − Referral fee (15%) | − $4.13 |
| − FBA fee (10%) | − $2.76 |
| − Monthly-fee share ($40 ÷ 100) | − $0.40 |
| − Product cost | − $10.00 |
| − Transportation | − $2.00 |
| **= Profit** | **$8.27** |
| **Margin (profit ÷ price)** | **30.0%** ✅ |

---

## Step 3 — Price cheat-sheet (same $10 item, $2 transport, 100/mo, 30% margin)

Round the calculator's number **up** to a tidy price — never down, or you dip
below 30%.

| Scenario | Referral | Fulfillment | Min price |
|----------|:--------:|:-----------:|:---------:|
| Best case (low-fee category, we ship) | 8% | FBM (0%) | **$20.00** |
| Low-fee category, Amazon ships | 8% | FBA (10%) | **$23.85** |
| Typical category, we ship | 15% | FBM (0%) | **$22.55**\* |
| Typical category, Amazon ships | 15% | FBA (10%) | **$27.56** |

\* FBM shows a *lower* price only because the 10% FBA fee is gone — but remember
your own postage is now inside "transportation," so bump that number up for FBM.

**Takeaway:** the same item needs a **~$7.50 higher** Amazon price under FBA at
15% ($27.56) than in the best case ($20.00) — the fees really do move the floor
that much. Always price for the scenario you're actually in.

---

## Step 4 — Rules of thumb before we list anything

1. **Check the item's real market price first.** The calculator gives the *floor*.
   If similar items on Amazon sell for **less** than our floor, that item is **not
   profitable to list** — sell it in-store or on eBay instead. The calculator flags
   this when you enter a target/market price.
2. **Volume matters.** At 10 sales/month the $40 fee is $4/item; you need real
   volume before the Professional plan pays for itself. Under ~**40 items/month**,
   consider the Individual plan (no $40 fee, but ~$0.99 per item sold) — compare
   both in the calculator by setting the monthly fee to $0 and adding $0.99 to
   transportation.
3. **Know your category's referral %.** Electronics ≈ 8%, most general goods ≈ 15%,
   jewelry can be higher. Look it up per category before pricing.
4. **Returns and damage** aren't in this model. Build a small cushion by aiming a
   little above 30% (e.g. 35%) on fragile or high-return items.
5. **Round prices up**, and to psychological price points ($27.56 → $27.99).

---

## Step 5 — What's already done / what's next

- ✅ This plan + the interactive calculator (works offline, no account needed).
- ⬜ Confirm the referral % for the categories ABC actually sells.
- ⬜ Pull real FBA per-item fees for a few sample items and replace the 10%
  approximation with exact dollars.
- ⬜ Decide FBA vs FBM as the default (recommend **FBM to start** — no inventory
  shipped away, lower risk while learning the channel).
- ⬜ Later: wire Amazon in as a `sold_channel` like eBay, so an item sold on
  Amazon is marked sold here and protected from the Bravo re-import.

No Amazon API work happens until we've validated a handful of items are actually
profitable using the calculator.
