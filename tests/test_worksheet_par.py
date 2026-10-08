"""Worksheet + PAR tests: FR-39 routes, FR-38 build/validate/read.

Run from meta bro root:  python tests/test_worksheet_par.py
(stdlib only)
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.par import PARError, build_par, read_par, validate_par  # noqa: E402
from engine.worksheet import BANNER, WorksheetError, record  # noqa: E402

SHA = "e" * 64
WEIGHTS = "sha256:" + "f" * 64


def _par(**kw):
    args = {"policy": {"id": "arm-reach", "weights": WEIGHTS},
            "release": {"parent": WEIGHTS, "delta": "IN-ODD"},
            "gates": [{"id": "tracking", "verdict": "PASS",
                       "measurement": 0.1, "evidence": "ev:1"}],
            "ledger_head": SHA,
            "odd": "test cell",
            "independence": {"builder": "OEM-X", "funder": "OEM-X",
                             "relationship": "none"}}
    args.update(kw)
    return build_par(**args)


class TestWorksheet(unittest.TestCase):
    def _rec(self, ml, evo, ota):
        return record(product="p", analyst="qa", ml_safety_function=ml,
                      self_evolving=evo, frozen_weight_ota=ota)

    def test_notified_body_route(self):
        out = self._rec(True, True, False)
        self.assertEqual(out["implied_route"],
                         "PART_A_5_6_NOTIFIED_BODY_ROUTE")
        self.assertEqual(out["banner"], BANNER)

    def test_substantial_mod_route(self):
        out = self._rec(True, False, True)
        self.assertEqual(out["implied_route"],
                         "SUBSTANTIAL_MODIFICATION_REVIEW")

    def test_out_of_scope(self):
        out = self._rec(False, True, True)
        self.assertEqual(out["implied_route"], "OUT_OF_SCOPE_CANDIDATE")

    def test_unresolved_on_none(self):
        out = self._rec(True, None, True)
        self.assertEqual(out["implied_route"], "UNRESOLVED_INPUTS")

    def test_strict_types(self):
        with self.assertRaises(WorksheetError):
            self._rec("yes", True, True)


class TestPAR(unittest.TestCase):
    def test_build_validate_read(self):
        envelope = _par()
        check = validate_par(envelope)
        self.assertTrue(check["ok"])
        self.assertEqual(check["gates"], 1)
        view = read_par(envelope)
        self.assertTrue(view["ok"])
        text = "\n".join(view["lines"])
        self.assertIn("arm-reach", text)
        self.assertIn("IN-ODD", text)
        self.assertIn("PASS", text)

    def test_tamper_fails(self):
        envelope = _par()
        envelope["par"]["gates"][0]["verdict"] = "BLOCKED"
        self.assertFalse(validate_par(envelope)["ok"])
        self.assertFalse(read_par(envelope)["ok"])

    def test_bad_verdict_raises(self):
        with self.assertRaises(PARError):
            _par(gates=[{"id": "t", "verdict": "CERTIFIED"}])

    def test_missing_independence_raises(self):
        with self.assertRaises(PARError):
            _par(independence={"builder": "x"})

    def test_bad_hashes_raise(self):
        with self.assertRaises(PARError):
            _par(ledger_head="nope")
        with self.assertRaises(PARError):
            _par(policy={"id": "p", "weights": "raw-bytes"})

    def test_blocked_count(self):
        envelope = _par(gates=[{"id": "a", "verdict": "PASS"},
                               {"id": "b", "verdict": "BLOCKED"}])
        self.assertEqual(validate_par(envelope)["blocked"], 1)

    def test_read_stripped_but_resealed_never_raises(self):
        from engine import canonical_hash
        envelope = _par()
        del envelope["par"]["policy"]
        envelope["par_hash"] = canonical_hash(envelope["par"])
        view = read_par(envelope)  # must return, not raise
        self.assertFalse(view["ok"])
        self.assertIn("incomplete", view["reason"])

    def test_schema_types_enforced(self):
        good = {"id": "t", "verdict": "PASS", "measurement": None,
                "evidence": None}
        self.assertTrue(validate_par(_par(gates=[good]))["ok"])
        for bad_measure in ("high", True, float("inf"), float("nan"),
                            [0.1]):
            with self.assertRaises(PARError, msg=bad_measure):
                _par(gates=[{**good, "measurement": bad_measure}])
        for bad_evidence in ({"ptr": 1}, ["ev"], 42, True):
            with self.assertRaises(PARError, msg=bad_evidence):
                _par(gates=[{**good, "evidence": bad_evidence}])


if __name__ == "__main__":
    unittest.main(verbosity=2)
