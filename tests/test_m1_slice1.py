"""M1 slice 1 tests: canonical hashing, Frechet core, verdict precedence.

Run from meta bro root:  python tests/test_m1_slice1.py
(runs under unittest and pytest alike; stdlib only)
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine import canonical_hash, pin_artifact  # noqa: E402
from engine.frechet import FrechetError, discrete_frechet  # noqa: E402
from engine.verdict import band_for, decide, verdict_badge  # noqa: E402


class TestCanonical(unittest.TestCase):
    def test_key_order_irrelevant(self):
        a = {"x": 1, "y": [2, 3]}
        b = {"y": [2, 3], "x": 1}
        self.assertEqual(canonical_hash(a), canonical_hash(b))

    def test_hash_shape_and_avalanche(self):
        import re
        h = canonical_hash({"b": 2, "a": 1})
        self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", h) is not None)
        self.assertNotEqual(h, canonical_hash({"b": 2, "a": 2}))
        # NOTE: no hardcoded golden: cross-run stability is verified by running
        # this file twice and diffing canonical_hash outputs (see demo log).

    def test_rejects_nonfinite(self):
        with self.assertRaises(ValueError):
            canonical_hash({"v": float("nan")})
        with self.assertRaises(ValueError):
            canonical_hash({"v": [1.0, float("inf")]})

    def test_pin_artifact(self):
        env = pin_artifact({"m": 0.5}, profile_version="draft-0")
        self.assertEqual(env["inputs_hash"], canonical_hash({"m": 0.5}))
        self.assertEqual(env["code_version"], "0.1.0")
        self.assertNotIn("created", env)


class TestFrechet(unittest.TestCase):
    def test_identical_is_zero(self):
        p = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
        self.assertEqual(discrete_frechet(p, p), 0.0)

    def test_hand_computed(self):
        # corridor width 1.0: Frechet must equal 1.0 exactly here
        p = [(0.0, 0.0), (2.0, 0.0)]
        q = [(0.0, 1.0), (2.0, 1.0)]
        self.assertEqual(discrete_frechet(p, q), 1.0)

    def test_dim_mismatch_raises(self):
        with self.assertRaises(FrechetError):
            discrete_frechet([(0.0, 0.0)], [(0.0, 0.0, 0.0)])

    def test_empty_raises(self):
        with self.assertRaises(FrechetError):
            discrete_frechet([], [(0.0, 0.0)])

    def test_nonfinite_raises(self):
        with self.assertRaises(FrechetError):
            discrete_frechet([(0.0, float("nan"))], [(0.0, 0.0)])

    def test_bool_coords_rejected(self):
        with self.assertRaises(FrechetError):
            discrete_frechet([(True, 0.0)], [(0.0, 0.0)])

    def test_cells_cap_refuses_loudly(self):
        big = [(0.0, 0.0)] * 2000
        wide = [(0.0, 0.0)] * 501  # 2000x501 = 1,002,000 > MAX_CELLS
        with self.assertRaises(FrechetError) as ctx:
            discrete_frechet(big, wide)
        self.assertIn("stride", str(ctx.exception))

    def test_at_capacity_passes(self):
        side = [(float(i), 0.0) for i in range(1000)]  # 1M cells == MAX
        self.assertEqual(discrete_frechet(side, side), 0.0)


class TestVerdict(unittest.TestCase):
    def test_all_pass_trusted(self):
        label, band, _ = decide([("g1", "PASS"), ("g2", "PASS")])
        self.assertEqual((label, band), ("TRUSTED", "green"))

    def test_review_wins_over_pass(self):
        label, _, reasons = decide([("g1", "PASS"), ("g2", "REVIEW")])
        self.assertEqual(label, "REVIEW")
        self.assertIn("g2=REVIEW", reasons)

    def test_insufficient_is_review(self):
        label, band, _ = decide([("g1", "INSUFFICIENT")])
        self.assertEqual((label, band), ("REVIEW", "amber"))

    def test_blocked_beats_everything(self):
        label, band, _ = decide(
            [("g1", "PASS"), ("g2", "REVIEW"), ("g3", "BLOCKED")])
        self.assertEqual((label, band), ("BLOCKED", "red"))

    def test_empty_is_review(self):
        label, _, _ = decide([])
        self.assertEqual(label, "REVIEW")

    def test_bands(self):
        self.assertEqual(band_for(0.1, 0.15, 0.5), "green")
        self.assertEqual(band_for(0.2, 0.15, 0.5), "amber")
        self.assertEqual(band_for(0.9, 0.15, 0.5), "red")


class TestBadge(unittest.TestCase):
    def test_colors(self):
        self.assertEqual(verdict_badge("TRUSTED")["color"], "green")
        self.assertEqual(verdict_badge("REVIEW")["color"], "yellow")
        self.assertEqual(verdict_badge("BLOCKED")["color"], "red")

    def test_version_pinned(self):
        self.assertEqual(verdict_badge("REVIEW")["badge_version"], "1")

    def test_gate_statuses_rejected(self):
        for bad in ("PASS", "INSUFFICIENT", "TRUST", ""):
            with self.assertRaises(ValueError, msg=bad):
                verdict_badge(bad)


if __name__ == "__main__":
    unittest.main(verbosity=2)
