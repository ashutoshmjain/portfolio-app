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
- **Tax Harvest** — per-lot unrealized P&L with Long/Short holding term,
  realized gains from closed lots, $15K Medi-Cal gains guardrail + leeway
- **Charts** (leading tab) — Target vs Actual allocation; Actual vs
  Standard daily close with Y-axis $2M–$5M and $100K steps (the chart
  Google Sheets flattened)

## Data model — one row per lot

All positions live in **`portfolio.csv`** (gitignored, never pushed):

```
bank,account,account_type,asset,shares,cost_per_share,acquired_date,sold_date,sale_price_per_share
```

- **Open lot:** `sold_date` and `sale_price_per_share` blank. **Closed lot:**
  both filled. Status is DERIVED from the dates — there is no status column.
- **Partial sale = two rows** (closed sold quantity + open remainder); the
  Sell action splits automatically, never by hand.
- `account_type`: `Traditional IRA`, `Roth IRA`, `Taxable`, `HSA`, `Cash`.
  Cash rows (`CASH_USD`, savings) need no cost or dates.
- **Share edits are count CORRECTIONS, not sales** — no tax event. A sale
  always records date and price.
- Settings live in **`profile.json`** (gitignored): date of birth, monthly
  Social Security (owner + spouse), other realized gains this year + source
  note, and the sheet-ported spending base figures.

## Manage data (☰ menu)

No new tab — data work lives with the other routine actions. **Manage
data** opens a full-size window with three sections:

- **Coverage** — Bank → Account → position checklist (Shares ✓/✗, Cost
  ✓/✗, Acquired ✓/✗) with an overall progress line. Taxable = REQUIRED,
  IRA/Roth/HSA = OPTIONAL, Cash = complete. Per-account type dropdown to
  correct the type, and per-account **Download template**.
- **Template** — **Download full template** (header row only) or upload a
  filled one. Uploads validate FIRST (bad numbers/dates, sold-without-price,
  type conflicts) and change nothing on failure; on success they MERGE by
  account+asset, leaving every other position untouched. Fill it yourself,
  or paste broker screenshots into ChatGPT, Muse, Gemini, or any AI and ask
  it to fill the template, then upload here.
- **Profile** — date of birth, SS amounts, other gains + note. Shows live
  spending capacity: before-65 $/yr, after-65 base + SS = all-in $/yr.

## Position lifecycle (Accounts tab buttons)

- **Add position** — bank, account (existing or new + type), asset, shares,
  optional cost + acquired date.
- **Sell / Reduce** — quantity + date + price; auto-splits the lot.
- **Close position** — sell-all; the row leaves holdings, enters realized
  gains. **Reopen** clears the sold fields.
- Selling without a cost on file records the gain as **unknown** — the app
  never invents basis.

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

- **Buy/sell**: use the Accounts tab buttons (Add / Sell / Close), or fill
  a template in the Data window and upload it. Then Refresh prices.
- **Home value**: open the ☰ menu, type a new Zillow value, press Apply home.
- **Log today's close** (☰ menu): appends today's row to `drift_log.csv`
  (skips weekends, like the old daily cron). Upserts if run twice.
- **Cost basis**: fill cost + acquired date per lot (Data window or
  template) to activate P&L, holding terms, and harvest rankings. Never
  invent basis — leave blank until you pull it from the broker.
- **Migration note (2026-11-02)**: `holdings.yaml` + `cost_basis.csv` were
  replaced by `portfolio.csv` + `profile.json`. The old files sit in a
  dated backup folder next to the app folder
  (`portfolio-app-backup-20261102`); delete it after a few confident runs.
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
