"""Dossier worksheet passthrough (stubbed fastapi, runs anywhere).

Run from meta bro root:  python backend/tests/test_dossier_worksheet.py
dossiers_compile accepts an optional worksheet object and stores it
on the dossier doc (the briefing renders it as the Scoping section);
non-dict worksheets are 422.
"""

import os
import shutil
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))


class _StubRouter:
    def __init__(self, *args, **kwargs):
        pass

    def _add(self, path):
        def deco(func):
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

_RUN = {"scorecard": {"payload": {
    "verdict": "TRUSTED",
    "gates": [{"gate": "t", "status": "PASS", "measurement": 0.1,
               "evidence": "ev:1"}]}},
        "policy_id": "p1"}
_INDEP = {"builder": "b", "funder": "f", "relationship": "none"}
SHEET = {"product": "arm", "analyst": "qa",
         "answers": {"ml_safety_function": True, "self_evolving": True,
                     "frozen_weight_ota": False},
         "implied_route": "PART_A_5_6_NOTIFIED_BODY_ROUTE",
         "banner": "BANNER"}


class TestDossierWorksheet(unittest.TestCase):
    def setUp(self):
        self.root = os.path.join(BASE, "backend", "tests", "_dow_tmp")
        self._old = service._STORE
        service._STORE = FileLayoutStore(self.root)
        service._STORE.save("runs", "run_ws1", _RUN)
        self.addCleanup(self._restore)

    def _restore(self):
        service._STORE = self._old
        shutil.rmtree(self.root, ignore_errors=True)

    def _compile(self, **kw):
        body = {"run_ids": ["run_ws1"], "independence": dict(_INDEP),
                "odd": "test cell"}
        body.update(kw)
        return service.dossiers_compile(body)

    def test_worksheet_stored(self):
        out = self._compile(worksheet=dict(SHEET))
        stored = service._STORE.get("dossiers", out["dossier_id"])
        self.assertEqual(stored["doc"]["worksheet"]["implied_route"],
                         "PART_A_5_6_NOTIFIED_BODY_ROUTE")
        self.assertNotIn("worksheet", out)  # response shape unchanged

    def test_worksheet_omitted_ok(self):
        out = self._compile()
        stored = service._STORE.get("dossiers", out["dossier_id"])
        self.assertIsNone(stored["doc"]["worksheet"])

    def test_concurrent_dossier_compiles_preserve_ledger_sequence(self):
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: self._compile(), range(8)))
        self.assertEqual(len(results), 8)
        self.assertTrue(service.ledger_verify()["ok"])
        self.assertEqual(sorted(result["ledger_index"] for result in results), list(range(8)))

    def test_worksheet_non_dict_is_422(self):
        try:
            self._compile(worksheet="xx")
        except HTTPException as exc:
            self.assertEqual(exc.status_code, 422)
            return
        self.fail("non-dict worksheet did not raise 422")


if __name__ == "__main__":
    unittest.main(verbosity=2)
