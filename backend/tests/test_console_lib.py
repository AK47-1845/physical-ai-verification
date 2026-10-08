"""Console library tests: hunt bool spaces + service presets (stdlib only).

Run from meta bro root:  python backend/tests/test_console_lib.py
Covers the preset registries the 15 new console routes stand on:
preset scorers, fixture policy specs, preset skill contracts,
named property predicates, plus bool-space hardening in hunt.py.
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.hunt import HuntError, grid_search, random_search  # noqa: E402
from engine.property import PropertyError, check_property, get_predicate  # noqa: E402

from backend.eval import policy_fixtures as fixtures  # noqa: E402
from backend.eval.hunt_backends import (  # noqa: E402
    FixtureBackend,
    RedTeamBackend,
    broken_score_fn,
    fixture_policies,
    get_score_preset,
    sane_score_fn,
)
from backend.eval.skill_contracts import SkillContractError, check_skill, get_preset_contract  # noqa: E402


class TestHuntBoolSpaces(unittest.TestCase):
    def _backend(self):
        return FixtureBackend("clean", horizon=16, seed=1)

    def test_grid_bool_value_rejected(self):
        with self.assertRaises(HuntError):
            grid_search(self._backend(), {"bias": [True], "noise_scale": [1.0]},
                        seed=1, trial_cap=2)

    def test_random_bool_bound_rejected(self):
        with self.assertRaises(HuntError):
            random_search(self._backend(),
                          {"bias": [True, 1.0], "noise_scale": [0.5, 1.5]},
                          seed=1, trial_cap=2)

    def test_valid_spaces_still_run(self):
        grid = grid_search(self._backend(),
                           {"bias": [0.0], "noise_scale": [1.0]},
                           seed=1, trial_cap=2)
        self.assertEqual(len(grid["trials"]), 1)
        rand = random_search(self._backend(),
                             {"bias": [0.0, 0.5], "noise_scale": [0.5, 1.5]},
                             seed=1, trial_cap=2)
        self.assertEqual(len(rand["trials"]), 2)


class TestScorePresets(unittest.TestCase):
    def test_unknown_preset_raises(self):
        with self.assertRaises(HuntError):
            get_score_preset("evil")
        with self.assertRaises(HuntError):
            get_score_preset(["sane"])

    def test_broken_always_trusted(self):
        out = broken_score_fn([[0, 0]], [[0, 0]], [[0, 0]], [])
        self.assertEqual(out, {"label": "TRUSTED"})

    def test_sane_verdicts(self):
        acts = fixtures.reference_actions(horizon=16)
        clean = fixtures.clean_rollout(acts, seed=1)
        moved = fixtures.clean_rollout(fixtures.probe_actions(acts),
                                       seed=1)
        out = sane_score_fn(clean, acts, moved, [])
        self.assertEqual(out, {"label": "TRUSTED"})
        tape = fixtures.playback_rollout(acts)
        taped = fixtures.playback_rollout(fixtures.probe_actions(acts))
        out = sane_score_fn(tape, acts, taped, [])
        self.assertEqual(out, {"label": "BLOCKED"})

    def test_sane_empty_trace_raises(self):
        with self.assertRaises(HuntError):
            sane_score_fn([], [[0, 0]], [[0, 0]], [])


class TestFixturePolicies(unittest.TestCase):
    def test_valid_build(self):
        policies = fixture_policies([{"id": "clean", "must_block": False},
                                     {"id": "playback",
                                      "must_block": True}])
        self.assertEqual(sorted(policies), ["clean", "playback"])
        self.assertTrue(policies["playback"]["must_block"])

    def test_bad_specs_raise(self):
        with self.assertRaises(HuntError):
            fixture_policies([])
        with self.assertRaises(HuntError):
            fixture_policies([{"id": "nope", "must_block": True}])
        with self.assertRaises(HuntError):
            fixture_policies([{"id": ["clean"], "must_block": True}])
        with self.assertRaises(HuntError):
            fixture_policies([{"id": "clean", "must_block": True},
                              {"id": "clean", "must_block": False}])
        with self.assertRaises(HuntError):
            fixture_policies([{"id": "clean", "must_block": 1}])
        with self.assertRaises(HuntError):
            fixture_policies([["clean"]])

    def test_redteam_broken_finds_breaks(self):
        policies = fixture_policies([{"id": "clean", "must_block": False},
                                     {"id": "playback",
                                      "must_block": True}])
        backend = RedTeamBackend(policies, broken_score_fn, horizon=16,
                                 seed=1)
        cat = grid_search(backend, {"policy_idx": [0, 1],
                                    "noise_scale": [1.0]},
                          seed=1, trial_cap=4)
        self.assertEqual(len(cat["breaks"]), 1)
        self.assertEqual(cat["breaks"][0]["params"]["policy_idx"], 1.0)

    def test_redteam_sane_zero_hits(self):
        policies = fixture_policies([{"id": "clean", "must_block": False},
                                     {"id": "playback",
                                      "must_block": True}])
        backend = RedTeamBackend(policies, sane_score_fn, horizon=16,
                                 seed=1)
        cat = grid_search(backend, {"policy_idx": [0, 1],
                                    "noise_scale": [1.0]},
                          seed=1, trial_cap=4)
        self.assertEqual(cat["breaks"], [])


class TestPresetContracts(unittest.TestCase):
    def test_unknown_preset_raises(self):
        with self.assertRaises(SkillContractError):
            get_preset_contract("teleport")
        with self.assertRaises(SkillContractError):
            get_preset_contract(None)

    def test_grasp_holds_and_violates(self):
        contract = get_preset_contract("grasp")
        self.assertEqual(sorted(contract), ["post", "pre", "skill_id"])
        held = check_skill(contract, [{"gripper_open": True,
                                       "holding": False},
                                      {"gripper_open": True,
                                       "holding": True}])
        self.assertTrue(held["holds"])
        dropped = check_skill(contract, [{"gripper_open": False,
                                          "holding": False},
                                         {"gripper_open": True,
                                          "holding": True}])
        self.assertFalse(dropped["holds"])
        self.assertFalse(dropped["pre"])

    def test_release_mirror(self):
        contract = get_preset_contract("release")
        held = check_skill(contract, [{"gripper_open": False,
                                       "holding": True},
                                      {"gripper_open": True,
                                       "holding": False}])
        self.assertTrue(held["holds"])


class TestPresetPredicates(unittest.TestCase):
    def test_unknown_predicate_raises(self):
        with self.assertRaises(PropertyError):
            get_predicate("vibes")
        with self.assertRaises(PropertyError):
            get_predicate(5)

    def test_clearance_margins(self):
        pred = get_predicate("clearance")
        self.assertEqual(pred["version"], "clearance/v1")
        spec = {"op": "always", "predicate": pred["fn"],
                "name": "stay-clear", "version": pred["version"]}
        out = check_property(spec, [{"clearance": 0.5},
                                    {"clearance": 0.2}])
        self.assertTrue(out["satisfied"])
        self.assertAlmostEqual(out["margin"], 0.2)
        out = check_property(spec, [{"clearance": 0.5},
                                    {"clearance": -0.1}])
        self.assertFalse(out["satisfied"])

    def test_speed_cap_and_bool_margin(self):
        pred = get_predicate("speed_cap_2")
        spec = {"op": "always", "predicate": pred["fn"],
                "name": "speed-cap", "version": pred["version"]}
        out = check_property(spec, [{"speed": 1.0}, {"speed": 1.5}])
        self.assertTrue(out["satisfied"])
        self.assertAlmostEqual(out["margin"], 0.5)
        with self.assertRaises(PropertyError):
            check_property(spec, [{"speed": True}])


if __name__ == "__main__":
    unittest.main(verbosity=2)
