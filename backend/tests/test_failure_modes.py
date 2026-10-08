"""Failure-mode harness tests: FM1..FM5 incl. MVP-steal behaviors.

Run from meta bro root:  python backend/tests/test_failure_modes.py
(stdlib only)
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from backend.eval.failure_modes import (  # noqa: E402
    FailureModeError,
    drift_gate,
    executability_proxy,
    hallucination_gate,
    marginalization_probe,
    marginalization_shuffle,
    sim_real_gap,
)


class TestFM1(unittest.TestCase):
    def test_identical_no_breach(self):
        out = drift_gate([(0.0,), (1.0,)], [(0.0,), (1.0,)], threshold=0.5)
        self.assertFalse(out["breach"])
        self.assertEqual(out["coherence_horizon"], 2)
        self.assertEqual(out["horizon_ratio"], 1.0)

    def test_sustained_breach_trips(self):
        out = drift_gate([(0.0,)] * 5,
                         [(0.0,), (0.0,), (1.0,), (1.0,), (1.0,)],
                         threshold=0.5, breach_run=2)
        self.assertTrue(out["breach"])
        self.assertEqual(out["coherence_horizon"], 2)
        self.assertEqual(out["horizon_ratio"], 0.4)

    def test_single_spike_debounced(self):
        out = drift_gate([(0.0,)] * 5,
                         [(0.0,), (0.0,), (5.0,), (0.0,), (0.0,)],
                         threshold=0.5, breach_run=2)
        self.assertFalse(out["breach"])
        self.assertEqual(out["coherence_horizon"], 5)

    def test_bad_thresholds_rejected(self):
        for bad in (-0.1, True):
            with self.assertRaises(FailureModeError, msg=repr(bad)):
                drift_gate([(0.0,)], [(0.0,)], threshold=bad)

    def test_bool_coords_rejected(self):
        with self.assertRaises(FailureModeError):
            drift_gate([(True,)], [(0.0,)], threshold=0.5)


class TestFM2Proxy(unittest.TestCase):
    def test_straight_line_zero_jerk(self):
        traj = [[float(t), 0.0] for t in range(6)]
        out = executability_proxy(traj, bounds=(-1.0, 6.0))
        self.assertAlmostEqual(out["max_jerk"], 0.0)
        self.assertEqual(out["bound_violations"], 0)
        self.assertIn("PROXY", out["proxy_warning"])

    def test_violations_counted(self):
        out = executability_proxy([[0.0, 0.0], [9.0, 0.0], [0.0, -9.0]],
                                  bounds=(-2.0, 2.0))
        self.assertEqual(out["bound_violations"], 2)
        self.assertAlmostEqual(out["violation_rate"], 2 / 6)

    def test_malformed_bounds_rejected(self):
        traj = [[0.0, 0.0], [1.0, 0.0]]
        for bad in ([1.0], "ab", 5, (2.0, -2.0), (True, 1.0)):
            with self.assertRaises(FailureModeError, msg=repr(bad)):
                executability_proxy(traj, bounds=bad)


class TestFM3(unittest.TestCase):
    def test_identity_no_trips(self):
        out = hallucination_gate(lambda x: x, lambda z: z,
                                 [[1.0, 2.0], [3.0, 4.0]], threshold=0.0)
        self.assertEqual(out["residuals"], [0.0, 0.0])
        self.assertEqual(out["trips"], [])

    def test_collapsed_codebook_trips(self):
        out = hallucination_gate(lambda x: [0.0], lambda z: [0.0, 0.0],
                                 [[3.0, 4.0]], threshold=24.9)
        self.assertEqual(out["residuals"], [25.0])
        self.assertEqual(out["trips"], [0])
        self.assertEqual(out["trip_rate"], 1.0)

    def test_threshold_boundary_strict(self):
        out = hallucination_gate(lambda x: [0.0], lambda z: [0.0, 0.0],
                                 [[3.0, 4.0]], threshold=25.0)
        self.assertEqual(out["trips"], [])

    def test_bad_model_raises(self):
        with self.assertRaises(FailureModeError):
            hallucination_gate(lambda x: x, lambda z: [1.0],
                               [[1.0, 2.0]], threshold=1.0)

    def test_negative_threshold_rejected(self):
        with self.assertRaises(FailureModeError):
            hallucination_gate(lambda x: x, lambda z: z,
                               [[1.0, 2.0]], threshold=-1.0)


class TestFM4(unittest.TestCase):
    def test_shuffle_wiring(self):
        out = marginalization_shuffle(lambda z, a: [1.0], None,
                                      [0, 1, 2], seed=5)
        self.assertTrue(out["marginalized"])

    def test_probe_echo_responsive(self):
        echo = lambda acts, seed: [row[:] for row in acts]  # noqa: E731
        out = marginalization_probe(echo, [[1.0, 0.0]] * 4,
                                    probe_offsets=[0.5, -0.3], seed=1)
        self.assertAlmostEqual(out["normalized"], 0.17, places=6)
        self.assertTrue(out["responsive"])

    def test_probe_playback_dead(self):
        tape = lambda acts, seed: [[0.0, 0.0]] * len(acts)  # noqa: E731
        out = marginalization_probe(tape, [[1.0, 0.0]] * 4,
                                    probe_offsets=[0.5, -0.3], seed=1)
        self.assertEqual(out["raw"], 0.0)
        self.assertEqual(out["normalized"], 0.0)
        self.assertFalse(out["responsive"])

    def test_null_probe_rejected(self):
        echo = lambda acts, seed: [row[:] for row in acts]  # noqa: E731
        with self.assertRaises(FailureModeError):
            marginalization_probe(echo, [[1.0, 0.0]] * 4,
                                  probe_offsets=[0.0, 0.0], seed=1)

    def test_rollout_dim_change_rejected(self):
        shrink = lambda acts, seed: [[0.0]] * len(acts)  # noqa: E731
        with self.assertRaises(FailureModeError):
            marginalization_probe(shrink, [[1.0, 0.0]] * 4,
                                  probe_offsets=[0.5, -0.3], seed=1)


class TestFM5(unittest.TestCase):
    def test_hand_corridor(self):
        out = sim_real_gap([(0.0, 0.0), (2.0, 0.0)],
                           [(0.0, 1.0), (2.0, 1.0)])
        self.assertEqual(out["frechet"], 1.0)

    def test_refusal_bubbles(self):
        with self.assertRaises(FailureModeError):
            sim_real_gap([], [(0.0,)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
