# Crypto-Backed ("Secure") Loan Product — Market, Legal & Process Research

**Prepared:** August 2026
**Purpose:** Feasibility research for launching a *secured* consumer/commercial loan product collateralized by cryptocurrency (a "crypto-backed loan").
**Status:** Research brief — not legal or financial advice. Engage licensed fintech counsel (money-transmission, consumer-lending, and securities) and a compliance/BSA advisor before building or marketing anything.

---

## 0. What we mean by the product

A **crypto-backed loan** (a.k.a. crypto-collateralized or Bitcoin-backed loan) is a *secured* loan: the borrower pledges a digital asset (usually BTC or ETH) as collateral and receives cash or a stablecoin (USD/USDC). The borrower keeps ownership of the crypto (subject to the lender's security interest), pays interest, and gets the collateral back when the loan is repaid. Because it is **over-collateralized**, it is fundamentally different — legally and financially — from the *unsecured* "earn interest on your deposits" products (Celsius, BlockFi Interest Accounts) that collapsed in 2022.

This is the correct model to build. The failures below happened because platforms mixed custody, lending, and speculative asset deployment. A clean product keeps them separate.

---

## 1. Market size & growth projection

| Metric | Value | Source |
|---|---|---|
| Crypto lending **platform revenue** market, 2025 | **$10.68B** | Research and Markets |
| Same, 2026 | **$12.69B** (18.8% CAGR) | Research and Markets |
| Projected 2030 | **$25.06B** (~18.5% CAGR) | Research and Markets |
| **Outstanding crypto-collateralized loans**, Q3 2025 | **$73.59B** (new cycle high) | AMINA Bank / industry data |
| Bitcoin-loan segment, 2025 | **$12.4B** → projected **$58.7B** by 2034 (18.9% CAGR) | Extrapolate / Dataintelo |

**Read-through for a projection:** the sector is compounding at roughly **18–19% per year** and is expected to roughly **double every ~4 years** through 2030. Outstanding collateralized loan balances (the number that matters for a lender) already sit near **$74B** and are back above the previous (2021) cycle peak. Growth drivers cited: institutional borrowing, demand for *compliant* platforms, cross-chain lending, real-time collateral monitoring, and "buy-borrow-don't-sell" tax strategies among long-term holders.

### Illustrative unit economics for a projection model
Assume a conservative launch:
- Interest spread (borrower rate − cost of capital): **6–9%** net.
- Origination fee: **1–2%** of principal.
- Loan book target Year 1: **$10M** originated → at ~7% net spread + 1.5% origination ≈ **$0.85M** gross revenue on that book (before losses, opex, custody, insurance).
- Expected credit loss on a well-run 50% LTV, auto-liquidating book is **low** (collateral is liquid and over-collateralized) — the dominant risks are operational, custody, and gap/liquidation-slippage risk in a fast crash, not ordinary default.

> These are planning placeholders. Build a real model with your actual cost of capital, LTV bands, liquidation assumptions, and a stress scenario (e.g., BTC −40% in 24h with thin liquidity).

---

## 2. Who does it now, and market share

The market splits into **DeFi** (on-chain protocols) and **CeFi** (companies).

- **DeFi ≈ 62.7%** of outstanding loans; **CeFi ≈ 37.3%** (Q3 2025).

### CeFi (companies — most relevant to your product)
| Company | Secured loan book / position | Share of *tracked CeFi* lending |
|---|---|---|
| **Tether** | ~$14.6B secured loans | **~59.9%** |
| **Nexo** | ~$2.04B | — |
| **Galaxy** | ~$1.8B | — |
| *Top 3 combined* | — | **~75.7%** |

Other active CeFi lenders/consumer platforms: **Ledn**, **YouHodler**, **CoinLoan**, **Coinbase** (BTC-backed loans via Morpho, relaunched Jan 2025), **Binance**, **Kraken**, plus newer "no-rehypothecation / qualified-custody" entrants like **Arch Lending** and **CoinRabbit**. **BlockFi, Celsius, and Genesis** are defunct (2022–2023 bankruptcies) — their exit is precisely why the compliant slots reopened.

- **Consumer Bitcoin-loan niche:** **Ledn originated ~$1.4B in BTC-backed loans in 2025** and claims **~30% of the consumer market** — a useful benchmark for a consumer-focused entrant.

### DeFi (protocols)
**Aave**, **Morpho**, **Compound**, **Maker/Sky** dominate. They are over-collateralized, transparent, and non-custodial — the structural template even CeFi now imitates.

**Takeaway:** CeFi is *concentrated* (Tether + a few big players), but the **compliant, consumer/SMB, U.S.-licensed** segment is fragmented and still forming after the 2022 shakeout. That gap — trust + compliance + qualified custody — is the opening.

---

## 3. The laws that involve this business (U.S. focus)

There is **no single crypto-lending license**. A compliant product sits at the intersection of *several* regimes. This is the hardest and most expensive part of the build.

### 3.1 Federal
- **FinCEN / Bank Secrecy Act (BSA):** Register as a **Money Services Business (MSB)**; run an **AML/KYC** program, SARs/CTRs, sanctions (OFAC) screening. Almost certainly applies if you move crypto or fiat for customers.
- **SEC (securities law):** The **critical lesson.** The SEC treated *unsecured, pooled-yield* products (BlockFi Interest Accounts, Celsius Earn) as **unregistered securities** (Howey test). **BlockFi settled for $100M in Feb 2022.** A clean, *individually-collateralized, over-collateralized loan where the borrower retains title* is designed to avoid the "investment contract" characterization — but the way you fund the loan book and any yield offered to depositors can drag you back into securities law. **Do not offer retail a pooled-interest deposit product** without securities counsel.
- **CFTC:** Asserts commodity jurisdiction over BTC/ETH spot markets; relevant to margin/leverage and liquidation mechanics.
- **Truth in Lending Act (TILA) / Regulation Z:** For **consumer** credit, requires written disclosures of the **finance charge and APR**, plus advertising disclosure rules. Applies regardless of the collateral being crypto.
- **Other consumer statutes:** ECOA (fair lending / anti-discrimination), FCRA (if credit reporting/checks), UDAAP (CFPB — deceptive practices), GLBA (data privacy/safeguarding).

### 3.2 State — the heavy lift
- **Money Transmitter Licenses (MTLs):** As of 2026, businesses that transmit, exchange, or custody digital assets for customers must be **licensed in nearly every state** where they have customers. Applied for largely via **NMLS**; expect **surety bonds and minimum net-worth** requirements per state. New York requires the **BitLicense**.
- **Lender / consumer-finance licenses:** Separate from MTLs. Which license depends on **who the borrower is (consumer vs. business), the interest rate, the loan amount, and the product structure.** Many states run these through NMLS too, with a bond + net-worth minimum. **There is no national lending license.**
- **Usury caps:** States cap interest rates and fees. Example: **New York** generally requires a *Licensed Lender* license for consumer loans ≤ $25,000 above **16%**, and **criminal usury** exposure exists at higher rates. Rates you can charge vary widely by state.
- **"True lender" / bank-partnership scrutiny:** States are actively legislating against the model of routing loans through a partner bank to export a higher rate. Some states are opting out of DIDMCA rate exportation. If you plan a bank-partner structure, this is a live risk.
- **UCC (secured-transactions law):** 2022–2026 amendments (Article 12 on "controllable electronic records") changed how you **perfect a security interest** in crypto collateral. Getting perfection right is what makes your loan actually *secured* in a borrower bankruptcy.

### 3.3 Custody & the anti-rehypothecation rule (the make-or-break)
The single clearest post-collapse lesson from Celsius/BlockFi/Genesis:
- Hold pledged collateral in a **segregated, qualified-custody account**;
- Documents leave **title with the borrower**, subject only to the lender's **security interest**;
- The custodian has **no right of use or rehypothecation** (no re-pledging the same coins across multiple loans — the exact practice that sank Celsius).

Combining custody + lending + speculative deployment without clear disclosures is what regulators and bankruptcies punished. **Don't.**

### 3.4 Federal legislative backdrop (2025–2026, moving)
- **GENIUS Act** — signed into law **July 18, 2025**. First federal framework for **payment stablecoins** (issuer licensing, hard reserves). *Narrow:* it governs stablecoin issuers, **not** lenders — you still need state MTLs and lending licenses. But it makes USD-stablecoin loan disbursement cleaner.
- **CLARITY Act** — passed the **House (294–134) in July 2025**, **pending in the Senate**. Market-structure bill: gives CFTC exclusive jurisdiction over digital-commodity spot markets, carves out truly decentralized DeFi, clarifies SEC-vs-CFTC lines. If it becomes law, it materially reduces the "regulation by enforcement" uncertainty this sector operates under. **Monitor it.**

> **Non-U.S. note:** If you'd operate outside the U.S., the frameworks differ sharply (EU **MiCA**, UK FCA, UAE VARA, Switzerland FINMA). Pick your jurisdiction early — it drives the whole compliance build.

---

## 4. How the loan works (the process)

### 4.1 Borrower flow
1. **Onboard / KYC-AML** — identity, sanctions screening, (for consumers) TILA-triggered disclosures.
2. **Deposit collateral** — borrower sends BTC/ETH to a **segregated qualified-custody** wallet. Title stays with borrower; you take a perfected security interest.
3. **Set LTV & disburse** — loan amount = collateral value × starting LTV. **Typical starting LTV is 50–60%.** Borrower receives USD or a stablecoin.
4. **Service** — borrower pays interest (monthly, or accrued on a revolving line).
5. **Monitor** — real-time collateral valuation; track LTV as the crypto price moves.
6. **Margin / liquidation** — if price falls and LTV rises to the **liquidation threshold**, issue a margin call (often a **24-hour grace period** to add collateral or partially repay). If not cured, **auto-liquidate** enough collateral to restore the target LTV.
7. **Repay & release** — borrower repays principal + interest; collateral returned in full.

### 4.2 Key parameters (2026 market benchmarks)
| Parameter | Market norm | Notes |
|---|---|---|
| **Starting LTV** | 50–60% | Conservative = lower rate + more crash buffer |
| **Max LTV** | ~50% (Ledn), ~50% (Nexo per asset) | Higher LTV = higher liquidation risk |
| **Liquidation LTV** | ~65–90% depending on platform | The threshold that triggers forced sale |
| **Consumer APR** | **~5%–11.5%** (Ledn ~9.25–11.49%; Coinbase/Morpho opens ~5%, floats; Nexo 1.9%–18.9% tiered) | Rate scales with LTV, loan size, and (Nexo) token holdings |
| **Term** | 12-month fixed (Ledn) *or* open revolving credit line (Nexo) | Two viable product shapes |
| **Loan size** | $1,000 – $1,000,000 (Ledn) | Set floors/ceilings to match your capital & risk |

### 4.3 Product-design decisions you must make
- **Custody model:** cold-storage-only (charge more, safest, easiest trust story) **vs.** lend out collateral (cheaper rate, but re-introduces the rehypothecation risk you're trying to avoid). **Recommend cold-storage / no-rehypothecation** for a trust-first launch.
- **Fixed-term vs. revolving line.**
- **Disbursement in fiat vs. stablecoin** (stablecoin is operationally simpler; fiat needs banking rails).
- **Liquidation engine:** partial-liquidation with grace period is more borrower-friendly and reduces churn/complaints; needs a robust price oracle and execution venue to avoid slippage in a crash.
- **Source of lending capital:** your balance sheet, a credit facility, or institutional partners — **not** a retail pooled-yield deposit product (securities-law trap).

---

## 5. Why lenders failed — the "do it right" checklist

Celsius, BlockFi, Genesis, Hodlnaut all **froze withdrawals and went bankrupt in 2022**. Root causes and the fix:

| Failure mode | What went wrong | Do this instead |
|---|---|---|
| **Rehypothecation** | Same collateral re-pledged across multiple loans (Celsius) | Contractual **no-rehypothecation**; segregated custody |
| **Unsecured lending** | Lent to counterparties with weak/no collateral | **Over-collateralized only**, per-loan |
| **Counterparty concentration** | BlockFi's ~$680M Alameda exposure | Diversify; limit single-counterparty exposure |
| **Custody/lending mixed** | Opaque commingling of customer assets | Separate custody, lending, and treasury; disclose clearly |
| **Unregistered securities (yield to retail)** | BlockFi $100M SEC settlement (Feb 2022) | No pooled retail-yield product without registration/exemption |
| **Opaque leverage** | Hidden risk parameters | Transparent LTV, liquidation, and reserve disclosures |

---

## 6. Recommended path to launch (sequenced)

1. **Pick jurisdiction & customer type** (U.S. consumer? U.S. business-only? offshore?). Business-only lending avoids much consumer-protection burden; U.S. consumer is the biggest market but the heaviest lift.
2. **Engage counsel** — fintech regulatory (MTL/BitLicense), consumer-lending (TILA/usury/licensing), securities (funding & any yield side), and BSA/AML.
3. **Licensing plan** — map required MTLs + lender licenses state-by-state (NMLS); budget for bonds and net-worth minimums. Consider launching in a **narrow set of favorable states** first.
4. **Custody & security-interest design** — qualified custodian, segregation, UCC Article 12 perfection, no rehypothecation.
5. **Risk engine** — LTV bands, oracle/pricing, margin-call + liquidation logic, stress tests.
6. **Compliance stack** — KYC/AML/OFAC, TILA disclosures, recordkeeping, complaint handling.
7. **Capital & unit-economics model** — cost of funds, spread, origination fee, loss/liquidation-slippage reserve, insurance.
8. **Monitor legislation** — CLARITY Act (Senate) and any lending-specific rules; they can shift the compliance map quickly.

---

## 7. Bottom line

- **Market:** real and growing ~**18–19%/yr**; **~$74B** outstanding collateralized loans (Q3 2025); platform revenue **~$12.7B (2026) → ~$25B (2030)**.
- **Competition:** CeFi is concentrated (**Tether ~60%**, top-3 ~76%), but the **compliant, licensed, no-rehypothecation, consumer/SMB** slot is open — the exact gap left by Celsius/BlockFi. Ledn (~30% of the *consumer* BTC-loan niche) is the benchmark to beat.
- **Legal:** the barrier and the moat. Expect a **multi-license** build (FinCEN MSB + state MTLs/BitLicense + state lender licenses), **TILA** disclosures for consumers, **usury** caps, **UCC** perfection, and **airtight custody with no rehypothecation**. Avoid the securities trap by **not** offering pooled retail yield.
- **Product:** over-collateralized, ~**50% starting LTV**, transparent liquidation with a grace period, cold-storage custody, fiat/stablecoin disbursement, priced ~**5–11% APR** to compete.

---

## Sources
- [Crypto Lending Platform Market Report 2026 — Research and Markets](https://www.researchandmarkets.com/reports/6103510/crypto-lending-platform-market-report)
- [Crypto Lending in 2026: How Borrowing Against Bitcoin Is Reshaping Global Credit — AMINA Bank](https://aminagroup.com/research/crypto-lending-in-2026-how-borrowing-against-bitcoin-is-reshaping-global-credit/)
- [Cryptocurrency Lending Market — MarketsandMarkets](https://www.marketsandmarkets.com/Market-Reports/cryptocurrency-lending-market-238822701.html)
- [Ledn identifies massive turning point for crypto lending markets — Yahoo Finance](https://finance.yahoo.com/markets/crypto/articles/ledn-identifies-massive-turning-point-100402318.html)
- [5 leading Bitcoin-backed loan platforms in 2026 — crypto.news](https://crypto.news/5-leading-bitcoin-backed-loan-platforms-in-2026/)
- [Ledn Leads Bitcoin-Backed Loan Platforms in 2026 — CryptoNexa](https://www.cryptonexa.com/ledn-leads-bitcoin-backed-loan-platforms-in-2026-as-market-hits-record)
- [Bitcoin Loan Market Size — Extrapolate](https://extrapolate.com/Information-Technology-Communication-IoT/Bitcoin-Loan-Market-Size-Share-and/22820)
- [Understanding US Cryptocurrency Regulations in 2025 — Faisal Khan](https://faisalkhan.com/solutions/licensing/money-transmitter-license-mtl/us-cryptocurrency-regulation/)
- [US Crypto Regulations: Federal and State Rules (2026) — Sumsub](https://sumsub.com/blog/us-crypto-regulations/)
- [State-by-State Crypto Licensing Map: 2026 — Astraea Counsel](https://astraea.law/insights/state-by-state-crypto-licensing-map-2025)
- [How Do Crypto-Backed Loans Work — Northwestern (Learner)](https://sites.northwestern.edu/learner/how-do-crypto-backed-loans-work/)
- [Loan-to-Value Ratio and Liquidation (Crypto Loans) — Bybit Help Center](https://www.bybit.com/en/help-center/article/Loan-to-Value-Ratio-and-Liquidation-Crypto-Loans)
- [Best Bitcoin-Backed Loan Rates in 2026 — Ledn Blog](https://www.ledn.io/post/bitcoin-loan-rates)
- [Crypto-backed loans compared: Nexo vs. Ledn — Nexo](https://nexo.com/blog/nexo-vs-ledn-crypto-backed-loans)
- [Best U.S. Crypto Loan Lenders in 2026 — Milo](https://www.milo.io/blog/best-us-crypto-loan-lenders-in-2025-rates-and-features-compared/)
- [Why Crypto Lenders Fail: Lessons for Investors — FinanceFeeds](https://financefeeds.com/why-crypto-lenders-fail-lessons-for-investors/)
- [Why Bitcoin-backed loans need qualified custody and no rehypothecation — crypto.news](https://crypto.news/why-bitcoin-backed-loans-need-qualified-custody/)
- [Bitcoin Loans Are Back, But Rehypothecation Still Lingers — Cointelegraph](https://cointelegraph.com/news/bitcoin-loans-back-rewriting-book-celsius-burned)
- [Lending Against Digital Assets: Five Key Takeaways After a Year of UCC Change — Crowell FinTalk](https://www.crowellfintalk.com/2026/08/lending-against-digital-assets-five-key-takeaways-for-lenders-after-a-year-of-regulatory-and-ucc-change/)
- [A Primer on State Consumer Financial Regulation — Venable LLP](https://www.venable.com/insights/publications/2025/02/a-primer-on-state-consumer-financial-regulation)
- [Truth in Lending Act (TILA) & Regulation Z — NCUA](https://ncua.gov/regulation-supervision/manuals-guides/federal-consumer-financial-protection-guide/compliance-management/lending-regulations/truth-lending-act-regulation-z)
- [States Expand Regulation of Consumer Lending: "True Lender" & DIDMCA — Stinson LLP](https://www.stinson.com/newsroom-publications-states-expand-regulation-of-consumer-lending-codification-of-true-lender-and-opt-out-of-didmcas-interest-exportation)
- [Clarifying the CLARITY Act — Arnold & Porter](https://www.arnoldporter.com/en/perspectives/advisories/2025/08/clarifying-the-clarity-act)
- [What the GENIUS and Market Structure Bills Mean for Crypto Compliance — Chainalysis](https://www.chainalysis.com/blog/genius-act-market-structure-bills-crypto-compliance-july-2025/)
