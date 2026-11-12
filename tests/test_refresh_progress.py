"""Progress plumbing for Refresh: _bounded_map reports per-item completion
via on_done (the top-bar progress bar rides on this). No network — the
worker function is local. Stdlib unittest only, no new dependency.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import portfolio_calc as pc


class TestBoundedMapProgress(unittest.TestCase):
    def test_on_done_once_per_item(self):
        seen = []
        out = pc._bounded_map(lambda t: (t, 1), ["A", "B", "C", "D"],
                              on_done=seen.append)
        self.assertEqual(sorted(seen), ["A", "B", "C", "D"])
        self.assertEqual(sorted(out), ["A", "B", "C", "D"])

    def test_on_done_covers_errors(self):
        def flaky(t):
            if t == "bad":
                raise RuntimeError("boom")
            return (t, 1)

        seen = []
        pc._bounded_map(flaky, ["ok", "bad"], on_done=seen.append)
        self.assertEqual(sorted(seen), ["bad", "ok"])

    def test_no_callback_still_works(self):
        out = pc._bounded_map(lambda t: (t, 1), ["A", "B"])
        self.assertEqual(sorted(out), ["A", "B"])


if __name__ == "__main__":
    unittest.main()
