#!/usr/bin/env python3
"""Portfolio Dashboard — Windows desktop app (CustomTkinter + matplotlib).

Local replacement for the Google Sheets portfolio dashboard. No Google
sign-in, no API quirks: positions live in portfolio.csv (one row per lot;
manage from the ☰ menu → Manage data), prices come from yfinance, the
daily close log is drift_log.csv.

Run on Windows:  python portfolio_app.py
Setup:           pip install -r requirements.txt

NEVER executes trades. Display only.
"""
import csv
import datetime
import gc
import json
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog
# NOTE: no messagebox anywhere — every dialog is the copyable custom
# modal (_confirm / _confirm3 rendering SelectableMsg), per the no-native-
# dialog rule. Do not reintroduce messagebox.

import customtkinter as ctk

import portfolio_calc as pc

HERE = os.path.dirname(os.path.abspath(__file__))
PORTFOLIO_CSV = os.path.join(HERE, "portfolio.csv")
PROFILE_JSON = os.path.join(HERE, "profile.json")
CACHE = os.path.join(HERE, "prices_cache.json")
DRIFT_LOG = os.path.join(HERE, "drift_log.csv")
# Account registry: accounts exist independent of lots (a staged or
# lot-less account is a registry entry). In the delete set, gitignored,
# listed in the README data-files list.
ACCOUNTS_JSON = os.path.join(HERE, "accounts.json")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

def _n(n, one, many=None):
    """Plain plurals for UI strings: '1 row' vs '3 rows' — no '(s)'."""
    return "%d %s" % (n, one if n == 1 else (many or one + "s"))


# ---- app-wide type scale: ONE place, not scattered per-widget values ----
# Retirement-planner audience skews older: body text >= 15px everywhere,
# headings a few px above body, bold table headers >= 15px. Widgets without
# an explicit font inherit FS_BODY via the theme default below, so buttons
# and entries are legible with no per-widget edits. NOTE: CTk sizes are
# pixels but tkinter renders points (px * 72/96), so these are chosen to
# land exactly: 16px -> 12pt -> 16px, 20px -> 15pt -> 20px,
# 24px -> 18pt -> 24px. Do NOT pick odd values — rounding would shave a
# pixel off the 15px minimum.
FS_BODY = 16          # body text minimum, everywhere
FS_HEAD = 20          # section headings (body + 4)
FS_TITLE = 24         # top headline numbers
FS_TABLE_HEAD = 16    # bold table headers
FS_SMALL = 13         # secondary hints only — never body text
# Secondary text on dark: light enough to read at body size (never tiny +
# dim). Body text itself is always the default light color, never this.
CLR_SECONDARY = "#C9C9C9"
ctk.ThemeManager.theme["CTkFont"]["size"] = FS_BODY
# Minimum canvas width (px) before a chart may lay out and draw. At cold
# start the canvas reports transient near-zero widths while the window is
# still being mapped; shrinking the figure to those widths and drawing is
# what collapsed the layout engine to zero (tight_layout warned first,
# constrained warned next). The figure keeps its creation size until the
# canvas reports a real width — floor is below every supported window
# (960px split-screen lands ~900px here).
_MIN_CHART_W = 600


BROKER_GUIDE = [
    {"field": "bank",
     "concept": "The institution itself.",
     "schwab": "The institution itself.",
     "vanguard": "The institution itself.",
     "example": "Schwab"},
    {"field": "account",
     "concept": "Which account holds the position.",
     "schwab": "Accounts → Positions → account selector at the top.",
     "vanguard": "My Dashboard → account selector.",
     "example": "Schwab living Trust"},
    {"field": "account_type",
     "concept": "Tax treatment, from the account's kind.",
     "schwab": "From the account's kind: “Roth IRA” / “Traditional IRA” in "
               "the name or account summary; a plain brokerage account is "
               "Taxable.",
     "vanguard": "From the account label: “Brokerage” = Taxable; "
                 "“Traditional IRA” / “Roth IRA” as labeled. Note: Vanguard "
                 "does not provide cost basis services for IRA accounts, so "
                 "blank IRA cost is expected, not an error.",
     "example": "Taxable"},
    {"field": "asset",
     "concept": "Ticker for stocks/ETFs/crypto, label otherwise.",
     "schwab": "Positions → Symbol column.",
     "vanguard": "Holdings → Symbol/Fund column.",
     "example": "VTI"},
    {"field": "shares",
     "concept": "Quantity held in this lot.",
     "schwab": "Positions → Quantity column.",
     "vanguard": "Holdings → Shares/Quantity column.",
     "example": "396"},
    {"field": "cost_per_share",
     "concept": "What one share cost. PER SHARE — not the lot total.",
     "schwab": "Positions → click the blue $ under Cost Basis → lot popup; "
               "or symbol → Lot Details → cost per lot. If only a lot total "
               "is shown, divide by the lot's quantity.",
     "vanguard": "My Dashboard → Portfolio → Cost basis → Unrealized → "
                 "“Show lot details” → cost per lot (mutual funds may show "
                 "average cost; use the lot cost when the method is "
                 "specific-ID).",
     "example": "210.50"},
    {"field": "acquired_date",
     "concept": "When this lot was bought (YYYY-MM-DD).",
     "schwab": "Same lot popup / Lot Details → “Open Date” per lot.",
     "vanguard": "Same lot detail → “Date acquired” per lot.",
     "example": "2021-06-14"},
    {"field": "sold_date",
     "concept": "When this lot was sold. Blank for open lots.",
     "schwab": "Accounts → History → Realized Gain/Loss → “Closed Date”.",
     "vanguard": "Cost basis → Realized gains & losses → sale/closed date.",
     "example": "2026-02-03"},
    {"field": "sale_price_per_share",
     "concept": "Proceeds PER SHARE. Goes with sold_date, always.",
     "schwab": "Realized Gain/Loss → Proceeds per lot ÷ quantity sold (if "
               "only total proceeds are shown).",
     "vanguard": "Realized view → Proceeds per lot ÷ quantity sold.",
     "example": "268.40"},
]

AI_TEMPLATE_PROMPT = """Fill this CSV template from these broker screenshots. One row per LOT (not per position — one asset can have several rows with different dates/costs).

Columns (keep this exact header row):
bank,account,account_type,asset,shares,cost_per_share,acquired_date,sold_date,sale_price_per_share

Rules:
- account_type is one of: Traditional IRA, Roth IRA, Taxable, HSA, Cash.
- cost_per_share and sale_price_per_share are PER SHARE, not totals. If the broker shows only a lot total, divide by the lot's quantity.
- Dates are YYYY-MM-DD.
- Open lots (still held): leave sold_date and sale_price_per_share blank.
- Closed lots (sold): fill sold_date AND sale_price_per_share, always together.
- Cash / savings rows: asset CASH_USD, no cost or dates needed.
- Never combine two lots with different dates or costs into one row.
- If a value is not visible, leave it blank — never invent numbers.

Return ONLY the CSV, no explanation."""


def money(x):
    return pc.fmt_usd(x)


def pct(x):
    return pc.fmt_pct(x)


class SelectableMsg:
    """Message widget with real mouse selection — a drop-in for the message
    CTkLabels it replaces (.configure(text=...)/.pack/.grid/.winfo_exists
    compatible, plus .cget("text")).

    The standing copy rule covers every user-facing message: plain labels
    only copy via click+Ctrl+C, so dialog/popup/status messages use this
    borderless read-only text instead — drag to select, Ctrl+C to copy.
    Typing/paste/cut are blocked; navigation, selection and Control
    shortcuts stay live. A textvariable (status bar) is mirrored live.
    """

    def __init__(self, parent, text="", text_color=None, wraplength=None,
                 font=None, textvariable=None, wrap="word"):
        fg = {"orange": "orange", "red": "red"}.get(
            text_color, "#EDEDED" if text_color is None else text_color)
        tkfont = None
        if font is not None:
            try:
                tkfont = (font.cget("family"), font.cget("size"),
                          font.cget("weight"))
            except (tk.TclError, AttributeError, TypeError):
                tkfont = None
        self._box = tk.Text(parent, wrap=wrap, width=20, height=1,
                            relief="flat", borderwidth=0,
                            highlightthickness=0, bg="#2B2B2B", fg=fg,
                            cursor="xterm", font=tkfont or ("Roboto", -16),
                            spacing1=2, spacing3=4,
                            insertbackground="#EDEDED")
        self._text = ""
        self._var = textvariable
        if textvariable is not None:
            try:
                self._text = textvariable.get()
            except tk.TclError:
                pass
        if text:
            self._text = text
        if self._text:
            self._box.insert("1.0", self._text)
        self._fit_later()

        def _ro_key(e):
            if e.state & 0x4:  # Control held: copy, select-all, etc.
                return None
            if e.keysym in ("Left", "Right", "Up", "Down", "Home", "End",
                            "Prior", "Next"):
                return None
            return "break"

        self._box.bind("<KeyPress>", _ro_key, add="+")
        for _seq in ("<<Cut>>", "<<Paste>>"):
            self._box.bind(_seq, lambda e: "break", add="+")
        self._box.bind("<Configure>", lambda e: self._fit(), add="+")
        if textvariable is not None:
            try:
                textvariable.trace_add(
                    "write", lambda *a: self.set(textvariable.get()))
            except tk.TclError:
                pass

    def set(self, text):
        try:
            self._box.delete("1.0", "end")
            if text:
                self._box.insert("1.0", text)
            self._text = text or ""
            self._fit()
        except tk.TclError:
            pass

    def _fit(self):
        try:
            self._box.update_idletasks()
            if str(self._box.cget("wrap")) == "none":
                return
            n = self._box.count("1.0", "end", "displaylines")
            h = max(1, (n[0] if n else 1))
            if int(self._box.cget("height")) != h:
                self._box.configure(height=h)
        except tk.TclError:
            pass

    def _fit_later(self):
        try:
            self._box.after_idle(self._fit)
        except tk.TclError:
            pass

    def configure(self, cnf=None, **kw):
        if "text" in kw:
            self.set(kw.pop("text"))
        if "text_color" in kw:
            colour = kw.pop("text_color")
            kw["fg"] = {"orange": "orange", "red": "red"}.get(
                colour, "#EDEDED" if colour is None else colour)
        if not kw and cnf is None:
            return
        try:
            self._box.configure(cnf, **kw) if cnf else \
                self._box.configure(**kw)
        except tk.TclError:
            pass

    config = configure

    def cget(self, key):
        if key == "text":
            return self._text
        try:
            return self._box.cget(key)
        except tk.TclError:
            return None

    def __getattr__(self, name):
        # pack/grid/place/bind/winfo_exists/destroy/focus live on the box.
        return getattr(self.__dict__["_box"], name)


class Table(ctk.CTkFrame):
    """Simple grid table: header row bold, values as labels.

    A plain full-height frame, NOT a scrollable: tables render at their
    complete content height inside the view's single scroll region. One
    view = one scrollbar — nested scroll regions fought over mouse-wheel
    events and looked antiquated, so no table carries its own scrollbar.

    Every table carries a Copy button (header toolbar, above the grid so
    it never widens the columns): TSV to the clipboard, pasting straight
    into Excel, Sheets, or any AI chat. Ctrl+C with the table focused
    (click its Copy button first) copies the same TSV.
    """

    def __init__(self, master, headers, rows, col_widths=None, **kw):
        super().__init__(master, **kw)
        self.headers = list(headers)
        self._rows = [list(r) for r in rows]
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, columnspan=len(headers), sticky="e",
                 padx=4, pady=(2, 0))
        ctk.CTkButton(bar, text="Copy table", width=96,
                      command=self.copy_to_clipboard).pack(side="right")
        for j, h in enumerate(headers):
            lbl = ctk.CTkLabel(self, text=h, font=ctk.CTkFont(weight="bold"),
                               anchor="w")
            lbl.grid(row=1, column=j, padx=4, pady=3, sticky="w")
        for i, row in enumerate(rows, start=2):
            for j, val in enumerate(row):
                bold = str(val).startswith("**")
                text = str(val).replace("**", "")
                # House style: negative figures render red + parenthesized
                # (the parens come from the shared fmt_usd/fmt_pct/fmt_pp;
                # the red is applied here so every table inherits it).
                neg = pc.is_negative_figure(str(val))
                lbl = ctk.CTkLabel(
                    self, text=text,
                    font=ctk.CTkFont(weight="bold") if bold else None,
                    text_color="red" if neg else None,
                    anchor="w")
                lbl.grid(row=i, column=j, padx=4, pady=3, sticky="w")

    def copy_to_clipboard(self):
        lines = ["\t".join(str(h) for h in self.headers)]
        for row in self._rows:
            lines.append("\t".join(str(v).replace("**", "") for v in row))
        top = self.winfo_toplevel()
        try:
            top.clipboard_clear()
            top.clipboard_append("\n".join(lines))
            top.update()
        except tk.TclError:
            return False
        try:
            top.status_var.set(
                "Copied %s — paste into Excel, Sheets, or any AI."
                % _n(len(self._rows), "row"))
        except (tk.TclError, AttributeError):
            pass
        return True


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Portfolio Dashboard")
        self.geometry("1240x860")
        self.lots = pc.load_portfolio(PORTFOLIO_CSV)
        self.profile = pc.load_profile(PROFILE_JSON)
        self._migrate_watchlist()
        key_note = self._migrate_rentcast_key()
        self.accounts = pc.load_accounts(ACCOUNTS_JSON)
        self.positions = pc.positions_from_lots(self.lots)
        self.cost_basis = pc.cost_map_from_lots(self.lots)
        self.prices = pc.load_price_cache(CACHE)
        self.watch = pc.load_watchlist_cache(CACHE)
        self.home_value = pc.HOME_DEFAULT
        self._sync_home()
        self.data = None
        self.cov_lots = None
        # Live scroll regions by stable key (re-registered on every build;
        # _keep_scrolls snapshots/restores fractions across rebuilds).
        self._scroll_keep = {}
        # Refresh guard: one price fetch at a time — a second click while
        # the worker runs gets an instant "sit tight" instead of a
        # duplicate fetch piling onto a slow machine.
        self._refreshing = False
        self.status_var = tk.StringVar(value="Ready — open the ☰ menu.")
        if key_note:
            self.status_var.set(key_note)

        # ---- Top bar (slim: actions live in the hamburger menu so a
        # narrow split-screen window never chops them) ----
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(top, text="PORTFOLIO DASHBOARD",
                     font=ctk.CTkFont(size=FS_HEAD, weight="bold")).pack(
                         side="left", padx=8)
        self.date_lbl = ctk.CTkLabel(
            top, text="As of %s" % datetime.date.today().isoformat())
        self.date_lbl.pack(side="left", padx=8)
        ctk.CTkButton(top, text="☰", width=44,
                      command=self.toggle_menu).pack(side="right", padx=4)
        # Selectable so every status line copies — same rule as dialogs.
        self.status = SelectableMsg(top, textvariable=self.status_var,
                                    text_color="orange", wrap="none")
        self.status.pack(side="left", padx=8)
        # Refresh progress: hidden unless a price fetch is running. The
        # ticker count is known upfront, so this is determinate (k/N) —
        # on a slow machine the bar, not silence, answers "is it stuck?".
        self.refresh_bar = ctk.CTkProgressBar(top, width=120)
        self.refresh_bar.set(0)
        self.menu_win = None
        self.bind_all("<MouseWheel>", self._wheel_scroll, add="+")
        # Standard Windows copy: click any text to focus it, Ctrl+C copies.
        # Entries/text boxes keep native selection copy; labels copy their
        # text; anything inside a Table copies the whole table as TSV.
        self.bind_all("<Button-1>", self._focus_for_copy, add="+")
        self.bind_all("<Control-c>", self._copy_hotkey, add="+")

        # ---- Tabs ----
        # Top level: Dashboard, Diversification, Tax Harvest, Data Entry.
        # Dashboard holds Overview (landing), Accounts, Holdings, Liquidity,
        # Tax implications. Data Entry holds Inputs, Template, Danger Zone;
        # Settings lives under the hamburger menu (no Profile sub-tab).
        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=4)
        for name in ("Dashboard", "Diversification", "Tax Harvest",
                     "Data Entry"):
            self.tabs.add(name)
        self.dash_tabs = ctk.CTkTabview(self.tabs.tab("Dashboard"))
        self.dash_tabs.pack(fill="both", expand=True, padx=4, pady=4)
        for name in ("Overview", "Accounts", "Holdings", "Liquidity",
                     "Tax implications"):
            self.dash_tabs.add(name)
        self.data_tabs = ctk.CTkTabview(self.tabs.tab("Data Entry"))
        self.data_tabs.pack(fill="both", expand=True, padx=4, pady=4)
        for name in ("Inputs", "Template", "Danger Zone"):
            self.data_tabs.add(name)
        self.tabs.set("Dashboard")
        self.dash_tabs.set("Overview")
        self.frames = {}

        self.recompute()
        self.build_all()
        self.refresh_data_window()

    # ---- data ----
    def account_registry(self):
        """Ordered union: registry entries first, then any lots-only
        accounts (uploads can introduce accounts the registry never saw).
        The Accounts view renders exactly this — never a hardcoded list."""
        out = [dict(a) for a in self.accounts]
        seen = {(a.get("bank") or "", a.get("account") or "") for a in out}
        for lot in self.lots:
            key = (lot.get("bank") or "", lot.get("account") or "")
            if key[1] and key not in seen:
                seen.add(key)
                out.append({"bank": key[0], "account": key[1],
                            "account_type": lot.get("account_type") or ""})
        return out

    def _sync_registry(self, shells=()):
        """Grow the registry from the lots (+ staged shell accounts), save
        only when it changed. Never shrinks except delete-all."""
        have = {(a.get("bank") or "", a.get("account") or "")
                for a in self.accounts}
        changed = False
        for lot in self.lots:
            key = (lot.get("bank") or "", lot.get("account") or "")
            if key[1] and key not in have:
                have.add(key)
                self.accounts.append(
                    {"bank": key[0], "account": key[1],
                     "account_type": lot.get("account_type") or ""})
                changed = True
        for bank, acct, atype in shells:
            key = (bank or "", acct or "")
            if key[1] and key not in have:
                have.add(key)
                self.accounts.append({"bank": key[0], "account": key[1],
                                      "account_type": atype or ""})
                changed = True
        if changed:
            pc.save_accounts(ACCOUNTS_JSON, self.accounts)

    def registry_accounts_arg(self):
        return [(a.get("bank") or "", a.get("account") or "",
                 a.get("account_type") or "")
                for a in self.account_registry()]

    def recompute(self):
        self.positions = pc.positions_from_lots(self.lots)
        self.cost_basis = pc.cost_map_from_lots(self.lots)
        # Drift inputs derive per recompute: baseline from the drift log's
        # year-start row, year-start prices from the price cache (filled
        # once per year on Refresh). Nothing hardcoded, ever.
        year = datetime.date.today().year
        base = pc.year_baseline(pc.load_drift_log(DRIFT_LOG), year)
        start = pc.cached_year_start(CACHE, year)
        self.data = pc.compute(self.positions, self.prices, self.home_value,
                               self.cost_basis,
                               accounts=self.registry_accounts_arg(),
                               drift_start=start, drift_baseline=base)

    def save_lots(self, msg="Data saved."):
        # File + main views only. Data Entry refresh is explicit at each
        # call site (structural rebuild vs in-place repaint, F5).
        # Registry grows from the lots on every external commit.
        self._sync_registry()
        pc.save_portfolio(PORTFOLIO_CSV, self.lots)
        self.recompute()
        self.build_all()
        self.status_var.set(msg)

    def lots_changed_externally(self, msg="Data saved."):
        """Mutations from outside the grid (forms, uploads, type edits):
        commit, then rebuild the grid (scroll preserved)."""
        self.save_lots(msg)
        if getattr(self, "cov_lots", None) is not None:
            self._cov_reset()
        self.refresh_data_window()

    def _snap_scrolls(self, names):
        """Fractions for the named scroll regions (registry holds the live
        widgets). Fractions — not widget refs — survive the rebuild."""
        snapped = {}
        for name in names:
            w = self._scroll_keep.get(name)
            if w is None:
                continue
            try:
                if not w.winfo_exists():
                    continue
            except (tk.TclError, AttributeError):
                continue
            try:
                if isinstance(w, ctk.CTkScrollableFrame):
                    snapped[name] = w._parent_canvas.yview()
                else:  # guide textbox
                    snapped[name] = w.yview()
            except (tk.TclError, AttributeError):
                pass
        return snapped

    def _restore_scrolls(self, snapped):
        for name, y in snapped.items():
            w = self._scroll_keep.get(name)
            if w is None:
                continue
            try:
                if isinstance(w, ctk.CTkScrollableFrame):
                    w._parent_canvas.yview_moveto(y[0])
                else:
                    w.yview_moveto(y[0])
            except (tk.TclError, AttributeError, TypeError):
                pass

    def _keep_scrolls(self, fn, names):
        # Every edit-triggered rebuild preserves scroll position: snapshot
        # the fractions, rebuild (widgets are recreated and re-registered),
        # restore on the new widgets. Views never jump to the top after an
        # add, remove, delete, or edit.
        snapped = self._snap_scrolls(names)
        fn()
        self._restore_scrolls(snapped)

    def _cov_keep_scroll(self, fn):
        self._keep_scrolls(fn, ("coverage",))

    def _migrate_watchlist(self):
        # One-time fold of the legacy flat watchlist_custom into a named
        # user class, so existing custom tickers survive the grouping.
        legacy = [str(t).strip().upper()
                  for t in (self.profile.get("watchlist_custom") or [])]
        legacy = [t for t in legacy if t]
        if not legacy:
            return
        classes = dict(self.profile.get("watchlist_classes") or {})
        mine = list(classes.get("My watchlist", []))
        for t in legacy:
            if t not in mine:
                mine.append(t)
        classes["My watchlist"] = mine
        self.profile["watchlist_classes"] = classes
        self.profile["watchlist_custom"] = []
        pc.save_profile(PROFILE_JSON, self.profile)

    def _check_settings_data(self, data):
        """Validate an imported settings file. Returns an error string, or
        None when the file is safe to apply. Unknown keys are ignored
        (forward compatibility); structural and numeric fields are checked
        so a bad file applies nothing — never a partial apply."""
        if not isinstance(data, dict):
            return "Not a settings file (a JSON object is expected)"
        for key in ("properties", "watchlist_custom"):
            if key in data and not isinstance(data[key], list):
                return "'%s' must be a list" % key
        if "watchlist_classes" in data and \
                not isinstance(data["watchlist_classes"], dict):
            return "'watchlist_classes' must be an object"
        if "watchlist_names" in data and \
                not isinstance(data["watchlist_names"], dict):
            return "'watchlist_names' must be an object"
        if "rentcast_key" in data and \
                not isinstance(data["rentcast_key"], str):
            return "'rentcast_key' must be text"
        for key in ("ss_owner_monthly", "ss_spouse_monthly",
                    "other_realized_gains_current_year",
                    "other_annual_income",
                    "private_insurance_per_person_mo"):
            if key in data:
                try:
                    float(data[key] or 0)
                except (TypeError, ValueError):
                    return "'%s' must be a number" % key
        # Legacy key: the entered cap is gone (now derived), but old
        # files/backups may still carry it — still validated, still
        # ignored everywhere else.
        if "annual_net_gains_cap" in data and \
                data["annual_net_gains_cap"] not in (None, ""):
            try:
                if float(data["annual_net_gains_cap"]) < 0:
                    raise ValueError
            except (TypeError, ValueError):
                return "'annual_net_gains_cap' must be blank or a number"
        for key in ("magi_ceiling_annual", "after65_agi_threshold"):
            if key in data and data[key] not in (None, ""):
                try:
                    float(data[key])
                except (TypeError, ValueError):
                    return "'%s' must be blank or a number" % key
        if "employer_medical_cover" in data and \
                not isinstance(data["employer_medical_cover"], bool):
            return "'employer_medical_cover' must be true/false"
        if "home_purchase_price" in data and data["home_purchase_price"] \
                not in (None, ""):
            try:
                float(data["home_purchase_price"])
            except (TypeError, ValueError):
                return "'home_purchase_price' must be blank or a number"
        return None

    def watch_classes(self):
        """Ordered [(class name, [tickers])]: the fixed standard classes
        from code, then user-defined classes from profile.json."""
        out = [(c, list(pc.WATCHLIST_CLASSES[c]))
               for c in pc.WATCHLIST_CLASS_ORDER]
        for name, tickers in (
                self.profile.get("watchlist_classes") or {}).items():
            clean = [str(t).strip().upper() for t in (tickers or [])
                     if str(t).strip()]
            out.append((str(name), clean))
        return out

    def watch_tickers(self):
        """Flat fetch/duplicate-check set: standard members + every user
        class member (deduped, uppercase)."""
        out = []
        for _name, tickers in self.watch_classes():
            for t in tickers:
                if t not in out:
                    out.append(t)
        return out

    def _busy(self, text):
        # Instant ack before a blocking rebuild: status text + watch cursor,
        # painted NOW (update_idletasks) so a slow machine never sits on a
        # dead screen while build_all() grinds. Pair with _idle() in a
        # finally — text-only, no widgets, per the no-fancy-stuff rule.
        self.status_var.set(text)
        try:
            self.configure(cursor="watch")
        except tk.TclError:
            pass
        try:
            self.update_idletasks()
        except tk.TclError:
            pass

    def _idle(self):
        try:
            self.configure(cursor="")
        except tk.TclError:
            pass

    def refresh_async(self):
        # Fetch on a worker thread (network), deliver on the main thread.
        # NOTE: tkinter widgets — including after() — may only be touched
        # from the main thread (cross-thread after() raises RuntimeError and
        # silently kills the refresh), so the worker posts its result to a
        # queue and a main-thread poller picks it up. The worker also runs
        # with GC disabled: a collection there could finalize a tkinter
        # object, whose finalizer calls into Tk and deadlocks against the
        # main thread's Tcl loop (seen live: Font.__del__ inside a worker
        # yfinance import — yfinance is now imported once at startup).
        if self._refreshing:
            self.status_var.set("Already refreshing — sit tight, "
                                "prices are on their way.")
            return
        self._refreshing = True
        t0 = time.monotonic()
        try:
            self.configure(cursor="watch")
        except tk.TclError:
            pass
        tickers = sorted({p["ticker"] for p in self.positions
                          if p["ticker"] != "CASH_USD"})
        watch = self.watch_tickers()
        total = len(tickers) + len(watch)
        self.refresh_bar.pack(side="left", padx=8)
        self.refresh_bar.set(0)
        self.status_var.set("Fetching %d prices from Yahoo Finance…"
                            % total)
        box = queue.Queue()
        done = [0]
        clock = threading.Lock()

        def bump(_t=None):
            # Worker threads land here per ticker; the queue carries it
            # to the main thread — widgets are only touched in poll().
            with clock:
                done[0] += 1
                box.put(("progress", done[0], total))

        def work():
            gc.disable()
            try:
                try:
                    prices, errors, used_cache = pc.fetch_prices(
                        tickers, CACHE, on_done=bump)
                    # Year-start prices for the standard YTD, once per
                    # year, in this same fetch cycle — never backgrounded,
                    # never on start. Failures leave drift unknown.
                    try:
                        pc.ensure_year_start(
                            CACHE, datetime.date.today().year)
                    except Exception:  # noqa: BLE001 - drift stays unknown
                        pass
                    try:
                        wq, werr, _live = pc.fetch_watchlist(
                            watch, CACHE, on_done=bump)
                    except Exception as e:  # noqa: BLE001 - no crash
                        wq, werr = {}, ["watchlist: %s" % type(e).__name__]
                except Exception as e:  # noqa: BLE001 - never strand poll
                    prices, errors, used_cache = (
                        dict(self.prices),
                        ["refresh failed: %s" % type(e).__name__], True)
                    wq, werr = {}, []
                box.put((prices, errors, used_cache, wq, werr,
                         time.monotonic() - t0))
            finally:
                gc.enable()

        def poll():
            try:
                payload = box.get_nowait()
            except queue.Empty:
                self.after(150, poll)
                return
            if (isinstance(payload, tuple) and len(payload) == 3
                    and payload[0] == "progress"):
                _done, _total = payload[1], payload[2]
                try:
                    self.refresh_bar.set(
                        min(1.0, _done / _total) if _total else 0)
                except (tk.TclError, ValueError):
                    pass
                self.status_var.set("Fetching prices from Yahoo "
                                    "Finance… %d/%d" % (_done, _total))
                self.after(150, poll)
                return
            self._after_refresh(*payload)

        threading.Thread(target=work, daemon=True).start()
        self.after(150, poll)

    def _after_refresh(self, prices, errors, used_cache, watch_quotes=None,
                       watch_errors=None, elapsed=None):
        # Stand down first: the bar, cursor and guard reset even if the
        # rebuild below ever raised — Refresh must never wedge disabled.
        self._refreshing = False
        try:
            self.configure(cursor="")
        except tk.TclError:
            pass
        try:
            self.refresh_bar.pack_forget()
        except tk.TclError:
            pass
        self.prices = prices
        self.watch = pc.load_watchlist_cache(CACHE)
        if watch_quotes:
            for t, q in watch_quotes.items():
                if isinstance(q, dict) and (q.get("price") is not None
                                            or q.get("mcap") is not None):
                    self.watch[t] = q
        self.recompute()
        self.build_all()
        try:
            self._cov_refresh_chrome()
        except (tk.TclError, ValueError, AttributeError):
            pass
        timing = ("" if elapsed is None
                  else " (%ds)" % int(round(elapsed)))
        if errors:
            self.status_var.set("Price fetch partial%s — %s. "
                                "Stale tickers use last-known prices."
                                % (timing, "; ".join(errors[:3])))
        elif used_cache:
            self.status_var.set("Prices refreshed%s (some from cache)."
                                % timing)
        else:
            self.status_var.set("Prices refreshed %s%s."
                                % (datetime.datetime.now().strftime("%H:%M"),
                                   timing))
        if watch_errors:
            self.status_var.set(self.status_var.get()
                                + " Watchlist: %s."
                                % "; ".join(watch_errors[:2]))

    def log_close(self):
        d = self.data["drift"]
        if d["standard_total"] is None:
            self.status_var.set("Cannot log close — drift needs live "
                                "BTC/GLD/VTI/MSTR prices.")
            return
        msg = pc.append_close(DRIFT_LOG, self.data["liquid"], self.home_value,
                              d["today_total"], d["standard_total"])
        self.status_var.set(msg)
        self.build_diversification()

    # ---- hamburger menu: exactly three items ----
    def toggle_menu(self):
        """Open/close the ☰ popup: Refresh stocks, Refresh home estimates,
        Log, Settings. Data Entry is a tab now — no window opens from here."""
        if self.menu_win is not None and self.menu_win.winfo_exists():
            self._close_menu()
            return
        win = ctk.CTkToplevel(self)
        win.title("Actions")
        win.transient(self)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.geometry("+%d+%d" % (self.winfo_x() + self.winfo_width() - 320,
                                 self.winfo_y() + 60))
        ctk.CTkButton(win, text="Refresh stocks",
                      command=self.refresh_from_menu).pack(
                          padx=12, pady=(12, 4), fill="x")
        ctk.CTkButton(win, text="Refresh home estimates",
                      command=self.home_from_menu).pack(
                          padx=12, pady=4, fill="x")
        ctk.CTkButton(win, text="Log",
                      command=self.log_from_menu).pack(
                          padx=12, pady=4, fill="x")
        ctk.CTkButton(win, text="Settings",
                      command=self.settings_from_menu).pack(
                          padx=12, pady=(4, 12), fill="x")
        self.menu_win = win
        # CustomTkinter withdraws a new Toplevel on Windows while theming
        # its titlebar; re-show ours once that settles.
        win.after(50, self._show_menu)

    def _show_menu(self):
        if self.menu_win is not None and self.menu_win.winfo_exists():
            self.menu_win.deiconify()
            self.menu_win.lift()

    def _close_menu(self):
        if self.menu_win is not None and self.menu_win.winfo_exists():
            self.menu_win.destroy()
        self.menu_win = None

    def refresh_from_menu(self):
        self._close_menu()
        self.refresh_async()

    def log_from_menu(self):
        self._close_menu()
        self.log_close()

    def settings_from_menu(self):
        self._close_menu()
        self.open_settings()

    # ---- home value: Properties list + RentCast auto-estimates ----
    @staticmethod
    def _looks_like_address(value):
        # RentCast keys are opaque tokens: no spaces, no commas. A value
        # with either was typed into the wrong field (the Prompt-7
        # screenshot: the home address sitting in the key field).
        v = (value or "").strip()
        return bool(v) and ("," in v or any(ch.isspace() for ch in v))

    def _migrate_rentcast_key(self):
        """Heal keys saved before address-validation existed: an
        address-like stored key is the home address typed into the wrong
        field, and the server rejects it with 401. If no properties exist
        yet, move it to a property address (preserving the user's data and
        fixing Refresh in one stroke); otherwise clear it. Either way the
        401 cannot recur from this cause. Returns a status note or ""."""
        key = (self.profile.get("rentcast_key") or "").strip()
        if not self._looks_like_address(key):
            return ""
        if not self._properties():
            self.profile["properties"] = [{
                "address": key, "applied_value": 0.0,
                "last_estimate": None, "last_source": "",
                "last_asof": ""}]
            note = ("The saved RentCast key looked like a street address, "
                    "so it was moved to Properties as your home address — "
                    "paste the real key in Settings.")
        else:
            note = ("The saved RentCast key looked like a street address, "
                    "so it was cleared — paste the real key in Settings.")
        self.profile["rentcast_key"] = ""
        pc.save_profile(PROFILE_JSON, self.profile)
        return note

    def _properties(self):
        props = self.profile.get("properties") or []
        return [dict(p) for p in props if isinstance(p, dict)]

    def _home_total(self):
        total = 0.0
        for p in self._properties():
            try:
                total += float(p.get("applied_value") or 0)
            except (TypeError, ValueError):
                pass
        return total

    def _sync_home(self):
        # The applied value is what flows into Holdings, net worth and
        # drift. Session scalar stays the single source those views read.
        self.home_value = self._home_total()

    def _home_rows(self):
        """[(label, applied)] for Holdings: one row per property. The cell
        shows a short tag ("RE 1", "RE 2", …) so the row's numbers align
        under the column headers; the full address goes in the legend
        below the table (_home_legend)."""
        rows = []
        for i, p in enumerate(self._properties()):
            try:
                val = float(p.get("applied_value") or 0)
            except (TypeError, ValueError):
                val = 0.0
            rows.append(("RE %d" % (i + 1), val))
        return rows

    def _home_legend(self):
        """[(tag, address)] matching _home_rows, for the legend below the
        Holdings table."""
        return [("RE %d" % (i + 1),
                 (p.get("address") or "").strip() or "(no address)")
                for i, p in enumerate(self._properties())]

    def home_from_menu(self):
        self._close_menu()
        win = ctk.CTkToplevel(self)
        win.title("Refresh home estimates")
        win.transient(self)
        win.resizable(False, False)
        ctk.CTkLabel(win, text="Latest home value estimate:").pack(
            padx=12, pady=(12, 2), anchor="w")
        # Fetches per property and SHOWS the pulled value + source +
        # date — it never silently replaces anything. The user accepts the
        # pulled value or overwrites the applied value manually (e.g. after
        # checking Zillow or Redfin in the browser), then Save applies it.
        # RentCast is called ONLY here — never in the background, never on
        # app start.
        props = self._properties()
        if not props:
            ctk.CTkLabel(
                win, text="No properties yet — add one in Settings "
                          "(Properties), then Refresh.",
                wraplength=360, anchor="w").pack(padx=12, pady=12,
                                                anchor="w")
            ctk.CTkButton(win, text="Close",
                          command=win.destroy).pack(padx=12, pady=(0, 12),
                                                   fill="x")
            win.after(50, lambda: (win.deiconify(), win.lift())
                      if win.winfo_exists() else None)
            return
        key = (self.profile.get("rentcast_key") or "").strip()
        rows = []
        for p in props:
            box = ctk.CTkFrame(win, fg_color="transparent")
            box.pack(fill="x", padx=12, pady=4)
            ctk.CTkLabel(
                box, text=(p.get("address") or "(no address)").strip() or
                "(no address)",
                font=ctk.CTkFont(weight="bold"),
                wraplength=380, anchor="w").pack(anchor="w")
            line = ctk.CTkFrame(box, fg_color="transparent")
            line.pack(fill="x", pady=2)
            ctk.CTkLabel(line, text="Applied $").pack(side="left")
            applied = ctk.CTkEntry(line, width=140)
            try:
                cur = float(p.get("applied_value") or 0)
                if cur:
                    applied.insert(0, str(p.get("applied_value")))
            except (TypeError, ValueError):
                pass
            applied.pack(side="left", padx=4)
            use_btn = ctk.CTkButton(line, text="Use estimate", width=110,
                                    state="disabled")
            use_btn.pack(side="left", padx=4)
            pulled = SelectableMsg(box, text="Fetching…",
                                     text_color=CLR_SECONDARY)
            pulled.pack(anchor="w")
            rows.append({"prop": p, "applied": applied,
                         "use_btn": use_btn, "pulled": pulled,
                         "result": None})
        quota_lbl = SelectableMsg(win, text="",
                                    text_color=CLR_SECONDARY)
        quota_lbl.pack(padx=12, anchor="w")
        msg = SelectableMsg(win, text="", text_color="orange")
        msg.pack(padx=12, anchor="w")

        def finish(result_list):
            if not win.winfo_exists():
                return
            quota = ""
            for i, res in enumerate(result_list):
                rows[i]["result"] = res
                if res["error"] and res["price"] is None:
                    rows[i]["pulled"].configure(text=res["error"])
                else:
                    tail = (" — %s" % res["error"]) if res["error"] else ""
                    rows[i]["pulled"].configure(
                        text="RentCast: %s (as of %s)%s" % (
                            money(res["price"]), res["asof"], tail))
                    rows[i]["use_btn"].configure(
                        state="normal",
                        command=lambda r=rows[i]: (
                            r["applied"].delete(0, "end"),
                            r["applied"].insert(
                                0, str(r["result"]["price"]))))
                if res.get("quota"):
                    quota = res["quota"]
            if quota:
                quota_lbl.configure(text=quota)

        if not key:
            for r in rows:
                last = r["prop"].get("last_estimate")
                if last:
                    r["pulled"].configure(
                        text="Last: %s (%s, %s). Add your free RentCast "
                             "key in Settings, then Refresh for a live "
                             "estimate."
                             % (money(last), r["prop"].get("last_source")
                                or "?", r["prop"].get("last_asof") or "?"))
                else:
                    r["pulled"].configure(
                        text="No RentCast key — add your free Developer key "
                             "in Settings, then Refresh.")
            # The no-key state offers a direct path: no closing the popup,
            # opening the menu, and opening Settings by hand.
            ctk.CTkButton(win, text="Open Settings", width=150,
                          command=lambda: (win.destroy(),
                                           self.open_settings())).pack(
                                               padx=12, pady=(6, 2),
                                               anchor="w")
        else:
            snapshots = [(p.get("address") or "") for p in props]
            box_q = queue.Queue()

            def work():
                box_q.put([pc.fetch_rentcast_estimate(a, key)
                           for a in snapshots])

            threading.Thread(target=work, daemon=True).start()

            def poll():
                if not win.winfo_exists():
                    return
                try:
                    finish(box_q.get_nowait())
                except queue.Empty:
                    win.after(150, poll)

            win.after(150, poll)

        def save():
            new_props = []
            for r in rows:
                raw = r["applied"].get().strip().replace(",", "").replace(
                    "$", "")
                try:
                    applied = float(raw or 0)
                except ValueError:
                    msg.configure(text="Applied values must be numbers — "
                                       "nothing saved.")
                    return
                prop = dict(r["prop"])
                prop["applied_value"] = applied
                if r["result"] and r["result"]["price"] is not None:
                    prop["last_estimate"] = r["result"]["price"]
                    prop["last_source"] = r["result"]["source"]
                    prop["last_asof"] = r["result"]["asof"]
                new_props.append(prop)
            self._busy("Applying home values…")
            try:
                self.profile["properties"] = new_props
                pc.save_profile(PROFILE_JSON, self.profile)
                self._sync_home()
                self.recompute()
                self.build_all()
                self.refresh_data_window()
            finally:
                self._idle()
            win.destroy()
            self.status_var.set("Home updated to %s."
                                % money(self.home_value))

        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=(4, 12))
        ctk.CTkButton(bar, text="Save applies", width=130,
                      command=save).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bar, text="Cancel", width=110,
                      command=win.destroy).pack(side="left")
        win.after(50, lambda: (win.deiconify(), win.lift())
                  if win.winfo_exists() else None)

    # ---- builders ----
    def _clear(self, tab):
        frame = self.tabs.tab(tab)
        for w in frame.winfo_children():
            w.destroy()
        return frame

    def _clear_dash(self, tab):
        frame = self.dash_tabs.tab(tab)
        for w in frame.winfo_children():
            w.destroy()
        return frame

    def build_all(self):
        self._keep_scrolls(self._build_all_inner,
                           ("overview", "accounts", "holdings",
                            "liquidity", "taximplic", "diversification",
                            "tax"))

    def _build_all_inner(self):
        # Main views only — Data Entry refresh is explicit at each call
        # site (structural rebuild vs in-place repaint, fix 5).
        self.build_overview()
        self.build_accounts()
        self.build_holdings()
        self.build_liquidity()
        self.build_taximplic()
        self.build_diversification()
        self.build_tax()

    def _wheel_scroll(self, event):
        # Global wheel: scroll whichever CTkScrollableFrame sits under the
        # cursor, so scrolling works over entry fields too.
        try:
            target = self.winfo_containing(event.x_root, event.y_root)
        except tk.TclError:
            return
        # One notch = several rows (~5 units ≈ 90–120px): wheel must feel
        # as fast as dragging the scrollbar. Window-level binding runs for
        # every widget, so entries/buttons/rows never swallow the wheel.
        try:
            steps = event.delta // 120
        except (AttributeError, TypeError):
            steps = 0
        if not steps:
            steps = 1 if getattr(event, "delta", 0) > 0 else -1
        w = target
        while w is not None:
            if isinstance(w, (ctk.CTkTextbox, tk.Text)):
                try:
                    w.yview_scroll(-5 * steps, "units")
                except tk.TclError:
                    pass
                return "break"
            if isinstance(w, ctk.CTkScrollableFrame):
                # Nested scroll regions (a table inside a scrolling tab):
                # scroll the innermost one that still has room; when it is
                # already at its limit in this direction, fall through to
                # the outer region instead of swallowing the notch.
                try:
                    cv = w._parent_canvas
                    lo, hi = cv.yview()
                    at_top = lo <= 0.0 and steps > 0
                    at_bottom = hi >= 1.0 and steps < 0
                    if not (at_top or at_bottom):
                        cv.yview_scroll(-5 * steps, "units")
                        return "break"
                except (tk.TclError, AttributeError):
                    return "break"
            w = w.master

    def _focus_for_copy(self, event):
        # Clicking a readout label focuses it so Ctrl+C can copy it.
        # Buttons, entries and menus keep their native click behavior.
        # NOTE: CTkLabel is a frame wrapping an inner tk.Label — a click
        # can land on either, or on a wrapping container, so walk up to
        # the nearest label-with-text or Table before focusing.
        try:
            w = event.widget
        except AttributeError:
            return None
        # Destroyed widgets arrive as a path-name string, not a widget:
        # a string has no .master, so resolve it (or bail) instead of
        # raising AttributeError noise on stderr. Library-side CustomTk
        # scroll noise is not ours to fix — this guards only our walk.
        if isinstance(w, str):
            try:
                w = self.nametowidget(w)
            except (tk.TclError, KeyError, AttributeError):
                return None
        while w is not None and w is not self:
            if isinstance(w, Table):
                try:
                    w.focus_set()
                except tk.TclError:
                    pass
                break
            if isinstance(w, (ctk.CTkLabel, tk.Label)):
                try:
                    if w.cget("text"):
                        w.focus_set()
                except tk.TclError:
                    pass
                break
            w = w.master
        return None

    def _copy_hotkey(self, event=None):
        # Ctrl+C across the app. Native selection in entries/text boxes
        # wins (class binding already copied); otherwise copy the focused
        # label's text, or the enclosing Table as TSV. Plain-text
        # clipboard: pastes straight into Excel, Sheets, or any AI chat.
        try:
            w = self.focus_get()
        except tk.TclError:
            return None
        if w is not None:
            try:
                if w.selection_present():
                    return None
            except (tk.TclError, AttributeError):
                pass
            try:
                if w.tag_ranges("sel"):
                    return None
            except (tk.TclError, AttributeError):
                pass
            t = w
            while t is not None and t is not self:
                if isinstance(t, Table):
                    t.copy_to_clipboard()
                    return "break"
                if isinstance(t, (ctk.CTkLabel, tk.Label)):
                    try:
                        text = t.cget("text")
                    except tk.TclError:
                        text = ""
                    if text:
                        self._to_clipboard(text,
                                          "Copied text — paste anywhere.")
                        return "break"
                t = t.master
        return None

    def _to_clipboard(self, text, msg=None):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update()
        except tk.TclError:
            return False
        if msg:
            self.status_var.set(msg)
        return True

    def _tooltip(self, widget, text):
        """Hover tooltip for a widget (e.g. an `upload` cost cell)."""
        tip = {"win": None}

        def show(_e=None):
            if tip["win"] is not None:
                return
            try:
                x = widget.winfo_rootx() + 12
                y = widget.winfo_rooty() + widget.winfo_height() + 4
            except tk.TclError:
                return
            win = tk.Toplevel(self)
            win.wm_overrideredirect(True)
            win.wm_geometry("+%d+%d" % (x, y))
            tk.Label(win, text=text, bg="#3A3A3A", fg="#EDEDED",
                     relief="solid", borderwidth=1, wraplength=320,
                     justify="left").pack()
            tip["win"] = win

        def hide(_e=None):
            win, tip["win"] = tip["win"], None
            if win is not None:
                try:
                    win.destroy()
                except tk.TclError:
                    pass

        widget.bind("<Enter>", show, add="+")
        widget.bind("<Leave>", hide, add="+")

    def _selectable_note(self, parent, text, bg="#2B2B2B", **pack_kw):
        """Read-only, mouse-selectable text block (real selection + Ctrl+C).

        A borderless tk.Text that auto-heights to its wrapped lines and
        refits on resize. Typing/paste/cut are blocked; navigation,
        selection and Control shortcuts (copy, select-all) work.
        """
        # width=20: wrapping (not requested width) decides the layout, so
        # this block can never widen a split-screen interior itself.
        box = tk.Text(parent, wrap="word", width=20, height=2, relief="flat",
                      borderwidth=0, highlightthickness=0, bg=bg,
                      fg="#EDEDED", cursor="xterm",
                      font=("Roboto", -FS_BODY), spacing1=2, spacing3=4,
                      insertbackground="#EDEDED")
        box.insert("1.0", text)

        def _ro_key(e):
            if e.state & 0x4:  # Control held: copy, select-all, etc.
                return None
            if e.keysym in ("Left", "Right", "Up", "Down", "Home", "End",
                            "Prior", "Next"):
                return None
            return "break"

        box.bind("<KeyPress>", _ro_key, add="+")
        for seq in ("<<Cut>>", "<<Paste>>"):
            box.bind(seq, lambda e: "break", add="+")

        def _fit(_e=None):
            try:
                n = box.count("1.0", "end", "displaylines")
                h = max(1, (n[0] if n else 1))
                if int(box.cget("height")) != h:
                    box.configure(height=h)
            except tk.TclError:
                pass

        box.bind("<Configure>", _fit, add="+")
        if not pack_kw:
            pack_kw = {"padx": 8, "pady": 4, "anchor": "w", "fill": "x"}
        box.pack(**pack_kw)
        box.after_idle(_fit)
        return box

    def _required_missing(self):
        return sum(
            1 for lot in pc.open_lots(self.lots)
            if lot.get("account_type") == "Taxable"
            and lot.get("asset") != pc.CASH_ASSET
            and (lot.get("cost") is None or not lot.get("acquired")))

    def _chart_canvas(self, master, fig):
        """Embed a matplotlib figure that tracks its container's WIDTH.

        Height is fixed by the caller's figsize and the tab body scrolls
        vertically — so a tall figure is never cropped by a short window
        (sizing height from width grew figures past their allocation and
        cut off x-labels, legends and whole bar groups). Width tracking
        keeps split-screen (960px) free of horizontal overflow. On
        <Configure> (20px debounce) the figure width follows the widget;
        draw_idle emits no further Configure, so this converges.
        """
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        canvas = FigureCanvasTkAgg(fig, master=master)
        widget = canvas.get_tk_widget()
        widget.pack(fill="both", expand=True, padx=10, pady=6)
        state = {"w": 0}

        def _fit(_e=None):
            try:
                w = widget.winfo_width()
            except tk.TclError:
                return
            if w < _MIN_CHART_W:
                # No real size yet (cold-start transient, or a window
                # narrower than any supported layout): never shrink the
                # figure here and never draw — that first draw at a
                # degenerate size is the collapse the warning reported.
                # One bounded idle retry covers a canvas that never fires
                # another Configure.
                if state["w"] == 0 and state.get("retry", 0) < 8:
                    state["retry"] = state.get("retry", 0) + 1
                    try:
                        widget.after(250, lambda: _fit(None))
                    except tk.TclError:
                        pass
                return
            if abs(w - state["w"]) < 20:
                return
            state["w"] = w
            try:
                fig.set_size_inches(w / fig.get_dpi(),
                                    fig.get_size_inches()[1],
                                    forward=True)
                # Manual tight_layout only for figures without a layout
                # engine — the chart builders use the constrained engine
                # (solved on draw), where a manual pass only warns.
                # get_layout_engine is the current API; the constrained
                # getters are deprecated.
                use_tight = True
                get_engine = getattr(fig, "get_layout_engine", None)
                if get_engine is not None:
                    try:
                        use_tight = get_engine() is None
                    except Exception:  # noqa: BLE001 - fall back to tight
                        use_tight = True
                elif hasattr(fig, "get_constrained_layout"):
                    try:
                        use_tight = not fig.get_constrained_layout()
                    except Exception:  # noqa: BLE001
                        use_tight = True
                if use_tight:
                    fig.tight_layout()
                # The Tk canvas keeps its creation-time requested size
                # (1000px): without this the scrollable interior stays
                # 1000+ wide and the audit (rightly) reports overflow.
                fw, fh = fig.get_size_inches() * fig.get_dpi()
                widget.configure(width=int(fw), height=int(fh))
            except (ValueError, tk.TclError):
                pass
            canvas.draw_idle()

        widget.bind("<Configure>", _fit, add="+")
        return canvas

    def _goto_template(self):
        self.tabs.set("Data Entry")
        self.data_tabs.set("Template")

    def build_overview(self):
        self._keep_scrolls(self._build_overview_inner, ("overview",))

    def _build_overview_inner(self):
        f = self._clear_dash("Overview")
        # One vertical scroll region for the whole view: the chart keeps
        # its full figure height at any window size instead of being
        # cropped by a short window (lost x-labels, legends, bar groups).
        body = ctk.CTkScrollableFrame(f)
        self._scroll_keep["overview"] = body
        body.pack(fill="both", expand=True)
        if not self.positions:
            # DATA-DRIVEN empty state: zero positions means no numbers, no
            # chart, no alerts — a home-only net worth or a vacuous
            # "all complete" would mislead. Same panel after delete-all.
            ctk.CTkLabel(
                body, text="No data yet — add your first bank / account, "
                           "or upload a filled template.",
                font=ctk.CTkFont(size=FS_HEAD, weight="bold"),
                wraplength=860, anchor="w").pack(padx=10, pady=(24, 8),
                                                anchor="w")
            ctk.CTkButton(body, text="Add your first bank / account",
                          width=240,
                          command=self._cov_add_account).pack(
                              padx=10, pady=4, anchor="w")
            ctk.CTkButton(body, text="Upload",
                          width=240,
                          command=self._goto_template).pack(
                              padx=10, pady=4, anchor="w")
            self.build_watchlist(body)
            return
        tnw = self.data["tnw"]
        # Computed figures from live values — the radar as of today
        # (prices/home at the last refresh), never entered numbers.
        sp = pc.spending_capacity(self.profile, self.lots, self.prices)
        d = self.data["drift"]
        cap = sp["cap"]
        cap_note = (self.profile.get("cap_note") or "").strip()
        missing = self._required_missing()
        ctk.CTkLabel(body, text="Total net worth: %s" % money(tnw),
                     font=ctk.CTkFont(size=FS_TITLE, weight="bold")).pack(
                         padx=10, pady=(10, 2), anchor="w")
        ctk.CTkLabel(
            body, text="Allowed spending (as of %s; prices/home at last "
                    "refresh): %s/yr before 65 (pool %s ÷ %s yrs) · "
                    "%s/yr after 65 (IRAs %s ÷ 20; + Social Security "
                    "= %s)." % (
                        sp["asof"], money(sp["before65"]),
                        money(sp["under65"]),
                        "--" if sp["div_years"] is None
                        else "%d" % sp["div_years"],
                        money(sp["after65_base"]), money(sp["ira"]),
                        money(sp["after65_allin"])),
            font=ctk.CTkFont(size=FS_BODY)).pack(padx=10, pady=2, anchor="w")
        if sp["realizable"] is None:
            real_line = ("Realizable this year: — (set a MAGI ceiling in "
                         "Settings so headroom can derive).")
        else:
            real_line = ("Realizable this year ≈ %s (cash %s on hand + "
                         "sales within the %s gains cap)." % (
                             money(sp["realizable"]), money(sp["real_cash"]),
                             money(cap)))
        ctk.CTkLabel(body, text=real_line,
                     font=ctk.CTkFont(size=FS_BODY)).pack(padx=10, pady=2,
                                                          anchor="w")
        if sp["magi_status"] == "na":
            magi_alert = ("Medi-Cal: employer medical cover — "
                          "MAGI section not applicable.")
        elif sp["magi_status"] == "within":
            magi_alert = ("Medi-Cal MAGI %s of %s ceiling: WITHIN by %s."
                          % (money(sp["magi"]), money(sp["ceiling"]),
                             money(sp["ceiling"] - sp["magi"])))
        elif sp["magi_status"] == "over":
            try:
                ins = float(self.profile.get(
                    "private_insurance_per_person_mo", 1000) or 1000)
            except (ValueError, TypeError):
                ins = 1000.0
            magi_alert = ("Medi-Cal MAGI %s vs %s ceiling: OVER by %s — "
                          "cover lost ≈ %s/yr private for two."
                          % (money(sp["magi"]), money(sp["ceiling"]),
                             money(sp["magi"] - sp["ceiling"]),
                             money(ins * 12 * 2)))
        else:
            magi_alert = ("Medi-Cal MAGI unknown — set a ceiling in "
                          "Settings (☰ menu).")
        if sp["headroom"] is None:
            headroom_alert = ("Gains headroom unknown — no ceiling set.")
        else:
            headroom_alert = ("Gains headroom: %s of the %s cap%s. "
                              "Harvesting losses increases headroom."
                              % (money(sp["headroom"]), money(cap),
                                 " (%s)" % cap_note if cap_note else ""))
        if sp["agi_threshold"] is None or sp["agi_total"] is None:
            agi_alert = ("After-65 AGI guardrail: no threshold set — "
                         "set one in Settings.")
        else:
            agi_alert = ("After-65 AGI guardrail: IRAs/20 %s + other %s = "
                         "%s vs %s threshold: %s by %s (SS taxation not "
                         "modeled)."
                         % (money(sp["after65_base"]), money(sp["other"]),
                            money(sp["agi_total"]),
                            money(sp["agi_threshold"]),
                            "UNDER" if sp["agi_total"] <= sp["agi_threshold"]
                            else "OVER",
                            money(abs(sp["agi_threshold"]
                                      - sp["agi_total"]))))
        alerts = [
            # No wrapping parens around the drift figure: the shared
            # formatters already parenthesize negatives, so "(%s)" would
            # render "((2.9%))" on a losing year.
            "Drift vs standard: actual %s vs standard %s; drift %s." % (
                pct(d["actual_ytd"]), pct(d["standard_ytd"]),
                pct(d["drift_pp"])),
            magi_alert,
            headroom_alert,
            agi_alert,
            "%d REQUIRED position%s still missing cost or dates — feed "
            "them in Data Entry." % (missing, "" if missing == 1 else "s")
            if missing else
            "All REQUIRED positions have cost and dates.",
        ]
        for alert in alerts:
            ctk.CTkLabel(body, text="• " + alert, wraplength=860,
                         anchor="w").pack(padx=10, pady=1, anchor="w")
        summary = ("Total net worth: %s\n"
                   "Allowed spending (as of %s): %s/yr before 65 · "
                   "%s/yr after 65 (+ Social Security = %s).\n"
                   "%s\n%s"
                   % (money(tnw), sp["asof"], money(sp["before65"]),
                      money(sp["after65_base"]), money(sp["after65_allin"]),
                      real_line,
                      "\n".join("• " + a for a in alerts)))
        ctk.CTkButton(body, text="Copy summary", width=140,
                      command=lambda:
                      self._to_clipboard(summary, "Overview summary copied "
                                                 "— paste anywhere.")
                      ).pack(padx=10, pady=(6, 2), anchor="w")
        # Primary visual: the Actual-vs-Standard daily-close LINE chart —
        # the same shared implementation (and values) as Diversification.
        # The allocation bar chart lives in Diversification only.
        from matplotlib.figure import Figure
        fig = Figure(figsize=(10, 4.6), dpi=100)
        if pc.make_drift_chart(fig, pc.load_drift_log(DRIFT_LOG)):
            self._chart_canvas(body, fig)
        else:
            self._selectable_note(
                body, "No drift data yet — press Log after a close to "
                      "start the history.", padx=10, pady=6, fill="x")
        self.build_watchlist(body)
        # RESERVED: Overview bottom area below the watchlist is held for
        # the FUTURE upcoming-events calendar (earnings calls and other
        # events for portfolio holdings) — related to the deferred news
        # feed. The one-path navigation standing rule keeps the tab bar
        # as the sole navigation; no duplicate Go-to buttons here. Do not
        # build the calendar in this pass — this comment reserves the
        # space.

    def _watch_row(self, t):
        q = (self.watch or {}).get(t, {})
        price = q.get("price")
        t = self._watch_label(t)
        if t == "BTC" and price is not None:
            # BTC-USD quotes carry no market cap: COMPUTE mined supply x
            # price, so the row never shows "--" when priced.
            mcap = pc.btc_class_mcap(price)
        else:
            mcap = q.get("mcap")
        return [t, money(price),
                "--" if mcap is None else "$%.2fT" % (mcap / 1e12)]

    def _watch_class_title(self, name, tickers):
        # Header shows the class name + its total approx market cap. The
        # Gold total is the COMPUTED above-ground stock value — a different
        # number from GLD's net assets in its row; shown in different places
        # and labeled distinctly, never conflated.
        total = pc.watch_class_total(name, self.watch or {}, tickers)
        total_txt = "--" if total is None else "$%.2fT" % (total / 1e12)
        if name == "Gold":
            return "Gold (above-ground stock) · %s total" % total_txt
        return "%s · %s total" % (name, total_txt)

    def build_watchlist(self, body):
        # Market data, not portfolio data: always shown — even with zero
        # positions (the empty-state rule hides net worth, spending, drift
        # and alerts, never this). Prices update ONLY on Refresh stocks,
        # the same fetch cycle as portfolio prices; cached quotes show
        # before the first refresh. No polling, no separate refresh.
        # Standard classes are fixed content in code; user-defined classes
        # persist in profile.json and clear on delete-all. Watchlist first,
        # the reserved events calendar goes below it when built.
        ctk.CTkLabel(body, text="Watchlist",
                     font=ctk.CTkFont(size=FS_HEAD, weight="bold")).pack(
                         padx=10, pady=(10, 2), anchor="w")
        for name, tickers in self.watch_classes():
            standard = name in pc.WATCHLIST_CLASSES
            self._watch_class_section(body, name, tickers, standard)
        # New user-defined class: an asset class is a named watchlist.
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(6, 2))
        ctk.CTkLabel(row, text="New asset class:").pack(side="left",
                                                       padx=4)
        cls_var = tk.StringVar()
        ctk.CTkEntry(row, width=140, textvariable=cls_var).pack(
            side="left", padx=4)
        cmsg = SelectableMsg(row, text="", text_color="orange")
        cmsg.pack(side="left", padx=4)
        ctk.CTkButton(row, text="Add class", width=100,
                      command=lambda: self._watch_new_class(
                          cls_var.get(), cmsg)).pack(side="left", padx=4)

    def _watch_class_section(self, body, name, tickers, standard):
        # Every class owns its controls. Standard classes (fixed content
        # in code) show no edit controls at all — a "standard" note only.
        # A user class carries its Add ticker row, per-ticker Remove
        # buttons, and its own Delete class button in the section header;
        # no add/remove path targets the standard classes.
        head = ctk.CTkFrame(body, fg_color="transparent")
        head.pack(fill="x", padx=10, pady=(6, 0))
        ctk.CTkLabel(head, text=self._watch_class_title(name, tickers),
                     font=ctk.CTkFont(size=FS_BODY,
                                      weight="bold")).pack(side="left")
        if standard:
            ctk.CTkLabel(head, text="standard",
                         text_color=CLR_SECONDARY).pack(side="left", padx=8)
            Table(body, ["Ticker", "Price", "Market cap ($T)"],
                  [self._watch_row(t) for t in tickers]
                  ).pack(fill="x", padx=10, pady=4)
            return
        ctk.CTkButton(head, text="Delete class", width=110,
                      command=lambda: self._watch_delete_class(
                          name)).pack(side="right", padx=4)
        ctk.CTkButton(head, text="Copy", width=80,
                      command=lambda: self._copy_watch_class(
                          name, tickers)).pack(side="right", padx=4)
        for t in tickers:
            self._watch_ticker_row(body, name, t)
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(row, text="Add ticker to %s:" % name).pack(
            side="left", padx=4)
        add_var = tk.StringVar()
        ctk.CTkEntry(row, width=100, textvariable=add_var).pack(
            side="left", padx=4)
        wmsg = SelectableMsg(row, text="", text_color="orange")
        wmsg.pack(side="left", padx=4)
        ctk.CTkButton(row, text="Add", width=70,
                      command=lambda: self._watch_add(
                          name, add_var.get(), wmsg)).pack(side="left",
                                                           padx=4)

    def _watch_ticker_row(self, body, classname, t):
        vals = self._watch_row(t)
        row = ctk.CTkFrame(body)
        row.pack(fill="x", padx=10, pady=1)
        for col, (txt, w) in enumerate(
                [(vals[0], 90), (vals[1], 110), (vals[2], 130)]):
            neg = pc.is_negative_figure(txt)
            ctk.CTkLabel(row, text=txt, width=w, anchor="w",
                         text_color="red" if neg else None).grid(
                             row=0, column=col, padx=4, sticky="w")
        ctk.CTkButton(row, text="Remove", width=90,
                      command=lambda: self._watch_remove(
                          classname, t)).grid(row=0, column=3, padx=4)

    def _copy_watch_class(self, name, tickers):
        lines = ["\t".join(["Ticker", "Price", "Market cap ($T)"])]
        for t in tickers:
            lines.append("\t".join(self._watch_row(t)))
        self._to_clipboard("\n".join(lines),
                           "Watchlist class %s copied — paste anywhere."
                           % name)

    def _watch_user_classes(self):
        return dict(self.profile.get("watchlist_classes") or {})

    def _watch_save_classes(self, classes):
        self.profile["watchlist_classes"] = classes
        pc.save_profile(PROFILE_JSON, self.profile)

    # Markers of a transport/cache failure (as opposed to an unknown
    # symbol): a valid symbol with no network or no cached data must not
    # be rejected as "unknown". The generic "no quote (offline and
    # uncached)" line is deliberately NOT a marker — it fires for unknown
    # symbols too; only real exception names count.
    _NET_MARKERS = ("urlerror", "connection", "timeout", "timed out",
                    "resolve", "ssl", "http error", "network", "retries",
                    "unreachable", "failed to", "eof", "remote end")

    def _watch_label(self, t):
        # "SQ — Block Inc." once a company-name search resolved it (name
        # stored in the profile); bare ticker otherwise.
        name = (self.profile.get("watchlist_names") or {}).get(t)
        return "%s — %s" % (t, name) if name else t

    def _watch_fetch_status(self, sym):
        """(status, quotes): 'ok' | 'offline' | 'unknown'. A valid symbol
        with no network or no cached data is never 'unknown'."""
        try:
            quotes, errs, live = pc.fetch_watchlist([sym], CACHE)
        except Exception:  # noqa: BLE001 - never crash on quotes
            return "offline", {}
        if sym in live and quotes.get(sym, {}).get("price"):
            return "ok", quotes
        blob = " ".join(errs or []).lower()
        if any(m in blob for m in self._NET_MARKERS):
            return "offline", quotes
        return "unknown", quotes

    def _watch_commit(self, classname, sym, msg, name=None):
        classes = self._watch_user_classes()
        classes[classname] = classes.get(classname, []) + [sym]
        if name:
            names = dict(self.profile.get("watchlist_names") or {})
            names[sym] = name
            self.profile["watchlist_names"] = names
        self._watch_save_classes(classes)
        self.watch = pc.load_watchlist_cache(CACHE)
        self.build_overview()
        self.status_var.set("Added %s to %s." % (sym, classname))

    def _watch_add(self, classname, sym_raw, msg):
        raw = (sym_raw or "").strip()
        classes = self._watch_user_classes()
        if classname not in classes:
            msg.configure(text="%s is not a watchlist class." % classname)
            return
        if not raw:
            msg.configure(text="Enter a ticker symbol or company name.")
            return
        sym = raw.upper()
        if sym in self.watch_tickers():
            msg.configure(text="%s is already in watchlist." % sym)
            return
        msg.configure(text="Fetching %s…" % sym)
        status, _quotes = self._watch_fetch_status(sym)
        if status == "ok":
            self._watch_commit(classname, sym, msg)
            return
        if status == "offline":
            msg.configure(
                text="Could not fetch %s right now (no network or no "
                     "saved data) — not added, but the symbol may be "
                     "valid. Try again after Refresh stocks." % sym)
            return
        # Unknown as a symbol — resolve as a company name via the price
        # feed's symbol search instead of upper-casing it into a fake one.
        results, err = pc.search_tickers(raw)
        if err:
            msg.configure(
                text="Could not search for '%s' right now (no network?) — "
                     "try again after Refresh stocks." % raw)
            return
        if not results:
            msg.configure(text="No match for '%s' — try the ticker "
                               "symbol." % raw)
            return
        picked = self._watch_pick_symbol(raw, results)
        if not picked:
            msg.configure(text="")
            return
        sym2, name2 = picked
        if sym2 in self.watch_tickers():
            msg.configure(text="%s is already in watchlist." % sym2)
            return
        status2, _quotes2 = self._watch_fetch_status(sym2)
        if status2 != "ok":
            if status2 == "offline":
                msg.configure(
                    text="Could not fetch %s right now (no network or no "
                         "saved data) — not added. Try again after "
                         "Refresh stocks." % sym2)
            else:
                msg.configure(text="Could not find ticker %s — check the "
                                   "symbol." % sym2)
            return
        self._watch_commit(classname, sym2, msg, name=name2)

    def _watch_pick_symbol(self, query, results):
        """One button per match — the user confirms the resolution.
        Returns (symbol, name) or None on cancel."""
        win = ctk.CTkToplevel(self)
        win.title("Add ticker")
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()
        SelectableMsg(win, text="Matches for '%s' — pick one:" % query
                      ).pack(padx=16, pady=(14, 6), anchor="w")
        picked = {"sym": None}

        def choose(sym, name):
            picked["sym"] = (sym, name)
            win.destroy()

        for sym, name, exch in results:
            label = "%s — %s%s" % (sym, name or "?",
                                   " (%s)" % exch if exch else "")
            ctk.CTkButton(win, text=label[:48], width=340,
                          command=lambda s=sym, n=name: choose(s, n)
                          ).pack(padx=16, pady=2, anchor="w")
        ctk.CTkButton(win, text="Cancel", width=120,
                      command=win.destroy).pack(padx=16, pady=(6, 14),
                                               anchor="w")
        self.wait_window(win)
        return picked["sym"]

    def _drop_watch_name(self, sym):
        # A resolved company name belongs to its ticker's presence: drop
        # it once no class lists the ticker anymore.
        if any(sym in tickers
               for _c, tickers in self.watch_classes()):
            return
        names = dict(self.profile.get("watchlist_names") or {})
        if sym in names:
            del names[sym]
            self.profile["watchlist_names"] = names

    def _watch_remove(self, classname, sym):
        classes = self._watch_user_classes()
        members = classes.get(classname, [])
        if sym in members:
            classes[classname] = [t for t in members if t != sym]
            self._watch_save_classes(classes)
            self._drop_watch_name(sym)
            pc.save_profile(PROFILE_JSON, self.profile)
            self.build_overview()
            self.status_var.set("Removed %s from %s." % (sym, classname))
        else:
            self.status_var.set("%s is not in your watchlist." % sym)

    def _watch_new_class(self, name_raw, msg):
        name = (name_raw or "").strip()
        classes = self._watch_user_classes()
        if not name:
            msg.configure(text="Name the new asset class.")
            return
        taken = [c.lower() for c in list(pc.WATCHLIST_CLASSES)
                 + list(classes)]
        if name.lower() in taken:
            msg.configure(text="%s already exists." % name)
            return
        classes[name] = []
        self._watch_save_classes(classes)
        self.build_overview()
        self.status_var.set("Added watchlist class %s." % name)

    def _watch_delete_class(self, name):
        classes = self._watch_user_classes()
        if name in pc.WATCHLIST_CLASSES or name not in classes:
            return
        # No undo exists, so the confirm is the safety net (same as
        # delete-lot and delete-all).
        if not self._confirm(
                "Delete class",
                "Delete watchlist class '%s' and its %s? There is no "
                "undo." % (name, _n(len(classes[name]), "ticker")),
                ok_text="Delete class"):
            return
        gone = classes[name]
        del classes[name]
        self._watch_save_classes(classes)
        for t in gone:
            self._drop_watch_name(t)
        pc.save_profile(PROFILE_JSON, self.profile)
        self.build_overview()
        self.status_var.set("Deleted watchlist class %s." % name)

    def _hold_avg_text(self, avg, missing):
        # Checklist rule: the average shows ONLY when every open lot has
        # cost. Otherwise the cell reads `upload` — a prompt to upload the
        # missing cost data in Data Entry (count lives in the tooltip).
        if (missing or 0) > 1e-9:
            return "upload"
        if avg is None:
            return "--"
        return "$%.2f" % avg

    def _hold_missing_tip(self, missing, shares):
        return ("%s of %s shares lack cost — upload cost data in "
                "Data Entry." % (pc._fmt_shares(missing),
                                 pc._fmt_shares(shares)))

    def build_holdings(self):
        # ONE expanding table, ONE scroll region: each summary row carries
        # its own ▶/▼ expander; per-account rows insert directly beneath.
        # No lower panel, no nested scrolls.
        # DELIBERATE (Prompt 7 Delta 2, Issue 7 — decided, not a bug): no
        # `if not self.positions` guard here, unlike Overview. With zero
        # positions but a saved property, Holdings shows the RE home row
        # and its TOTAL while Overview shows "No data yet". The home is a
        # real asset; the inconsistency is accepted — do not re-flag.
        f = self._clear_dash("Holdings")
        if getattr(self, "_hold_expanded", None) is None:
            self._hold_expanded = set()
        # One Holdings row per property (today: one home row). Purchase-
        # price gain math only in the single-property case.
        home_rows = self._home_rows()
        rows, _total = pc.holdings_by_asset(
            self.lots, self.prices, self.home_value,
            self.profile.get("home_purchase_price") or None,
            homes=home_rows or None)
        scroll = ctk.CTkScrollableFrame(f)
        self._scroll_keep["holdings"] = scroll
        scroll.pack(fill="both", expand=True, padx=6, pady=6)
        header = ctk.CTkFrame(scroll, fg_color="transparent")
        header.pack(fill="x", padx=4)
        for col, (txt, w) in enumerate(
                [("", 30), ("Asset", 150), ("Total shares", 90),
                 ("Avg purchase price", 170), ("Current price", 90),
                 ("Current value", 100), ("Net gain $", 90),
                 ("Net gain %", 80)]):
            ctk.CTkLabel(header, text=txt, width=w,
                         font=ctk.CTkFont(weight="bold")).grid(
                             row=0, column=col, padx=2, sticky="w")
        for r in rows:
            self._hold_row(scroll, r)
        # Totals row: total value + total gains, labeled with what it
        # includes (positions + home rows; cash excluded — cash lives in
        # Accounts / Liquidity, never in Holdings). Gains total shows only
        # when every row's gain is computable, never a partial sum.
        tot_gain = sum(r["gain"] for r in rows if r["gain"] is not None)
        gain_unknown = any(r["gain"] is None for r in rows)
        tot = ctk.CTkFrame(scroll)
        tot.pack(fill="x", padx=4, pady=(4, 1))
        tline = ctk.CTkFrame(tot, fg_color="transparent")
        tline.pack(fill="x")
        ctk.CTkLabel(tline, text="", width=30).grid(row=0, column=0,
                                                   padx=2)
        tcells = [("TOTAL (positions + home; cash excluded)", 150),
                  ("", 90), ("", 170), ("", 90),
                  (money(_total), 100),
                  (("--" if gain_unknown else money(tot_gain)), 90),
                  ("", 80)]
        for col, (txt, w) in enumerate(tcells):
            ctk.CTkLabel(
                tline, text=txt, width=w, anchor="w",
                wraplength=w if col == 0 else 0,
                font=ctk.CTkFont(weight="bold"),
                text_color="red" if col == 5 and not gain_unknown
                and tot_gain < 0 else None).grid(row=0, column=col + 1,
                                                padx=2, sticky="w")
        legend = self._home_legend()
        if legend:
            self._selectable_note(
                scroll, "\n".join("%s — %s" % (tag, addr)
                                  for tag, addr in legend),
                padx=10, pady=(2, 4), fill="x")
        ctk.CTkButton(f, text="Copy table", width=110,
                      command=lambda: self._copy_holdings(rows)
                      ).pack(padx=6, pady=(6, 0), anchor="w")
        ctk.CTkLabel(
            f, text="Averages and gains show only when every open lot has "
                    "cost — otherwise Avg reads upload (hover for the "
                    "missing count) and gains read --. The table is a "
                    "checklist: upload the missing cost data in Data Entry. "
                    "Cash lives in Liquidity. Home is one row per property "
                    "(value only unless a purchase price is set in "
                    "Settings). "
                    "Click ▶ on a row for its per-account breakdown.",
            wraplength=860, anchor="w").pack(padx=6, pady=6, anchor="w")

    def _copy_holdings(self, rows):
        lines = ["\t".join(["Asset", "Total shares", "Avg purchase price",
                             "Current price", "Current value", "Net gain $",
                             "Net gain %"])]
        for r in rows:
            lines.append("\t".join([
                r["asset"], pc._fmt_shares(r["shares"]),
                self._hold_avg_text(r["avg_cost"], r["missing"]),
                "--" if r["price"] is None else "$%.2f" % r["price"],
                money(r["value"]),
                "--" if r["gain"] is None else money(r["gain"]),
                "--" if r["gain_pct"] is None else "%.1f%%" % (
                    r["gain_pct"] * 100)]))
        tot_gain = sum(r["gain"] for r in rows if r["gain"] is not None)
        gain_unknown = any(r["gain"] is None for r in rows)
        lines.append("\t".join([
            "TOTAL (positions + home; cash excluded)", "", "", "",
            money(sum(r["value"] for r in rows
                      if r["value"] is not None)),
            "--" if gain_unknown else money(tot_gain), ""]))
        for tag, addr in self._home_legend():
            lines.append("%s — %s" % (tag, addr))
        self._to_clipboard("\n".join(lines), "Holdings table copied — paste "
                                             "anywhere.")

    def _hold_row(self, scroll, r):
        box = ctk.CTkFrame(scroll)
        box.pack(fill="x", padx=4, pady=1)
        line = ctk.CTkFrame(box, fg_color="transparent")
        line.pack(fill="x")
        expanded = r["asset"] in self._hold_expanded
        if r["by_acct"]:
            btn = ctk.CTkButton(line, width=30,
                                text="▼" if expanded else "▶",
                                command=lambda: self._hold_toggle(
                                    box, detail, r, btn))
            btn.grid(row=0, column=0, padx=2)
        else:
            ctk.CTkLabel(line, text="", width=30).grid(row=0, column=0,
                                                      padx=2)
        cells = [
            r["asset"], pc._fmt_shares(r["shares"]),
            self._hold_avg_text(r["avg_cost"], r["missing"]),
            "--" if r["price"] is None else "$%.2f" % r["price"],
            money(r["value"]),
            "--" if r["gain"] is None else money(r["gain"]),
            "--" if r["gain_pct"] is None else "%.1f%%" % (
                r["gain_pct"] * 100)]
        widths = [150, 90, 170, 90, 100, 90, 80]
        for col, (txt, w) in enumerate(zip(cells, widths)):
            lbl = ctk.CTkLabel(line, text=txt, width=w, anchor="w")
            lbl.grid(row=0, column=col + 1, padx=2, sticky="w")
            if col == 2 and not r.get("complete", True):
                self._tooltip(lbl, self._hold_missing_tip(
                    r["missing"], r["shares"]))
        detail = ctk.CTkFrame(box, fg_color="transparent")
        if expanded:
            self._hold_fill_detail(detail, r)
            detail.pack(fill="x", padx=4, pady=2)

    def _hold_fill_detail(self, detail, r):
        # Per-account aggregates (same completeness rule as the summary:
        # average and gains show only when that account's lots for the
        # asset all have cost — this shows WHICH accounts still need data).
        for ri, acct in enumerate(sorted(r["by_acct"])):
            lots = r["by_acct"][acct]
            sh = sum(l.get("shares") or 0.0 for l in lots)
            ksh = sum(l.get("shares") or 0.0 for l in lots
                      if l.get("cost") is not None)
            kcost = sum((l.get("shares") or 0.0) * l["cost"] for l in lots
                        if l.get("cost") is not None)
            missing = sh - ksh
            complete = missing <= 1e-9
            avg = kcost / ksh if complete and ksh else None
            price = r["price"]
            value = None if price is None else sh * price
            if price is not None and avg is not None:
                gain = ksh * (price - avg)
                gain_pct = gain / kcost if kcost else None
            else:
                gain, gain_pct = None, None
            cells = [
                "    " + acct, pc._fmt_shares(sh),
                self._hold_avg_text(avg, missing),
                "--" if price is None else "$%.2f" % price,
                money(value),
                "--" if gain is None else money(gain),
                "--" if gain_pct is None else "%.1f%%" % (gain_pct * 100)]
            widths = [150, 90, 170, 90, 100, 90, 80]
            for col, (txt, w) in enumerate(zip(cells, widths)):
                lbl = ctk.CTkLabel(detail, text=txt, width=w, anchor="w",
                                   text_color=CLR_SECONDARY)
                lbl.grid(row=ri, column=col + 1, padx=2, sticky="w")
                if col == 2 and not complete:
                    self._tooltip(lbl, self._hold_missing_tip(missing, sh))

    def _hold_toggle(self, box, detail, r, btn):
        if r["asset"] in self._hold_expanded:
            self._hold_expanded.discard(r["asset"])
            btn.configure(text="▶")
            detail.pack_forget()
        else:
            self._hold_expanded.add(r["asset"])
            btn.configure(text="▼")
            if not detail.winfo_children():
                self._hold_fill_detail(detail, r)
            detail.pack(fill="x", padx=4, pady=2)

    def build_accounts(self):
        f = self._clear_dash("Accounts")
        # Data-driven: registry union lots. After delete-all there are no
        # accounts — empty state, no ghost rows at $0 (Issue 1). New
        # accounts appear here after Save (Issue 4c): this builder runs on
        # every recompute, so no view ever serves a stale list.
        if not self.account_registry():
            ctk.CTkLabel(
                f, text="No accounts yet — add your first bank / account.",
                font=ctk.CTkFont(size=FS_HEAD, weight="bold"),
                wraplength=860, anchor="w").pack(padx=10, pady=(24, 8),
                                                 anchor="w")
            ctk.CTkButton(f, text="Add your first bank / account",
                          width=240,
                          command=self._cov_add_account).pack(
                              padx=10, pady=4, anchor="w")
            return
        d = self.data

        def strong(x):
            return "**--" if x is None else "**" + pct(x)

        rows = []
        for r in d["view1"]:
            rows.append([r["account"], money(r["BTC & related"]),
                         money(r["Gold & silver"]), money(r["Equities"]),
                         money(r["Cash & cash-like"]), money(r["re"]),
                         "**" + money(r["total"]), strong(r["pct"])])
        t = d["view1_total"]
        rows.append(["**TOTAL", "**" + money(t["BTC & related"]),
                     "**" + money(t["Gold & silver"]),
                     "**" + money(t["Equities"]),
                     "**" + money(t["Cash & cash-like"]),
                     "**" + money(t["re"]), "**" + money(t["total"]),
                     strong(t["pct"])])
        m = d["mix"]
        rows.append(["**Mix %", strong(m["BTC & related"]),
                     strong(m["Gold & silver"]), strong(m["Equities"]),
                     strong(m["Cash & cash-like"]), strong(m["re"]),
                     strong(1.0 if t["total"] else None), ""])
        # One scroll region for the view: the full-height table lives in
        # a single scrollable; the action bar stays fixed below it.
        body = ctk.CTkScrollableFrame(f)
        self._scroll_keep["accounts"] = body
        body.pack(fill="both", expand=True, padx=6, pady=6)
        Table(body, ["Account", "BTC", "Gold", "Equities", "Cash-like",
                     "Real Estate", "Total", "% of portfolio"],
              rows).pack(fill="x", padx=6, pady=6)
        bar = ctk.CTkFrame(f)
        bar.pack(fill="x", padx=6, pady=6)
        ctk.CTkButton(bar, text="Add position",
                      command=self.add_position_form).pack(side="left", padx=4)
        # Record-keeping language, never trading language: this app is not
        # connected to any brokerage and places no orders — every action
        # here records something that already happened at the brokerage.
        ctk.CTkButton(bar, text="Sold / Reduce",
                      command=lambda: self.sell_form(close_all=False)).pack(
                          side="left", padx=4)
        ctk.CTkButton(bar, text="Mark closed",
                      command=lambda: self.sell_form(close_all=True)).pack(
                          side="left", padx=4)
        ctk.CTkButton(bar, text="Reopen",
                      command=self.reopen_form).pack(side="left", padx=4)

    def build_liquidity(self):
        # The sheet's Liquidity Plan tab, rebuilt: ONE row per institution,
        # framed by TRUE access ages. Cash/Taxable/HSA are Available now;
        # Traditional/Roth IRA unlock penalty-free at 59½ (Feb 2028) — 65
        # is a spending/SS milestone on Overview only, never a gate here.
        # Rows sum Available now + Unlocks at 59½ = Total. No model change:
        # the calc keys (under65/over65) already hold exactly these two
        # buckets, relabeled here.
        f = self._clear_dash("Liquidity")
        if getattr(self, "_liq_expanded", None) is None:
            self._liq_expanded = set()
        ctk.CTkLabel(
            f, text="Access to funds — what you can reach now, and what "
                    "unlocks penalty-free at 59½.",
            font=ctk.CTkFont(size=FS_HEAD, weight="bold")).pack(
                padx=6, pady=(6, 2), anchor="w")
        banks = pc.liquidity_by_bank(self.lots, self.prices)
        ctk.CTkButton(f, text="Copy table", width=110,
                      command=lambda: self._copy_liquidity(banks)
                      ).pack(padx=6, pady=(0, 2), anchor="w")
        scroll = ctk.CTkScrollableFrame(f)
        scroll.pack(fill="both", expand=True, padx=6, pady=6)
        self._liq_scroll = scroll
        self._scroll_keep["liquidity"] = scroll
        header = ctk.CTkFrame(scroll, fg_color="transparent")
        header.pack(fill="x", padx=4)
        for col, (txt, w) in enumerate(
                [("", 30), ("Institution", 170), ("Available now", 130),
                 ("Unlocks at 59½", 150), ("Total", 130)]):
            ctk.CTkLabel(header, text=txt, width=w,
                         font=ctk.CTkFont(size=FS_TABLE_HEAD,
                                          weight="bold")).grid(
                             row=0, column=col, padx=2, sticky="w")
        for norm in sorted(banks, key=lambda k: -banks[k]["total"]):
            b = banks[norm]
            box = ctk.CTkFrame(scroll)
            box.pack(fill="x", padx=4, pady=3)
            line = ctk.CTkFrame(box, fg_color="transparent")
            line.pack(fill="x")
            expanded = norm in self._liq_expanded
            btn = ctk.CTkButton(line, width=30,
                                text="▼" if expanded else "▶",
                                command=lambda n=norm: self._liq_toggle(n))
            btn.grid(row=0, column=0, padx=2)
            for col, txt in enumerate(
                    [b["display"], money(b["under65"]), money(b["over65"]),
                     money(b["total"])]):
                ctk.CTkLabel(line, text=txt, width=[170, 130, 150,
                                                   130][col],
                             anchor="w").grid(row=0, column=col + 1, padx=2,
                                              sticky="w")
            detail = ctk.CTkFrame(box, fg_color="transparent")
            if expanded:
                for ri, acct in enumerate(sorted(b["accounts"])):
                    a = b["accounts"][acct]
                    for col, txt in enumerate(
                            ["    " + acct, money(a["under"]),
                             money(a["over"]),
                             money(a["under"] + a["over"])]):
                        ctk.CTkLabel(detail, text=txt, width=[170, 130, 150,
                                                             130][col],
                                     anchor="w",
                                     text_color=CLR_SECONDARY).grid(
                                         row=ri, column=col + 1, padx=2,
                                         sticky="w")
                detail.pack(fill="x", padx=4, pady=2)
        under = sum(b["under65"] for b in banks.values())
        over = sum(b["over65"] for b in banks.values())
        liquid = under + over
        # Totals as a table row in the same columns — not just note text.
        tot = ctk.CTkFrame(scroll)
        tot.pack(fill="x", padx=4, pady=3)
        tline = ctk.CTkFrame(tot, fg_color="transparent")
        tline.pack(fill="x")
        ctk.CTkLabel(tline, text="", width=30).grid(row=0, column=0,
                                                   padx=2)
        for col, txt in enumerate(
                ["TOTAL (all institutions)", money(under), money(over),
                 money(liquid)]):
            ctk.CTkLabel(tline, text=txt, width=[170, 130, 150, 130][col],
                         anchor="w", wraplength=[170, 130, 150, 130][col],
                         font=ctk.CTkFont(weight="bold")).grid(
                             row=0, column=col + 1, padx=2, sticky="w")
        sp = pc.spending_capacity(self.profile, self.lots, self.prices)
        years = (under / sp["before65"]) if sp["before65"] else None
        self._selectable_note(
            f, "Home %s · net worth %s. Available-now total ÷ "
               "%s/yr before-65 spending = %s years of pre-65 spending "
               "covered by available-now money."
               % (money(self.home_value), money(self.data["tnw"]),
                  money(sp["before65"]),
                  "--" if years is None else "%.1f" % years),
            padx=6, pady=6, fill="x")
        self._selectable_note(
            f, "59½ (%s): penalty-free ≠ tax-free — Traditional "
               "withdrawals are still taxed as income; Roth earnings "
               "also need the 5-year rule."
               % pc.fifty_nine_half(self.profile.get("date_of_birth")),
            padx=6, pady=(0, 6), fill="x")

    def _copy_liquidity(self, banks):
        lines = ["\t".join(["Institution", "Available now",
                             "Unlocks at 59½", "Total"])]
        for norm in sorted(banks, key=lambda k: -banks[k]["total"]):
            b = banks[norm]
            lines.append("\t".join(
                [b["display"], money(b["under65"]), money(b["over65"]),
                 money(b["total"])]))
            for acct in sorted(b["accounts"]):
                a = b["accounts"][acct]
                lines.append("\t".join(
                    ["    " + acct, money(a["under"]), money(a["over"]),
                     money(a["under"] + a["over"])]))
        self._to_clipboard("\n".join(lines), "Liquidity table copied — "
                                             "paste anywhere.")

    def _liq_toggle(self, norm):
        if norm in self._liq_expanded:
            self._liq_expanded.discard(norm)
        else:
            self._liq_expanded.add(norm)
        y = None
        try:
            if self._liq_scroll is not None and \
                    self._liq_scroll.winfo_exists():
                y = self._liq_scroll._parent_canvas.yview()
        except (tk.TclError, AttributeError):
            y = None
        self.build_liquidity()
        if y:
            try:
                self._liq_scroll._parent_canvas.yview_moveto(y[0])
            except (tk.TclError, AttributeError):
                pass

    TAX_TYPE_NOTES = {
        "Traditional IRA": "Withdrawals taxed as income; required minimum "
                           "distributions (RMDs) apply from the statutory "
                           "age.",
        "Roth IRA": "Qualified withdrawals tax-free; no owner RMDs.",
        "Taxable": "Capital gains tax on sale (short vs long term by "
                   "holding period); tax-loss harvesting eligible.",
        "HSA": "Tax-free for qualified medical expenses.",
        "Cash": "N/A — spendable, no investment tax treatment.",
    }

    def build_taximplic(self):
        f = self._clear_dash("Tax implications")
        # One scroll region for the view (both tables full-height inside).
        body = ctk.CTkScrollableFrame(f)
        self._scroll_keep["taximplic"] = body
        body.pack(fill="both", expand=True)
        self._selectable_note(
            body, "What each account type means for tax and withdrawals "
                  "(facts, not advice).",
            padx=6, pady=6, fill="x")
        Table(body, ["Account type", "Tax / withdrawal treatment"],
              [["**" + t, self.TAX_TYPE_NOTES[t]] for t in
               ("Traditional IRA", "Roth IRA", "Taxable", "HSA", "Cash")]
              ).pack(fill="x", padx=6, pady=6)
        seen = {}
        for lot in self.lots:
            seen.setdefault(lot.get("account"),
                            lot.get("account_type") or "?")
        Table(body, ["Account", "Type"],
              [[a, seen[a]] for a in sorted(seen)]
              ).pack(fill="x", padx=6, pady=6)

    def build_diversification(self):
        from matplotlib.figure import Figure
        f = self._clear("Diversification")
        # One vertical scroll region: tables + both charts keep full height
        # at any window size instead of being cropped (see build_overview).
        body = ctk.CTkScrollableFrame(f)
        self._scroll_keep["diversification"] = body
        body.pack(fill="both", expand=True)
        if not self.positions:
            # Empty state (same rule as Overview/Accounts): zero positions
            # means no numbers, no chart, no rebalance plan — a fresh copy
            # must not show the previous owner's account names or sizing.
            ctk.CTkLabel(
                body, text="No data yet — add your first bank / account, "
                           "or upload a filled template.",
                font=ctk.CTkFont(size=FS_HEAD, weight="bold"),
                wraplength=860, anchor="w").pack(padx=10, pady=(24, 8),
                                                anchor="w")
            ctk.CTkButton(body, text="Add your first bank / account",
                          width=240,
                          command=self._cov_add_account).pack(
                              padx=10, pady=4, anchor="w")
            ctk.CTkButton(body, text="Upload",
                          width=240,
                          command=self._goto_template).pack(
                              padx=10, pady=4, anchor="w")
            return
        self._selectable_note(
            body, "The standard — 15:15:35:15:20 of total net worth\n"
                  "• BTC 15% — asymmetric upside, not maxi "
                  "(9% spot/ETF + 6% MSTR)\n"
                  "• Gold 15% — structural hedge against technology\n"
                  "• Equities 35% — growth engine\n"
                  "• Cash 15% — buffer, incl. 20% STRC\n"
                  "• Real Estate 20% — home anchor\n"
                  "Note: STRC is BTC-correlated preferred, so effective BTC "
                  "exposure runs ~2–3pp above stated.",
            padx=6, pady=6, fill="x")
        rows = []
        for r in self.data["view3"]:
            rows.append([r["bucket"], pct(r["target_pct"]),
                         money(r["target_dollar"]), money(r["actual"]),
                         pct(r["actual_pct"]),
                         pc.fmt_pp(r["deviation_pp"]),
                         money(r["rebalance"])])
        # Totals row: Target $ / Actual $ both sum to net worth — the
        # cross-view tie. Deviation and Rebalance are per-bucket moves,
        # not summable, so they stay blank.
        tnw3 = self.data["tnw"]
        if tnw3:
            apct = sum(r["actual_pct"] for r in self.data["view3"]
                       if r["actual_pct"] is not None)
            apct_txt = "**" + pct(apct)
        else:
            apct_txt = "**--"
        rows.append(["**TOTAL",
                     "**" + pct(sum(r["target_pct"]
                                    for r in self.data["view3"])),
                     "**" + money(sum(r["target_dollar"]
                                      for r in self.data["view3"])),
                     "**" + money(sum(r["actual"]
                                      for r in self.data["view3"])),
                     apct_txt, "", ""])
        Table(body, ["Bucket", "Target %", "Target $", "Actual $",
                     "Actual %", "Deviation (pp)",
                     "Rebalance (buy / sell)"],
              rows).pack(fill="both", padx=6, pady=6)
        fig1 = Figure(figsize=(10, 4.2), dpi=100)
        pc.make_allocation_chart(fig1, self.data["view3"])
        self._chart_canvas(body, fig1)
        # Account label is data-driven — never a hardcoded name. When one
        # IRA account can supply every planned sell quantity, name it and
        # keep the no-tax note; otherwise stay generic (tax depends on the
        # account used). Legs with no computable quantity stay out of sells
        # (e.g. the cash-sweep leg, whose sell_sh is None).
        acct_types = {a.get("account"): (a.get("account_type") or "")
                      for a in self.account_registry()}
        sells = {t["sell"]: t["sell_sh"]
                 for t in self.data["view4"]["trades"]
                 if t.get("sell") and t.get("sell_sh") is not None}
        acct_label, is_ira = pc.rebalance_account(self.positions, sells,
                                                  acct_types)
        if is_ira:
            plan_note = ("REBALANCE PLAN (display only, NEVER executes "
                         "trades). All 4 trades inside %s: no tax "
                         "(IRA). Verify at your brokerage before "
                         "placing any trade." % acct_label)
            tax_txt = "- (IRA)"
        else:
            plan_note = ("REBALANCE PLAN (display only, NEVER executes "
                         "trades). Tax depends on the account used — verify "
                         "at your brokerage before placing any trade.")
            tax_txt = "--"
        self._selectable_note(body, plan_note, padx=6, pady=6, fill="x")
        rows = []
        for t in self.data["view4"]["trades"]:
            rows.append([str(t["n"]), acct_label, t["sell"],
                         "--" if t["sell_sh"] is None else f"{t['sell_sh']:,}",
                         money(t["proceeds"]), t["buy"],
                         "--" if t["buy_sh"] is None else f"{t['buy_sh']:,}",
                         tax_txt])
        Table(body, ["#", "Account", "Sell", "Sell shares",
                     "Est. proceeds $", "Buy", "Est. buy shares", "Tax cost"],
              rows).pack(fill="both", padx=6, pady=6)
        v4 = self.data["view4"]
        tnw = self.data["tnw"]
        rows = []
        for b in pc.BUCKETS:
            before = v4["before"][b]
            after = v4["after"][b]
            rows.append([b, money(before),
                         pct(before / tnw) if tnw else "--",
                         money(after),
                         pct(after / tnw) if tnw else "--"])
        rows.append(["**TOTAL", "**" + money(tnw),
                     "**" + (pct(1.0) if tnw else "--"),
                     "**" + money(v4["after_total"]),
                     "**" + pct(v4["after_total"] / tnw) if tnw else "--"])
        Table(body, ["Bucket", "Before $", "Before %", "After $",
                     "After %"],
              rows).pack(fill="both", padx=6, pady=6)
        d = self.data["drift"]
        # The baseline renders from the drift log's year-start row — never
        # literal owner numbers. No baseline yet (empty log) reads as
        # unknown, not as a previous owner's $4,526K.
        drift_txt = (
            "Drift (calendar-year baseline %s = liquid %s + home %s): "
            "actual YTD %s | standard YTD %s | drift %s, %s | "
            "standard total %s"
            % (money(d["baseline_total"]), money(d["baseline_liquid"]),
               money(d["baseline_home"]), pct(d["actual_ytd"]),
               pct(d["standard_ytd"]), pct(d["drift_pp"]),
               money(d["drift_dollar"]), money(d["standard_total"])))
        self._selectable_note(body, drift_txt, padx=6, pady=6, fill="x")
        fig2 = Figure(figsize=(10, 6.0), dpi=100)
        if pc.make_drift_chart(fig2, pc.load_drift_log(DRIFT_LOG)):
            self._chart_canvas(body, fig2)
        else:
            self._selectable_note(
                body, "No drift data yet — press Log after a close to "
                      "start the history.", padx=6, pady=6, fill="x")

    def build_tax(self):
        f = self._clear("Tax Harvest")
        ctk.CTkLabel(f, text="Tax Loss Harvesting",
                     font=ctk.CTkFont(size=FS_HEAD, weight="bold")).pack(
                         padx=6, pady=(6, 0), anchor="w")
        # One scroll region for the view: all tables full-height inside.
        body = ctk.CTkScrollableFrame(f)
        self._scroll_keep["tax"] = body
        body.pack(fill="both", expand=True)
        year = datetime.date.today().year
        prices = self.prices
        rows = []
        losers = []
        # Totals accumulate here (raw numbers — the rows hold formatted
        # strings). A column with any unknown shows "--", never a partial.
        vsum, vunknown, psum, punknown = 0.0, False, 0.0, False
        for lot in pc.open_lots(self.lots):
            if pc.is_cash_row(lot):
                continue
            price = prices.get(lot["asset"])
            value = None if price is None else price * (lot["shares"] or 0)
            if lot.get("cost") is not None and price is not None:
                pnl = (lot["shares"] or 0) * (price - lot["cost"])
            else:
                pnl = None
            if value is None:
                vunknown = True
            else:
                vsum += value
            if pnl is None:
                punknown = True
            else:
                psum += pnl
            term = pc.holding_term(lot.get("acquired"))
            if pnl is not None and pnl < 0:
                losers.append((pnl, len(rows)))
            rows.append([lot["asset"], lot["account"],
                         str(lot["shares"]),
                         "--" if lot.get("cost") is None
                         else "$%.2f" % lot["cost"],
                         "--" if price is None else "$%.2f" % price,
                         money(value),
                         "need cost/date" if pnl is None
                         else money(pnl),
                         term or "--", ""])
        losers.sort()
        for rank, (_, i) in enumerate(losers, start=1):
            rows[i][-1] = str(rank)
        if rows:
            rows.append(["**TOTAL", "", "", "", "",
                         "**" + ("--" if vunknown else money(vsum)),
                         "**" + ("--" if punknown else money(psum)),
                         "", ""])
        Table(body, ["Asset", "Account", "Shares", "Cost/share $",
                     "Price now", "Value $", "Unrealized P&L $", "Term",
                     "Harvest rank"],
              rows).pack(fill="x", padx=6, pady=6)
        total, unknown, sold_rows = pc.realized_gains_year(
            self.lots, year,
            self.profile.get("other_realized_gains_current_year", 0) or 0.0)
        srows = []
        for r in sold_rows:
            srows.append([r["asset"], r["account"], str(r["shares"]),
                          "--" if r["cost"] is None else "$%.2f" % r["cost"],
                          "$%.2f" % r["sale_price"], r["sold_date"],
                          r["term"] or "--",
                          "basis unknown" if r["gain"] is None
                          else money(r["gain"])])
        if srows:
            Table(body, ["Sold %d — asset" % year, "Account", "Shares",
                         "Cost $", "Sale $", "Sold", "Term", "Gain $"],
                  srows).pack(fill="x", padx=6, pady=6)
        # Derived cap: Medi-Cal MAGI ceiling minus other annual income
        # (Settings). None when no ceiling is set — never hardcoded.
        cap = pc.gains_cap(self.profile)
        cap_note = (self.profile.get("cap_note") or "").strip()
        other = self.profile.get("other_realized_gains_current_year",
                                 0) or 0.0
        header = "%d annual net-gains budget" % year
        if cap_note:
            header += " — %s" % cap_note
        Table(body, [header, "$"],
              [["Annual net-gains cap%s" % (
                  "" if cap is not None else " (unset — set in Settings)"),
                money(cap)],
               ["Pre-app realized gains (full note in Settings)",
                money(other)],
               ["Realized from sold lots above", money(total - other)],
               ["**Net realized YTD", "**" + money(total)],
               ["**Remaining budget (leeway)",
                "**" + (money(cap - total) if cap is not None
                        else "—")]],
              ).pack(fill="x", padx=6, pady=6)
        note = ("Itemized sold rows and the pre-app field must NOT overlap "
                "— no double-counting. ")
        if unknown:
            note += ("%s have unknown basis and are EXCLUDED from the "
                     "total. " % _n(unknown, "sold lot"))
        note += ("Do NOT invent basis. Wash-sale rule: do not rebuy the "
                 "same asset within 30 days of a loss sale.")
        self._selectable_note(body, note, padx=6, pady=6, fill="x")

    # (Charts merged into build_diversification; Rebalance merged too.)


    # ---- Data Entry tab (Inputs / Template / Danger Zone) ----
    def _ensure_cov_state(self):
        if getattr(self, "cov_lots", None) is None:
            self.cov_lots = []
            self.cov_next_rid = 0
            self.cov_filter = None
            self.cov_guide = None
            self._cov_reset()
            # Inputs opens guided: first account with required gaps.
            todo = self._cov_incomplete_required()
            if todo:
                self.cov_filter = todo[0]
                self.cov_guide = todo[0]
            else:
                self.cov_guide = "done"

    def refresh_data_window(self):
        self._keep_scrolls(self._refresh_data_window_inner,
                           ("coverage", "template_guide"))

    def _refresh_data_window_inner(self):
        self._ensure_cov_state()
        self.build_data_coverage()
        self.build_data_template()
        self.build_data_danger()

    def _clear_data_tab(self, name):
        frame = self.data_tabs.tab(name)
        for w in frame.winfo_children():
            w.destroy()
        return frame

    def _cov_save_label(self, n):
        if n == 0:
            return "Save"
        return "Save (%s)" % _n(n, "unsaved change", "unsaved changes")

    def build_data_coverage(self):
        self._keep_scrolls(self._build_data_coverage_inner, ("coverage",))

    def _build_data_coverage_inner(self):
        f = self._clear_data_tab("Inputs")
        self.cov_nav_rows = []
        self.cov_widgets = {}
        self._cov_scroll = None
        t = self._cov_totals()
        # Button row first (widths fit 960px with margin); the progress
        # line sits below it so long counts never squeeze the buttons.
        top = ctk.CTkFrame(f, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(8, 2))
        n = self._cov_counts()
        # Adjacent pair at the right end, safe action first: [Save]
        # [Discard changes]. Side="right" packing puts the LAST packed
        # widget leftmost, so Discard packs before Save to read Save-then-
        # Discard left to right. No header-row "Show all": the guided
        # panel's own "Show all" (next to "Next account") is the single
        # path to the full grid — one-path rule, and the freed room fits
        # this pair at 960px.
        self.cov_save_btn = ctk.CTkButton(
            top, text=self._cov_save_label(n), width=230,
            command=self._cov_save,
            state="normal" if n else "disabled")
        self._tooltip(self.cov_save_btn,
                      "Staged edits not yet committed — press Save to "
                      "validate and commit them all at once.")
        self.cov_discard_btn = ctk.CTkButton(
            top, text="Discard changes", width=150,
            command=self._cov_discard,
            state="normal" if n else "disabled")
        self._tooltip(self.cov_discard_btn,
                      "Discard unsaved changes (saved data is not "
                      "affected).")
        self.cov_discard_btn.pack(side="right", padx=4)
        self.cov_save_btn.pack(side="right", padx=4)
        ctk.CTkButton(top, text="Copy grid", width=120,
                      command=self._copy_cov_grid).pack(side="right",
                                                       padx=4)
        ctk.CTkButton(top, text="+ Add account", width=160,
                      command=self._cov_add_account).pack(side="right",
                                                         padx=4)
        if not self.cov_filter:
            ctk.CTkButton(top, text="Guided", width=100,
                          command=self._cov_guide_start).pack(side="right",
                                                             padx=4)
        self.cov_progress = SelectableMsg(
            f, text="Positions %d of %d · Cost entered %d of %d · Dates "
                    "entered %d of %d" % (
                        t["holdings_ok"], t["holdings_n"], t["cost_ok"],
                        t["cost_n"], t["acq_ok"], t["acq_n"]),
            font=ctk.CTkFont(size=FS_BODY, weight="bold"))
        self.cov_progress.pack(anchor="w", padx=8)
        self.cov_warn = SelectableMsg(f, text="", text_color="orange")
        self.cov_warn.pack(padx=8, anchor="w")
        if self.cov_guide:
            self._cov_guide_panel(f)
        else:
            self._selectable_note(
                f, "How this grid works\n"
                   "• Taxable accounts are REQUIRED — cost and dates drive "
                   "your taxes and tax-loss harvesting. IRA, Roth and HSA "
                   "accounts are OPTIONAL (display only). Cash is always "
                   "complete.\n"
                   "• Rows are locked. Click Edit to change a row, or ↗ to "
                   "move it to another account.\n"
                   "• Typing never recalculates anything. Save (top right) "
                   "checks everything and commits at once; Discard "
                   "changes throws away unsaved edits (saved data is "
                   "not affected).\n"
                   "• Click any text and press Ctrl+C to copy it — or drag "
                   "to select any message; every "
                   "table has a Copy table button.",
                padx=8, pady=2, fill="x")
        if not self.cov_lots:
            ctk.CTkLabel(
                f, text="No accounts yet.",
                font=ctk.CTkFont(size=FS_HEAD, weight="bold")).pack(
                    padx=8, pady=(24, 4))
            ctk.CTkButton(f, text="Add your first bank / account",
                          width=240,
                          command=self._cov_add_account).pack(padx=8, pady=8)
            ctk.CTkLabel(
                f, text="Or upload a filled template in the Template sub-tab.",
                wraplength=600).pack(padx=8, pady=4)
            self._cov_refresh_chrome()
            return
        scroll = ctk.CTkScrollableFrame(f)
        scroll.pack(fill="both", expand=True, padx=8, pady=8)
        self._cov_scroll = scroll
        self._scroll_keep["coverage"] = scroll
        groups = {}
        for row in self.cov_lots:
            groups.setdefault(row.get("bank") or "?",
                              {}).setdefault(row.get("account"), []).append(
                                  row)
        for bank in sorted(groups):
            if self.cov_filter and not any(
                    a == self.cov_filter for a in groups[bank]):
                continue
            ctk.CTkLabel(scroll, text=bank,
                         font=ctk.CTkFont(size=FS_HEAD, weight="bold")).pack(
                             padx=6, pady=(10, 2), anchor="w")
            for acct in sorted(groups[bank]):
                if self.cov_filter and acct != self.cov_filter:
                    continue
                self._cov_account_section(scroll, bank, acct,
                                          groups[bank][acct])
        self._cov_refresh_chrome()

    def _cov_account_type(self, rows):
        for r in rows:
            if r.get("account_type"):
                return r["account_type"]
        return "Taxable"

    def _cov_account_section(self, scroll, bank, acct, rows):
        box = ctk.CTkFrame(scroll)
        box.pack(fill="x", padx=6, pady=4)
        atype = self._cov_account_type(rows)
        flag = "REQUIRED" if atype == "Taxable" else (
            "OPTIONAL" if atype in pc.RETIREMENT_TYPES else "COMPLETE")
        color = {"REQUIRED": "orange", "OPTIONAL": "gray",
                 "COMPLETE": "green"}.get(flag, "gray")
        head = ctk.CTkFrame(box, fg_color="transparent")
        head.pack(fill="x", padx=6, pady=4)
        ctk.CTkLabel(head, text=acct,
                     font=ctk.CTkFont(weight="bold")).pack(side="left",
                                                           padx=4)
        ctk.CTkLabel(head, text="[ %s ]" % flag,
                     text_color=color).pack(side="left", padx=4)
        self.cov_widgets.setdefault("acctval", {})[acct] = ctk.CTkLabel(
            head, text="")
        self.cov_widgets["acctval"][acct].pack(side="left", padx=8)
        menu = ctk.CTkOptionMenu(
            head, values=pc.ACCOUNT_TYPES,
            command=lambda v, a=acct: self.set_account_type(a, v))
        menu.set(atype)
        menu.pack(side="right", padx=4)
        ctk.CTkButton(head, text="Download template", width=140,
                      command=lambda a=acct:
                      self.download_account_template(a)).pack(side="right",
                                                             padx=4)
        hdr = ctk.CTkFrame(box, fg_color="transparent")
        hdr.pack(fill="x", padx=6)
        # Column budget: 798px + 44 grid padx + 24 frame chrome = 866,
        # inside a ~869px viewport at 960px window width (split screen).
        for col, (txt, w) in enumerate(
                [("Asset", 96), ("Shares", 62), ("Cost $", 62),
                 ("Acquired", 96), ("Sold", 96), ("Sale $", 62),
                 ("", 190), ("", 18), ("", 48), ("", 38), ("", 30)]):
            ctk.CTkLabel(hdr, text=txt, width=w,
                         font=ctk.CTkFont(weight="bold")).grid(
                             row=0, column=col, padx=2)
        for st, title in (("Open", None), ("Closed", "Closed")):
            sub = [r for r in rows if pc.lot_status(r) == st]
            if st == "Closed" and sub:
                ctk.CTkLabel(box, text="Closed",
                             font=ctk.CTkFont(weight="bold")).pack(
                                 padx=12, pady=(6, 0), anchor="w")
            for row in sub:
                self._cov_row(box, row)
        ctk.CTkButton(box, text="+ Add row", width=100,
                      command=lambda b=bank, a=acct:
                      self._cov_add_row(b, a)).pack(padx=12, pady=4,
                                                   anchor="w")

    def _cov_totals(self):
        # Staged shells are accounts, not positions — exclude them from
        # the coverage denominators.
        t = pc.coverage(
            [self._cov_stripped(r) for r in self.cov_lots
             if r.get("asset") or r.get("shares") is not None])["total"]
        t["required_left"] = sum(
            1 for r in self.cov_lots
            if pc.lot_status(r) == "Open"
            and r.get("account_type") == "Taxable"
            and r.get("asset") and r.get("shares")
            and r.get("asset") != pc.CASH_ASSET
            and (r.get("cost") is None or not r.get("acquired")))
        return t

    def _cov_row(self, box, row):
        # Grid columns: Asset, Shares, Cost, Acquired, Sold, Sale, Math,
        # marker, Edit, Del. Bank/Account live in the edit drawer (row 1)
        # and the section header — not as grid columns (fix 3).
        rid = row["_rid"]
        fr = ctk.CTkFrame(box, fg_color="transparent")
        fr.pack(fill="x", padx=6, pady=2)
        W = self.cov_widgets.setdefault(rid, {})
        W["frame"] = fr
        try:
            W["frame_def"] = fr.cget("fg_color")
        except tk.TclError:
            W["frame_def"] = "transparent"
        W["lockables"] = []
        nav = []

        def entry(parent, col, width, value, erow=0):
            var = tk.StringVar(value="" if value is None else str(value))
            ent = ctk.CTkEntry(parent, width=width, textvariable=var)
            ent.grid(row=erow, column=col, padx=2)
            return ent, var

        def snap(ent):
            try:
                W.setdefault("entry_fg_def", ent.cget("fg_color"))
                W.setdefault("entry_tx_def", ent.cget("text_color"))
            except tk.TclError:
                pass
            W["lockables"].append(ent)

        assets = sorted({r.get("asset") for r in self.cov_lots
                         if r.get("asset")})

        # asset menu + free-text (col 0)
        acell = ctk.CTkFrame(fr, fg_color="transparent")
        acell.grid(row=0, column=0, padx=2)
        avals = assets + ["< new >"]
        amenu = ctk.CTkOptionMenu(
            acell, width=96, values=avals,
            command=lambda v, r=rid: self._cov_menu(r, "asset", v))
        amenu.pack()
        anew_var = tk.StringVar()
        anew = ctk.CTkEntry(acell, width=96, textvariable=anew_var)
        cur_a = row.get("asset") or ""
        if cur_a in assets:
            amenu.set(cur_a)
        else:
            amenu.set("< new >")
            anew_var.set(cur_a)
            anew.pack()
        anew_var.trace_add(
            "write", lambda *_a, r=rid: self._cov_typed(r, "asset"))
        W["asset_menu"] = amenu
        W["asset_new"] = anew
        W["asset_new_var"] = anew_var
        W["asset_place"] = "pack"
        W["asset_col"] = 0
        snap(amenu)
        snap(anew)
        try:
            W["fg_def"] = amenu.cget("fg_color")
        except tk.TclError:
            W["fg_def"] = None
        nav.append(amenu)

        # Cash rows are an amount, not a position: one Amount field only
        # (stored as shares=amount, cost=1). Never cost/date prompts (§2).
        is_cash = (row.get("asset") == pc.CASH_ASSET or
                   row.get("account_type") == "Cash")
        W["is_cash"] = is_cash
        if is_cash:
            amt_ent, amt_var = entry(fr, 1, 170, row.get("shares"))
            W.update(shares=amt_ent, shares_var=amt_var)
            snap(amt_ent)
            amt_var.trace_add(
                "write", lambda *_a, r=rid: self._cov_typed(r, "shares"))
            nav.append(amt_ent)
            W["cash_note"] = ctk.CTkLabel(fr, text="Amount ($)", width=170,
                                          anchor="w")
            W["cash_note"].grid(row=0, column=2, columnspan=4, padx=2,
                                sticky="w")
        else:
            sh_ent, sh_var = entry(fr, 1, 62, row.get("shares"))
            co_ent, co_var = entry(fr, 2, 62, row.get("cost"))
            W.update(shares=sh_ent, shares_var=sh_var, cost=co_ent,
                     cost_var=co_var)
            for _e in (sh_ent, co_ent):
                snap(_e)
            sh_var.trace_add(
                "write", lambda *_a, r=rid: self._cov_typed(r, "shares"))
            co_var.trace_add(
                "write", lambda *_a, r=rid: self._cov_typed(r, "cost"))
            nav += [sh_ent, co_ent]

        def date_cell(col, field):
            acell2 = ctk.CTkFrame(fr, fg_color="transparent")
            acell2.grid(row=0, column=col, padx=2)
            var = tk.StringVar(value=row.get(field) or "")
            ent = ctk.CTkEntry(acell2, width=70, textvariable=var)
            ent.pack(side="left")
            btn = ctk.CTkButton(acell2, text="\U0001F4C5", width=24,
                                command=lambda r=rid, f=field:
                                self._cov_calendar(r, f))
            btn.pack(side="left", padx=1)
            var.trace_add(
                "write", lambda *_a, r=rid, f=field: self._cov_typed(r, f))
            W[field] = ent
            W[field + "_var"] = var
            W["lockables"].append(btn)
            snap(ent)
            nav.append(ent)

        if not is_cash:
            date_cell(3, "acquired")
            date_cell(4, "sold_date")
            sa_ent, sa_var = entry(fr, 5, 62, row.get("sale_price"))
            W.update(sale_price=sa_ent, sale_price_var=sa_var)
            snap(sa_ent)
            sa_var.trace_add(
                "write", lambda *_a, r=rid: self._cov_typed(r, "sale_price"))
            nav.append(sa_ent)

        # wraplength: long gain strings wrap to two lines instead of
        # clipping — no clipped text at split-screen width.
        math = ctk.CTkLabel(fr, text="", width=190, wraplength=190,
                            anchor="w")
        math.grid(row=0, column=6, padx=2)
        W["math"] = math
        try:
            W["math_def"] = math.cget("text_color")
        except tk.TclError:
            W["math_def"] = None
        marker = ctk.CTkLabel(fr, text="●", width=18, text_color="orange")
        marker.grid(row=0, column=7, padx=2)
        W["marker"] = marker
        edit = ctk.CTkButton(fr, text="Edit", width=48,
                             command=lambda r=rid: self._cov_toggle_lock(r))
        edit.grid(row=0, column=8, padx=2)
        W["edit"] = edit
        ctk.CTkButton(fr, text="Del", width=38,
                      command=lambda r=rid: self._cov_delete(r)).grid(
                          row=0, column=9, padx=2)
        move = ctk.CTkButton(fr, text="↗", width=30,
                             command=lambda r=rid: self._cov_toggle_move(r))
        move.grid(row=0, column=10, padx=2)
        W["move"] = move
        W["lockables"].append(move)

        # edit drawer: bank/account editors for moving the lot. Hidden
        # unless the row's Move line is explicitly expanded (§1 fix).
        drawer = ctk.CTkFrame(fr, fg_color="transparent")
        drawer.grid(row=1, column=0, columnspan=11, sticky="w", padx=2)
        W["drawer"] = drawer
        ctk.CTkLabel(drawer, text="Move this lot to —").pack(side="left",
                                                             padx=2)
        ctk.CTkLabel(drawer, text="Bank / Brokerage:").pack(side="left",
                                                            padx=2)
        bank_var = tk.StringVar(value=row.get("bank", ""))
        bank = ctk.CTkEntry(drawer, width=110, textvariable=bank_var)
        bank.pack(side="left", padx=2)
        bank_var.trace_add(
            "write", lambda *_a, r=rid: self._cov_typed(r, "bank"))
        W["bank"] = bank
        W["bank_var"] = bank_var
        snap(bank)
        ctk.CTkLabel(drawer, text="Account:").pack(side="left", padx=2)
        accounts = sorted({r.get("account") for r in self.cov_lots
                           if r.get("account")})
        acell3 = ctk.CTkFrame(drawer, fg_color="transparent")
        acell3.pack(side="left", padx=2)
        cvals = accounts + ["< new >"]
        cmenu = ctk.CTkOptionMenu(
            acell3, width=170, values=cvals,
            command=lambda v, r=rid: self._cov_menu(r, "account", v))
        cmenu.pack(side="left")
        cnew_var = tk.StringVar()
        cnew = ctk.CTkEntry(acell3, width=170, textvariable=cnew_var)
        cur_c = row.get("account") or ""
        if cur_c in accounts:
            cmenu.set(cur_c)
        else:
            cmenu.set("< new >")
            cnew_var.set(cur_c)
            cnew.pack(side="left")
        cnew_var.trace_add(
            "write", lambda *_a, r=rid: self._cov_typed(r, "account"))
        W["account_menu"] = cmenu
        W["account_new"] = cnew
        W["account_new_var"] = cnew_var
        W["account_place"] = "pack"
        W["account_place"] = "pack"
        snap(cmenu)
        snap(cnew)
        try:
            W["bd_def"] = bank.cget("border_color")
        except tk.TclError:
            W["bd_def"] = "gray"
        nav.append(bank)

        ridx = len(self.cov_nav_rows)
        self.cov_nav_rows.append(nav)
        W["nav"] = nav
        for cidx, widget in enumerate(nav):
            widget.bind("<Return>", lambda _e, rr=ridx, c=cidx:
                        self._cov_move(rr + 1, c, +1))
            widget.bind("<Up>", lambda _e, rr=ridx, c=cidx:
                        self._cov_move(rr - 1, c, -1))
            widget.bind("<Down>", lambda _e, rr=ridx, c=cidx:
                        self._cov_move(rr + 1, c, +1))
        self._cov_sync_new_visibility(rid)
        self._cov_apply_lock_visual(rid)
        self._cov_paint_row(rid)

    def _cov_apply_lock_visual(self, rid):
        # In-place lock/unlock: states, drawer, white editing row (fix 4),
        # dirty marker. No rebuild, no scroll jump (fix 5).
        W = self.cov_widgets.get(rid, {})
        try:
            row = self._cov_row_by_rid(rid)
        except StopIteration:
            return
        if "frame" not in W:
            return
        locked = row.get("_locked", True)
        state = "disabled" if locked else "normal"
        for w in W.get("lockables", []):
            try:
                w.configure(state=state)
            except (tk.TclError, ValueError):
                pass
        drawer = W.get("drawer")
        show_drawer = (not locked) and bool(row.get("_move_open"))
        if drawer is not None:
            try:
                if show_drawer:
                    drawer.grid(row=1, column=0, columnspan=11, sticky="w",
                                padx=2)
                else:
                    drawer.grid_remove()
            except tk.TclError:
                pass
        fr = W["frame"]
        entry_fg = W.get("entry_fg_def")
        entry_tx = W.get("entry_tx_def")
        try:
            if locked:
                if W.get("frame_def") is not None:
                    fr.configure(fg_color=W["frame_def"])
            else:
                fr.configure(fg_color="white")
        except (tk.TclError, ValueError):
            pass
        for key in ("bank", "shares", "cost", "acquired", "sold_date",
                    "sale_price", "account_new", "asset_new"):
            w = W.get(key)
            if w is None:
                continue
            try:
                if locked:
                    if entry_fg is not None:
                        w.configure(fg_color=entry_fg)
                    if entry_tx is not None:
                        w.configure(text_color=entry_tx)
                else:
                    w.configure(fg_color="white", text_color="black")
            except (tk.TclError, ValueError):
                pass
        math = W.get("math")
        if math is not None:
            try:
                if locked and W.get("math_def") is not None:
                    math.configure(text_color=W["math_def"])
                elif not locked:
                    math.configure(text_color="black")
            except (tk.TclError, ValueError):
                pass
        edit = W.get("edit")
        if edit is not None:
            try:
                edit.configure(text="Edit" if locked else "Lock")
            except (tk.TclError, ValueError):
                pass
        if row["_orig"] is None:
            dirty = True
        else:
            try:
                dirty = self._cov_stripped(row) != self._cov_stripped(
                    self.lots[row["_orig"]])
            except IndexError:
                dirty = True
        marker = W.get("marker")
        if marker is not None:
            try:
                if locked and dirty:
                    marker.grid(row=0, column=7, padx=2)
                else:
                    marker.grid_remove()
            except tk.TclError:
                pass

    def _cov_repaint_all(self):
        for rid, W in list(self.cov_widgets.items()):
            if rid == "acctval" or not isinstance(W, dict):
                continue
            if "frame" not in W:
                continue
            try:
                alive = W["frame"].winfo_exists()
            except tk.TclError:
                continue
            if not alive:
                continue
            try:
                self._cov_row_by_rid(rid)
            except StopIteration:
                continue
            self._cov_apply_lock_visual(rid)
            self._cov_paint_row(rid)
        self._cov_refresh_chrome()

    def _cov_move(self, ridx, cidx, direction):
        # Skip unmapped widgets (collapsed Move drawers) in scan direction.
        r = ridx
        while 0 <= r < len(self.cov_nav_rows):
            row = self.cov_nav_rows[r]
            if 0 <= cidx < len(row):
                try:
                    if row[cidx].winfo_exists() and \
                            row[cidx].winfo_ismapped():
                        row[cidx].focus_set()
                        return "break"
                except tk.TclError:
                    pass
            r += direction
        return "break"

    def _cov_toggle_move(self, rid):
        # Expanding one row's Move line never touches any other row.
        try:
            row = self._cov_row_by_rid(rid)
        except StopIteration:
            return
        row["_move_open"] = not row.get("_move_open")
        self._cov_apply_lock_visual(rid)

    def _cov_toggle_lock(self, rid):
        row = self._cov_row_by_rid(rid)
        row["_locked"] = not row.get("_locked", True)
        if row.get("_locked"):
            row["_move_open"] = False
        self._cov_apply_lock_visual(rid)
        self._cov_paint_row(rid)
        self._cov_refresh_chrome()

    def _cov_rebind_nav(self):
        self.cov_nav_rows = []
        for row in self.cov_lots:
            W = self.cov_widgets.get(row["_rid"], {})
            nav = W.get("nav")
            if not nav:
                continue
            try:
                if not W.get("frame") or not W["frame"].winfo_exists():
                    continue
            except tk.TclError:
                continue
            ridx = len(self.cov_nav_rows)
            self.cov_nav_rows.append(nav)
            for cidx, widget in enumerate(nav):
                try:
                    widget.bind("<Return>", lambda _e, rr=ridx, c=cidx:
                                self._cov_move(rr + 1, c, +1))
                    widget.bind("<Up>", lambda _e, rr=ridx, c=cidx:
                                self._cov_move(rr - 1, c, -1))
                    widget.bind("<Down>", lambda _e, rr=ridx, c=cidx:
                                self._cov_move(rr + 1, c, +1))
                except tk.TclError:
                    pass

    def _cov_row_by_rid(self, rid):
        return next(r for r in self.cov_lots if r["_rid"] == rid)

    def _cov_menu(self, rid, field, value):
        self._cov_sync_new_visibility(rid)
        self._cov_typed(rid, field)

    def _cov_sync_new_visibility(self, rid):
        W = self.cov_widgets.get(rid, {})
        for field in ("account", "asset"):
            menu = W.get(field + "_menu")
            new_ent = W.get(field + "_new")
            if menu is None or new_ent is None:
                continue
            picked_new = menu.get() == "< new >"
            has_new = bool(new_ent.winfo_manager())
            place = W.get(field + "_place", "grid")
            col = W.get(field + "_col", 0)
            if picked_new and not has_new:
                if place == "grid":
                    menu.grid_remove()
                    new_ent.grid(row=0, column=col, padx=2)
                else:
                    menu.pack_forget()
                    new_ent.pack(side="left", padx=2)
            elif not picked_new and has_new:
                if place == "grid":
                    new_ent.grid_remove()
                    menu.grid(row=0, column=col, padx=2)
                else:
                    new_ent.pack_forget()
                    menu.pack(side="left", padx=2)

    def _cov_resolve(self, rid, field):
        W = self.cov_widgets[rid]
        if field in ("account", "asset"):
            menu = W[field + "_menu"]
            if menu.get() == "< new >":
                return W[field + "_new_var"].get().strip()
            return menu.get()
        return W[field + "_var"].get()

    def _cov_typed(self, rid, field):
        # Stage a keystroke into the working copy. Pure form state: no
        # recompute, no chart redraw, no file write — ever.
        try:
            row = self._cov_row_by_rid(rid)
        except StopIteration:
            return
        text = self._cov_resolve(rid, field)
        if field in ("shares", "cost", "sale_price"):
            try:
                row[field] = None if text.strip() == "" else float(text)
            except ValueError:
                row[field] = None
                row["_bad_" + field] = True
            else:
                row.pop("_bad_" + field, None)
        elif field in ("acquired", "sold_date"):
            row[field] = text.strip()
        elif field == "bank":
            row[field] = text.strip()
        elif field in ("account", "asset"):
            row[field] = text.strip()
            if field == "account" and text.strip():
                for cand in list(self.cov_lots) + self.lots:
                    if cand.get("account") == text.strip() and \
                            cand.get("account_type"):
                        row["account_type"] = cand["account_type"]
                        break
        self._cov_paint_row(rid)
        self._cov_refresh_chrome()

    def _cov_orig_field(self, row, field):
        if row["_orig"] is None:
            return None, True
        return self.lots[row["_orig"]].get(field), False

    def _cov_paint_row(self, rid):
        W = self.cov_widgets.get(rid, {})
        if not W:
            return
        row = self._cov_row_by_rid(rid)
        today = datetime.date.today().isoformat()
        bad = False

        bd_def = W.get("bd_def", "gray")
        fg_def = W.get("fg_def")

        def border(widget, is_bad, changed):
            try:
                if is_bad:
                    widget.configure(border_color="#E5484D")
                elif changed:
                    widget.configure(border_color="#F5A524")
                else:
                    widget.configure(border_color=bd_def)
            except (tk.TclError, ValueError):
                pass
            return is_bad

        def menu_mark(menu, changed):
            try:
                if changed:
                    menu.configure(fg_color="#8A6D00")
                elif fg_def is not None:
                    menu.configure(fg_color=fg_def)
            except (tk.TclError, ValueError):
                pass

        for field, var_key in (("bank", "bank_var"),
                               ("shares", "shares_var"),
                               ("cost", "cost_var"),
                               ("sale_price", "sale_price_var"),
                               ("acquired", "acquired_var"),
                               ("sold_date", "sold_date_var")):
            widget = W.get(field)
            var = W.get(var_key)
            if widget is None or var is None:
                continue
            text = var.get()
            is_bad, changed = False, False
            if field == "bank":
                changed = row["_orig"] is None or \
                    text.strip() != (self.lots[row["_orig"]].get("bank", "")
                                     if row["_orig"] is not None else "")
            elif field == "shares":
                try:
                    v = float(text) if text.strip() else None
                    # A staged shell intentionally carries no lot yet —
                    # empty shares are expected, never an error.
                    is_bad = (v is None or v <= 0) and \
                        not self._cov_is_shell(row)
                except ValueError:
                    is_bad = True
                orig, is_new = self._cov_orig_field(row, "shares")
                changed = is_new or (not is_bad and v != orig)
            elif field in ("cost", "sale_price"):
                try:
                    v = None if not text.strip() else float(text)
                    is_bad = v is not None and v < 0
                except ValueError:
                    is_bad, v = True, None
                orig, is_new = self._cov_orig_field(
                    row, "cost" if field == "cost" else "sale_price")
                changed = is_new or (not is_bad and v != orig)
            else:
                if text.strip():
                    try:
                        datetime.date.fromisoformat(text.strip())
                    except ValueError:
                        is_bad = True
                    if field == "acquired" and not is_bad and \
                            text.strip() > today:
                        is_bad = True
                orig, is_new = self._cov_orig_field(row, field)
                changed = is_new or text.strip() != (orig or "")
            bad = border(widget, is_bad, changed) or bad
        for field in ("account", "asset"):
            menu = W.get(field + "_menu")
            if menu is None:
                continue
            orig, is_new = self._cov_orig_field(row, field)
            menu_mark(menu, is_new or row.get(field) != orig)
        # live row arithmetic: implied totals, never a recompute
        sh, co = row.get("shares"), row.get("cost")
        parts = []
        if sh and (row.get("asset") == pc.CASH_ASSET
                   or row.get("account_type") == "Cash"):
            parts.append("≡ %s" % money(sh))
        elif sh and co is not None:
            parts.append("≡ %s" % money(sh * co))
        elif sh:
            parts.append("≡ ? (need cost)")
        elif row.get("asset"):
            parts.append("≡ ? (need shares)")
        elif row.get("_orig") is None:
            parts.append("≡ ○ (empty row — fill asset + shares to add a "
                         "lot, or leave it: the account registers on Save)")
        else:
            parts.append("≡ ? (need shares+cost)")
        if row.get("sold_date") and row.get("sale_price") and sh:
            proc = row["sale_price"] * sh
            if co is not None:
                parts.append("→ %s (%s %s)" % (
                    money(proc), money((row["sale_price"] - co) * sh),
                    pc.holding_term(row.get("acquired"),
                                    sold=row["sold_date"]) or "?"))
            else:
                parts.append("→ %s (basis unknown)" % money(proc))
        W["math"].configure(text=" · ".join(parts))
        row["_row_bad"] = bad

    def _cov_acct_value(self, acct):
        total = 0.0
        for r in self.cov_lots:
            if r.get("account") != acct or pc.lot_status(r) != "Open":
                continue
            if r.get("shares") is None:
                continue
            price = 1.0 if r.get("asset") == pc.CASH_ASSET \
                else self.prices.get(r.get("asset"))
            if price is not None:
                total += r["shares"] * price
        return total

    def _cov_refresh_chrome(self):
        # Cheap form chrome only: counts, warnings, values. NEVER a
        # portfolio recompute — Save owns the single recompute.
        n = self._cov_counts()
        if getattr(self, "cov_save_btn", None) is not None:
            try:
                self.cov_save_btn.configure(
                    text=self._cov_save_label(n),
                    state="normal" if n else "disabled")
            except (tk.TclError, ValueError):
                pass
        # The discard button shares Save's enabled condition: with zero
        # staged changes there is nothing to discard, so it stays greyed.
        if getattr(self, "cov_discard_btn", None) is not None:
            try:
                self.cov_discard_btn.configure(
                    state="normal" if n else "disabled")
            except (tk.TclError, ValueError):
                pass
        if getattr(self, "cov_progress", None) is not None:
            try:
                t = self._cov_totals()
                self.cov_progress.configure(
                    text="Positions %d of %d · Cost entered %d of %d · "
                         "Dates entered %d of %d"
                         % (t["holdings_ok"], t["holdings_n"], t["cost_ok"],
                            t["cost_n"], t["acq_ok"], t["acq_n"]))
            except (tk.TclError, ValueError):
                pass
        dup = {}
        for r in self.cov_lots:
            if pc.lot_status(r) != "Open":
                continue  # a closed row may share its open residual's key
            key = (r.get("account"), r.get("asset"), r.get("acquired"),
                   r.get("cost"))
            dup.setdefault(key, []).append(r["_rid"])
        dups = []
        for dup_rs in dup.values():
            if len(dup_rs) > 1:
                first = next(rr for rr in self.cov_lots
                             if rr["_rid"] == dup_rs[0])
                dups.append("you already have a %s lot with this date and "
                            "cost — second lot, or duplicate?"
                            % (first.get("asset") or "?"))
        bad_rows = sum(1 for r in self.cov_lots if r.get("_row_bad"))
        bits = []
        if dups:
            bits.append(dups[0] if len(dups) == 1 else
                        "%d duplicate-lot warnings (first: %s)"
                        % (len(dups), dups[0]))
        if bad_rows:
            bits.append("%s have invalid cells (red) — fix before Save"
                        % _n(bad_rows, "row"))
        if getattr(self, "cov_warn", None) is not None and \
                self.cov_warn.winfo_exists():
            self.cov_warn.configure(text=" · ".join(bits))
        for acct, lbl in (getattr(self, "cov_widgets", {}) or {}).get(
                "acctval", {}).items():
            try:
                lbl.configure(text="≈ %s (check vs broker)" % money(
                    self._cov_acct_value(acct)))
            except tk.TclError:
                pass
        if getattr(self, "cov_count_lbl", None) is not None and \
                self.cov_count_lbl.winfo_exists():
            left = self._cov_totals()["required_left"]
            self.cov_count_lbl.configure(
                text="%s left to feed" % _n(left, "position"))

    def _cov_save(self):
        # Shell rows (staged account, no lot yet) are NOT lots: exclude
        # them from validation/merge, register their accounts instead.
        shells = [(r.get("bank") or "", r.get("account") or "",
                   r.get("account_type") or "")
                  for r in self.cov_lots if self._cov_is_shell(r)]
        raw = []
        for r in self.cov_lots:
            if self._cov_is_shell(r):
                continue
            raw.append({
                "bank": (r.get("bank") or ""), "account": (r.get("account")
                                                           or ""),
                "account_type": (r.get("account_type") or ""),
                "asset": (r.get("asset") or ""),
                "shares": ("" if r.get("shares") is None
                           else str(r["shares"])),
                "cost_per_share": ("" if r.get("cost") is None
                                   else str(r["cost"])),
                "acquired_date": (r.get("acquired") or ""),
                "sold_date": (r.get("sold_date") or ""),
                "sale_price_per_share": ("" if r.get("sale_price") is None
                                         else str(r["sale_price"]))})
        errors = pc.validate_lot_rows(raw)
        if errors or any(r.get("_row_bad") for r in self.cov_lots):
            shown = list(errors[:8])
            if any(r.get("_row_bad") for r in self.cov_lots):
                shown.append("red cells must be fixed first")
            self.cov_warn.configure(text="Save blocked:\n" +
                                    "\n".join(shown))
            self.status_var.set("Coverage not saved — fix the flagged rows.")
            return False
        new = [pc.row_to_lot(r) for r in raw]
        # Net-change needs: dated growth minus dateless shares released by
        # the same edit (a row gaining a date converts its own shares, so
        # only true growth draws the unattributed balance).
        old_dated = pc.dated_totals(self.lots)
        new_dated = pc.dated_totals(new)
        old_und = pc.undated_totals(self.lots)
        new_und = pc.undated_totals(new)
        needs = {}
        for k, v in new_dated.items():
            need = v - old_dated.get(k, 0.0) - max(
                0.0, old_und.get(k, 0.0) - new_und.get(k, 0.0))
            if need > 1e-9:
                needs[k] = need
        orig_keys = {pc.lot_key(l) for l in self.lots}
        absent = {pc.lot_key(l) for l in new if pc.lot_key(l) not in orig_keys}
        new2 = [dict(l) for l in new]
        derrs = pc.drawdown_amounts(new2, needs, exclude_keys=absent)
        if derrs:
            self.cov_warn.configure(text="Save blocked:\n" + "\n".join(derrs))
            self.status_var.set("Coverage not saved — dated shares exceed "
                                "the unattributed balance.")
            return False
        n_rows_pre = len(self.cov_lots)
        sec_pre = sorted((l.get("bank"), l.get("account"),
                          pc.lot_status(l)) for l in self.lots)
        self.lots = new2
        # Register staged shells (save_lots also syncs from the lots).
        self._sync_registry(shells=shells)
        self.save_lots("Coverage saved.")
        sec_post = sorted((l.get("bank"), l.get("account"),
                           pc.lot_status(l)) for l in self.lots)
        moved = sec_pre != sec_post
        # Rematch working rows to committed lots by content. Cost/date/share
        # edits rematch fully (repaint in place, no scroll jump — fix 5);
        # new/deleted/moved rows cannot rematch (structural rebuild).
        used = set()
        for row in self.cov_lots:
            s = self._cov_stripped(row)
            row["_orig"] = None
            for j, lot in enumerate(self.lots):
                if j in used:
                    continue
                if self._cov_stripped(lot) == s:
                    row["_orig"] = j
                    used.add(j)
                    break
            row["_locked"] = True
            row["_move_open"] = False
        if not moved and len(self.lots) == n_rows_pre and all(
                r["_orig"] is not None for r in self.cov_lots):
            self._cov_repaint_all()
        else:
            self._cov_reset()
            self._cov_keep_scroll(self.build_data_coverage)
        return True

    def _cov_revert(self):
        self._cov_reset()
        self._cov_keep_scroll(self.build_data_coverage)
        self.status_var.set("Unsaved coverage edits discarded.")

    def _confirm(self, title, text, ok_text="Discard", parent=None):
        """Small modal with named confirm/cancel buttons. Returns True only
        on the confirm button; closing the window counts as cancel. Pass
        the open dialog as parent so the modal stacks above it — on Linux
        a root-parented modal can hide behind it while its grab makes the
        app look frozen."""
        win = ctk.CTkToplevel(self)
        win.title(title)
        win.transient(parent or self)
        win.resizable(False, False)
        win.grab_set()
        win.lift()
        SelectableMsg(win, text=text).pack(
            padx=16, pady=(14, 10), anchor="w", fill="x")
        result = {"ok": False}
        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(0, 14))

        def _ok():
            result["ok"] = True
            win.destroy()

        ctk.CTkButton(bar, text=ok_text, width=120,
                      command=_ok).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bar, text="Cancel", width=120,
                      command=win.destroy).pack(side="left")
        self.wait_window(win)
        return result["ok"]

    def _confirm3(self, title, text, labels, parent=None):
        """Three-way copyable modal: _confirm is 2-way, but the unsaved-
        edits gate needs three outcomes (save-first / saved-state-only /
        cancel). Returns the button index; closing the window counts as
        the last (cancel) outcome."""
        win = ctk.CTkToplevel(self)
        win.title(title)
        win.transient(parent or self)
        win.resizable(False, False)
        win.grab_set()
        win.lift()
        SelectableMsg(win, text=text).pack(
            padx=16, pady=(14, 10), anchor="w", fill="x")
        result = {"idx": None}
        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(0, 14))

        def _pick(i):
            result["idx"] = i
            win.destroy()

        for i, label in enumerate(labels):
            ctk.CTkButton(bar, text=label, width=150,
                          command=lambda i=i: _pick(i)).pack(
                              side="left", padx=(0, 8))
        self.wait_window(win)
        if result["idx"] is None:
            return len(labels) - 1
        return result["idx"]

    def _notify(self, title, text):
        """Copyable one-click-dismiss message dialog (SelectableMsg, never
        a native messagebox). For results the user must actually read —
        e.g. what an upload did."""
        win = ctk.CTkToplevel(self)
        win.title(title)
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()
        win.lift()
        SelectableMsg(win, text=text).pack(
            padx=16, pady=(14, 10), anchor="w", fill="x")
        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkButton(bar, text="OK", width=120,
                      command=win.destroy).pack(side="left")
        self.wait_window(win)

    def _cov_discard(self):
        # "Revert" never said WHAT it reverts, so it read as if saved work
        # were at risk. It discards only this session's unsaved staged
        # edits and reloads from the saved file — previous sessions'
        # saved rows survive, because the reload comes from that file.
        n = self._cov_counts()
        if n == 0:
            return
        if not self._confirm(
                "Discard changes",
                "Discard %s? Saved data is not affected."
                % _n(n, "unsaved change", "unsaved changes"),
                ok_text="Discard changes"):
            return
        self._cov_revert()

    def _copy_cov_grid(self):
        # Locked (disabled) grid entries are not selectable — this button
        # copies the staged grid as TSV instead (unsaved edits included,
        # flagged with *).
        lines = ["\t".join(["Bank", "Account", "Type", "Asset", "Shares",
                             "Cost/share", "Acquired", "Sold",
                             "Sale price"])]
        for r in (self.cov_lots or []):
            if r.get("_orig") is None:
                mark = "*new* "
            elif self._cov_stripped(r) != self._cov_stripped(
                    self.lots[r["_orig"]]):
                mark = "* "
            else:
                mark = ""
            lines.append("\t".join([
                mark + (r.get("bank") or ""), r.get("account") or "",
                r.get("account_type") or "", r.get("asset") or "",
                "" if r.get("shares") is None else str(r.get("shares")),
                "" if r.get("cost") is None else str(r.get("cost")),
                r.get("acquired") or "", r.get("sold_date") or "",
                "" if r.get("sale_price") is None
                else str(r.get("sale_price"))]))
        self._to_clipboard("\n".join(lines), "Inputs grid copied — paste "
                                             "anywhere.")

    def _cov_add_row(self, bank, acct):
        atype = self._cov_account_type(
            [r for r in self.cov_lots if r.get("account") == acct])
        is_cash_acct = atype == "Cash"
        row = {"bank": bank, "account": acct, "account_type": atype,
               "asset": "CASH_USD" if is_cash_acct else "",
               "shares": None, "cost": 1.0 if is_cash_acct else None,
               "acquired": "",
               "sold_date": "", "sale_price": None,
               "_rid": self.cov_next_rid, "_orig": None, "_locked": False}
        self.cov_next_rid += 1
        self.cov_lots.append(row)
        self.build_data_coverage()
        self._cov_scroll_to_row(row["_rid"])

    def _cov_scroll_to_row(self, rid):
        W = self.cov_widgets.get(rid, {})
        fr = W.get("frame")
        scroll = getattr(self, "_cov_scroll", None)
        if fr is None or scroll is None:
            return
        try:
            cv = scroll._parent_canvas
            cv.update_idletasks()
            bbox = cv.bbox("all")
            if not bbox or not bbox[3]:
                return
            cv.yview_moveto(max(0.0, min(1.0, (fr.winfo_y() - 100)
                                         / bbox[3])))
        except (tk.TclError, AttributeError):
            pass

    def _cov_is_shell(self, row):
        """A staged account shell: no asset AND no shares yet. Shells are
        visible in the grid and dirty, but carry no position — Save skips
        them for lots and registers their account instead."""
        return not row.get("asset") and row.get("shares") is None

    def _cov_add_account(self):
        # Covers BOTH cases: new account under an existing bank (dropdown)
        # or under a new bank (free text). The first lot is OPTIONAL: with
        # bank + name + type only, an (empty) shell row is staged — the
        # account registers on Save. Creating stages; Save commits.
        win = ctk.CTkToplevel(self)
        win.title("Add account")
        win.transient(self)
        win.resizable(False, False)
        body = ctk.CTkFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=14)
        banks = sorted({r.get("bank") for r in self.cov_lots
                        if r.get("bank")})
        ctk.CTkLabel(body, text="Bank / Brokerage").pack(anchor="w", padx=4)
        bank_menu = ctk.CTkOptionMenu(body, width=260,
                                      values=banks + ["< new >"])
        if banks:
            bank_menu.set(banks[0])
        bank_menu.pack(anchor="w", padx=4, pady=2)
        bank_var = tk.StringVar()
        bank_ent = ctk.CTkEntry(body, width=260, textvariable=bank_var)
        if not banks:
            bank_menu.set("< new >")
            bank_ent.pack(anchor="w", padx=4, pady=2)
        ctk.CTkLabel(body, text="Account name").pack(anchor="w", padx=4,
                                                     pady=(8, 0))
        acct_var = tk.StringVar()
        ctk.CTkEntry(body, width=260, textvariable=acct_var).pack(
            anchor="w", padx=4, pady=2)
        ctk.CTkLabel(body, text="Account type (drives whether cost/dates "
                                "are required)").pack(anchor="w", padx=4,
                                                      pady=(8, 0))
        type_menu = ctk.CTkOptionMenu(body, values=pc.ACCOUNT_TYPES,
                                      width=260)
        type_menu.set("Taxable")
        type_menu.pack(anchor="w", padx=4, pady=2)
        ctk.CTkLabel(body, text="First lot — asset").pack(anchor="w", padx=4,
                                                          pady=(8, 0))
        asset_var = tk.StringVar()
        ctk.CTkEntry(body, width=260, textvariable=asset_var).pack(
            anchor="w", padx=4, pady=2)
        ctk.CTkLabel(body, text="First lot — shares").pack(anchor="w",
                                                           padx=4, pady=(8, 0))
        shares_var = tk.StringVar()
        ctk.CTkEntry(body, width=260, textvariable=shares_var).pack(
            anchor="w", padx=4, pady=2)
        msg = SelectableMsg(body, text="", text_color="orange")
        msg.pack(anchor="w", padx=4, pady=6)

        def sync_bank(*_a):
            if bank_menu.get() == "< new >" and not bank_ent.winfo_manager():
                bank_ent.pack(anchor="w", padx=4, pady=2)
            elif bank_menu.get() != "< new >" and bank_ent.winfo_manager():
                bank_ent.pack_forget()

        bank_menu.configure(command=lambda _v: sync_bank())

        def save():
            if bank_menu.get() == "< new >":
                bank = bank_var.get().strip()
                if not bank:
                    msg.configure(
                        text="Bank is required — type the new bank name.")
                    return
            else:
                bank = bank_menu.get()
            acct = acct_var.get().strip()
            if not acct:
                msg.configure(text="Account name is required.")
                return
            if any(r.get("account") == acct for r in self.cov_lots):
                msg.configure(text="That account already exists — add rows "
                                   "to its section instead.")
                return
            atype = type_menu.get()
            asset = asset_var.get().strip()
            shares_raw = shares_var.get().strip()
            # First lot is optional: neither field → shell row (account
            # registers on Save). Either field → both required + valid.
            if not asset and not shares_raw:
                shares, asset_out, cost = None, "", None
            else:
                if atype != "Cash" and not asset:
                    msg.configure(text="First-lot asset is required.")
                    return
                try:
                    shares = float(shares_raw)
                    if shares <= 0:
                        raise ValueError
                except ValueError:
                    msg.configure(
                        text="First-lot shares must be a positive number.")
                    return
                asset_out = asset or "CASH_USD"
                cost = 1.0 if atype == "Cash" else None
            is_shell = shares is None
            row = {"bank": bank, "account": acct, "account_type": atype,
                   "asset": asset_out, "shares": shares, "cost": cost,
                   "acquired": "", "sold_date": "", "sale_price": None,
                   "_rid": self.cov_next_rid, "_orig": None, "_locked": False}
            self.cov_next_rid += 1
            self.cov_lots.append(row)
            win.destroy()
            # Land on Inputs with the new account visible, staged and
            # dirty-marked — Save lives here, not in the Accounts tab.
            self.cov_filter = acct
            self.cov_guide = acct
            self.tabs.set("Data Entry")
            self.data_tabs.set("Inputs")
            self.build_data_coverage()
            self._cov_scroll_to_row(row["_rid"])
            extra = "" if (is_shell or atype != "Taxable") else \
                " — fill cost/dates first"
            self.status_var.set(
                "Account %s will be added when you press Save in "
                "Data Entry → Inputs%s." % (acct, extra))

        ctk.CTkButton(body, text="Create account", command=save).pack(
            anchor="w", padx=4, pady=8)
        win.after(50, lambda: (win.deiconify(), win.lift())
                  if win.winfo_exists() else None)

    def _cov_delete(self, rid):
        row = self._cov_row_by_rid(rid)
        if not self._confirm(
                "Delete lot",
                "Delete this lot row?\n%s — %s (%s)\nOnly this row is "
                "removed." % (row.get("account"), row.get("asset"),
                               row.get("shares")),
                ok_text="Delete"):
            return
        W = self.cov_widgets.pop(rid, {})
        try:
            if W.get("frame") is not None and W["frame"].winfo_exists():
                W["frame"].destroy()
        except tk.TclError:
            pass
        self.cov_lots = [r for r in self.cov_lots if r["_rid"] != rid]
        self._cov_rebind_nav()
        self._cov_refresh_chrome()

    def _cov_calendar(self, rid, field):
        # Hybrid entry: the field stays typeable; the picker is an
        # alternative. Header "< November 2026 >" flanks the label; the
        # year/month labels open one-action pickers. Anchored by the field,
        # never covering the edited row.
        import calendar as calmod
        W = self.cov_widgets.get(rid, {})
        var = W.get(field + "_var")
        anchor = W.get(field)
        if var is None:
            return
        try:
            cur = datetime.date.fromisoformat(var.get().strip())
        except ValueError:
            cur = datetime.date.today()
        win = ctk.CTkToplevel(self)
        win.title("Pick a date")
        win.transient(self)
        win.resizable(False, False)
        try:
            fx = anchor.winfo_rootx()
            fy = anchor.winfo_rooty() + anchor.winfo_height() + 4
        except (tk.TclError, AttributeError):
            fx, fy = self.winfo_x() + 200, self.winfo_y() + 200
        win.geometry("+%d+%d" % (fx, max(0, fy - 60)))
        state = {"y": cur.year, "m": cur.month, "view": "days"}
        header = ctk.CTkFrame(win, fg_color="transparent")
        header.pack(padx=10, pady=(10, 2))
        month_btn = ctk.CTkButton(header, width=110)
        year_btn = ctk.CTkButton(header, width=70)
        ctk.CTkButton(header, text="<", width=36,
                      command=lambda: self._cov_cal_step(state, -1, draw)
                      ).pack(side="left", padx=2)
        month_btn.pack(side="left", padx=2)
        year_btn.pack(side="left", padx=2)
        ctk.CTkButton(header, text=">", width=36,
                      command=lambda: self._cov_cal_step(state, +1, draw)
                      ).pack(side="left", padx=2)
        body = ctk.CTkFrame(win, fg_color="transparent")
        body.pack(padx=10, pady=6)

        def clear():
            for w in body.winfo_children():
                w.destroy()

        def pick_day(day):
            var.set("%04d-%02d-%02d" % (state["y"], state["m"], day))
            win.destroy()

        def draw():
            clear()
            month_btn.configure(
                text=calmod.month_name[state["m"]],
                command=lambda: show("months"))
            year_btn.configure(text=str(state["y"]),
                               command=lambda: show("years"))
            if state["view"] == "days":
                for c, wd in enumerate(["Mo", "Tu", "We", "Th", "Fr",
                                        "Sa", "Su"]):
                    ctk.CTkLabel(body, text=wd, width=36).grid(row=0,
                                                              column=c)
                r = 1
                for week in calmod.monthcalendar(state["y"], state["m"]):
                    c = 0
                    for day in week:
                        if day:
                            ctk.CTkButton(
                                body, text=str(day), width=36,
                                command=lambda d=day: pick_day(d)).grid(
                                    row=r, column=c, padx=1, pady=1)
                        c += 1
                    r += 1
            elif state["view"] == "months":
                for i in range(1, 13):
                    ctk.CTkButton(
                        body, text=calmod.month_abbr[i], width=76,
                        command=lambda m=i: choose_month(m)).grid(
                            row=(i - 1) // 3, column=(i - 1) % 3,
                            padx=2, pady=2)
            else:
                years = range(state["y"] - 15, state["y"] + 16)
                for i, yy in enumerate(years):
                    ctk.CTkButton(
                        body, text=str(yy), width=64,
                        command=lambda y=yy: choose_year(y)).grid(
                            row=i // 5, column=i % 5, padx=2, pady=2)

        def show(view):
            state["view"] = view
            draw()

        def choose_month(m):
            state["m"] = m
            state["view"] = "days"
            draw()

        def choose_year(y):
            state["y"] = y
            state["view"] = "days"
            draw()

        draw()
        win.after(50, lambda: (win.deiconify(), win.lift())
                  if win.winfo_exists() else None)

    def _cov_cal_step(self, state, delta, draw):
        m = state["m"] + delta
        state["y"] += (m - 1) // 12
        state["m"] = (m - 1) % 12 + 1
        state["view"] = "days"
        draw()

    def _cov_incomplete_required(self):
        """Accounts (taxable first) with open lots missing cost or dates.
        Only accounts holding real positions qualify — a staged shell or
        an account with zero lots has nothing to feed."""
        todo = []
        seen = set()
        for r in self.cov_lots:
            a = r.get("account")
            if a in seen or r.get("account_type") != "Taxable":
                continue
            if any(x.get("account") == a and pc.lot_status(x) == "Open"
                   and x.get("asset") and x.get("shares")
                   and x.get("asset") != pc.CASH_ASSET
                   and (x.get("cost") is None or not x.get("acquired"))
                   for x in self.cov_lots):
                todo.append(a)
                seen.add(a)
        return todo

    def _cov_guide_start(self):
        todo = self._cov_incomplete_required()
        if not todo:
            self.cov_filter = None
            self.cov_guide = "done"
            self.build_data_coverage()
            return
        self.cov_filter = todo[0]
        self.cov_guide = self.cov_filter
        self.build_data_coverage()

    def _cov_guide_next(self):
        todo = [a for a in self._cov_incomplete_required()
                if a != self.cov_filter]
        if not todo:
            self.cov_filter = None
            self.cov_guide = "done"
            self.build_data_coverage()
            return
        self.cov_filter = todo[0]
        self.cov_guide = self.cov_filter
        self.build_data_coverage()

    def _cov_show_all(self):
        self.cov_filter = None
        self.cov_guide = None
        self.build_data_coverage()

    def _cov_guide_panel(self, f):
        panel = ctk.CTkFrame(f)
        panel.pack(fill="x", padx=8, pady=2)
        if self.cov_guide == "done" and not self.cov_filter:
            if not self.cov_lots:
                # No rows at all: the grid's own No-accounts panel speaks.
                # Claiming "all fed" here would be the vacuous truth again.
                panel.pack_forget()
                return
            ctk.CTkLabel(
                panel,
                text="All required accounts fed — Show all to review the "
                     "full grid.",
                font=ctk.CTkFont(size=FS_BODY, weight="bold")).pack(
                    padx=8, pady=8, anchor="w")
            bar = ctk.CTkFrame(panel, fg_color="transparent")
            bar.pack(fill="x", padx=8, pady=(0, 6))
            ctk.CTkButton(bar, text="Show all", width=100,
                          command=self._cov_show_all).pack(side="left",
                                                          padx=4)
            return
        left = self._cov_totals()["required_left"]
        self.cov_count_lbl = ctk.CTkLabel(
            panel, text="%s left to feed" % _n(left, "position"),
            font=ctk.CTkFont(size=FS_BODY, weight="bold"))
        self.cov_count_lbl.pack(padx=8, pady=(6, 2), anchor="w")
        bank = next((r.get("bank") for r in self.cov_lots
                     if r.get("account") == self.cov_filter), "")
        if "Schwab" in (bank or ""):
            bank_label = "Schwab"
        elif "Vanguard" in (bank or ""):
            bank_label = "Vanguard"
        else:
            bank_label = "your broker"
        lines = [
            "Feeding this account: %s" % self.cov_filter,
            "Fill the rows below from this one broker statement, then "
            "press Save. The full grid stays available via Show all.",
            "",
        ]
        if "Schwab" in (bank or "") or "Vanguard" in (bank or ""):
            lines.append("Where each number lives (%s):" % bank_label)
            for g in BROKER_GUIDE:
                if g["field"] in ("bank", "account", "account_type"):
                    continue
                where = g["schwab"] if "Schwab" in (bank or "") \
                    else g["vanguard"]
                lines.append("• %s — %s (example: %s)" % (
                    g["field"], where, g["example"]))
        else:
            # One pattern for every other broker — stated once, not repeated
            # on all six lines.
            lines.append("Where each number lives: open lots under "
                         "Holdings/Positions → Cost basis/Lots; sold lots "
                         "under History/Realized gains (the year-end 1099-B "
                         "is the authority).")
            for g in BROKER_GUIDE:
                if g["field"] in ("bank", "account", "account_type"):
                    continue
                lines.append("• %s — %s (example: %s)" % (
                    g["field"], g["concept"], g["example"]))
        self._selectable_note(panel, "\n".join(lines))
        bar = ctk.CTkFrame(panel, fg_color="transparent")
        bar.pack(fill="x", padx=8, pady=(0, 6))
        ctk.CTkButton(bar, text="Next account", width=130,
                      command=self._cov_guide_next).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="Show all", width=100,
                      command=self._cov_show_all).pack(side="left", padx=4)

    def set_account_type(self, account, atype):
        for lot in self.lots:
            if lot["account"] == account:
                lot["account_type"] = atype
        if getattr(self, "cov_lots", None) is not None and self._cov_counts():
            self.status_var.set(
                "Save or discard Inputs edits first.")
            self.tabs.set("Data Entry")
            self.data_tabs.set("Inputs")
            return
        self.lots_changed_externally("Account type updated for %s." % account)

    # ---- Coverage staged editing: typing NEVER recomputes ----
    def _cov_reset(self):
        self.cov_lots = []
        for i, lot in enumerate(self.lots):
            row = dict(lot)
            row["_rid"] = i
            row["_orig"] = i
            row["_locked"] = True
            self.cov_lots.append(row)
        self.cov_next_rid = len(self.lots)
        # A filter naming an account with no rows is stale (e.g. after
        # delete-all or an upload that fed it) — the panel would show a
        # ghost account with nothing below it. Re-point at real work.
        have = {r.get("account") for r in self.cov_lots}
        if getattr(self, "cov_filter", None) not in have:
            self.cov_filter = None
        if getattr(self, "cov_guide", None) not in (None, "done") and \
                self.cov_guide not in have:
            todo = self._cov_incomplete_required()
            if todo:
                self.cov_filter = todo[0]
                self.cov_guide = todo[0]
            else:
                self.cov_guide = "done"
        # Completion state follows the work: new required lots (upload,
        # new account) re-point a finished guide at the first account
        # left to feed. Show-all (guide None) is never disturbed.
        if getattr(self, "cov_guide", None) == "done":
            todo = self._cov_incomplete_required()
            if todo:
                self.cov_filter = todo[0]
                self.cov_guide = todo[0]

    def _cov_stripped(self, row):
        return {k: v for k, v in row.items() if not k.startswith("_")}

    def _cov_counts(self):
        dirty = 0
        for row in self.cov_lots:
            if row["_orig"] is None:
                dirty += 1
            elif self._cov_stripped(row) != self._cov_stripped(
                    self.lots[row["_orig"]]):
                dirty += 1
        present = {r["_orig"] for r in self.cov_lots
                   if r["_orig"] is not None}
        deleted = len(self.lots) - len(present)
        return dirty + deleted

    def _template_more(self, choice):
        # Secondary Template actions live in the More menu so the button
        # row fits a 960px split-screen window. Reset the menu label after
        # each pick.
        try:
            # No Import broker CSV: it duplicated Upload (both accept only
            # template-shaped files) — the template is the one way in.
            {"Paste rows": self.paste_rows,
             "Copy AI prompt": self.copy_ai_prompt}[choice]()
        finally:
            try:
                self.template_more_menu.set("More ▾")
            except (tk.TclError, AttributeError):
                pass

    def build_data_template(self):
        f = self._clear_data_tab("Template")
        self._selectable_note(
            f, "Two ways to fill the template\n"
               "1. Yourself — press Download Template (or one account's "
               "download from Inputs), fill one row per lot, then press "
               "Upload.\n"
               "2. With AI — paste broker screenshots into ChatGPT, Muse, "
               "Gemini or any AI together with the Copy-AI-prompt text, "
               "then upload the CSV it returns.\n"
               "Open lots leave sold_date and sale_price_per_share blank. "
               "Uploads upsert by lot key (account + asset + acquired date "
               "+ cost): matches update, new rows insert, uploads NEVER "
               "delete rows. Uploads need NOT be complete — they merge. To "
               "replace a dataset entirely, delete all data first "
               "(Danger Zone — wipes lots, settings, drift log, price "
               "cache and the account registry), then upload.",
            padx=8, pady=8, fill="x")
        bar = ctk.CTkFrame(f, fg_color="transparent")
        bar.pack(fill="x", padx=8, pady=4)
        ctk.CTkButton(bar, text="Download Template",
                      command=self.download_full_template).pack(
                          side="left", padx=4)
        ctk.CTkButton(bar, text="Download Data",
                      command=self.download_filled_template).pack(
                          side="left", padx=4)
        ctk.CTkButton(bar, text="Upload",
                      command=self.upload_template).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="Backup",
                      command=self.backup_now).pack(side="left", padx=4)
        restore_btn = ctk.CTkButton(bar, text="Restore",
                                        command=self.restore_backup)
        restore_btn.pack(side="left", padx=4)
        self._tooltip(restore_btn, "Restore: pick an encrypted backup "
                                    "set and replace current data with it.")
        self.template_more_menu = ctk.CTkOptionMenu(
            bar, values=["Paste rows", "Copy AI prompt"],
            command=self._template_more, width=110)
        self.template_more_menu.set("More ▾")
        self.template_more_menu.pack(side="left", padx=4)
        ctk.CTkLabel(
            f, text="Download Data: your current data, filled into the "
                   "lots-only CSV template — upload it into another copy "
                   "of the app. Backup: one-click ENCRYPTED backup of the "
                   "whole data set (lots, settings, drift, prices, "
                   "registry) as JSON into your remembered cloud folder "
                   "(passphrase asked every time, never stored). Restore: "
                   "pick a set and replace current data with it. Upload "
                   "stays CSV; backups are JSON throughout.",
            text_color=CLR_SECONDARY, wraplength=860,
            anchor="w").pack(padx=12, anchor="w")
        stamp = self.profile.get("last_backup_time")
        stamp_path = self.profile.get("last_backup_path")
        stamp_row = ctk.CTkFrame(f, fg_color="transparent")
        stamp_row.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(
            stamp_row,
            text=("Last backup: %s → %s" % (stamp, stamp_path)
                  if stamp and stamp_path else "No backups yet."),
            text_color=CLR_SECONDARY, wraplength=640,
            anchor="w").pack(side="left")
        ctk.CTkButton(stamp_row, text="Change backup folder", width=160,
                      command=self.change_backup_folder).pack(side="left",
                                                              padx=8)
        self.template_msg = SelectableMsg(f, text="")
        self.template_msg.pack(padx=8, pady=4, anchor="w")
        ctk.CTkLabel(f, text="Where to find each field at your broker:",
                     font=ctk.CTkFont(weight="bold")).pack(padx=8, pady=(8, 2),
                                                           anchor="w")
        # One scrollable text block, not per-cell labels (fast scrolling).
        guide = ctk.CTkTextbox(f, wrap="word")
        self._scroll_keep["template_guide"] = guide
        guide.pack(fill="both", expand=True, padx=8, pady=4)
        lines = []
        for g in BROKER_GUIDE:
            lines.append("%s — %s" % (g["field"], g["concept"]))
            lines.append("  Schwab: %s" % g["schwab"])
            lines.append("  Vanguard: %s" % g["vanguard"])
            lines.append("  Example: %s" % g["example"])
            lines.append("")
        lines.append(
            "Which broker export to start from (read this before "
            "exporting):")
        lines.append(
            "  Schwab — open lots: Positions → Cost Basis $ / Lot Details "
            "→ export. Sold lots: Realized Gain/Loss → Export Lot Details.")
        lines.append(
            "  Vanguard — Cost basis → Unrealized / Realized → Show lot "
            "details → Export (top-right of the table).")
        lines.append(
            "  The template is the one way in: Upload accepts ONLY a file "
            "shaped like the template (this exact header row: "
            "bank,account,account_type,asset,shares,cost_per_share,"
            "acquired_date,sold_date,sale_price_per_share). A raw "
            "Schwab/Vanguard export has different columns, so reshape it "
            "to the template first — by hand or with the Copy AI prompt — "
            "then Upload it. With thousands of institutions, each with its "
            "own format, no auto-mapping is built; nothing is ever "
            "guessed.")
        lines.append(
            "  Combine ALL accounts into ONE template file and run ONE "
            "upload — uploads upsert by lot key, so one complete file "
            "beats several partial ones.")
        lines.append(
            "  Caveats that are normal, not errors: Vanguard provides no "
            "cost basis for IRA accounts, so blank IRA cost is expected. "
            "The year-end 1099-B is the authority for sold lots.")
        lines.append(
            "  Other brokers (Wells, Chase, Coinbase, Cash App, Health "
            "Equity): same concepts — Holdings/Positions → Cost basis/Lots "
            "for open lots; History/Realized gains for closed lots.")
        lines.append("")
        guide.insert("1.0", "\n".join(lines))
        # Read-only but mouse-selectable (Ctrl+C works): a disabled box
        # cannot be selected at all. Typing/paste/cut are blocked below;
        # navigation, selection and Control shortcuts stay live.
        _tb = guide._textbox

        def _guide_key(e):
            if e.state & 0x4:  # Control held: copy, select-all, etc.
                return None
            if e.keysym in ("Left", "Right", "Up", "Down", "Home", "End",
                            "Prior", "Next"):
                return None
            return "break"

        _tb.bind("<KeyPress>", _guide_key, add="+")
        for _seq in ("<<Cut>>", "<<Paste>>"):
            _tb.bind(_seq, lambda e: "break", add="+")

    def copy_ai_prompt(self):
        self.clipboard_clear()
        self.clipboard_append(AI_TEMPLATE_PROMPT)
        self.template_msg.configure(
            text="AI prompt copied — paste it with broker screenshots into "
                 "ChatGPT, Muse, Gemini, or any AI, then upload the CSV here.")

    def _ingest_rows(self, rows, source):
        """Validate-then-merge path shared by upload, paste, and import.
        Returns an error string, or the upsert breakdown: matching rows
        UPDATE (already existed), new rows INSERT — uploads never delete.
        A duplicate upload reads e.g. '31 rows: 31 updated, 0 inserted'."""
        errors = pc.validate_lot_rows(rows, existing=self.lots)
        if errors:
            shown = "\n".join(errors[:12])
            if len(errors) > 12:
                shown += "\n… and %d more" % (len(errors) - 12)
            return "REJECTED — nothing changed:\n%s" % shown
        merged, ins, derrs = pc.merge_upload(self.lots, rows)
        if derrs:
            return "REJECTED — nothing changed:\n%s" % "\n".join(derrs)
        updated = len(rows) - len(ins)
        self.lots = merged
        # The popup carries the full detail (file + counts); the message
        # lines keep only the short summary — the full path is what
        # truncates the top status row, so it must not go there.
        full, short = pc.upload_result_text(len(rows), updated, len(ins),
                                            source)
        self.lots_changed_externally(short)
        # Values appear without a manual step: reuse the manual Refresh
        # worker exactly (same fetch, progress, guard, error surfacing).
        # Skip silently when one is already running — the guard's own
        # status line would clobber the ingest summary.
        if not self._refreshing:
            self.refresh_async()
        self._notify("Upload complete", full)
        return short

    def paste_rows(self):
        try:
            text = self.clipboard_get()
        except tk.TclError:
            self.template_msg.configure(text="Clipboard is empty.")
            return
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if not lines:
            self.template_msg.configure(text="Clipboard has no rows.")
            return
        delim = "\t" if "\t" in lines[0] else ","
        try:
            rows = list(csv.DictReader(lines, delimiter=delim))
        except csv.Error as e:
            self.template_msg.configure(text="Cannot parse clipboard: %s" % e)
            return
        norm = {(k or "").strip().lower(): k for k in (rows[0] if rows else {})}
        if "account" not in norm or "asset" not in norm:
            self.template_msg.configure(
                text="Clipboard needs the template header row (bank, "
                     "account, …) — copy it from the downloaded template.")
            return
        fixed = [{(k.strip().lower() if k.strip().lower() in
                   set(pc.LOT_FIELDS) else k): v for k, v in r.items()}
                 for r in rows]
        msg = self._ingest_rows(fixed, "clipboard")
        self.template_msg.configure(text=msg)

    # import_broker_csv was deleted (Prompt 7): it duplicated Upload —
    # both accepted only template-shaped files, so the menu item only
    # confused. The template is the one way in (Upload).
    def _write_template_csv(self, path, lots):
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=pc.LOT_FIELDS)
            w.writeheader()
            w.writerows(self._template_row_dicts(lots))

    def download_full_template(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile="portfolio-template.csv")
        if path:
            self._write_template_csv(path, [])
            self.template_msg.configure(
                text="Wrote header-only template to %s" % path)

    def _downloads_dir(self):
        """Default folder for the filled-template save dialog: the user's
        Downloads folder — never the repo folder."""
        d = os.path.join(os.path.expanduser("~"), "Downloads")
        if os.path.isdir(d):
            return d
        return os.path.expanduser("~")

    def _ensure_saved(self, action):
        """Saved-state gate shared by download and backup: with unsaved
        Inputs edits, offer Save-first / saved-state-only / Cancel.
        Returns True when the export may proceed."""
        self._ensure_cov_state()
        if not self._cov_counts():
            return True
        choice = self._confirm3(
            "Unsaved edits",
            "The Inputs grid has unsaved edits.\n\n"
            "Save first, then %s — or %s the last saved state "
            "(unsaved edits excluded)?" % (action, action.capitalize()),
            ["Save first", "%s saved state" % action.capitalize(),
             "Cancel"])
        if choice == 2:
            return False
        if choice == 0 and not self._cov_save():
            self.template_msg.configure(
                text="%s cancelled — fix the flagged rows, "
                     "then save." % action.capitalize())
            return False
        return True

    def download_filled_template(self):
        """Download the full dataset (open + closed lots, all accounts)
        as a plain CSV in the exact template format, so it can be fed to
        another copy of the app via Upload. Exports the
        last SAVED state: unsaved Inputs edits trigger a
        Save & Download / Download saved state / Cancel choice."""
        if not self._ensure_saved("download"):
            return
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialdir=self._downloads_dir(),
            initialfile="filled-template-%s.csv" % stamp)
        if path:
            self._write_template_csv(path, self.lots)
            self.template_msg.configure(
                text="Wrote %s with your current data to %s"
                     % (_n(len(self.lots), "row"), path))

    def _cloud_roots(self):
        """Known cloud-sync roots that actually exist on this machine."""
        import glob as _glob
        home = os.path.expanduser("~")
        cands = [os.path.join(home, n) for n in
                 ("Google Drive", "OneDrive", "Dropbox", "iCloudDrive")]
        cands += _glob.glob(os.path.join(home, "OneDrive*"))
        for drive in ("G", "H", "I", "J", "K", "L"):
            # Drive for Desktop mounts a virtual drive (default G:).
            cands.append("%s:\\My Drive" % drive)
        return [os.path.normcase(os.path.abspath(c)) for c in cands
                if os.path.isdir(c)]

    def _is_cloud_path(self, path):
        mine = os.path.normcase(os.path.abspath(path or ""))
        return any(mine == r or mine.startswith(r + os.sep)
                   for r in self._cloud_roots())

    def _cloud_default_dir(self):
        roots = self._cloud_roots()
        if roots:
            return roots[0]
        return self._downloads_dir()

    def change_backup_folder(self):
        folder = filedialog.askdirectory(
            initialdir=self._cloud_default_dir(),
            title="Pick a backup folder — a cloud-synced folder "
                  "(Drive/OneDrive/Dropbox) carries sets to other machines")
        if not folder:
            return
        if not self._is_cloud_path(folder) and not self._confirm(
                "Not a cloud folder",
                "This folder is not under a known cloud sync root "
                "(Google Drive, OneDrive, Dropbox). A backup here dies "
                "with this machine.\nUse it anyway?",
                ok_text="Use anyway"):
            return
        self.profile["backup_folder"] = folder
        pc.save_profile(PROFILE_JSON, self.profile)
        self.refresh_data_window()
        self.status_var.set("Backup folder set to %s." % folder)

    def _template_row_dicts(self, lots):
        """CSV-shaped string dicts — the exact template format (blanks stay
        blank). Shared by the CSV writer and the JSON backup set, so a
        backup's lots validate and restore through the same path."""
        return [{
            "bank": lot.get("bank", ""),
            "account": lot.get("account", ""),
            "account_type": lot.get("account_type", ""),
            "asset": lot.get("asset", ""),
            "shares": "" if lot.get("shares") is None
            else lot["shares"],
            "cost_per_share": "" if lot.get("cost") is None
            else lot["cost"],
            "acquired_date": lot.get("acquired", ""),
            "sold_date": lot.get("sold_date", ""),
            "sale_price_per_share": ""
            if lot.get("sale_price") is None else lot["sale_price"]}
            for lot in lots]

    def _ask_passphrase(self, title, confirm=False):
        """Masked passphrase prompt. Never stored, never logged, never in
        the repo. Returns the passphrase, or None on cancel."""
        win = ctk.CTkToplevel(self)
        win.title(title)
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()
        win.lift()
        SelectableMsg(win, text="Type the backup passphrase. It is never "
                                "stored — lose it and the set cannot be "
                                "restored.").pack(
            padx=16, pady=(14, 6), anchor="w", fill="x")
        ents = []
        for label in (("Passphrase", "Confirm passphrase") if confirm
                      else ("Passphrase",)):
            ctk.CTkLabel(win, text=label).pack(anchor="w", padx=16)
            ent = ctk.CTkEntry(win, width=300, show="*")
            ent.pack(anchor="w", padx=16, pady=(0, 8))
            ents.append(ent)
        result = {"pw": None}
        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(0, 14))

        def _ok():
            first = ents[0].get()
            if confirm and first != ents[1].get():
                SelectableMsg(win, text="Passphrases do not match — "
                                        "retype both.",
                              text_color="orange").pack(padx=16, pady=4)
                return
            if not first:
                SelectableMsg(win, text="Empty passphrase — type one or "
                                        "Cancel.",
                              text_color="orange").pack(padx=16, pady=4)
                return
            result["pw"] = first
            for ent in ents:
                ent.delete(0, "end")
            win.destroy()

        ctk.CTkButton(bar, text="OK", width=120,
                      command=_ok).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bar, text="Cancel", width=120,
                      command=win.destroy).pack(side="left")
        try:
            ents[0].focus_set()
        except tk.TclError:
            pass
        self.wait_window(win)
        return result["pw"]

    def _read_json_file(self, path, default):
        try:
            with open(path) as fh:
                return json.load(fh)
        except (ValueError, OSError):
            return default

    def backup_now(self):
        """One-click ENCRYPTED JSON backup of the whole data set (lots,
        settings, drift log, price cache, account registry) as a
        timestamped set in the remembered backup folder. Sets accumulate
        — never overwritten. The folder must be cloud-synced (Drive for
        now): the chooser defaults to a cloud root and warns on a local
        folder. The passphrase is asked every time, never stored.
        Backup = whole app state as encrypted JSON; Download Data stays
        the lots-only CSV exchange format."""
        if not self._ensure_saved("back up"):
            return
        folder = self.profile.get("backup_folder") or ""
        if not folder or not os.path.isdir(folder):
            folder = filedialog.askdirectory(
                initialdir=self._cloud_default_dir(),
                title="Pick a backup folder — a cloud-synced folder "
                      "(Drive/OneDrive/Dropbox) carries sets to other "
                      "machines)")
            if not folder:
                return
            if not self._is_cloud_path(folder) and not self._confirm(
                    "Not a cloud folder",
                    "This folder is not under a known cloud sync root. "
                    "A backup here dies with this machine.\nUse it anyway?",
                    ok_text="Use anyway"):
                return
            self.profile["backup_folder"] = folder
        pw = self._ask_passphrase("Backup passphrase", confirm=True)
        if not pw:
            self.template_msg.configure(
                text="Backup cancelled — no passphrase, nothing written.")
            return
        drift_rows = []
        try:
            with open(DRIFT_LOG, newline="") as fh:
                drift_rows = list(csv.DictReader(fh))
        except OSError:
            pass
        datasets = {
            "lots": self._template_row_dicts(self.lots),
            "profile": dict(self.profile),
            "drift": drift_rows,
            "prices": self._read_json_file(CACHE, {}),
            "accounts": self._read_json_file(ACCOUNTS_JSON,
                                             {"accounts": []}),
            "_passphrase": pw,
        }
        try:
            keyparams, enc = pc.backup_encrypt(datasets)
        except (ValueError, RuntimeError) as e:
            self.template_msg.configure(text="Backup failed: %s" % e)
            return
        finally:
            datasets["_passphrase"] = ""
            del pw
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
        setdir = os.path.join(folder, "backup-%s" % stamp)
        try:
            os.makedirs(setdir)
            with open(os.path.join(setdir, "keyparams.json"), "w") as fh:
                json.dump(keyparams, fh, indent=1, sort_keys=True)
            for name in pc.BACKUP_DATASETS:
                with open(os.path.join(setdir, name + ".json.enc"),
                          "wb") as fh:
                    fh.write(enc[name])
        except OSError as e:
            import shutil as _shutil
            _shutil.rmtree(setdir, ignore_errors=True)
            self.template_msg.configure(text="Backup failed: %s" % e)
            return
        self.profile["last_backup_time"] = stamp[:8] + " " + stamp[9:]
        self.profile["last_backup_path"] = setdir
        pc.save_profile(PROFILE_JSON, self.profile)
        self.refresh_data_window()
        self.template_msg.configure(
            text="Backed up %s + settings + drift + prices + registry "
                 "(encrypted) to %s" % (_n(len(self.lots), "row"), setdir))

    def _backup_sets(self, folder):
        """Timestamped set dirs in the folder, newest first. A valid set
        holds keyparams.json plus one .json.enc per data set."""
        sets = []
        try:
            names = sorted(os.listdir(folder), reverse=True)
        except OSError:
            return sets
        for name in names:
            setdir = os.path.join(folder, name)
            if not (name.startswith("backup-")
                    and os.path.isdir(setdir)):
                continue
            if not os.path.isfile(os.path.join(setdir, "keyparams.json")):
                continue
            if all(os.path.isfile(os.path.join(
                    setdir, n + ".json.enc")) for n in pc.BACKUP_DATASETS):
                sets.append(name)
        return sets

    def restore_backup(self):
        """Restore an encrypted JSON backup set: pick a set, retype its
        passphrase, validate EVERYTHING first — a corrupt set or wrong
        passphrase errors plainly with current data untouched — then
        replace all five data files and rebuild. Backup-first is offered
        when no set exists from today."""
        folder = self.profile.get("backup_folder") or ""
        if not folder or not os.path.isdir(folder):
            self.template_msg.configure(
                text="No backup folder set — press Backup first (it asks "
                     "for the folder).")
            return
        sets = self._backup_sets(folder)
        if not sets:
            self.template_msg.configure(
                text="No backup sets in %s yet — press Backup first."
                % folder)
            return
        win = ctk.CTkToplevel(self)
        win.title("Restore backup")
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()
        win.lift()
        SelectableMsg(win, text="Pick a backup set. Restoring REPLACES "
                                "current lots, settings, drift log, price "
                                "cache and the account registry.").pack(
            padx=16, pady=(14, 6), anchor="w", fill="x")
        menu = ctk.CTkOptionMenu(win, values=sets, width=300)
        menu.set(sets[0])
        menu.pack(anchor="w", padx=16, pady=4)
        picked = {"name": sets[0]}

        def _go():
            picked["name"] = menu.get()
            win.destroy()

        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkButton(bar, text="Next", width=120,
                      command=_go).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bar, text="Cancel", width=120,
                      command=win.destroy).pack(side="left")
        self.wait_window(win)
        setname = picked.get("name")
        if not setname:
            return
        setdir = os.path.join(folder, setname)
        pw = self._ask_passphrase("Restore passphrase for %s" % setname)
        if not pw:
            self.template_msg.configure(
                text="Restore cancelled — current data untouched.")
            return
        try:
            with open(os.path.join(setdir, "keyparams.json")) as fh:
                keyparams = json.load(fh)
            payloads = {}
            for name in pc.BACKUP_DATASETS:
                with open(os.path.join(setdir, name + ".json.enc"),
                          "rb") as fh:
                    payloads[name] = fh.read()
            data = pc.backup_decrypt(keyparams, payloads, pw)
        except (ValueError, OSError, RuntimeError) as e:
            self.template_msg.configure(
                text="Restore failed: %s Current data untouched." % e)
            return
        finally:
            del pw
        # Validate EVERYTHING before touching a single file.
        problems = pc.validate_lot_rows(data.get("lots") or [])
        if not isinstance(data.get("profile"), dict):
            problems.append("settings set is corrupt")
        if not isinstance(data.get("accounts"), dict) or \
                not isinstance(data.get("accounts", {}).get("accounts"),
                               list):
            problems.append("account registry set is corrupt")
        if not isinstance(data.get("drift"), list):
            problems.append("drift-log set is corrupt")
        if not isinstance(data.get("prices"), dict):
            problems.append("price-cache set is corrupt")
        if problems:
            shown = "\n".join(problems[:8])
            self.template_msg.configure(
                text="Restore failed — set invalid, current data "
                     "untouched:\n%s" % shown)
            return
        today = datetime.date.today().strftime("%Y%m%d")
        if not any(s.startswith("backup-" + today) for s in sets):
            choice = self._confirm3(
                "No backup from today",
                "No backup set exists from today. Back up the current "
                "data first, so it is recoverable?",
                ["Back up current data first",
                 "Restore without backing up", "Cancel"])
            if choice == 2:
                self.template_msg.configure(
                    text="Restore cancelled — current data untouched.")
                return
            if choice == 0:
                self.backup_now()
                if (self.profile.get("last_backup_time") or "")[:8] \
                        != today:
                    self.template_msg.configure(
                        text="Restore cancelled (backup did not "
                             "complete) — current data untouched.")
                    return
        if not self._confirm(
                "Restore backup",
                "Restore %s?\nReplaces current lots, settings, drift "
                "log, price cache and the account registry." % setname,
                ok_text="Restore"):
            self.template_msg.configure(
                text="Restore cancelled — current data untouched.")
            return
        try:
            with open(PORTFOLIO_CSV, "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=pc.LOT_FIELDS)
                w.writeheader()
                w.writerows(data["lots"])
            prof = dict(pc.PROFILE_DEFAULTS)
            prof.update(data["profile"])
            prof["backup_folder"] = folder
            prof["last_backup_time"] = today[:4] + "-" + today[4:6] + \
                "-" + today[6:] + " (restored %s)" % setname
            prof["last_backup_path"] = setdir
            pc.save_profile(PROFILE_JSON, prof)
            with open(DRIFT_LOG, "w", newline="") as fh:
                w = csv.DictWriter(
                    fh, fieldnames=["date", "liquid", "home",
                                    "actual_total", "standard_total"])
                w.writeheader()
                w.writerows(data["drift"])
            with open(CACHE, "w") as fh:
                json.dump(data["prices"], fh, indent=1, sort_keys=True)
            pc.save_accounts(ACCOUNTS_JSON,
                             data["accounts"]["accounts"])
        except OSError as e:
            self.template_msg.configure(
                text="Restore failed mid-write: %s — re-upload or "
                     "restore an older set." % e)
            return
        # Reload in-memory state from the restored files (same files the
        # features themselves read), then rebuild everything.
        self.lots = [pc.row_to_lot(r) for r in data["lots"]]
        self.profile = prof
        self.accounts = pc.load_accounts(ACCOUNTS_JSON)
        self.prices = pc.load_price_cache(CACHE)
        self.watch = pc.load_watchlist_cache(CACHE)
        self._sync_home()
        self._hold_expanded = set()
        self._liq_expanded = set()
        self._cov_reset()
        self.cov_filter = None
        self.cov_guide = None
        self.recompute()
        self.build_all()
        self.refresh_data_window()
        self.template_msg.configure(
            text="Restored %s: %s + settings + drift + prices + "
                 "registry. Verify the numbers, then Refresh stocks."
                 % (setname, _n(len(self.lots), "row")))
        self.status_var.set("Restored backup %s." % setname)

    def download_account_template(self, account):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile="%s-template.csv" % "".join(
                c if c.isalnum() else "_" for c in account))
        if path:
            self._write_template_csv(
                path, [l for l in self.lots if l["account"] == account])
            self.template_msg.configure(
                text="Wrote %s's rows to %s" % (account, path))

    def upload_template(self):
        path = filedialog.askopenfilename(
            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            with open(path, newline="") as fh:
                rows = list(csv.DictReader(fh))
        except OSError as e:
            self.template_msg.configure(text="Cannot read file: %s" % e)
            return
        self._busy("Uploading %d rows…" % len(rows))
        try:
            msg = self._ingest_rows(rows, path)
        finally:
            self._idle()
        # _ingest_rows → save_lots rebuilds this tab, so write to the
        # fresh label.
        self.template_msg.configure(text=msg)

    def open_settings(self):
        # Formerly the Profile sub-tab: same fields and same save
        # semantics, now a dialog under the ☰ menu. Spending figures are
        # COMPUTED (Overview radar), never entered: Settings holds only
        # the policy inputs (Medi-Cal ceiling, other income, employer
        # cover, insurance, AGI threshold) plus identity/property fields.
        # Fixed footer: Save/Cancel live outside the scrollable, so they
        # stay on screen at any size; the fields scroll above. Dialog
        # height never exceeds the viewport.
        win = ctk.CTkToplevel(self)
        win.title("Settings")
        win.transient(self)
        win.resizable(False, False)
        try:
            max_h = max(480, self.winfo_screenheight() - 160)
        except tk.TclError:
            max_h = 720
        win.geometry("620x%d" % min(720, max_h))
        # Footer FIRST (side=bottom): the expanding body must never win
        # the space race. Packing the body first starved the footer and
        # pushed Save/Export/Import below the visible dialog on short
        # (768px) screens. Placed first, the footer always keeps its
        # space and the body takes only the remainder and scrolls.
        foot = ctk.CTkFrame(win, fg_color="transparent")
        foot.pack(fill="x", side="bottom", padx=10, pady=(4, 10))
        msg = SelectableMsg(foot, text="", text_color="orange")
        msg.pack(anchor="w", padx=4, pady=(0, 4))
        body = ctk.CTkScrollableFrame(win, width=580, height=440)
        body.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        entries = {}
        fields = [("date_of_birth", "Date of birth (YYYY-MM or YYYY-MM-DD)"),
                  ("ss_owner_monthly", "Owner Social Security $/mo"),
                  ("ss_spouse_monthly", "Spouse Social Security $/mo"),
                  ("magi_ceiling_annual",
                   "Medi-Cal MAGI ceiling $/yr (blank = no cap derived)"),
                  ("other_annual_income",
                   "Other annual income $/yr — W-2/pension "
                   "(blank = none)"),
                  ("private_insurance_per_person_mo",
                   "Private insurance $/person/mo if Medi-Cal lost"),
                  ("after65_agi_threshold",
                   "After-65 federal-tax-free AGI threshold $/yr"),
                  ("other_realized_gains_current_year",
                   "Other realized gains this year $ (pre-app history)"),
                  ("other_realized_gains_note", "Source note for the above"),
                  ("home_purchase_price",
                   "Home purchase price $ (optional — Holdings gain %)"),
                  ("cap_note", "Cap context note (shown next to budget)")]
        for key, label in fields:
            ctk.CTkLabel(body, text=label).pack(anchor="w", padx=4,
                                                pady=(6, 0))
            ent = ctk.CTkEntry(body, width=380)
            val = self.profile.get(key, "")
            ent.insert(0, "" if val is None else str(val))
            ent.pack(anchor="w", padx=4, pady=2)
            entries[key] = ent
        # Employer cover is yes/no, not a number: a checkbox, saved as a
        # bool. When on, the Medi-Cal MAGI section is not applicable.
        employer_var = tk.BooleanVar(
            value=bool(self.profile.get("employer_medical_cover")))
        ctk.CTkCheckBox(body, text="Employer medical cover (Medi-Cal "
                                   "MAGI section N/A when on)",
                        variable=employer_var).pack(anchor="w", padx=4,
                                                    pady=(8, 2))
        # ---- Properties: addresses live here; the RentCast key too.
        # Refresh (hamburger menu) pulls each estimate and SHOWS it —
        # nothing is replaced until the user accepts it or types a value
        # and presses Save settings. Redfin/Zillow enter through the
        # manual applied value (check in the browser, type the number).
        ctk.CTkLabel(body, text="Properties",
                     font=ctk.CTkFont(weight="bold")).pack(
                         anchor="w", padx=4, pady=(10, 0))
        prop_box = ctk.CTkFrame(body, fg_color="transparent")
        prop_box.pack(fill="x", padx=4, pady=2)
        prop_rows = []

        def add_prop_row(prop=None):
            prop = dict(prop or {})
            frame = ctk.CTkFrame(prop_box)
            frame.pack(fill="x", pady=3)
            ctk.CTkLabel(frame, text="Address (Street, City, State, Zip)").pack(
                anchor="w", padx=4)
            addr = ctk.CTkEntry(frame, width=380)
            addr.insert(0, prop.get("address") or "")
            addr.pack(anchor="w", padx=4, pady=2)
            line = ctk.CTkFrame(frame, fg_color="transparent")
            line.pack(fill="x", padx=4, pady=2)
            ctk.CTkLabel(line, text="Applied $").pack(side="left")
            applied = ctk.CTkEntry(line, width=130)
            try:
                cur = float(prop.get("applied_value") or 0)
                if cur:
                    applied.insert(0, str(prop.get("applied_value")))
            except (TypeError, ValueError):
                pass
            applied.pack(side="left", padx=4)
            last = prop.get("last_estimate")
            last_txt = ("Last: %s (%s, %s)" % (
                money(last), prop.get("last_source") or "?",
                prop.get("last_asof") or "?")) if last else "No estimate yet."
            ctk.CTkLabel(line, text=last_txt,
                         text_color=CLR_SECONDARY).pack(side="left", padx=4)

            def remove():
                frame.destroy()
                prop_rows[:] = [r for r in prop_rows if r["frame"] != frame]

            ctk.CTkButton(frame, text="Remove", width=90,
                          command=remove).pack(anchor="w", padx=4, pady=2)
            prop_rows.append({"frame": frame, "addr": addr,
                             "applied": applied, "last": prop})

        # One address row is always present: with zero saved properties
        # the empty row keeps adding a property visible without scrolling,
        # and blank-address rows never persist (skipped on save).
        for _p in self._properties() or [None]:
            add_prop_row(_p)
        ctk.CTkButton(body, text="Add property", width=140,
                      command=lambda: add_prop_row()).pack(
                          anchor="w", padx=4, pady=4)
        ctk.CTkLabel(
            body,
            text="RentCast API key (free Developer tier — key only, "
                 "never an address)").pack(anchor="w", padx=4, pady=(6, 0))
        key_ent = ctk.CTkEntry(body, width=380)
        key_ent.insert(0, self.profile.get("rentcast_key") or "")
        key_ent.pack(anchor="w", padx=4, pady=2)
        self._selectable_note(
            body, "Refresh home estimates (hamburger menu) pulls the "
                  "RentCast estimate per property and shows it next to "
                  "the applied value — accepting or typing a value and "
                  "saving is what applies it. No key: Refresh shows a "
                  "hint, nothing breaks.",
            padx=4, pady=4, fill="x")
        note = self._selectable_note(body, self._settings_summary_text(),
                                     padx=4, pady=4, fill="x")

        def save():
            try:
                self.profile["date_of_birth"] = \
                    entries["date_of_birth"].get().strip()
                self.profile["ss_owner_monthly"] = float(
                    entries["ss_owner_monthly"].get() or 0)
                self.profile["ss_spouse_monthly"] = float(
                    entries["ss_spouse_monthly"].get() or 0)
                def _nblank(key):
                    raw = entries[key].get().strip().replace(",",
                                                             "").replace(
                                                                 "$", "")
                    return None if not raw else float(raw)

                # Policy inputs for the computed figures. Blanks mean
                # unset (no cap, no threshold) — never a hidden zero rule.
                self.profile["magi_ceiling_annual"] = _nblank(
                    "magi_ceiling_annual")
                self.profile["other_annual_income"] = float(
                    entries["other_annual_income"].get().strip().replace(
                        ",", "").replace("$", "") or 0)
                self.profile["private_insurance_per_person_mo"] = float(
                    entries["private_insurance_per_person_mo"].get().strip(
                    ).replace(",", "").replace("$", "") or 0)
                self.profile["after65_agi_threshold"] = _nblank(
                    "after65_agi_threshold")
                self.profile["employer_medical_cover"] = bool(
                    employer_var.get())
                self.profile["other_realized_gains_current_year"] = float(
                    entries["other_realized_gains_current_year"].get() or 0)
                self.profile["other_realized_gains_note"] = \
                    entries["other_realized_gains_note"].get().strip()
                home_raw = entries["home_purchase_price"].get().strip()
                self.profile["home_purchase_price"] = \
                    "" if not home_raw else float(home_raw.replace(",", "")
                                                  .replace("$", ""))
                self.profile["cap_note"] = \
                    entries["cap_note"].get().strip()
            except ValueError:
                msg.configure(
                    text="Settings not saved — amounts must be numbers "
                         "(blank allowed only where labeled blank).")
                return
            try:
                new_props = []
                for r in prop_rows:
                    raw = r["applied"].get().strip().replace(",", ""
                                                             ).replace("$",
                                                                       "")
                    applied = float(raw or 0)
                    addr = r["addr"].get().strip()
                    if not addr:
                        continue  # default empty row never persists
                    last = dict(r["last"])
                    last["address"] = addr
                    last["applied_value"] = applied
                    new_props.append(last)
            except ValueError:
                msg.configure(text="Settings not saved — applied home "
                                   "values must be numbers.")
                return
            self.profile["properties"] = new_props
            key = key_ent.get().strip()
            # An address-like value is flagged plainly, never silently
            # stored as a key (API keys have no spaces or commas).
            if self._looks_like_address(key):
                msg.configure(
                    text="That looks like a street address, not a RentCast "
                         "key — put the address in a Properties address "
                         "field above. Nothing saved.")
                return
            self.profile["rentcast_key"] = key
            pc.save_profile(PROFILE_JSON, self.profile)
            self._sync_home()
            self.recompute()
            self.build_all()
            self.refresh_data_window()
            self.status_var.set("Settings saved.")
            win.destroy()

        # Fixed footer: always visible and clickable without scrolling;
        # Tab order reaches Save natively, Enter activates it.
        ctk.CTkButton(foot, text="Save settings", width=150,
                      command=save).pack(side="left", padx=4)
        ctk.CTkButton(foot, text="Cancel", width=110,
                      command=win.destroy).pack(side="left", padx=4)

        def export_settings():
            # Local-only file (like the backup): the profile.json format,
            # round-trippable into another copy of the app. Never defaults
            # into the repo folder.
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
            path = filedialog.asksaveasfilename(
                defaultextension=".json", filetypes=[("JSON", "*.json")],
                initialdir=self._downloads_dir(),
                initialfile="settings-%s.json" % stamp,
                parent=win)
            if not path:
                return
            try:
                with open(path, "w") as fh:
                    json.dump(self.profile, fh, indent=1, sort_keys=True)
            except OSError as e:
                msg.configure(text="Export failed: %s" % e)
                return
            self.status_var.set("Exported settings to %s." % path)

        def import_settings():
            path = filedialog.askopenfilename(
                filetypes=[("JSON", "*.json")], parent=win)
            if not path:
                return
            try:
                with open(path) as fh:
                    data = json.load(fh)
            except (ValueError, OSError) as e:
                msg.configure(text="Not a settings file (%s) — nothing "
                                   "applied." % type(e).__name__)
                return
            err = self._check_settings_data(data)
            if err:
                msg.configure(text="%s — nothing applied." % err)
                return
            if not self._confirm(
                    "Import settings",
                    "Replace ALL settings with '%s'? Portfolio lots and "
                    "the drift log are not touched."
                    % os.path.basename(path),
                    ok_text="Import settings", parent=win):
                return
            self._busy("Applying imported settings…")
            try:
                cleaned = {k: data[k] for k in pc.PROFILE_DEFAULTS
                           if k in data}
                self.profile = dict(pc.PROFILE_DEFAULTS)
                self.profile.update(cleaned)
                pc.save_profile(PROFILE_JSON, self.profile)
                self._sync_home()
                self.recompute()
                self.build_all()
                self.refresh_data_window()
            finally:
                self._idle()
            win.destroy()
            self.status_var.set("Imported settings from %s." % path)
            # Reopen pre-filled: the old dialog's fields were snapshots
            # taken at open time, so closing it on import made the values
            # vanish instead of appearing. Reopening shows what landed.
            self.open_settings()

        exp_bar = ctk.CTkFrame(foot, fg_color="transparent")
        exp_bar.pack(fill="x", pady=(6, 0))
        ctk.CTkButton(exp_bar, text="Export settings", width=150,
                      command=export_settings).pack(side="left", padx=4)
        ctk.CTkButton(exp_bar, text="Import settings", width=150,
                      command=import_settings).pack(side="left", padx=4)
        win.after(50, lambda: (win.deiconify(), win.lift())
                  if win.winfo_exists() else None)

    def _settings_summary_text(self):
        sp = pc.spending_capacity(self.profile, self.lots, self.prices)
        return ("Spending capacity (computed, as of %s): BEFORE 65 %s/yr "
                "(pool %s ÷ %s yrs) · AFTER 65 %s/yr base (IRAs %s ÷ 20) + "
                "SS = %s/yr all-in. Realizable this year ≈ %s. Age %s, "
                "turns 65 in %s. Compare against your own actual spending."
                % (sp["asof"], money(sp["before65"]), money(sp["under65"]),
                   "--" if sp["div_years"] is None
                   else "%d" % sp["div_years"],
                   money(sp["after65_base"]), money(sp["ira"]),
                   money(sp["after65_allin"]), money(sp["realizable"]),
                   "--" if sp["age"] is None else "%d" % sp["age"],
                   sp["turns65"]))

    def build_data_danger(self):
        f = self._clear_data_tab("Danger Zone")
        ctk.CTkLabel(
            f, text="Danger Zone",
            font=ctk.CTkFont(size=FS_HEAD, weight="bold"),
            text_color="red").pack(padx=8, pady=(8, 2), anchor="w")
        self._selectable_note(
            f, "Uploads upsert by lot key (account + asset + acquired date "
               "+ cost): matching rows UPDATE, new rows INSERT, uploads "
               "NEVER delete rows. So delete-then-upload is the ONLY way to "
               "get a clean dataset replacement — that is why this button "
               "matters beyond re-tests.\n"
               "Delete all data wipes portfolio.csv, profile.json, "
               "drift_log.csv, prices_cache.json and accounts.json. "
               "Afterwards the app is indistinguishable from a fresh "
               "install (blank settings, no numbers, no chart) and a "
               "re-upload restores the numbers.",
            padx=8, pady=8, fill="x")
        warn = ctk.CTkFrame(f, fg_color="transparent")
        warn.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(
            warn, text="Back up first — download your data:",
            text_color="red").pack(side="left", padx=4)
        ctk.CTkButton(warn, text="Download Data", width=200,
                      command=self.download_filled_template).pack(
                          side="left", padx=4)
        self.danger_entry = None
        self.danger_delete_btn = None
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(row, text="Type DELETE to enable:").pack(
            side="left", padx=4)
        ent = ctk.CTkEntry(row, width=120)
        ent.pack(side="left", padx=4)
        ent.bind("<KeyRelease>", lambda _e: self._danger_arm(ent.get()),
                 add="+")
        self.danger_entry = ent
        self.danger_delete_btn = ctk.CTkButton(
            row, text="Delete all data", width=160,
            fg_color="#8B0000", hover_color="#B00000",
            command=self.delete_all_data, state="disabled")
        self.danger_delete_btn.pack(side="left", padx=4)
        self.danger_msg = SelectableMsg(f, text="")
        self.danger_msg.pack(padx=8, pady=4, anchor="w")

    def _danger_arm(self, text):
        try:
            self.danger_delete_btn.configure(
                state="normal" if text.strip() == "DELETE" else "disabled")
        except (tk.TclError, AttributeError):
            pass

    def delete_all_data(self):
        # Uploads upsert, never replace — delete-then-upload is the ONLY
        # clean-replacement path, which is why this button exists.
        # The account registry (accounts.json) is in the delete set too:
        # without it the Accounts tab would keep listing ghost names at
        # $0 after a wipe.
        for path in (PORTFOLIO_CSV, PROFILE_JSON, DRIFT_LOG, CACHE,
                     ACCOUNTS_JSON):
            try:
                os.remove(path)
            except OSError:
                pass
        self.lots = []
        self.profile = dict(pc.PROFILE_DEFAULTS)
        self.accounts = []
        self.prices = {}
        self.watch = {}
        self.home_value = pc.HOME_DEFAULT
        self._hold_expanded = set()
        self._liq_expanded = set()
        self._cov_reset()
        # Drop any stale guided filter: it names accounts that no longer
        # exist, and the empty grid would show its panel with no rows.
        self.cov_filter = None
        self.cov_guide = "done"
        self.recompute()
        self.build_all()
        self.refresh_data_window()
        self.danger_msg.configure(
            text="All data deleted. The app is now empty.")
        # Reset LAST: nothing after this point may set status, so no
        # pre-delete message can survive the wipe.
        self.status_var.set("All data deleted. The app is now empty.")

    # ---- position lifecycle (Add / Sold / Mark closed / Reopen) ----
    def _form(self, title):
        win = ctk.CTkToplevel(self)
        win.title(title)
        win.transient(self)
        win.resizable(False, False)
        body = ctk.CTkFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=12)
        msg = SelectableMsg(body, text="", text_color="orange")
        entries = {}

        def row(label, default="", width=260):
            ctk.CTkLabel(body, text=label).pack(anchor="w", padx=4, pady=(6, 0))
            ent = ctk.CTkEntry(body, width=width)
            ent.insert(0, default)
            ent.pack(anchor="w", padx=4, pady=2)
            entries[label] = ent
            return ent

        return win, body, msg, entries, row

    def _lot_options(self, closed=False):
        opts = []
        idx = []
        for i, lot in enumerate(self.lots):
            if (pc.lot_status(lot) == "Closed") != closed:
                continue
            if not closed and pc.is_cash_row(lot):
                continue
            opts.append("%d: %s — %s (%s)" % (i, lot["account"],
                                             lot["asset"], lot["shares"]))
            idx.append(i)
        return opts, idx

    def add_position_form(self):
        win, body, msg, entries, row = self._form("Add position")
        accounts = sorted({l["account"] for l in self.lots})
        ctk.CTkLabel(body, text="Account").pack(anchor="w", padx=4,
                                                pady=(6, 0))
        acct_menu = ctk.CTkOptionMenu(
            body, values=accounts + ["< new account >"])
        if accounts:
            acct_menu.set(accounts[0])
        acct_menu.pack(anchor="w", padx=4, pady=2)
        row("New account name (only if < new account >)")
        row("Bank")
        type_menu = ctk.CTkOptionMenu(body, values=pc.ACCOUNT_TYPES)
        type_menu.set("Taxable")
        ctk.CTkLabel(body, text="Account type (new accounts only)").pack(
            anchor="w", padx=4, pady=(6, 0))
        type_menu.pack(anchor="w", padx=4, pady=2)
        row("Asset")
        row("Shares")
        row("Cost per share (optional)")
        row("Acquired date YYYY-MM-DD (optional)")
        msg.pack(anchor="w", padx=4, pady=6)

        def save():
            acct = acct_menu.get()
            if acct == "< new account >":
                acct = entries["New account name "
                               "(only if < new account >)"].get().strip()
                if not acct:
                    msg.configure(text="Name the new account.")
                    return
            try:
                shares = float(entries["Shares"].get())
                if shares <= 0:
                    raise ValueError
            except ValueError:
                msg.configure(text="Shares must be a positive number.")
                return
            cost_raw = entries["Cost per share (optional)"].get().strip()
            try:
                cost = float(cost_raw) if cost_raw else None
            except ValueError:
                msg.configure(text="Cost must be numeric or blank.")
                return
            acq = entries["Acquired date YYYY-MM-DD (optional)"].get().strip()
            if acq:
                try:
                    datetime.date.fromisoformat(acq)
                except ValueError:
                    msg.configure(text="Acquired date must be YYYY-MM-DD.")
                    return
            known = {l["account"]: l["account_type"] for l in self.lots
                     if l["account"] == acct and l["account_type"]}
            self.lots.append({
                "bank": entries["Bank"].get().strip(), "account": acct,
                "account_type": known.get(acct, type_menu.get()),
                "asset": entries["Asset"].get().strip() or "?",
                "shares": shares, "cost": cost, "acquired": acq,
                "sold_date": "", "sale_price": None})
            win.destroy()
            self.lots_changed_externally("Position added to %s." % acct)

        ctk.CTkButton(body, text="Save", command=save).pack(
            anchor="w", padx=4, pady=8)

    def _position_options(self):
        seen = {}
        for lot in pc.open_lots(self.lots):
            if pc.is_cash_row(lot):
                continue
            key = (lot["account"], lot["asset"])
            seen[key] = seen.get(key, 0.0) + (lot["shares"] or 0.0)
        return ["%s — %s (%s)" % (a, s, pc._fmt_shares(q))
                for (a, s), q in sorted(seen.items())]

    def sell_form(self, close_all=False):
        opts, idx = self._lot_options()
        pos_opts = self._position_options()
        if not pos_opts:
            self.status_var.set("No open positions.")
            return
        win, body, msg, entries, row = self._form(
            "Mark closed" if close_all else "Record a sale")
        method = tk.StringVar(value="fifo")
        ctk.CTkRadioButton(body, text="FIFO — oldest lots first (default)",
                          variable=method, value="fifo").pack(
                              anchor="w", padx=4, pady=2)
        ctk.CTkRadioButton(body, text="Specific lot (override)",
                          variable=method, value="specific").pack(
                              anchor="w", padx=4, pady=2)
        ctk.CTkLabel(body, text="Position (FIFO)").pack(
            anchor="w", padx=4, pady=(6, 0))
        pos_menu = ctk.CTkOptionMenu(body, values=pos_opts, width=340)
        pos_menu.set(pos_opts[0])
        pos_menu.pack(anchor="w", padx=4, pady=2)
        ctk.CTkLabel(body, text="Lot (specific override)").pack(
            anchor="w", padx=4, pady=(6, 0))
        menu = ctk.CTkOptionMenu(body, values=opts, width=340)
        menu.set(opts[0])
        menu.pack(anchor="w", padx=4, pady=2)
        if close_all:
            row("Quantity (full position)", "all")
        else:
            row("Quantity sold")
        row("Sold date YYYY-MM-DD",
            datetime.date.today().isoformat())
        row("Sale price per share")
        cost_ent = row("Cost per share (asked only if a lot lacks it)")
        msg.pack(anchor="w", padx=4, pady=6)

        def parse_common():
            # Returns ((qty_or_None, sold, price, cost), error_or_None).
            qty = None
            if not close_all:
                try:
                    qty = float(entries["Quantity sold"].get())
                    if qty <= 0:
                        raise ValueError
                except ValueError:
                    return None, "Quantity must be positive."
            try:
                sold = datetime.date.fromisoformat(
                    entries["Sold date YYYY-MM-DD"].get().strip())
            except ValueError:
                return None, "Sold date must be YYYY-MM-DD."
            try:
                price = float(entries["Sale price per share"].get())
            except ValueError:
                return None, "Sale price must be numeric."
            cost = None
            if cost_ent.get().strip():
                try:
                    cost = float(cost_ent.get().strip())
                except ValueError:
                    return None, "Cost must be numeric or blank."
            return (qty, sold.isoformat(), price, cost), None

        def save():
            parsed, err = parse_common()
            if err:
                msg.configure(text=err)
                return
            qty, sold, price, cost = parsed
            if method.get() == "fifo":
                sel = pos_menu.get().rsplit(" (", 1)[0]
                acct, asset = sel.split(" — ", 1)
                held = sum(l["shares"] or 0.0 for l in pc.open_lots(self.lots)
                           if l["account"] == acct and l["asset"] == asset)
                if close_all:
                    qty = held
                new_lots, ferr = pc.fifo_sell(
                    self.lots, acct, asset, qty, sold, price, cost)
                if ferr:
                    msg.configure(text=ferr)
                    return
                self.lots = new_lots
                win.destroy()
                self.lots_changed_externally("Sold %s of %s (%s)." % (
                    pc._fmt_shares(qty), asset, "FIFO"))
                return
            i = idx[opts.index(menu.get())]
            lot = self.lots[i]
            if close_all:
                qty = lot["shares"]
            if qty is None or qty <= 0 or qty > (lot["shares"] or 0):
                msg.configure(text="Quantity must be between 0 and %s."
                              % lot["shares"])
                return
            eff_cost = lot.get("cost") if lot.get("cost") is not None \
                else cost  # still None → gain flagged unknown, never invented
            if qty == lot["shares"]:
                lot["sold_date"] = sold
                lot["sale_price"] = price
                if eff_cost is not None:
                    lot["cost"] = eff_cost
            else:
                closed, opened = pc.split_for_sale(
                    lot, qty, sold, price, eff_cost)
                self.lots[i] = closed
                self.lots.insert(i + 1, opened)
            win.destroy()
            self.lots_changed_externally("Sale recorded for %s."
                                         % lot["asset"])

        ctk.CTkButton(body, text="Record sale", command=save).pack(
            anchor="w", padx=4, pady=8)

    def reopen_form(self):
        opts, idx = self._lot_options(closed=True)
        if not opts:
            self.status_var.set("No closed positions to reopen.")
            return
        win, body, msg, entries, row = self._form("Reopen position")
        ctk.CTkLabel(body, text="Closed position").pack(
            anchor="w", padx=4, pady=(6, 0))
        menu = ctk.CTkOptionMenu(body, values=opts, width=340)
        menu.set(opts[0])
        menu.pack(anchor="w", padx=4, pady=2)

        def save():
            i = idx[opts.index(menu.get())]
            self.lots[i]["sold_date"] = ""
            self.lots[i]["sale_price"] = None
            win.destroy()
            self.lots_changed_externally("Position reopened.")

        ctk.CTkButton(body, text="Reopen", command=save).pack(
            anchor="w", padx=4, pady=8)

if __name__ == "__main__":
    App().mainloop()
