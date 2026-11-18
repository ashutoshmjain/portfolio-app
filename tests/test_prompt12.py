"""Prompt 12 committed checks (a)-(n): sidebar shell, Retirement
Portfolio name, ten nav entries, appearance/scaling/Settings bottom,
transparent main view + header, Overview refresh button, Tax merge,
always-present Utilities page, auto-log on refresh, no home-estimates
action, left-aligned table titles, tutorial title/value fonts,
theme-aware colors. Stdlib unittest only, no new dependency.

Widget checks build a real App in a withdrawn root (no mainloop, no
window shown) and skip when no display is available; pure and source
checks run everywhere. Needles avoid backslash escapes.
"""
import datetime
import os
import sys
import tempfile
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


def need_display(test):
    return unittest.skipUnless(HAS_DISPLAY, "no display")(test)


NAV_TEN = ["Overview", "Accounts", "Holdings", "Liquidity", "Tax",
           "Diversification", "Inputs", "Template", "Danger Zone",
           "Utilities"]


class TestNavPages(unittest.TestCase):
    def test_ten_names_in_order(self):
        self.assertEqual(P.NAV_PAGES, NAV_TEN)

    def test_title_value_sizes(self):
        # Superseded by Prompt 14 item 1: title is the tutorial
        # heading 28; value size stays 20.
        self.assertEqual(P.TITLE_FONT_SIZE, 28)
        self.assertEqual(P.VALUE_FONT_SIZE, 20)

    def test_body_scale_prompt14(self):
        # Superseded by Prompt 14 item 1: the tutorial scale is
        # (14, 18, 12, 12).
        self.assertEqual((P.FS_BODY, P.FS_HEAD, P.FS_TABLE_HEAD,
                          P.FS_SMALL), (14, 18, 12, 12))

    def test_secondary_theme_aware(self):
        self.assertEqual(P.CLR_SECONDARY, ("gray40", "gray60"))

    def test_no_hardcoded_dark_pair(self):
        for lit in ("#EDEDED", "#2B2B2B", "#C9C9C9"):
            self.assertNotIn(lit, APP)


class TestShellGone(unittest.TestCase):
    def test_no_tab_shell(self):
        self.assertNotIn("self.tabs = ctk.CTkTabview", APP)
        self.assertNotIn("self.dash_tabs = ctk.CTkTabview", APP)
        self.assertNotIn("self.data_tabs = ctk.CTkTabview", APP)
        self.assertNotIn("def toggle_menu", APP)
        self.assertNotIn("self.menu_win", APP)

    def test_no_home_estimates_action(self):
        self.assertNotIn("Refresh home estimates", APP)
        self.assertNotIn("def home_from_menu", APP)
        self.assertNotIn("def log_close", APP)

    def test_settings_has_no_utilities(self):
        self.assertNotIn("plugin_vars", APP)

    def test_no_portfolio_dashboard(self):
        self.assertNotIn("PORTFOLIO DASHBOARD", APP)
        self.assertNotIn('text="Portfolio"', APP)


class TestTableTitlesLeft(unittest.TestCase):
    def test_table_class_left(self):
        self.assertIn('anchor="w"', APP)
        self.assertIn('sticky="w"', APP)

    def test_inputs_header_left(self):
        i = APP.find("Column budget:")
        blk = APP[i:i + 600]
        self.assertIn('sticky="w"', blk)


class TestAutoLogPure(unittest.TestCase):
    def test_upsert_by_date(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "drift.csv")
            m1 = pc.append_close(p, 100.0, 50.0, 150.0, 140.0)
            m2 = pc.append_close(p, 101.0, 50.0, 151.0, 141.0)
            if "weekend" in m1:
                self.assertIn("weekend", m2)
                self.assertFalse(os.path.exists(p))
                return
            rows = pc.load_drift_log(p)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["liquid"], 101)


@unittest.skipUnless(HAS_DISPLAY, "no display")
class TestShellWidgets(unittest.TestCase):
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
        # Re-init coverage from the injected lots (the same reset the
        # external-commit path runs — never raw-index stale cov state).
        cls.app._ensure_cov_state()
        cls.app._cov_reset()
        cls.app.update_idletasks()

    @classmethod
    def tearDownClass(cls):
        cls.app.destroy()

    def widgets(self):
        out = []

        def walk(w):
            out.append(w)
            for c in w.winfo_children():
                walk(c)
        walk(self.app)
        return out

    def nav_buttons(self):
        return [w for w in self.widgets()
                if "ctk_button" in str(type(w)).lower()
                and w.cget("text") in NAV_TEN]

    def test_root_grid_and_sidebar(self):
        app = self.app
        self.assertEqual(app.grid_columnconfigure(1)["weight"], 1)
        self.assertEqual(app.grid_rowconfigure(0)["weight"], 1)
        sb = app.sidebar
        self.assertEqual(sb.grid_info()["column"], 0)
        # Tk canonicalizes the sticky order (nsew -> nesw).
        self.assertEqual(sb.grid_info()["sticky"], "nesw")
        # Superseded by Prompt 13 item 5: the sidebar narrows 200->170.
        self.assertEqual(sb.cget("width"), 170)
        self.assertEqual(sb.cget("corner_radius"), 0)

    def test_names(self):
        self.assertEqual(self.app.title(), "Retirement Portfolio")
        titles = [w for w in self.widgets()
                  if "ctk_label" in str(type(w)).lower()
                  and w.cget("text") == "Retirement Portfolio"]
        self.assertTrue(titles)

    def test_nav_ten_in_order(self):
        btns = self.nav_buttons()
        self.assertEqual(len(btns), 10)
        # Nav buttons pack (fill=x) inside the scrollable frame: order
        # is pack order among the children.
        kids = self.app.nav_scroll.winfo_children()
        order = [w.cget("text") for w in kids
                 if "ctk_button" in str(type(w)).lower()]
        self.assertEqual(order, NAV_TEN)

    def test_nav_style_and_selection(self):
        btns = {b.cget("text"): b for b in self.nav_buttons()}
        sample = btns["Holdings"]
        self.assertEqual(sample.cget("anchor"), "w")
        self.assertEqual(sample.cget("height"), 32)
        self.assertEqual(sample.cget("fg_color"), "transparent")
        self.app.show_page("Holdings")
        self.app.update_idletasks()
        btns = {b.cget("text"): b for b in self.nav_buttons()}
        self.assertNotEqual(btns["Holdings"].cget("fg_color"),
                            "transparent")
        for name, b in btns.items():
            if name != "Holdings":
                self.assertEqual(b.cget("fg_color"), "transparent")
        self.app.show_page("Overview")

    def test_bottom_menus(self):
        app = self.app
        self.assertEqual(list(app.appearance_menu.cget("values")),
                         ["System", "Light", "Dark"])
        self.assertEqual(app.appearance_menu.get(), "Dark")
        self.assertEqual(list(app.scaling_menu.cget("values")),
                         ["80%", "90%", "100%", "110%", "120%"])
        self.assertEqual(app.scaling_menu.get(), "100%")
        settings = [w for w in app.sidebar.winfo_children()
                    if "ctk_button" in str(type(w)).lower()
                    and w.cget("text") == "Settings"]
        self.assertEqual(len(settings), 1)

    def test_main_transparent_and_header(self):
        from tkinter import font as tkfont
        app = self.app
        app.show_page("Diversification")
        app.update_idletasks()
        self.assertEqual(app.main.cget("fg_color"), "transparent")
        # Symmetric padx/pady come back as a single int from grid_info.
        self.assertEqual(app.main.grid_info()["padx"], 20)
        self.assertEqual(app.main.grid_info()["pady"], 20)
        self.assertEqual(app.header_title.cget("text"), "Diversification")
        # CTk renders the requested size as pixels (Tk reports points),
        # so assert the requested size on the font object itself.
        # Superseded by Prompt 14 item 1: header title is 28.
        self.assertEqual(app.header_title.cget("font").cget("size"), 28)
        self.assertIs(app.header_title.cget("font"), app.title_font)
        self.assertIn("As of", app.header_sub.cget("text")
                      if hasattr(app.header_sub, "cget") else "")

    def test_refresh_not_in_headers(self):
        # Superseded by Prompt 13 item 2: Refresh stocks moved to the
        # sidebar so every page can reach it — no page header carries
        # the button anymore (the sidebar test lives in test_prompt13).
        app = self.app
        for name in NAV_TEN:
            app.show_page(name)
            app.update_idletasks()
            acts = [w for w in app.header_actions.winfo_children()
                    if "ctk_button" in str(type(w)).lower()
                    and w.cget("text") == "Refresh stocks"]
            self.assertEqual(acts, [], name)

    def test_all_pages_render(self):
        from tkinter import TclError
        app = self.app
        for name in NAV_TEN:
            app.show_page(name)
            app.update_idletasks()
            self.assertTrue(app.page.winfo_children(), name)

    def test_tax_merge(self):
        from tkinter import font as tkfont
        app = self.app
        app.show_page("Tax")
        app.update_idletasks()
        tables = [w for w in self.widgets()
                  if isinstance(w, P.Table) and w.winfo_ismapped()]
        headers = [t.headers for t in tables]
        self.assertIn(["Account type", "Tax / withdrawal treatment"],
                      headers)
        self.assertTrue(any(h[:2] == ["Asset", "Account"] for h in headers))
        tlh = [w for w in self.widgets()
               if w.__class__ is tk.Text and
               "Tax Loss Harvesting" in w.get("1.0", "end-1c")]
        self.assertTrue(tlh)

    def test_utilities_always_present(self):
        app = self.app
        for pid in app.plugins:
            app.profile.setdefault("plugins", {})[pid] = \
                dict(app.profile.get("plugins", {}).get(pid, {}),
                     enabled=False)
        app.show_page("Utilities")
        app.update_idletasks()
        names = [b.cget("text") for b in self.nav_buttons()]
        self.assertIn("Utilities", names)
        tabs = app.util_tabs
        self.assertIsNotNone(tabs)
        tab0 = tabs.tab("Plugins")
        self.assertTrue(tab0.winfo_children())

    def test_value_cards_contrast(self):
        app = self.app
        app.show_page("Overview")
        app.update_idletasks()
        wrap = None
        for w in self.widgets():
            if not isinstance(w, tk.Frame):
                continue
            boxes = [c for c in w.winfo_children()
                     if isinstance(c, tk.Frame)]
            if boxes and all(
                    len([g for g in b.winfo_children()
                         if "ctk_label" in str(type(g)).lower()]) == 3
                    for b in boxes):
                wrap = w
                break
        self.assertIsNotNone(wrap)
        card = [c for c in wrap.winfo_children()
                if isinstance(c, tk.Frame)][0]
        self.assertNotEqual(card.cget("fg_color"),
                            app.main.cget("fg_color"))

    def test_auto_log(self):
        import portfolio_app as PA
        app = self.app
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "drift.csv")
            old = PA.DRIFT_LOG
            PA.DRIFT_LOG = p
            try:
                app.data["drift"]["standard_total"] = None
                app.auto_log_close()
                self.assertFalse(os.path.exists(p))
                self.assertIn("Cannot log close",
                              app.status_var.get())
                app.data["drift"]["standard_total"] = 140.0
                app.data["liquid"] = 100.0
                app.home_value = 50.0
                app.data["drift"]["today_total"] = 150.0
                app.auto_log_close()
                if "weekend" in app.status_var.get():
                    self.assertFalse(os.path.exists(p))
                else:
                    self.assertEqual(len(pc.load_drift_log(p)), 1)
            finally:
                PA.DRIFT_LOG = old

    def test_light_mode_renders(self):
        from tkinter import TclError
        app = self.app
        try:
            app.change_appearance_mode("Light")
            app.show_page("Overview")
            app.update_idletasks()
            app.show_page("Inputs")
            app.update_idletasks()
        finally:
            app.change_appearance_mode("Dark")
            app.show_page("Overview")
            app.update_idletasks()


if __name__ == "__main__":
    unittest.main()
