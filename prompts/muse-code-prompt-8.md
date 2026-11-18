# Prompt 8 — Plugin utilities (framework + Medical plugin, base) + the two Delta 6 fixes

Status: DRAFT — ready to close.

This prompt builds the plugin utilities framework with the Medical plugin as the first, base version, and folds in the two minor fixes from Prompt 7 Delta 6 (which is superseded by this prompt — do not build Delta 6 separately).

The Medical plugin in this prompt is the BASE version only: the user projects expected income, and when the plugin is activated the application computes the suggested total and plugs it into the Overview. The submission-letter feature (document upload, actual computation, creating the letter) is LATER, not in this prompt. The verification checklist is later too, as part of that submission feature. The Capital Gains Forms plugin is later (Phase 2).

## Item 1: Plugin utilities framework

**Where:** new `plugins/` directory at the repo root; the main tab bar (`portfolio_app.py`, the `CTkTabview` built around the Dashboard / Diversification / Tax Harvest / Data Entry tabs); the Settings dialog (`open_settings`); `profile.json`.

**Why:** retiree utilities (medical income, capital-gains forms) do not show up in portfolio apps, but they are a major source of retirees' headaches. They should be available to the people who need them and invisible to everyone else. Adding a utility must mean adding one file, not a core rewrite.

**Fix:** build the framework from the design in `prompts/plugin-utilities-design.md` (in this repo — read it first; the essentials are repeated here so this prompt is self-contained):
- Create `plugins/` with an empty `plugins/__init__.py`.
- Loader: at startup, scan `plugins/` for `*.py` (excluding `__init__.py` and files starting with `_`), import each module with `importlib.import_module` inside a try/except, and keep the ones that expose `PLUGIN_ID`, `PLUGIN_TITLE`, `PLUGIN_DESC`, and `build(app, parent)`. A module that fails to import, or lacks the interface, is skipped and noted in the console / status line. Imports happen lazily inside the try/except — never at module top-level — so a broken plugin cannot break startup.
- Plugin interface: `PLUGIN_ID` (stable string id), `PLUGIN_TITLE` (display name), `PLUGIN_DESC` (one line, shown in Settings), `build(app, parent)` (renders the plugin's UI into its sub-tab frame; receives the `App` instance), optional `on_data_changed(app)` (called after upload / refresh / recompute), optional `DEFAULT_STATE`. A plugin may read `app.lots`, `app.profile`, `app.prices`, `app.data` and may call `portfolio_calc` functions. It must NOT import `portfolio_app` (circular import) and must NOT write data files directly. `build()` must be idempotent — the core clears the parent before calling it, same as the core tabs.
- Utilities tab: a new main tab **Utilities** in the top tab bar (`self.tabs`), holding a nested `self.util_tabs = ctk.CTkTabview(...)` — the same pattern as `dash_tabs` (Dashboard sub-tabs) and `data_tabs` (Data Entry sub-tabs). One sub-tab per **enabled** plugin, titled with the plugin's title. If no plugin is enabled, the Utilities tab is hidden (the tab bar shows only the four core tabs). Enabling the first plugin makes it appear; disabling the last one hides it. Toggling rebuilds the tab bar.
- Settings: the Settings dialog gains a **Utilities** section listing each *discovered* plugin (title, one-line description, checkbox). Stored in `profile.json` under one key, namespaced by plugin id: `"plugins": {"medical": {"enabled": true, ...plugin state...}}`. Default for a fresh install: no plugin enabled (core only).
- Additive rule: the core is NOT refactored. The existing Medi-Cal logic (`spending_capacity`'s MAGI, gains cap, headroom; the Settings policy inputs; the Overview MAGI lines), the backup/restore, the upload, and the lot model stay exactly as they are. A plugin is additive: it reads the core's computed figures and may write back only into *existing* Settings fields through the normal profile-save + recompute path.
- Failure modes: a plugin that fails to import is skipped (noted, app starts normally). A plugin whose `build()` throws shows a plain error message in its sub-tab; other plugins and the core keep working. No sandboxing — plugins are the app's own code in the same repo, reviewed like the app.

**Tests:** the loader is tested for discovery and for graceful failure on a broken plugin (a module that raises on import, and a module missing the interface, must both be skipped without breaking startup). Each plugin's computations are tested without the GUI (stdlib unittest, same as the existing tests). The existing committed suite must keep passing.

**Verify:** pull main in the OneDrive clone, restart the app. With no plugin enabled, the tab bar shows only the four core tabs and there is no Utilities tab. Enable a plugin in Settings and the Utilities tab appears with that plugin's sub-tab. Disable it and the tab hides again. A deliberately broken plugin file (bad import) must not stop the app from starting.

## Item 2: Medical plugin, base version (project expected income; plug the computed total into the Overview)

**Where:** new file `plugins/medical.py`; the Utilities tab (Medical sub-tab); the Overview MAGI/headroom lines (Dashboard → Overview).

**Why:** the first utility. The user projects their expected income; when the plugin is activated, the application computes the suggested total and plugs it into the Overview. This replaces the lump "other annual income" estimate with a total computed from its named components. The submission-letter feature (document upload, actual computation, creating the letter) is LATER and is not in this prompt.

**Fix:**
- Plugin module `plugins/medical.py` with `PLUGIN_ID = "medical"`, title `"Medical"`, and a one-line description (Medi-Cal income projection).
- Inputs: projected / expected **annual** income, one simple number field per component — W-2, pension, interest, dividends, capital gains. Each field has a short label saying what it is and that it is a projection (expected income, not actuals).
- Compute: projected "other" = W-2 + pension + interest + dividends. Projected total income = projected "other" + projected capital gains. Show both computed totals in the plugin.
- Plug into the Overview, only when the plugin is activated (enabled in Settings): the plugin writes the projected "other" total into the existing `other_annual_income` field, through the normal profile-save + recompute path, so the Overview's MAGI and headroom reflect the component-based projection. Before overwriting it, the plugin saves the previous manual value in its own state (under `plugins.medical` in `profile.json`); when the plugin is deactivated, it restores that manual value. When the plugin is NOT activated, the Overview uses the manual lump `other_annual_income` and the actual realized gains (today's behavior, unchanged).
- The Overview must label the income as projected when the plugin is active (so a projection is never mistaken for the actual). A short "projected" note next to the MAGI/headroom lines is enough.
- The projected capital gains input is used in the plugin to show the projected total income (projected "other" + projected gains) inside the plugin, so the user sees the full forward-looking picture. It does NOT overwrite the core's realized gains — the core's actual realized gains (from lots plus `other_realized_gains_current_year`) remain the source of truth for gains and stay visible in the Tax Harvest tab. (Deliberate v1 boundary: plugging a projected gains figure into the Overview's MAGI would need a core hook, because realized gains are computed from lots; that is not in this prompt.)
- State: the plugin's inputs are stored in `profile.json` under `plugins.medical`, so they persist and are backed up with the rest of the profile.
- Widget conventions: same as the core (labels, copyable messages, `wraplength=860` for long lines, no horizontal overflow at ~960px split-screen).

**Tests:** the plugin's computation (projected "other" and projected total from the five inputs, including zeros and blanks) is tested without the GUI. The save/restore of the manual `other_annual_income` value on activation/deactivation is tested. The existing committed suite must keep passing.

**Verify:** pull main in the OneDrive clone, restart the app, enable Medical in Settings. The Utilities tab appears with a Medical sub-tab. Enter projected values for W-2, pension, interest, dividends, and capital gains; confirm the plugin shows the computed projected "other" total and the projected total income. Confirm the Overview's MAGI and headroom update to reflect the projected "other" total, and that the Overview labels the income as projected. Disable the plugin in Settings and confirm the Overview reverts to the manual lump value and the actual gains, and the Utilities tab hides. Re-enable it and confirm the projected inputs are still there (persisted).

## Item 3: Overview "Allowed spending" line is cut in split-screen (from Prompt 7 Delta 6, Issue 1)

**Where:** Dashboard → Overview tab, the "Allowed spending" line directly under "Total net worth". App state: any window at split-screen width (~960px). The user sent a screenshot on 2026-11-16: the line reads "·16; prices/home at last refresh): $201,337/yr before 65 (pool $1,409,356 ÷ 7 yrs) · $100,640/yr after 65 (IRAs $2,012,792 ÷" — the opening "Allowed spending (as of Nov " is cut on the left and the ending " 20; + Social Security = $110,640)." is cut on the right. It works fine in full screen. The "Realizable this year" line below it shows in full.

**Why (verified in the live code at commit eb7e212):** the "Allowed spending" line is a plain `ctk.CTkLabel` with NO `wraplength`, so it renders as one long line (~160 characters). In full screen the window is wide enough for the whole line; at ~960px split-screen it is wider than the view and the excess is clipped. The alert lines directly below it (`• Drift vs standard…`, `• Medi-Cal MAGI…`, etc.) are the same kind of label WITH `wraplength=860`, and they wrap and show in full in the same screenshot — these two labels are the only ones in the summary block missing it. The "Realizable this year" label has the same missing wrap; it happens to fit at 960px today (~95 characters, borderline) but will clip the same way at a slightly narrower width or with longer numbers.

**Fix:** add `wraplength=860` to the "Allowed spending" label and to the "Realizable this year" label — the same value the alert labels in the same block already use. The full text must be visible at every window width, including split-screen (~960px): the long line wraps to a second line instead of clipping. Do NOT change the text, the numbers, or the "Copy summary" string (the copied text keeps the same one-line-per-item layout). The short "Total net worth" line needs no change.

**Tests:** verify by inspection plus the manual check: open the Overview tab at full width and at ~960px split-screen width and confirm the "Allowed spending" line wraps to a second line with nothing cut on either side, and the "Realizable this year" line shows in full at both widths.

**Verify:** pull main in the OneDrive clone, restart the app, open Dashboard → Overview at full width and then snapped to split-screen (~960px). The "Allowed spending" line must wrap and show in full at both widths, with nothing cut on the left or the right; the "Realizable this year" line must also show in full at both widths.

## Item 4: the drift line shows the numbers but never says what drift IS (from Prompt 7 Delta 6, Issue 2)

**Where:** Dashboard → Overview tab, the "• Drift vs standard…" bullet in the summary, and the same line in the "Copy summary" text. The line currently reads "Drift vs standard: actual (7.5%) vs standard (2.1%); drift (5.4%)."

**Why:** the computation already matches the user's definition — drift is the year-to-date difference between the portfolio's actual return and the standard allocation's return. Verified in the live code (calc.py): `actual_ytd` = (TNW − Jan 1 baseline) / Jan 1 baseline; `standard_ytd` = the STANDARD 15:15:35:15:20 allocation's YTD return from year-start prices; `drift_pp` = actual_ytd − standard_ytd. On 2026-11-16 that is actual (7.5%) vs standard (2.1%), drift (5.4pp) — the portfolio is 5.4 points below the standard so far this year. But the line never says that, so a reader has to infer what "drift" means — and the parentheses (the app's negative format) make it harder to read. The definition belongs in the line itself.

**Fix:** restate the drift bullet so it defines drift in the user's words, and show the drift in percentage points (it is a difference of two returns, so points, not percent). The line becomes:
"Drift (year to date): the diff between how your portfolio is behaving and the standard allocation — actual (7.5%) vs standard (2.1%); drift (5.4pp)."
The numbers stay computed exactly as today (actual_ytd, standard_ytd, drift_pp from calc.py — no change to the computation, the baseline, or the standard weights); only the label text and the drift unit change. The "Copy summary" text carries the same line. The bullet keeps its `wraplength=860` so the longer line wraps instead of clipping.

**Tests:** verify by inspection plus the manual check: open the Overview tab and confirm the drift bullet reads with its definition and the drift in pp; confirm the "Copy summary" text carries the same line; confirm the numbers are unchanged from before this prompt (same actual, standard, and drift values for the same data).

**Verify:** pull main in the OneDrive clone, restart the app, open Dashboard → Overview and read the drift bullet — it must state the definition and show the drift in pp, with the same numbers as before. Copy the summary and confirm the same line is in the copied text.

## Deferred (explicitly NOT in this prompt)

- The submission-letter feature (document upload, actual computation, creating the letter) — later.
- The verification checklist — later, as part of the submission feature.
- The Capital Gains Forms plugin — later (Phase 2).
- Plugging a projected capital-gains figure into the Overview's MAGI — not in v1 (the core's realized gains are computed from lots and are the source of truth; that would need a core hook).

## Guardrails

- Build only the four items above. Do not rebuild earlier prompt/delta features, and do not change the staged-editing model, lot-key upsert semantics, the tab structure (except adding the Utilities tab this prompt specifies), the backup/restore, or the upload flow. Do not change the drift computation, the baseline, the standard weights, the spending numbers, or the chart — except the drift bullet text and unit in Item 4.
- Prompt 7 Delta 6 is superseded by this prompt (its two issues are Items 3 and 4 here). Do not build Delta 6 separately.
- Push to main, then stop. Do not launch the app, clone folders, or automate GUI testing. The user launch-checks it manually in `C:\Users\ashut\OneDrive\Desktop\github\portfolio-app` (pull main, start the app, enable Medical in Settings and check the Utilities tab + the projected Overview figures, open Overview at full width and at ~960px split-screen and confirm the two summary lines and the drift bullet show in full).
