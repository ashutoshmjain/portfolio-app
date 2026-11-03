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
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

import portfolio_calc as pc

HERE = os.path.dirname(os.path.abspath(__file__))
PORTFOLIO_CSV = os.path.join(HERE, "portfolio.csv")
PROFILE_JSON = os.path.join(HERE, "profile.json")
CACHE = os.path.join(HERE, "prices_cache.json")
DRIFT_LOG = os.path.join(HERE, "drift_log.csv")

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


class Table(ctk.CTkScrollableFrame):
    """Simple grid table: header row bold, values as labels.

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
                lbl = ctk.CTkLabel(
                    self, text=text,
                    font=ctk.CTkFont(weight="bold") if bold else None,
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
        self.positions = pc.positions_from_lots(self.lots)
        self.cost_basis = pc.cost_map_from_lots(self.lots)
        self.prices = pc.load_price_cache(CACHE)
        self.home_value = pc.HOME_DEFAULT
        self.data = None
        self.cov_lots = None
        self.status_var = tk.StringVar(value="Ready — open the ☰ menu.")

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
        self.status = ctk.CTkLabel(top, textvariable=self.status_var,
                                   text_color="orange")
        self.status.pack(side="left", padx=8)
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
        # Tax implications. Data Entry holds Inputs, Template, Profile.
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
        for name in ("Inputs", "Template", "Profile", "Danger Zone"):
            self.data_tabs.add(name)
        self.tabs.set("Dashboard")
        self.dash_tabs.set("Overview")
        self.frames = {}

        self.recompute()
        self.build_all()
        self.refresh_data_window()

    # ---- data ----
    def recompute(self):
        self.positions = pc.positions_from_lots(self.lots)
        self.cost_basis = pc.cost_map_from_lots(self.lots)
        self.data = pc.compute(self.positions, self.prices, self.home_value,
                               self.cost_basis)

    def save_lots(self, msg="Data saved."):
        # File + main views only. Data Entry refresh is explicit at each
        # call site (structural rebuild vs in-place repaint, F5).
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

    def _cov_keep_scroll(self, fn):
        scroll = getattr(self, "_cov_scroll", None)
        y = None
        try:
            if scroll is not None and scroll.winfo_exists():
                y = scroll._parent_canvas.yview()
        except (tk.TclError, AttributeError):
            y = None
        fn()
        if y:
            try:
                scroll._parent_canvas.yview_moveto(y[0])
                scroll._parent_canvas.update_idletasks()
            except (tk.TclError, AttributeError):
                pass

    def refresh_async(self):
        self.status_var.set("Fetching prices from Yahoo Finance…")
        tickers = sorted({p["ticker"] for p in self.positions
                          if p["ticker"] != "CASH_USD"})

        def work():
            prices, errors, used_cache = pc.fetch_prices(tickers, CACHE)
            self.after(0, lambda: self._after_refresh(prices, errors,
                                                      used_cache))

        threading.Thread(target=work, daemon=True).start()

    def _after_refresh(self, prices, errors, used_cache):
        self.prices = prices
        self.recompute()
        self.build_all()
        try:
            self._cov_refresh_chrome()
        except (tk.TclError, ValueError, AttributeError):
            pass
        if errors:
            self.status_var.set("Price fetch partial — %s. "
                                "Stale tickers use last-known prices."
                                % "; ".join(errors[:3]))
        elif used_cache:
            self.status_var.set("Prices refreshed (some from cache).")
        else:
            self.status_var.set("Prices refreshed %s."
                                % datetime.datetime.now().strftime("%H:%M"))

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
        Log. Data Entry is a tab now — no window opens from here."""
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

    def home_from_menu(self):
        self._close_menu()
        win = ctk.CTkToplevel(self)
        win.title("Home estimate")
        win.transient(self)
        win.resizable(False, False)
        ctk.CTkLabel(win, text="Latest home value estimate $ "
                               "(e.g. from Zillow):").pack(padx=12,
                                                           pady=(12, 2),
                                                           anchor="w")
        ent = ctk.CTkEntry(win, width=200)
        ent.insert(0, "" if not self.home_value else str(self.home_value))
        ent.pack(padx=12, pady=2, anchor="w")
        msg = ctk.CTkLabel(win, text="", text_color="orange")
        msg.pack(padx=12, anchor="w")

        def apply():
            try:
                self.home_value = float(ent.get().replace(",", "")
                                        .replace("$", ""))
            except ValueError:
                msg.configure(text="Not a number — kept previous.")
                return
            win.destroy()
            self.recompute()
            self.build_all()
            self.status_var.set("Home updated to %s."
                                % money(self.home_value))

        ctk.CTkButton(win, text="Apply", command=apply).pack(
            padx=12, pady=(4, 12), fill="x")
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
            if w < 50 or abs(w - state["w"]) < 20:
                return
            state["w"] = w
            try:
                fig.set_size_inches(w / fig.get_dpi(),
                                    fig.get_size_inches()[1],
                                    forward=True)
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
        f = self._clear_dash("Overview")
        # One vertical scroll region for the whole view: the chart keeps
        # its full figure height at any window size instead of being
        # cropped by a short window (lost x-labels, legends, bar groups).
        body = ctk.CTkScrollableFrame(f)
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
            ctk.CTkButton(body, text="Upload a filled template",
                          width=240,
                          command=self._goto_template).pack(
                              padx=10, pady=4, anchor="w")
            return
        tnw = self.data["tnw"]
        sp = pc.spending_capacity(self.profile)
        d = self.data["drift"]
        year = datetime.date.today().year
        realized, _unk, _rows = pc.realized_gains_year(
            self.lots, year,
            self.profile.get("other_realized_gains_current_year", 0) or 0.0)
        leeway = pc.TLH_CAP - realized
        missing = self._required_missing()
        ctk.CTkLabel(body, text="Total net worth: %s" % money(tnw),
                     font=ctk.CTkFont(size=FS_TITLE, weight="bold")).pack(
                         padx=10, pady=(10, 2), anchor="w")
        ctk.CTkLabel(
            body, text="Allowed spending: %s/yr before 65 · %s/yr after 65 "
                    "(base %s + Social Security)." % (
                        money(sp["before65"]), money(sp["after65_allin"]),
                        money(sp["after65_base"])),
            font=ctk.CTkFont(size=FS_BODY)).pack(padx=10, pady=2, anchor="w")
        alerts = [
            "Drift vs standard: actual %s vs standard %s (%s)." % (
                pct(d["actual_ytd"]), pct(d["standard_ytd"]),
                pct(d["drift_pp"])),
            "Tax-loss-harvest leeway: %s of the $15,000 cap." % money(leeway),
            "%d REQUIRED position%s still missing cost or dates — feed "
            "them in Data Entry." % (missing, "" if missing == 1 else "s")
            if missing else
            "All REQUIRED positions have cost and dates.",
        ]
        for alert in alerts:
            ctk.CTkLabel(body, text="• " + alert, wraplength=860,
                         anchor="w").pack(padx=10, pady=1, anchor="w")
        summary = ("Total net worth: %s\n"
                   "Allowed spending: %s/yr before 65 · %s/yr after 65 "
                   "(base %s + Social Security).\n%s"
                   % (money(tnw), money(sp["before65"]),
                      money(sp["after65_allin"]), money(sp["after65_base"]),
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
        pc.make_drift_chart(fig, pc.load_drift_log(DRIFT_LOG))
        self._chart_canvas(body, fig)
        # RESERVED: Overview bottom area is held for the FUTURE
        # upcoming-events calendar (earnings calls and other events for
        # portfolio holdings) — related to the deferred news feed. The
        # one-path navigation standing rule keeps the tab bar as the sole
        # navigation; no duplicate Go-to buttons here. Do not build the
        # calendar in this pass — this comment reserves the space.

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
        f = self._clear_dash("Holdings")
        if getattr(self, "_hold_expanded", None) is None:
            self._hold_expanded = set()
        rows, _total = pc.holdings_by_asset(
            self.lots, self.prices, self.home_value,
            self.profile.get("home_purchase_price") or None)
        scroll = ctk.CTkScrollableFrame(f)
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
        ctk.CTkButton(f, text="Copy table", width=110,
                      command=lambda: self._copy_holdings(rows)
                      ).pack(padx=6, pady=(6, 0), anchor="w")
        ctk.CTkLabel(
            f, text="Averages and gains show only when every open lot has "
                    "cost — otherwise Avg reads upload (hover for the "
                    "missing count) and gains read --. The table is a "
                    "checklist: upload the missing cost data in Data Entry. "
                    "Cash lives in Liquidity. Home is one more row (value "
                    "only unless a purchase price is set in the profile). "
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
        d = self.data
        rows = []
        for r in d["view1"]:
            rows.append([r["account"], money(r["BTC & related"]),
                         money(r["Gold & silver"]), money(r["Equities"]),
                         money(r["Cash & cash-like"]), money(r["re"]),
                         "**" + money(r["total"]), pct(r["pct"])])
        t = d["view1_total"]
        rows.append(["**TOTAL", "**" + money(t["BTC & related"]),
                     "**" + money(t["Gold & silver"]),
                     "**" + money(t["Equities"]),
                     "**" + money(t["Cash & cash-like"]),
                     "**" + money(t["re"]), "**" + money(t["total"]),
                     "**100.0%"])
        m = d["mix"]
        rows.append(["**Mix %", "**" + pct(m["BTC & related"]),
                     "**" + pct(m["Gold & silver"]), "**" + pct(m["Equities"]),
                     "**" + pct(m["Cash & cash-like"]), "**" + pct(m["re"]),
                     "**100.0%", ""])
        Table(f, ["Account", "BTC", "Gold", "Equities", "Cash-like",
                  "Real Estate", "Total", "% of portfolio"],
              rows).pack(fill="both", expand=True, padx=6, pady=6)
        bar = ctk.CTkFrame(f)
        bar.pack(fill="x", padx=6, pady=6)
        ctk.CTkButton(bar, text="Add position",
                      command=self.add_position_form).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="Sell / Reduce",
                      command=lambda: self.sell_form(close_all=False)).pack(
                          side="left", padx=4)
        ctk.CTkButton(bar, text="Close position",
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
        sp = pc.spending_capacity(self.profile)
        years = (under / sp["before65"]) if sp["before65"] else None
        self._selectable_note(
            f, "Totals: available now %s · unlocks at 59½ %s · liquid "
               "%s · home %s · net worth %s. Available-now total ÷ "
               "%s/yr before-65 spending = %s years of pre-65 spending "
               "covered by available-now money."
               % (money(under), money(over), money(liquid),
                  money(self.home_value), money(self.data["tnw"]),
                  money(sp["before65"]),
                  "--" if years is None else "%.1f" % years),
            padx=6, pady=6, fill="x")
        self._selectable_note(
            f, "59½ (%s): penalty-free ≠ tax-free — Traditional "
               "withdrawals are still taxed as income; Roth earnings "
               "also need the 5-year rule (Roth balance here is "
               "negligible)."
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
        self._selectable_note(
            f, "What each account type means for tax and withdrawals "
               "(facts, not advice).",
            padx=6, pady=6, fill="x")
        Table(f, ["Account type", "Tax / withdrawal treatment"],
              [["**" + t, self.TAX_TYPE_NOTES[t]] for t in
               ("Traditional IRA", "Roth IRA", "Taxable", "HSA", "Cash")]
              ).pack(fill="x", padx=6, pady=6)
        seen = {}
        for lot in self.lots:
            seen.setdefault(lot.get("account"),
                            lot.get("account_type") or "?")
        Table(f, ["Account", "Type"],
              [[a, seen[a]] for a in sorted(seen)]
              ).pack(fill="both", expand=True, padx=6, pady=6)

    def build_diversification(self):
        from matplotlib.figure import Figure
        f = self._clear("Diversification")
        # One vertical scroll region: tables + both charts keep full height
        # at any window size instead of being cropped (see build_overview).
        body = ctk.CTkScrollableFrame(f)
        body.pack(fill="both", expand=True)
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
                         "%+.1fpp" % r["deviation_pp"],
                         money(r["rebalance"])])
        Table(body, ["Bucket", "Target %", "Target $", "Actual $",
                     "Actual %", "Deviation (pp)",
                     "Rebalance buy(+) / sell(-)"],
              rows).pack(fill="both", padx=6, pady=6)
        fig1 = Figure(figsize=(10, 4.2), dpi=100)
        pc.make_allocation_chart(fig1, self.data["view3"])
        self._chart_canvas(body, fig1)
        self._selectable_note(
            body, "REBALANCE PLAN (display only, NEVER executes "
                  "trades). All 4 trades inside Schwab Ashu IRA: $0 tax, "
                  "Medi-Cal safe. Verify on the trade ticket before "
                  "executing.",
            padx=6, pady=6, fill="x")
        rows = []
        for t in self.data["view4"]["trades"]:
            rows.append([str(t["n"]), "Schwab Ashu IRA", t["sell"],
                         "--" if t["sell_sh"] is None else f"{t['sell_sh']:,}",
                         money(t["proceeds"]), t["buy"],
                         "--" if t["buy_sh"] is None else f"{t['buy_sh']:,}",
                         "$0 (IRA)"])
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
        rows.append(["**TOTAL", "**" + money(tnw), "**100.0%",
                     "**" + money(v4["after_total"]),
                     "**" + pct(v4["after_total"] / tnw) if tnw else "--"])
        Table(body, ["Bucket", "Before $", "Before %", "After $",
                     "After %"],
              rows).pack(fill="both", padx=6, pady=6)
        d = self.data["drift"]
        drift_txt = (
            "Drift (calendar-year baseline $4,526K = liquid $3,595K + home "
            "$931K): actual YTD %s | standard YTD %s | drift %s (%s) | "
            "standard total %s"
            % (pct(d["actual_ytd"]), pct(d["standard_ytd"]),
               pct(d["drift_pp"]), money(d["drift_dollar"]),
               money(d["standard_total"])))
        self._selectable_note(body, drift_txt, padx=6, pady=6, fill="x")
        fig2 = Figure(figsize=(10, 6.0), dpi=100)
        pc.make_drift_chart(fig2, pc.load_drift_log(DRIFT_LOG))
        self._chart_canvas(body, fig2)

    def build_tax(self):
        f = self._clear("Tax Harvest")
        ctk.CTkLabel(f, text="Tax Loss Harvesting",
                     font=ctk.CTkFont(size=FS_HEAD, weight="bold")).pack(
                         padx=6, pady=(6, 0), anchor="w")
        year = datetime.date.today().year
        prices = self.prices
        rows = []
        losers = []
        for lot in pc.open_lots(self.lots):
            if pc.is_cash_row(lot):
                continue
            price = prices.get(lot["asset"])
            value = None if price is None else price * (lot["shares"] or 0)
            if lot.get("cost") is not None and price is not None:
                pnl = (lot["shares"] or 0) * (price - lot["cost"])
            else:
                pnl = None
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
        Table(f, ["Asset", "Account", "Shares", "Cost/share $", "Price now",
                  "Value $", "Unrealized P&L $", "Term", "Harvest rank"],
              rows).pack(fill="both", expand=True, padx=6, pady=6)
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
            Table(f, ["Sold %d — asset" % year, "Account", "Shares", "Cost $",
                      "Sale $", "Sold", "Term", "Gain $"],
                  srows).pack(fill="both", padx=6, pady=6)
        cap = pc.TLH_CAP
        other = self.profile.get("other_realized_gains_current_year",
                                 0) or 0.0
        Table(f, ["%d capital-gains budget (Medi-Cal: keep net gains "
                  "under $15K/yr)" % year, "$"],
              [["Annual net-gains cap (your $15K guardrail)", money(cap)],
               ["Pre-app realized gains (full note in Profile)", money(other)],
               ["Realized from sold lots above", money(total - other)],
               ["**Net realized YTD", "**" + money(total)],
               ["**Remaining budget (leeway)", "**" + money(cap - total)]],
              ).pack(fill="both", padx=6, pady=6)
        note = ("Itemized sold rows and the pre-app field must NOT overlap "
                "— no double-counting. ")
        if unknown:
            note += ("%s have unknown basis and are EXCLUDED from the "
                     "total. " % _n(unknown, "sold lot"))
        note += ("Do NOT invent basis. Wash-sale rule: do not rebuy the "
                 "same asset within 30 days of a loss sale.")
        self._selectable_note(f, note, padx=6, pady=6, fill="x")

    # (Charts merged into build_diversification; Rebalance merged too.)


    # ---- Data Entry tab (Inputs / Template / Profile) ----
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
        self._ensure_cov_state()
        self.build_data_coverage()
        self.build_data_template()
        self.build_data_profile()
        self.build_data_danger()

    def _clear_data_tab(self, name):
        frame = self.data_tabs.tab(name)
        for w in frame.winfo_children():
            w.destroy()
        return frame

    def build_data_coverage(self):
        f = self._clear_data_tab("Inputs")
        self.cov_nav_rows = []
        self.cov_widgets = {}
        self._cov_scroll = None
        t = self._cov_totals()
        top = ctk.CTkFrame(f, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(8, 2))
        self.cov_progress = ctk.CTkLabel(
            top, text="Positions %d of %d · Cost entered %d of %d · Dates "
                      "entered %d of %d" % (
                          t["holdings_ok"], t["holdings_n"], t["cost_ok"],
                          t["cost_n"], t["acq_ok"], t["acq_n"]),
            font=ctk.CTkFont(size=FS_BODY, weight="bold"))
        self.cov_progress.pack(side="left", padx=4)
        n = self._cov_counts()
        self.cov_save_btn = ctk.CTkButton(
            top, text="Save (%d)" % n, width=110,
            command=self._cov_save,
            state="normal" if n else "disabled")
        self.cov_save_btn.pack(side="right", padx=4)
        ctk.CTkButton(top, text="Revert", width=80,
                      command=self._cov_revert).pack(side="right", padx=4)
        ctk.CTkButton(top, text="Copy grid", width=90,
                      command=self._copy_cov_grid).pack(side="right",
                                                       padx=4)
        ctk.CTkButton(top, text="+ Add account", width=110,
                      command=self._cov_add_account).pack(side="right",
                                                         padx=4)
        if self.cov_filter:
            ctk.CTkButton(top, text="Show all", width=80,
                          command=self._cov_show_all).pack(side="right",
                                                          padx=4)
        else:
            ctk.CTkButton(top, text="Guided", width=90,
                          command=self._cov_guide_start).pack(side="right",
                                                             padx=4)
        self.cov_warn = ctk.CTkLabel(f, text="", text_color="orange",
                                     wraplength=860, anchor="w")
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
                   "checks everything and commits at once; Revert throws "
                   "away unsaved edits.\n"
                   "• Click any text and press Ctrl+C to copy it; every "
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
        t = pc.coverage(
            [self._cov_stripped(r) for r in self.cov_lots])["total"]
        t["required_left"] = sum(
            1 for r in self.cov_lots
            if pc.lot_status(r) == "Open"
            and r.get("account_type") == "Taxable"
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
                    is_bad = v is None or v <= 0
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
                    text="Save (%d)" % n, state="normal" if n else "disabled")
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
        raw = []
        for r in self.cov_lots:
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

    def _cov_add_account(self):
        # Covers BOTH cases: new account under an existing bank (dropdown)
        # or under a new bank (free text). Creates the section with its
        # first lot row — sections only exist once rows do.
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
        msg = ctk.CTkLabel(body, text="", text_color="orange",
                           wraplength=320)
        msg.pack(anchor="w", padx=4, pady=6)

        def sync_bank(*_a):
            if bank_menu.get() == "< new >" and not bank_ent.winfo_manager():
                bank_ent.pack(anchor="w", padx=4, pady=2)
            elif bank_menu.get() != "< new >" and bank_ent.winfo_manager():
                bank_ent.pack_forget()

        bank_menu.configure(command=lambda _v: sync_bank())

        def save():
            bank = bank_var.get().strip() if bank_menu.get() == "< new >" \
                else bank_menu.get()
            acct = acct_var.get().strip()
            if not bank or not acct:
                msg.configure(text="Bank and account name are required.")
                return
            if any(r.get("account") == acct for r in self.cov_lots):
                msg.configure(text="That account already exists — add rows "
                                   "to its section instead.")
                return
            try:
                shares = float(shares_var.get())
                if shares <= 0:
                    raise ValueError
            except ValueError:
                msg.configure(text="Shares must be a positive number.")
                return
            if not asset_var.get().strip() and type_menu.get() != "Cash":
                msg.configure(text="First-lot asset is required.")
                return
            is_cash_acct = type_menu.get() == "Cash"
            row = {"bank": bank, "account": acct,
                   "account_type": type_menu.get(),
                   "asset": asset_var.get().strip() or "CASH_USD",
                   "shares": shares,
                   "cost": 1.0 if is_cash_acct else None, "acquired": "",
                   "sold_date": "", "sale_price": None,
                   "_rid": self.cov_next_rid, "_orig": None, "_locked": False}
            self.cov_next_rid += 1
            self.cov_lots.append(row)
            win.destroy()
            self.build_data_coverage()
            self._cov_scroll_to_row(row["_rid"])
            self.status_var.set("Account %s added — fill cost/dates, then "
                                "Save." % acct)

        ctk.CTkButton(body, text="Create account", command=save).pack(
            anchor="w", padx=4, pady=8)
        win.after(50, lambda: (win.deiconify(), win.lift())
                  if win.winfo_exists() else None)

    def _cov_delete(self, rid):
        row = self._cov_row_by_rid(rid)
        if not messagebox.askyesno(
                "Delete lot",
                "Delete this lot row?\n%s — %s (%s)\nOnly this row is "
                "removed." % (row.get("account"), row.get("asset"),
                               row.get("shares"))):
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
        """Accounts (taxable first) with open lots missing cost or dates."""
        todo = []
        seen = set()
        for r in self.cov_lots:
            a = r.get("account")
            if a in seen or r.get("account_type") != "Taxable":
                continue
            if any(x.get("account") == a and pc.lot_status(x) == "Open"
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
            self.status_var.set("Save or Revert Inputs edits first.")
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
            {"Paste rows": self.paste_rows,
             "Import broker CSV": self.import_broker_csv,
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
               "1. Yourself — download the full template (or one account's "
               "template from Inputs), fill one row per lot, upload it here.\n"
               "2. With AI — paste broker screenshots into ChatGPT, Muse, "
               "Gemini or any AI together with the Copy-AI-prompt text, "
               "then upload the CSV it returns.\n"
               "Open lots leave sold_date and sale_price_per_share blank. "
               "Uploads upsert by lot key (account + asset + acquired date "
               "+ cost): matches update, new rows insert, uploads NEVER "
               "delete rows. Uploads need NOT be complete — they merge. To "
               "replace a dataset entirely, delete all data first "
               "(Danger Zone), then upload.",
            padx=8, pady=8, fill="x")
        bar = ctk.CTkFrame(f, fg_color="transparent")
        bar.pack(fill="x", padx=8, pady=4)
        ctk.CTkButton(bar, text="Download full template",
                      command=self.download_full_template).pack(
                          side="left", padx=4)
        ctk.CTkButton(bar, text="Download filled template",
                      command=self.download_filled_template).pack(
                          side="left", padx=4)
        ctk.CTkButton(bar, text="Upload filled template",
                      command=self.upload_template).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="Back up now",
                      command=self.backup_now).pack(side="left", padx=4)
        self.template_more_menu = ctk.CTkOptionMenu(
            bar, values=["Paste rows", "Import broker CSV", "Copy AI prompt"],
            command=self._template_more, width=110)
        self.template_more_menu.set("More ▾")
        self.template_more_menu.pack(side="left", padx=4)
        ctk.CTkLabel(
            f, text="Download filled template: your current data, filled "
                   "into the template — upload it into another copy of the "
                   "app. Back up now: one-click backup into your remembered "
                   "backup folder (a synced Drive/OneDrive/Dropbox folder "
                   "carries it to other machines — no cloud built in).",
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
        self.template_msg = ctk.CTkLabel(f, text="", wraplength=860,
                                         anchor="w")
        self.template_msg.pack(padx=8, pady=4, anchor="w")
        ctk.CTkLabel(f, text="Where to find each field at your broker:",
                     font=ctk.CTkFont(weight="bold")).pack(padx=8, pady=(8, 2),
                                                           anchor="w")
        # One scrollable text block, not per-cell labels (fast scrolling).
        guide = ctk.CTkTextbox(f, wrap="word")
        guide.pack(fill="both", expand=True, padx=8, pady=4)
        lines = []
        for g in BROKER_GUIDE:
            lines.append("%s — %s" % (g["field"], g["concept"]))
            lines.append("  Schwab: %s" % g["schwab"])
            lines.append("  Vanguard: %s" % g["vanguard"])
            lines.append("  Example: %s" % g["example"])
            lines.append("")
        lines.append(
            "Faster than screenshots: both brokers export these lot tables "
            "as CSV — Schwab: Lot Details → Export, and Realized Gain/Loss "
            "→ Export Lot Details; Vanguard: Export at the top right of the "
            "cost basis table. Hand the export to any AI to fill the "
            "template, or use Import broker CSV. Other brokers (Wells, "
            "Chase, Coinbase, Cash App, Health Equity): same concepts — "
            "Holdings/Positions → Cost basis/Lots for open lots; "
            "History/Realized gains for closed lots; the year-end 1099-B is "
            "the authority for sold lots.")
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
        msg = ("Ingested %s from %s: %d updated (already existed), "
               "%d inserted (new)." % (_n(len(rows), "row"), source,
                                       updated, len(ins)))
        self.lots_changed_externally(msg)
        return msg

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

    def import_broker_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            with open(path, newline="") as fh:
                sample = fh.read(65536)
                fh.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
                except csv.Error:
                    dialect = csv.excel
                rows = list(csv.DictReader(fh, dialect=dialect))
        except OSError as e:
            self.template_msg.configure(text="Cannot read file: %s" % e)
            return
        if not rows:
            self.template_msg.configure(text="No data rows in that file.")
            return
        have = {(k or "").strip().lower() for k in rows[0]}
        if not set(pc.LOT_FIELDS) <= have:
            self.template_msg.configure(
                text="I don't recognize this export format (found columns: "
                     "%s). The template is the canonical format — download "
                     "it, or fill it via the AI prompt, or Paste rows. "
                     "Nothing was guessed, nothing changed."
                     % ", ".join(sorted(have)))
            return
        fixed = [{k.strip().lower(): v for k, v in r.items()} for r in rows]
        msg = self._ingest_rows(fixed, path)
        self.template_msg.configure(text=msg)

    def _write_template_csv(self, path, lots):
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=pc.LOT_FIELDS)
            w.writeheader()
            for lot in lots:
                w.writerow({
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
                    if lot.get("sale_price") is None else lot["sale_price"]})

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
        choice = messagebox.askyesnocancel(
            "Unsaved edits",
            "The Inputs grid has unsaved edits.\n\n"
            "Yes = Save first, then %s.\n"
            "No = %s the last saved state "
            "(unsaved edits excluded).\n"
            "Cancel = go back without %s." % (action, action.capitalize(),
                                             action))
        if choice is None:
            return False
        if choice and not self._cov_save():
            self.template_msg.configure(
                text="%s cancelled — fix the flagged rows, "
                     "then save." % action.capitalize())
            return False
        return True

    def download_filled_template(self):
        """Download the full dataset (open + closed lots, all accounts)
        as a plain CSV in the exact template format, so it can be fed to
        another copy of the app via Upload filled template. Exports the
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

    def change_backup_folder(self):
        folder = filedialog.askdirectory(
            title="Pick a backup folder (a synced Drive/OneDrive/Dropbox "
                  "folder carries backups to other machines)")
        if folder:
            self.profile["backup_folder"] = folder
            pc.save_profile(PROFILE_JSON, self.profile)
            self.refresh_data_window()
            self.status_var.set("Backup folder set to %s." % folder)

    def backup_now(self):
        """One-click backup of the filled template CSV into the remembered
        backup folder. First use asks for the folder (changeable via
        Change backup folder). Files accumulate — never overwritten.
        Backup = filled template CSV ONLY (no profile data)."""
        if not self._ensure_saved("back up"):
            return
        folder = self.profile.get("backup_folder") or ""
        if not folder or not os.path.isdir(folder):
            folder = filedialog.askdirectory(
                title="Pick a backup folder (a synced Drive/OneDrive/ "
                      "Dropbox folder carries backups to other machines)")
            if not folder:
                return
            self.profile["backup_folder"] = folder
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
        path = os.path.join(folder, "filled-template-%s.csv" % stamp)
        try:
            self._write_template_csv(path, self.lots)
        except OSError as e:
            self.template_msg.configure(text="Backup failed: %s" % e)
            return
        self.profile["last_backup_time"] = stamp[:8] + " " + stamp[9:]
        self.profile["last_backup_path"] = path
        pc.save_profile(PROFILE_JSON, self.profile)
        self.refresh_data_window()
        self.template_msg.configure(
            text="Backed up %s to %s"
                 % (_n(len(self.lots), "row"), path))

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
        msg = self._ingest_rows(rows, path)
        # _ingest_rows → save_lots rebuilds this tab, so write to the
        # fresh label.
        self.template_msg.configure(text=msg)

    def build_data_profile(self):
        f = self._clear_data_tab("Profile")
        self.prof_entries = {}
        grid = ctk.CTkFrame(f, fg_color="transparent")
        grid.pack(fill="x", padx=8, pady=8)
        fields = [("date_of_birth", "Date of birth (YYYY-MM or YYYY-MM-DD)"),
                  ("ss_owner_monthly", "Owner Social Security $/mo"),
                  ("ss_spouse_monthly", "Spouse Social Security $/mo"),
                  ("other_realized_gains_current_year",
                   "Other realized gains this year $ (pre-app history)"),
                  ("other_realized_gains_note", "Source note for the above"),
                  ("home_purchase_price",
                   "Home purchase price $ (optional — Holdings gain %)")]
        for i, (key, label) in enumerate(fields):
            ctk.CTkLabel(grid, text=label).grid(row=i, column=0, padx=6,
                                                pady=4, sticky="w")
            ent = ctk.CTkEntry(grid, width=320)
            ent.insert(0, str(self.profile.get(key, "")))
            ent.grid(row=i, column=1, padx=6, pady=4, sticky="w")
            self.prof_entries[key] = ent
        ctk.CTkButton(grid, text="Save profile",
                      command=self.save_profile_from_form).grid(
                          row=len(fields), column=1, padx=6, pady=8,
                          sticky="w")
        sp = pc.spending_capacity(self.profile)
        self._selectable_note(
            f, "Spending capacity (live): BEFORE 65 %s/yr · AFTER 65 "
               "%s/yr base + SS = %s/yr all-in. Owner is %s, turns 65 "
               "in %s. Compare against your own actual spending."
               % (money(sp["before65"]), money(sp["after65_base"]),
                  money(sp["after65_allin"]),
                  "--" if sp["age"] is None else "age %d" % sp["age"],
                  sp["turns65"]),
            padx=8, pady=8, fill="x")

    def save_profile_from_form(self):
        try:
            self.profile["date_of_birth"] = \
                self.prof_entries["date_of_birth"].get().strip()
            self.profile["ss_owner_monthly"] = float(
                self.prof_entries["ss_owner_monthly"].get() or 0)
            self.profile["ss_spouse_monthly"] = float(
                self.prof_entries["ss_spouse_monthly"].get() or 0)
            self.profile["other_realized_gains_current_year"] = float(
                self.prof_entries["other_realized_gains_current_year"].get()
                or 0)
            self.profile["other_realized_gains_note"] = \
                self.prof_entries["other_realized_gains_note"].get().strip()
            home_raw = self.prof_entries["home_purchase_price"].get().strip()
            self.profile["home_purchase_price"] = \
                "" if not home_raw else float(home_raw.replace(",", "")
                                              .replace("$", ""))
        except ValueError:
            self.status_var.set("Profile not saved — amounts must be numbers.")
            return
        pc.save_profile(PROFILE_JSON, self.profile)
        self.recompute()
        self.build_all()
        self.refresh_data_window()
        self.status_var.set("Profile saved.")

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
               "drift_log.csv and prices_cache.json. Afterwards the app is "
               "indistinguishable from a fresh install (blank profile, no "
               "numbers, no chart) and a re-upload restores the numbers.",
            padx=8, pady=8, fill="x")
        warn = ctk.CTkFrame(f, fg_color="transparent")
        warn.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(
            warn, text="Back up first — download your filled template:",
            text_color="red").pack(side="left", padx=4)
        ctk.CTkButton(warn, text="Download filled template", width=200,
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
        self.danger_msg = ctk.CTkLabel(f, text="", wraplength=860,
                                       anchor="w")
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
        for path in (PORTFOLIO_CSV, PROFILE_JSON, DRIFT_LOG, CACHE):
            try:
                os.remove(path)
            except OSError:
                pass
        self.lots = []
        self.profile = dict(pc.PROFILE_DEFAULTS)
        self.prices = {}
        self.home_value = pc.HOME_DEFAULT
        self._hold_expanded = set()
        self._liq_expanded = set()
        self._cov_reset()
        self.recompute()
        self.build_all()
        self.refresh_data_window()
        self.danger_msg.configure(
            text="All data deleted. The app is now empty.")
        self.status_var.set("All data deleted. The app is now empty.")

    # ---- position lifecycle (Add / Sell / Close / Reopen) ----
    def _form(self, title):
        win = ctk.CTkToplevel(self)
        win.title(title)
        win.transient(self)
        win.resizable(False, False)
        body = ctk.CTkFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=12)
        msg = ctk.CTkLabel(body, text="", text_color="orange",
                           wraplength=360, anchor="w")
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
            self.status_var.set("No open positions to sell.")
            return
        win, body, msg, entries, row = self._form(
            "Close position" if close_all else "Sell / Reduce")
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
            row("Quantity to sell")
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
                    qty = float(entries["Quantity to sell"].get())
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
