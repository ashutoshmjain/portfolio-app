"""Prompt 14 committed checks (a)-(f): tutorial type scale, plain
subtitle label, light-mode fix. Stdlib unittest only.

Widget checks build a real App in a withdrawn root (no mainloop) and
skip when no display is available; pure and source checks run
everywhere. Needles avoid backslash escapes.
"""
import os
import sys
import tkinter as tk
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import portfolio_app as P
import portfolio_calc as pc

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def repo_source(name):
    with open(os.path.join(REPO, name), encoding="utf-8") as f:
        return f.read()


APP = repo_source("portfolio_app.py")

try:
    _probe = tk.Tk()
    _probe.withdraw()
    _probe.destroy()
    HAS_DISPLAY = True
except tk.TclError:
    HAS_DISPLAY = False


def channels(hexcolor):
    h = hexcolor.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class TestTutorialScale(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(P.TITLE_FONT_SIZE, 28)
        self.assertEqual(P.FS_BODY, 14)
        self.assertEqual(P.FS_HEAD, 18)
        self.assertEqual(P.FS_TABLE_HEAD, 12)
        self.assertEqual(P.FS_SMALL, 12)
        self.assertEqual(P.FS_TITLE, 18)
        self.assertEqual(P.VALUE_FONT_SIZE, 20)

    def test_no_numeric_sizes(self):
        import re
        self.assertEqual(re.findall(r"CTkFont[(]size=(\d+)", APP), [])


class FakeTop:
    def __init__(self, mode):
        self._mode = mode

    def _get_appearance_mode(self):
        return self._mode


class FakeWidget:
    def __init__(self, mode):
        self._top = FakeTop(mode)

    def winfo_toplevel(self):
        return self._top


class TestModeIsLight(unittest.TestCase):
    def test_lowercase_modes(self):
        self.assertTrue(P._mode_is_light(FakeWidget("light")))
        self.assertFalse(P._mode_is_light(FakeWidget("dark")))

    def test_card_bg_light_vs_dark(self):
        light = P._card_bg(True)
        dark = P._card_bg(False)
        self.assertNotEqual(light, dark)
        self.assertGreater(sum(channels(light)), sum(channels(dark)))


class TestChartDressing(unittest.TestCase):
    def test_light_and_dark(self):
        from matplotlib.figure import Figure
        for light, panel, text in (
                (False, None, None),
                (True, "#D3D3D3", "#242424")):
            fig = Figure(figsize=(10, 2.5), dpi=100)
            ax = fig.add_subplot(111)
            ax.plot([0, 1], [0, 1], label="s")
            ax.legend()
            pc.dress_chart(fig, ax, light=light, panel_bg=panel,
                           text_color=text)
            if light:
                self.assertEqual(fig.patch.get_facecolor()[:3],
                                 tuple(c / 255 for c in channels(panel)))
                self.assertEqual(ax.xaxis.label.get_color(), text)
                self.assertEqual(ax.title.get_color(), text)
            else:
                self.assertEqual(ax.xaxis.label.get_color(),
                                 pc.CHART_TEXT)
                self.assertEqual(ax.title.get_color(), pc.CHART_TEXT)

    def test_drift_chart_light(self):
        from matplotlib.figure import Figure
        fig = Figure(figsize=(10, 2.5), dpi=100)
        rows = [{"date": "2026-01-02", "actual_total": 4000000.0,
                 "standard_total": 4100000.0},
                {"date": "2026-01-05", "actual_total": 4200000.0,
                 "standard_total": 4150000.0}]
        self.assertTrue(pc.make_drift_chart(
            fig, rows, light=True, panel_bg="#D3D3D3",
            text_color="#242424"))
        self.assertEqual(fig.patch.get_facecolor()[:3],
                         tuple(c / 255 for c in channels("#D3D3D3")))


@unittest.skipUnless(HAS_DISPLAY, "no display")
class TestHeaderSubtitle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = P.App()
        cls.app.withdraw()
        cls.app.lots = [
            {"bank": "Schwab", "account": "Schwab Taxable",
             "account_type": "Taxable", "asset": "VTI",
             "shares": 10.0, "cost": 200.0, "acquired": "2026-01-01",
             "sold_date": "", "sale_price_per_share": None}]
        cls.app.prices = {"VTI": 250.0}
        cls.app.recompute()
        cls.app._ensure_cov_state()
        cls.app._cov_reset()
        cls.app.show_page("Overview")
        cls.app.update_idletasks()

    @classmethod
    def tearDownClass(cls):
        cls.app.destroy()

    def test_plain_label(self):
        import customtkinter as ctk
        sub = self.app.header_net
        self.assertIsInstance(sub, ctk.CTkLabel)
        self.assertNotIsInstance(sub, P.SelectableMsg)
        self.assertTrue(sub.cget("text").startswith("Total net worth:"))
        self.assertEqual(sub.pack_info()["side"], "left")

    def test_status_bar_follows_mode(self):
        app = self.app
        for mode, light in (("Light", True), ("Dark", False)):
            app.change_appearance_mode(mode)
            app.update_idletasks()
            want = P._to_hex(P._theme_for_mode(P.PANEL_COLOR, light))
            self.assertEqual(app.header_sub._box.cget("bg").upper(),
                             want.upper())


if __name__ == "__main__":
    unittest.main()
