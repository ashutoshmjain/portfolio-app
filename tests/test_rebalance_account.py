"""Focused regression test: the display-only rebalance plan must never carry
a hardcoded owner account name. Account labels come from the lots via
portfolio_calc.rebalance_account; an empty app labels nothing.

Stdlib unittest only — no new dependency.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portfolio_calc import rebalance_account


def pos(account, ticker):
    return {"account": account, "ticker": ticker, "qty": 1.0,
            "bucket": "Equities"}


class TestRebalanceAccount(unittest.TestCase):
    def test_empty_positions_labels_nothing(self):
        self.assertEqual(rebalance_account([], {}), ("--", False))

    def test_single_ira_names_it(self):
        positions = [pos("Test IRA-1", "META"), pos("Test IRA-1", "VTI"),
                     pos("Test IRA-1", "GLD")]
        self.assertEqual(
            rebalance_account(positions, {"Test IRA-1": "Roth IRA"}),
            ("Test IRA-1", True))

    def test_single_taxable_is_not_ira(self):
        positions = [pos("Test Taxable", "META"),
                     pos("Test Taxable", "VTI"),
                     pos("Test Taxable", "GLD")]
        self.assertEqual(
            rebalance_account(positions, {"Test Taxable": "Taxable"}),
            ("Test Taxable", False))

    def test_split_accounts_stay_generic(self):
        positions = [pos("Test IRA-1", "META"), pos("Test Taxable", "VTI")]
        self.assertEqual(
            rebalance_account(positions, {"Test IRA-1": "Roth IRA",
                                          "Test Taxable": "Taxable"}),
            ("--", False))

    def test_unrelated_assets_stay_generic(self):
        self.assertEqual(rebalance_account([pos("Test IRA-1", "BTC")],
                                           {"Test IRA-1": "Roth IRA"}),
                         ("--", False))


if __name__ == "__main__":
    unittest.main()
