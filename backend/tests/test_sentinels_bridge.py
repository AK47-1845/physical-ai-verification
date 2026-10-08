"""Sentinel + bridge tests: collapse math, axiom wrap, seed stamps.

Run from meta bro root:  python backend/tests/test_sentinels_bridge.py
(stdlib only)
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from backend.provenance.axiom_bridge import BridgeError, bridge_generation, seed_stamp  # noqa: E402
from backend.provenance.manifest import verify_manifest  # noqa: E402
from backend.provenance.sentinels import SentinelError, collapse_report  # noqa: E402

# baseline with pinned tails: 90x mid + 5x lo + 5x hi
BASE_COL = [50.0] * 90 + [0.0] * 5 + [100.0] * 5


class TestSentinels(unittest.TestCase):
    def test_identical_is_ok(self):
        report = collapse_report({"x": BASE_COL}, {"x": list(BASE_COL)})
        col = report["columns"]["x"]
        self.assertEqual(col["variance_ratio"], 1.0)
        self.assertEqual(col["tail_mass_ratio"], 1.0)
        self.assertEqual(col["quantile_drift"], 0.0)
        self.assertEqual(col["status"], "OK")
        self.assertEqual(report["overall"], "OK")

    def test_collapsed_variance_is_risk(self):
        report = collapse_report({"x": BASE_COL}, {"x": [50.0] * 100})
        col = report["columns"]["x"]
        self.assertEqual(col["variance_ratio"], 0.0)
        self.assertEqual(col["status"], "COLLAPSE_RISK")
        self.assertEqual(report["overall"], "COLLAPSE_RISK")

    def test_missing_column_insufficient(self):
        report = collapse_report({"x": BASE_COL}, {})
        self.assertEqual(report["columns"]["x"]["status"], "INSUFFICIENT")
        self.assertEqual(report["overall"], "INSUFFICIENT")

    def test_single_point_insufficient(self):
        report = collapse_report({"x": [5.0]}, {"x": [5.0]})
        self.assertEqual(report["columns"]["x"]["status"], "INSUFFICIENT")

    def test_deterministic(self):
        kw = {"baseline": {"x": BASE_COL}, "current": {"x": [50.0] * 100}}
        self.assertEqual(collapse_report(**kw), collapse_report(**kw))

    def test_bad_inputs_raise(self):
        with self.assertRaises(SentinelError):
            collapse_report({}, {"x": [1.0]})
        with self.assertRaises(SentinelError):
            collapse_report({"x": [1.0, float("nan")]}, {"x": [1.0]})

    def test_bool_values_and_floors_rejected(self):
        with self.assertRaises(SentinelError):
            collapse_report({"x": [1.0, True]}, {"x": [1.0, 2.0]})
        with self.assertRaises(SentinelError):
            collapse_report({1: [1.0, 2.0]}, {"x": [1.0, 2.0]})
        with self.assertRaises(SentinelError):
            collapse_report({"x": [1.0, 2.0]}, {"x": [1.0, 2.0]},
                            var_floor=True)

    def test_unscored_current_columns_listed(self):
        report = collapse_report({"x": BASE_COL},
                                 {"x": list(BASE_COL), "y": [1.0],
                                  5: [2.0]})
        self.assertEqual(report["overall"], "OK")
        self.assertEqual(set(report["unscored_current_columns"]), {5, "y"})


class TestBridge(unittest.TestCase):
    def _run(self, **kw):
        args = {"generator_name": "axiom-tabular",
                "generator_version": "0.3.0", "seed": 42, "n_rows": 500,
                "content_hash": "c" * 64,
                "real_ingredients": [{"kind": "real", "n_rows": 1000,
                                      "content_hash": "d" * 64}]}
        args.update(kw)
        return bridge_generation(**args)

    def test_bridge_ok(self):
        out = self._run(axiom_datacard={"title": "axiom card"})
        self.assertTrue(verify_manifest(out["manifest"])["ok"])
        self.assertEqual(out["mix_batch"]["n_rows"], 500)
        self.assertEqual(out["mix_batch"]["manifest_id"],
                         out["manifest"]["manifest_id"])
        self.assertEqual(out["axiom_datacard"]["title"], "axiom card")

    def test_no_real_source_rejected(self):
        with self.assertRaises(BridgeError):
            self._run(real_ingredients=[])

    def test_generation_identity_is_hash_bound_without_mutating_inputs(self):
        params = {"temperature": 0.2}
        out = self._run(model_id="fixture-vla", model_version="0.1", batch_id="batch-001", generator_params=params)
        lineage = out["manifest"]["body"]["generator"]["params"]["lineage"]
        self.assertEqual(lineage, {"model_id": "fixture-vla", "model_version": "0.1", "batch_id": "batch-001"})
        self.assertEqual(params, {"temperature": 0.2})
        self.assertTrue(verify_manifest(out["manifest"])["ok"])
        changed = self._run(model_id="fixture-vla", model_version="0.2", batch_id="batch-001")
        self.assertNotEqual(out["manifest"]["manifest_id"], changed["manifest"]["manifest_id"])
        lineage["model_version"] = "tampered"
        self.assertFalse(verify_manifest(out["manifest"])["ok"])

    def test_generation_identity_requires_complete_bounded_strings(self):
        for values in ({"model_id": "model"}, {"model_version": "v1"}, {"batch_id": True}, {"model_id": "x" * 129, "model_version": "1"}):
            with self.assertRaises(BridgeError):
                self._run(**values)

    def test_bad_hash_rejected(self):
        with self.assertRaises(BridgeError):
            self._run(content_hash="nope")

    def test_non_dict_params_rejected(self):
        for bad in ([], 0, "x"):
            with self.assertRaises(BridgeError, msg=bad):
                self._run(generator_params=bad)

    def test_seed_stamp(self):
        self.assertEqual(seed_stamp(42, 7), seed_stamp(42, 7))
        self.assertNotEqual(seed_stamp(42, 7), seed_stamp(42, 8))
        self.assertNotEqual(seed_stamp(42, 7), seed_stamp(43, 7))
        self.assertEqual(len(seed_stamp(1, 1)), 12)
        with self.assertRaises(BridgeError):
            seed_stamp(1, -1)
        with self.assertRaises(BridgeError):
            seed_stamp(True, 1)
        with self.assertRaises(BridgeError):
            seed_stamp(1, True)
        with self.assertRaises(BridgeError):
            self._run(seed=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
