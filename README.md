# Portfolio Dashboard — Windows desktop app

Local replacement for the Google Sheets portfolio dashboard. No Google
sign-in, no API quirks, no chart-editor limits: everything runs on your
Windows PC.

## What it shows

- **Accounts** — 13 accounts + home + TOTAL + Mix % (total-net-worth basis)
- **Liquidity** — before/after 65 + spendability ($135,545/yr before 65;
  $111,900/yr + SS = $11,837/mo all-in after 65)
- **Diversification** — vs the 15:15:35:15:20 standard over total net worth
- **Rebalance** — the 4 Schwab Ashu IRA trades (display only, NEVER executes)
- **Tax Harvest** — $15K Medi-Cal gains guardrail, $11,781 leeway
- **Charts** (leading tab) — Target vs Actual allocation; Actual vs
  Standard daily close with Y-axis $2M–$5M and $100K steps (the chart
  Google Sheets flattened)

## Windows setup

1. Install Python 3.11+ from python.org (tick "Add python.exe to PATH").
2. Open Command Prompt in this folder and run:
   ```
   pip install -r requirements.txt
   python portfolio_app.py
   ```
3. Open the ☰ menu (top right) and press **Refresh prices**
   (Yahoo Finance). If the network fails, the app shows last-known
   prices from `prices_cache.json` and never crashes.

## Daily use

- **Edit holdings**: change `holdings.yaml` when you buy/sell, then Refresh.
  (Same file the Sheets dashboard used as its source of truth.)
- **Home value**: open the ☰ menu, type a new Zillow value, press Apply home.
- **Log today's close** (☰ menu): appends today's row to `drift_log.csv`
  (skips weekends, like the old daily cron). Upserts if run twice.
- **Cost basis**: fill `cost_basis.csv` (account,ticker,cost_per_share) to
  activate unrealized P&L and harvest rankings in Tax Harvest. Never invent
  basis — leave blank until you pull it from the broker.
- **Drift baseline**: the calendar-year baseline is Dec 30, 2025
  (liquid $3,595K, home $931K). Every January, update BASELINE_LIQUID /
  BASELINE_HOME and JAN1_PRICES in `portfolio_calc.py` from the new
  December snapshot.

## Maintaining with Muse Code (Windows)

This is plain Python — open the folder in VS Code with Muse Code and ask
it to change views, add a tab, or adjust the standard. The logic lives in
`portfolio_calc.py` (no GUI code, testable headless); the window lives in
`portfolio_app.py` (CustomTkinter + embedded matplotlib).

## Safety

- NEVER executes trades. NEVER writes to Google Sheets. NEVER sends
  anything outward. NEVER asks for passwords.
