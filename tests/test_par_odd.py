"""PAR ODD requirement: no PAR without an operating envelope.

Run from meta bro root:  python tests/test_par_odd.py
Every PAR pins its operational_design_domain (free-text envelope,
1..2000 chars). build_par refuses without it; validate_par reports
a PAR without ODD as not-ok with an INSUFFICIENT reason (missing
evidence, not tamper). ODD mutations are covered by the PAR
tamper matrix (test_par_matrix.py).
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.par import build_par, validate_par  # noqa: E402

W = "sha256:" + "ab" * 32
ARGS = {"policy": {"id": "p", "weights": W},
        "release": {"parent": W, "delta": "IN-ODD"},
        "gates": [{"id": "g1", "verdict": "PASS"}],
        "ledger_head": "cd" * 32,
        "independence": {"builder": "b", "funder": "f",
                         "relationship": "none"}}


class TestParOdd(unittest.TestCase):
    def test_build_requires_odd(self):
        with self.assertRaises(Exception):
            build_par(**ARGS)
        out = build_par(**ARGS, odd="warehouse cell, <2m/s, no humans")
        self.assertEqual(out["par"]["odd"], "warehouse cell, <2m/s, no humans")

    def test_empty_and_long_odd_rejected(self):
        for bad in ("", "   ", "x" * 2001, None, 42, ["x"]):
            with self.assertRaises(Exception, msg=f"accepted: {bad!r}"):
                build_par(**ARGS, odd=bad)

    def test_validate_missing_odd_is_insufficient(self):
        out = build_par(**ARGS, odd="cell A")
        del out["par"]["odd"]
        result = validate_par(out)
        self.assertFalse(result["ok"])
        self.assertIn("INSUFFICIENT", result["reason"])

    def test_pristine_with_odd_validates(self):
        out = build_par(**ARGS, odd="cell A")
        self.assertTrue(validate_par(out)["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
