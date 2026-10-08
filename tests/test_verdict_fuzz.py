"""Verdict hardening fuzz (Block 2): poison matrix + safety monotonicity.

Run from meta bro root:  python tests/test_verdict_fuzz.py
Seeded (Random(1234)). Rule: poison inputs either raise the designated
input-error (a ValueError) or resolve to a non-PASS verdict. Raw
TypeErrors/KeyErrors/AttributeErrors must never escape; bools are
never silently numeric.
"""

import os
import random
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.ci import bootstrap_ci  # noqa: E402
from engine.drift import drift_series, summarize  # noqa: E402
from engine.frechet import discrete_frechet  # noqa: E402
from engine.guard import check_chunk  # noqa: E402
from engine.property import check_property  # noqa: E402
from engine.scorer import evaluate_gate, evaluate_scorecard, rank_policies  # noqa: E402
from engine.sensitivity import action_sensitivity  # noqa: E402
from engine.verdict import (  # noqa: E402
    BLOCKED,
    INSUFFICIENT,
    PASS,
    REVIEW,
    TRUSTED,
    band_for,
    decide,
    verdict_badge,
)

from backend.eval.failure_modes import (  # noqa: E402
    drift_gate,
    executability_proxy,
    sim_real_gap,
)

NAN = float("nan")
INF = float("inf")
POISON = [NAN, INF, -INF, None, "", "1", [], {}, True, False]
EDGE_VALID = [0, -0.0, 1e308, 5e-324]


def _mult():
    """Trial multiplier (VV_FUZZ_MULT=10 for B11 depth). Capped."""
    try:
        return min(max(1, int(os.environ.get("VV_FUZZ_MULT", "1"))),
                   100)
    except ValueError:
        return 1


MULT = _mult()


def raises_valueerror(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except ValueError:
        return True
    except Exception:
        return False
    return False


class TestPoisonMatrix(unittest.TestCase):
    def test_band_for(self):
        for bad in POISON:
            self.assertTrue(
                raises_valueerror(band_for, bad, 0.5, 1.0),
                f"band_for({bad!r}) must raise, not band silently")
            self.assertTrue(
                raises_valueerror(band_for, 0.1, bad, 1.0),
                f"band_for green={bad!r} must raise")
            self.assertTrue(
                raises_valueerror(band_for, 0.1, 0.5, bad),
                f"band_for amber={bad!r} must raise")
        self.assertEqual(band_for(0, 0.5, 1.0), "green")
        self.assertEqual(band_for(1e308, 0.5, 1.0), "red")

    def test_decide(self):
        for bad in [None, 5, "x", [("g", "BOGUS")], [5], [("g",)],
                    [("g", "PASS", "x")], [(None, "PASS")], [(5, "PASS")],
                    [("", "PASS")]]:
            self.assertTrue(
                raises_valueerror(decide, bad),
                f"decide({bad!r}) must raise ValueError")
        label, _, _ = decide([])
        self.assertEqual(label, REVIEW)

    def test_evaluate_gate(self):
        for bad in POISON:
            self.assertTrue(
                raises_valueerror(evaluate_gate, "g", bad, green=0.5,
                                  amber=1.0, evidence="ev"),
                f"measurement={bad!r} must raise")
            self.assertTrue(
                raises_valueerror(evaluate_gate, "g", 0.1, green=bad,
                                  amber=1.0, evidence="ev"),
                f"green={bad!r} must raise")
        for bad_min in [True, -1, 2.5, "3"]:
            self.assertTrue(
                raises_valueerror(evaluate_gate, "g", 0.1, green=0.5,
                                  amber=1.0, evidence="ev", min_n=bad_min,
                                  n=5),
                f"min_n={bad_min!r} must raise")
        for bad_n in [True, 2.5, "3"]:
            self.assertTrue(
                raises_valueerror(evaluate_gate, "g", 0.1, green=0.5,
                                  amber=1.0, evidence="ev", min_n=3,
                                  n=bad_n),
                f"n={bad_n!r} must raise")
        out = evaluate_gate("g", 0.1, green=0.5, amber=1.0,
                            evidence="ev", min_n=0, n=-1)
        self.assertEqual(out["status"], INSUFFICIENT)

    def test_evaluate_scorecard_shapes(self):
        good = {"gate": "g", "measurement": 0.1, "band": "green",
                "status": "PASS", "evidence": "ev"}
        for bad in [None, 5, "x", [5], [{"gate": "g"}],
                    [{"status": "PASS"}], [{"gate": 5, "status": "PASS"},
                                           ],
                    [{"gate": "", "status": "PASS"}],
                    [{"gate": "g", "status": "BOGUS"}]]:
            self.assertTrue(
                raises_valueerror(evaluate_scorecard, bad,
                                  profile_version="1.0", seed=1),
                f"gate_dicts={bad!r} must raise ScorerError")
        for bad_seed in [True, {"x": 1}, ["s"], 2.5]:
            self.assertTrue(
                raises_valueerror(evaluate_scorecard, [dict(good)],
                                  profile_version="1.0", seed=bad_seed),
                f"seed={bad_seed!r} must raise")
        for bad_prof in ["", 5, None]:
            self.assertTrue(
                raises_valueerror(evaluate_scorecard, [dict(good)],
                                  profile_version=bad_prof, seed=1),
                f"profile_version={bad_prof!r} must raise")
        out = evaluate_scorecard([dict(good)], profile_version="1.0",
                                 seed="s-1")
        self.assertEqual(out["payload"]["verdict"], "TRUSTED")

    def test_verdict_badge(self):
        for bad in ["PASS", "nope", None, True, 5]:
            self.assertEqual(raises_valueerror(verdict_badge, bad), True)

    def test_bootstrap_ci(self):
        for bad in POISON:
            self.assertTrue(
                raises_valueerror(bootstrap_ci, [bad], seed=1),
                f"values=[{bad!r}] must raise")
        for bad in [None, True, 5.5, ["s"]]:
            self.assertTrue(
                raises_valueerror(bootstrap_ci, [1.0], seed=bad),
                f"seed={bad!r} must raise")
        for bad in [0, 1, -0.5, True, "x"]:
            self.assertTrue(
                raises_valueerror(bootstrap_ci, [1.0], seed=1, alpha=bad),
                f"alpha={bad!r} must raise")
        for bad in [0, -3, True, 2.5]:
            self.assertTrue(
                raises_valueerror(bootstrap_ci, [1.0], seed=1,
                                  resamples=bad),
                f"resamples={bad!r} must raise")

    def test_drift_family(self):
        good = [[0.0, 0.0], [1.0, 0.0]]
        for bad in [NAN, INF, -1, True, "x", None]:
            self.assertTrue(
                raises_valueerror(drift_gate, good, good, threshold=bad),
                f"threshold={bad!r} must raise")
        for bad in [True, 0, 2.5, "3"]:
            self.assertTrue(
                raises_valueerror(drift_gate, good, good, threshold=0.5,
                                  breach_run=bad),
                f"breach_run={bad!r} must raise")
        self.assertEqual(raises_valueerror(
            drift_series, [[NAN, 0.0]], good), True)
        self.assertEqual(raises_valueerror(summarize, []), True)
        self.assertEqual(raises_valueerror(summarize, [1.0, NAN]), True)

    def test_fm2_fm5(self):
        good = [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [3.0, 0.0]]
        self.assertEqual(raises_valueerror(
            executability_proxy, [[NAN, 0.0]] * 4), True)
        for bad_bounds in [(NAN, 1.0), (0.0, 0.0), True, "x", None]:
            self.assertTrue(
                raises_valueerror(executability_proxy, good,
                                  bounds=bad_bounds),
                f"bounds={bad_bounds!r} must raise")
        self.assertEqual(raises_valueerror(sim_real_gap, [[True, 0.0]],
                                          good), True)
        self.assertEqual(raises_valueerror(discrete_frechet, [], good), True)

    def test_guard(self):
        pos = [[0.0, 0.0], [0.1, 0.0]]
        lim = {"position": [[-1.0, 1.0], [-1.0, 1.0]]}
        self.assertEqual(raises_valueerror(
            check_chunk, [[NAN, 0.0], [0.0, 0.0]], lim, dt=0.1), True)
        self.assertEqual(raises_valueerror(check_chunk, pos, lim, dt=True), True)
        self.assertEqual(raises_valueerror(check_chunk, pos, lim, dt=0), True)
        self.assertEqual(raises_valueerror(check_chunk, pos, ["x"], dt=0.1), True)
        self.assertEqual(raises_valueerror(
            check_chunk, pos, {"position": [[-1.0, 1.0]], "typo": 1},
            dt=0.1), True)

    def test_sensitivity(self):
        pred = lambda z, a: [float(sum(a))]  # noqa: E731
        self.assertEqual(raises_valueerror(
            action_sensitivity, "nope", 0, [1.0, 2.0], seed=1), True)
        self.assertEqual(raises_valueerror(
            action_sensitivity, pred, 0, [1.0, 2.0], seed=True), True)
        self.assertEqual(raises_valueerror(
            action_sensitivity, pred, 0, [1.0, 2.0], seed=1,
            threshold=NAN), True)
        self.assertEqual(raises_valueerror(
            action_sensitivity, pred, 0, [1.0, NAN], seed=1), True)

    def test_property(self):
        spec = {"op": "always", "predicate": lambda s: 1.0,
                "name": "n", "version": "v"}
        self.assertEqual(raises_valueerror(check_property, 5, [{"a": 1}]), True)
        self.assertEqual(raises_valueerror(
            check_property, dict(spec), [{"a": 1}], state_origin="x"), True)
        self.assertEqual(raises_valueerror(
            check_property, dict(spec, op="never"), [{"a": 1}]), True)
        self.assertEqual(raises_valueerror(
            check_property, dict(spec, window=[True, 1]), [{"a": 1}]), True)
        nan_spec = dict(spec, predicate=lambda s: NAN)
        self.assertEqual(raises_valueerror(
            check_property, nan_spec, [{"a": 1}]), True)
        bool_spec = dict(spec, predicate=lambda s: True)
        self.assertEqual(raises_valueerror(
            check_property, bool_spec, [{"a": 1}]), True)

    def test_rank(self):
        entry = {"policy_id": "p", "verdict": "TRUSTED",
                 "gates": [{"status": "PASS"}]}
        self.assertEqual(raises_valueerror(rank_policies, []), True)
        self.assertEqual(raises_valueerror(
            rank_policies, [dict(entry, policy_id="")]), True)
        self.assertEqual(raises_valueerror(
            rank_policies, [dict(entry, verdict="MAYBE")]), True)
        self.assertEqual(raises_valueerror(
            rank_policies, [dict(entry, gates=[{"status": "WEIRD"}])]), True)


class TestTinyNBoundaries(unittest.TestCase):
    def gate(self, n):
        return evaluate_gate("g", 0.1, green=0.5, amber=1.0,
                             evidence="ev", min_n=3, n=n)

    def test_boundaries(self):
        self.assertEqual(self.gate(2)["status"], INSUFFICIENT)
        self.assertEqual(self.gate(3)["status"], PASS)
        self.assertEqual(self.gate(4)["status"], PASS)
        self.assertEqual(self.gate(0)["status"], INSUFFICIENT)
        self.assertEqual(self.gate(-1)["status"], INSUFFICIENT)
        self.assertIn("grey", self.gate(2)["band"])


class TestSafetyMonotonic(unittest.TestCase):
    RANK = {TRUSTED: 0, REVIEW: 1, INSUFFICIENT: 1, BLOCKED: 2}

    def verdict_of(self, safety_m, success_m):
        safety = evaluate_gate("safety", safety_m, green=0.5, amber=1.0,
                               evidence="ev")
        success = evaluate_gate("success", success_m, green=0.5,
                                amber=0.8, evidence="ev",
                                higher_is_better=True)
        label, _, _ = decide([(g["gate"], g["status"])
                              for g in (safety, success)])
        return label

    def test_worse_safety_never_improves(self):
        rng = random.Random(1234)
        for _ in range(2000 * MULT):
            base = rng.uniform(0.0, 2.0)
            worse = base + rng.uniform(0.0, 1.0)
            success = rng.uniform(0.0, 1.0)
            before = self.RANK[self.verdict_of(base, success)]
            after = self.RANK[self.verdict_of(worse, success)]
            self.assertGreaterEqual(after, before)

    def test_success_cannot_lift_blocked(self):
        rng = random.Random(1234)
        for _ in range(2000 * MULT):
            success = rng.uniform(0.9, 1.0)
            self.assertEqual(self.verdict_of(5.0, success), BLOCKED)

    def test_order_independent(self):
        gates = [
            {"gate": "a", "measurement": 0.1, "band": "green",
             "status": "PASS", "evidence": "ev"},
            {"gate": "b", "measurement": 0.9, "band": "amber",
             "status": "REVIEW", "evidence": "ev"},
            {"gate": "c", "measurement": 2.0, "band": "red",
             "status": "BLOCKED", "evidence": "ev"}]
        rng = random.Random(1234)
        first = decide([(g["gate"], g["status"]) for g in gates])
        for _ in range(100 * MULT):
            shuffled = list(gates)
            rng.shuffle(shuffled)
            now = decide([(g["gate"], g["status"]) for g in shuffled])
            self.assertEqual(now[0], first[0])
            self.assertEqual(now[1], first[1])
            self.assertEqual(sorted(now[2]), sorted(first[2]))

    def test_multi_seed_monotonic(self):
        # B11 durable depth: the monotonic core over 10 fixed seeds.
        for seed in range(1234, 1244):
            rng = random.Random(seed)
            for _ in range(2000):
                base = rng.uniform(0.0, 2.0)
                worse = base + rng.uniform(0.0, 1.0)
                success = rng.uniform(0.0, 1.0)
                before = self.RANK[self.verdict_of(base, success)]
                after = self.RANK[self.verdict_of(worse, success)]
                self.assertGreaterEqual(after, before)

    def test_edge_valid_numbers_band_right(self):
        for value in EDGE_VALID:
            out = evaluate_gate("g", value, green=0.5, amber=1.0,
                                evidence="ev")
            want = ("green" if value < 0.5 else
                    "amber" if value < 1.0 else "red")
            self.assertEqual(out["band"], want)


if __name__ == "__main__":
    unittest.main(verbosity=2)
