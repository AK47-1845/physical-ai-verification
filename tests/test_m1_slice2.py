"""M1 slice 2 tests: drift, sensitivity, spread, bootstrap CI, scorer.

Run from meta bro root:  python tests/test_m1_slice2.py
(runs under unittest and pytest alike; stdlib only)
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.ci import CIError, bootstrap_ci  # noqa: E402
from engine.drift import DriftError, drift_report, summarize  # noqa: E402
from engine.scorer import ScorerError, evaluate_gate, evaluate_scorecard, rank_policies  # noqa: E402
from engine.sensitivity import SensitivityError, action_sensitivity  # noqa: E402
from engine.spread import SpreadError, ensemble_spread  # noqa: E402


class TestDrift(unittest.TestCase):
    def test_identical_is_zero(self):
        p = [(0.0, 0.0), (1.0, 2.0)]
        rep = drift_report(p, p)
        self.assertEqual(rep["per_sample"], [0.0, 0.0])
        self.assertEqual((rep["max"], rep["mean"]), (0.0, 0.0))
        self.assertEqual(rep["horizon"], 2)

    def test_hand_computed(self):
        rep = drift_report([(0.0, 0.0), (1.0, 0.0)],
                           [(0.0, 1.0), (1.0, 1.0)])
        self.assertEqual(rep["per_sample"], [1.0, 1.0])
        self.assertEqual((rep["max"], rep["mean"]), (1.0, 1.0))

    def test_length_mismatch_raises(self):
        with self.assertRaises(DriftError):
            drift_report([(0.0,)], [(0.0,), (1.0,)])

    def test_ragged_raises(self):
        with self.assertRaises(DriftError):
            drift_report([(0.0, 0.0), (1.0,)], [(0.0, 0.0), (1.0, 1.0)])

    def test_bool_coords_rejected(self):
        with self.assertRaises(DriftError):
            drift_report([(True, 0.0)], [(0.0, 0.0)])

    def test_summarize_validates(self):
        self.assertEqual(summarize([1.0, 3.0])["mean"], 2.0)
        for bad in (["a"], [True], [float("nan")], [], "ab", {"m": 1}):
            with self.assertRaises(DriftError, msg=repr(bad)):
                summarize(bad)


class TestSensitivity(unittest.TestCase):
    def test_constant_predictor_is_marginalized(self):
        out = action_sensitivity(lambda z, a: [0.5, 0.5], None,
                                 [0, 1, 2, 3], seed=7)
        self.assertEqual(out["statistic"], 0.0)
        self.assertTrue(out["marginalized"])

    def test_echo_predictor_is_sensitive(self):
        echo = lambda z, a: [float(v) for v in a]  # noqa: E731
        acts = [0, 1, 2, 3, 4]
        # at least one seed over ten must permute (p(all identity) ~= 0)
        stats = [action_sensitivity(echo, None, acts, seed=s)["statistic"]
                 for s in range(10)]
        self.assertTrue(any(s > 0 for s in stats))

    def test_seeded_determinism(self):
        echo = lambda z, a: [float(v) for v in a]  # noqa: E731
        a = action_sensitivity(echo, None, [0, 1, 2], seed=3)
        b = action_sensitivity(echo, None, [0, 1, 2], seed=3)
        self.assertEqual(a, b)

    def test_bool_inputs_rejected(self):
        echo = lambda z, a: [float(v) for v in a]  # noqa: E731
        with self.assertRaises(SensitivityError):
            action_sensitivity(echo, None, [0, 1], seed=True)
        with self.assertRaises(SensitivityError):
            action_sensitivity(echo, None, [0, 1], seed=1, threshold=True)
        with self.assertRaises(SensitivityError):
            action_sensitivity(lambda z, a: [True], None, [0, 1], seed=1)

    def test_crashes_wrapped(self):
        def boom(z, a):
            raise RuntimeError("model down")
        with self.assertRaises(SensitivityError) as ctx:
            action_sensitivity(boom, None, [0, 1], seed=1)
        self.assertIn("crashed", str(ctx.exception))

    def test_bad_actions_rejected(self):
        echo = lambda z, a: [float(v) for v in a]  # noqa: E731
        for bad in ("ab", {"a": 1}):
            with self.assertRaises(SensitivityError, msg=repr(bad)):
                action_sensitivity(echo, None, bad, seed=1)


class TestSpread(unittest.TestCase):
    def test_identical_is_zero(self):
        r = [[(0.0, 1.0), (2.0, 3.0)], [(0.0, 1.0), (2.0, 3.0)]]
        out = ensemble_spread(r)
        self.assertEqual(out["per_sample"], [0.0, 0.0])

    def test_hand_computed(self):
        # sample0 pts (0,0),(2,0): dim vars 1,0 -> sqrt(1/2); same sample1
        out = ensemble_spread([[(0.0, 0.0), (2.0, 0.0)],
                               [(2.0, 0.0), (0.0, 0.0)]])
        self.assertAlmostEqual(out["per_sample"][0], 0.7071067811865476)
        self.assertAlmostEqual(out["max"], out["mean"])
        self.assertEqual(out["rollouts"], 2)

    def test_single_rollout_is_zero(self):
        out = ensemble_spread([[(1.0,), (2.0,)]])
        self.assertEqual(out["per_sample"], [0.0, 0.0])

    def test_length_mismatch_raises(self):
        with self.assertRaises(SpreadError):
            ensemble_spread([[(0.0,)], [(0.0,), (1.0,)]])

    def test_bool_coords_rejected(self):
        with self.assertRaises(SpreadError):
            ensemble_spread([[(True,)], [(False,)]])


class TestCI(unittest.TestCase):
    def test_constant_values_exact(self):
        out = bootstrap_ci([5.0] * 20, seed=1)
        self.assertEqual((out["lo"], out["hi"], out["mean"]), (5.0, 5.0, 5.0))
        self.assertEqual(out["n"], 20)

    def test_seeded_determinism(self):
        vals = [0.1, 0.4, 0.3, 0.9, 0.2]
        a = bootstrap_ci(vals, seed=11, resamples=200)
        b = bootstrap_ci(vals, seed=11, resamples=200)
        self.assertEqual(a, b)
        self.assertLessEqual(a["lo"], a["mean"])
        self.assertLessEqual(a["mean"], a["hi"])

    def test_bad_inputs_raise(self):
        with self.assertRaises(CIError):
            bootstrap_ci([], seed=1)
        with self.assertRaises(CIError):
            bootstrap_ci([1.0], seed=1, alpha=0.0)
        with self.assertRaises(CIError):
            bootstrap_ci([1.0], seed=1, alpha=1.0)
        with self.assertRaises(CIError):
            bootstrap_ci([1.0], seed=1, resamples=0)

    def test_nonfinite_raises(self):
        with self.assertRaises(CIError):
            bootstrap_ci([1.0, float("nan")], seed=1)

    def test_bool_inputs_rejected(self):
        with self.assertRaises(CIError):
            bootstrap_ci([1.0, True], seed=1)
        with self.assertRaises(CIError):
            bootstrap_ci([1.0], seed=True)
        with self.assertRaises(CIError):
            bootstrap_ci([1.0], seed=1, alpha=True)

    def test_bad_containers_rejected(self):
        for bad in ("ab", b"ab", {0: 1.0}):
            with self.assertRaises(CIError, msg=repr(bad)):
                bootstrap_ci(bad, seed=1)

    def test_bytes_seed_echoed_raw(self):
        out = bootstrap_ci([1.0, 2.0, 3.0], seed=b"audit")
        self.assertEqual(out["seed"], b"audit")
        self.assertLessEqual(out["lo"], out["hi"])


class TestScorer(unittest.TestCase):
    def test_pass_review_blocked(self):
        g = lambda m: evaluate_gate(  # noqa: E731
            "t", m, green=0.15, amber=0.5, evidence="ev:1")
        self.assertEqual(g(0.1)["status"], "PASS")
        self.assertEqual(g(0.2)["status"], "REVIEW")
        self.assertEqual(g(0.9)["status"], "BLOCKED")

    def test_higher_is_better_flips(self):
        g = lambda m: evaluate_gate(  # noqa: E731
            "s", m, green=0.5, amber=0.8, evidence="ev:1",
            higher_is_better=True)
        self.assertEqual(g(0.9)["status"], "PASS")
        self.assertEqual(g(0.6)["status"], "REVIEW")
        self.assertEqual(g(0.1)["status"], "BLOCKED")

    def test_below_min_n_is_insufficient(self):
        out = evaluate_gate("t", 0.01, green=0.15, amber=0.5,
                            evidence="ev:1", min_n=10, n=3)
        self.assertEqual(out["status"], "INSUFFICIENT")
        self.assertEqual(out["band"], "grey")

    def test_bad_thresholds_raise(self):
        with self.assertRaises(Exception):
            evaluate_gate("t", 0.1, green=0.5, amber=0.15, evidence="ev:1")

    def test_bad_counts_raise(self):
        kw = {"green": 0.15, "amber": 0.5, "evidence": "ev:1"}
        for bad_min in (True, "10", -1, 2.5):
            with self.assertRaises(ScorerError, msg=bad_min):
                evaluate_gate("t", 0.1, min_n=bad_min, n=3, **kw)
        for bad_n in (True, "3", 2.5):
            with self.assertRaises(ScorerError, msg=bad_n):
                evaluate_gate("t", 0.1, min_n=10, n=bad_n, **kw)

    def test_scorecard_trusted_and_pinned(self):
        gates = [evaluate_gate("a", 0.1, green=0.15, amber=0.5,
                               evidence="ev:a"),
                 evaluate_gate("b", 0.1, green=0.15, amber=0.5,
                               evidence="ev:b")]
        card = evaluate_scorecard(gates, profile_version="draft-0", seed=9)
        self.assertEqual(card["payload"]["verdict"], "TRUSTED")
        self.assertIn("envelope_hash", card)
        again = evaluate_scorecard(gates, profile_version="draft-0", seed=9)
        self.assertEqual(card["envelope_hash"], again["envelope_hash"])

    def test_scorecard_blocked(self):
        gates = [evaluate_gate("a", 9.9, green=0.15, amber=0.5,
                               evidence="ev:a")]
        card = evaluate_scorecard(gates, profile_version="draft-0", seed=9)
        self.assertEqual(card["payload"]["verdict"], "BLOCKED")
        self.assertEqual(card["payload"]["band"], "red")

    def test_scorecard_malformed_is_scorer_error(self):
        kw = {"profile_version": "draft-0", "seed": 9}
        with self.assertRaises(ScorerError):
            evaluate_scorecard([{"gate": "a"}], **kw)
        with self.assertRaises(ScorerError):
            evaluate_scorecard(["nope"], **kw)
        with self.assertRaises(ScorerError):
            evaluate_scorecard([{"gate": "a", "status": "CERTIFIED"}],
                               **kw)
        with self.assertRaises(ScorerError):
            evaluate_scorecard(42, **kw)


class TestRank(unittest.TestCase):
    def _entry(self, pid, verdict, statuses):
        return {"policy_id": pid, "verdict": verdict,
                "gates": [{"status": s} for s in statuses]}

    def test_worst_first(self):
        out = rank_policies([
            self._entry("good", "TRUSTED", ["PASS", "PASS"]),
            self._entry("bad", "BLOCKED", ["BLOCKED", "PASS"]),
            self._entry("mid", "REVIEW", ["REVIEW", "PASS"]),
        ])
        self.assertEqual(out["ranking"], ["bad", "mid", "good"])
        self.assertEqual(out["rows"][0]["rank"], 1)
        self.assertEqual(out["policies"], 3)

    def test_tiebreak_counts_then_id(self):
        out = rank_policies([
            self._entry("b", "REVIEW", ["REVIEW"]),
            self._entry("a", "REVIEW", ["REVIEW", "REVIEW"]),
            self._entry("c", "REVIEW", ["INSUFFICIENT"]),
        ])
        self.assertEqual(out["ranking"], ["a", "b", "c"])

    def test_blocked_count_beats_label_tie(self):
        out = rank_policies([
            self._entry("one", "BLOCKED", ["BLOCKED", "PASS"]),
            self._entry("two", "BLOCKED", ["BLOCKED", "BLOCKED"]),
        ])
        self.assertEqual(out["ranking"], ["two", "one"])

    def test_bad_entries_raise(self):
        with self.assertRaises(ScorerError):
            rank_policies([])
        with self.assertRaises(ScorerError):
            rank_policies([self._entry("a", "TRUSTED", ["PASS"]),
                           self._entry("a", "TRUSTED", ["PASS"])])
        with self.assertRaises(ScorerError):
            rank_policies([self._entry("a", "TRUSTY", ["PASS"])])
        with self.assertRaises(ScorerError):
            rank_policies([self._entry("a", "TRUSTED", ["MAYBE"])])


if __name__ == "__main__":
    unittest.main(verbosity=2)
