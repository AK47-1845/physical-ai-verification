"""FR-43 retention tests: policy windows + purge boundaries.

Run from meta bro root:  python tests/test_retention.py
(stdlib only)
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.retention import DEFAULT_MONTHS, RetentionError, due_for_purge, retention_policy  # noqa: E402


class TestRetention(unittest.TestCase):
    def test_default_is_twelve_months(self):
        self.assertEqual(DEFAULT_MONTHS, 12)
        policy = retention_policy()
        self.assertEqual((policy["months"], policy["days"],
                          policy["default_applied"]), (12, 360, True))

    def test_custom_window(self):
        policy = retention_policy(months=24)
        self.assertEqual((policy["months"], policy["days"],
                          policy["default_applied"]), (24, 720, False))

    def test_boundary_day_keeps_log(self):
        base = 1_000_000
        kept = due_for_purge(decided_ts=base, now_ts=base + 360 * 86400)
        self.assertFalse(kept["due"])
        self.assertAlmostEqual(kept["age_days"], 360.0)
        purged = due_for_purge(decided_ts=base,
                               now_ts=base + 360 * 86400 + 1)
        self.assertTrue(purged["due"])

    def test_fresh_and_stale(self):
        base = 2_000_000
        fresh = due_for_purge(decided_ts=base, now_ts=base + 100,
                              months=12)
        self.assertFalse(fresh["due"])
        stale = due_for_purge(decided_ts=base,
                              now_ts=base + 400 * 86400, months=12)
        self.assertTrue(stale["due"])

    def test_bad_inputs_raise(self):
        with self.assertRaises(RetentionError):
            retention_policy(months=0)
        with self.assertRaises(RetentionError):
            retention_policy(months=121)
        with self.assertRaises(RetentionError):
            retention_policy(months=True)
        with self.assertRaises(RetentionError):
            due_for_purge(decided_ts=2_000_000, now_ts=1_000_000)
        with self.assertRaises(RetentionError):
            due_for_purge(decided_ts=-5, now_ts=10)

    def test_deterministic(self):
        kw = {"decided_ts": 1_000, "now_ts": 2_000, "months": 6}
        self.assertEqual(due_for_purge(**kw), due_for_purge(**kw))


if __name__ == "__main__":
    unittest.main(verbosity=2)
