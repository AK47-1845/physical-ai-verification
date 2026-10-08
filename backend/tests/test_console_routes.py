"""Console route tests: the 15 new service handlers (fastapi-gated).

Run from meta bro root:  python backend/tests/test_console_routes.py
Handlers are called directly (no TestClient). Without fastapi
installed every test skips; they run on his machine after the
service deps install (START-BACKEND.cmd does that).
"""

import os
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

TRACE_A = [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [3.0, 0.0]]
TRACE_B = [[0.0, 0.0], [1.0, 0.1], [2.0, 0.0], [3.0, 0.1]]

LIBERO_DOC = {"framework": "libero", "benchmark": "libero_spatial",
              "task_id": 3, "seed": 100, "env_num": 20, "num_success": 14,
              "success_rate": 0.7, "loss": 0.42}


def _service(test):
    try:
        import fastapi  # noqa: F401
    except ImportError:
        raise unittest.SkipTest("fastapi not installed")
    import backend.service_app as service
    return service


class TestConsoleRoutePaths(unittest.TestCase):
    def test_new_paths_mounted(self):
        service = _service(self)
        paths = sorted(r.path for r in service.router.routes)
        for path in ("/api/v2/eval/failure-modes", "/api/v2/eval/hunt",
                     "/api/v2/eval/redteam", "/api/v2/eval/hunt/summarize",
                     "/api/v2/eval/envelope", "/api/v2/eval/briefing",
                     "/api/v2/eval/contracts/check", "/api/v2/eval/task-graph",
                     "/api/v2/eval/rank", "/api/v2/eval/credibility",
                     "/api/v2/eval/bounded", "/api/v2/eval/property",
                     "/api/v2/adapters/ingest", "/api/v2/adapters/status",
                     "/api/v2/provenance/duplicates"):
            self.assertIn(path, paths)


class TestConsoleHandlers(unittest.TestCase):
    def test_failure_modes(self):
        service = _service(self)
        out = service.eval_failure_modes({"intended": TRACE_A,
                                          "observed": TRACE_B})
        self.assertIn("fm1_drift", out)
        self.assertIn("fm2_executability_proxy", out)
        self.assertIn("fm5_sim_real_gap", out)
        self.assertIn("FM3/FM4", out["note"])

    def test_failure_modes_empty_is_422(self):
        service = _service(self)
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            service.eval_failure_modes({})
        self.assertEqual(ctx.exception.status_code, 422)

    def test_hunt_defaults(self):
        service = _service(self)
        out = service.eval_hunt({})
        self.assertEqual(out["mode"], "grid")
        self.assertTrue(out["trials"])

    def test_hunt_refusals(self):
        service = _service(self)
        from fastapi import HTTPException
        for bad in ({"method": "bogus"}, {"trial_cap": 999},
                    {"trial_cap": True}, {"policy": "nope"}):
            with self.assertRaises(HTTPException, msg=bad):
                service.eval_hunt(bad)

    def test_redteam_broken_vs_sane(self):
        service = _service(self)
        broken = service.eval_redteam({"score_fn": "broken"})
        self.assertTrue(broken["breaks"])
        sane = service.eval_redteam({"score_fn": "sane"})
        self.assertEqual(sane["breaks"], [])
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            service.eval_redteam({"score_fn": "evil"})

    def test_hunt_summarize(self):
        service = _service(self)
        from engine.hunt import grid_search

        from backend.eval.hunt_backends import FixtureBackend
        backend = FixtureBackend("playback", horizon=16, seed=1)
        catalogue = grid_search(backend, {"noise_scale": [1.0],
                                          "bias": [0.0]},
                                seed=1, trial_cap=2)
        out = service.eval_hunt_summarize({"catalogue": catalogue})
        self.assertIn("summary", out)
        self.assertIn("sealed", out)

    def test_envelope(self):
        service = _service(self)
        out = service.eval_envelope(
            {"trials": [{"breaks": True, "params": {"f": 2.0}},
                        {"breaks": False, "params": {"f": 1.0}}],
             "param_names": ["f"]})
        self.assertEqual(out["params"]["f"]["min_break"], 2.0)

    def test_briefing(self):
        service = _service(self)
        from engine.par import build_par
        par = build_par(
            policy={"id": "arm-reach",
                    "weights": "sha256:" + "f" * 64},
            release={"parent": "sha256:" + "f" * 64, "delta": "IN-ODD"},
            gates=[{"id": "tracking", "verdict": "PASS",
                    "measurement": 0.1, "evidence": "ev:1"}],
            ledger_head="e" * 64, odd="test cell",
            independence={"builder": "OEM-X", "funder": "OEM-X",
                          "relationship": "none"})
        out = service.eval_briefing({"par_envelope": par})
        self.assertTrue(out["sections"])
        self.assertIn("attention", out)

    def test_contracts_check(self):
        service = _service(self)
        out = service.eval_contract_check(
            {"contract_id": "grasp",
             "states": [{"gripper_open": True, "holding": False},
                        {"gripper_open": True, "holding": True}]})
        self.assertTrue(out["holds"])
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            service.eval_contract_check(
                {"contract_id": "teleport", "states": [{"a": 1}]})

    def test_task_graph(self):
        service = _service(self)
        out = service.eval_task_graph(
            {"graph": {"nodes": [{"id": "a"}, {"id": "b"}],
                       "edges": [["a", "b"]]}})
        self.assertEqual(out["order"], ["a", "b"])

    def test_rank(self):
        service = _service(self)
        out = service.eval_rank(
            {"entries": [
                {"policy_id": "p1", "verdict": "TRUSTED",
                 "gates": [{"status": "PASS"}]},
                {"policy_id": "p2", "verdict": "BLOCKED",
                 "gates": [{"status": "BLOCKED"}]}]})
        self.assertEqual(out["ranking"], ["p2", "p1"])

    def test_credibility(self):
        service = _service(self)
        from engine import canonical_hash
        card = {"gate_id": "tracking", "gate_version": "1.0",
                "corpus_hash": "a" * 64, "n": 120,
                "false_positives": 2, "false_negatives": 1,
                "label_counts": {"pass": 100, "fail": 20},
                "calibration_bins": [{"lo": 0.0, "hi": 0.5,
                                      "predicted": 0.2, "observed": 0.22,
                                      "n": 60}],
                "rollout_types": {"policy-sampled": 120},
                "transfer_error": 0.03, "search_hits": 0,
                "date": "2026-10-04", "analyst": "qa"}
        out = service.eval_credibility(
            {"card_envelope": {"card": card,
                               "card_hash": canonical_hash(card)}})
        self.assertIn("lift", out)
        self.assertIn("reasons", out)

    def test_bounded(self):
        service = _service(self)
        out = service.eval_bounded(
            {"layers": [{"weights": [[0.5]], "bias": [0.0]}],
             "input_box": [[0.0, 1.0]],
             "output_bounds": [[-0.5, 1.0]]})
        self.assertEqual(out["verdict"], "PROVEN")

    def test_property(self):
        service = _service(self)
        out = service.eval_property(
            {"spec": {"op": "always", "predicate": "clearance",
                      "name": "stay-clear"},
             "trace": [{"clearance": 0.5}, {"clearance": 0.2}]})
        self.assertTrue(out["satisfied"])
        self.assertAlmostEqual(out["margin"], 0.2)

    def test_adapters_ingest(self):
        service = _service(self)
        out = service.adapters_ingest({"harness": "simpler-libero",
                                       "document": dict(LIBERO_DOC)})
        self.assertEqual(out["provenance"]["schema_status"], "DERIVED")
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            service.adapters_ingest({"harness": "halos",
                                      "document": {}})
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.detail["error"], "input")
        self.assertIn("UNVERIFIED", ctx.exception.detail["message"])

    def test_adapters_status(self):
        service = _service(self)
        out = service.adapters_status()
        self.assertEqual(len(out["adapters"]), 5)

    def test_duplicates(self):
        service = _service(self)
        out = service.duplicates_route(
            {"rows": [[1.0], [1.0], [5.0]], "mode": "near"})
        self.assertGreater(out["rate"], 0.0)
        out = service.duplicates_route(
            {"rows": [[1.0], [1.0], [5.0]], "mode": "exact"})
        self.assertIn("rate", out)
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            service.duplicates_route({"rows": [], "mode": "near"})

    def test_history_lists(self):
        service = _service(self)
        from backend.persist.filelayout import FileLayoutStore
        with tempfile.TemporaryDirectory() as tmp:
            old, service._STORE = service._STORE, FileLayoutStore(root=tmp)
            try:
                self._history_lists_inner(service)
            finally:
                service._STORE = old

    def _history_lists_inner(self, service):
        run = service.runs_evaluate(
            {"intended": TRACE_A, "observed": TRACE_B,
             "policy_id": "history-probe"})
        self.assertIn(run["run_id"], service.list_runs()["run_ids"])
        dos = service.dossiers_compile(
            {"run_ids": [run["run_id"]],
             "odd": "Synthetic history test, task-space traces, supervised",
             "independence": {"builder": "b", "funder": "f",
                              "relationship": "none"}})
        self.assertIn(dos["dossier_id"],
                      service.list_dossiers()["dossier_ids"])
        fetched = service.dossiers_get(dos["dossier_id"])
        self.assertEqual(fetched["doc"]["ledger_index"],
                         dos["ledger_index"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
