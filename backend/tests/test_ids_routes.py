"""Route-level ID validation: attack IDs -> 422, never 404/500.

Run from meta bro root:  python backend/tests/test_ids_routes.py
Fastapi-gated (skips here, runs on his machine): calls the ID-taking
handlers directly and requires HTTPException 422 for every attack
string. Path safety itself is covered in tests/test_ids.py.
"""

import os
import shutil
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

ATTACKS = ["../x", "..\\x", "a/b", "C:\\x", ".", "..", "con",
           "NUL.txt", "x.", "x ", ".hidden", "a" * 129, "\u0441on"]


def _service():
    try:
        import fastapi  # noqa: F401
    except ImportError:
        raise unittest.SkipTest("fastapi not installed")
    import backend.service_app as service
    return service


class TestRouteIds(unittest.TestCase):
    def setUp(self):
        self.service = _service()
        from backend.persist.filelayout import FileLayoutStore
        self.root = os.path.join(BASE, "backend", "tests", "_ids_tmp")
        self._old = self.service._STORE
        self.service._STORE = FileLayoutStore(self.root)
        self.addCleanup(self._restore)

    def _restore(self):
        self.service._STORE = self._old
        shutil.rmtree(self.root, ignore_errors=True)

    def _assert_422(self, func, *args):
        from fastapi import HTTPException
        try:
            func(*args)
        except HTTPException as exc:
            self.assertEqual(exc.status_code, 422)
            return
        self.fail(f"{func.__name__}{args!r} did not raise 422")

    def test_path_param_routes_reject_attacks(self):
        service = self.service
        for bad in ATTACKS:
            self._assert_422(service.runs_get, bad)
            self._assert_422(service.dossiers_get, bad)
            self._assert_422(service.get_pilot, bad)
            self._assert_422(service.corpus_risk, bad)
            self._assert_422(service.add_generation_route, bad, {})

    def test_body_id_lists_reject_attacks(self):
        for bad in ATTACKS:
            self._assert_422(self.service.dossiers_compile,
                             {"run_ids": [bad]})
            self._assert_422(self.service.create_corpus,
                             {"corpus_id": bad})

    def test_valid_ids_still_404_when_missing(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.service.runs_get("run_missing0000")
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
