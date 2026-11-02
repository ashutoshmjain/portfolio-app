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
from tkinter import filedialog

import customtkinter as ctk

import portfolio_calc as pc

HERE = os.path.dirname(os.path.abspath(__file__))
PORTFOLIO_CSV = os.path.join(HERE, "portfolio.csv")
PROFILE_JSON = os.path.join(HERE, "profile.json")
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
        cov = pc.coverage(self.lots)
        t = cov["total"]
        ctk.CTkLabel(
            f, text="Holdings %d/%d · Cost %d/%d · Acquired dates %d/%d" % (
                t["holdings_ok"], t["holdings_n"], t["cost_ok"], t["cost_n"],
                t["acq_ok"], t["acq_n"]),
            font=ctk.CTkFont(size=15, weight="bold")).pack(
                padx=8, pady=(8, 2), anchor="w")
        ctk.CTkLabel(
            f, text="Taxable: REQUIRED (tax + harvesting need cost and "
                    "dates) · IRA/Roth/HSA: OPTIONAL (display only) · "
                    "Cash: complete by nature.",
            wraplength=1050, anchor="w").pack(padx=8, pady=2, anchor="w")
        scroll = ctk.CTkScrollableFrame(f)
        scroll.pack(fill="both", expand=True, padx=8, pady=8)
        for bank, bdata in cov["banks"].items():
            ctk.CTkLabel(scroll, text=bank,
                         font=ctk.CTkFont(size=14, weight="bold")).pack(
                             padx=6, pady=(10, 2), anchor="w")
            for acct, adata in bdata["accounts"].items():
                box = ctk.CTkFrame(scroll)
                box.pack(fill="x", padx=6, pady=4)
                flag = adata["flag"]
                color = {"REQUIRED": "orange", "OPTIONAL": "gray",
                         "COMPLETE": "green"}.get(flag, "gray")
                head = ctk.CTkFrame(box, fg_color="transparent")
                head.pack(fill="x", padx=6, pady=4)
                ctk.CTkLabel(head, text=acct,
                             font=ctk.CTkFont(weight="bold")).pack(
                                 side="left", padx=4)
                ctk.CTkLabel(head, text="[ %s ]" % flag,
                             text_color=color).pack(side="left", padx=4)
                ctk.CTkLabel(
                    head, text="%(cost)s · %(dates)s" % adata["summary"]).pack(
                        side="left", padx=8)
                menu = ctk.CTkOptionMenu(
                    head, values=pc.ACCOUNT_TYPES,
                    command=lambda v, a=acct: self.set_account_type(a, v))
                menu.set(adata["type"] or "Taxable")
                menu.pack(side="right", padx=4)
                ctk.CTkButton(head, text="Download template", width=140,
                              command=lambda a=acct:
                              self.download_account_template(a)).pack(
                                  side="right", padx=4)
                prows = []
                for p in adata["positions"]:
                    prows.append([
                        p["asset"],
                        "✓ shares" if p["shares_ok"] else "✗ shares",
                        "✓ cost" if p["cost_ok"] else "✗ cost",
                        "✓ acquired" if p["acq_ok"] else "✗ acquired"])
                Table(box, ["Position", "Shares", "Cost", "Acquired"],
                      prows).pack(fill="x", padx=6, pady=4)

    def set_account_type(self, account, atype):
        for lot in self.lots:
            if lot["account"] == account:
                lot["account_type"] = atype
        self.save_lots("Account type updated for %s." % account)

    def build_data_template(self):
        f = self._clear_data_tab("Template")
        ctk.CTkLabel(
            f, text="Fill this yourself, or paste screenshots of your broker "
                    "positions into ChatGPT, Muse, Gemini, or any AI and ask "
                    "it to fill this template — then upload the result here. "
                    "One row per lot. Open lots leave sold_date and "
                    "sale_price_per_share blank. Uploads MERGE by "
                    "account+asset: only the uploaded positions change, "
                    "everything else is left alone.",
            wraplength=1050, anchor="w").pack(padx=8, pady=8, anchor="w")
        bar = ctk.CTkFrame(f, fg_color="transparent")
        bar.pack(fill="x", padx=8, pady=4)
        ctk.CTkButton(bar, text="Download full template",
                      command=self.download_full_template).pack(
                          side="left", padx=4)
        ctk.CTkButton(bar, text="Upload filled template",
                      command=self.upload_template).pack(side="left", padx=4)
        self.template_msg = ctk.CTkLabel(f, text="", wraplength=1050,
                                         anchor="w")
        self.template_msg.pack(padx=8, pady=8, anchor="w")

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
        errors = pc.validate_lot_rows(rows, existing=self.lots)
        if errors:
            shown = "\n".join(errors[:12])
            if len(errors) > 12:
                shown += "\n… and %d more" % (len(errors) - 12)
            self.template_msg.configure(
                text="Upload REJECTED — nothing changed:\n%s" % shown)
            return
        self.lots = pc.merge_lots(self.lots, rows)
        msg = "Uploaded %d row(s) from %s." % (len(rows), path)
        self.save_lots(msg)
        # save_lots rebuilds this tab, so write to the fresh label.
        self.template_msg.configure(text=msg)

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

    def sell_form(self, close_all=False):
        opts, idx = self._lot_options()
        if not opts:
            self.status_var.set("No open positions to sell.")
            return
        win, body, msg, entries, row = self._form(
            "Close position" if close_all else "Sell / Reduce")
        ctk.CTkLabel(body, text="Position").pack(anchor="w", padx=4,
                                                 pady=(6, 0))
        menu = ctk.CTkOptionMenu(body, values=opts, width=340)
        menu.set(opts[0])
        menu.pack(anchor="w", padx=4, pady=2)
        if close_all:
            row("Quantity (full position)", opts[0].rsplit("(", 1)[-1]
                .rstrip(")"))
        else:
            row("Quantity to sell")
        row("Sold date YYYY-MM-DD",
            datetime.date.today().isoformat())
        row("Sale price per share")
        cost_ent = row("Cost per share (asked only if missing)")
        msg.pack(anchor="w", padx=4, pady=6)

        def save():
            i = idx[opts.index(menu.get())]
            lot = self.lots[i]
            try:
                qty = float(entries["Quantity (full position)"].get()) \
                    if close_all else float(entries["Quantity to sell"].get())
                if qty <= 0 or qty > (lot["shares"] or 0):
                    raise ValueError
            except ValueError:
                msg.configure(text="Quantity must be between 0 and %s."
                              % lot["shares"])
                return
            try:
                sold = datetime.date.fromisoformat(
                    entries["Sold date YYYY-MM-DD"].get().strip())
            except ValueError:
                msg.configure(text="Sold date must be YYYY-MM-DD.")
                return
            try:
                price = float(entries["Sale price per share"].get())
            except ValueError:
                msg.configure(text="Sale price must be numeric.")
                return
            cost_raw = cost_ent.get().strip()
            if lot.get("cost") is not None:
                cost = lot["cost"]
            elif cost_raw:
                try:
                    cost = float(cost_raw)
                except ValueError:
                    msg.configure(text="Cost must be numeric or blank.")
                    return
            else:
                cost = None  # flagged unknown, never invented
            if qty == lot["shares"]:
                lot["sold_date"] = sold.isoformat()
                lot["sale_price"] = price
                if cost is not None:
                    lot["cost"] = cost
            else:
                closed, opened = pc.split_for_sale(
                    lot, qty, sold.isoformat(), price, cost)
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
