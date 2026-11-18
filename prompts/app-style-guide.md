# Portfolio App — Style Guide

Living document. The single reference for how this app looks and reads.
Every prompt that touches the UI follows it; a new rule goes here first,
then into a prompt. If the code and this guide disagree, the code is wrong
until a prompt fixes it — unless the user has said otherwise.

## 0. What the app is built with

- **Python + CustomTkinter + matplotlib.** CustomTkinter is a modern
  widget library built on **tkinter**, Python's standard GUI toolkit.
  CustomTkinter supplies the modern-looking widgets (`CTkButton`,
  `CTkLabel`, `CTkEntry`, `CTkTabview`, …) and the theme system;
  underneath it is all tkinter (Tk). matplotlib draws the charts.
- **Appearance: dark mode, blue color theme**, set once at startup
  (`ctk.set_appearance_mode("dark")`,
  `ctk.set_default_color_theme("blue")`). There is no separate published
  "CustomTkinter style guide" — the library's own documentation is the
  canonical reference for widget parameters and theming:
  <https://customtkinter.tomschimansky.com/>.
- The general principles below are the recurring consensus across the
  tkinter / CustomTkinter guidance: centralize styles in one place,
  prefer theme colors over hardcoded hex, keep spacing consistent, use
  one geometry manager per container, and lay out responsively so the
  app works at any window width.

## 1. Type scale — ONE place, not scattered per-widget values

| Constant | Size | Use |
|---|---|---|
| `FS_BODY` | 12 | Body text, everywhere |
| `FS_HEAD` | 16 | Section headings |
| `FS_TITLE` | 18 | Top headline numbers |
| `FS_TABLE_HEAD` | 12, bold | Table headers |
| `FS_SMALL` | 11 | Secondary hints only — never body text |

(The scale changed again on 2026-11-18 by the user's call — headline
18, body 12, superseding the earlier "body ≥ 15px" minimum. The steps
are now head = body + 4, title = body + 6.)

- Never set a font size inline per widget; use the named constants.
- The theme default font size is `FS_BODY`.

## 2. Colors — named roles, not one-off hex

| Role | Value | Use |
|---|---|---|
| Panel / note background | `#2B2B2B` | Selectable text blocks, notes |
| Default text | `#EDEDED` | All body text |
| Tooltip background | `#3A3A3A` | Hover tooltips (text `#EDEDED`) |
| Orange | `orange` | Warnings and status messages |
| Red | `red` | Negative figures (always parenthesized, never a minus sign) |
| Gray | `gray` | Secondary / display-only notes |

- Never hardcode a new color for a one-off; use the named roles above.
- Disabled labels in dark mode can show a distracting white grid in
  CustomTkinter — avoid `state="disabled"` on labels; grey out with
  color instead (see §4).

## 3. Text — the SelectableMsg rule

This is the core rule. It exists because of a real defect: a plain
`CTkLabel` **centers** its wrapped lines (the default justification),
so a continuation line drifts to the middle of the label instead of
starting at the left edge. A `tk.Text` left-aligns wrapped lines by
default — and it makes the text selectable.

- **All display text uses `SelectableMsg`** — prose, headings, titles,
  summaries, dialog messages, guidance, and status. `SelectableMsg`
  is the app's read-only `tk.Text` with word wrap: drag to select,
  Ctrl+C to copy. Typing, paste, and cut are blocked.
- **Full-width `SelectableMsg` MUST be packed (or gridded) with
  `fill="x"`** (or `sticky="ew"`). Without it the Text keeps its
  requested width of 20 characters (~250px) and wraps into short
  lines even when the window is wide — the heading "Positions 30 of
  30 · Cost entered 4 of 28 · Dates entered 4 of 28" wrapped into
  three rows for exactly this reason. This is the single most common
  layout mistake in this app.
- **Inline, single-line `SelectableMsg`** (a label inside a row, e.g.
  "Applied $") is packed without fill; it sizes to its text.
- `SelectableMsg` accepts `font`, `text_color`, `textvariable`, and
  `.configure(text=...)` / `.winfo_exists()` — it is a drop-in for the
  labels it replaces. It accepts `wraplength` (ignored — the Text
  wraps at its container width and reflows on resize) and `anchor`
  (accepted and ignored — Text is always left/top).
- **`CTkLabel` is kept ONLY for:**
  1. Fixed-width grid / table cells — the `Table` class and the row
     labels that use `width=` (character width). `SelectableMsg`
     takes no `width` parameter, and a Text widget per cell is heavy
     (a table can be hundreds of cells). The tables already carry a
     "Copy table" button (TSV), so per-cell selection adds little.
  2. Layout spacers / markers — empty `width=30` labels, the "●" dot.
  3. Overview value cards — three stacked `CTkLabel`s per card (small
     gray title, large bold value, small gray detail). The card text
     is short and single-line by design, so the centered-wrapped-lines
     defect does not apply (see §7). Trade-off, stated: the card
     figures are view-only; the main summary lines stay `SelectableMsg`
     and copyable.
- **Controls are not text.** Buttons, entries, combos, checkboxes,
  switches, and tab names stay their own widget types.
- Long text wraps at the container width and reflows on resize.
  Never set a fixed `wraplength` that fights the container.

## 4. Cell states — one rule for every data cell

A data cell has two independent facts: whether it holds a value, and
whether the user can edit it. The appearance follows from those two
facts, the same way everywhere:

| | Editable | Non-editable |
|---|---|---|
| **Empty** (no value) | **Lighter shade** background — the cell is waiting for input; the lighter shade draws the eye to what still needs filling | Normal / default (a bare `-` for a missing value). Nothing to enter and nothing to show |
| **Filled** (has a value) | **Normal shade** — the standard cell, no special treatment; it reads as an ordinary entered value | **Greyed out** (muted foreground) — the value is display-only; the grey tells the user it cannot be changed here |

- **Scope.** This rule governs the Data Entry lot grid (the
  Cost / Acquired / Sold / Sale entry fields and the computed display
  cells beside them) and any editable/display cell pair. Inside an
  editable grid, a computed display value (account total, "Closed"
  marker, a computed note) is filled + non-editable, so it greys out.
- **Record tables are the exception.** The read-only tables
  (Holdings, Accounts, Liquidity, Tax Harvest) are the record itself —
  their data cells render in the normal text color, because greying
  the entire record would hurt readability. The rule applies where a
  cell is a display value sitting inside an otherwise editable grid,
  not to a whole read-only table.
- **Numbers.** Zero renders as a bare `-`. Negative figures render
  red + parenthesized with `$` inside, never a minus sign (this
  includes percentages). Use the shared `fmt_usd` / `pct` /
  `drift_pp_text` helpers.

## 5. Layout

- **Fully usable in split-screen (~960px).** No clipped text or
  buttons; no horizontal scrollbar; no stacked button rows. Fix by
  consolidation / wrapping, never by a scrollbar.
- **One geometry manager per container.** Don't mix `pack` and `grid`
  in the same parent.
- **Consistent padding.** The established values are `padx=8–10` and
  `pady=1–4` for text, `padx=4` for row items. Don't invent new
  padding per widget.
- **One view = one scrollbar.** Tables render at their full content
  height inside the view's single scroll region; no table carries its
  own scrollbar.
- **One-path principle.** Exactly one way to reach any destination;
  no unnecessary buttons or menus.

## 6. Numbers, copy, and voice

- Money and percents use the shared `fmt_usd` / `pct` /
  `drift_pp_text` helpers (see §4 for zero / negative).
- **Copy must be real.** Every message, summary, and table carries a
  copy path: selectable text, "Copy table" (TSV). (The Overview
  summary's one-click "Copy summary" button was removed 2026-11-18
  by the user's call for elegance; the summary's copy path is now
  the selectable text — drag to select, Ctrl+C to copy.) A label
  that can only be copied by click+Ctrl+C is not enough for
  a message the user will paste elsewhere.
- **"Copy table" buttons sit on the right edge of their table
  (right-aligned), across the app** — so any future "Copy table"
  button follows the same rule.
- App copy reads as record-keeping, never as a trading platform.

## 7. Headings and structure

- One headline number per view (the "Total net worth" line,
  `FS_TITLE` bold). Section headings `FS_HEAD` bold. Table headers
  `FS_TABLE_HEAD` bold.
- Tabs: Dashboard, Diversification, Tax Harvest, Data Entry (LAST).
  No Retirement tab. Utilities appears only when ≥1 plugin is enabled.
- Dashboard sub-tabs: Overview, Accounts, Holdings, Liquidity, Tax
  implications. Data Entry sub-tabs: Inputs, Template, Danger Zone.

## 8. References — what this guide is built on

- CustomTkinter documentation (the library's own docs — widget
  parameters, appearance modes, color themes):
  <https://customtkinter.tomschimansky.com/>
- The general tkinter / CustomTkinter best-practice consensus:
  centralize styles in one place; prefer theme colors over hardcoded
  hex; consistent spacing; one geometry manager per container;
  responsive layout with weights.
- The app's own conventions, verified in code: the type scale
  (`FS_BODY` / `FS_HEAD` / `FS_TITLE`), the dark + blue theme, the
  `SelectableMsg` copy rule, the one-path principle, the split-screen
  constraint, and the number formatting (zero `-`, negative red +
  parenthesized).
