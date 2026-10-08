"""lerobot-eval VERIFIED graduation: native summary fixture + negatives.

Run from meta code new 2.0 root:  python backend/tests/test_lerobot_verified.py
(stdlib only)

Conformance: the recorded fixture file parses to canonical records +
summary + VERIFIED provenance. Negatives: every cross-check refuses
garbage loudly (AdapterError, never a trace).
"""

import json
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from backend.adapters.ingest import AdapterError, get_adapter  # noqa: E402

FIXTURE = os.path.join(BASE, "backend", "adapters", "fixtures",
                       "lerobot-eval", "summary_task.json")


def _fixture():
    with open(FIXTURE, encoding="utf-8") as handle:
        return json.load(handle)


class TestNativeConformance(unittest.TestCase):
    def test_fixture_parses(self):
        out = get_adapter("lerobot-eval").parse(_fixture())
        self.assertEqual(out["summary"]["n"], 10)
        self.assertEqual(out["summary"]["successes"], 6)
        self.assertAlmostEqual(out["summary"]["success_rate"], 0.6)
        self.assertAlmostEqual(out["summary"]["pc_success"], 60.0)
        self.assertEqual(out["summary"]["ci95_source"], "reported")
        self.assertEqual(len(out["records"]), 10)
        self.assertEqual(out["records"][0]["kind"], "lerobot-episode")
        self.assertEqual(out["records"][0]["task_group"], "libero_goal")
        self.assertTrue(out["records"][0]["is_success"])
        self.assertFalse(out["records"][2]["is_success"])

    def test_provenance_verified(self):
        prov = get_adapter("lerobot-eval").parse(_fixture())["provenance"]
        self.assertTrue(prov["schema_status"].startswith(
            "VERIFIED:2026-10-06:lerobot@"))
        self.assertEqual(prov["shape"], "native-summary")
        self.assertEqual(prov["graduated"]["date"], "2026-10-06")
        self.assertIn("summary_task.json",
                      prov["graduated"]["fixture"])
        self.assertIn("pending", prov["review"])
        self.assertEqual(prov["ignored"]["metrics"],
                         ["avg_reward", "max_reward", "video_paths"])

    def test_accepts_json_text(self):
        with open(FIXTURE, encoding="utf-8") as handle:
            text = handle.read()
        out = get_adapter("lerobot-eval").parse(text)
        self.assertEqual(out["summary"]["successes"], 6)

    def test_ci95_computed_when_absent(self):
        doc = _fixture()
        del doc["pc_success_ci95"]
        out = get_adapter("lerobot-eval").parse(doc)
        self.assertEqual(out["summary"]["ci95_source"], "computed")
        lo, hi = out["summary"]["pc_success_ci95"]
        self.assertLess(lo, 60.0)
        self.assertGreater(hi, 60.0)


class TestNativeNegatives(unittest.TestCase):
    def _mutate(self, func):
        doc = _fixture()
        func(doc)
        with self.assertRaises(AdapterError):
            get_adapter("lerobot-eval").parse(doc)

    def test_count_mismatches_refused(self):
        self._mutate(lambda d: d.update(n_episodes=50))
        self._mutate(lambda d: d.update(n_success=7))
        self._mutate(lambda d: d["metrics"]["successes"].pop())

    def test_rate_mismatch_refused(self):
        self._mutate(lambda d: d.update(pc_success=61.0))

    def test_ci95_mismatch_refused(self):
        self._mutate(lambda d: d.update(pc_success_ci95=[30.0, 80.0]))
        self._mutate(lambda d: d.update(pc_success_ci95="narrow"))
        self._mutate(lambda d: d.update(pc_success_ci95=[50.0]))

    def test_strict_types(self):
        self._mutate(lambda d: d["metrics"].update(successes=[1, 0]))
        self._mutate(lambda d: d.update(task_id="3"))
        self._mutate(lambda d: d.update(task_group=""))

    def test_ambiguous_and_garbage_refused(self):
        both = _fixture()
        both["episodes"] = [{"is_success": True}]
        with self.assertRaises(AdapterError):
            get_adapter("lerobot-eval").parse(both)
        with self.assertRaises(AdapterError):
            get_adapter("lerobot-eval").parse({"task": "x"})
        with self.assertRaises(AdapterError):
            get_adapter("lerobot-eval").parse(42)
        with self.assertRaises(AdapterError):
            get_adapter("lerobot-eval").parse("{bad json")


class TestTranscriptionLoudIgnore(unittest.TestCase):
    def test_unknown_keys_reported(self):
        doc = {"task": "pour", "policy": None,
               "episodes": [{"is_success": True, "temp_c": 21.5}],
               "operator": "ada"}
        out = get_adapter("lerobot-eval").parse(doc)
        self.assertEqual(out["provenance"]["shape"],
                         "episode-transcription")
        self.assertEqual(out["provenance"]["ignored"]["top"],
                         ["operator"])
        self.assertEqual(out["provenance"]["ignored"]["episodes"],
                         {0: ["temp_c"]})
        self.assertEqual(out["summary"]["successes"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
