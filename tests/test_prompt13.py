"""Prompt 13 committed checks (a)-(k): landing-page aesthetics.
Status bar full-width; Refresh in sidebar; type scale -2; no sidebar
subtitle; 170px sidebar; collapse control; card panel background;
chart + Watchlist share it; Total net worth in header; compact chart
with controls panel. Stdlib unittest only, no new dependency.

Widget checks build a real App in a withdrawn root (no mainloop, no
window shown) and skip when no display is available; pure and source
checks run everywhere. Needles avoid backslash escapes.
"""
import os
import sys
import tkinter as tk
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import portfolio_app as P

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


def luminance(color, light):
    import tkinter as _tk
    if isinstance(color, (tuple, list)):
        color = P._theme_for_mode(color, light)
    color = P._to_hex(color)
    root = _tk._default_root
    r, g, b = root.winfo_rgb(color)
    return 0.299 * r + 0.587 * g + 0.114 * b


class TestTypeScale13(unittest.TestCase):
    def test_constants(self):
        # Superseded by Prompt 14 item 1 (tutorial scale).
        self.assertEqual(P.FS_BODY, 14)
        self.assertEqual(P.FS_HEAD, 18)
        self.assertEqual(P.FS_TABLE_HEAD, 12)
        self.assertEqual(P.FS_SMALL, 12)
        self.assertEqual(P.FS_TITLE, 18)
        self.assertEqual(P.TITLE_FONT_SIZE, 28)
        self.assertEqual(P.VALUE_FONT_SIZE, 20)
        self.assertEqual(P.SIDEBAR_WIDTH, 170)

    def test_no_sidebar_subtitle(self):
        self.assertNotIn("All pages, one sidebar", APP)


@unittest.skipUnless(HAS_DISPLAY, "no display")
class TestLandingWidgets(unittest.TestCase):
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

    def widgets(self, root=None):
        out = []

        def walk(w):
            out.append(w)
            for c in w.winfo_children():
                walk(c)
        walk(root or self.app)
        return out

    def test_status_bar_full_width(self):
        app = self.app
        self.assertEqual(app.header_sub.pack_info()["fill"], "x")
        parent = app.header_sub.master
        self.assertIn("e", parent.grid_info()["sticky"])
        self.assertIn("w", parent.grid_info()["sticky"])

    def test_refresh_in_sidebar_above_settings(self):
        from tkinter import font as tkfont
        app = self.app
        bar = [w for w in app.sidebar.winfo_children()
               if "ctk_button" in str(type(w)).lower()
               and w.cget("text") == "Refresh stocks"]
        self.assertEqual(len(bar), 1)
        kids = app.sidebar.winfo_children()
        self.assertLess(kids.index(bar[0]),
                        kids.index(app.settings_btn))
        self.assertEqual(app.refresh_btn.master, app.sidebar)

    def test_no_refresh_in_any_header(self):
        app = self.app
        for name in P.NAV_PAGES:
            app.show_page(name)
            app.update_idletasks()
            acts = [w for w in app.header_actions.winfo_children()
                    if "button" in str(type(w)).lower()
                    and w.cget("text") == "Refresh stocks"]
            self.assertEqual(acts, [], name)
        app.show_page("Overview")
        app.update_idletasks()

    def test_sidebar_bottom_order(self):
        app = self.app
        kids = app.sidebar.winfo_children()
        seq = [kids.index(app.appearance_menu),
               kids.index(app.scaling_menu),
               kids.index(app.refresh_btn),
               kids.index(app.settings_btn)]
        self.assertEqual(seq, sorted(seq))

    def test_nav_fit_narrow_sidebar(self):
        app = self.app
        avail = P.SIDEBAR_WIDTH - 14
        for name, btn in app.nav_buttons.items():
            self.assertLessEqual(btn.winfo_reqwidth(), avail, name)

    def test_collapse_expand(self):
        app = self.app
        app.show_page("Holdings")
        app.update_idletasks()
        before = len(app.page.winfo_children())
        app.collapse_btn.invoke()
        app.update_idletasks()
        # winfo_manager, not ismapped: the test root stays withdrawn,
        # so nothing is ever "mapped" — manager presence is the signal.
        self.assertEqual(app.sidebar.winfo_manager(), "")
        info = app.main.grid_info()
        self.assertEqual((info["column"], info["columnspan"]), (0, 2))
        self.assertEqual(app.header_title.cget("text"), "Holdings")
        app.expand_btn.invoke()
        app.update_idletasks()
        self.assertEqual(app.sidebar.winfo_manager(), "grid")
        info = app.main.grid_info()
        self.assertEqual((info["column"], info["columnspan"]), (1, 1))
        self.assertEqual(app.header_title.cget("text"), "Holdings")
        self.assertEqual(len(app.page.winfo_children()), before)

    def test_cards_read_as_boxes(self):
        for mode in ("Dark", "Light"):
            light = mode == "Light"
            self.app.change_appearance_mode(mode)
            self.app.show_page("Overview")
            self.app.update_idletasks()
            boxes = self.card_boxes()
            self.assertTrue(boxes)
            win = self.app.cget("fg_color")
            for box in boxes:
                bg = box.cget("fg_color")
                self.assertNotEqual(P._to_hex(
                    P._theme_for_mode(bg, light) if isinstance(
                        bg, (tuple, list)) else bg), "transparent")
                if light:
                    self.assertLess(luminance(bg, light),
                                    luminance(win, light))
                else:
                    self.assertGreater(luminance(bg, light),
                                       luminance(win, light))
        self.app.change_appearance_mode("Dark")
        self.app.show_page("Overview")
        self.app.update_idletasks()

    def card_boxes(self):
        for w in self.widgets(self.app.page):
            if not isinstance(w, tk.Frame):
                continue
            boxes = [c for c in w.winfo_children()
                     if isinstance(c, tk.Frame)]
            if boxes and all(
                    len([g for g in b.winfo_children()
                         if "ctk_label" in str(type(g)).lower()]) == 3
                    for b in boxes):
                return boxes
        return []

    def test_one_panel_color(self):
        app = self.app
        app.show_page("Overview")
        app.update_idletasks()
        boxes = self.card_boxes()
        card_bg = P._to_hex(boxes[0].cget("fg_color"))
        panels = [w for w in self.widgets(app.page)
                  if isinstance(w, tk.Frame)
                  and P._to_hex(w.cget("fg_color")) == card_bg]
        # Four cards + chart panel + watchlist panel share one color.
        self.assertGreaterEqual(len(panels), 6)

    def test_net_worth_in_header(self):
        # SelectableMsg wraps a tk.Text box: winfo_children yields the
        # box, never the wrapper — so assert on the attribute directly.
        app = self.app
        app.show_page("Overview")
        app.update_idletasks()
        sub = app.header_net
        self.assertEqual(sub.winfo_manager(), "pack")
        self.assertEqual(sub.pack_info()["side"], "left")
        self.assertTrue(
            sub.cget("text").startswith("Total net worth:"))
        # Superseded by Prompt 14 item 2: the subtitle is a plain
        # label in FS_SMALL, not an 11px SelectableMsg.
        self.assertEqual(sub.cget("font").cget("size"), 12)
        texts = [w.get("1.0", "end-1c") for w in self.widgets(app.page)
                 if w.__class__ is tk.Text]
        self.assertFalse(any(t.startswith("Total net worth")
                             for t in texts))
        app.show_page("Accounts")
        app.update_idletasks()
        self.assertEqual(sub.winfo_manager(), "")
        app.show_page("Overview")
        app.update_idletasks()

    def test_compact_chart_with_controls(self):
        app = self.app
        app.show_page("Overview")
        app.update_idletasks()
        shows = [w for w in self.widgets(app.page)
                 if "checkbox" in str(type(w)).lower().replace("_", "")
                 and w.cget("text") == "Show standard"]
        self.assertEqual(len(shows), 1)
        self.assertTrue(bool(shows[0].get()))
        saves = [w for w in self.widgets(app.page)
                 if "button" in str(type(w)).lower()
                 and w.cget("text") == "Save chart as PNG"]
        self.assertEqual(len(saves), 1)
        row = shows[0].master
        chart_panel = saves[0].master
        self.assertIs(row, chart_panel)
        parent = row.master
        kids = [c for c in parent.winfo_children()
                if str(c) in (str(k) for k in parent.grid_slaves())]
        self.assertEqual(len(kids), 2)
        self.assertGreater(parent.grid_columnconfigure(0)["weight"],
                           parent.grid_columnconfigure(1)["weight"])


class TestChartSource(unittest.TestCase):
    def test_compact_figsize(self):
        self.assertIn("figsize=(10, 2.5)", APP)
        self.assertNotIn("figsize=(10, 4.6)", APP)


if __name__ == "__main__":
    unittest.main()
