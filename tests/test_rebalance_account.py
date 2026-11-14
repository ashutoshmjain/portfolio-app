"""Rebalance-plan account label: the single account that can supply every
planned sell — never a hardcoded owner account name.

Contract under test: portfolio_calc.rebalance_account(positions, sells,
acct_types) returns (label, is_ira) where the label is the single account
whose qty for every ticker in sells covers the planned sell quantity.
Anything else — zero or several candidates, empty sells, a None quantity
— stays ("--", False). is_ira reflects the named account's type.

Stdlib unittest only — no new dependency.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portfolio_calc import rebalance_account


def pos(account, ticker, qty=1.0):
    return {"account": account, "ticker": ticker, "qty": qty,
            "bucket": "Equities"}


SELLS = {"META": 416.0, "VTI": 760.0, "GLD": 324.0}
TYPES = {"Ira": "Traditional IRA", "Tax": "Taxable", "Ira2": "Roth IRA"}


class TestRebalanceAccount(unittest.TestCase):
    def test_empty_positions_labels_nothing(self):
        self.assertEqual(rebalance_account([], SELLS, TYPES),
                         ("--", False))

    def test_empty_sells_labels_nothing(self):
        positions = [pos("Ira", "META", 500.0)]
        self.assertEqual(rebalance_account(positions, {}, TYPES),
                         ("--", False))

    def test_none_quantity_labels_nothing(self):
        positions = [pos("Ira", "META", 500.0)]
        self.assertEqual(
            rebalance_account(positions, {"META": None}, TYPES),
            ("--", False))

    def test_one_ira_supplies_all_names_it(self):
        # Mirror of the real shape: META only in the IRA, VTI/GLD spread
        # across accounts, the IRA quantities above every sell quantity.
        positions = [pos("Ira", "META", 500.0),
                     pos("Ira", "VTI", 1296.0),
                     pos("Ira", "GLD", 1000.0),
                     pos("Tax", "VTI", 350.0),
                     pos("Tax", "GLD", 209.0)]
        self.assertEqual(rebalance_account(positions, SELLS, TYPES),
                         ("Ira", True))

    def test_short_on_one_leg_stays_generic(self):
        # The IRA holds all three tickers but not enough VTI.
        positions = [pos("Ira", "META", 500.0),
                     pos("Ira", "VTI", 100.0),
                     pos("Ira", "GLD", 1000.0),
                     pos("Tax", "VTI", 350.0),
                     pos("Tax", "GLD", 209.0)]
        self.assertEqual(rebalance_account(positions, SELLS, TYPES),
                         ("--", False))

    def test_no_single_supplier_stays_generic(self):
        # META and VTI live in different IRAs; neither covers all sells.
        positions = [pos("Ira", "META", 500.0),
                     pos("Ira2", "VTI", 1296.0),
                     pos("Ira2", "GLD", 1000.0)]
        self.assertEqual(
            rebalance_account(positions, SELLS,
                              {"Ira": "Traditional IRA",
                               "Ira2": "Roth IRA"}),
            ("--", False))

    def test_single_taxable_supplier_named_not_ira(self):
        positions = [pos("Tax", "META", 500.0),
                     pos("Tax", "VTI", 1296.0),
                     pos("Tax", "GLD", 1000.0)]
        self.assertEqual(rebalance_account(positions, SELLS, TYPES),
                         ("Tax", False))

    def test_two_suppliers_stay_generic(self):
        positions = [pos("Ira", "META", 500.0),
                     pos("Ira", "VTI", 1296.0),
                     pos("Ira", "GLD", 1000.0),
                     pos("Ira2", "META", 500.0),
                     pos("Ira2", "VTI", 1296.0),
                     pos("Ira2", "GLD", 1000.0)]
        self.assertEqual(
            rebalance_account(positions, SELLS,
                              {"Ira": "Traditional IRA",
                               "Ira2": "Roth IRA"}),
            ("--", False))

    def test_unrelated_assets_stay_generic(self):
        self.assertEqual(rebalance_account([pos("Ira", "BTC", 2.0)],
                                           SELLS, TYPES),
                         ("--", False))


if __name__ == "__main__":
    unittest.main()
