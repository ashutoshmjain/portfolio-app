"""Medi-Cal plugin (base version): project Medi-Cal income from its
components and plug the projected "other" total into the Overview.

The question this screen answers is "Do you qualify for Medi-Cal?" —
the verdict is computed from the projection against the MAGI ceiling
setting. Scope is deliberately narrow: the user projects expected income
per component; the plugin computes the projected "other" total and the
projected total income, and (while the plugin is enabled) writes the
projected "other" into the existing `other_annual_income` field through
the normal profile-save + recompute path, so the core's MAGI, gains cap,
and headroom reflect the component-based projection. The previous manual
lump is stashed in this plugin's own state and restored on deactivation.

NOT in this version: the submission-letter feature (document upload,
actual computation, creating the letter), the verification checklist,
and Capital Gains Forms (a separate later plugin). The projected capital
gains figure is shown for the forward-looking picture only — the core's
actual realized gains (lots + other_realized_gains_current_year, visible
in Tax Harvest) stay the source of truth and are never overwritten.
"""

import customtkinter as ctk

import portfolio_calc as pc

PLUGIN_ID = "medical"
PLUGIN_TITLE = "Medi-Cal"
PLUGIN_DESC = ("Project Medi-Cal income from its components; the "
               "projected total plugs into the Overview.")

# (state key, label shown next to the field). All annual, all projected
# (expected income, not actuals).
FIELDS = (("w2", "W-2 wages (projected annual)"),
          ("pension", "Pension (projected annual)"),
          ("interest", "Interest (projected annual)"),
          ("dividends", "Dividends (projected annual)"),
          ("gains", "Capital gains (projected annual)"))

# Components feeding "other" (everything but gains) vs gains itself.
OTHER_KEYS = ("w2", "pension", "interest", "dividends")

DEFAULT_STATE = {"enabled": False,
                 "w2": "", "pension": "", "interest": "",
                 "dividends": "", "gains": "",
                 "manual_other_annual_income": None,
                 "applied": False}


def parse_amount(raw):
    """A component field value as a number. Blank means nothing expected
    (0.0); anything non-numeric raises ValueError for the UI to report."""
    s = "" if raw is None else str(raw).strip().replace(",", ""
                                                         ).replace("$", "")
    if not s:
        return 0.0
    return float(s)


def projected_other(state):
    """Projected "other" annual income: W-2 + pension + interest +
    dividends (NOT gains)."""
    state = state or {}
    return sum(parse_amount(state.get(k, "")) for k in OTHER_KEYS)


def projected_total(state):
    """Projected total income (the projected MAGI): projected "other" +
    projected gains."""
    state = state or {}
    return projected_other(state) + parse_amount(state.get("gains", ""))


def qualifies(total, ceiling):
    """Qualification verdict inputs: True (qualifies) / False (does
    not) / None (no ceiling set, verdict undeterminable). One shared
    helper so the sub-tab verdict and the Overview line cannot drift
    apart."""
    if ceiling is None:
        return None
    return total <= ceiling


def verdict_text(total, ceiling):
    """The qualification verdict from the projection. Headless-pure:
    the sub-tab and the Overview derive their wording from this."""
    if qualifies(total, ceiling) is None:
        return "Set a MAGI ceiling in Settings to see the verdict."
    if qualifies(total, ceiling):
        return "You appear to qualify for Medi-Cal."
    return "You do not qualify for Medi-Cal. Check with your tax professional."


def totals_text(state):
    """The two totals lines as rendered under the fields. Raises
    ValueError when saved values are not numeric (the caller shows the
    fix-it text instead)."""
    return ("Projected other (W-2 + pension + interest + dividends): "
            "%s\nProjected total income (other + gains): %s"
            % (pc.fmt_usd(projected_other(state)),
               pc.fmt_usd(projected_total(state))))


def _ceiling(profile):
    """The MAGI ceiling setting as a number, or None when unset/invalid
    (blank means no cap derived — never a hidden default)."""
    try:
        raw = profile.get("magi_ceiling_annual")
        return None if raw in (None, "") else float(raw)
    except (ValueError, TypeError):
        return None


def overview_verdict_line(profile):
    """Overview Medi-Cal bullet text, or None when the plugin is not
    activated (enabled + applied). States the qualification verdict from
    the projection — never just the MAGI numbers."""
    st = (profile.get("plugins") or {}).get(PLUGIN_ID) or {}
    if not (st.get("enabled") and st.get("applied")):
        return None
    try:
        total = projected_total(st)
    except ValueError:
        return ("Medi-Cal: saved projection is not numeric — open the "
                "Medi-Cal tab and press Update projection.")
    ceiling = _ceiling(profile)
    if ceiling is None:
        return ("Medi-Cal: set a MAGI ceiling in Settings to see the "
                "qualification verdict.")
    if qualifies(total, ceiling):
        return ("Medi-Cal: qualified for Medi-Cal (projected MAGI %s "
                "vs %s ceiling)." % (pc.fmt_usd(total),
                                     pc.fmt_usd(ceiling)))
    return ("Medi-Cal: not qualified for Medi-Cal (projected MAGI %s "
            "vs %s ceiling) — check with your tax professional."
            % (pc.fmt_usd(total), pc.fmt_usd(ceiling)))


def card_figures(profile):
    """Overview value-card inputs, or None when the plugin is not
    activated (same gating as the verdict bullet: enabled + applied).
    Derives straight from the projection and the ceiling setting — no
    sentence parsing. {"qualified", "magi", "ceiling"}; magi None when
    the saved projection is not numeric."""
    st = (profile.get("plugins") or {}).get(PLUGIN_ID) or {}
    if not (st.get("enabled") and st.get("applied")):
        return None
    try:
        total = projected_total(st)
    except ValueError:
        return {"qualified": None, "magi": None, "ceiling": _ceiling(profile)}
    ceiling = _ceiling(profile)
    return {"qualified": qualifies(total, ceiling), "magi": total,
            "ceiling": ceiling}


def _state(app):
    """This plugin's namespaced state dict, seeded from DEFAULT_STATE on
    first use (user values are never overwritten by the seed)."""
    plugins = app.profile.setdefault("plugins", {})
    st = plugins.setdefault(PLUGIN_ID, {})
    for key, val in DEFAULT_STATE.items():
        st.setdefault(key, val)
    return st


def on_enabled(app, enabled):
    """Enable/disable transition (called by Settings save, before the
    profile is persisted). On enable: stash the manual
    `other_annual_income`, then plug in the projected "other". On
    disable: restore the stashed manual value. Profile persistence and
    the recompute + rebuild that follow happen in the core's normal
    Settings-save path."""
    st = _state(app)
    if enabled:
        if "manual_other_annual_income" not in st \
                or st.get("manual_other_annual_income") is None:
            try:
                st["manual_other_annual_income"] = float(
                    app.profile.get("other_annual_income", 0) or 0)
            except (ValueError, TypeError):
                st["manual_other_annual_income"] = 0.0
        try:
            app.profile["other_annual_income"] = projected_other(st)
        except ValueError:
            app.profile["other_annual_income"] = 0.0
        st["applied"] = True
    else:
        manual = st.pop("manual_other_annual_income", None)
        if manual is not None:
            try:
                app.profile["other_annual_income"] = float(manual)
            except (ValueError, TypeError):
                app.profile["other_annual_income"] = 0.0
        st["applied"] = False


def _readout_texts(app):
    """Totals + verdict lines from the SAVED state and the ceiling
    setting (what the sub-tab must show — never stale)."""
    st = (app.profile.get("plugins") or {}).get(PLUGIN_ID) or {}
    try:
        totals = totals_text(st)
        verdict = verdict_text(projected_total(st),
                               _ceiling(app.profile))
    except ValueError:
        totals = ("Saved values are not numbers — fix them and press "
                  "Update projection.")
        verdict = totals
    return totals, verdict


def _refresh_readouts(app):
    """Refresh the totals + verdict labels in place (no sub-tab rebuild,
    so typed input keeps focus). Missing or dead widgets are a no-op."""
    ui = getattr(app, "_medical_ui", None) or {}
    totals_w = ui.get("totals")
    verdict_w = ui.get("verdict")
    if totals_w is None and verdict_w is None:
        return
    totals, verdict = _readout_texts(app)
    for w, text in ((totals_w, totals), (verdict_w, verdict)):
        if w is None:
            continue
        try:
            if not w.winfo_exists():
                continue
            w.configure(text=text)
        except Exception:  # noqa: BLE001 - readout refresh is display-only
            pass


def on_data_changed(app):
    """Framework steady-state hook: refresh the displayed totals and
    verdict whenever the core rebuilds (Update, Settings save, Refresh)
    without rebuilding the sub-tab — typed input keeps focus."""
    _refresh_readouts(app)


def _update_from_entries(app, entries, msg):
    """Read the five fields, validate, persist the projection, plug it
    into the Overview (enabled only — this tab exists only then), and
    refresh through the normal profile-save + recompute path. The totals
    and verdict labels refresh via on_data_changed during that rebuild;
    refresh them here too so the update holds even without a rebuild."""
    st = _state(app)
    try:
        for key, _label in FIELDS:
            st[key] = entries[key].get().strip()
        other = projected_other(st)  # validates everything at once
        total = projected_total(st)
    except ValueError:
        msg.configure(
            text="Projection not saved — amounts must be numbers "
                 "(blank = none expected).")
        return
    app.profile["other_annual_income"] = other
    st["applied"] = True
    _refresh_readouts(app)
    app.commit_profile(
        "Projection updated — Overview reflects the projected total "
        "(other %s, total income %s)." % (pc.fmt_usd(other),
                                          pc.fmt_usd(total)))


def build(app, parent):
    """Render the Medi-Cal sub-tab. Idempotent: the core clears `parent`
    before calling it, so this renders fresh from saved state every time.
    Widget refs for the totals/verdict refresh live on app._medical_ui."""
    # Deferred: the core imports this plugin at startup, so importing the
    # shared message widget + type scale at module top would be circular.
    from portfolio_app import FS_BODY, FS_HEAD, SelectableMsg
    st = _state(app)
    ceiling = _ceiling(app.profile)
    if ceiling is None:
        explainer = ("Medi-Cal is a California program that pays for "
                     "medical and dental care (Denti-Cal) for people "
                     "whose income (MAGI) is below the ceiling. Set the "
                     "MAGI ceiling in Settings to see the verdict.")
    else:
        explainer = ("Medi-Cal is a California program that pays for "
                     "medical and dental care (Denti-Cal) for people "
                     "whose income (MAGI) is below the ceiling (below %s "
                     "a year)." % pc.fmt_usd(ceiling))
    SelectableMsg(parent, text="Medi-Cal — projected income (base)",
                  font=ctk.CTkFont(size=FS_HEAD, weight="bold")).pack(
                      anchor="w", padx=8, pady=(8, 2), fill="x")
    SelectableMsg(parent, text=explainer,
                  anchor="w").pack(anchor="w", padx=8, pady=(0, 4),
                                   fill="x")
    SelectableMsg(parent, text="Project expected (not actual) annual income "
                               "per component. The Overview uses this "
                               "projection (income marked projected there)."
                               if st.get("applied") else
                               "Project expected (not actual) annual income "
                               "per component. Not applied — press Update "
                               "projection to plug it in.",
                  anchor="w").pack(anchor="w", padx=8, pady=(0, 4),
                                   fill="x")
    entries = {}
    for key, label in FIELDS:
        SelectableMsg(parent, text=label).pack(
            anchor="w", padx=8, pady=(6, 0), fill="x")
        ent = ctk.CTkEntry(parent, width=200)
        ent.insert(0, "" if st.get(key) is None else str(st.get(key)))
        ent.pack(anchor="w", padx=8, pady=2)
        entries[key] = ent
        if key == "gains":
            SelectableMsg(
                parent,
                text="Capital gains are the profit on a sale, not the "
                     "amount you sold. Example: selling $100,000 of stock "
                     "you bought for $100,000 gives $0 capital gains.",
                anchor="w",
                text_color="gray").pack(anchor="w", padx=8, pady=(0, 2),
                                        fill="x")
    totals, verdict = _readout_texts(app)
    totals_w = SelectableMsg(parent, text=totals,
                               anchor="w")
    totals_w.pack(anchor="w", padx=8, pady=(8, 2), fill="x")
    verdict_w = SelectableMsg(parent, text=verdict,
                              font=ctk.CTkFont(size=FS_BODY,
                                               weight="bold"),
                              anchor="w")
    verdict_w.pack(anchor="w", padx=8, pady=(0, 2), fill="x")
    app._medical_ui = {"totals": totals_w, "verdict": verdict_w}
    SelectableMsg(parent, text="Projected gains are shown for the "
                                 "forward-looking picture only — the core's "
                                 "actual realized gains (Tax Harvest tab) "
                                 "stay the source of truth.",
                  anchor="w",
                  text_color="gray").pack(anchor="w", padx=8, pady=(0, 4),
                                          fill="x")
    msg = SelectableMsg(parent, text="", text_color="orange",
                        anchor="w")
    msg.pack(anchor="w", padx=8, pady=4, fill="x")
    ctk.CTkButton(parent, text="Update projection", width=200,
                  command=lambda: _update_from_entries(
                      app, entries, msg)).pack(anchor="w", padx=8, pady=4)
