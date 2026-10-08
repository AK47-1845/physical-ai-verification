"""M2 tests: chunk envelope guard (position/velocity/acceleration).

Run from meta bro root:  python tests/test_m2.py
(runs under unittest and pytest alike; stdlib only)
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.guard import GuardError, check_chunk  # noqa: E402

BOUNDS = [(-1.0, 1.0), (-1.0, 1.0)]
FULL = {"position": BOUNDS, "velocity": [2.0, 2.0],
        "acceleration": [50.0, 50.0]}


class TestGuard(unittest.TestCase):
    def test_clean_chunk_passes(self):
        out = check_chunk([[0.0, 0.0], [0.1, 0.0], [0.2, 0.0]],
                          FULL, dt=0.1)
        self.assertFalse(out["halt"])
        self.assertEqual(out["breaches"], [])
        self.assertEqual((out["steps"], out["joints"]), (3, 2))

    def test_position_breach_halts(self):
        out = check_chunk([[0.0], [2.0]], {"position": [(-1.0, 1.0)]},
                          dt=0.1)
        self.assertTrue(out["halt"])
        self.assertEqual(out["breaches"][0]["check"], "position")
        self.assertEqual(out["breaches"][0]["step"], 1)

    def test_velocity_breach_halts(self):
        # v = (1-0)/0.1 = 10 > 2, detected at step 1
        out = check_chunk([[0.0], [1.0]],
                          {"position": [(-5.0, 5.0)], "velocity": [2.0]},
                          dt=0.1)
        self.assertTrue(out["halt"])
        hits = [b for b in out["breaches"] if b["check"] == "velocity"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["step"], 1)
        self.assertAlmostEqual(hits[0]["value"], 10.0)

    def test_acceleration_breach_halts(self):
        # v: 1 then 4; a = (4-1)/0.1 = 30 > 5, detected at step 2
        out = check_chunk([[0.0], [0.1], [0.5]],
                          {"position": [(-5.0, 5.0)],
                           "velocity": [100.0], "acceleration": [5.0]},
                          dt=0.1)
        self.assertTrue(out["halt"])
        hits = [b for b in out["breaches"] if b["check"] == "acceleration"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["step"], 2)
        self.assertAlmostEqual(hits[0]["value"], 30.0)

    def test_optional_limits_skip_checks(self):
        # velocity 10 would breach a cap, but none is given
        out = check_chunk([[0.0], [1.0]], {"position": [(-5.0, 5.0)]},
                          dt=0.1)
        self.assertFalse(out["halt"])

    def test_single_step_position_only(self):
        out = check_chunk([[0.5]], FULL_SINGLE, dt=0.1)
        self.assertFalse(out["halt"])

    def test_bool_values_rejected(self):
        good = {"position": [(-1.0, 1.0)]}
        with self.assertRaises(GuardError):
            check_chunk([[True]], good, dt=0.1)
        with self.assertRaises(GuardError):
            check_chunk([[0.5]], good, dt=True)
        with self.assertRaises(GuardError):
            check_chunk([[0.5]], {"position": [(True, 1.0)]}, dt=0.1)
        with self.assertRaises(GuardError):
            check_chunk([[0.0], [0.1]],
                          {"position": [(-5.0, 5.0)],
                           "velocity": [True]}, dt=0.1)

    def test_unknown_limits_key_rejected(self):
        with self.assertRaises(GuardError):
            check_chunk([[0.0], [0.1]],
                          {"position": [(-5.0, 5.0)],
                           "velosity": [2.0]}, dt=0.1)
        with self.assertRaises(GuardError):
            check_chunk([[0.0]], {"position": [(-1.0, 1.0)],
                                  "jerk": [1.0]}, dt=0.1)

    def test_null_caps_skip(self):
        out = check_chunk([[0.0], [1.0]],
                          {"position": [(-5.0, 5.0)],
                           "velocity": None, "acceleration": None},
                          dt=0.1)
        self.assertFalse(out["halt"])

    def test_bad_inputs_raise(self):
        with self.assertRaises(GuardError):
            check_chunk([], FULL, dt=0.1)
        with self.assertRaises(GuardError):
            check_chunk([[0.0], [0.1, 0.2]], FULL, dt=0.1)
        with self.assertRaises(GuardError):
            check_chunk([[0.0]], FULL, dt=0.0)
        with self.assertRaises(GuardError):
            check_chunk([[0.0]], {"velocity": [1.0]}, dt=0.1)
        with self.assertRaises(GuardError):
            check_chunk([[0.0]], FULL, dt=0.1)
        with self.assertRaises(GuardError):
            check_chunk([[float("nan")]], {"position": [(-1.0, 1.0)]},
                        dt=0.1)
        with self.assertRaises(GuardError):
            check_chunk([0.0, 0.1], {"position": [(-1.0, 1.0)]},
                        dt=0.1)
        with self.assertRaises(GuardError):
            check_chunk(5.0, {"position": [(-1.0, 1.0)]}, dt=0.1)


FULL_SINGLE = {"position": [(-1.0, 1.0)], "velocity": [2.0],
               "acceleration": [50.0]}


if __name__ == "__main__":
    unittest.main(verbosity=2)
