"""Error contract: 422 means caller input wrong, 500 means we broke.

Run from meta bro root:  python backend/tests/test_error_contract.py
FastAPI is stubbed (same pattern as test_console_presets_live) so
this runs without service deps. Every route class gets one
malformed-input case asserting 422 with the stable body
{"error": "input", "message": ...}; one injected engine failure
asserts the 500 body {"error": "internal", "error_id": ...} with
no traceback text leaking to the client.
"""

import os
import shutil
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))


class _StubRouter:
    def __init__(self, *args, **kwargs):
        self.routes = []

    def _add(self, path):
        def deco(func):
            self.routes.append(path)
            return func
        return deco

    def get(self, path):
        return self._add(path)

    def post(self, path):
        return self._add(path)


class _StubHTTPException(Exception):
    def __init__(self, status_code, detail=None):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


class _StubFastAPI:
    APIRouter = _StubRouter
    HTTPException = _StubHTTPException


try:
    import fastapi  # noqa: F401 - availability probe; except-branch installs stub
except ImportError:
    sys.modules.setdefault("fastapi", _StubFastAPI())

from fastapi import HTTPException  # noqa: E402

import backend.service_app as service  # noqa: E402
from backend.persist.filelayout import FileLayoutStore  # noqa: E402

_SEED_RUN = {"scorecard": {"payload": {
    "verdict": "TRUSTED", "gates": []}}, "policy_id": "p1"}


class TestErrorContract(unittest.TestCase):
    def setUp(self):
        self.root = os.path.join(BASE, "backend", "tests", "_err_tmp")
        self._old = service._STORE
        service._STORE = FileLayoutStore(self.root)
        self.addCleanup(self._restore)

    def _restore(self):
        service._STORE = self._old
        shutil.rmtree(self.root, ignore_errors=True)

    def _assert_422(self, func, *args):
        try:
            func(*args)
        except HTTPException as exc:
            self.assertEqual(exc.status_code, 422)
            self.assertEqual(set(exc.detail), {"error", "message"})
            self.assertEqual(exc.detail["error"], "input")
            self.assertTrue(exc.detail["message"])
            return
        self.fail(f"{func.__name__} did not raise 422")

    def test_runs_evaluate(self):
        self._assert_422(service.runs_evaluate, {})

    def test_dossiers_compile(self):
        self._assert_422(service.dossiers_compile, {"run_ids": []})
        self._assert_422(service.dossiers_compile, "xx")

    def test_pilots(self):
        self._assert_422(service.create_pilot, {})
        self._assert_422(service.create_pilot, {"email": "nope"})

    def test_provenance_batches(self):
        self._assert_422(service.stamp_batch_route, {})
        self._assert_422(service.stamp_batch_route, "xx")

    def test_provenance_bridge(self):
        self._assert_422(service.bridge_route, {})

    def test_sentinels(self):
        self._assert_422(service.sentinels_route, {})
        self._assert_422(service.sentinels_route,
                         {"baseline": {}, "current": {},
                          "thresholds": []})

    def test_corpora(self):
        self._assert_422(service.create_corpus, {})
        service._STORE.save("corpora", "c1",
                            {"corpus_id": "c1", "generations": []})
        self._assert_422(service.add_generation_route, "c1", {})
        self._assert_422(service.add_generation_route, "c1", "xx")

    def test_corpus_risk_malformed(self):
        service._STORE.save("corpora", "c9",
                            {"corpus_id": "c9",
                             "generations": ["oops"]})
        self._assert_422(service.corpus_risk, "c9")

    def test_par(self):
        self._assert_422(service.par_build, {})
        self._assert_422(service.par_validate, "xx")
        self._assert_422(service.par_read, "xx")

    def test_worksheet(self):
        self._assert_422(service.worksheet_record, {})

    def test_panel(self):
        self._assert_422(service.panel_commit, {})
        # reveal is total like validate_par: garbage returns a
        # not-verified verdict (200), never a 422.
        out = service.panel_reveal({})
        self.assertFalse(out["verified"])
        self._assert_422(service.panel_reveal, "xx")

    def test_release(self):
        self._assert_422(service.release_compare, {})

    def test_eval_score_transfer(self):
        self._assert_422(service.eval_score, {})
        self._assert_422(service.eval_transfer, {})

    def test_failure_modes(self):
        self._assert_422(service.eval_failure_modes, {})

    def test_hunt_caps(self):
        self._assert_422(service.eval_hunt, {"trial_cap": 999})
        self._assert_422(service.eval_hunt, {"method": "bogus"})
        self._assert_422(service.eval_redteam, {"trial_cap": 0})

    def test_hunt_summarize_envelope(self):
        self._assert_422(service.eval_hunt_summarize, {})
        self._assert_422(service.eval_envelope, {})

    def test_briefing_contracts(self):
        self._assert_422(service.eval_briefing, {})
        self._assert_422(service.eval_contract_check, {})
        self._assert_422(service.eval_task_graph, {})

    def test_rank_credibility(self):
        self._assert_422(service.eval_rank, {})
        self._assert_422(service.eval_credibility, {"min_n": "xx"})

    def test_bounded_property(self):
        self._assert_422(service.eval_bounded, {})
        self._assert_422(service.eval_property, {})

    def test_adapters_duplicates(self):
        self._assert_422(service.adapters_ingest,
                         {"harness": "nope", "document": {}})
        self._assert_422(service.duplicates_route,
                         {"rows": [], "mode": "near"})

    def test_404_shape(self):
        try:
            service.runs_get("run_missing0000")
        except HTTPException as exc:
            self.assertEqual(exc.status_code, 404)
            self.assertEqual(exc.detail["error"], "not_found")
            return
        self.fail("runs_get did not raise 404")

    def _assert_404(self, func, *args):
        try:
            func(*args)
        except HTTPException as exc:
            self.assertEqual(exc.status_code, 404)
            self.assertEqual(exc.detail["error"], "not_found")
            return
        self.fail(f"{func.__name__} did not raise 404")

    def test_ui_release(self):
        import backend.tools.golden_lib as glib
        arts = glib.build_all()["stories"]
        for story in ("clean", "drifty"):
            service._STORE.save(
                "runs", f"run_vm_{story}",
                {"scorecard": arts[story]["scorecard"],
                 "policy_id": f"golden-{story}"})
        out = service.ui_release("run_vm_clean")
        self.assertEqual(out["verdict"], "TRUSTED")
        self.assertEqual(out["run_id"], "run_vm_clean")
        self.assertEqual(
            [c["label"] for c in out["chips"]], ["DRAFT", "UNSIGNED"])
        cmpd = service.ui_release("run_vm_drifty", "run_vm_clean")
        self.assertEqual(cmpd["compare_id"], "run_vm_clean")
        self.assertTrue(cmpd["deltas"])
        self.assertTrue(any(d["regression"] for d in cmpd["deltas"]))
        same = service.ui_release("run_vm_clean", "run_vm_clean")
        self.assertFalse(any(d["regression"] for d in same["deltas"]))
        self._assert_422(service.ui_release, "../x")
        self._assert_422(service.ui_release, "run_vm_clean", "C:\\x")
        self._assert_404(service.ui_release, "run_missing0000")
        self._assert_404(service.ui_release, "run_vm_clean",
                         "run_missing0000")

    def test_injected_internal_failure_is_500(self):
        import engine.bounded as bounded_mod
        real = bounded_mod.verify_affine_relu

        def boom(*args, **kwargs):
            raise RuntimeError("boom-hidden")

        bounded_mod.verify_affine_relu = boom
        try:
            service.eval_bounded(
                {"layers": [{"weights": [[0.5]], "bias": [0.0]}],
                 "input_box": [[0.0, 1.0]],
                 "output_bounds": [[-0.5, 1.0]]})
        except HTTPException as exc:
            self.assertEqual(exc.status_code, 500)
            self.assertEqual(set(exc.detail), {"error", "error_id"})
            self.assertEqual(exc.detail["error"], "internal")
            self.assertRegex(exc.detail["error_id"], r"^[0-9a-f]{8}$")
            blob = str(exc.detail)
            self.assertNotIn("boom-hidden", blob)
            self.assertNotIn("Traceback", blob)
        else:
            self.fail("injected failure did not raise 500")
        finally:
            bounded_mod.verify_affine_relu = real


if __name__ == "__main__":
    unittest.main(verbosity=2)
