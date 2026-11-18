# Plugin Utilities — Design

Status: APPROVED by the user 2026-11-17 — building as Prompt 8 (`muse-code-prompt-8.md`).

## 1. Why

Retiree headaches that no portfolio app covers: verifying income for Medi-Cal, reconciling the capital gains on tax forms against your own records. These are not popular features, but they are a major source of trouble for retirees. The app is a portfolio tracker; these are optional, specialized tools. They should be available to the people who need them and invisible to everyone else.

So: a small, explicit plugin system. One utility at a time, each selectable, no core rewrite.

## 2. Goals and non-goals

**Goals**
- Optional utilities, selectable per user (opt-in, not forced on).
- Adding a utility = adding one file, not a core rewrite.
- A broken utility cannot break the app.
- Utility state is backed up and restored with the rest of the data.
- The core stays a pure portfolio tracker.

**Non-goals**
- Third-party or untrusted plugins. This system organizes the app's own optional features (same repo, same review as the app). There is no sandboxing and no plugin marketplace.
- Plugins with their own data files.
- A utility that needs its own top-level tab or its own menu entry.

## 3. Where plugins live

A `plugins/` directory at the repo root, next to `portfolio_app.py` and `portfolio_calc.py`. Each plugin is one module:

- `plugins/__init__.py` (empty — marks the package)
- `plugins/medical.py` (first plugin)
- `plugins/capgains.py` (second plugin, later)

The core does NOT hardcode a list of plugins. It discovers them.

## 4. Discovery and loading

At startup the core scans `plugins/` for `*.py` (excluding `__init__.py` and files starting with `_`), imports each module with `importlib.import_module`, and keeps the ones that provide the plugin interface (§5).

- A module that fails to import, or lacks the interface, is skipped and noted in the console / status line. The app still starts.
- Imports happen lazily inside a try/except in the loader — never at module top-level — so a broken plugin cannot break startup.

## 5. The plugin interface (the contract)

Each plugin module exposes:

| Name | What it is |
|---|---|
| `PLUGIN_ID` | Stable string id, e.g. `"medical"`. Never changes once set. |
| `PLUGIN_TITLE` | Display name, e.g. `"Medical"`. Shown as the sub-tab title. |
| `PLUGIN_DESC` | One line, shown in Settings so the user knows what it does. |
| `build(app, parent)` | Renders the plugin's UI into `parent` (its sub-tab frame). Receives the `App` instance. |
| `on_data_changed(app)` *(optional)* | Called after upload / refresh / recompute so the plugin can refresh its display. |
| `on_enabled(app, enabled)` *(optional)* | Called by Settings save when the plugin's enabled flag changes, before the profile is persisted — for enable/disable transitions (e.g. stashing a manual value the plugin writes over, restoring it on disable). |
| `DEFAULT_STATE` *(optional)* | The plugin's initial state dict. |

`PLUGIN_ID` is the stable key (profile state, saved data) and never changes once set; `PLUGIN_TITLE` is display-only — renaming the title (e.g. "Medical" → "Medi-Cal") needs no state migration.

**What a plugin may do**
- Read `app.lots`, `app.profile`, `app.prices`, `app.data` (the computed dict).
- Call `portfolio_calc` functions for computations.
- Use the app's widget conventions: `CTkLabel`, `SelectableMsg`, `wraplength=860` for long lines, copyable messages, no horizontal overflow at ~960px.

**What a plugin may not do**
- Import `portfolio_app` (circular import). It receives the `App` instance as a parameter instead.
- Write data files directly. All persistence goes through the profile dict (§7) or the core's existing save functions. This keeps backup/restore correct.
- Add its own top-level tab or menu entry. It renders only inside the Utilities tab (§6).

`build()` must be idempotent: the core clears the parent before calling it (same `_clear` pattern the core tabs use), so it renders fresh on every rebuild.

## 6. UI: the Utilities tab

A new main tab **Utilities** in the top tab bar, alongside Dashboard / Diversification / Tax Harvest / Data Entry. Built the same way the existing tabs are built: `self.tabs` is a `CTkTabview`; the Utilities tab holds a nested `self.util_tabs = ctk.CTkTabview(...)`, exactly like `dash_tabs` (Dashboard sub-tabs) and `data_tabs` (Data Entry sub-tabs).

- One sub-tab per **enabled** plugin, titled with the plugin's title. The plugin's `build(app, parent)` renders into its sub-tab.
- If no plugin is enabled, the Utilities tab is hidden — the tab bar shows only the four core tabs. Enabling the first plugin makes it appear; disabling the last one hides it. Toggling rebuilds the tab bar (the app already rebuilds tabs on change).

## 7. Enabling and settings (how a user selects a utility)

The Settings dialog (`open_settings`) gains a **Utilities** section listing each *discovered* plugin: title, one-line description, and a checkbox. Checked = enabled.

Stored in `profile.json` under one key, namespaced by plugin id:

```json
"plugins": {
  "medical": {"enabled": true, "case_number": "2325231", "...": "..."},
  "capgains": {"enabled": false}
}
```

The `enabled` flag and the plugin's own state live together under its id.

Why `profile.json`: it is already in the encrypted backup set, so plugin state (enabled flags, case numbers, checklist state) is backed up and restored automatically. No new data files, no backup changes.

Default for a fresh install: no plugin enabled (core only). The user turns on what they need.

## 8. Data and the core (the additive rule)

**The core is NOT refactored.** The existing Medi-Cal logic — `spending_capacity`'s MAGI, gains cap, and headroom; the Settings policy inputs; the Overview MAGI lines — stays exactly as it is.

A plugin is **additive**: it reads the core's computed figures and adds a new capability on top. It may write back into the *existing* Settings fields (for example, the Medical plugin writes the computed "other annual income" total into the existing `other_annual_income` field, through the same profile-save + recompute path Settings uses, so the core's MAGI updates). It must not invent new core fields or change core computations.

If a plugin is disabled, the app works exactly as before (the user enters the lump figure manually, as today). Disabling a plugin never loses core data — only the plugin's own state is hidden (it stays in `profile.json` and comes back if re-enabled).

## 9. The Medical plugin (first instance)

The Medi-Cal income verification utility. What it does:

- **Income components breakdown.** W-2, CalPERS pension, interest, dividends, capital gains — each an input with a source-document note. Computes the "other annual income" total from the components and writes it to the existing Settings field, so the core's MAGI is computed from parts instead of a lump estimate.
- **MAGI and headroom display.** Reads the core's computed figures and shows the breakdown, so the total is transparent.
- **Verification checklist.** The documents to collect (pay stubs, CalPERS award letter, gains letter, Schwab statement, YTD interest/dividend summaries), each checkable. State stored in the plugin's profile namespace.
- **Capital gains letter generator.** Produces the letter text (date, source, amount, signed under penalty of perjury) ready to copy.
- **Renewal info.** Case number, due date, county, contact — stored in the plugin's state.

What it does NOT do: it does not submit anything, does not talk to the county, does not change the core's MAGI computation. It is a computation + checklist + letter aid.

This is the worked example that proves the framework. Its field-by-field spec is a separate build prompt.

## 10. The Capital Gains Forms plugin (second instance, later)

Verification of the capital gains figures on tax forms against the app's records. The user enters the totals from the 1099-B and Schedule D; the plugin compares them to the app's computed realized gains (from `realized_gains_year`) and flags any discrepancy — a sale the app doesn't have, a missing lot, a basis difference.

Why it fits the same framework: same shape — read the core's computed figures, add a comparison/checklist UI, store its own state (the entered form totals) in its profile namespace. No core changes. A second plugin is a new file plus the same interface, no framework changes.

## 11. Failure modes and safety

- A plugin that fails to import → skipped, noted, app starts normally.
- A plugin whose `build()` throws → its sub-tab shows a plain error message; other plugins and the core keep working.
- A plugin is code in the same repo (open source, reviewed like the app). No sandboxing, no third-party loading — this system organizes the app's own optional features, it does not run untrusted code.
- No new data files. No changes to backup/restore, upload, or the lot model.

## 12. Testing

- Each plugin gets its own test file under `tests/` (stdlib unittest, same as the existing tests). A plugin's computations (e.g. the Medical plugin's component sum and MAGI) are tested without the GUI. The loader is tested for discovery and for graceful failure on a broken plugin.
- The core's existing tests keep passing — the core is untouched by the framework except for the tab-bar and Settings additions, which the loader/build tests cover.

## 13. Rollout

- **Phase 1 — framework + Medical.** Add `plugins/`, the loader, the Utilities tab, the Settings section, and the Medical plugin. This is the first build. (The Medical plugin's full field spec is a separate prompt.)
- **Phase 2 — Capital Gains Forms.** Add `plugins/capgains.py` using the same interface. No framework changes.
- **Later — more utilities the same way**, one file each. If a utility outgrows the pattern (needs its own data file, or a top-level tab), that is a design discussion, not a silent expansion.

## 14. Decisions for the user

1. The additive rule: core untouched; a plugin writes back only to existing Settings fields. Confirm.
2. The Utilities tab is hidden when no plugin is enabled. Confirm.
3. Plugin state lives in `profile.json` under `plugins`. Confirm.
4. No sandboxing — plugins are the app's own code in the same repo. Confirm.
