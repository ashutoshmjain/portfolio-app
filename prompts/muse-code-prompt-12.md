# Prompt 12 — Sidebar redesign: adopt the CustomTkinter tutorial (climate-app) layout and style; app renamed "Retirement Portfolio"

Status: DRAFT

## Context

The app is a desktop portfolio tracker (Python + CustomTkinter on
tkinter + matplotlib; dark mode + blue theme; see
`prompts/app-style-guide.md` first). The Overview's four value cards
(Prompt 11) do not read as boxes: each card is a plain `CTkFrame`
with the default color and the Overview page behind it is the same
color, so the text floats with no box around it. The owner's call
(2026-11-18) is to stop debating each detail and adopt the
CustomTkinter tutorial app's layout and style wholesale — the
climate-app tutorial at
https://customtkinter.tomschimansky.com/tutorial/climate-app is the
reference, created by the creators of CustomTkinter. Its layout
resolves the micro-decisions (for example, table titles are
left-aligned just like the rows). The tutorial's main view is
transparent over the darker window background, so the same
default-frame cards stand out as boxes — that is the card fix, folded
into this redesign (no separate card-color change).

The current shell is a slim top bar ("Portfolio" title + "As of"
date + a ☰ button + a status line) above a main `CTkTabview`
(Dashboard, Diversification, Tax Harvest, Data Entry, Utilities),
with Dashboard holding a sub-`CTkTabview` (Overview, Accounts,
Holdings, Liquidity, Tax implications) and Data Entry holding a
sub-`CTkTabview` (Inputs, Template, Danger Zone). The ☰ menu holds
four actions: Refresh stocks, Refresh home estimates, Log, Settings.
This prompt replaces that whole shell with the tutorial's left
sidebar + transparent main view, and renames the app
"Retirement Portfolio". The tutorial's style is adopted AS IS —
including its two named fonts and its appearance-mode menu. That
supersedes the Prompt 11 type scale for the title/value elements:
the tutorial's `title_font` (26pt bold) is the page header title
and the Total net worth headline, and its `value_font` (20pt bold)
is the sidebar title and the value card values. The dense content
keeps the Prompt 11 scale (FS_BODY 12, FS_HEAD 16, FS_TABLE_HEAD
12, FS_SMALL 11) — the tutorial does not define those, and the
app's tables and body text are already set for them. No figure,
computation, or data model changes. No new data files.

Reference (read before building): the tutorial's `create_sidebar`
and `create_main_view` in the climate-app source — a 200px sidebar
(`CTkFrame`, `corner_radius=0`) with a title at the top, a scrollable
list of transparent left-aligned nav buttons (selected = accent), and
option menus at the bottom; a transparent main view (`padx=20`,
`pady=20`) with a header (title + gray subtitle), value cards, and
content. One geometry manager per container (the app's standing
rule); the root grids column 0 = sidebar (fixed 200), column 1 =
main view (weight 1), row 0 weight 1.

## Items

1. **Sidebar shell.** Replace the top bar and both tabviews with
    the tutorial's sidebar. `sidebar = ctk.CTkFrame(self, width=200,
    corner_radius=0)`, gridded row 0, column 0, `sticky="nsew"`.
    Root: `self.grid_columnconfigure(1, weight=1)`,
    `self.grid_rowconfigure(0, weight=1)`. The slim top bar
    ("Portfolio" + "As of" + ☰ button + status line), the main
    `CTkTabview` (`self.tabs`), the Dashboard sub-`CTkTabview`
    (`self.dash_tabs`), and the Data Entry sub-`CTkTabview`
    (`self.data_tabs`) are all removed. The ☰ popup menu
    (`toggle_menu`, `self.menu_win`) is removed — its actions are
    redistributed below (Items 6, 7, 10, 11). The window title
    becomes "Retirement Portfolio" (was "Portfolio Dashboard").
2. **Sidebar title.** At the top of the sidebar, the title
    "Retirement Portfolio" in the tutorial's `value_font` (20pt
    bold) — the tutorial's title slot (it uses a logo image +
    title; this app has no logo, so the title alone). No subtitle.
    The app is now called "Retirement Portfolio" everywhere the
    name appears (window title, README, style guide). The old
    header title "Portfolio" (Prompt 11) is gone with the top bar.
3. **Nav buttons — ten entries, flat list, this order.**
    Overview, Accounts, Holdings, Liquidity, Tax, Diversification,
    Inputs, Template, Danger Zone, Utilities. (The owner's count:
    the five Dashboard views + Diversification + Tax Harvest +
    Data Entry's three, then Utilities — and Tax implications +
    Tax Harvest merge into "Tax", Item 8 — so ten.) A
    `CTkScrollableFrame` (`fg_color="transparent"`, width ~160)
    in the sidebar middle, expanding (`grid_rowconfigure` weight 1),
    holds one button per entry. Each button is the tutorial's nav
    button exactly: `CTkButton(text=<name>, anchor="w", height=32,
    fg_color="transparent", text_color=("gray10", "gray90"),
    hover_color=("gray75", "gray25"), command=show that page)`.
    The selected page's button gets `fg_color` = the accent color
    (the blue theme's button color, `THEME["CTkButton"]["fg_color"]`
    as the tutorial reads it); every other button stays
    transparent. Clicking a button shows that page in the main
    view (the page builders run; scroll-state keeping works as it
    does now across rebuilds). No grouping headings, no icons.
4. **Sidebar bottom — appearance mode + UI scaling + Settings.**
    Mirroring the tutorial's bottom exactly: an "Appearance mode:"
    label + `CTkOptionMenu` with values ["System", "Light",
    "Dark"] (calling `ctk.set_appearance_mode` as the tutorial
    does), then a "UI scaling:" label + `CTkOptionMenu` with
    values ["80%", "90%", "100%", "110%", "120%"] (default "100%",
    calling `ctk.set_widget_scaling` as the tutorial does). Below
    the UI scaling menu, a "Settings" button that opens Settings
    (the same `open_settings` the ☰ menu's Settings action
    called). The default appearance mode stays "dark" (as now), so
    nothing changes for the current user unless they switch. The
    theme settings are wanted now that the app is matured and
    getting ship-ready (owner, 2026-11-18) — which is why the
    colors must be theme-aware (Item 14), so Light mode renders
    correctly instead of showing dark-tuned colors on a light
    background.
5. **Main view + header.** A `CTkFrame` with
    `fg_color="transparent"`, gridded row 0, column 1, `padx=20`,
    `pady=20`, `sticky="nsew"` — the tutorial's main view. Its
    header is a transparent frame holding the current page's title
    in the tutorial's `title_font` (26pt bold) and, beneath it, a
    gray subtitle line (FS_SMALL + CLR_SECONDARY) with the "As of
    <date>" date and the status message — the two globals that
    lived in the old top bar. The page title changes per page; the
    subtitle is the same on every page. This transparent main view
    IS the card fix: the window background is darker than the
    default `CTkFrame` color, so the value cards (plain
    `CTkFrame`, unchanged) now read as boxes. Do not give the
    cards an explicit `fg_color` — the tutorial's mechanism is the
    fix. The value card values use the tutorial's `value_font`
    (20pt bold); the card titles and details stay FS_SMALL +
    CLR_SECONDARY.
6. **Overview (landing page) + Refresh stocks.** The Overview
    keeps its content unchanged (Total net worth, Allowed spending,
    Realizable, the four value cards, the chart, the Watchlist).
    A "Refresh stocks" button sits at the top right of the
    Overview's header (the tutorial header's right side). It calls
    the same refresh the ☰ menu's Refresh stocks action called.
    Only the Overview has it — no Refresh button on other pages.
7. **The ten pages.** Each sidebar entry shows its page in the
    main view. The existing builders move unchanged into the main
    view: the five Dashboard views (Overview, Accounts, Holdings,
    Liquidity) become top-level pages; Diversification becomes a
    top-level page; Data Entry's three sub-tabs (Inputs, Template,
    Danger Zone) become three top-level pages; Utilities becomes a
    top-level page (Item 9); Tax implications + Tax Harvest merge
    into the Tax page (Item 8). One view = one scroll region, as
    now. The "As of" date and status subtitle (Item 5) appear on
    every page.
8. **Tax page (merge Tax implications + Tax Harvest).** One page
    called "Tax". It shows the Tax implications content first,
    then the Tax Harvest content, in one scroll region, in this
    order: (a) the note "What each account type means for tax and
    withdrawals (facts, not advice).", (b) the Table ["Account
    type", "Tax / withdrawal treatment"] (one row per account
    type), (c) the Table ["Account", "Type"] (one row per account),
    (d) the "Tax Loss Harvesting" heading and the TLH
    opportunities Table, the sold-lots Table, and the summary
    Table. Reuse the existing builders' table code; do not rebuild
    the tables. The two old builders (`build_taximplic`,
    `build_tax`) fold into one `build_tax` page.
9. **Utilities page — always visible, activation moves here.**
    The Utilities sidebar entry is ALWAYS present (the old
    gating — hidden when no plugin is enabled — is removed; the
    `_sync_utility_tabs` add/delete logic goes with it). The
    Utilities page keeps its `CTkTabview`, but its first sub-tab
    is now "Plugins": it lists EVERY discovered plugin (title +
    description + an enable/disable control), whether enabled or
    not — no hiding. Each ENABLED plugin also gets its own sub-tab
    (their content, as now). The activation moves here from
    Settings: remove the "Utilities" section from Settings (the
    per-plugin `CTkCheckBox` list at `open_settings` ~line 5090
    and its comment about the tab appearing/disappearing). The
    plugin state still lives in `profile.json` under `"plugins"`
    and is still backed up/restored with it; only the UI that
    edits it moves.
10. **Auto-log on refresh; the manual Log action is gone.** Every
    successful Refresh stocks automatically appends a drift-log
    entry — the same `pc.append_close(DRIFT_LOG, liquid,
    home_value, today_total, standard_total)` the old "Log" action
    called (`log_close`). No user option, no toggle, no button:
    it always logs on refresh. `append_close` already upserts by
    date (one row per day; a second refresh the same day
    overwrites today's row) and returns "weekend — no market
    close to log" on Saturday/Sunday, so multiple refreshes and
    weekend refreshes are safe. If the refresh leaves the
    standard total unavailable (live BTC/GLD/VTI/MSTR prices
    missing), show the status message ("Cannot log close — drift
    needs live BTC/GLD/VTI/MSTR prices.") and do not write — do
    not crash. The old "Log" action and its ☰ menu entry are
    removed.
11. **Refresh home estimates is gone.** The "Refresh home
    estimates" action is removed (the owner is not using the
    RentCast API). Home-value settings (the RentCast key, the
    home purchase price, the manual applied value) stay in
    Settings, unchanged. A Real Estate tab in Utilities is a
    later idea, not this prompt.
12. **Table titles left-aligned like the rows.** Style rule, in
    the guide and in code: every table's header (title) row is
    left-aligned, exactly like its data rows. The `Table` class
    already does this (`CTkLabel(..., anchor="w")` gridded
    `sticky="w"`); record it as the rule and apply it to every
    other header rendering in the app (Watchlist class headers,
    Holdings column headers, any hand-built header row) so no
    table centers or right-aligns its titles. Add the rule to
    the style guide §4 (cell states / tables).
13. **Style guide + README follow.** Update
    `prompts/app-style-guide.md`: §5 (layout) gains the sidebar
    (200px, `corner_radius=0`, title, scrollable nav buttons,
    appearance mode + UI scaling + Settings at the bottom) and the
    transparent main view (`padx=20`, `pady=20`, header title +
    gray subtitle); §3 gains the nav-button style (transparent,
    left-aligned, 32px, hover gray, selected = accent) and the
    tutorial's two fonts (`title_font` 26pt bold,
    `value_font` 20pt bold); §4 gains the table-title left-align
    rule; §1 records the new type scale (title 26, value 20,
    body 12, headings 16, table headers 12, small 11) and that
    the Prompt 11 scale is superseded for the title/value
    elements by the tutorial's fonts, adopted as-is. The README's
    app name becomes "Retirement Portfolio" and its navigation
    description becomes the sidebar (ten entries), not the tab
    bar.
14. **Theme-aware colors (the appearance menu must work).** The
    app's hardcoded dark colors must adapt to the appearance mode,
    or Light mode shows dark-tuned colors on a light background.
    Convert them to theme-aware (light, dark) tuples, following
    the tutorial's pattern (`GRAY_TEXT_COLOR = ("gray40",
    "gray60")`): `CLR_SECONDARY` becomes `("gray40", "gray60")`
    (replacing `"#C9C9C9"`); primary text and panel backgrounds
    use the theme default (remove the hardcoded `"#EDEDED"` text
    color and `"#2B2B2B"` panel color, letting the theme supply
    the mode-appropriate color); `CELL_EMPTY_BG` derives
    per-mode from the panel color (dark: `_lighter` of the dark
    panel, as now; light: a slightly darker shade of the light
    panel, via the same helper with a factor below 1). The
    status colors (orange `#F5A524`, red `#E5484D`) are
    mode-independent and stay as-is. The default appearance mode
    stays "dark", so the current look is unchanged unless the
    user switches.

## Guardrails

- Build only these fourteen items. No figure, computation, tab
  content, or data-model change. The page builders' content moves;
  it does not change. No new hardcoded sizes beyond the tutorial's
  own (sidebar width 200, nav button height 32, main padx/pady 20,
  title 26, value 20) — those are the tutorial's numbers, named in
  the items, and they are the only numeric layout/font literals
  this prompt adds.
- The type scale changes only as Items 2, 5, and 13 name it
  (title 26, value 20 for the title/value elements; body 12,
  headings 16, table headers 12, small 11 stay). Do not change
  any other font size.
- Do not add a Real Estate tab. Do not merge any other pages (the
  Tax merge is the only one). Do not reintroduce a top tab bar or
  a ☰ menu.
- The auto-log (Item 10) writes only through `append_close` — one
  row per day, weekends skipped — never a second log path.
- The appearance menu (Item 4) defaults to Dark. The theme-aware
  colors (Item 14) must render correctly in Light mode — verify
  by switching to Light in the headless probe, not by assuming.

## Verification

- Full committed test suite passes, plus NEW committed tests for
  this prompt: (a) the root grids column 1 with weight 1 and the
  sidebar is a 200-wide `corner_radius=0` frame at column 0;
  (b) the sidebar title reads exactly "Retirement Portfolio" and
  the window title reads "Retirement Portfolio"; (c) the nav list
  holds exactly the ten names in order (Overview, Accounts,
  Holdings, Liquidity, Tax, Diversification, Inputs, Template,
  Danger Zone, Utilities); (d) a nav button is transparent with
  `anchor="w"` and height 32, and the selected one carries the
  accent `fg_color`; (e) the sidebar bottom holds an
  appearance-mode menu (System/Light/Dark, default Dark) above a
  UI scaling menu (80/90/100/110/120, default 100%) with a
  Settings button below it; (f) the main view is a transparent
  frame with padx/pady 20 and its header shows the page title
  (26pt bold) plus the "As of" date and status; (g) the Overview
  header carries a "Refresh stocks" button at the top right and
  no other page does; (h) the Tax page renders both the
  account-type treatment table and the TLH opportunities table;
  (i) the Utilities entry is present with no plugin enabled, its
  "Plugins" sub-tab lists every discovered plugin with an
  enable/disable control, and Settings carries no Utilities
  section; (j) a refresh appends a drift-log row (upsert by date)
  with no user option, and a missing standard total logs nothing
  and shows the status message; (k) no "Refresh home estimates"
  action, no ☰ menu, no top tab bar; (l) every table header is
  left-aligned (`anchor="w"` / `sticky="w"`); (m) the title font
  reads 26 and the value font reads 20 (sidebar title + card
  values), while the body/table/small scale still reads
  12/16/12/11; (n) the secondary color is theme-aware
  (`("gray40", "gray60")`) and no hardcoded `"#EDEDED"` /
  `"#2B2B2B"` text/panel color remains, and switching the
  appearance mode to Light renders the sidebar and a page
  without error.
  (Prompt 11's verification asked for new tests and they were
  added — keep that bar: add these ones.)
- Headless probe: build the app and click each of the ten sidebar
  entries, confirming each page renders; confirm the selected
  button turns accent and the others stay transparent; confirm
  the Overview shows the four value cards as visible boxes (the
  card frames contrast with the main-view background) and the
  Refresh stocks button at the top right; confirm the Tax page
  shows both the reference tables and the TLH tables; confirm
  the Utilities page lists all plugins with the first sub-tab
  "Plugins"; confirm a refresh writes one drift-log row for
  today; switch the appearance mode to Light and confirm the
  sidebar and a page render without error and the text stays
  readable; confirm the sidebar + main view fit at full width and
  at ~960px split-screen with no horizontal scrollbar.
- Manual GUI check is the owner's step: the sidebar reads like
  the tutorial's (title, ten entries, appearance mode + UI
  scaling + Settings at the bottom); every page reachable from
  the sidebar; the value cards now look like boxes; the Tax page
  reads as one page; the Utilities page shows all plugins with
  activation on the page; a Refresh stocks click logs today's
  drift row; switching to Light mode looks right.

## Run line

Pull the latest portfolio-app, then execute
`prompts/muse-code-prompt-12.md` — read
`prompts/app-style-guide.md` first, build the fourteen items, and report
per item.
