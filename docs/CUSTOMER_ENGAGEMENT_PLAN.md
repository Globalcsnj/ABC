# Customer Engagement — Brainstorm & Plan

Now that each sale can carry **customer name + phone** (from the Sold report),
we can turn one-time buyers into repeat customers. Two ideas:

1. **Post-purchase thank-you text** (short-term).
2. **Customer analysis + item recommendations** (builds on #1).

---

## 1. Post-purchase thank-you SMS

### How it would work
- After the daily Sold-report import, the system builds a list of buyers with a
  phone number who bought that day.
- Staff reviews the list (one screen) and clicks **Send** — or it auto-sends.
- A texting gateway delivers the message. Options:
  - **Twilio / Telnyx** (pay-per-text, ~1¢–3¢ each, reliable, needs an account +
    a sending number). Recommended.
  - Store PC's own phone/Google Voice (manual, free, doesn't scale).

### ⚠️ Legal (important — must do before sending)
US texting is governed by **TCPA / carrier rules**. To stay compliant:
- **Get consent at the counter** — a checkbox/line on the receipt or a quick
  "OK to text you?" Yes/No captured at sale (add a `sms_opt_in` field).
- **Every message includes an opt-out** — "Reply STOP to opt out."
- Don't text outside ~8am–9pm local; don't over-message.
- Keep it to transactional + light marketing.

I'd add an **opt-in flag** and only text customers who said yes.

### Message template (editable in the app)
> **Hi {first_name}, thank you for shopping at ABC MoneyLoan Pawnshop!** 🙏
> We hope you love your {item}. Questions? Call us at {store_phone}.
> Our website is coming soon — and remember, we **buy, pawn & sell jewelry,
> electronics and more**. Got something to sell or pawn? Come see us at
> 146 E. State St, Trenton.
> — Reply STOP to opt out.

Short version (fits one SMS segment, cheaper):
> Thanks for shopping at ABC MoneyLoan, {first_name}! Questions? {store_phone}.
> We buy/pawn/sell jewelry & electronics — website coming soon. Reply STOP to opt out.

Templates are stored with placeholders ({first_name}, {item}, {store_phone}) so
you can edit the wording without code changes.

---

## 2. Customer analysis & recommendations

Group sold items by **customer** (name + phone) to build a simple profile:
- **What they buy** — top categories/types (e.g. "video games", "tools", "jewelry").
- **How often & how much** — visit count, total spent, average ticket, last visit.
- **Value tier** — VIP / regular / one-time.

From that, **suggest items they might want**:
- **Same-category in stock:** they bought PS4 games → show current PS4 games /
  consoles / controllers in stock.
- **Aged stock match:** prioritize 90+ day items in their interest categories —
  moves slow inventory to a warm lead.
- **Complementary:** bought a camera → lenses, memory cards, bags.

### Where it shows up
- A **Customers** page: searchable list with profile, purchase history,
  interests, and "Recommend" button.
- Recommendations feed the **thank-you text** ("You might also like…") or a
  later **win-back text** ("New arrivals in games — come take a look").

### Data note
Matching is by **name + phone**. Phone is the reliable key (names vary), so the
opt-in capture also cleans up the customer list over time.

---

## Suggested phases
1. **Capture** (done): store customer name + phone + opt-in on each sale.
2. **Customers page**: profiles, purchase history, interests, recommendations
   (no texting yet — pure in-app, no cost, no compliance risk).
3. **Manual texting**: review-and-send thank-yous via Twilio, with opt-in + STOP.
4. **Automation**: auto-send after import; scheduled win-back campaigns tied to
   aged stock and customer interests.

## Open questions
1. Texting budget / provider — set up a Twilio account, or start with a manual
   copy-paste list the first days?
2. Capture **opt-in** at the counter? (Needed before any texting.)
3. Store phone number to put in messages?
4. Auto-send, or staff clicks Send after reviewing?
