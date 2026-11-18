"""Plugin loader: discovery finds interface-conformant modules and skips
the rest without breaking startup.

Contract under test: portfolio_calc.discover_plugins(package, path)
returns ({plugin_id: module}, [notes]). A module that raises on import,
or lacks the interface, is skipped with a note. Files named __init__.py
or starting with _ are never scanned.

Stdlib unittest only — no new dependency.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import portfolio_calc as pc


GOOD_SRC = '''PLUGIN_ID = "good"
PLUGIN_TITLE = "Good"
PLUGIN_DESC = "A well-behaved fixture plugin."
def build(app, parent):
    pass
'''

BROKEN_SRC = 'raise RuntimeError("boom on import")\n'

NOIFACE_SRC = '''PLUGIN_ID = "noiface"
PLUGIN_TITLE = "No interface"
'''


class TestDiscoverPlugins(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pkg = os.path.join(self.tmp.name, "fakepkg")
        os.mkdir(self.pkg)
        files = {"__init__.py": "",
                 "good.py": GOOD_SRC,
                 "broken.py": BROKEN_SRC,
                 "noiface.py": NOIFACE_SRC,
                 "_hidden.py": GOOD_SRC}
        for name, src in files.items():
            with open(os.path.join(self.pkg, name), "w") as fh:
                fh.write(src)
        sys.path.insert(0, self.tmp.name)

    def tearDown(self):
        sys.path.remove(self.tmp.name)
        for key in [k for k in sys.modules if k == "fakepkg"
                    or k.startswith("fakepkg.")]:
            del sys.modules[key]
        self.tmp.cleanup()

    def test_discovers_good_plugin(self):
        mods, _notes = pc.discover_plugins(package="fakepkg",
                                            path=self.pkg)
        self.assertEqual(set(mods), {"good"})
        self.assertEqual(mods["good"].PLUGIN_TITLE, "Good")

    def test_broken_and_bad_modules_skipped_with_notes(self):
        mods, notes = pc.discover_plugins(package="fakepkg",
                                          path=self.pkg)
        self.assertNotIn("broken", mods)
        self.assertNotIn("noiface", mods)
        text = "\n".join(notes)
        self.assertIn("broken", text)
        self.assertIn("noiface", text)

    def test_underscore_files_ignored(self):
        mods, notes = pc.discover_plugins(package="fakepkg",
                                          path=self.pkg)
        self.assertNotIn("_hidden", mods)
        self.assertFalse(any("_hidden" in n for n in notes))

    def test_missing_directory_never_raises(self):
        mods, notes = pc.discover_plugins(
            package="fakepkg", path=os.path.join(self.tmp.name, "nope"))
        self.assertEqual(mods, {})
        self.assertTrue(notes)

    def test_real_package_exposes_interface(self):
        mods, notes = pc.discover_plugins()
        self.assertIn("medical", mods)
        med = mods["medical"]
        for attr in ("PLUGIN_ID", "PLUGIN_TITLE", "PLUGIN_DESC",
                     "build", "DEFAULT_STATE", "on_enabled"):
            self.assertTrue(hasattr(med, attr), attr)
        self.assertTrue(callable(med.build))
        self.assertTrue(callable(med.on_enabled))

    def test_display_title_is_medical(self):
        # PLUGIN_ID stays "medical" (state key); the user-visible title
        # is "Medi-Cal".
        mods, _notes = pc.discover_plugins()
        self.assertEqual(mods["medical"].PLUGIN_ID, "medical")
        self.assertEqual(mods["medical"].PLUGIN_TITLE, "Medi-Cal")


if __name__ == "__main__":
    unittest.main()
