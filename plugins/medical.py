"""Medical plugin (base version): project Medi-Cal income from its
components and plug the projected "other" total into the Overview.

Scope is deliberately narrow: the user projects expected income per
component; the plugin computes the projected "other" total and the
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
PLUGIN_TITLE = "Medical"
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
    """Projected total income: projected "other" + projected gains."""
    state = state or {}
    return projected_other(state) + parse_amount(state.get("gains", ""))


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


def _update_from_entries(app, entries, msg):
    """Read the five fields, validate, persist the projection, plug it
    into the Overview (enabled only — this tab exists only then), and
    refresh through the normal profile-save + recompute path."""
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
    app.commit_profile(
        "Projection updated — Overview reflects the projected total "
        "(other %s, total income %s)." % (pc.fmt_usd(other),
                                          pc.fmt_usd(total)))


def build(app, parent):
    """Render the Medical sub-tab. Idempotent: the core clears `parent`
    before calling it, so this renders fresh from saved state every time."""
    st = _state(app)
    try:
        other = projected_other(st)
        total = projected_total(st)
        computed_ok = True
    except ValueError:
        other = total = 0.0
        computed_ok = False
    ctk.CTkLabel(parent, text="Medical — projected income (base)",
                 font=ctk.CTkFont(size=20, weight="bold")).pack(
                     anchor="w", padx=8, pady=(8, 2))
    app_note = ("The Overview uses this projection "
                "(income marked projected there)."
                if st.get("applied") else
                "Not applied — press Update projection to plug it in.")
    ctk.CTkLabel(parent, text="Project expected (not actual) annual income "
                              "per component. " + app_note,
                 wraplength=860, anchor="w").pack(
                     anchor="w", padx=8, pady=(0, 4))
    entries = {}
    for key, label in FIELDS:
        ctk.CTkLabel(parent, text=label).pack(anchor="w", padx=8,
                                              pady=(6, 0))
        ent = ctk.CTkEntry(parent, width=200)
        ent.insert(0, "" if st.get(key) is None else str(st.get(key)))
        ent.pack(anchor="w", padx=8, pady=2)
        entries[key] = ent
    totals = ("Projected other (W-2 + pension + interest + dividends): "
              "%s\nProjected total income (other + gains): %s" % (
                  pc.fmt_usd(other), pc.fmt_usd(total)) if computed_ok
              else "Saved values are not numbers — fix them and press "
                   "Update projection.")
    ctk.CTkLabel(parent, text=totals, wraplength=860,
                 anchor="w").pack(anchor="w", padx=8, pady=(8, 2))
    ctk.CTkLabel(parent, text="Projected gains are shown for the "
                              "forward-looking picture only — the core's "
                              "actual realized gains (Tax Harvest tab) "
                              "stay the source of truth.",
                 wraplength=860, anchor="w",
                 text_color="gray").pack(anchor="w", padx=8, pady=(0, 4))
    msg = ctk.CTkLabel(parent, text="", text_color="orange",
                       wraplength=860, anchor="w")
    msg.pack(anchor="w", padx=8, pady=4)
    ctk.CTkButton(parent, text="Update projection", width=200,
                  command=lambda: _update_from_entries(
                      app, entries, msg)).pack(anchor="w", padx=8, pady=4)
