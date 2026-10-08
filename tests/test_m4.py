"""M4 tests: hunt backends, grid/random search, catalogue summary.

Run from meta bro root:  python tests/test_m4.py
(runs under unittest and pytest alike; stdlib only)
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.hunt import (  # noqa: E402
    HuntError,
    grid_search,
    random_search,
    refine_search,
    seal_trials,
    summarize,
)


class ThresholdBackend:
    """Breaks iff params['x'] > 0.5. Deterministic oracle for tests."""

    def evaluate(self, params):
        x = params["x"]
        return {"breaks": x > 0.5, "measurement": x}


class TestGridSearch(unittest.TestCase):
    def test_finds_seeded_break(self):
        cat = grid_search(ThresholdBackend(), {"x": [0.0, 0.5, 1.0]},
                          seed=4, trial_cap=10)
        self.assertEqual(len(cat["trials"]), 3)
        self.assertTrue(cat["exhausted"])
        self.assertEqual(len(cat["breaks"]), 1)
        self.assertEqual(cat["breaks"][0]["params"], {"x": 1.0})

    def test_cap_truncates(self):
        cat = grid_search(ThresholdBackend(), {"x": [0.0, 0.5, 1.0]},
                          seed=4, trial_cap=2)
        self.assertEqual(len(cat["trials"]), 2)
        self.assertFalse(cat["exhausted"])
        self.assertEqual(cat["breaks"], [])

    def test_two_dim_product_order(self):
        seen = []
        # canonical order = sorted names; spot-check via params echo below
        class Echo:
            def evaluate(self, params):
                seen.append((params["a"], params["b"]))
                return {"breaks": False, "measurement": 0.0}
        grid_search(Echo(), {"b": [0.0, 1.0], "a": [0.0, 1.0]},
                    seed=1, trial_cap=4)
        self.assertEqual(seen, [(0.0, 0.0), (0.0, 1.0),
                                (1.0, 0.0), (1.0, 1.0)])

    def test_bad_space_raises(self):
        with self.assertRaises(HuntError):
            grid_search(ThresholdBackend(), {}, seed=1, trial_cap=5)
        with self.assertRaises(HuntError):
            grid_search(ThresholdBackend(), {"x": []}, seed=1, trial_cap=5)
        with self.assertRaises(HuntError):
            grid_search(ThresholdBackend(), {"x": [0.0]}, seed=1,
                        trial_cap=0)


class TestRandomSearch(unittest.TestCase):
    def test_seeded_determinism(self):
        kw = {"space": {"x": (0.0, 1.0)}, "seed": 9, "trial_cap": 25}
        a = random_search(ThresholdBackend(), **kw)
        b = random_search(ThresholdBackend(), **kw)
        self.assertEqual(a, b)

    def test_bounds_respected(self):
        cat = random_search(ThresholdBackend(),
                            {"x": (0.25, 0.75), "y": (-1.0, 1.0)},
                            seed=2, trial_cap=50)
        for trial in cat["trials"]:
            self.assertTrue(0.25 <= trial["params"]["x"] <= 0.75)
            self.assertTrue(-1.0 <= trial["params"]["y"] <= 1.0)

    def test_bad_bounds_raise(self):
        with self.assertRaises(HuntError):
            random_search(ThresholdBackend(), {"x": (1.0, 0.0)},
                          seed=1, trial_cap=5)
        with self.assertRaises(HuntError):
            random_search(ThresholdBackend(), {"x": (0.0,)},
                          seed=1, trial_cap=5)


class TestBackendContract(unittest.TestCase):
    def test_garbage_result_raises(self):
        class Bad:
            def evaluate(self, params):
                return {"breaks": "yes"}
        with self.assertRaises(HuntError):
            grid_search(Bad(), {"x": [0.0]}, seed=1, trial_cap=1)

    def test_raising_backend_wrapped(self):
        class Boom:
            def evaluate(self, params):
                raise RuntimeError("sim exploded")
        with self.assertRaises(HuntError):
            grid_search(Boom(), {"x": [0.0]}, seed=1, trial_cap=1)

    def test_summarize(self):
        cat = grid_search(ThresholdBackend(), {"x": [0.0, 1.0]},
                          seed=1, trial_cap=10)
        summary = summarize(cat)
        self.assertEqual((summary["trials"], summary["breaks"]), (2, 1))
        self.assertEqual(summary["break_rate"], 0.5)
        self.assertEqual(summary["worst"]["params"], {"x": 1.0})


class TestRefine(unittest.TestCase):
    def test_zooms_around_break(self):
        coarse = grid_search(ThresholdBackend(), {"x": [0.0, 1.0]},
                             seed=1, trial_cap=10)
        breaks = [t["params"] for t in coarse["breaks"]]
        self.assertEqual(breaks, [{"x": 1.0}])
        fine = refine_search(ThresholdBackend(), breaks,
                             {"x": (0.0, 1.0)}, seed=1, trial_cap=10,
                             zoom=0.25, subdiv=3)
        self.assertEqual(fine["mode"], "refine")
        self.assertEqual(fine["refined_from"], 1)
        pts = [t["params"]["x"] for t in fine["trials"]]
        self.assertEqual(pts, [0.875, 1.0])
        self.assertTrue(all(t["breaks"] for t in fine["trials"]))
        self.assertTrue(all(t["parent"] == 0 for t in fine["trials"]))
        self.assertTrue(fine["exhausted"])

    def test_deterministic(self):
        kw = {"breaks": [{"x": 0.75}], "ranges": {"x": (0.0, 1.0)},
              "seed": 3, "trial_cap": 20, "zoom": 0.5, "subdiv": 4}
        self.assertEqual(refine_search(ThresholdBackend(), **kw),
                         refine_search(ThresholdBackend(), **kw))

    def test_cap_truncates(self):
        fine = refine_search(ThresholdBackend(), [{"x": 0.75}],
                             {"x": (0.0, 1.0)}, seed=1, trial_cap=1,
                             zoom=0.5, subdiv=4)
        self.assertEqual(len(fine["trials"]), 1)
        self.assertFalse(fine["exhausted"])

    def test_bad_inputs_raise(self):
        good_ranges = {"x": (0.0, 1.0)}
        with self.assertRaises(HuntError):
            refine_search(ThresholdBackend(), [], good_ranges,
                          seed=1, trial_cap=5)
        with self.assertRaises(HuntError):
            refine_search(ThresholdBackend(), [{"y": 0.5}],
                          good_ranges, seed=1, trial_cap=5)
        with self.assertRaises(HuntError):
            refine_search(ThresholdBackend(), [{"x": 0.5}],
                          {"x": (1.0, 0.0)}, seed=1, trial_cap=5)
        for bad_zoom in (0.0, 1.0, -0.1, True, "near"):
            with self.assertRaises(HuntError):
                refine_search(ThresholdBackend(), [{"x": 0.5}],
                              good_ranges, seed=1, trial_cap=5,
                              zoom=bad_zoom)
        for bad_sub in (1, 0, True, 2.5):
            with self.assertRaises(HuntError):
                refine_search(ThresholdBackend(), [{"x": 0.5}],
                              good_ranges, seed=1, trial_cap=5,
                              subdiv=bad_sub)


class TestSeed(unittest.TestCase):
    def test_bool_seeds_rejected(self):
        with self.assertRaises(HuntError):
            grid_search(ThresholdBackend(), {"x": [0.0]}, seed=True,
                        trial_cap=1)
        with self.assertRaises(HuntError):
            random_search(ThresholdBackend(), {"x": (0.0, 1.0)},
                          seed=False, trial_cap=1)
        with self.assertRaises(HuntError):
            refine_search(ThresholdBackend(), [{"x": 0.5}],
                          {"x": (0.0, 1.0)}, seed=True, trial_cap=1)

    def test_bytes_seed_accepted(self):
        cat = grid_search(ThresholdBackend(), {"x": [0.0, 1.0]},
                          seed=b"audit", trial_cap=10)
        self.assertEqual(len(cat["trials"]), 2)


class TestSeal(unittest.TestCase):
    def test_seals_hash_params(self):
        cat = grid_search(ThresholdBackend(), {"x": [0.0, 1.0]},
                          seed=1, trial_cap=10)
        sealed = seal_trials(cat)
        self.assertEqual(sealed["trials"], 2)
        for seal in sealed["sealed"]:
            self.assertEqual(len(seal["params_hash"]), 64)
            int(seal["params_hash"], 16)
        self.assertEqual(len(sealed["catalogue_hash"]), 64)
        self.assertEqual([s["breaks"] for s in sealed["sealed"]],
                         [False, True])

    def test_tamper_changes_hash(self):
        cat = grid_search(ThresholdBackend(), {"x": [0.0, 1.0]},
                          seed=1, trial_cap=10)
        before = seal_trials(cat)["catalogue_hash"]
        cat["trials"][0]["breaks"] = True
        after = seal_trials(cat)["catalogue_hash"]
        self.assertNotEqual(before, after)

    def test_bad_catalogue_raises(self):
        with self.assertRaises(HuntError):
            seal_trials({"trials": "nope"})
        with self.assertRaises(HuntError):
            seal_trials({"trials": [{"trial": 0, "params": {"x": 0.0},
                                     "breaks": "yes",
                                     "measurement": 0.0}]})


if __name__ == "__main__":
    unittest.main(verbosity=2)
