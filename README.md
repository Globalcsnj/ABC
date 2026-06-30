# ABC MoneyLoan Pawnshop – Inventory System

## Setup

```bash
pip install -r requirements.txt
python run.py
```

Open: http://localhost:8000

## Barcode Format

| Scan | Format | Example |
|------|--------|---------|
| Location | `001` | SalesFloor 001 |
| Sublocation | `001-1` | SalesFloor 001, Section 1 |
| Item | Bravo item code | existing tags |

Item is recorded as: `001-1-ITEMCODE`

## Workflow

1. Import Bravo CSV exports (Retail / Loan / Layaway) on the Dashboard
2. Start a new Audit Session
3. Scan location → sublocation → items, repeat
4. Close session to view the report

## Bravo Export

Export from Bravo Reports menu as CSV. The system auto-detects common column names:
`Item #`, `ItemNumber`, `SKU`, `Barcode`, `Description`, `Category`, `Price`
