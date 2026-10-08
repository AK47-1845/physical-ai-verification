"""G9/G10 gate tests: property margins, time-to-success.

Run from meta bro root:  python tests/test_gates.py
(stdlib only)
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.fall_impact import FallImpactError, assess_fall_impact  # noqa: E402
from engine.property import PropertyError, check_property  # noqa: E402
from engine.success_time import SuccessTimeError, first_success_times, summarize_times  # noqa: E402


class TestProperty(unittest.TestCase):
    def test_always_holds(self):
        spec = {"op": "always", "name": "x-positive", "version": "1",
                "predicate": lambda s: s}
        out = check_property(spec, [1.0, 2.0, 3.0])
        self.assertTrue(out["satisfied"])
        self.assertEqual(out["margin"], 1.0)
        self.assertEqual(out["witness"], 0)
        self.assertEqual(out["label"], "MEASURED")

    def test_always_violated(self):
        spec = {"op": "always", "name": "x", "version": "1",
                "predicate": lambda s: s}
        out = check_property(spec, [1.0, -2.0])
        self.assertFalse(out["satisfied"])
        self.assertEqual((out["margin"], out["witness"]), (-2.0, 1))

    def test_boundary_zero_fails_closed(self):
        spec = {"op": "always", "name": "x", "version": "1",
                "predicate": lambda s: s}
        out = check_property(spec, [0.0, 1.0])
        self.assertEqual(out["margin"], 0.0)
        self.assertFalse(out["satisfied"])

    def test_eventually(self):
        spec = {"op": "eventually", "name": "x", "version": "1",
                "predicate": lambda s: s}
        out = check_property(spec, [-1.0, -2.0, 0.5])
        self.assertTrue(out["satisfied"])
        self.assertEqual((out["margin"], out["witness"]), (0.5, 2))

    def test_window_slicing(self):
        spec = {"op": "always", "name": "x", "version": "1",
                "predicate": lambda s: s, "window": [0, 0]}
        out = check_property(spec, [5.0, -9.0, 5.0])
        self.assertTrue(out["satisfied"])
        self.assertEqual(out["margin"], 5.0)

    def test_estimated_labels_proxy(self):
        spec = {"op": "always", "name": "x", "version": "1",
                "predicate": lambda s: s}
        out = check_property(spec, [1.0], state_origin="estimated")
        self.assertEqual(out["label"], "PROXY")

    def test_spec_hash_stable(self):
        spec = {"op": "always", "name": "x", "version": "1",
                "predicate": lambda s: s}
        a = check_property(spec, [1.0])
        b = check_property(spec, [2.0])
        self.assertEqual(a["spec_hash"], b["spec_hash"])

    def test_bad_inputs_raise(self):
        with self.assertRaises(PropertyError):
            check_property({"op": "sometimes", "name": "x",
                            "predicate": lambda s: 1.0}, [1.0])
        with self.assertRaises(PropertyError):
            check_property({"op": "always", "name": "x",
                            "predicate": lambda s: 1.0,
                            "window": [0, 5]}, [1.0])
        with self.assertRaises(PropertyError):
            check_property({"op": "always", "name": "x",
                            "predicate": lambda s: float("nan")}, [1.0])

    def test_bool_window_and_margins_rejected(self):
        base = {"op": "always", "name": "x", "version": "1",
                "predicate": lambda s: s}
        with self.assertRaises(PropertyError):
            check_property(dict(base, window=[True, 0]), [1.0])
        with self.assertRaises(PropertyError):
            check_property(dict(base, predicate=lambda s: True), [1.0])

    def test_string_and_dict_traces_rejected(self):
        spec = {"op": "always", "name": "x", "version": "1",
                "predicate": lambda s: 1.0}
        for bad in ("abc", b"abc", {"a": 1}):
            with self.assertRaises(PropertyError, msg=repr(bad)):
                check_property(spec, bad)

    def test_version_type_tagged_in_hash(self):
        def mk(v):
            return {"op": "always", "name": "x", "version": v,
                    "predicate": lambda s: s}
        a = check_property(mk(1), [1.0])
        b = check_property(mk("1"), [1.0])
        self.assertNotEqual(a["spec_hash"], b["spec_hash"])
        self.assertEqual(a["margin"], b["margin"])


class TestSuccessTime(unittest.TestCase):
    def test_hand_distribution(self):
        times = first_success_times([[False, False, True], [True], [False]],
                                    lambda s: s)
        self.assertEqual(times, [2, 0, None])
        summary = summarize_times(times)
        self.assertEqual((summary["n"], summary["successes"],
                          summary["censored"]), (3, 2, 1))
        self.assertAlmostEqual(summary["success_rate"], 2 / 3)
        self.assertEqual(summary["median_time"], 1.0)
        self.assertEqual(summary["mean_time"], 1.0)
        self.assertEqual((summary["min_time"], summary["max_time"]), (0, 2))

    def test_all_censored(self):
        summary = summarize_times([None, None])
        self.assertEqual(summary["success_rate"], 0.0)
        self.assertIsNone(summary["median_time"])
        self.assertIsNone(summary["mean_time"])

    def test_bad_inputs_raise(self):
        with self.assertRaises(SuccessTimeError):
            first_success_times([], lambda s: True)
        with self.assertRaises(SuccessTimeError):
            first_success_times([[]], lambda s: True)
        with self.assertRaises(SuccessTimeError):
            first_success_times([[1]], lambda s: 1)
        with self.assertRaises(SuccessTimeError):
            summarize_times([])

    def test_string_containers_rejected(self):
        fn = lambda s: True  # noqa: E731
        for bad in ("ab", b"ab", {"r": [1]}):
            with self.assertRaises(SuccessTimeError, msg=repr(bad)):
                first_success_times(bad, fn)
            with self.assertRaises(SuccessTimeError, msg=repr(bad)):
                first_success_times([bad], fn)

    def test_bool_times_rejected(self):
        for bad in (True, False):
            with self.assertRaises(SuccessTimeError):
                summarize_times([0, bad])
        with self.assertRaises(SuccessTimeError):
            summarize_times([1.5])


class TestFallImpact(unittest.TestCase):
    def test_always_insufficient(self):
        out = assess_fall_impact()
        self.assertEqual(out["gate"], "G11_fall_impact")
        self.assertEqual(out["status"], "DRAFT_PLACEHOLDER")
        self.assertEqual(out["verdict"], "INSUFFICIENT")
        self.assertIn("25785-1", out["reason"])

    def test_metrics_recorded_never_judged(self):
        out = assess_fall_impact({"hic_proxy": 12.5, "impulse": 3.0})
        self.assertEqual(out["verdict"], "INSUFFICIENT")
        self.assertEqual(out["metrics"], {"hic_proxy": 12.5,
                                          "impulse": 3.0})

    def test_bad_metrics_raise(self):
        with self.assertRaises(FallImpactError):
            assess_fall_impact({"hic": float("inf")})
        with self.assertRaises(FallImpactError):
            assess_fall_impact({"hic": True})
        with self.assertRaises(FallImpactError):
            assess_fall_impact(["hic"])

    def test_deterministic(self):
        self.assertEqual(assess_fall_impact({"a": 1.0}),
                         assess_fall_impact({"a": 1.0}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
