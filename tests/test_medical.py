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


USER_EXAMPLE = {"w2": "10000", "pension": "7200", "interest": "50",
                "dividends": "4000", "gains": "30000"}


class TestVerdict(unittest.TestCase):
    def test_user_example_does_not_qualify(self):
        total = medical.projected_total(USER_EXAMPLE)
        self.assertEqual(total, 51250.0)
        self.assertEqual(
            medical.verdict_text(total, 25000.0),
            "You do not qualify for Medi-Cal. Check with your tax "
            "professional.")

    def test_small_projection_qualifies(self):
        st = dict(USER_EXAMPLE, w2="0", pension="0", interest="0",
                  dividends="0", gains="0")
        self.assertEqual(
            medical.verdict_text(medical.projected_total(st), 25000.0),
            "You appear to qualify for Medi-Cal.")

    def test_no_ceiling_needs_setting(self):
        self.assertEqual(
            medical.verdict_text(0.0, None),
            "Set a MAGI ceiling in Settings to see the verdict.")

    def test_qualifies_boundary(self):
        self.assertTrue(medical.qualifies(25000.0, 25000.0))
        self.assertFalse(medical.qualifies(25000.01, 25000.0))
        self.assertIsNone(medical.qualifies(0.0, None))


class TestTotalsText(unittest.TestCase):
    def test_user_example_figures(self):
        text = medical.totals_text(USER_EXAMPLE)
        self.assertIn("$21,250", text)
        self.assertIn("$51,250", text)

    def test_updated_state_changes_totals(self):
        st = dict(USER_EXAMPLE)
        before = medical.totals_text(st)
        st["w2"] = "20000"
        after = medical.totals_text(st)
        self.assertNotEqual(before, after)
        self.assertIn("$31,250", after)
        self.assertIn("$61,250", after)

    def test_bad_values_raise(self):
        with self.assertRaises(ValueError):
            medical.totals_text({"w2": "abc"})


class FakeLabel:
    def __init__(self):
        self.text = None
        self.alive = True

    def winfo_exists(self):
        return self.alive

    def configure(self, text=""):
        self.text = text


def stub_app_with_ui(state):
    app = stub_app(other=21250.0)
    app.profile["plugins"]["medical"] = dict(state)
    app._medical_ui = {"totals": FakeLabel(), "verdict": FakeLabel()}
    return app


class TestReadoutRefresh(unittest.TestCase):
    def test_on_data_changed_refreshes_totals_and_verdict(self):
        app = stub_app_with_ui(dict(USER_EXAMPLE, enabled=True,
                                    applied=True))
        app.profile["magi_ceiling_annual"] = 25000.0
        medical.on_data_changed(app)
        ui = app._medical_ui
        self.assertIn("$21,250", ui["totals"].text)
        self.assertIn("$51,250", ui["totals"].text)
        self.assertIn("You do not qualify", ui["verdict"].text)

    def test_on_data_changed_no_ui_is_noop(self):
        app = stub_app(other=0.0)
        app.profile["plugins"]["medical"] = dict(USER_EXAMPLE,
                                                 enabled=True,
                                                 applied=True)
        medical.on_data_changed(app)  # must not raise

    def test_on_data_changed_dead_widgets_skipped(self):
        app = stub_app_with_ui(dict(USER_EXAMPLE, enabled=True,
                                    applied=True))
        for w in app._medical_ui.values():
            w.alive = False
        medical.on_data_changed(app)  # must not raise


class TestOverviewVerdictLine(unittest.TestCase):
    def base_profile(self, med_state):
        return {"magi_ceiling_annual": 25000.0,
                "plugins": {"medical": med_state}}

    def test_absent_when_disabled(self):
        prof = self.base_profile({"enabled": False, "applied": False})
        self.assertIsNone(medical.overview_verdict_line(prof))

    def test_absent_when_not_applied(self):
        prof = self.base_profile(dict(USER_EXAMPLE, enabled=True,
                                      applied=False))
        self.assertIsNone(medical.overview_verdict_line(prof))

    def test_absent_with_no_state(self):
        self.assertIsNone(medical.overview_verdict_line({}))

    def test_not_qualified_line(self):
        prof = self.base_profile(dict(USER_EXAMPLE, enabled=True,
                                      applied=True))
        self.assertEqual(
            medical.overview_verdict_line(prof),
            "Medi-Cal: not qualified for Medi-Cal (projected MAGI "
            "$51,250 vs $25,000 ceiling) — check with your tax "
            "professional.")

    def test_qualified_line(self):
        st = dict(USER_EXAMPLE, w2="0", pension="0", interest="0",
                  dividends="0", gains="0", enabled=True, applied=True)
        prof = self.base_profile(st)
        self.assertEqual(
            medical.overview_verdict_line(prof),
            # Zero MAGI renders "-" per the house zero style.
            "Medi-Cal: qualified for Medi-Cal (projected MAGI - vs "
            "$25,000 ceiling).")

    def test_no_ceiling_line(self):
        st = dict(USER_EXAMPLE, enabled=True, applied=True)
        prof = {"magi_ceiling_annual": None,
                "plugins": {"medical": st}}
        self.assertIn("set a MAGI ceiling",
                      medical.overview_verdict_line(prof))

    def test_corrupt_state_line(self):
        st = dict(USER_EXAMPLE, w2="abc", enabled=True, applied=True)
        prof = self.base_profile(st)
        self.assertIn("not numeric",
                      medical.overview_verdict_line(prof))


if __name__ == "__main__":
    unittest.main()
