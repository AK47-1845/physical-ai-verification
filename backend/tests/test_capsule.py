"""Replay capsule: seal binds mode, verify recomputes the hash.

Run from meta code new 2.0 root:  python backend/tests/test_capsule.py
Unit tests are stdlib-only; route tests call the guarded handlers
directly and skip without fastapi.
"""

import copy
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from backend.eval.capsule import SCHEMA, CapsuleError, seal_capsule, verify_capsule  # noqa: E402

REQUEST = {"path": "runs/evaluate", "method": "POST",
           "body": {"policy_id": "demo-clean-v1"}}
ENVELOPE = {"status": 200, "data": {"verdict": "TRUSTED"}}


def _body(**over):
    body = {"request": copy.deepcopy(REQUEST),
            "envelope": copy.deepcopy(ENVELOPE), "mode": "live",
            "backend_host": "127.0.0.1:8012"}
    body.update(over)
    return body


class TestSeal(unittest.TestCase):
    def test_round_trip(self):
        capsule = seal_capsule(_body())
        self.assertEqual(capsule["schema"], SCHEMA)
        self.assertEqual(capsule["mode"], "live")
        self.assertIn("replay", capsule)
        self.assertIn("track_hash", capsule)
        verdict = verify_capsule(capsule)
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["mode"], "live")
        self.assertIn("UNSIGNED", verdict["authorship"])

    def test_deterministic(self):
        first = seal_capsule(_body())["track_hash"]
        second = seal_capsule(_body())["track_hash"]
        self.assertEqual(first, second)

    def test_mode_required(self):
        for bad in ({}, {"mode": ""}, {"mode": "  "}, {"mode": 7}):
            with self.subTest(bad=bad):
                body = _body()
                body.pop("mode", None)
                body.update(bad)
                with self.assertRaises(CapsuleError):
                    seal_capsule(body)

    def test_shape_refusals(self):
        with self.assertRaises(CapsuleError):
            seal_capsule({"mode": "live"})
        with self.assertRaises(CapsuleError):
            seal_capsule(_body(request={"path": "x"}))
        with self.assertRaises(CapsuleError):
            seal_capsule(_body(envelope={"status": 200}))
        with self.assertRaises(CapsuleError):
            seal_capsule(_body(surprise=1))

    def test_tamper_detected(self):
        capsule = seal_capsule(_body())
        for path in (["mode"], ["backend_host"],
                     ["request", "body"], ["envelope", "data"],
                     ["envelope", "status"]):
            with self.subTest(path=path):
                tampered = copy.deepcopy(capsule)
                node = tampered
                for key in path[:-1]:
                    node = node[key]
                node[path[-1]] = "TAMPERED"
                verdict = verify_capsule(tampered)
                self.assertFalse(verdict["ok"])
                self.assertIn("mismatch", verdict["reason"])

    def test_unknown_keys_ignored_loudly(self):
        capsule = seal_capsule(_body())
        capsule["future_field"] = {"v": 2}
        verdict = verify_capsule(capsule)
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["ignored"], ["future_field"])

    def test_wrong_schema_refused(self):
        capsule = seal_capsule(_body())
        capsule["schema"] = "verification.replay-capsule/999"
        with self.assertRaises(CapsuleError):
            verify_capsule(capsule)


class TestCapsuleRoutes(unittest.TestCase):
    def test_seal_verify_round_trip(self):
        try:
            import fastapi  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("fastapi not installed")
        import backend.service_app as service
        capsule = service.capsule_seal(_body())
        self.assertIn("track_hash", capsule)
        verdict = service.capsule_verify(capsule)
        self.assertTrue(verdict["ok"])
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            service.capsule_seal({"mode": "live"})
        self.assertEqual(ctx.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main(verbosity=2)
