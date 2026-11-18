# Prompt 13 — Design aesthetics: the landing page

Status: DRAFT

## Context

Prompt 12's sidebar shell is live and the owner likes it. His screenshot
(2026-11-18, Overview, split-screen) shows four follow-ups, and he then
shared the tutorial app's screenshot
(customtkinter.tomschimansky.com/tutorial/climate-app) as the design
reference and asked for a design-aesthetics pass on the landing page
(the Overview). This prompt IS that pass: it bakes in the seven
features already discussed, plus the panel consistency the reference
screenshot shows.

What the reference screenshot shows that our landing page does not
yet. Design reference — the screenshot and the link. Open the screenshot at
`prompts/design-reference-climate-app.png.b64` (in this repo, beside
this spec — it is part of this prompt) and follow its layout and
panel treatment. The picture is stored as base64 text because the
repo push is text-only: decode it to a PNG first (`base64 -d
prompts/design-reference-climate-app.png.b64 >
design-reference-climate-app.png`) and open the PNG. The tutorial
page is https://customtkinter.tomschimansky.com/tutorial/climate-app
— open it for the full tutorial. The words below describe the same
reference precisely, so the build does not depend on the picture
alone.

- Every content block sits on the SAME slightly lighter panel
  background — the four value cards, the map, the chart panel, the
  notes panel. Each block reads as a distinct box, and the whole view
  has one consistent "panel" language. Our value cards blend into the
  main view (no explicit background), and the chart and Watchlist sit
  directly on the main view with no panel at all.
- The header is one line: a large bold title with a short gray
  subtitle beside it — the reference screenshot shows "Dublin"
  followed by "Ireland · 53.35° N, 6.26° W" in small gray text on
  the same line. Our status line sits below the title as a small
  dark box (Item 1 fixes the box; the title stays above it). Our
  Total net worth headline is a big line below the header; the
  reference screenshot puts its headline figure in the small gray
  subtitle beside the title (Item 9 does the same for our net
  worth).
- The main visual (the map) is a compact panel, about twice as wide
  as it is tall, and to its right sits a narrower panel holding the
  controls (units, compare, a checkbox, a save button). Both panels
  pop out over the background on the same panel color. Our chart is
  a tall full-width figure with no controls beside it (Item 10
  makes it a compact panel with a controls panel on the right).
- Interactive controls are the blue accent: the selected nav button,
  the buttons, the dropdowns. Our app already does this (selected
  Overview is blue, the Dark/100% dropdowns are blue) — no change.

The Prompt 12 font gap is SETTLED by the owner's call (2026-11-18):
the value card values STAY at `FS_TITLE` = 18 — the 26/20 for those
is not happening. The Total net worth headline is no longer a big
line at all — it moves into the header as small gray text (Item 9),
so `FS_TITLE` = 18 now applies only to the card values.
`TITLE_FONT_SIZE` 26 and `VALUE_FONT_SIZE` 20 remain for the page
header title and the sidebar title only.

## Where

- Tab: the Overview (the landing page) and the shell around it. The
  status bar is the subtitle under the page title in the main view
  header. The Refresh button is the top-right button on the Overview
  header. The sidebar is the 200px left pane. The value cards, the
  chart and the Watchlist are the Overview's content blocks.
- App state: any page, dark mode, split-screen (~960px).

## Items

1. **Status bar becomes a full-width horizontal bar.** The subtitle
   under the page title ("As of <date>" + the status message,
   `self.header_sub`, a SelectableMsg in the header's left frame)
   currently renders as a small dark box, because its frame is
   gridded `sticky="w"` and only takes the width of its text. Make
   it a longer horizontal bar that spans the full width of the main
   view, under the page title. The text stays exactly the same
   ("As of <date>" + the status message); only the geometry
   changes — the bar stretches from the left edge to the right edge
   of the main view. The page title stays above it, same size.

2. **Refresh stocks moves to the sidebar, above Settings.** Remove
   the "Refresh stocks" button from the Overview header (and from
   the header actions box entirely — no page carries it in the
   header). Add a "Refresh stocks" button to the sidebar, above the
   Settings button, so it is reachable from every page. The progress
   bar moves with it: it sits directly below the Refresh button in
   the sidebar and shows the same refresh progress. The refresh
   itself is unchanged (same `refresh_async`, same auto-log of the
   drift row on success). This also corrects the sidebar bottom
   order: the build placed the Settings button ABOVE the appearance
   and scaling menus, but Prompt 12 put Settings BELOW UI scaling.
   The bottom of the sidebar, top to bottom, is now: Appearance
   mode menu, UI scaling menu, Refresh stocks button, Settings
   button (at the very bottom). The appearance and scaling menus
   keep their values and defaults (Dark, 100%).

3. **Drop body, heading and table-header type by 2 points.** `FS_BODY`
   12 → 10, `FS_HEAD` 16 → 14, `FS_TABLE_HEAD` 12 → 10. These are
   constants only; the new values flow everywhere those sizes are
   used. Unchanged: `TITLE_FONT_SIZE` 26, `VALUE_FONT_SIZE` 20,
   `FS_SMALL` 11, `FS_TITLE` 18. The style guide §1 and the README
   record the new scale: title 26, value 20, body 10, headings 14,
   table headers 10, small 11.

4. **Remove the sidebar subtitle.** Delete the "All pages, one
   sidebar" label under the sidebar title ("Retirement Portfolio").
   Nothing replaces it. The title stays, the nav buttons move up to
   fill the freed space.

5. **Narrow the sidebar.** `SIDEBAR_WIDTH` 200 → 170. The nav
   buttons, the appearance/scaling menus, the Refresh button and
   the Settings button all keep their layout (same padding, same
   heights); only the pane gets narrower, giving the main view 30px
   more. All ten nav names must still fit without clipping at the
   new width, at the new body size (10pt).

6. **Collapse button for the sidebar.** Add a control that hides
   the left sidebar so the main view takes the full window width —
   the fix for wide tables in split-screen. A collapse control sits
   at the top of the sidebar (next to the title); clicking it hides
   the sidebar and shows an expand control at the top-left of the
   main view; clicking expand brings the sidebar back. The
   collapsed state is session-only (not persisted); the app starts
   with the sidebar shown. The main view must reflow to the full
   width when collapsed (no empty gap where the sidebar was) and
   back to the sidebar width when expanded. The current page and
   its scroll position are kept across collapse/expand.

7. **Value cards get a distinct background so they read as cards.**
   The four Overview value cards (`_overview_cards`) are plain
   `CTkFrame`s with no explicit `fg_color`, so they take the
   default frame color — which blends into the transparent main
   view and the window behind it. In the reference screenshot the
   same cards stand out as boxes. Give each card an explicit background that
   is visibly lighter than the main view in dark mode (a slightly
   lighter grey), so each card reads as a distinct box. The
   background must be theme-aware: it stays distinct in Light mode
   too (a correspondingly darker shade of the light panel, not the
   dark-mode grey). Reuse the existing theme-aware derivation
   pattern (`_lighter` + the theme pair, the way `_cell_empty_bg`
   derives the empty-cell shade from `PANEL_COLOR`) rather than
   hardcoding a new palette color. The card contents do not change:
   title and detail stay FS_SMALL + CLR_SECONDARY, the value stays
   FS_TITLE (18) bold, left-aligned, same padding, same 20px gaps,
   same 20px below the row.

8. **The chart and the Watchlist get the same panel background as
   the cards.** In the reference screenshot every content block
   shares one panel background, so the whole view reads as a set of
   panels.
   On our Overview only the value cards would have it (Item 7);
   the chart (a matplotlib canvas packed directly on the body) and
   the Watchlist (heading + class sections packed directly on the
   body) sit on the bare main view. Wrap each of them in the same
   panel background as the value cards — one consistent panel color
   for all three blocks (cards, chart, Watchlist). The chart's
   figure background matches the panel, so the chart reads as one
   panel rather than a dark figure on a lighter frame. The chart
   data, axes, legend and title do not change; the Watchlist rows
   and "Copy table" behaviour do not change. The summary lines
   above the cards (Allowed spending, Realizable) stay as plain text
   on the main view, as the reference screenshot's title + subtitle
   do — they are not panels. (Total net worth is no longer a summary line —
   it moves into the header, Item 9.)

9. **Total net worth moves into the header as a small gray subtitle.**
   The big "Total net worth: $..." line is removed from the Overview
   content. Instead, on the Overview only, the header title line
   reads "Overview" followed by the Total net worth in small gray
   text on the same line, to the right of the title — the way the
   reference screenshot shows "Dublin" followed by "Ireland ·
   53.35° N, 6.26° W".
   The subtitle reads "Total net worth: $4,172,299" (the live figure,
   same value the removed headline showed), in `FS_SMALL` (11pt) and
   `CLR_SECONDARY` (gray), not bold. It shows only on the Overview;
   on every other page the header title stands alone with no
   subtitle. Removing the big headline line lets the cards sit right
   below the header area, giving them room. The Allowed spending and
   Realizable lines stay where they are, above the cards, as plain
   body text.

10. **The chart becomes a compact panel with a controls panel on the
    right.** The Overview chart ("Actual vs Standard — daily close")
    is a tall full-width figure (`Figure(figsize=(10, 4.6))`). Make
    it a compact panel like the map in the reference screenshot
    (the map panel in the decoded
    `prompts/design-reference-climate-app.png.b64` — decode it to a
    PNG first, see the design reference above):
    reduce the figure height to 2.5 inches (`figsize=(10, 2.5)`, width stays 10), so
    the rendered chart is about half as tall as now — roughly twice
    as wide as it is tall — and place it in the left column of a
    two-column row. On the right-hand side, in the narrower column
    (about 40% of the row, the chart taking about 60%), sits a
    controls panel holding the chart's controls: a "Show standard"
    checkbox (checked by default; unchecking hides the Standard
    line and redraws with Actual only) and a "Save chart as PNG"
    button (saves the current figure as a PNG via the file dialog).
    These mirror the right-hand controls panel in the reference
    screenshot (units, compare, checkbox, save button).
    Both panels — the chart and the controls — use the same panel
    background as the value cards (Item 7), so they pop out over
    the main view. The chart's data, axes, legend and title do not
    change; the controls only change what the chart shows and let
    the owner save it. The Watchlist stays full-width below this
    row.

## Guardrails

- Build only these ten items. Page content moves, it does not
  change.
- No new pages, no new menus, no new settings, no persistence for
  the collapsed state, no logo.
- The only numeric layout/font literals added or changed are the
  ones this prompt names (sidebar 170, FS_BODY 10, FS_HEAD 14,
  FS_TABLE_HEAD 10, chart figsize height 2.5). No other size
  changes. The card and panel backgrounds are theme-aware shades,
  not hardcoded colors.
- The Refresh button keeps the same refresh and auto-log behaviour;
  the only change is where it lives.
- The status bar keeps the same text; only its width changes.
- The card values stay FS_TITLE (18) — the owner's call, not a gap.
  The Total net worth is now small gray header text (Item 9), not
  a headline.
- The blue accent for interactive controls is already in place
  (selected nav, buttons, dropdowns); do not recolor anything else.
- The chart controls (Item 10) are the only new controls: a
  show/hide toggle for the Standard line and a save-as-PNG button.
  No other new controls.

## Verification

- Full committed suite passes, plus NEW committed tests:
  (a) the status subtitle stretches full-width (its container
      expands and the widget fills "x" across the main view);
  (b) a "Refresh stocks" button exists in the sidebar above the
      Settings button, and no "Refresh stocks" button exists in any
      page header;
  (c) the sidebar bottom order is Appearance menu, UI scaling menu,
      Refresh stocks button, Settings button (top to bottom);
  (d) `FS_BODY` reads 10, `FS_HEAD` reads 14, `FS_TABLE_HEAD` reads
      10, while `TITLE_FONT_SIZE` reads 26, `VALUE_FONT_SIZE` reads
      20 and `FS_SMALL` reads 11;
  (e) the literal "All pages, one sidebar" does not appear in the
      app;
  (f) `SIDEBAR_WIDTH` reads 170 and all ten nav names fit without
      clipping;
  (g) a collapse control exists; collapsing hides the sidebar and
      the main view takes the full width; expanding brings the
      sidebar back and the current page is kept;
  (h) each value card carries an explicit background that differs
      from the main view background in both Dark and Light mode
      (the card frames are visibly distinct boxes, not the default
      frame color blending into the view);
  (i) the chart block and the Watchlist block carry the same panel
      background as the value cards (one consistent panel color for
      all three blocks on the Overview);
  (j) on the Overview the header title line carries a small gray
      Total net worth subtitle (FS_SMALL + CLR_SECONDARY) to the
      right of "Overview", and the big "Total net worth" headline
      line is gone from the Overview content; on other pages the
      header title has no net worth subtitle;
  (k) the Overview chart figure height reads 2.5 (figsize (10,
      2.5)), the chart sits in the left column of a two-column row
      with a controls panel on the right, both on the panel
      background, and the controls panel holds a "Show standard"
      checkbox and a "Save chart as PNG" button.
- Headless probe: open the app; the status bar is a full-width bar
  under the page title; switch to Holdings and press Refresh stocks
  in the sidebar (it works from a non-Overview page and logs today's
  drift row); the sidebar bottom reads Dark, 100%, Refresh stocks,
  Settings top to bottom; collapse the sidebar and confirm a wide
  table fits at ~960px with no horizontal scrollbar, then expand and
  confirm the sidebar returns; body/headings/table headers read
  smaller than before; the four Overview cards are visible boxes
  (their background contrasts with the main view) in Dark mode, and
  switch to Light and confirm they still read as boxes; the chart
  and the Watchlist sit on the same panel background as the cards,
  so the Overview reads as a set of panels; the header reads
  "Overview" with the Total net worth in small gray text beside it
  and the cards sit right below the header area; the chart is a
  compact panel about half as tall as before with a controls panel
  on its right (Show standard checkbox + Save chart as PNG button),
  both popping out over the background; unchecking Show standard
  redraws with Actual only. Manual GUI check is the owner's step.
