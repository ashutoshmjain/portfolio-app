# Prompt 14 — Tutorial type scale, header net-worth subtitle, light-mode fix

Status: DRAFT 2026-11-18 — awaiting the owner's yes to post.

## Context

The app is `Retirement Portfolio` (Python + CustomTkinter on tkinter +
matplotlib). The repo is `ashutoshmjain/portfolio-app`, branch `main`.
The last build is Prompt 13 (`9d31d35`, verified: full suite 106 tests,
83 ran, 23 skipped headless, 0 failures). The review below is from the
owner's manual launch-check of that build (two screenshots, Dark and
Light, full width ~1920px, 2026-11-18). Read `prompts/app-style-guide.md`
first. Build only the three items below, then report per item.

Design reference — the tutorial pages. The font sizes come from the
CustomTkinter styling tutorial's Fonts page,
https://customtkinter.tomschimansky.com/tutorial/fonts (open it):
its Medium (default) size is heading 28, text 14, and its small
secondary label (the date line) is 12. The header subtitle treatment
comes from the climate-app tutorial,
https://customtkinter.tomschimansky.com/tutorial/climate-app (open it):
its header is a title label (`title_font`, 26 bold) beside a plain
`CTkLabel` subtitle (`text_color=("gray40", "gray60")`, no explicit
font, so the default font) on the same line — no box, no wrap. The
words below describe the same references precisely, so the build does
not depend on the pages alone.

What is true now (verified in code at `9d31d35`):

- Type scale: `FS_BODY` 10, `FS_HEAD` 14, `FS_TABLE_HEAD` 10,
  `FS_SMALL` 11, `FS_TITLE` 18 (card values only), `TITLE_FONT_SIZE`
  26, `VALUE_FONT_SIZE` 20. The theme default font size is set to
  `FS_BODY`, so sidebar nav buttons and table cells inherit it.
  Prompt 13 dropped body/headings/table headers by 2px; the owner
  reports the text is now too small to read comfortably.
- The header Total net worth (`self.header_net`) is a `SelectableMsg`
  (a `tk.Text` box, `width=20`, background = panel color) packed
  beside the title, in `CTkFont(size=11)` — the only numeric font
  size literal in the app. Because the box is 20 characters wide and
  the text "Total net worth: $4,172,299" is 26 characters, it wraps
  to two lines and renders as a small dark box. The reference's
  subtitle is a plain label, one line, no box.
- Light mode is broken (verified against the library source and by
  calling the color helpers headless). Two independent causes:
  (a) `_mode_is_light` always returns False. It compares
  `widget.winfo_toplevel()._get_appearance_mode() == "Light"`, but
  CustomTkinter's `_get_appearance_mode()` returns lowercase
  `"light"` / `"dark"` (see
  `windows/widgets/appearance_mode/appearance_mode_base_class.py`:
  it returns `"light"` when the mode is 0, `"dark"` otherwise).
  `"light" == "Light"` is False, so every theme-derived color
  (`_card_bg`, `SelectableMsg` background, `_cell_empty_bg`)
  resolves to its dark half in Light mode — dark panels on a light
  window, dark text on dark panels in the tables. Dark mode looks
  right only because False is accidentally the correct answer there.
  The fallback (`ctk.get_appearance_mode() == "Light"`) never runs:
  `_get_appearance_mode()` does not raise, it just returns the
  lowercase string. Verified headless: `_card_bg(True)` is the light
  gray `#D3D3D3` and `_card_bg(False)` is `#292929` — the helper is
  correct, the `light` flag it is given is wrong.
  (b) The matplotlib chart dressing is hardcoded dark
  (`portfolio_calc.py`: `CHART_BG = "#242424"`,
  `CHART_AXES = "#2B2B2B"`, `CHART_TEXT = "#EDEDED"`,
  `CHART_SPINE = "#8A8A8A"`, applied by `_darken_chart`). The figure
  is dark in both modes. The comment there says "the app is dark" —
  that is no longer true; Light mode is a supported mode.
  The page body IS rebuilt on a mode switch
  (`change_appearance_mode` calls `refresh_current_page`), so once
  (a) and (b) are fixed the rebuilt page picks up the new mode. The
  header is NOT rebuilt: `header_sub` (the "As of …" status bar, a
  `SelectableMsg` built once at startup) keeps its construction-time
  background after a switch, so it stays dark in Light mode. The
  net-worth subtitle becomes a `CTkLabel` under item 2, so it
  updates itself; the status bar needs its background refreshed on
  a mode switch.

## Items

1. **Type scale follows the tutorial (Fonts page, Medium).**
   Where: Overview, full width and split-screen (~960px) — every
   page; the sidebar nav text and the table cells are the visible
   symptom (both inherit the theme default font size).
   Change only these constants (in `portfolio_app.py`):
   `TITLE_FONT_SIZE` 26 → 28 (the tutorial's heading),
   `FS_BODY` 10 → 14 (the tutorial's text),
   `FS_HEAD` 14 → 18 (section headings: body + 4, the same step as
   before Prompt 13),
   `FS_TABLE_HEAD` 10 → 12 (the tutorial's small size),
   `FS_SMALL` 11 → 12 (the tutorial's small size).
   Unchanged: `VALUE_FONT_SIZE` 20 (sidebar title; the tutorial does
   not define one, and the climate app uses 20), `FS_TITLE` 18 (card
   values — the owner's earlier call to hold at 18). No other font
   size changes anywhere. Update the style guide §1 type-scale table
   and the README scale line to the new numbers. The sidebar nav text
   and the table cell text grow with `FS_BODY` because they inherit
   the theme default — no per-widget font change is needed, and none
   is wanted.

2. **Total net worth becomes a plain subtitle label, like the
   reference's "Ireland" line — no box, one line, small and gray.**
   Where: Overview header, full width — the "Total net worth:
   $4,172,299" beside the "Overview" title, currently a small dark
   box wrapping to two lines.
   Replace `self.header_net` (a `SelectableMsg` in
   `CTkFont(size=11)`) with a plain `CTkLabel`, like the reference's
   `location_label`: `text_color=CLR_SECONDARY`, font in `FS_SMALL`
   (the small/secondary size, 12 under the tutorial scale — smaller
   than the body text, the way a subtitle sits below a title),
   packed beside the title with a small left pad and a small top pad
   so it sits on the title's baseline (the reference uses
   `padx=15, pady=(6, 0)`).
   The label sizes to its text, so "Total net worth: $4,172,299"
   sits on one line with no box and no wrap. The `size=11` literal
   goes away with the `SelectableMsg` — after this item there is no
   numeric font size literal left in the app. The text stays the
   live figure, Overview only, and the other pages still show no
   subtitle. The header title, the status bar, and the rest of the
   header do not change.

3. **Light mode renders correctly — light panels, dark text,
   light chart.**
   Where: Overview, Light mode, full width — the value cards, the
   chart panel, the watchlist panel, the "As of …" status bar, the
   Allowed spending / Realizable lines, and the watchlist table all
   render dark on a light window, and the table rows are dark text
   on a dark panel (unreadable).
   (a) Fix `_mode_is_light` so it returns True in Light mode:
   compare the appearance-mode string case-insensitively
   (`_get_appearance_mode()` returns lowercase `"light"` /
   `"dark"`; `ctk.get_appearance_mode()` returns capitalized
   `"Light"` / `"Dark"` — normalize before comparing). No other
   change to the color helpers: `_card_bg`, `_cell_empty_bg`, and
   the `SelectableMsg` background resolution are correct once they
   are given the right `light` flag.
   (b) Make the matplotlib chart dressing mode-aware. The figure
   background, axes background, text, and spine colors must follow
   the current mode: in Light mode the figure and axes sit on the
   same light panel background as the cards and the text is dark;
   in Dark mode they stay exactly as now. Pass the mode (or the
   resolved colors) into the chart dressing from the app side;
   do not hardcode a second palette in the calc module. The chart
   is rebuilt when the page rebuilds, so a mode switch picks the
   new dressing up with the page.
   (c) Refresh the persistent header status bar on a mode switch.
   `header_sub` is built once at startup and is not rebuilt by
   `refresh_current_page`, so after (a) its background must be
   re-resolved to the new mode's panel color (and its text color
   to the new mode's text color) inside `change_appearance_mode`.
   The net-worth subtitle needs no such step — it is a `CTkLabel`
   after item 2 and updates itself. After this item, switching
   Dark → Light (and Light → Dark) leaves every visible panel
   light with dark text in Light mode and dark with light text in
   Dark mode, and the watchlist table reads dark-on-light in
   Light mode. No other page, control, or color changes.

## Guardrails

- Build only these three items. Page content does not change; no
  new pages, menus, settings, or controls. The only numeric
  constants changed are the five font sizes in item 1. The only
  numeric font literal removed is the `size=11` in item 2. No
  hardcoded palette colors: the chart's light-mode colors are
  derived from the theme the same way `_card_bg` derives them, not
  a second hardcoded palette.
- The `_mode_is_light` fix is a comparison fix, not a rework of
  the color helpers. Do not change `_card_bg`, `_cell_empty_bg`,
  `_to_hex`, `_theme_for_mode`, or `SelectableMsg`'s construction
  except as item 3(c) requires for the header status bar.
- `FS_TITLE` stays 18 and `VALUE_FONT_SIZE` stays 20 — the owner's
  calls, not gaps. The sidebar width stays 170, the collapse
  control stays as built, the chart stays `figsize(10, 2.5)` with
  its controls panel.
- The Data Entry pages (Inputs, Template, Danger Zone) are skipped
  by `refresh_current_page` by design; item 3 does not change that.
  If a mode switch while on one of those pages leaves a stale
  panel there, note it in the report rather than rebuilding those
  pages.

## Verification

- The full committed suite passes (run `python -m unittest
  discover -s tests` from the repo root — the WHOLE suite, all
  test files, not a subset; the last build's report counted only
  the `test_prompt*.py` files as "60/60" when the suite is 106).
  Add NEW committed tests: (a) the five font constants are the
  tutorial values (28 / 14 / 18 / 12 / 12) with `FS_TITLE` 18 and
  `VALUE_FONT_SIZE` 20 unchanged; (b) `_mode_is_light` returns
  True when the appearance mode reports `"light"` (lowercase) and
  False for `"dark"`; (c) `_card_bg(True)` is a light color and
  `_card_bg(False)` is dark; (d) `header_net` is a plain `CTkLabel`
  (not a `SelectableMsg`) and no `size=11` literal remains in the
  app; (e) the chart dressing produces a light figure background
  with dark text in Light mode and the current dark dressing in
  Dark mode; (f) after a mode switch the header status bar carries
  the new mode's panel background. Update the older scale tests
  that assert the superseded Prompt 13 values, with a supersede
  note naming this prompt and item.
- Headless probe (run it; do not commit it): the font constants;
  `_card_bg` light vs dark; the chart dressing in both modes;
  a mode switch Dark → Light → Dark on the Overview rebuilds the
  page with light panels then dark panels, the status bar follows,
  and the table rows stay readable in both modes.
- Manual GUI check is the owner's step: full width and ~960px
  split-screen, Light and Dark, collapse/expand, the net-worth
  subtitle beside "Overview" on one line with no box, the chart
  controls, and the watchlist table readable in Light mode.
