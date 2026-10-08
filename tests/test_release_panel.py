"""Release + panel tests: FR-34 deltas, FR-37 commit-reveal.

Run from meta bro root:  python tests/test_release_panel.py
(stdlib only)
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.panel import PanelError, build_panel, commit, reveal  # noqa: E402
from engine.release import ReleaseError, compare  # noqa: E402

G_PASS = {"gate": "t", "measurement": 0.1, "status": "PASS"}
G_BLOCK = {"gate": "t", "measurement": 0.9, "status": "BLOCKED"}


class TestRelease(unittest.TestCase):
    def test_identical_shortcircuits(self):
        out = compare([G_PASS], [G_PASS], parent_weights_hash="h",
                      child_weights_hash="h")
        self.assertTrue(out["identical"])
        self.assertEqual(out["deltas"], [])
        self.assertIsNone(out["flag"])
        self.assertEqual(out["hash_proof"], "h")

    def test_regression_flags(self):
        out = compare([G_PASS], [G_BLOCK], parent_weights_hash="p",
                      child_weights_hash="c")
        self.assertFalse(out["identical"])
        self.assertEqual(out["flag"], "SUBSTANTIAL_MODIFICATION_CANDIDATE")
        self.assertAlmostEqual(out["deltas"][0]["delta"], 0.8)
        self.assertTrue(out["deltas"][0]["worsened"])
        self.assertEqual(out["deltas"][0]["status_shift"],
                         ["PASS", "BLOCKED"])

    def test_improvement_no_flag(self):
        out = compare([G_BLOCK], [G_PASS], parent_weights_hash="p",
                      child_weights_hash="c")
        self.assertIsNone(out["flag"])
        self.assertFalse(out["deltas"][0]["worsened"])

    def test_tolerance_breach_flags(self):
        g1 = {"gate": "t", "measurement": 0.1, "status": "PASS"}
        g2 = {"gate": "t", "measurement": 0.2, "status": "PASS"}
        out = compare([g1], [g2], parent_weights_hash="p",
                      child_weights_hash="c", tolerances={"t": 0.05})
        self.assertEqual(out["flag"], "SUBSTANTIAL_MODIFICATION_CANDIDATE")

    def test_conservative_delta_ci(self):
        # binary-exact fractions only: [0.5-0.25, 0.75-0.125] = [0.25, 0.625]
        g1 = dict(G_PASS, ci={"lo": 0.125, "hi": 0.25})
        g2 = dict(G_PASS, ci={"lo": 0.5, "hi": 0.75})
        g2 = dict(g2, measurement=0.625)
        out = compare([g1], [g2], parent_weights_hash="p",
                      child_weights_hash="c")
        self.assertEqual(out["deltas"][0]["delta_ci"], [0.25, 0.625])

    def test_gate_set_mismatch_raises(self):
        other = {"gate": "x", "measurement": 0.1, "status": "PASS"}
        with self.assertRaises(ReleaseError):
            compare([G_PASS], [other], parent_weights_hash="p",
                    child_weights_hash="c")

    def test_falsy_non_dict_tolerances_rejected(self):
        for bad in (0, [], False):
            with self.assertRaises(ReleaseError, msg=bad):
                compare([G_PASS], [G_PASS], parent_weights_hash="p",
                        child_weights_hash="c", tolerances=bad)

    def test_unhashable_status_rejected(self):
        bad = {"gate": "t", "measurement": 0.1, "status": ["PASS"]}
        with self.assertRaises(ReleaseError):
            compare([bad], [G_PASS], parent_weights_hash="p",
                    child_weights_hash="c")

    def test_bool_measurements_rejected(self):
        for boolean in (True, False):
            bad = {"gate": "t", "measurement": boolean, "status": "PASS"}
            with self.assertRaises(ReleaseError):
                compare([bad], [G_PASS], parent_weights_hash="p",
                        child_weights_hash="c")

    def test_nonstring_hashes_rejected(self):
        for bad in (123, None, "", ["h"]):
            with self.assertRaises(ReleaseError, msg=repr(bad)):
                compare([G_PASS], [G_PASS], parent_weights_hash=bad,
                        child_weights_hash="c")

    def test_bool_tolerance_rejected(self):
        with self.assertRaises(ReleaseError):
            compare([G_PASS], [G_PASS], parent_weights_hash="p",
                    child_weights_hash="c", tolerances={"t": True})

    def test_bool_ci_endpoints_yield_none(self):
        g1 = dict(G_PASS, ci={"lo": True, "hi": 0.25})
        g2 = dict(G_PASS, ci={"lo": 0.5, "hi": 0.75})
        out = compare([g1], [g2], parent_weights_hash="p",
                      child_weights_hash="c")
        self.assertIsNone(out["deltas"][0]["delta_ci"])

    def test_insufficient_appearing_flags(self):
        gone = {"gate": "t", "measurement": 0.1, "status": "INSUFFICIENT"}
        out = compare([G_PASS], [gone], parent_weights_hash="p",
                      child_weights_hash="c")
        self.assertEqual(out["flag"], "SUBSTANTIAL_MODIFICATION_CANDIDATE")
        self.assertTrue(out["deltas"][0]["worsened"])
        self.assertIn("evidence vanished", out["reasons"][0])
        masked = compare([G_BLOCK], [gone], parent_weights_hash="p",
                         child_weights_hash="c")
        self.assertEqual(masked["flag"],
                         "SUBSTANTIAL_MODIFICATION_CANDIDATE")

    def test_insufficient_resolving_no_flag(self):
        gone = {"gate": "t", "measurement": 0.1, "status": "INSUFFICIENT"}
        out = compare([gone], [G_PASS], parent_weights_hash="p",
                      child_weights_hash="c")
        self.assertIsNone(out["flag"])
        self.assertFalse(out["deltas"][0]["worsened"])

    def test_identical_path_validates_gates(self):
        bad = {"gate": "t", "measurement": "lots", "status": "PASS"}
        with self.assertRaises(ReleaseError):
            compare([bad], [bad], parent_weights_hash="h",
                    child_weights_hash="h")


class TestPanel(unittest.TestCase):
    def test_commit_reveal_roundtrip(self):
        stamp = commit("seed-1", 12)
        result = reveal(stamp["commitment"], "seed-1", 12)
        self.assertTrue(result["verified"])

    def test_wrong_seed_fails(self):
        stamp = commit("seed-1", 12)
        result = reveal(stamp["commitment"], "seed-2", 12)
        self.assertFalse(result["verified"])

    def test_wrong_count_fails(self):
        stamp = commit("seed-1", 12)
        result = reveal(stamp["commitment"], "seed-1", 13)
        self.assertFalse(result["verified"])

    def test_build_deterministic(self):
        make = lambda rng, i: {"case": i, "x": rng.random()}  # noqa: E731
        a = build_panel("s", 5, make)
        b = build_panel("s", 5, make)
        self.assertEqual(a, b)
        c = build_panel("other", 5, make)
        self.assertNotEqual(a["cases"], c["cases"])

    def test_bad_inputs_raise(self):
        with self.assertRaises(PanelError):
            commit("", 3)
        with self.assertRaises(PanelError):
            commit("s", 0)
        with self.assertRaises(PanelError):
            build_panel("s", 2, "not-callable")

    def test_bool_seeds_rejected(self):
        for boolean in (True, False):
            with self.assertRaises(PanelError):
                commit(boolean, 3)
            with self.assertRaises(PanelError):
                build_panel(boolean, 2, lambda rng, i: i)
            result = reveal("x" * 64, boolean, 3)
            self.assertFalse(result["verified"])

    def test_str_int_seed_normalization_pinned(self):
        self.assertEqual(commit("1", 5)["commitment"],
                         commit(1, 5)["commitment"])
        make = lambda rng, i: {"x": rng.random()}  # noqa: E731
        self.assertEqual(build_panel("1", 3, make)["cases"],
                         build_panel(1, 3, make)["cases"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
