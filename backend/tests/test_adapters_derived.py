"""FR-42 DERIVED adapter tests: documented-shape ingestion.

Run from meta bro root:  python backend/tests/test_adapters_derived.py
(stdlib only)

Fixtures are hand-built transcriptions of the shapes documented from
each harness's own primaries (URLs + dates in provenance). They test
the PARSER, not the harness: VERIFIED graduation still needs a
recorded real-log run (D-night-11).
"""

import json
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from backend.adapters.ingest import AdapterError, conformance_report, get_adapter  # noqa: E402

LIBERO_DOC = {"framework": "libero", "benchmark": "libero_spatial",
              "task_id": 3, "seed": 100, "env_num": 20, "num_success": 14,
              "success_rate": 0.7, "loss": 0.42}

SIMPLER_DOC = {"framework": "simpler", "task": "pick_coke_can",
               "variant": "visual-matching",
               "episodes": [{"success": True, "steps": 120, "seed": 1},
                            {"success": False, "steps": 200},
                            {"success": True}]}

LEROBOT_DOC = {"task": "libero_spatial", "policy": "smolvla_base",
               "n_episodes": 3,
               "episodes": [{"is_success": True, "episode": 0},
                            {"is_success": True, "episode": 1},
                            {"is_success": False, "episode": 2}]}


class TestLiberoDerived(unittest.TestCase):
    def test_parses_transcription(self):
        out = get_adapter("simpler-libero").parse(dict(LIBERO_DOC))
        self.assertEqual(out["summary"]["successes"], 14)
        self.assertAlmostEqual(out["summary"]["success_rate"], 0.7)
        self.assertEqual(out["records"][0]["kind"], "libero-task")
        self.assertEqual(out["provenance"]["schema_status"], "DERIVED")
        self.assertEqual(out["provenance"]["derived_date"], "2026-10-04")
        self.assertTrue(out["provenance"]["source_urls"])

    def test_accepts_json_text(self):
        out = get_adapter("simpler-libero").parse(json.dumps(LIBERO_DOC))
        self.assertEqual(out["summary"]["n"], 20)

    def test_rate_mismatch_refused(self):
        bad = dict(LIBERO_DOC, success_rate=0.9)
        with self.assertRaises(AdapterError):
            get_adapter("simpler-libero").parse(bad)

    def test_bad_shapes_refused(self):
        base = dict(LIBERO_DOC)
        for key, val in (("benchmark", "libero_500"), ("task_id", -1),
                         ("env_num", 0), ("num_success", 21),
                         ("seed", "100"), ("loss", "low")):
            with self.assertRaises(AdapterError, msg=key):
                get_adapter("simpler-libero").parse(dict(base, **{key: val}))

    def test_bad_framework_refused(self):
        with self.assertRaises(AdapterError):
            get_adapter("simpler-libero").parse({"framework": "robosuite"})
        with self.assertRaises(AdapterError):
            get_adapter("simpler-libero").parse([1, 2])
        with self.assertRaises(AdapterError):
            get_adapter("simpler-libero").parse("{not json")


class TestSimplerDerived(unittest.TestCase):
    def test_parses_episodes(self):
        doc = json.loads(json.dumps(SIMPLER_DOC))
        out = get_adapter("simpler-libero").parse(doc)
        self.assertEqual(out["summary"], {"n": 3, "successes": 2,
                                          "success_rate": 2 / 3})
        self.assertTrue(all(r["kind"] == "simpler-episode"
                            for r in out["records"]))

    def test_strict_bools(self):
        doc = json.loads(json.dumps(SIMPLER_DOC))
        doc["episodes"][0]["success"] = 1
        with self.assertRaises(AdapterError):
            get_adapter("simpler-libero").parse(doc)

    def test_bad_variant_and_empty_refused(self):
        doc = json.loads(json.dumps(SIMPLER_DOC))
        doc["variant"] = "cartoon"
        with self.assertRaises(AdapterError):
            get_adapter("simpler-libero").parse(doc)
        doc["variant"] = "visual-matching"
        doc["episodes"] = []
        with self.assertRaises(AdapterError):
            get_adapter("simpler-libero").parse(doc)


class TestLeRobotDerived(unittest.TestCase):
    def test_parses_episodes(self):
        doc = json.loads(json.dumps(LEROBOT_DOC))
        out = get_adapter("lerobot-eval").parse(doc)
        self.assertEqual(out["summary"]["successes"], 2)
        self.assertAlmostEqual(out["summary"]["success_rate"], 2 / 3)
        self.assertEqual(out["records"][0]["policy"], "smolvla_base")

    def test_count_mismatch_refused(self):
        doc = json.loads(json.dumps(LEROBOT_DOC))
        doc["n_episodes"] = 50
        with self.assertRaises(AdapterError):
            get_adapter("lerobot-eval").parse(doc)

    def test_bad_shapes_refused(self):
        doc = json.loads(json.dumps(LEROBOT_DOC))
        doc["episodes"][1] = {"is_success": "yes"}
        with self.assertRaises(AdapterError):
            get_adapter("lerobot-eval").parse(doc)
        with self.assertRaises(AdapterError):
            get_adapter("lerobot-eval").parse({"task": "x"})
        with self.assertRaises(AdapterError):
            get_adapter("lerobot-eval").parse(42)


class TestStubReasons(unittest.TestCase):
    def test_remaining_stubs_loud(self):
        report = conformance_report()
        by_name = {a["name"]: a for a in report["adapters"]}
        for name in ("isaac-lab-arena", "roboarena", "halos"):
            self.assertEqual(by_name[name]["schema_status"], "STUB")
            self.assertTrue(by_name[name]["stub_reason"])
            with self.assertRaises(AdapterError) as ctx:
                get_adapter(name).parse("{}")
            self.assertIn("UNVERIFIED", str(ctx.exception))
        self.assertEqual(by_name["simpler-libero"]["schema_status"],
                         "DERIVED")
        self.assertIsNone(by_name["simpler-libero"]["stub_reason"])
        self.assertTrue(by_name["simpler-libero"]["source"])
        self.assertTrue(
            by_name["lerobot-eval"]["schema_status"].startswith(
                "VERIFIED:2026-10-06:lerobot@"))
        self.assertIsNone(by_name["lerobot-eval"]["stub_reason"])
        self.assertTrue(by_name["lerobot-eval"]["source"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
