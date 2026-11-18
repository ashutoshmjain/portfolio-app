# Prompt 10 — SelectableMsg everywhere + the app style guide

Status: DRAFT

## Context

The app's display text is split between two widgets. `SelectableMsg`
(a read-only `tk.Text` with word wrap) left-aligns wrapped lines and
makes text selectable (drag to select, Ctrl+C). A plain `CTkLabel`
centers its wrapped lines, so a continuation line drifts to the middle
instead of starting at the left edge. The Overview (the landing page)
still uses `CTkLabel` for its summary, and the Data Entry heading
wraps into three short rows because its `SelectableMsg` is packed
without `fill="x"`.

The standing reference for how the app looks is now
`prompts/app-style-guide.md` in this repo. Read it first; this prompt
applies it. The guide names the technology (Python + CustomTkinter on
tkinter, matplotlib for charts), the type scale, the colors, the
`SelectableMsg` rule, and the cell-state rule.

## Items

### 1. SelectableMsg accepts `anchor` (prerequisite for the swap)

Where: `SelectableMsg.__init__` in `portfolio_app.py`.

- Add an `anchor` parameter to `SelectableMsg.__init__` (accept and
  ignore it — a Text widget is always left/top, so the value has no
  effect). Several labels pass `anchor="w"` in the constructor (the
  Overview bullets do), and a mechanical swap must not raise
  `TypeError` on them.
- `wraplength` is already accepted (and ignored — the Text wraps at
  its container width). Confirm it stays accepted; do not remove it.

### 2. Overview summary → SelectableMsg (the landing page)

Where: Dashboard tab → Overview sub-tab → the summary block at the
top (the "Total net worth" line, the "Allowed spending" line, the
"Realizable" line, and the bullet lines). Screenshot: the Overview
after a refresh, full width and ~960px.

- Convert every label in the summary block to `SelectableMsg`:
  the "Total net worth" title (`FS_TITLE` bold), the "Allowed
  spending" line, the "Realizable" line, and the alert bullets
  (drift, Medi-Cal verdict, gains headroom, after-65 AGI guardrail,
  REQUIRED-positions).
- Pack each full-width one with `fill="x"` so it spans the container
  and wraps at the container width.
- Result: the wrapped continuation lines ("$98,066/yr after 65…",
  "standard (3.6%); drift (5.7pp).", "not modeled).") start at the
  left edge, aligned with their first lines — not centered.
- Copy summary, the scroll preservation, and every figure stay
  exactly as they are. Only the widget type and the alignment change.

### 3. Remaining prose and title labels → SelectableMsg

Where: every view that still renders display text with `CTkLabel`.

Convert each of the following to `SelectableMsg`, keeping its text,
font, and color. Pack a full-width one with `fill="x"`; pack an
inline single-line one (a label inside a row) without fill.

- Header bar: "PORTFOLIO DASHBOARD" and the date label.
- Watchlist (Dashboard → Overview, below the chart): the "Watchlist"
  heading, the class-section headings, "New asset class:", and
  "Add ticker to …:".
- Accounts (Dashboard → Accounts): the section heading.
- Diversification tab: the section heading.
- Tax Harvest tab: the "Tax Loss Harvesting" heading.
- Data Entry → Inputs: the bank headings, the account headings and
  the account-value labels, the "Closed" marker label, the drawer
  labels ("Move this lot to —", "Bank / Brokerage:", "Account:"),
  and the add-account form labels ("Bank / Brokerage",
  "Account name", "Account type (drives whether cost/dates …)",
  "First lot — asset", "First lot — shares").
- Data Entry → Inputs → guide panel: the "11 positions left to
  feed" line and the count line.
- Data Entry → Template: the section heading and the "Where to find
  each field at your broker:" line.
- Data Entry → Danger Zone: the section headings and the
  "Type DELETE to enable:" line.
- Settings dialog: every field label, the "Utilities" heading, the
  plugin descriptions, the "Properties" heading, the "Address
  (Street, City, State, Zip)" label, and the "Applied $" / last-value
  labels.
- Home-value dialog: "Latest home value estimate:" and its lines.
- Passphrase dialog: the prompt label.
- Add-position / Sell / Reopen forms: every field label ("Account",
  "Account type (new accounts only)", "Position (FIFO)",
  "Lot (specific override)", "Closed position").
- Utilities tab placeholder (when no plugin is enabled).

### 4. Fix the narrow-wrap defect (Data Entry heading)

Where: Data Entry tab → Inputs sub-tab → the heading at the top
("Positions 30 of 30 · Cost entered 4 of 28 · Dates entered 4 of
28"). Screenshot: the Data Entry Inputs view at full width.

- The heading (`self.cov_progress`, already a `SelectableMsg`) is
  packed without `fill="x"`, so the Text keeps its requested width
  of 20 characters (~250px) and wraps into three short rows even
  though the window is 960px wide.
- Pack it with `fill="x"` so it spans the container. The whole line
  fits on one row at full width and at ~960px.
- Do the same for the orange warning line under it (`self.cov_warn`),
  which is packed the same way.
- Rule for every `SelectableMsg` in this prompt: a full-width one is
  packed with `fill="x"` (or gridded with `sticky="ew"`). A
  `SelectableMsg` packed without fill goes narrow — that is the defect
  this item fixes, and it must not be reintroduced by any other item.

### 5. Cell states — the shading rule in the Data Entry grid

Where: Data Entry tab → Inputs sub-tab → the lot grid (the Cost $,
Acquired, Sold, Sale $ fields and the computed display cells beside
them: account totals, the "Closed" marker, computed notes).

Apply the cell-state rule from `prompts/app-style-guide.md` §4
(the 2×2 matrix: empty + editable → lighter shade; filled +
editable → normal shade; filled + non-editable → greyed out;
empty + non-editable → normal / bare `-`):

- An empty editable entry field (no cost, no date) renders with a
  lighter shade background, so the eye goes to what still needs
  filling.
- A filled editable entry field renders with the normal shade.
- A filled computed display cell (account total, "Closed" marker, a
  computed note) renders greyed out (muted foreground) — it is
  display-only and cannot be changed there.
- The "(need cost)" hints and the "?" markers keep their current
  muted hint treatment.
- The record tables (Holdings, Accounts, Liquidity, Tax Harvest) are
  NOT re-shaded: their data cells stay the normal text color (see
  item 7 — they are the record, not an input grid).

### 6. Medical plugin labels → SelectableMsg

Where: Utilities tab → Medi-Cal sub-tab.

- Convert all nine labels to `SelectableMsg`: the "Medi-Cal —
  projected income (base)" heading, the explainer, the "Project
  expected (not actual) annual income…" line, the five field labels
  (W-2, Pension, Interest, Dividends, Capital gains), the capital
  gains profit-not-proceeds note, the totals label, the verdict
  label, the display-only note, and the orange message label.
- Pack the explainer, totals, and verdict with `fill="x"`.
- The totals and verdict labels are stored in `app._medical_ui` and
  refreshed in place via `.configure(text=...)` and
  `.winfo_exists()` — both work on `SelectableMsg`. The refresh
  behavior (in place, no sub-tab rebuild, typing keeps focus) must
  keep working exactly as it does now.
- The plugin's `PLUGIN_ID` stays "medical" and its title stays
  "Medi-Cal". No state change.

### 7. What stays a plain label (do NOT convert)

- The `Table` class headers and cells, and the fixed-width grid-row
  labels (Holdings, Accounts, Liquidity rows, the Data Entry grid
  row labels, the calendar weekday labels). These use a fixed
  `width=` (character width); `SelectableMsg` takes no `width`
  parameter, and a Text widget per cell is heavy. The tables already
  carry a "Copy table" button (TSV). Leave them as `CTkLabel`.
- Layout spacers / markers: the empty `width=30` labels and the "●"
  dot. These are layout, not text.
- Controls stay their own widget types: buttons, entries, combos,
  checkboxes, switches, and tab names.

### 8. The style guide is the standing reference

- `prompts/app-style-guide.md` is the app's style guide. Do not
  duplicate its rules into other files.
- Add one line to the README pointing at it (where the README
  describes the UI / the plugin framework), so a new builder finds
  it.

### 9. Drop all font sizes by 2

Where: the type scale in `portfolio_app.py` (the `FS_*` constants)
and the two inline sizes in `plugins/medical.py`.

- Change the named constants, each down by 2:
  `FS_BODY` 16 → 14, `FS_HEAD` 20 → 18, `FS_TITLE` 24 → 22,
  `FS_TABLE_HEAD` 16 → 14, `FS_SMALL` 13 → 11.
- This supersedes the earlier "body ≥ 15px" minimum (body is now
  14, by the user's call). Update the comment on the constants to
  match, and update the type-scale table in
  `prompts/app-style-guide.md` §1 (already updated in this prompt's
  draft — confirm it reads 14 / 18 / 22 / 14 / 11).
- Replace the two inline sizes in `plugins/medical.py` with the
  named constants (no inline sizes anywhere): the "Medi-Cal —
  projected income (base)" heading (`size=20`) becomes `FS_HEAD`
  (18, bold); the verdict label (`size=18`) becomes `FS_BODY`
  (14, bold) — it stays bold for prominence, and it lands on a
  named constant rather than a one-off 16.
- Every widget that uses the named constants picks the new sizes up
  automatically. Do not change any other size, weight, or layout to
  compensate. The split-screen (~960px) constraint still holds —
  smaller text must not leave a view looking empty or misaligned;
  if a heading or summary now looks lost in its container, say so
  in the report rather than inventing a new size.

## Guardrails

- Build only these nine items. Do not change any figure, any
  computation, any tab structure, or any control.
- Do not convert the `Table` cells or the fixed-width grid labels to
  `SelectableMsg` (item 7). Do not change buttons, entries, combos,
  checkboxes, switches, or tab names.
- Do not hardcode a new color. Use the named roles in the style
  guide (§2). The cell shading in item 5 uses the guide's "lighter
  shade" — derive it from the existing panel background, don't invent
  a new palette.
- Push to main, then stop. The user launch-checks manually.

## Verification

- The committed test suite must pass in full. Add tests for: (a)
  `SelectableMsg` accepts `anchor` without raising; (b) the Overview
  summary labels are `SelectableMsg` (not `CTkLabel`); (c) the Data
  Entry heading is packed with `fill="x"`; (d) the cell-state shading
  (empty editable → lighter, filled editable → normal, filled
  non-editable → greyed); (e) the Medical totals/verdict refresh
  still works in place via `.configure(text=...)` on the converted
  labels; (f) the type scale reads `FS_BODY` 14, `FS_HEAD` 18,
  `FS_TITLE` 22, `FS_TABLE_HEAD` 14, `FS_SMALL` 11, and no
  `CTkFont(size=` literal remains anywhere (all sizes go through the
  named constants).
- Run a headless probe that builds the Overview, the Data Entry
  Inputs view, and the Medi-Cal sub-tab and asserts the widget types
  and the pack/grid options above.
- Report per item. Manual GUI check is the owner's step: Overview
  at full width and ~960px (all summary lines start at the left
  edge, nothing centered); Data Entry heading on one row; empty grid
  cells visibly lighter; computed display cells greyed.

## Deferred (do NOT build)

- A `width` parameter on `SelectableMsg` (would be needed to convert
  the fixed-width grid cells — not in this prompt).
- A light-mode theme or a theme switcher.
- Any change to the Table class beyond the shading in item 5.
