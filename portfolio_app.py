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
    """Simple grid table: header row bold, values as labels."""

    def __init__(self, master, headers, rows, col_widths=None, **kw):
        super().__init__(master, **kw)
        self.headers = headers
        for j, h in enumerate(headers):
            lbl = ctk.CTkLabel(self, text=h, font=ctk.CTkFont(weight="bold"),
                               anchor="w")
            lbl.grid(row=0, column=j, padx=6, pady=3, sticky="w")
        for i, row in enumerate(rows, start=1):
            for j, val in enumerate(row):
                bold = str(val).startswith("**")
                text = str(val).replace("**", "")
                lbl = ctk.CTkLabel(
                    self, text=text,
                    font=ctk.CTkFont(weight="bold") if bold else None,
                    anchor="w")
                lbl.grid(row=i, column=j, padx=6, pady=2, sticky="w")


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
        self.data_win = None
        self.status_var = tk.StringVar(value="Ready — press Refresh prices.")

        # ---- Top bar (slim: actions live in the hamburger menu so a
        # narrow split-screen window never chops them) ----
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(top, text="PORTFOLIO DASHBOARD",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(
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
        self.home_entry = None

        # ---- Tabs ----
        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=4)
        for name in ("Charts", "Accounts", "Liquidity", "Diversification",
                     "Rebalance", "Tax Harvest"):
            self.tabs.add(name)
        self.tabs.set("Charts")
        self.frames = {}

        self.recompute()
        self.build_all()

    # ---- data ----
    def recompute(self):
        self.positions = pc.positions_from_lots(self.lots)
        self.cost_basis = pc.cost_map_from_lots(self.lots)
        self.data = pc.compute(self.positions, self.prices, self.home_value,
                               self.cost_basis)

    def save_lots(self, msg="Data saved."):
        pc.save_portfolio(PORTFOLIO_CSV, self.lots)
        self.recompute()
        self.build_all()
        if getattr(self, "cov_lots", None) is not None:
            self._cov_reset()
        self.refresh_data_window()
        self.status_var.set(msg)

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
        self.build_charts()

    # ---- hamburger menu ----
    def toggle_menu(self):
        """Open/close the ☰ popup holding all actions."""
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
        ctk.CTkLabel(win, text="Home (Zillow) $:").pack(
            padx=12, pady=(12, 2), anchor="w")
        self.home_entry = ctk.CTkEntry(win, width=200)
        self.home_entry.insert(0, str(self.home_value))
        self.home_entry.pack(padx=12, pady=2, anchor="w")
        ctk.CTkButton(win, text="Apply home",
                      command=self.apply_home_from_menu).pack(
                          padx=12, pady=4, fill="x")
        ctk.CTkButton(win, text="Refresh prices",
                      command=self.refresh_from_menu).pack(
                          padx=12, pady=4, fill="x")
        ctk.CTkButton(win, text="Log today's close",
                      command=self.log_from_menu).pack(
                          padx=12, pady=4, fill="x")
        ctk.CTkButton(win, text="Manage data",
                      command=self.manage_data_from_menu).pack(
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

    def apply_home(self):
        if self.home_entry is None or not self.home_entry.winfo_exists():
            self.status_var.set("Open the ☰ menu to set the home value.")
            return
        try:
            self.home_value = float(self.home_entry.get().replace(",", "")
                                    .replace("$", ""))
        except ValueError:
            self.status_var.set("Home value not a number — kept previous.")
            return
        self.recompute()
        self.build_all()
        self.status_var.set("Home updated to %s." % money(self.home_value))

    def apply_home_from_menu(self):
        self.apply_home()
        self._close_menu()

    def refresh_from_menu(self):
        self._close_menu()
        self.refresh_async()

    def log_from_menu(self):
        self._close_menu()
        self.log_close()

    def manage_data_from_menu(self):
        self._close_menu()
        self.open_data_window()

    # ---- builders ----
    def _clear(self, tab):
        frame = self.tabs.tab(tab)
        for w in frame.winfo_children():
            w.destroy()
        return frame

    def build_all(self):
        self.build_accounts()
        self.build_liquidity()
        self.build_diversification()
        self.build_rebalance()
        self.build_tax()
        self.build_charts()

    def build_accounts(self):
        f = self._clear("Accounts")
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
        f = self._clear("Liquidity")
        v = self.data["view2"]
        sp = pc.spending_capacity(self.profile)
        rows = [
            ["< 65 -- available now", money(v["lt"]), pct(v["lt_pct"]),
             "Funds %s/yr spend until 65" % money(sp["before65"])],
            ["> 65 -- IRA/401(k) unlock", money(v["gt"]), pct(v["gt_pct"]),
             "Funds %s/yr + SS after 65" % money(sp["after65_base"])],
            ["Real Estate (home) -- illiquid", money(v["re"]),
             pct(v["re_pct"]), "Not spendable; tracks Zillow"],
            ["**TOTAL NET WORTH", "**" + money(v["tnw"]), "**100.0%", ""],
        ]
        Table(f, ["Access", "Value $", "% of net worth", "What it funds"],
              rows).pack(fill="both", expand=True, padx=6, pady=6)
        ctk.CTkLabel(
            f, text="Spendability (sheet-ported, live from profile): before "
                    "65 %s/yr ($%s/mo). After 65: %s/yr ($%s/mo) + owner SS "
                    "$%s/mo + spouse SS $%s/mo = %s/mo all-in."
                    % (money(sp["before65"]), money(sp["before65"] / 12),
                       money(sp["after65_base"]),
                       money(sp["after65_base"] / 12),
                       money(self.profile.get("ss_owner_monthly", 0)),
                       money(self.profile.get("ss_spouse_monthly", 0)),
                       money(sp["after65_allin"] / 12)),
            wraplength=1100, anchor="w").pack(padx=6, pady=6, anchor="w")

    def build_diversification(self):
        f = self._clear("Diversification")
        rows = []
        for r in self.data["view3"]:
            rows.append([r["bucket"], pct(r["target_pct"]),
                         money(r["target_dollar"]), money(r["actual"]),
                         pct(r["actual_pct"]),
                         "%+.1fpp" % r["deviation_pp"],
                         money(r["rebalance"])])
        Table(f, ["Bucket", "Target %", "Target $", "Actual $", "Actual %",
                  "Deviation (pp)", "Rebalance buy(+) / sell(-)"],
              rows).pack(fill="both", expand=True, padx=6, pady=6)
        ctk.CTkLabel(
            f, text="Standard v3 = 15:15:35:15:20 over TOTAL net worth. "
                    "BTC 15% = 9% spot/ETF + 6% MSTR. Cash 15% incl 20% STRC. "
                    "RE 20% = your home (Zillow; structural, can't rebalance). "
                    "NOTE: STRC is BTC-correlated preferred — in a BTC crash "
                    "your 'cash' won't act like cash; effective BTC exposure "
                    "runs ~2-3pp above stated.",
            wraplength=1100, anchor="w").pack(padx=6, pady=6, anchor="w")

    def build_rebalance(self):
        f = self._clear("Rebalance")
        ctk.CTkLabel(
            f, text="VIEW 4 — REBALANCE PLAN (display only, NEVER executes "
                    "trades). All 4 trades inside Schwab Ashu IRA: $0 tax, "
                    "Medi-Cal safe. Verify on the trade ticket before "
                    "executing; tell Brownie after each execution.",
            wraplength=1100, anchor="w").pack(padx=6, pady=6, anchor="w")
        rows = []
        for t in self.data["view4"]["trades"]:
            rows.append([str(t["n"]), "Schwab Ashu IRA", t["sell"],
                         "--" if t["sell_sh"] is None else f"{t['sell_sh']:,}",
                         money(t["proceeds"]), t["buy"],
                         "--" if t["buy_sh"] is None else f"{t['buy_sh']:,}",
                         "$0 (IRA)"])
        Table(f, ["#", "Account", "Sell", "Sell shares", "Est. proceeds $",
                  "Buy", "Est. buy shares", "Tax cost"],
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
        Table(f, ["Bucket", "Before $", "Before %", "After $", "After %"],
              rows).pack(fill="both", padx=6, pady=6)
        ctk.CTkLabel(
            f, text="Landing ≈ 15.0 / 15.0 / 35.0 / 16.5 / 18.5 — BTC, gold "
                    "and equities on target; the ~1.5pp cash overweight is "
                    "the residual (liquid can't fund the RE gap without "
                    "selling the house, so cash absorbs it). New BTC money "
                    "goes to IBIT: MSTR is already ~6.7% vs the 6% sub-target.",
            wraplength=1100, anchor="w").pack(padx=6, pady=6, anchor="w")

    def build_tax(self):
        f = self._clear("Tax Harvest")
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
                         "cost or acquired date needed" if pnl is None
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
               ["Pre-app realized gains (%s)"
                % self.profile.get("other_realized_gains_note", ""),
                money(other)],
               ["Realized from sold lots above", money(total - other)],
               ["**Net realized YTD", "**" + money(total)],
               ["**Remaining budget (leeway)", "**" + money(cap - total)]],
              ).pack(fill="both", padx=6, pady=6)
        note = ("Itemized sold rows and the pre-app field must NOT overlap "
                "— no double-counting. ")
        if unknown:
            note += ("%d sold lot(s) have unknown basis and are EXCLUDED "
                     "from the total. " % unknown)
        note += ("Do NOT invent basis. Wash-sale rule: do not rebuy the "
                 "same asset within 30 days of a loss sale.")
        ctk.CTkLabel(f, text=note, wraplength=1100,
                     anchor="w").pack(padx=6, pady=6, anchor="w")

    def build_charts(self):
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        from matplotlib.figure import Figure
        f = self._clear("Charts")
        d = self.data["drift"]
        drift_txt = (
            "Drift (calendar-year baseline $4,526K = liquid $3,595K + home "
            "$931K): actual YTD %s | standard YTD %s | drift %s (%s) | "
            "standard total %s"
            % (pct(d["actual_ytd"]), pct(d["standard_ytd"]),
               pct(d["drift_pp"]), money(d["drift_dollar"]),
               money(d["standard_total"])))
        ctk.CTkLabel(f, text=drift_txt, wraplength=1100,
                     anchor="w").pack(padx=6, pady=6, anchor="w")
        fig1 = Figure(figsize=(10, 4.2), dpi=100)
        pc.make_allocation_chart(fig1, self.data["view3"])
        FigureCanvasTkAgg(fig1, master=f).get_tk_widget().pack(
            fill="both", padx=6, pady=6)
        # Tall drift chart: the whole reason for leaving Google Sheets.
        fig2 = Figure(figsize=(10, 8.5), dpi=100)
        pc.make_drift_chart(fig2, pc.load_drift_log(DRIFT_LOG))
        FigureCanvasTkAgg(fig2, master=f).get_tk_widget().pack(
            fill="both", expand=True, padx=6, pady=6)


    # ---- Data window (Manage data) ----
    def open_data_window(self):
        if self.data_win is not None and self.data_win.winfo_exists():
            self.data_win.lift()
            self.data_win.focus_force()
            return
        win = ctk.CTkToplevel(self)
        win.title("Manage data")
        win.geometry("1120x760")
        win.transient(self)
        tabs = ctk.CTkTabview(win)
        tabs.pack(fill="both", expand=True, padx=10, pady=10)
        for name in ("Coverage", "Template", "Profile"):
            tabs.add(name)
        self.data_win = win
        self.data_tabs = tabs
        self.cov_lots = []
        self.cov_next_rid = 0
        self.cov_filter = None
        self.cov_guide = None
        self._cov_reset()
        win.protocol("WM_DELETE_WINDOW", self._close_data_window)
        self.refresh_data_window()
        win.after(50, self._show_data_window)

    def _show_data_window(self):
        if self.data_win is not None and self.data_win.winfo_exists():
            self.data_win.deiconify()
            self.data_win.lift()

    def refresh_data_window(self):
        if self.data_win is None or not self.data_win.winfo_exists():
            return
        self.build_data_coverage()
        self.build_data_template()
        self.build_data_profile()

    def _clear_data_tab(self, name):
        frame = self.data_tabs.tab(name)
        for w in frame.winfo_children():
            w.destroy()
        return frame

    def build_data_coverage(self):
        f = self._clear_data_tab("Coverage")
        self.cov_nav_rows = []
        self.cov_widgets = {}
        t = self._cov_totals()
        top = ctk.CTkFrame(f, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(8, 2))
        ctk.CTkLabel(
            top, text="Holdings %d/%d · Cost %d/%d · Acquired dates %d/%d" % (
                t["holdings_ok"], t["holdings_n"], t["cost_ok"], t["cost_n"],
                t["acq_ok"], t["acq_n"]),
            font=ctk.CTkFont(size=15, weight="bold")).pack(
                side="left", padx=4)
        n = self._cov_counts()
        self.cov_save_btn = ctk.CTkButton(
            top, text="Save (%d)" % n, width=110,
            command=self._cov_save,
            state="normal" if n else "disabled")
        self.cov_save_btn.pack(side="right", padx=4)
        ctk.CTkButton(top, text="Revert", width=80,
                      command=self._cov_revert).pack(side="right", padx=4)
        if self.cov_filter:
            ctk.CTkButton(top, text="Show all", width=80,
                          command=self._cov_show_all).pack(side="right",
                                                          padx=4)
        else:
            ctk.CTkButton(top, text="Feed one account", width=130,
                          command=self._cov_guide_start).pack(side="right",
                                                             padx=4)
        self.cov_warn = ctk.CTkLabel(f, text="", text_color="orange",
                                     wraplength=1050, anchor="w")
        self.cov_warn.pack(padx=8, anchor="w")
        if self.cov_guide:
            self._cov_guide_panel(f)
        else:
            ctk.CTkLabel(
                f, text="Taxable: REQUIRED (tax + harvesting need cost and "
                        "dates) · IRA/Roth/HSA: OPTIONAL (display only) · "
                        "Cash: complete by nature. Rows are locked — click "
                        "Edit on a row to change it. Typing never recomputes; "
                        "Save commits everything at once.",
                wraplength=1050, anchor="w").pack(padx=8, pady=2, anchor="w")
        scroll = ctk.CTkScrollableFrame(f)
        scroll.pack(fill="both", expand=True, padx=8, pady=8)
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
                         font=ctk.CTkFont(size=14, weight="bold")).pack(
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
        for col, (txt, w) in enumerate(
                [("Bank", 80), ("Account", 150), ("Asset", 110),
                 ("Shares", 80), ("Cost $", 80), ("Acquired", 120),
                 ("Sold", 120), ("Sale $", 80), ("", 175),
                 ("", 52), ("", 52)]):
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
        rid = row["_rid"]
        locked = row.get("_locked", True)
        state = "disabled" if locked else "normal"
        fr = ctk.CTkFrame(box, fg_color="transparent")
        fr.pack(fill="x", padx=6, pady=1)
        W = self.cov_widgets.setdefault(rid, {})
        nav = []

        def entry(col, width, value):
            var = tk.StringVar(value="" if value is None else str(value))
            ent = ctk.CTkEntry(fr, width=width, textvariable=var,
                               state=state)
            ent.grid(row=0, column=col, padx=2)
            return ent, var

        bank_ent, bank_var = entry(0, 80, row.get("bank", ""))
        W["bank"], W["bank_var"] = bank_ent, bank_var
        try:
            W["bd_def"] = bank_ent.cget("border_color")
        except tk.TclError:
            W["bd_def"] = "gray"
        bank_var.trace_add(
            "write", lambda *_a, r=rid: self._cov_typed(r, "bank"))
        nav.append(bank_ent)

        accounts = sorted({r.get("account") for r in self.cov_lots
                           if r.get("account")})
        assets = sorted({r.get("asset") for r in self.cov_lots
                         if r.get("asset")})

        def pick_cell(col, field, options, width, current):
            cell = ctk.CTkFrame(fr, fg_color="transparent")
            cell.grid(row=0, column=col, padx=2)
            vals = list(options) + ["< new >"]
            menu = ctk.CTkOptionMenu(
                cell, width=width, values=vals, state=state,
                command=lambda v, r=rid, f=field: self._cov_menu(r, f, v))
            menu.pack()
            new_var = tk.StringVar()
            new_ent = ctk.CTkEntry(cell, width=width, textvariable=new_var,
                                   state=state)
            if current in options:
                menu.set(current)
            else:
                menu.set("< new >")
                new_var.set(current or "")
                new_ent.pack()
            new_var.trace_add(
                "write", lambda *_a, r=rid, f=field: self._cov_typed(r, f))
            W[field + "_menu"] = menu
            W[field + "_new"] = new_ent
            W[field + "_new_var"] = new_var
            nav.append(menu)
            return menu

        pick_cell(1, "account", accounts, 150, row.get("account") or "")
        pick_cell(2, "asset", assets, 110, row.get("asset") or "")
        try:
            W["fg_def"] = W["account_menu"].cget("fg_color")
        except tk.TclError:
            W["fg_def"] = None

        sh_ent, sh_var = entry(3, 80, row.get("shares"))
        co_ent, co_var = entry(4, 80, row.get("cost"))
        W.update(shares=sh_ent, shares_var=sh_var, cost=co_ent,
                 cost_var=co_var)
        sh_var.trace_add(
            "write", lambda *_a, r=rid: self._cov_typed(r, "shares"))
        co_var.trace_add(
            "write", lambda *_a, r=rid: self._cov_typed(r, "cost"))
        nav += [sh_ent, co_ent]

        def date_cell(col, field):
            acell = ctk.CTkFrame(fr, fg_color="transparent")
            acell.grid(row=0, column=col, padx=2)
            var = tk.StringVar(value=row.get(field) or "")
            ent = ctk.CTkEntry(acell, width=88, textvariable=var,
                               state=state)
            ent.pack(side="left")
            ctk.CTkButton(acell, text="📅", width=28,
                          state=state,
                          command=lambda r=rid, f=field:
                          self._cov_calendar(r, f)).pack(side="left", padx=1)
            var.trace_add(
                "write", lambda *_a, r=rid, f=field: self._cov_typed(r, f))
            W[field] = ent
            W[field + "_var"] = var
            nav.append(ent)

        date_cell(5, "acquired")
        date_cell(6, "sold_date")
        sa_ent, sa_var = entry(7, 80, row.get("sale_price"))
        W.update(sale_price=sa_ent, sale_price_var=sa_var)
        sa_var.trace_add(
            "write", lambda *_a, r=rid: self._cov_typed(r, "sale_price"))
        nav.append(sa_ent)

        math = ctk.CTkLabel(fr, text="", width=175, anchor="w")
        math.grid(row=0, column=8, padx=2)
        W["math"] = math
        edit = ctk.CTkButton(fr, text="Lock" if not locked else "Edit",
                             width=52,
                             command=lambda r=rid: self._cov_toggle_lock(r))
        edit.grid(row=0, column=9, padx=2)
        ctk.CTkButton(fr, text="Del", width=52,
                      command=lambda r=rid: self._cov_delete(r)).grid(
                          row=0, column=10, padx=2)
        ridx = len(self.cov_nav_rows)
        self.cov_nav_rows.append(nav)
        for cidx, widget in enumerate(nav):
            widget.bind("<Return>", lambda _e, rr=ridx, c=cidx:
                        self._cov_move(rr + 1, c))
            widget.bind("<Up>", lambda _e, rr=ridx, c=cidx:
                        self._cov_move(rr - 1, c))
            widget.bind("<Down>", lambda _e, rr=ridx, c=cidx:
                        self._cov_move(rr + 1, c))
        self._cov_sync_new_visibility(rid)
        self._cov_paint_row(rid)

    def _cov_move(self, ridx, cidx):
        if 0 <= ridx < len(self.cov_nav_rows):
            row = self.cov_nav_rows[ridx]
            if 0 <= cidx < len(row):
                try:
                    row[cidx].focus_set()
                except tk.TclError:
                    pass
        return "break"

    def _cov_row_by_rid(self, rid):
        return next(r for r in self.cov_lots if r["_rid"] == rid)

    def _cov_menu(self, rid, field, value):
        self._cov_sync_new_visibility(rid)
        self._cov_typed(rid, field)

    def _cov_sync_new_visibility(self, rid):
        W = self.cov_widgets.get(rid, {})
        row = self._cov_row_by_rid(rid)
        for field in ("account", "asset"):
            menu = W.get(field + "_menu")
            new_ent = W.get(field + "_new")
            if menu is None or new_ent is None:
                continue
            picked_new = menu.get() == "< new >"
            has_new = bool(new_ent.winfo_manager())
            if picked_new and not has_new:
                new_ent.pack()
            elif not picked_new and has_new:
                new_ent.pack_forget()

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
        if sh and co is not None:
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
        if getattr(self, "cov_save_btn", None) is not None and \
                self.cov_save_btn.winfo_exists():
            self.cov_save_btn.configure(
                text="Save (%d)" % n, state="normal" if n else "disabled")
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
            bits.append("%d row(s) have invalid cells (red) — fix before "
                        "Save" % bad_rows)
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
                text="%d required positions to go" % left)

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
        new2 = [dict(l) for l in new]
        derrs = pc.drawdown_amounts(new2, needs)
        if derrs:
            self.cov_warn.configure(text="Save blocked:\n" + "\n".join(derrs))
            self.status_var.set("Coverage not saved — dated shares exceed "
                                "the unattributed balance.")
            return False
        self.lots = new2
        self.save_lots("Coverage saved.")
        return True

    def _cov_revert(self):
        self._cov_reset()
        self.build_data_coverage()
        self.status_var.set("Unsaved coverage edits discarded.")

    def _cov_add_row(self, bank, acct):
        atype = self._cov_account_type(
            [r for r in self.cov_lots if r.get("account") == acct])
        row = {"bank": bank, "account": acct, "account_type": atype,
               "asset": "", "shares": None, "cost": None, "acquired": "",
               "sold_date": "", "sale_price": None,
               "_rid": self.cov_next_rid, "_orig": None, "_locked": False}
        self.cov_next_rid += 1
        self.cov_lots.append(row)
        self.build_data_coverage()

    def _cov_delete(self, rid):
        row = self._cov_row_by_rid(rid)
        if not messagebox.askyesno(
                "Delete lot",
                "Delete this lot row?\n%s — %s (%s)\nOnly this row is "
                "removed." % (row.get("account"), row.get("asset"),
                               row.get("shares"))):
            return
        self.cov_lots = [r for r in self.cov_lots if r["_rid"] != rid]
        self.build_data_coverage()
        self._cov_refresh_chrome()

    def _cov_toggle_lock(self, rid):
        self._cov_row_by_rid(rid)["_locked"] = \
            not self._cov_row_by_rid(rid).get("_locked", True)
        self.build_data_coverage()

    def _cov_calendar(self, rid, field):
        import calendar as calmod
        W = self.cov_widgets.get(rid, {})
        var = W.get(field + "_var")
        if var is None:
            return
        try:
            cur = datetime.date.fromisoformat(var.get().strip())
        except ValueError:
            cur = datetime.date.today()
        win = ctk.CTkToplevel(self.data_win)
        win.title("Pick a date")
        win.transient(self.data_win)
        win.resizable(False, False)
        state = {"y": cur.year, "m": cur.month}
        title = ctk.CTkLabel(win, text="", font=ctk.CTkFont(weight="bold"))
        title.pack(padx=10, pady=(10, 2))
        grid = ctk.CTkFrame(win, fg_color="transparent")
        grid.pack(padx=10, pady=6)
        for c, wd in enumerate(["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]):
            ctk.CTkLabel(grid, text=wd, width=36).grid(row=0, column=c)

        def draw():
            for w in grid.winfo_children():
                if int(str(w.grid_info().get("row", 0))) >= 1:
                    w.destroy()
            title.configure(
                text="%s %d" % (calmod.month_name[state["m"]], state["y"]))
            r = 1
            for week in calmod.monthcalendar(state["y"], state["m"]):
                c = 0
                for day in week:
                    if day:
                        ctk.CTkButton(
                            grid, text=str(day), width=36,
                            command=lambda d=day: pick(d)).grid(row=r,
                                                               column=c,
                                                               padx=1, pady=1)
                    c += 1
                r += 1

        def pick(day):
            var.set("%04d-%02d-%02d" % (state["y"], state["m"], day))
            win.destroy()

        def step(dm):
            m = state["m"] + dm
            state["y"] += (m - 1) // 12
            state["m"] = (m - 1) % 12 + 1
            draw()

        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(padx=10, pady=(0, 10))
        ctk.CTkButton(bar, text="<", width=40,
                      command=lambda: step(-1)).pack(side="left", padx=4)
        ctk.CTkButton(bar, text=">", width=40,
                      command=lambda: step(1)).pack(side="left", padx=4)
        draw()
        win.after(50, lambda: (win.deiconify(), win.lift())
                  if win.winfo_exists() else None)

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
            self.status_var.set("All required accounts are complete.")
            return
        self.cov_filter = todo[0]
        self.cov_guide = self.cov_filter
        self.build_data_coverage()

    def _cov_guide_next(self):
        todo = [a for a in self._cov_incomplete_required()
                if a != self.cov_filter]
        if not todo:
            self.cov_filter = None
            self.cov_guide = None
            self.build_data_coverage()
            self.status_var.set("All required accounts complete — full grid.")
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
        left = self._cov_totals()["required_left"]
        self.cov_count_lbl = ctk.CTkLabel(
            panel, text="%d required positions to go" % left,
            font=ctk.CTkFont(size=14, weight="bold"))
        self.cov_count_lbl.pack(padx=8, pady=(6, 2), anchor="w")
        ctk.CTkLabel(
            panel, text="Feeding: %s — save this account, then take the "
                        "next. The full grid stays available via Show all."
                        % self.cov_filter,
            wraplength=1000, anchor="w").pack(padx=8, anchor="w")
        bank = next((r.get("bank") for r in self.cov_lots
                     if r.get("account") == self.cov_filter), "")
        lines = []
        for g in BROKER_GUIDE:
            if g["field"] in ("bank", "account", "account_type"):
                continue
            if "Schwab" in (bank or ""):
                where = g["schwab"]
            elif "Vanguard" in (bank or ""):
                where = g["vanguard"]
            else:
                where = g["concept"] + " (Holdings/Positions → Cost " \
                    "basis/Lots; History/Realized gains for sold lots)"
            lines.append("%s: %s  (e.g. %s)" % (
                g["field"], where, g["example"]))
        ctk.CTkLabel(panel, text="\n".join(lines), wraplength=1000,
                     anchor="w", justify="left").pack(padx=8, pady=4,
                                                     anchor="w")
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
            self.status_var.set("Save or Revert coverage edits first.")
            self.open_data_window()
            return
        self.save_lots("Account type updated for %s." % account)

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

    def _close_data_window(self):
        if self.data_win is None or not self.data_win.winfo_exists():
            self.data_win = None
            return
        n = self._cov_counts()
        if n:
            ans = messagebox.askyesnocancel(
                "Unsaved changes",
                "%d unsaved change(s). Save before closing?" % n)
            if ans is None:
                return
            if ans and not self._cov_save():
                return
        self.data_win.destroy()
        self.data_win = None

    def refresh_data_window(self):
        if self.data_win is None or not self.data_win.winfo_exists():
            return
        # Builders render from the working copy, so staged keystrokes
        # survive rebuilds; only Save/Revert replace cov_lots.
        self.build_data_coverage()
        self.build_data_template()
        self.build_data_profile()

    def build_data_template(self):
        f = self._clear_data_tab("Template")
        ctk.CTkLabel(
            f, text="Fill this yourself, or paste screenshots of your broker "
                    "positions into ChatGPT, Muse, Gemini, or any AI and ask "
                    "it to fill this template — then upload the result here "
                    "(Copy AI prompt button below). "
                    "One row per lot. Open lots leave sold_date and "
                    "sale_price_per_share blank. Uploads upsert by lot "
                    "(account+asset+acquired+cost): matching lots update, "
                    "new lots insert, uploads NEVER delete rows.",
            wraplength=1050, anchor="w").pack(padx=8, pady=8, anchor="w")
        bar = ctk.CTkFrame(f, fg_color="transparent")
        bar.pack(fill="x", padx=8, pady=4)
        ctk.CTkButton(bar, text="Download full template",
                      command=self.download_full_template).pack(
                          side="left", padx=4)
        ctk.CTkButton(bar, text="Upload filled template",
                      command=self.upload_template).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="Paste rows",
                      command=self.paste_rows).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="Import broker CSV",
                      command=self.import_broker_csv).pack(side="left",
                                                          padx=4)
        ctk.CTkButton(bar, text="Copy AI prompt",
                      command=self.copy_ai_prompt).pack(side="left", padx=4)
        self.template_msg = ctk.CTkLabel(f, text="", wraplength=1050,
                                         anchor="w")
        self.template_msg.pack(padx=8, pady=4, anchor="w")
        ctk.CTkLabel(f, text="Where each field lives at your broker:",
                     font=ctk.CTkFont(weight="bold")).pack(padx=8, pady=(8, 2),
                                                           anchor="w")
        scroll = ctk.CTkScrollableFrame(f)
        scroll.pack(fill="both", expand=True, padx=8, pady=4)
        for g in BROKER_GUIDE:
            ctk.CTkLabel(scroll, text=g["field"],
                         font=ctk.CTkFont(weight="bold")).pack(
                             padx=6, anchor="w")
            ctk.CTkLabel(
                scroll,
                text="Concept: %s\nSchwab: %s\nVanguard: %s\nExample: %s" % (
                    g["concept"], g["schwab"], g["vanguard"], g["example"]),
                wraplength=1000, anchor="w").pack(padx=18, pady=(0, 8),
                                                 anchor="w")
        ctk.CTkLabel(
            scroll,
            text="Faster than screenshots: both brokers export these lot "
                 "tables as CSV — Schwab: Lot Details → Export, and Realized "
                 "Gain/Loss → Export Lot Details; Vanguard: Export at the "
                 "top right of the cost basis table. Hand the export to any "
                 "AI to fill the template, or use Import broker CSV. Other "
                 "brokers (Wells, Chase, Coinbase, Cash App, Health Equity): "
                 "same concepts — Holdings/Positions → Cost basis/Lots for "
                 "open lots; History/Realized gains for closed lots; the "
                 "year-end 1099-B is the authority for sold lots.",
            wraplength=1000, anchor="w").pack(padx=6, pady=8, anchor="w")

    def copy_ai_prompt(self):
        self.clipboard_clear()
        self.clipboard_append(AI_TEMPLATE_PROMPT)
        self.template_msg.configure(
            text="AI prompt copied — paste it with broker screenshots into "
                 "ChatGPT, Muse, Gemini, or any AI, then upload the CSV here.")

    def _ingest_rows(self, rows, source):
        """Validate-then-merge path shared by upload, paste, and import."""
        errors = pc.validate_lot_rows(rows, existing=self.lots)
        if errors:
            shown = "\n".join(errors[:12])
            if len(errors) > 12:
                shown += "\n… and %d more" % (len(errors) - 12)
            return "REJECTED — nothing changed:\n%s" % shown
        merged, _ins, derrs = pc.merge_upload(self.lots, rows)
        if derrs:
            return "REJECTED — nothing changed:\n%s" % "\n".join(derrs)
        self.lots = merged
        self.save_lots("Ingested %d row(s) from %s."
                       % (len(rows), source))
        return None

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
        self.template_msg.configure(
            text=msg if msg else "Pasted %d row(s) from clipboard." % len(rows))

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
        self.template_msg.configure(
            text=msg if msg else "Imported %d row(s)." % len(rows))

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
        self.template_msg.configure(
            text=msg if msg else "Uploaded %d row(s)." % len(rows))

    def build_data_profile(self):
        f = self._clear_data_tab("Profile")
        self.prof_entries = {}
        grid = ctk.CTkFrame(f, fg_color="transparent")
        grid.pack(fill="x", padx=8, pady=8)
        fields = [("date_of_birth", "Date of birth (YYYY-MM or YYYY-MM-DD)"),
                  ("ss_owner_monthly", "Owner SS $/mo"),
                  ("ss_spouse_monthly", "Spouse SS $/mo"),
                  ("other_realized_gains_current_year",
                   "Other realized gains this year $"),
                  ("other_realized_gains_note", "Note for the above")]
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
        ctk.CTkLabel(
            f, text="Spending capacity (live): BEFORE 65 %s/yr · AFTER 65 "
                    "%s/yr base + SS = %s/yr all-in. Owner is %s, turns 65 "
                    "in %s. Actual spending ≈ $60K/yr (context only)."
                    % (money(sp["before65"]), money(sp["after65_base"]),
                       money(sp["after65_allin"]),
                       "--" if sp["age"] is None else "age %d" % sp["age"],
                       sp["turns65"]),
            wraplength=1050, anchor="w").pack(padx=8, pady=8, anchor="w")

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
        except ValueError:
            self.status_var.set("Profile not saved — amounts must be numbers.")
            return
        pc.save_profile(PROFILE_JSON, self.profile)
        self.recompute()
        self.build_all()
        self.refresh_data_window()
        self.status_var.set("Profile saved.")

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
            self.save_lots("Position added to %s." % acct)

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
                self.save_lots("Sold %s of %s (%s)." % (
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
            self.save_lots("Sale recorded for %s." % lot["asset"])

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
            self.save_lots("Position reopened.")

        ctk.CTkButton(body, text="Reopen", command=save).pack(
            anchor="w", padx=4, pady=8)

if __name__ == "__main__":
    App().mainloop()
