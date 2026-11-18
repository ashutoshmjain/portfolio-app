# Prompt 9 — Overview summary alignment (landing page) + Medi-Cal plugin rework (the Medi-Cal question, verdict, gains note) + stale totals fix

Status: DRAFT — ready to close.

This prompt fixes the Overview summary alignment the user reported on the landing page, reworks the Medical plugin into the Medi-Cal question it is meant to answer, and fixes the plugin's totals not refreshing after Update. Prompt 8 is BUILT (005e1c4); this prompt builds on it.

## Item 1: Overview summary — the top lines are cut off (landing page)

**Where:** Dashboard → Overview tab, the summary block at the top. App state: any window, after a refresh / rebuild. The user sent a screenshot 2026-11-17 19:29 (Overview, "Prices refreshed 19:29 (3s)."): the visible summary starts mid-sentence with "$98,856/yr after 65 (IRAs $1,977,125 ÷ 20; + Social Security = $129,000)." — the "Total net worth" line and the first line of "Allowed spending" are NOT visible (cut off above the visible area). The "Realizable" line, the drift bullet, and the other bullets show in full.

**Why:** The Overview summary is the landing page — it must show every line fully and aligned. The summary lives in a CTkScrollableFrame (build_overview, app.py ~1558) and the Overview rebuild preserves the scroll position across rebuilds (_keep_scrolls / _snap_scrolls / _restore_scrolls). The wrapped "Allowed spending" label (wraplength=860, Prompt 8 Item 3) is now two lines tall. Diagnose the exact layout cause — whether the scroll position, the wrapped label's height, or the frame's scroll region — and fix it at the cause, not by hiding lines.

**Fix:** The Overview summary must show ALL its lines fully and left-aligned at the top of the view, with no line cut off: "Total net worth", the full "Allowed spending" line (both wrapped lines), "Realizable this year", and every bullet (drift, Medi-Cal when shown, headroom, AGI, missing-cost). No line may start mid-sentence. This must hold at full width and at ~960px split-screen, on first open and after a refresh/rebuild (the scroll position must not leave the top lines hidden after a rebuild).

**Tests:** verify by inspection that the summary labels are packed with the correct wraplength and that a rebuild leaves the top visible. The layout itself is verified manually (see Verify).

**Verify:** pull main in the OneDrive clone, restart the app, open Dashboard → Overview at full width and at ~960px split-screen. The "Total net worth" line and the full "Allowed spending" line (both lines) must be visible at the top, with nothing cut off. Press Refresh stocks (a rebuild) and confirm the top lines stay visible (the view does not land scrolled down with the top cut off). Screenshot both widths.

## Item 2: The plugin is "Medi-Cal", not "Medical"

**Where:** the Utilities tab (sub-tab title), the plugin heading, and every label that names the plugin. Currently the sub-tab reads "Medical" and the heading reads "Medical — projected income (base)".

**Why:** "Medical" is the generic word; the program is "Medi-Cal" (with the capital CAL). The plugin is about Medi-Cal eligibility, so it must be named Medi-Cal everywhere the user sees it, to distinguish it from ordinary medical care.

**Fix:** Change the DISPLAY title to "Medi-Cal" (sub-tab title, heading "Medi-Cal — projected income (base)", and any label that says "Medical"). The internal PLUGIN_ID stays "medical" — do not rename it; the saved state lives under profile["plugins"]["medical"], and renaming the id would orphan it. Update the README's Utilities/Medical mentions to "Medi-Cal" to match.

**Tests:** the loader test still finds the plugin under id "medical" with title "Medi-Cal"; assert the display title.

**Verify:** enable the plugin in Settings; the Utilities sub-tab reads "Medi-Cal" and the heading reads "Medi-Cal — projected income (base)".

## Item 3: Add the Medi-Cal explainer + the qualification verdict

**Where:** the Medi-Cal plugin sub-tab (plugins/medical.py build), below the heading and above the input fields.

**Why:** The question the screen answers is "Do you qualify for Medi-Cal?" The user must know what Medi-Cal is and whether their projected income qualifies. In the user's example (W-2 10000, pension 7200, interest 50, dividends 4000, gains 30000 → projected total $51,250 vs $25,000 ceiling), the answer is "not qualified" — and the screen must say so plainly, with a pointer to a tax professional.

**Fix:**
- Add an explainer line (wraplength=860) under the heading: "Medi-Cal is a California program that pays for medical and dental care (Denti-Cal) for people whose income (MAGI) is below the ceiling." The ceiling figure comes from the app's MAGI ceiling setting (profile["magi_ceiling"], default $25,000) — render the actual setting value (e.g., "below $25,000 a year"), not a hardcoded number, so it stays correct if the ceiling changes.
- Add a qualification verdict, computed from the projection: projected MAGI = projected "other" + projected gains (the projected total income). If projected MAGI ≤ MAGI ceiling → "You appear to qualify for Medi-Cal." If projected MAGI > MAGI ceiling → "You do not qualify for Medi-Cal. Check with your tax professional." The verdict is prominent (its own line, directly under the totals) and updates whenever the projection is updated (see Item 6 for the refresh fix). In the user's example ($51,250 vs $25,000) it must read "You do not qualify for Medi-Cal. Check with your tax professional."

**Tests:** the verdict logic is tested headless (projected total ≤ ceiling → qualify; > ceiling → not qualify, with the tax-professional pointer; the ceiling is read from the profile setting, not hardcoded).

**Verify:** enter the user's example (W-2 10000, pension 7200, interest 50, dividends 4000, gains 30000), press Update projection, and confirm the verdict reads "You do not qualify for Medi-Cal. Check with your tax professional." Enter a small projection (e.g., all zeros) and confirm it reads "You appear to qualify for Medi-Cal."

## Item 4: Capital gains means the profit, not the sale amount

**Where:** the "Capital gains (projected annual)" field on the Medi-Cal plugin sub-tab.

**Why:** A user can easily enter the total sale proceeds as "capital gains" and hugely overstate income. Capital gains are only the profit. The user's example: selling $100,000 of stock bought for $100,000 gives $0 capital gains.

**Fix:** Add a helper note directly under the capital gains field (wraplength=860, muted/gray like the existing gains note): "Capital gains are the profit on a sale, not the amount you sold. Example: selling $100,000 of stock you bought for $100,000 gives $0 capital gains." Keep the existing note that projected gains are display-only (the core's actual realized gains stay the source of truth).

**Tests:** none beyond the manual check (text only).

**Verify:** open the Medi-Cal sub-tab and confirm the note appears under the capital gains field with the $100,000 / $0 example.

## Item 5: The Overview Medi-Cal line appears only when the plugin is activated — and states the verdict

**Where:** Dashboard → Overview tab, the summary bullets (the "• Medi-Cal MAGI ..." line). Currently the Overview always shows "• Medi-Cal MAGI $13,219 of $25,000 ceiling: WITHIN by $11,781." (with a "(projected)" suffix when the plugin is active).

**Why:** The Medi-Cal question now lives in the plugin. The Overview should not carry its own Medical line by default; the line should appear only when the plugin is activated, and when it appears it should state the qualification verdict (not just the MAGI numbers).

**Fix:**
- When the Medi-Cal plugin is NOT activated, the Overview shows NO Medi-Cal line (remove the "• Medi-Cal MAGI ..." bullet from the default summary). The "Gains headroom" line stays — it is the gains-cap figure used for harvesting decisions; only the Medi-Cal MAGI line is gated.
- When the plugin IS activated, the Overview shows a Medi-Cal line that states the qualification verdict from the projection: if the projected MAGI ≤ ceiling → "Medi-Cal: qualified for Medi-Cal (projected MAGI $X vs $25,000 ceiling)." If the projected MAGI > ceiling → "Medi-Cal: not qualified for Medi-Cal (projected MAGI $X vs $25,000 ceiling) — check with your tax professional." The projected MAGI and ceiling figures come from the plugin's projection and the profile's ceiling setting. The "(projected)" suffix is no longer needed on this line (the line itself is the projection verdict) — drop it from the Medi-Cal line.
- The Copy summary carries the same Medi-Cal line (present only when the plugin is activated, with the same verdict text).

**Tests:** the verdict text is derived from the same headless function as Item 3; the Overview bullet is present only when the plugin is enabled+applied, and absent otherwise (test the gating condition headless where the summary is built from data).

**Verify:** with the plugin disabled, open the Overview and confirm there is NO Medi-Cal line. Enable the plugin, enter the user's example ($51,250 projected total), press Update, open the Overview and confirm the Medi-Cal line reads "not qualified for Medi-Cal" with the projected MAGI and ceiling. Copy the summary and confirm the same line is in the copied text.

## Item 6: The plugin's displayed totals must refresh after "Update projection"

**Where:** the Medi-Cal plugin sub-tab, the two totals lines ("Projected other ..." and "Projected total income ..."). The user sent a screenshot 2026-11-17 (Medi-Cal tab, W-2 10000, pension 7200, interest 50, dividends 4000, gains 30000, status bar "Projection updated — Overview reflects the projected total (other $21,250, total income $51,250)."): the two totals lines STILL show "-" (dash) even though the values are now $21,250 and $51,250.

**Why:** The totals are rendered once in build() from the saved state. After pressing "Update projection," the sub-tab is NOT rebuilt (the enabled set didn't change, so _sync_utility_tabs skips the rebuild) and the plugin has no on_data_changed refresh — so the displayed totals stay at their first-render value ("-" from the blank fields). The status bar updates (via commit_profile) but the in-tab totals do not. The user sees "-" next to filled-in fields, which contradicts the status bar.

**Fix:** After "Update projection" (and whenever the saved projection changes), the plugin's displayed "Projected other" and "Projected total income" must show the computed values ($21,250 and $51,250 in the example), not "-". Implement this via the plugin's on_data_changed hook (the framework's steady-state update path) or by refreshing the totals labels in place after Update — whichever fits the framework; do not rebuild the whole sub-tab on every Update (that would lose the user's typed input focus). The totals must also refresh when the verdict changes (Item 3).

**Tests:** headless test that the totals rendered from a state with values show the computed figures (not "-"), and that after an update the displayed totals match the new projection.

**Verify:** open the Medi-Cal sub-tab (blank fields, totals "-"), enter the user's example values, press Update projection, and confirm the two totals lines now read "$21,250" and "$51,250" (not "-"). Change a value and press Update again; confirm the totals update again.

## Item 7: Record the on_enabled hook in the design doc

**Where:** prompts/plugin-utilities-design.md (the plugin interface section).

**Why:** Prompt 8 added an on_enabled(app, enabled) hook for enable/disable transitions (the Medical plugin uses it to stash/restore the manual lump). The design doc doesn't name it, and the build report flagged it as a deviation. The design doc is the contract; it should name the hook so a future plugin author knows it exists.

**Fix:** In prompts/plugin-utilities-design.md, add on_enabled(app, enabled) to the plugin interface (optional hook, called by the Settings save when a plugin's enabled flag changes, before the profile is persisted). No code change. Note that PLUGIN_ID stays the stable id and the display title is separate (see Item 2).

**Tests:** none (doc only).

**Verify:** read the design doc and confirm the interface lists on_enabled.

## Backup — no change needed (assessment)

The Medi-Cal plugin's data (projected inputs, the stashed manual lump, the applied flag) lives in profile.json under plugins.medical. The backup already includes the whole profile (backup_now writes "profile": dict(self.profile) into the encrypted set), and restore merges it back (prof.update(data["profile"])). Delete-all resets the profile to defaults (plugins: {}), wiping it. So the Medi-Cal data is already backed up, restored, and wiped consistently with the rest of the profile — no backup code change in this prompt. (If a future plugin ever needs its own data file outside the profile, that is when backup needs a change.)

## Guardrails

- Build only the seven items above. Do not rebuild earlier prompt/delta features, and do not change the staged-editing model, lot-key upsert semantics, the tab structure (except the Medi-Cal display title), the backup/restore, or the upload flow. Do not change the drift computation, the spending numbers, or the charts — except the Overview summary lines in Items 1 and 5.
- Do not rename the plugin's internal id ("medical") — only the display title changes (Item 2). Do not hardcode the MAGI ceiling ($25,000) in the explainer or the verdict — read it from the profile setting.
- Push to main, then stop. Do not launch the app, clone folders, or automate GUI testing. The user launch-checks it manually in `C:\Users\ashut\OneDrive\Desktop\github\portfolio-app` (pull main, restart, enable Medi-Cal in Settings and check the sub-tab title + explainer + verdict + gains note + refreshed totals, open Overview at full width and at ~960px and confirm the summary shows in full with no line cut off and the Medi-Cal line gated as specified).
