"""FR-19 report tests: standalone HTML evidence export.

Run from meta bro root:  python tests/test_report.py
(stdlib only)
"""

import hashlib
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.par import build_par  # noqa: E402
from engine.report import ReportError, render_report_html  # noqa: E402
from engine.scorer import evaluate_gate, evaluate_scorecard  # noqa: E402

W = "sha256:" + "c" * 64
P = "sha256:" + "d" * 64
HEAD = "e" * 64
INDEP = {"builder": "oem-x", "funder": "oem-x", "relationship": "none"}


def _par(**kw):
    args = {"policy": {"id": "pol-1", "weights": W},
            "release": {"parent": P, "delta": "IN-ODD"},
            "gates": [{"id": "G2", "verdict": "PASS", "measurement": 0.1,
                       "evidence": "run-1"}],
            "ledger_head": HEAD, "independence": INDEP, "odd": "test cell"}
    args.update(kw)
    return build_par(**args)


class TestReport(unittest.TestCase):
    def test_renders_and_hashes(self):
        out = render_report_html(_par())
        self.assertIn("pol-1", out["html"])
        self.assertIn("G2", out["html"])
        self.assertIn("PASS", out["html"])
        self.assertIn(out["par_hash"], out["html"])
        expect = hashlib.sha256(
            out["html"].encode("utf-8")).hexdigest()
        self.assertEqual(out["html_hash"], expect)
        self.assertEqual(out["blocked"], 0)

    def test_escapes_xss(self):
        evil = _par(policy={"id": "<script>alert(1)</script>",
                            "weights": W})
        out = render_report_html(evil)
        self.assertNotIn("<script>", out["html"])
        self.assertIn("&lt;script&gt;", out["html"])

    def test_invalid_par_raises(self):
        bad = _par()
        bad["par_hash"] = "0" * 64
        with self.assertRaises(ReportError):
            render_report_html(bad)

    def test_null_measurement_renders_na(self):
        par = _par(gates=[{"id": "G9", "verdict": "REVIEW",
                           "measurement": None, "evidence": None}])
        out = render_report_html(par)
        self.assertIn("n/a", out["html"])
        self.assertIn("REVIEW", out["html"])

    def test_scorecard_crosslink(self):
        gate = evaluate_gate("G2", 0.1, green=0.15, amber=0.5,
                             evidence="run-1")
        card = evaluate_scorecard([gate], profile_version="v1", seed=1)
        out = render_report_html(_par(), scorecard=card)
        self.assertIn(card["inputs_hash"][:16], out["html"])
        self.assertIn("TRUSTED", out["html"])

    def test_bad_scorecard_raises(self):
        with self.assertRaises(ReportError):
            render_report_html(_par(), scorecard={"nope": True})

    def test_worksheet_banner_surfaced(self):
        par = _par(worksheet={"implied_route": "PART_A_5_6",
                              "banner": "HUMAN AND LEGAL REVIEW REQUIRED"})
        out = render_report_html(par)
        self.assertIn("PART_A_5_6", out["html"])
        self.assertIn("HUMAN AND LEGAL REVIEW REQUIRED", out["html"])

    def test_deterministic(self):
        self.assertEqual(render_report_html(_par()),
                         render_report_html(_par()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
