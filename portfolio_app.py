#!/usr/bin/env python3
"""Portfolio Dashboard — Windows desktop app (CustomTkinter + matplotlib).

Local replacement for the Google Sheets portfolio dashboard. No Google
sign-in, no API quirks: holdings live in holdings.yaml (edit it when you
trade), prices come from yfinance, the daily close log is drift_log.csv.

Run on Windows:  python portfolio_app.py
Setup:           pip install -r requirements.txt

NEVER executes trades. Display only.
"""
import datetime
import os
import threading
import tkinter as tk

import customtkinter as ctk

import portfolio_calc as pc

HERE = os.path.dirname(os.path.abspath(__file__))
HOLDINGS = os.path.join(HERE, "holdings.yaml")
COST_BASIS = os.path.join(HERE, "cost_basis.csv")
CACHE = os.path.join(HERE, "prices_cache.json")
DRIFT_LOG = os.path.join(HERE, "drift_log.csv")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


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
        self.positions = pc.load_holdings(HOLDINGS)
        self.cost_basis = pc.load_cost_basis(COST_BASIS)
        self.prices = pc.load_price_cache(CACHE)
        self.home_value = pc.HOME_DEFAULT
        self.data = None
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
        self.data = pc.compute(self.positions, self.prices, self.home_value,
                               self.cost_basis)

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

    def build_liquidity(self):
        f = self._clear("Liquidity")
        v = self.data["view2"]
        rows = [
            ["< 65 -- available now", money(v["lt"]), pct(v["lt_pct"]),
             "Funds $135,545/yr spend until 65"],
            ["> 65 -- IRA/401(k) unlock", money(v["gt"]), pct(v["gt_pct"]),
             "Funds $111,900/yr + SS after 65"],
            ["Real Estate (home) -- illiquid", money(v["re"]),
             pct(v["re_pct"]), "Not spendable; tracks Zillow"],
            ["**TOTAL NET WORTH", "**" + money(v["tnw"]), "**100.0%", ""],
        ]
        Table(f, ["Access", "Value $", "% of net worth", "What it funds"],
              rows).pack(fill="both", expand=True, padx=6, pady=6)
        ctk.CTkLabel(
            f, text="Spendability (user-confirmed): before 65 $135,545/yr "
                    "($11,295/mo). After 65: $111,900/yr ($9,325/mo) + his SS "
                    "$1,812/mo + Anjali SS $700/mo = $11,837/mo all-in.",
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
        rows = []
        for r in self.data["view5"]:
            if r["pnl"] is None:
                pnl = "cost basis needed"
                rank = "cost basis needed"
            else:
                pnl = money(r["pnl"])
                rank = "--" if r["rank"] is None else str(r["rank"])
            rows.append([r["ticker"], r["account"], str(r["qty"]),
                         "--" if r["cost"] is None else "$%.2f" % r["cost"],
                         "--" if r["price"] is None else "$%.2f" % r["price"],
                         money(r["value"]), pnl, r["bucket"], rank])
        Table(f, ["Ticker", "Account", "Qty", "Cost/share $", "Price now",
                  "Value $", "Unrealized P&L $", "Bucket", "Harvest rank"],
              rows).pack(fill="both", expand=True, padx=6, pady=6)
        b = self.data["budget"]
        Table(f, ["2026 capital-gains budget (Medi-Cal: keep net gains "
                  "under $15K/yr)", "$"],
              [["Annual net-gains cap (your $15K guardrail)",
                money(b["cap"])],
               ["Realized GAINS YTD (Schwab Living Trust)", money(b["gains"])],
               ["Realized LOSSES banked YTD", money(b["losses"])],
               ["**Net realized YTD", "**" + money(b["net"])],
               ["**Remaining budget (leeway)", "**" + money(b["left"])]],
              ).pack(fill="both", padx=6, pady=6)
        ctk.CTkLabel(
            f, text="No cost basis on file yet — fill cost_basis.csv "
                    "(account,ticker,cost_per_share) to activate P&L and "
                    "harvest rankings. Do NOT invent basis. Wash-sale rule: "
                    "do not rebuy the same ticker within 30 days of a loss "
                    "sale.",
            wraplength=1100, anchor="w").pack(padx=6, pady=6, anchor="w")

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


if __name__ == "__main__":
    App().mainloop()
