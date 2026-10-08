"""Cross-embodiment tests: normalization, centering, joint refusal.

Run from meta bro root:  python backend/tests/test_xembodiment.py
(stdlib only)
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from backend.eval.xembodiment import XEmbodimentError, transfer_report, transfer_score  # noqa: E402

ARM = {"embodiment_id": "arm-7dof", "space": "task",
       "position_scale": 1.0, "frame_id": "world"}
HUMANOID = {"embodiment_id": "humanoid", "space": "task",
            "position_scale": 2.0, "frame_id": "world"}
JOINT = {"embodiment_id": "arm-7dof", "space": "joint",
         "position_scale": 1.0, "frame_id": "world"}

TRACE = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]


class TestTransfer(unittest.TestCase):
    def test_identical_is_zero(self):
        out = transfer_score(ARM, TRACE, ARM, TRACE)
        self.assertEqual(out["centered_frechet"], 0.0)
        self.assertEqual(out["normalized_frechet"], 0.0)

    def test_scaled_copies_match(self):
        # humanoid reports 2x units with 2x scale: same normalized shape
        doubled = [(2 * x, 2 * y) for x, y in TRACE]
        out = transfer_score(ARM, TRACE, HUMANOID, doubled)
        self.assertAlmostEqual(out["centered_frechet"], 0.0, places=9)
        self.assertAlmostEqual(out["normalized_frechet"], 0.0, places=9)

    def test_translation_invariant_centered_only(self):
        shifted = [(x + 5.0, y - 3.0) for x, y in TRACE]
        out = transfer_score(ARM, TRACE, ARM, shifted)
        self.assertAlmostEqual(out["centered_frechet"], 0.0, places=9)
        self.assertGreater(out["normalized_frechet"], 0.0)

    def test_different_lengths_ok(self):
        out = transfer_score(ARM, TRACE, ARM, [(0.0, 0.0), (9.0, 9.0)])
        self.assertGreater(out["centered_frechet"], 0.0)
        self.assertEqual((out["n"], out["m"]), (3, 2))

    def test_joint_space_refused(self):
        with self.assertRaises(XEmbodimentError) as ctx:
            transfer_score(JOINT, TRACE, ARM, TRACE)
        self.assertIn("REFUSED", str(ctx.exception))

    def test_dim_mismatch_refused(self):
        with self.assertRaises(XEmbodimentError):
            transfer_score(ARM, TRACE, ARM, [(0.0, 0.0, 0.0)])

    def test_report_verdict(self):
        out = transfer_report(ARM, TRACE, ARM, TRACE, threshold=0.1)
        self.assertTrue(out["transfers"])
        self.assertIn("M5b", out["limitation"])
        out = transfer_report(ARM, TRACE, ARM, [(0.0, 0.0), (9.0, 9.0)],
                              threshold=0.1)
        self.assertFalse(out["transfers"])

    def test_bool_inputs_rejected(self):
        bad_card = dict(ARM, position_scale=True)
        with self.assertRaises(XEmbodimentError):
            transfer_score(bad_card, TRACE, ARM, TRACE)
        with self.assertRaises(XEmbodimentError):
            transfer_score(ARM, [(True, 0.0)], ARM, TRACE)
        with self.assertRaises(XEmbodimentError):
            transfer_report(ARM, TRACE, ARM, TRACE, threshold=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
