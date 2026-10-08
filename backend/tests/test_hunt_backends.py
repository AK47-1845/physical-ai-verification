"""Hunt backend tests: fixture falsification + FR-36 red-team.

Run from meta bro root:  python backend/tests/test_hunt_backends.py
(stdlib only)
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.hunt import HuntError, grid_search  # noqa: E402

from backend.eval import policy_fixtures as fixtures  # noqa: E402
from backend.eval.failure_modes import drift_gate  # noqa: E402
from backend.eval.hunt_backends import FixtureBackend, RedTeamBackend  # noqa: E402


def sane_score(pred, ref, probed, seeds):
    """Sane scorer: drift breach or dead probe => BLOCKED else TRUSTED.

    pred/probed are the nominal/moved pair already (same seed), so the
    probe response is their normalized difference, directly.
    """
    drift = drift_gate(ref, pred, threshold=0.5)
    diffs = [sum((a - b) ** 2 for a, b in zip(p, q))
             for p, q in zip(pred, probed)]
    raw = sum(diffs) / len(diffs)
    energy = sum(v * v for row in pred for v in row) / len(pred) + 1e-9
    responsive = (raw / energy) > 0.01
    _ = seeds
    if drift["breach"] or not responsive:
        return {"label": "BLOCKED"}
    return {"label": "TRUSTED"}


def broken_score(pred, ref, probed, seeds):
    """Deliberately broken scorer: TRUSTED no matter what."""
    _ = (pred, ref, probed, seeds)
    return {"label": "TRUSTED"}


POLICIES = {
    "clean": {"rollout": lambda a, s, n: fixtures.clean_rollout(
        a, seed=s, noise_scale=n), "must_block": False},
    "playback": {"rollout": lambda a, s, n: fixtures.playback_rollout(a),
                 "must_block": True},
}


class TestFixtureBackend(unittest.TestCase):
    def test_deterministic(self):
        backend = FixtureBackend("clean", horizon=32, seed=4)
        params = {"noise_scale": 1.0, "bias": 0.1}
        self.assertEqual(backend.evaluate(params), backend.evaluate(params))

    def test_playback_always_breaks(self):
        backend = FixtureBackend("playback", horizon=32, seed=1)
        out = backend.evaluate({"noise_scale": 1.0, "bias": 0.0})
        self.assertTrue(out["breaks"])

    def test_clean_silent_holds(self):
        backend = FixtureBackend("clean", horizon=32, seed=1)
        out = backend.evaluate({"noise_scale": 0.0, "bias": 0.0})
        self.assertFalse(out["breaks"])

    def test_grid_finds_break(self):
        backend = FixtureBackend("playback", horizon=32, seed=1)
        cat = grid_search(backend,
                          {"noise_scale": [0.0, 1.0], "bias": [0.0, 0.2]},
                          seed=1, trial_cap=4)
        self.assertEqual(len(cat["breaks"]), 4)

    def test_bad_params_raise(self):
        backend = FixtureBackend("clean", horizon=32, seed=1)
        with self.assertRaises(HuntError):
            backend.evaluate({"noise_scale": 1.0})
        with self.assertRaises(HuntError):
            backend.evaluate({"noise_scale": -1.0, "bias": 0.0})

    def test_unknown_policy_raises(self):
        with self.assertRaises(HuntError):
            FixtureBackend("nope")

    def test_bool_seed_and_params_and_policy_rejected(self):
        with self.assertRaises(HuntError):
            FixtureBackend("clean", seed=True)
        with self.assertRaises(HuntError):
            FixtureBackend("clean", horizon=True)
        backend = FixtureBackend("clean", seed=1)
        with self.assertRaises(HuntError):
            backend.evaluate({"bias": True, "noise_scale": 1.0})
        with self.assertRaises(HuntError):
            backend.evaluate([("bias", 0.0)])
        with self.assertRaises(HuntError):
            FixtureBackend(True)


class TestRedTeam(unittest.TestCase):
    SPACE = {"policy_idx": [0, 1], "noise_scale": [1.0]}

    def test_sane_scorer_zero_hits(self):
        backend = RedTeamBackend(POLICIES, sane_score, horizon=32, seed=1)
        cat = grid_search(backend, self.SPACE, seed=1, trial_cap=4)
        self.assertEqual(cat["breaks"], [])

    def test_broken_scorer_caught(self):
        backend = RedTeamBackend(POLICIES, broken_score, horizon=32, seed=1)
        cat = grid_search(backend, self.SPACE, seed=1, trial_cap=4)
        self.assertEqual(len(cat["breaks"]), 1)
        hit = cat["breaks"][0]
        self.assertEqual(hit["measurement"], 1.0)

    def test_bad_index_raises(self):
        backend = RedTeamBackend(POLICIES, sane_score, horizon=32, seed=1)
        with self.assertRaises(HuntError):
            backend.evaluate({"policy_idx": 5, "noise_scale": 1.0})

    def test_bad_horizon_raises_hunt_error(self):
        with self.assertRaises(HuntError):
            RedTeamBackend(POLICIES, sane_score, horizon=2)

    def test_bool_seed_and_shape_inputs_rejected(self):
        with self.assertRaises(HuntError):
            RedTeamBackend(POLICIES, sane_score, seed=False)
        with self.assertRaises(HuntError):
            RedTeamBackend(POLICIES, sane_score, horizon=True)
        with self.assertRaises(HuntError):
            RedTeamBackend(5, sane_score)
        with self.assertRaises(HuntError):
            RedTeamBackend({}, sane_score)
        with self.assertRaises(HuntError):
            RedTeamBackend({"a": 5}, sane_score)
        with self.assertRaises(HuntError):
            RedTeamBackend({"a": {"rollout": 5, "must_block": True}},
                           sane_score)
        backend = RedTeamBackend(POLICIES, sane_score, seed=1)
        with self.assertRaises(HuntError):
            backend.evaluate({"policy_idx": True, "noise_scale": 1.0})
        with self.assertRaises(HuntError):
            backend.evaluate({"policy_idx": 0})
        weird = RedTeamBackend(POLICIES, lambda p, d: "TRUSTED", seed=1)
        with self.assertRaises(HuntError):
            weird.evaluate({"policy_idx": 0, "noise_scale": 1.0})


if __name__ == "__main__":
    unittest.main(verbosity=2)
