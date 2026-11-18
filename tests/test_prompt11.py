"""Prompt 11 committed checks (a)-(m): type scale, header title, watchlist
columns, value cards, REQUIRED move, cash row, Copy-table alignment.
Stdlib unittest only, no new dependency. Source-structure guards read the
repo files literally; behavior guards use headless-pure helpers (no Tk
window is created by this suite). Needles avoid backslash escapes.
"""
import datetime
import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import portfolio_app as P
import portfolio_calc as pc
from plugins import medical

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def repo_source(name):
    with open(os.path.join(REPO, name), encoding="utf-8") as f:
        return f.read()


APP = repo_source("portfolio_app.py")
MED = repo_source(os.path.join("plugins", "medical.py"))


def overview_region():
    return APP[APP.find("def _build_overview_inner"):
               APP.find("def _overview_cards")]


def holdings_region():
    return APP[APP.find("def build_holdings"):APP.find("def _copy_holdings")]


class TestTypeScale(unittest.TestCase):
    def test_constants(self):
        # Superseded by Prompt 14 item 1 (tutorial scale): text 14,
        # headings 18, table headers 12, small 12; card values stay 18.
        self.assertEqual(P.FS_BODY, 14)
        self.assertEqual(P.FS_HEAD, 18)
        self.assertEqual(P.FS_TITLE, 18)
        self.assertEqual(P.FS_TABLE_HEAD, 12)
        self.assertEqual(P.FS_SMALL, 12)

    def test_no_numeric_sizes(self):
        # Superseded by Prompt 14 item 2: the 11px header literal is
        # gone with the SelectableMsg subtitle — no numeric font size
        # literal remains anywhere.
        for src in (APP, MED):
            self.assertEqual(re.findall(r"CTkFont\(size=(\d+)", src), [])


class TestHeaderTitle(unittest.TestCase):
    def test_portfolio(self):
        # Superseded by Prompt 12 item 3: the old top-banner "Portfolio"
        # label is gone with the hamburger bar; the window and the
        # sidebar title now read exactly "Retirement Portfolio".
        self.assertIn('text="Retirement Portfolio"', APP)
        self.assertNotIn("PORTFOLIO DASHBOARD", APP)
        self.assertNotIn('text="Portfolio",', APP)


class TestWatchlistHeaders(unittest.TestCase):
    def test_seven_headers(self):
        self.assertEqual(pc.WATCH_HEADERS,
                         ["Ticker", "Price", "Week", "Month", "Quarter",
                          "Market cap ($T)", "PEG"])
        self.assertIn("pc.WATCH_HEADERS", APP)


class TestWatchRow(unittest.TestCase):
    def test_seven_values(self):
        q = {"price": 4231.37, "mcap": 4.52e12, "week": 4180.0,
             "month": 4100.5, "quarter": 3900.0, "peg": 1.283}
        self.assertEqual(P.watch_row_values("AAPL", q),
                         ["AAPL", "$4,231", "$4,180", "$4,100", "$3,900",
                          "$4.52T", "1.28"])

    def test_missing_is_bare_dash(self):
        q = {"price": 100.0, "mcap": None, "week": None, "month": None,
             "quarter": None, "peg": None}
        self.assertEqual(P.watch_row_values("GLD", q),
                         ["GLD", "$100", "-", "-", "-", "--", "-"])

    def test_cache_carries_new_keys(self):
        d = {"watchlist": {"MSTR": {"price": 150.0, "mcap": 5e9,
                                    "week": 140.0, "month": 130.0,
                                    "quarter": 120.0, "peg": 0.95}}}
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "prices_cache.json")
            with open(p, "w") as f:
                json.dump(d, f)
            got = pc.load_watchlist_cache(p)
        self.assertEqual(got["MSTR"]["week"], 140.0)
        self.assertEqual(got["MSTR"]["month"], 130.0)
        self.assertEqual(got["MSTR"]["quarter"], 120.0)
        self.assertEqual(got["MSTR"]["peg"], 0.95)


class TestBackdatePicker(unittest.TestCase):
    def test_picks_close_on_or_before(self):
        bars = [(datetime.date(2026, 11, 9), 100.0),
                (datetime.date(2026, 11, 10), 101.0),
                (datetime.date(2026, 11, 11), 102.0),
                (datetime.date(2026, 11, 12), 103.0),
                (datetime.date(2026, 11, 13), 104.0)]
        today = datetime.date(2026, 11, 18)
        week, month, quarter = pc.pick_backdate_closes(bars, today)
        self.assertEqual(week, 102.0)
        self.assertIsNone(month)
        self.assertIsNone(quarter)

    def test_month_and_quarter(self):
        bars = [(datetime.date(2026, 8, 18), 90.0),
                (datetime.date(2026, 10, 18), 95.0),
                (datetime.date(2026, 11, 13), 104.0)]
        today = datetime.date(2026, 11, 18)
        week, month, quarter = pc.pick_backdate_closes(bars, today)
        self.assertEqual(week, 95.0)
        self.assertEqual(month, 95.0)
        self.assertEqual(quarter, 90.0)


class TestOverviewCards(unittest.TestCase):
    def _inputs(self):
        d = {"actual_ytd": 0.093, "standard_ytd": 0.036, "drift_pp": 0.057}
        sp = {"headroom": 1531.0, "after65_base": 50000.0, "other": 5000.0,
              "agi_total": 118316.0, "agi_threshold": 63000.0}
        med = {"qualified": False, "magi": 24250.0, "ceiling": 25000.0}
        return d, sp, med

    def test_four_cards(self):
        d, sp, med = self._inputs()
        cards = pc.overview_cards(d, sp, 4750.0, None, " (projected)", med)
        self.assertEqual([c["title"] for c in cards],
                         ["Drift (year to date)", "Medi-Cal",
                          "Gains headroom", "After-65 AGI guardrail"])
        self.assertEqual(cards[0]["value"], "5.7pp")
        self.assertEqual(cards[0]["detail"], "actual 9.3% vs standard 3.6%")
        self.assertEqual(cards[1]["value"], "Not qualified")
        self.assertEqual(cards[1]["detail"], "MAGI $24,250 vs $25,000 ceiling")
        self.assertEqual(cards[2]["value"], "$1,531")
        self.assertEqual(cards[2]["detail"], "of the $4,750 cap (projected)")
        self.assertEqual(cards[3]["value"], "OVER by $55,316")
        self.assertEqual(cards[3]["detail"], "$118,316 vs $63,000 threshold")

    def test_no_medical_card_when_inactive(self):
        d, sp, _med = self._inputs()
        cards = pc.overview_cards(d, sp, 4750.0, None, "", None)
        self.assertEqual(len(cards), 3)
        self.assertNotIn("Medi-Cal", [c["title"] for c in cards])

    def test_unset_caps(self):
        d = {"actual_ytd": 0.01, "standard_ytd": 0.02, "drift_pp": -0.01}
        sp = {"headroom": None, "after65_base": 0.0, "other": 0.0,
              "agi_total": None, "agi_threshold": None}
        cards = pc.overview_cards(d, sp, None, None, "", None)
        self.assertEqual(cards[1]["value"], "-")
        self.assertEqual(cards[1]["detail"], "no ceiling set")
        self.assertEqual(cards[2]["value"], "-")
        self.assertEqual(cards[2]["detail"], "no threshold set")


class TestMedicalCardFigures(unittest.TestCase):
    def test_active(self):
        prof = {"magi_ceiling_annual": 25000.0,
                "plugins": {"medical": {"w2": "10000", "pension": "7200",
                                        "interest": "50", "dividends": "4000",
                                        "gains": "3000", "enabled": True,
                                        "applied": True}}}
        self.assertEqual(medical.card_figures(prof),
                         {"qualified": True, "magi": 24250.0,
                          "ceiling": 25000.0})

    def test_inactive_is_none(self):
        prof = {"plugins": {"medical": {"enabled": False, "applied": False}}}
        self.assertIsNone(medical.card_figures(prof))


class TestOverviewBulletsGone(unittest.TestCase):
    def test_no_required_on_overview(self):
        self.assertNotIn("REQUIRED", overview_region())

    def test_no_copy_summary(self):
        self.assertNotIn("Copy summary", APP)


class TestRequiredLine(unittest.TestCase):
    def test_text(self):
        self.assertEqual(P.required_line_text(0),
                         "All REQUIRED positions have cost and dates.")
        self.assertEqual(P.required_line_text(1),
                         "1 REQUIRED position still missing cost or dates "
                         "— feed them in Data Entry.")
        self.assertEqual(P.required_line_text(3),
                         "3 REQUIRED positions still missing cost or dates "
                         "— feed them in Data Entry.")

    def test_holdings_renders_it_body_style(self):
        body = holdings_region()
        self.assertIn("required_line_text", body)
        self.assertIn("size=FS_BODY", body)
        self.assertIn('fill="x"', body)


class TestCashRow(unittest.TestCase):
    def _lots(self):
        return [{"bank": "Wells", "account": "Wells Savings",
                 "account_type": "Cash", "asset": "CASH_USD",
                 "shares": 5000.0, "cost": 1.0, "acquired": "2026-01-01",
                 "sold_date": "", "sale_price_per_share": None},
                {"bank": "Schwab", "account": "Schwab IRA",
                 "account_type": "Traditional IRA", "asset": "VTI",
                 "shares": 10.0, "cost": 200.0, "acquired": "2026-01-01",
                 "sold_date": "", "sale_price_per_share": None}]

    def test_cash_aggregates(self):
        rows, total = pc.holdings_by_asset(
            self._lots(), {"VTI": 250.0}, 0.0)
        cash = [r for r in rows if r["asset"] == "CASH_USD"]
        self.assertEqual(len(cash), 1)
        self.assertTrue(cash[0]["complete"])
        self.assertEqual(cash[0]["missing"], 0.0)
        self.assertIsNone(cash[0]["gain"])
        self.assertIsNone(cash[0]["gain_pct"])
        self.assertEqual(cash[0]["value"], 5000.0)
        self.assertEqual(total, 7500.0)
        self.assertEqual([r["asset"] for r in rows],
                         ["CASH_USD", "VTI", "Home (real estate)"])

    def test_totals_label(self):
        body = holdings_region()
        self.assertIn('"TOTAL"', body)
        self.assertNotIn("cash excluded", body.lower())


class TestCopyButtonsRight(unittest.TestCase):
    def test_holdings_and_liquidity_anchor_e(self):
        self.assertEqual(APP.count('text="Copy table"'), 3)
        self.assertIn("anchor=\"e\"", APP)

    def test_table_toolbar_stays_right(self):
        self.assertIn('sticky="e"', APP)
        self.assertIn('pack(side="right")', APP)


if __name__ == "__main__":
    unittest.main()
