# Portfolio Dashboard — Windows desktop app

Local replacement for the Google Sheets portfolio dashboard. No Google
sign-in, no API quirks, no chart-editor limits: everything runs on your
Windows PC.

## What it shows

Top-level tabs, in order: **Dashboard, Diversification, Tax Harvest,
Data Entry.** The ☰ menu holds four items: Refresh stocks,
Refresh home estimates, Log, Settings.

- **Dashboard** — sub-tabs: **Overview** (landing: net worth, spending
  capacity, key alerts, a Copy summary button, then the Actual-vs-Standard
  daily-close LINE chart — blue Actual total $, red Standard total $,
  $2M–$5M / $100K steps, same shared implementation and values as
  Diversification; then the watchlist — standard asset classes
  (Octonions: the 8 mega-caps; Bitcoin: BTC + MSTR/IBIT/ARKB proxies;
  Gold: GLD) plus your own named watchlist classes, each with its class
  total; BTC's cap is COMPUTED as mined supply × price (BTC-USD carries no
  cap — never "--" when priced; supply accrues from a stored anchor at
  ~450 BTC/day), and Gold's class total is the COMPUTED above-ground stock
  × live gold price (GLD price × 10) — a different number from GLD's net
  assets in its row; fund caps without a market cap (IBIT, ARKB, VTI, any
  user-class ETF) fall back to net assets, so no fund row reads "--" when
  priced; your classes persist in profile.json and clear on delete-all
  while the standard classes always reappear; standard classes show no
  edit controls (a "standard" note only) while each user class owns its
  Add ticker row (named for the class), per-ticker Remove buttons, its own
  Delete class (confirmed) and Copy buttons, plus an Add class row below;
  unknown symbols and offline/no-data failures report differently on Add;
  Add accepts a company name too — it resolves via the price feed's symbol
  search, shows the matches for picking, and the row keeps the resolved
  name ("SQ — Block Inc.");
  columns Ticker | Price | Market cap ($T), prices updating only on Refresh
  stocks; the bottom area is reserved for the future upcoming-events
  calendar),
  **Accounts** (bank → account → position
  quantities, prices, values — data-driven from lots + the account
  registry, never a hardcoded list; rebuilds on every Save and refresh; $0
  totals show `--`, not 100%), **Holdings** (ONE expanding table filling
  the window, one scroll region: one row per asset aggregated across
  accounts; Avg purchase price and gains show ONLY when every open lot has
  cost — otherwise Avg reads `upload` with a missing-count tooltip and
  gains read `--`, per account in the ▶/▼ expansion too; home is one row
  per property labeled RE 1, RE 2 (never the full address — the row's
  numbers stay aligned; the legend below the table maps RE N to the
  address); a TOTAL row (total value + total gains, positions + home,
  cash excluded; gains total shows only when every row is computable)
  closes the table and ties to Overview net worth; cash lives in
  Liquidity),
  **Liquidity** (the sheet's Liquidity Plan tab, framed by TRUE access age:
  ONE row per institution — Chase/chase unified case-insensitively — with
  Available now / Unlocks at 59½ (date from the Settings date of birth) /
  Total; Cash + Taxable + HSA count as Available now, Traditional + Roth
  IRA unlock at 59½; rows sum and expand to accounts; footer has liquid
  total, home, net worth, and years of pre-65 spending covered by
  available-now money; 65 appears nowhere on this tab — it stays a
  spending/SS milestone on Overview only),
  **Tax implications** (per-type tax facts, not advice, + your
  account→type mapping).
  Every view that lists money shows a total: Holdings and Diversification
  bucket tables carry TOTAL rows tying to net worth, the Tax Harvest losers
  table totals Value $ / Unrealized P&L $ (unknown columns read `--`, never
  a partial sum), and Liquidity shows its totals as a table row instead of
  note text (the note keeps only home, net worth, and years-of-spending).
- **Empty state** — with ZERO positions, Overview shows no numbers, no
  chart, no alerts: only "No data yet — add your first bank / account, or
  upload a filled template" with those two actions as buttons. A fresh copy
  ships blank defaults (no personal values in the code) — fill in
  Settings (☰ menu, including Properties for the home address) and pull
  the home estimate via ☰ → Refresh home estimates.
- **Diversification** — the 15:15:35:15:20 standard + rationale, current
  position vs standard, the Target-vs-actual allocation bar chart (this tab
  only), rebalance plan (display only — NEVER executes trades), and the
  same Actual-vs-Standard drift line chart as Overview (one shared
  implementation — values tie exactly; Y-axis $2M–$5M, $100K steps — the
  chart Google Sheets flattened).
- **Tax Harvest** (view title "Tax Loss Harvesting") — per-lot unrealized
  P&L with Long/Short holding term, realized gains from closed lots, and a
  user-set annual net-gains cap (blank = no cap enforced) with leeway math;
  the cap and its note live in Settings.
- **Data Entry** (last) — sub-tabs Inputs / Template /
  Danger Zone (see below). Profile moved to Settings under the ☰ menu
  (Refresh stocks, Refresh home estimates, Log, Settings).

Deferred: an Overview news feed (earnings, Fed meetings) waits for the
AI-embedding phase — raw feeds are noisy and curation is the value. No
placeholder UI. (The Overview bottom area is separately reserved for the
future upcoming-events calendar for portfolio holdings.)

## Copying out of the app (Ctrl+C, tables, AI)

- Click any text, then press **Ctrl+C** — entries keep native selection
  copy; readout labels copy their text (the click focuses the label even
  when it lands on a wrapper); anything inside a table copies the
  whole table. The top bar confirms each copy.
- Every dialog, popup, and status message is mouse-selectable too — drag
  to select, Ctrl+C to copy: Refresh results, confirmations, Settings and
  Template messages, watchlist messages, Inputs progress/warnings, the
  status bar. No message in the app is copy-proof (native file dialogs
  aside).
- Overview has a **Copy summary** button (net worth, spending, alerts).
  Holdings, Liquidity, and the Inputs grid each have a **Copy table** /
  **Copy grid** button: TSV to the clipboard, pasting straight into Excel,
  Sheets, or any AI chat.
- Instruction blocks (Inputs guide, Template guide, Diversification
  standard) and the key readout notes are real selectable text: drag to
  select, Ctrl+C to copy.
- Counts use plain plurals ("1 row", "11 positions") — no "(s)" anywhere.

## Readability (older eyes, split screen)

- Type scale lives in one place (`FS_BODY` / `FS_HEAD` / `FS_TITLE` /
  `FS_TABLE_HEAD` in `portfolio_app.py`): body 16px everywhere, headings
  20px, headline numbers 24px, bold table headers 16px. Every widget
  without an explicit font inherits body size from the theme default, so
  buttons and entries are legible with no per-widget edits. (CTk sizes are
  pixels but tkinter renders points — the values are chosen to land
  exactly; don't pick odd sizes.)
- Dark theme kept; body text is always light, secondary rows use a readable
  light grey (`CLR_SECONDARY`) — never tiny + dim. Tables use generous row
  padding; charts are dark-dressed with scaled-up titles/labels/legends.
  The drift chart labels every $500K with $100K minor gridlines (31 labels
  crowded the edge and stole a third of the plot).
- Split-screen safe: every tab is verified at 960px window width — no
  clipped text, no unreachable buttons, no horizontal overflow. Every
  edit-triggered rebuild preserves scroll position (snapshot fractions,
  rebuild, restore on the new widgets) — no view jumps back to the top
  after an add, remove, delete, or edit. Charts
  track the container width and shrink to fit; Overview and
  Diversification scroll vertically as one region each, so tall figures
  are never cropped by a short window (that clipping once ate x-labels,
  legends, and whole bar groups). Long labels wrap at 860px; crowded
  button rows consolidate secondary actions into a More ▾ menu instead of
  scrolling or stacking. One scroll region per view: tables render at
  full height inside the view's single scrollable — no nested scrollbars
  (they fought over mouse-wheel events). Both charts use the constrained
  layout engine (solved on every draw at the figure's real size) — never a
  manual tight_layout pass, and the first layout waits for a real canvas
  size instead of a transient near-zero startup width (each warned on cold
  start before this — first the tight-layout warning, then the
  constrained-collapse warning).
- Money/percent style (shared formatters, every view inherits): exactly
  zero renders as a bare `-` (known-and-zero — `$0` / `0.0%` never appear);
  negatives render red and in parentheses with the $ inside — `($5,000)`,
  `(2.3%)` — never a minus sign; `--` still means unknown / not computable
  (gains without cost, % of a $0 total) and `upload` still prompts for
  cost awaiting entry — never collapse `--` into `-` or vice versa.
  Positive values, thousands separators, and share quantities are
  unchanged.

## Data model — one row per lot

All positions live in **`portfolio.csv`** (gitignored, never pushed):

```
bank,account,account_type,asset,shares,cost_per_share,acquired_date,sold_date,sale_price_per_share
```

- **Open lot:** `sold_date` and `sale_price_per_share` blank. **Closed lot:**
  both filled. Status is DERIVED from the dates — there is no status column.
- **Partial sale = two rows** (closed sold quantity + open remainder); the
  Sold action splits automatically, never by hand.
- **Lot key = account + asset + acquired_date + cost_per_share.** Uploads
  upsert on that key (match → update, no match → insert) and NEVER delete
  rows. Two open rows sharing a key are rejected as duplicates. New dated
  lots draw down the dateless (unattributed) balance for that asset,
  keeping a residual row; dated shares beyond the balance are rejected —
  nothing is ever silently dropped or double-counted. Correct a lot's date
  in the grid (net-change, no false draw); uploads only add or update.
- **Upload transparency** — every upload/paste/import reports "N rows: X
  updated (already existed), Y inserted (new)", so a duplicate upload reads
  e.g. "31 rows: 31 updated, 0 inserted" and the dedup is visible instead
  of wondered-about. Uploads need NOT be complete — they merge. Complete
  replacement = delete all data first (Danger Zone), then upload.
- `account_type`: `Traditional IRA`, `Roth IRA`, `Taxable`, `HSA`, `Cash`.
  Cash rows (`CASH_USD`, savings) need no cost or dates.
- **Share edits are count CORRECTIONS, not sales** — no tax event. A sale
  always records date and price.
- Settings live in **`profile.json`** (gitignored): date of birth, monthly
  Social Security (owner + spouse), other realized gains this year + source
  note, spending base figures, the remembered backup folder, and the last
  backup stamp, the annual net-gains cap + note, and user-defined
  watchlist classes. A fresh copy ships NEUTRAL blanks — no personal values
  are seeded in the code; the user fills these in Settings (☰ menu).

## Data Entry (last tab)

Sub-tabs Inputs / Template / Danger Zone — the tab bar is the
only navigation (the ☰ menu opens no window).

- **Inputs** — OPENS on the guided one-account view by default (first
  account with required gaps, taxable first; the guided panel's "Show all"
  leaves for the full grid, "Guided" returns; completion state when all
  required accounts are fed — one
  account bounds the widget count, which keeps scrolling fast; the guided
  picker follows lots holding positions needing cost/dates, never
  account names without lots). Bank →
  Account → lot grid with an overall progress line. Taxable = REQUIRED,
  IRA/Roth/HSA = OPTIONAL, Cash = complete. No Bank/Account grid columns
  (shown in the section header); unlocked rows stay single-line — a per-row
  **↗ Move** button expands ONLY that row's bank/account line (collapses on
  Lock/Save; never duplicates). Cash rows (`CASH_USD`, Cash-type accounts)
  render as a single **Amount ($)** field — no shares/cost/date prompts,
  never flagged invalid, no Sold/Mark-closed (stored as shares=amount,
  cost=1).
  Closed lots listed per account, per-account type dropdown, per-account
  **Download template**, per-account live value (check vs broker),
  **+ Add row** inheriting the section, **+ Add account** (existing bank
  from dropdown or new bank as free text; first lot OPTIONAL — bank + name
  + type alone stages an empty shell that registers on Save; doubles as the
  empty-state "Add your first bank / account" prompt, landing on Inputs
  with the staged account visible). Rows are locked by default; Edit
  unlocks to a white row with dark text (dirty marker if relocked with
  unsaved edits). Typing stages only — Tab/Enter/arrows move, Save
  validates and commits with one recompute ("Save (N unsaved change(s))",
  plain "Save" at 0); **Discard changes** sits immediately right of Save,
  stays greyed out at 0 staged changes, and confirms before discarding
  ("Saved data is not affected"). An empty shell row reads "register
  the account on Save"; shares-present-but-costless rows hint "need cost". Dates are
  typeable (YYYY-MM-DD) with a picker button; the picker header reads
  "< November 2026 >" (arrows flank at top), year/month labels open
  one-action pickers, and the popup anchors by the field without covering
  the edited row. Bad cells get a red outline, duplicates a warning, each
  row shows live cost/proceeds/gain/term arithmetic. Typing fewer shares is
  a count correction, never a sale. Edit/Lock/Save update rows in place
  (scroll preserved; only Add scrolls). Mouse wheel scrolls 5 units/notch
  app-wide, over entries and buttons too — as fast as scrollbar drag. Grid
  columns budget to 798px so the full grid fits a 960px split-screen window
  with no horizontal overflow; long gain strings wrap instead of clipping.
- **Template** — row reads **Download Template | Download Data |
  Upload | Backup | More ▾**. **Download Template** (header only),
  **Download Data** (your current data, filled into the template — a plain
  CSV for uploading into another copy of the app; defaults to your
  Downloads folder as `filled-template-YYYYMMDD-HHMM.csv`, never the repo
  folder; exports the last saved state, so unsaved Inputs edits ask Save &
  Download / Download saved state / Cancel), **Upload** (reports "N rows:
  X updated, Y inserted"), **Backup** (one-click backup into your
  remembered backup folder — timestamped `filled-template-*.csv` files
  accumulate; a synced Drive/OneDrive/Dropbox folder carries them to other
  machines, no cloud integration — plus a last-backup stamp and a
  Change-backup-folder button), and a **More ▾** menu holding the secondary
  actions **Paste rows** (clipboard TSV/CSV) and **Copy AI prompt**
  (ready-made screenshot-to-CSV prompt for any AI) — no Import broker CSV:
  it duplicated Upload (both accepted only template-shaped files), so it was
  deleted and the template is the one way in. Download = save-dialog each
  time, anywhere; backup = remembered folder + one click + stamp. The tab
  also carries a per-field broker guide (Schwab + Vanguard paths,
  CSV-export pointers, 1099-B note) plus a "Which broker export to start
  from" block with the exact Schwab (Positions → Cost Basis $ / Lot Details
  → export) and Vanguard (Cost basis → Unrealized/Realized → Show lot
  details → Export, top-right) steps, the template-only rule, the
  combine-ALL-accounts-into-one-file encouragement, and the standing
  caveats (Vanguard IRA blank cost is expected; 1099-B is the authority).
- **True-up test** — verify a fresh copy of the app reproduces your data:
  Save, then Template → Download Data (note open/closed counts,
  per-account values, liquid total, net worth). Fresh clone (no data files
  carried over) → install → run → confirm the empty state → upload the
  file via Upload. Press Refresh stocks in BOTH apps back-to-back, apply
  the same home value in the clone (Settings → Properties, or ☰ → Refresh
  home estimates), then compare: lots/shares/cost/counts must match exactly,
  liquid total and net worth must match. The template carries positions,
  not prices (the clone fetches its own) and not home value (set it
  identically in the clone).
- **Settings** (☰ menu dialog, formerly the Profile sub-tab) — date of
  birth, SS amounts, allowed spending $/yr before 65 and after-65 base
  (enterable here — Overview, Liquidity and the live summary all update
  from them), other gains + note, optional home purchase price,
  annual net-gains cap $/yr (blank = no cap enforced) + cap reason/note,
  RentCast API key (free Developer tier, pasted in by the user — an
  address-like value is refused, keys have no spaces or commas) and the
  Properties list (one address row present by default; blank-address rows
  never save; address + applied value + last estimate/source/date per
  property, Add/Remove; Redfin and Zillow enter through the manual applied
  value — check in the browser, type the number; no scrapers; the no-key
  Refresh popup offers an Open Settings button)
  (all blank by default — the user fills them in). Shows live spending
  capacity: before-65 $/yr, after-65 base + SS = all-in $/yr. Save/Cancel
  live in a fixed footer that never scrolls away; the dialog never exceeds
  the viewport height; **Export settings** / **Import settings** in the
  footer move the whole settings file (`settings-YYYYMMDD-HHMM.json`,
  profile.json format) to a clone — Import confirms first, validates the
  file, and applies nothing on error; lots and drift log are never
  touched.
- **Danger Zone** — red-styled data-management tab. Delete all data (with
  a backup-first warning, an inline Download Data button, and a
  type-DELETE confirmation) wipes portfolio.csv, profile.json (settings,
  cap, watchlist classes, RentCast key, properties), drift_log.csv,
  prices_cache.json, and accounts.json, returning the app to
  the fresh-install empty state; re-uploading restores the numbers. Needed
  because uploads upsert, never replace — delete-then-upload is the only
  clean dataset replacement.
- **Feed one account** — the default Inputs view (see above): one taxable
  account at a time with its broker guidance and a "N required positions to
  go" countdown, then the next incomplete account. The full grid stays
  available via the guided panel's "Show all" (the single path — the header
  row carries no duplicate).

## Position lifecycle (Accounts tab buttons + Coverage grid)

Record-keeping language throughout: this app places no orders and connects
to no brokerage — every action records something that already happened at
the brokerage.

- **Add position** — bank, account (existing or new + type), asset, shares,
  optional cost + acquired date.
- **Sold / Reduce** — records a sale: FIFO by default (oldest lots first,
  dateless last, one closed row per lot consumed), specific-lot override
  available.
- **Mark closed** — records a full sale; the row leaves holdings, enters
  realized gains. **Reopen** clears the sold fields (also possible inline).
- **Delete lot** — per-row, with confirmation; the only way rows disappear
  (uploads never delete).
- Recording a sale without a cost on file records the gain as **unknown** —
  the app never invents basis.

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

- **Record buys/sells**: use the Accounts tab buttons (Add / Sold / Mark
  closed), edit the Inputs grid, or fill a template and upload it. Then
  ☰ → Refresh stocks.
- **Home value**: Settings → Properties (address + applied value per
  property; the applied value flows into Holdings, net worth and drift;
  Holdings shows one row per property). ☰ → Refresh home estimates pulls
  the RentCast estimate per property (free Developer key in Settings) and
  SHOWS value + source + date — accepting or typing a value and saving is
  what applies it; nothing is silently replaced. No key: Refresh shows a
  plain hint. Redfin/Zillow enter via the manual applied value (no
  scrapers). RentCast is called ONLY on explicit Refresh — 50 calls/month
  free tier; remaining quota shows when the API reports it. A stored key
  that looks like an address (typed into the wrong field before validation
  existed — the usual cause of a 401) is healed on load: moved to
  Properties as the home address when none exists, else cleared, with a
  status note; the fetcher itself never burns a call on an address-like
  key.
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
- **Data files** (all gitignored, never committed): `portfolio.csv`
  (lots), `profile.json` (settings + cap + user watchlist classes +
  RentCast key + properties),
  `accounts.json` (account registry — accounts exist independent of lots),
  `drift_log.csv`, `prices_cache.json` (prices + cached watchlist quotes),
  backups, downloaded CSVs and settings exports. Delete-all wipes all five
  store files (the custom watchlist classes clear with the profile; the
  standard classes are fixed content in code and reappear regardless).

## Maintaining with Muse Code (Windows)

This is plain Python — open the folder in VS Code with Muse Code and ask
it to change views, add a tab, or adjust the standard. The logic lives in
`portfolio_calc.py` (no GUI code, testable headless); the window lives in
`portfolio_app.py` (CustomTkinter + embedded matplotlib).

## Safety

- NEVER executes trades. NEVER writes to Google Sheets. NEVER sends
  anything outward. NEVER asks for passwords.
