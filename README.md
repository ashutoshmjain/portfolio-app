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
- **Lot key = account + asset + acquired_date + cost_per_share.** Uploads
  upsert on that key (match → update, no match → insert) and NEVER delete
  rows. Two open rows sharing a key are rejected as duplicates. New dated
  lots draw down the dateless (unattributed) balance for that asset,
  keeping a residual row; dated shares beyond the balance are rejected —
  nothing is ever silently dropped or double-counted. Correct a lot's date
  in the grid (net-change, no false draw); uploads only add or update.
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

- **Coverage** — Bank → Account → lot grid with an overall progress line.
  Taxable = REQUIRED, IRA/Roth/HSA = OPTIONAL, Cash = complete. Every field
  is editable inline (including bank and account, so a misfiled lot moves
  instead of being re-typed), plus closed lots, per-account type dropdown,
  per-account **Download template**, and per-account live value (check vs
  the broker statement). Rows are locked by default; Edit unlocks. Typing
  stages only — Save validates and commits everything with one recompute,
  Revert discards, closing with unsaved edits asks Save/Discard/Cancel.
  Dates are typeable (YYYY-MM-DD) with a picker button beside each; bad
  cells get a red outline, duplicates a warning, and each row shows live
  cost/proceeds/gain/term arithmetic. Typing fewer shares is a count
  correction, never a sale.
- **Template** — **Download full template** (header only), **Upload**,
  **Paste rows** (clipboard TSV/CSV), **Import broker CSV** (template-shaped
  exports import; anything else is plainly rejected, never guessed), and
  **Copy AI prompt** (ready-made screenshot-to-CSV prompt for any AI). The
  tab also carries a per-field broker guide (Schwab + Vanguard paths,
  CSV-export pointers, 1099-B note).
- **Profile** — date of birth, SS amounts, other gains + note (all editable,
  so a wrong seed is fixable in place). Shows live spending capacity:
  before-65 $/yr, after-65 base + SS = all-in $/yr.
- **Feed one account** — guided mode: one taxable account at a time with
  its broker guidance and a "N required positions to go" countdown, then
  the next. The full grid stays available.

## Position lifecycle (Accounts tab buttons + Coverage grid)

- **Add position** — bank, account (existing or new + type), asset, shares,
  optional cost + acquired date.
- **Sell / Reduce** — FIFO by default (oldest lots first, dateless last,
  one closed row per lot consumed), specific-lot override available.
- **Close position** — sell-all; the row leaves holdings, enters realized
  gains. **Reopen** clears the sold fields (also possible inline).
- **Delete lot** — per-row, with confirmation; the only way rows disappear
  (uploads never delete).
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
