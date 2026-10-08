"""Adapter + store + fixture contract tests (stdlib only).

Run from meta bro root:  python backend/tests/test_contracts_store.py
FastAPI-dependent checks are skipped without fastapi installed.
"""

import os
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from backend.adapters.ingest import AdapterError, conformance_report, get_adapter  # noqa: E402
from backend.eval import policy_fixtures as fixtures  # noqa: E402
from backend.eval.failure_modes import marginalization_probe  # noqa: E402
from backend.persist.filelayout import FileLayoutStore  # noqa: E402


class TestAdapters(unittest.TestCase):
    def test_stubs_refuse_loudly(self):
        for name in ("isaac-lab-arena", "roboarena", "halos"):
            adapter = get_adapter(name)
            self.assertEqual(adapter.SCHEMA_STATUS, "STUB")
            with self.assertRaises(AdapterError) as ctx:
                adapter.parse("{}")
            self.assertIn("UNVERIFIED", str(ctx.exception))
        self.assertEqual(get_adapter("simpler-libero").SCHEMA_STATUS,
                         "DERIVED")
        self.assertTrue(
            get_adapter("lerobot-eval").SCHEMA_STATUS.startswith(
                "VERIFIED:2026-10-06:lerobot@"))

    def test_unknown_adapter_raises(self):
        with self.assertRaises(AdapterError):
            get_adapter("nope")
        with self.assertRaises(AdapterError):
            get_adapter(["isaac-arena"])

    def test_conformance_report_shape(self):
        report = conformance_report()
        self.assertEqual(len(report["adapters"]), 5)
        by_name = {a["name"]: a for a in report["adapters"]}
        for name in ("isaac-lab-arena", "roboarena", "halos"):
            self.assertEqual(by_name[name]["schema_status"], "STUB")
            self.assertTrue(by_name[name]["stub_reason"])
        self.assertEqual(by_name["simpler-libero"]["schema_status"],
                         "DERIVED")
        self.assertTrue(
            by_name["lerobot-eval"]["schema_status"].startswith(
                "VERIFIED:2026-10-06:lerobot@"))


class TestFileLayoutStore(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = FileLayoutStore(root=tmp)
            envelope = store.save("pilots", "p1", {"a": 1})
            self.assertIn("stored_at", envelope)
            self.assertEqual(store.get("pilots", "p1")["doc"], {"a": 1})
            self.assertEqual(store.list_ids("pilots"), ["p1"])
            self.assertIsNone(store.get("pilots", "missing"))

    def test_unsafe_ids_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = FileLayoutStore(root=tmp)
            for bad in ("", "../x", "a/b", ".."):
                with self.assertRaises(Exception):
                    store.save("pilots", bad, {})

    def test_ledger_append_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = FileLayoutStore(root=tmp)
            self.assertEqual(store.append_ledger({"i": 0}), 1)
            self.assertEqual(store.append_ledger({"i": 1}), 2)
            self.assertEqual(store.read_ledger(), [{"i": 0}, {"i": 1}])

    def test_open_store_defaults_to_files(self):
        from backend.persist import open_store
        old = os.environ.pop("MONGO_URL", None)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                store = open_store(root=tmp)
                self.assertIsInstance(store, FileLayoutStore)
        finally:
            if old is not None:
                os.environ["MONGO_URL"] = old


class TestPolicyFixtures(unittest.TestCase):
    def test_deterministic(self):
        acts = fixtures.reference_actions(horizon=16)
        a = fixtures.clean_rollout(acts, seed=3)
        b = fixtures.clean_rollout(acts, seed=3)
        self.assertEqual(a, b)

    def test_playback_dead_via_probe(self):
        acts = fixtures.reference_actions(horizon=16)
        out = marginalization_probe(fixtures.playback_rollout, acts,
                                    probe_offsets=[0.5, -0.3], seed=1)
        self.assertEqual(out["normalized"], 0.0)
        self.assertFalse(out["responsive"])

    def test_clean_responsive_via_probe(self):
        acts = fixtures.reference_actions(horizon=16)
        out = marginalization_probe(fixtures.clean_rollout, acts,
                                    probe_offsets=[0.5, -0.3], seed=1)
        self.assertTrue(out["responsive"])

    def test_unknown_policy_raises(self):
        with self.assertRaises(KeyError):
            fixtures.get_policy("nope")


class TestServiceApp(unittest.TestCase):
    def test_router_import_or_skip(self):
        try:
            import fastapi  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("fastapi not installed")
        from backend.service_app import router
        paths = sorted(r.path for r in router.routes)
        self.assertIn("/api/v2/pilots", paths)
        self.assertIn("/api/v2/par/build", paths)
        self.assertIn("/api/v2/eval/transfer", paths)
        self.assertIn("/api/v2/runs/evaluate", paths)
        self.assertIn("/api/v2/runs/{run_id}", paths)
        self.assertIn("/api/v2/dossiers/compile", paths)
        self.assertIn("/api/v2/ledger/verify", paths)

    def _service(self):
        try:
            import fastapi  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("fastapi not installed")
        import backend.service_app as service
        return service

    def _store_with_runs(self, tmp):
        service = self._service()
        store = FileLayoutStore(root=tmp)
        store.save("runs", "r1", {"scorecard": {"payload": {"gates": [
            {"gate": "g", "status": "PASS", "measurement": 0.1}]}},
            "policy_id": "p"})
        old, service._STORE = service._STORE, store
        self.addCleanup(setattr, service, "_STORE", old)
        return service, store

    def _corrupt_ledger(self, tmp):
        with open(os.path.join(tmp, "ledger.jsonl"), "a",
                  encoding="utf-8") as handle:
            handle.write("{not json\n")

    def test_ledger_verify_corrupt_returns_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            service, _ = self._store_with_runs(tmp)
            self._corrupt_ledger(tmp)
            out = service.ledger_verify()
        self.assertFalse(out["ok"])
        self.assertIsNone(out["first_bad"])
        self.assertIn("ledger unreadable", out["reason"])

    def test_dossiers_compile_corrupt_ledger_is_422(self):
        with tempfile.TemporaryDirectory() as tmp:
            service, _ = self._store_with_runs(tmp)
            from fastapi import HTTPException
            self._corrupt_ledger(tmp)
            with self.assertRaises(HTTPException) as ctx:
                service.dossiers_compile(
                    {"run_ids": ["r1"], "independence": {"a": "b"},
                     "odd": "Synthetic corrupt-ledger test, supervised"})
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.detail["error"], "input")
        self.assertIn("stored ledger is corrupt",
                      ctx.exception.detail["message"])

    def test_corpus_risk_malformed_history_is_422(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service()
            store = FileLayoutStore(root=tmp)
            store.save("corpora", "c1",
                       {"corpus_id": "c1", "generations": ["oops"]})
            old, service._STORE = service._STORE, store
            self.addCleanup(setattr, service, "_STORE", old)
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as ctx:
                service.corpus_risk("c1")
        self.assertEqual(ctx.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main(verbosity=2)
