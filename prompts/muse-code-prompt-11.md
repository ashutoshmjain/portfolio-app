# Prompt 11 — Type scale down (headline 18, body 12) + header title "Portfolio" + Watchlist columns (Week / Month / Quarter / PEG) + Overview value cards + Holdings cash row + Copy-table buttons right

Status: BUILT (commit 003b580, 2026-11-18)

## Context

The user reviewed the Overview summary after Prompt 10 and called the
sizes down. He named two numbers and one text change, and declined the
bullets fix (the bullets stay as they are — see Item 4).

The type scale lives in one place, `portfolio_app.py` lines 60–64:

- `FS_BODY = 14` — body text, everywhere (also the theme default:
  `ctk.ThemeManager.theme["CTkFont"]["size"] = FS_BODY`, so every widget
  without an explicit font inherits it).
- `FS_HEAD = 18` — section headings (body + 4).
- `FS_TITLE = 22` — top headline numbers.
- `FS_TABLE_HEAD = 14` — bold table headers (tracks body).
- `FS_SMALL = 11` — secondary hints only, never body text.

The header bar title (top left) currently reads "PORTFOLIO DASHBOARD"
(`portfolio_app.py` line 426, a `SelectableMsg` with
`font=ctk.CTkFont(size=FS_HEAD, weight="bold")`).

## Items

1. **Headline 18, across the app.** `FS_TITLE` 22 → 18. The only
   `FS_TITLE` usage is the Overview "Total net worth" line
   (`portfolio_app.py` line 1597), so this is the headline the user
   named. Change the constant, not the call site. The comment on the
   constant updates to the new value.

2. **Body 12, across the app.** `FS_BODY` 14 → 12. This is the theme
   default, so it flows to every widget without an explicit font, and to
   every explicit `CTkFont(size=FS_BODY)` call site. Change the
   constant, not the call sites. The comment on the constant updates to
   the new value.

3. **Section headings follow the rule: `FS_HEAD` 18 → 16.** The user
   named only the headline and the body, but `FS_HEAD` (18) would equal
   the new headline (18) if left alone, and the headline must stay the
   largest. The guide's rule is head = body + 4, so 12 + 4 = 16. Change
   the constant; the comment updates to "section headings (body + 4)".
   This flows to every `FS_HEAD` call site (the header bar title, the
   Watchlist / Accounts / Diversification / Data Entry / Danger Zone /
   Settings headings) — no call-site edits.

4. **The bullets are NOT changed.** The user declined the fix from the
   Prompt 10 follow-up: the Overview bullets keep the `SelectableMsg`
   default font (no `font=` passed), which is `("Roboto", -FS_BODY)` —
   the same number in pixels. When `FS_BODY` becomes 12 the bullets
   read 12px, still smaller than the 12pt body text (≈16px). Do NOT add
   an explicit font to the bullet widget. This is deliberate: the user
   said the bullets "are fine".

5. **Table headers track the body: `FS_TABLE_HEAD` 14 → 12.** They
   were equal to `FS_BODY` before and stay equal. Change the constant;
   the comment updates. The single usage (the table-header font) needs
   no call-site edit.

6. **`FS_SMALL` stays 11.** The user did not name it and it is already
   the smallest size in the scale. Do not change it. (It will read only
   1px below the new body — that is accepted, not a defect to fix.)

7. **Header title text: "PORTFOLIO DASHBOARD" → "Portfolio".**
   (`portfolio_app.py` line 426.) Exact new text is `Portfolio`
   (title case, not all caps). Only the text changes — the widget, the
   `FS_HEAD` bold font, and the packing stay exactly as they are. (Its
   size therefore follows Item 3: 16px bold.)

8. **The style guide and the README follow the new scale.** Update
   `prompts/app-style-guide.md` §1 (the type-scale table and the note
   under it) to: `FS_BODY` 12, `FS_HEAD` 16, `FS_TITLE` 18,
   `FS_TABLE_HEAD` 12 bold, `FS_SMALL` 11. Update the note to record
   that the scale changed again on 2026-11-18 by the user's call
   (headline 18, body 12) and that the steps are now head = body + 4,
   title = body + 6. Update the README type-scale line ("body 14px
   everywhere, headings 18px, headline numbers 22px, bold table
   headers 14px") to the new numbers. Do not duplicate the guide's
   rules anywhere else.

## Watchlist columns (context)

The Watchlist is the Overview table built by `build_watchlist`
(`portfolio_app.py` line 1745). It has one Table per class — the
built-ins Octonions (AAPL, MSFT, NVDA, AMZN, META, GOOGL, TSLA, SPCX),
Bitcoin (BTC, MSTR, IBIT, ARKB), Gold (GLD) — plus any user-defined
class — and every class goes through the same row builder
(`_watch_row`, line 1721) and the same row layout
(`_watch_ticker_row`, line 1815). Today the Table has exactly three
columns: `["Ticker", "Price", "Market cap ($T)"]`, and `_watch_row`
returns three values `[ticker, money(price), mcap_text]`.

The data comes from `fetch_watchlist` in `portfolio_calc.py` (line
~545). Per ticker it already pulls `fast_info` (price, market cap),
falls back to `history(period="5d")` for the price, and calls
`tk.info` for the market-cap fallback (`totalAssets` / `netAssets`)
on funds. The quotes dict is `{"price": ..., "mcap": ...}` per ticker,
and a failed refresh falls back to the cached quote (never a crash,
never a blank where a cached value exists). BTC's market cap is
COMPUTED from mined supply × price, never "--" when priced.

9. **Watchlist: Week / Month / Quarter price columns.** The Table
   headers become seven columns, in this order:
   `["Ticker", "Price", "Week", "Month", "Quarter", "Market cap ($T)",
   "PEG"]`. The three new columns are PRICES (dollar amounts), not
   percent changes — the stock's price as of that date back:
   - **Week** — the close on the last trading day on or before
     (today − 7 calendar days).
   - **Month** — the close on the last trading day on or before
     (today − 1 calendar month).
   - **Quarter** — the close on the last trading day on or before
     (today − 3 calendar months).
   Format each with `money()`, exactly like the Price column. A
   missing value (no history that far back, or a failed fetch with
   nothing cached) shows "-" (bare dash, per the financial-formatting
   rule).
   Source: in the same per-ticker fetch in `fetch_watchlist`, pull ONE
   `history(period="3mo")` per ticker and pick the close on or before
   each of the three target dates from that single pull — do not make
   three separate history calls per ticker. Extend the quote dict and
   the watchlist cache to carry `week`, `month`, `quarter`, with the
   same fallback as price/mcap (a failed refresh keeps the cached
   value). `_watch_row` returns seven values; `_watch_ticker_row`
   lays out seven columns plus the Remove button; `_copy_watch_class`
   TSV headers become the seven names. This applies to EVERY
   watchlist class (Octonions, Bitcoin, Gold, and user-defined
   classes) — they all go through the same row builder. Split-screen:
   seven columns plus Remove must fit in ~960px with no horizontal
   scrollbar — size the columns to fit (the historical prices are
   prices, so they take the Price column's width or narrower; PEG is a
   short number).

10. **Watchlist: PEG column.** The PEG column shows the yfinance
    `pegRatio` (5-year expected PEG) from the same `tk.info` already
    fetched in `fetch_watchlist` for the market-cap fallback — no new
    data source, no new fetch. Format to 2 decimals (e.g. "1.28").
    Where yfinance has no PEG (BTC, GLD, IBIT, ARKB, and any stock
    without one, e.g. a recent IPO), show "-" (bare dash). Extend the
    quote dict and the watchlist cache to carry `peg`, with the same
    fallback as price/mcap. Note: this is Yahoo's 5-year expected PEG,
    which may differ from the weekly scan's MarketBeat forward PEG
    shown in the PEG Ratios Space. The scan's exact numbers would need
    the scan to publish a machine-readable file the app can read, and
    no such file exists today — that is a separate piece of work, not
    this item. If the user wants the scan's numbers he will say so.

## Overview value cards (context)

The Overview summary ends in a vertical list of bullets — the
`alerts` list (`portfolio_app.py` lines ~1655–1690), rendered by a
loop as `SelectableMsg` lines, followed by a "Copy summary" button
(line ~1696). The alerts, in display order, are: Drift, Medi-Cal
verdict (inserted second, ONLY when the plugin is activated),
Gains headroom, After-65 AGI guardrail, and REQUIRED positions
("N REQUIRED positions still missing cost or dates — feed them in
Data Entry", or "All REQUIRED positions have cost and dates").
The user wants the landing page to look like a real dashboard, so
the four metric bullets become value cards in the layout of the
CustomTkinter climate-app tutorial's "Value cards"
(https://customtkinter.tomschimansky.com/tutorial/climate-app#value-cards):
exactly four boxes in a single horizontal row of equal-width columns
(not a 2×2 grid), below the header and above the chart. Each card is
a plain `CTkFrame` with three stacked left-aligned labels and no
icon: a small gray title, a large bold value, a small gray detail.
The tutorial builds them with one shared helper, a transparent
wrapper gridded with four columns (`weight=1, uniform="cards"` for
equal widths), a 20px gap between cards and no gap after the 4th,
and 20px of space below the row.

11. **Overview: the four metric bullets become value cards.** Build
    the cards with one shared helper, following the tutorial's
    structure: a transparent `cards` wrapper, gridded with four
    columns (`weight=1, uniform="cards"`), 20px of space below the
    row. Each card is a plain `CTkFrame` (theme default frame color),
    20px gap between cards, no gap after the 4th. Inside each card,
    three stacked labels, all left-aligned (`sticky="w"`), no icon:
    - Row 0 — title: `FS_SMALL`, muted color (`CLR_SECONDARY`),
      padx=15, pady=(10, 0).
    - Row 1 — value: `FS_TITLE` bold, default text color, padx=15.
    - Row 2 — detail: `FS_SMALL`, muted color (`CLR_SECONDARY`),
      padx=15, pady=(0, 8).
    The three labels are `CTkLabel` (not `SelectableMsg`) — deliberate,
    matching the tutorial. The card text is short and single-line by
    design, so the centered-wrapped-lines defect does not apply.
    Trade-off, stated: the card figures are view-only (not
    selectable); the main summary lines (Total net worth, Allowed
    spending, Realizable) stay `SelectableMsg` and copyable. Add
    value-card labels to the style guide §3 `CTkLabel` keep-list.
    The four cards, in display order, with their exact title / value /
    detail:
    1. **Drift** — title "Drift (year to date)", value = the drift in
       points (`drift_pp_text`, e.g. "5.7pp", parenthesized when
       negative), detail "actual 9.3% vs standard 3.6%".
    2. **Medi-Cal** — title "Medi-Cal", value "Qualified" or "Not
       qualified", detail "MAGI $24,250 vs $25,000 ceiling". This
       card appears ONLY when the plugin is activated (same gating
       as the bullet today). When inactive, the row shows the
       remaining cards spread across the width (the uniform grid
       adapts; do not leave an empty slot). Derive the verdict word
       and the MAGI figures from the same projection the bullet
       used; add a small plugin accessor if parsing the verdict
       sentence is fragile.
    3. **Gains headroom** — title "Gains headroom", value = the
       headroom amount (e.g. "$1,531"), detail "of the $4,750 cap
       (projected)". When headroom is None (no ceiling set), value
       "—" and detail "no ceiling set".
    4. **After-65 AGI guardrail** — title "After-65 AGI guardrail",
       value "OVER by $55,316" (or "UNDER by $X"), detail
       "$118,316 vs $63,000 threshold". When no threshold is set,
       value "—" and detail "no threshold set".
    The REQUIRED positions alert does NOT become a card and does NOT
    stay on the Overview at all. It moves to the top of the Holdings
    tab (Item 13). Placement: the cards sit where the bullets were —
    below the "Realizable" line and above the chart. The chart and the
    Watchlist below are unchanged. The `alerts` data is still built
    the same way (Medi-Cal inserted second only when activated); the
    bullet-rendering loop is replaced by the card builder, and the
    REQUIRED alert is rendered on the Holdings tab instead.
    Split-screen: at ~960px the cards must fit in one row with no
    horizontal scrollbar and no wrapping. Keep the title / value /
    detail short enough to fit on one line at the narrowest card
    width (the strings above are sized to fit); do not let them wrap
    (a wrapped `CTkLabel` centers its continuation line). If a
    value/detail would wrap at 960px, shorten it rather than wrapping.

12. **Remove the "Copy summary" button.** Remove the
    `CTkButton(body, text="Copy summary", ...)` (line ~1696) AND the
    `summary` string construction (line ~1688) — the string is only
    used by that button, so it becomes dead code. Do not leave it.
    The main summary lines stay `SelectableMsg`, so the summary is
    still copyable per line (drag to select, Ctrl+C). Update the
    style guide §6 (copy rule): note that the Overview summary's
    one-click "Copy summary" button was removed 2026-11-18 by the
    user's call for elegance, and the summary's copy path is now the
    selectable text.

## Holdings tab (context)

The Holdings tab (`build_holdings`, `portfolio_app.py` line ~2045)
aggregates open lots by asset via `pc.holdings_by_asset`
(`portfolio_calc.py` line 1630), which returns rows sorted by value
descending plus a total. Today `holdings_by_asset` SKIPS cash
(line 1644: `if lot.get("asset") == CASH_ASSET: continue`) and its
docstring says "CASH_USD excluded — cash lives in Liquidity". The
Totals row is labeled "TOTAL (positions + home; cash excluded)"
(`portfolio_app.py` line 2091; the same label in the Copy-table TSV,
line 2140), and the comment above it (line 2080) says cash "lives in
Accounts / Liquidity, never in Holdings". Each row has a ▶/▼
expander when it has per-account lots (`_hold_row`, line 2149), and
the detail (`_hold_fill_detail`, line 2184) shows per-account
aggregates. Cash is priced at $1.00 wherever a price is needed
(`portfolio_calc.py` lines 1570, 1604). The REQUIRED count
(`_required_missing`, line 1472) already excludes `CASH_ASSET` —
cash never counts as a position missing cost.

13. **The REQUIRED line moves to the top of the Holdings tab, in
    Body style.** The "N REQUIRED positions still missing cost or
    dates — feed them in Data Entry." line (or "All REQUIRED
    positions have cost and dates." when none are missing) no longer
    appears on the Overview at all — it moves to the very top of the
    Holdings tab, above the positions table. Render it as a
    `SelectableMsg` with `font=ctk.CTkFont(size=FS_BODY)`, packed
    full-width with `fill="x"` (the Body style — the same size and
    treatment as the "Allowed spending" / "Realizable" lines on the
    Overview). The text and the logic are unchanged (it still uses
    `_required_missing()`; it still shows the "All..." text when
    nothing is missing). It is the same line, in a new home — because
    Holdings is where the missing cost is visible (the Cost column
    reads "upload" there).

14. **Cash is a row like any other ticker, and the Total drops its
    qualifier.** Remove the cash skip in `holdings_by_asset`
    (`portfolio_calc.py` line 1644) so `CASH_USD` aggregates into a
    row like any other asset, and update that function's docstring
    (drop "CASH_USD excluded — cash lives in Liquidity") and the
    Totals-row comment (`portfolio_app.py` line 2080). The cash row:
    - Appears in the table sorted by value descending with the other
      rows (its value is the total cash; priced at $1.00, as the
      code already does).
    - Cost shows "—" (cash has no cost basis to enter) and Gain
      shows "—" (cash has no gain). The cash row is always complete
      — it never counts as a position missing cost, and it never
      shows "upload".
    - Has the ▶ expander like any other row. Its dropdown groups the
      cash by INSTITUTION (summing the cash accounts at each
      institution — Wells, Chase, Schwab, ...) rather than by
      account, because the user asked for the institution-wise
      breakup.
    The Totals row label becomes simply "TOTAL" — in the table (line
    2091) AND in the Copy-table TSV (line 2140). No parenthetical
    qualifier: the total now includes everything (positions + cash +
    home), so it needs no explanation. Consistency check: the
    Holdings TOTAL should now equal the Overview Total net worth.

15. **"Copy table" buttons sit on the right edge of the table,
    across the app.** There are three "Copy table" buttons. The
    Table class's own button (`portfolio_app.py` line 343, in
    `Table.__init__`) is already right-aligned — its toolbar frame
    is `sticky="e"` and the button packs `side="right"` — no change;
    verify it stays. The Holdings button (`build_holdings`, line
    2110) and the Liquidity button (`build_liquidity`, line 2313)
    are packed with `anchor="w"` (left-aligned) — change both to
    `anchor="e"` (right-aligned to their table's right edge). Keep
    each button's vertical position (Holdings stays below the table,
    Liquidity stays above the table); only the horizontal alignment
    changes. Do not move either button to the other end of its tab.
    This is a style rule, not a one-off: add it to the style guide
    §6 (copy rule) — "'Copy table' buttons sit on the right edge of
    their table (right-aligned), across the app." — so any future
    "Copy table" button follows the same rule.

## Guardrails

- Build only these fifteen items. No figure, computation, tab, control,
  or layout change. No widget conversion beyond Item 7's text change
  and Item 11's bullet-to-card conversion.
- Change the constants, not the call sites. Do not introduce a new
  hardcoded size anywhere. After the change, no `CTkFont(size=` literal
  (a bare number) may remain anywhere in `portfolio_app.py` or
  `plugins/medical.py` — every size must come from a named constant.
- The bullets (Item 4) are explicitly out of scope for a font fix.
  Do not "helpfully" add a font to them.
- Do not change the header title's widget, font, or packing — text
  only.

## Verification

- The committed test suite passes in full. (It has no font-size test
  yet — see below.)
- Add committed tests for: (a) the type scale reads FS_BODY 12,
  FS_HEAD 16, FS_TITLE 18, FS_TABLE_HEAD 12, FS_SMALL 11; (b) no
  `CTkFont(size=` numeric literal remains in `portfolio_app.py` or
  `plugins/medical.py`; (c) the header title reads exactly "Portfolio";
  (d) the Watchlist headers are the seven names in order (Ticker,
  Price, Week, Month, Quarter, Market cap ($T), PEG); (e) `_watch_row`
  returns seven values and the quote dict carries `week`, `month`,
  `quarter`, `peg`; (f) the historical-price picker returns the close
  on or before each target date from a single 3-month history;
  (g) the Overview builds the four value cards (Drift, Medi-Cal when
  active, Gains headroom, AGI guardrail) with title / value / detail;
  (h) the Medi-Cal card is absent when the plugin is not activated;
  (i) the Overview shows no REQUIRED line at all (it moved to
  Holdings); (j) no "Copy summary" button exists in the Overview;
  (k) the REQUIRED line appears at the top of the Holdings tab in Body
  style; (l) `holdings_by_asset` includes a CASH_USD row (Cost "—",
  Gain "—", always complete) sorted by value with the rest, its
  expander grouping by institution, and the Totals label reads exactly
  "TOTAL" in the table and in the Copy-table TSV; (m) every "Copy
  table" button is right-aligned to its table's right edge (the
  Holdings and Liquidity buttons use `anchor="e"`; the Table class's
  button stays `sticky="e"` / `side="right"`).
  (Prompt 10's verification asked for new tests and they were not added
  — the suite stayed at 46. Add these ones.)
- Headless probe: build the Overview and confirm the "Total net worth"
  line renders at the headline size and the "Allowed spending" /
  "Realizable" lines at the body size; confirm the header bar reads
  "Portfolio"; build the Watchlist and confirm seven columns render
  with the Week / Month / Quarter cells showing prices and the PEG
  cell showing a 2-decimal number or "-"; confirm the Overview shows
  four value cards in a row with title / value / detail, no REQUIRED
  line, and no "Copy summary" button; build the Holdings tab and
  confirm the REQUIRED line sits at the top in Body style, a CASH_USD
  row appears among the positions, and the Totals label reads "TOTAL";
  confirm the Holdings and Liquidity "Copy table" buttons are
  right-aligned and the Table class's button is right-aligned.
- Manual GUI check is the owner's step: Overview at full width and at
  ~960px split-screen — the headline, the body sentences, and the
  bullets must all still read cleanly with no clipping, the header
  bar must read "Portfolio", the Watchlist must show all seven
  columns with no horizontal scrollbar, and the four value cards must
  sit in one row with equal widths, title / value / detail
  left-aligned, no wrapping, no horizontal scrollbar, and no "Copy
  summary" button; Holdings tab — the REQUIRED line at the top, the
  CASH_USD row among the positions with its ▶ expander showing the
  institution-wise breakup, and the Totals label reading simply
  "TOTAL"; Liquidity and Holdings tabs — the "Copy table" button on
  the right edge of the table.

## Run line

Pull the latest portfolio-app, then execute
`prompts/muse-code-prompt-11.md` — read
`prompts/app-style-guide.md` first, build the fifteen items, and report
per item.

## Build report (2026-11-18, commit 003b580)

Per-item outcome. Committed suite 68/68 OK (46 pre-existing +
22 new in `tests/test_prompt11.py`, checks (a)-(m)). Headless probe
23/23 ALL PASS in a withdrawn root (no mainloop): header reads
"Portfolio"; headline renders 18, body lines 12; four cards in one row
with title / value / detail, no REQUIRED line, no Copy summary button;
standard tables carry the seven headers with Week prices + 2-decimal PEG;
REQUIRED line tops Holdings in Body style with fill=x; CASH_USD row and
plain TOTAL present; both Copy-table buttons anchor=e. Manual GUI check
(full + 960px split-screen) is the owner's step.

1. FS_TITLE 22 -> 18 (constant + comment). Only usage is the Overview
   headline; probe confirms it renders 18.
2. FS_BODY 14 -> 12 (constant + comment; theme default flows everywhere).
   Probe confirms Allowed spending / Realizable render 12.
3. FS_HEAD 18 -> 16 (constant + comment "section headings (body + 4)");
   headline stays largest. Header title, Watchlist, and section headings
   follow with no call-site edits.
4. Bullets not refonted: the declined fix is honored. (The bullet loop
   itself is gone, replaced by the Item 11 cards; no font was added to
   any remaining default-font note.)
5. FS_TABLE_HEAD 14 -> 12 (constant + comment; tracks body).
6. FS_SMALL stays 11 (untouched).
7. Header title reads exactly "Portfolio" (text-only change; widget,
   FS_HEAD bold font, and packing untouched; probe confirms).
8. Style guide section 1 table + note follow the new scale (12 / 16 /
   18 / 12 / 11; steps head = body + 4, title = body + 6, dated
   2026-11-18); README type-scale line reads the new numbers. No rule
   duplicated elsewhere.
9. Watchlist Week / Month / Quarter: one `history(period="3mo")` per
   ticker; `pick_backdate_closes` picks the close on or before each
   target (7d / 1mo / 3mo, calendar months, day-clamped) from that pull
   (price fallback is the same pull's last close — no 5d call, no three
   calls). `money()`-formatted like Price; missing shows "-". Quote
   dict + cache carry week/month/quarter with the price/mcap fallback
   (fresh miss keeps cached). `_watch_row` returns seven values via the
   pure `watch_row_values` helper; user-class rows share it; TSV headers
   are the seven names. Column widths 70/90/90/90/90/110/60 + Remove 90
   fit 960px with no horizontal scrollbar.
10. Watchlist PEG: `pegRatio` from the same `tk.info` already fetched
    for the market-cap fallback (no new source/fetch); 2 decimals;
    missing (BTC, GLD, funds without one) shows "-"; cached fallback
    like the other keys.
11. Four value cards via one `_overview_cards` helper (transparent
    wrapper, one equal `uniform="cards"` column per card, 20px gaps, no
    gap after the 4th, 20px below the row; CTkFrame + three left-aligned
    CTkLabels: FS_SMALL gray title padx=15 pady=(10,0), FS_TITLE bold
    value padx=15, FS_SMALL gray detail padx=15 pady=(0,8)). Order:
    Drift (drift_pp_text value, "actual x% vs standard y%" detail),
    Medi-Cal only when activated (value Qualified / Not qualified via
    the new `medical.card_figures` accessor — derived from projection
    + ceiling, no sentence parsing; no empty slot when inactive),
    Gains headroom ("-" / "no ceiling set" when unset), AGI guardrail
    ("OVER/UNDER by $X", "$A vs $B threshold"; "-" pair when unset).
    Cards replaced the bullet loop; the REQUIRED wording moved to
    Holdings (Item 13). Card text is single-line by design (labels carry
    no wraplength). Guide section 3 keep-list gains the value-card entry
    with the stated trade-off.
12. "Copy summary" button AND the `summary` string removed (string was
    used only by the button — no dead code left). Summary stays
    copyable per selectable line. Guide section 6 notes the removal
    (2026-11-18, user's call for elegance) and the selectable-text path.
13. REQUIRED line moved to the very top of Holdings as a `SelectableMsg`
    with `FS_BODY` font, packed full-width (`fill="x"`); text and logic
    unchanged via the pure `required_line_text` helper (still uses
    `_required_missing()`; "All ..." text when nothing is missing).
    Nothing REQUIRED renders on the Overview (comment wording adjusted
    so the literal appears nowhere in the Overview builder).
14. Cash is a row like any other ticker: the `holdings_by_asset` skip is
    removed (docstring updated); cash priced at $1.00 with avg/gain
    forced None (stored cost=1 is an amount convention, not a basis);
    row sorts by value with the rest and is always complete (never
    "upload" — the tooltip branch skips cash too). Cost/Gain cells
    render "—" in the table and TSV. Its expander groups by institution
    (bank of each lot, "?" fallback). Totals row label is exactly
    "TOTAL" in the table and TSV; `gain_unknown` ignores the cash row
    (cash carries no gain by design), so totals stay computable. The
    Totals-row comment and the Holdings guidance note follow the new
    scope. Holdings TOTAL now equals the Overview Total net worth (both
    include positions + cash + home; verified by construction — cash was
    already in the Overview liquid total at $1.00).
15. Holdings + Liquidity "Copy table" buttons pack `anchor="e"`
    (vertical positions unchanged); Table toolbar stays `sticky="e"` /
    `side="right"` (verified, untouched). Guide section 6 gains the
    right-edge rule as a standing style rule.
