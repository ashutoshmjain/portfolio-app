"""Medical plugin (base): projected "other" and projected total from the
five components, plus the enable/disable stash dance on the manual lump.

Contract under test (all headless — no GUI):
- parse_amount: blank/None means nothing expected (0.0); commas and $
  tolerated; anything else raises ValueError.
- projected_other = W-2 + pension + interest + dividends (NOT gains);
  projected_total = projected_other + gains.
- on_enabled(app, True) stashes the manual other_annual_income in plugin
  state and plugs in the projected "other"; on_enabled(app, False)
  restores the stash and drops the applied flag.

Stdlib unittest only — no new dependency.
"""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plugins import medical


def stub_app(other=0.0):
    return types.SimpleNamespace(
        profile={"other_annual_income": other, "plugins": {}})


class TestParseAmount(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(medical.parse_amount("1000"), 1000.0)

    def test_blank_means_none_expected(self):
        self.assertEqual(medical.parse_amount(""), 0.0)
        self.assertEqual(medical.parse_amount("   "), 0.0)
        self.assertEqual(medical.parse_amount(None), 0.0)

    def test_punctuation_tolerated(self):
        self.assertEqual(medical.parse_amount("1,000"), 1000.0)
        self.assertEqual(medical.parse_amount("$500"), 500.0)

    def test_garbage_raises(self):
        with self.assertRaises(ValueError):
            medical.parse_amount("abc")


class TestProjection(unittest.TestCase):
    def test_components_sum(self):
        st = {"w2": "100", "pension": "200", "interest": "10",
              "dividends": "5", "gains": "999"}
        self.assertEqual(medical.projected_other(st), 315.0)
        self.assertEqual(medical.projected_total(st), 1314.0)

    def test_blanks_are_zero(self):
        st = {"w2": "", "pension": "", "interest": "",
              "dividends": "", "gains": ""}
        self.assertEqual(medical.projected_other(st), 0.0)
        self.assertEqual(medical.projected_total(st), 0.0)

    def test_gains_excluded_from_other(self):
        st = {"w2": "", "pension": "", "interest": "",
              "dividends": "", "gains": "5000"}
        self.assertEqual(medical.projected_other(st), 0.0)
        self.assertEqual(medical.projected_total(st), 5000.0)


class TestEnableDisable(unittest.TestCase):
    def test_enable_stashes_manual_and_plugs_projection(self):
        app = stub_app(other=10000.0)
        app.profile["plugins"]["medical"] = {
            "enabled": False, "w2": "5000", "pension": "0",
            "interest": "0", "dividends": "0", "gains": "0",
            "manual_other_annual_income": None, "applied": False}
        medical.on_enabled(app, True)
        st = app.profile["plugins"]["medical"]
        self.assertEqual(st["manual_other_annual_income"], 10000.0)
        self.assertEqual(app.profile["other_annual_income"], 5000.0)
        self.assertTrue(st["applied"])

    def test_disable_restores_manual(self):
        app = stub_app(other=5000.0)
        app.profile["plugins"]["medical"] = {
            "enabled": True, "w2": "5000",
            "manual_other_annual_income": 10000.0, "applied": True}
        medical.on_enabled(app, False)
        st = app.profile["plugins"]["medical"]
        self.assertEqual(app.profile["other_annual_income"], 10000.0)
        self.assertFalse(st["applied"])
        self.assertNotIn("manual_other_annual_income", st)

    def test_round_trip_returns_original(self):
        app = stub_app(other=7500.0)
        medical.on_enabled(app, True)
        app.profile["other_annual_income"] = 123.0  # plugged projection
        medical.on_enabled(app, False)
        self.assertEqual(app.profile["other_annual_income"], 7500.0)

    def test_enable_with_blank_inputs_plugs_zero(self):
        app = stub_app(other=7500.0)
        medical.on_enabled(app, True)
        self.assertEqual(app.profile["other_annual_income"], 0.0)
        self.assertEqual(app.profile["plugins"]["medical"]
                         ["manual_other_annual_income"], 7500.0)


if __name__ == "__main__":
    unittest.main()
