"""Duplicate detection tests: exact rates, SimHash clustering, caps.

Run from meta bro root:  python backend/tests/test_duplicates.py
(stdlib only)
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from backend.provenance.duplicates import MAX_ROWS, DupError, exact_dup_rate, near_dup_rate  # noqa: E402


class TestDuplicates(unittest.TestCase):
    def test_exact_rate(self):
        out = exact_dup_rate([{"a": 1}, {"a": 1}, {"a": 2}])
        self.assertAlmostEqual(out["rate"], 1 / 3)
        self.assertEqual((out["unique"], out["total"]), (2, 3))

    def test_exact_unique_is_zero(self):
        out = exact_dup_rate([[1.0], [2.0], [3.0]])
        self.assertEqual(out["rate"], 0.0)

    def test_near_quantized_match(self):
        out = near_dup_rate([[0.001], [0.002]], resolution=0.01, hamming=3)
        self.assertEqual(out["clusters"], 1)
        self.assertEqual(out["rate"], 0.5)

    def test_near_far_apart_distinct(self):
        rows = [[float(i * 100)] for i in range(6)]
        out = near_dup_rate(rows, resolution=0.01, hamming=3)
        self.assertEqual(out["clusters"], 6)
        self.assertEqual(out["rate"], 0.0)

    def test_deterministic(self):
        rows = [[0.0], [0.001], [5.0]]
        self.assertEqual(near_dup_rate(rows), near_dup_rate(rows))

    def test_cap_refuses(self):
        with self.assertRaises(DupError):
            near_dup_rate([[0.0]] * (MAX_ROWS + 1))

    def test_empty_raises(self):
        with self.assertRaises(DupError):
            exact_dup_rate([])

    def test_bad_resolution_rejected(self):
        rows = [[0.0], [1.0]]
        for bad in (True, float("inf"), float("nan"), 0.0, -0.1, "fine"):
            with self.assertRaises(DupError, msg=repr(bad)):
                near_dup_rate(rows, resolution=bad)


if __name__ == "__main__":
    unittest.main(verbosity=2)
