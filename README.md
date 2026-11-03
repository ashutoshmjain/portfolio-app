# Portfolio Dashboard — Windows desktop app

Local replacement for the Google Sheets portfolio dashboard. No Google
sign-in, no API quirks, no chart-editor limits: everything runs on your
Windows PC.

## What it shows

Top-level tabs, in order: **Dashboard, Diversification, Tax Harvest,
Data Entry.** The ☰ menu holds exactly three items: Refresh stocks,
Refresh home estimates, Log.

- **Dashboard** — sub-tabs: **Overview** (landing: net worth, spending
  capacity, key alerts, Target-vs-actual allocation grouped-bar chart —
  blue Target %, red Actual %, 5 buckets, 0–50% axis — then navigation
  cards), **Accounts** (bank → account → position quantities, prices,
  values), **Holdings** (ONE expanding table filling the window, one scroll
  region: one row per asset aggregated across accounts, weighted avg cost
  over known-cost lots only; ▶/▼ expands per-account rows in place beneath
  the summary row; home is one more row; cash lives in Liquidity),
  **Liquidity** (the sheet's Liquidity Plan tab: ONE row per institution —
  Chase/chase unified case-insensitively — with Available < 65 / Available
  > 65 / of-which penalty-free at 59½ (Feb 2028, a subset of > 65) / Total;
  Cash + Taxable + HSA count < 65, Traditional + Roth IRA count > 65;
  rows expand to accounts; footer has liquid total, home, net worth, and
  years of before-65 spending covered), **Tax implications** (per-type tax
  facts, not advice, + your account→type mapping).
- **Diversification** — the 15:15:35:15:20 standard + rationale, current
  position vs standard, the same Target-vs-actual chart (one shared
  implementation — values tie exactly), rebalance plan (display only —
  NEVER executes trades), drift chart (Actual vs Standard daily close,
  Y-axis $2M–$5M, $100K steps — the chart Google Sheets flattened).
- **Tax Harvest** (view title "Tax Loss Harvesting") — per-lot unrealized
  P&L with Long/Short holding term, realized gains from closed lots, $15K
  Medi-Cal gains guardrail + leeway.
- **Data Entry** (last) — sub-tabs Inputs / Template / Profile (see below).

Deferred: an Overview news feed (earnings, Fed meetings) waits for the
AI-embedding phase — raw feeds are noisy and curation is the value. No
placeholder UI.

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

## Data Entry (last tab)

Sub-tabs Inputs / Template / Profile (reached via the tab or Overview
cards — the ☰ menu opens no window).

- **Inputs** — OPENS on the guided one-account view by default (first
  account with required gaps, taxable first; "Show all" is opt-in, "Guided"
  returns; completion state when all required accounts are fed — one
  account bounds the widget count, which keeps scrolling fast). Bank →
  Account → lot grid with an overall progress line. Taxable = REQUIRED,
  IRA/Roth/HSA = OPTIONAL, Cash = complete. No Bank/Account grid columns
  (shown in the section header); unlocked rows stay single-line — a per-row
  **↗ Move** button expands ONLY that row's bank/account line (collapses on
  Lock/Save; never duplicates). Cash rows (`CASH_USD`, Cash-type accounts)
  render as a single **Amount ($)** field — no shares/cost/date prompts,
  never flagged invalid, no Sell/Close (stored as shares=amount, cost=1).
  Closed lots listed per account, per-account type dropdown, per-account
  **Download template**, per-account live value (check vs broker),
  **+ Add row** inheriting the section, **+ Add account** (existing bank
  from dropdown or new bank as free text, plus first lot; doubles as the
  empty-state "Add your first bank / account" prompt). Rows are locked by
  default; Edit unlocks to a white row with dark text (dirty marker if
  relocked with unsaved edits). Typing stages only — Tab/Enter/arrows move,
  Save validates and commits with one recompute, Revert discards. Dates are
  typeable (YYYY-MM-DD) with a picker button; the picker header reads
  "< November 2026 >" (arrows flank at top), year/month labels open
  one-action pickers, and the popup anchors by the field without covering
  the edited row. Bad cells get a red outline, duplicates a warning, each
  row shows live cost/proceeds/gain/term arithmetic. Typing fewer shares is
  a count correction, never a sale. Edit/Lock/Save update rows in place
  (scroll preserved; only Add scrolls). Mouse wheel scrolls 5 units/notch
  app-wide, over entries and buttons too — as fast as scrollbar drag.
- **Template** — **Download full template** (header only), **Upload**,
  **Paste rows** (clipboard TSV/CSV), **Import broker CSV** (template-shaped
  exports import; anything else is plainly rejected, never guessed), and
  **Copy AI prompt** (ready-made screenshot-to-CSV prompt for any AI). The
  tab also carries a per-field broker guide (Schwab + Vanguard paths,
  CSV-export pointers, 1099-B note) as one fast-scrolling text block.
- **Profile** — date of birth, SS amounts, other gains + note, optional home
  purchase price (all editable, so a wrong seed is fixable in place). Shows
  live spending capacity: before-65 $/yr, after-65 base + SS = all-in $/yr.
- **Feed one account** — the default Inputs view (see above): one taxable
  account at a time with its broker guidance and a "N required positions to
  go" countdown, then the next incomplete account. The full grid stays
  available via Show all.

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
3. Open the ☰ menu (top right) and press **Refresh stocks**
   (Yahoo Finance). If the network fails, the app shows last-known
   prices from `prices_cache.json` and never crashes.

## Daily use

- **Buy/sell**: use the Accounts tab buttons (Add / Sell / Close), edit the
  Inputs grid, or fill a template and upload it. Then ☰ → Refresh stocks.
- **Home value**: ☰ → Refresh home estimates (prefilled prompt; no Zillow
  scraper — automatic fetching only if a reliable estimate API appears).
- **Log** (☰ menu): appends today's close to `drift_log.csv`
  (skips weekends, like the old daily cron). Upserts if run twice.
- **Cost basis**: fill cost + acquired date per lot (Inputs grid or
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
