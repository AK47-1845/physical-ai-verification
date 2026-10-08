"""Briefing tests: NB walkthrough assembly + attention ordering.

Run from meta bro root:  python backend/tests/test_briefing.py
(stdlib only)
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.credibility import build_card  # noqa: E402
from engine.par import build_par  # noqa: E402

from backend.eval.briefing import BriefingError, briefing_view  # noqa: E402

SHA = "d" * 64
WEIGHTS = "sha256:" + "e" * 64


def _par(**kw):
    args = {"policy": {"id": "arm", "weights": WEIGHTS},
            "release": {"parent": WEIGHTS, "delta": "IN-ODD"},
            "gates": [{"id": "t", "verdict": "PASS", "evidence": "ev:1"}],
            "ledger_head": SHA, "odd": "test cell",
            "independence": {"builder": "B", "funder": "F",
                             "relationship": "none"}}
    args.update(kw)
    return build_par(**args)


def _card(**kw):
    args = {"gate_id": "t", "gate_version": "1.0", "corpus_hash": SHA,
            "n": 50, "false_positives": 0, "false_negatives": 0,
            "label_counts": {"pass": 50},
            "calibration_bins": [{"lo": 0.0, "hi": 1.0, "predicted": 0.9,
                                  "observed": 0.9, "n": 50}],
            "rollout_types": {"policy-sampled": 50}, "transfer_error": None,
            "search_hits": 0, "date": "2026-10-04", "analyst": "qa"}
    args.update(kw)
    return build_card(**args)


class TestBriefing(unittest.TestCase):
    def test_full_briefing_ok(self):
        out = briefing_view(_par(), worksheet={"implied_route": "R",
                                               "banner": "B"},
                            cards=[_card()],
                            ledger_verdict={"ok": True, "entries": 3})
        self.assertEqual(len(out["sections"]), 7)
        self.assertEqual(out["sections"][0]["title"], "Scoping")
        self.assertEqual(out["attention"], [])
        self.assertEqual(out["blocked_count"], 0)

    def test_attention_first(self):
        par = _par(gates=[{"id": "t", "verdict": "BLOCKED"},
                          {"id": "u", "verdict": "INSUFFICIENT"}],
                   release={"parent": WEIGHTS,
                            "delta": "SUBSTANTIAL_MODIFICATION_CANDIDATE"})
        out = briefing_view(par)
        self.assertIn("release: SUBSTANTIAL_MODIFICATION_CANDIDATE",
                      out["attention"])
        self.assertIn("gate BLOCKED: t", out["attention"])
        self.assertIn("gate INSUFFICIENT (missing evidence): u",
                      out["attention"])
        self.assertIn("worksheet: missing (route unimplied)",
                      out["attention"])
        self.assertIn("ledger: unverified in this briefing", out["attention"])

    def test_card_lift_surfaced(self):
        out = briefing_view(_par(), cards=[_card(n=2)])
        self.assertIn("credibility: t cannot lift DRAFT", out["attention"])

    def test_invalid_par_refused(self):
        par = _par()
        par["par"]["gates"] = []
        with self.assertRaises(BriefingError):
            briefing_view(par)

    def test_stripped_but_resealed_is_briefing_error(self):
        from engine import canonical_hash
        par = _par()
        del par["par"]["release"]
        par["par_hash"] = canonical_hash(par["par"])
        with self.assertRaises(BriefingError) as ctx:
            briefing_view(par)  # must raise BriefingError, not KeyError
        self.assertIn("incomplete", str(ctx.exception))


def _sheet(**kw):
    args = {"product": "arm", "analyst": "qa",
            "answers": {"ml_safety_function": True,
                        "self_evolving": True,
                        "frozen_weight_ota": False},
            "implied_route": "PART_A_5_6_NOTIFIED_BODY_ROUTE",
            "banner": "BANNER"}
    args.update(kw)
    return args


class TestScoping(unittest.TestCase):
    def test_scoping_is_first(self):
        out = briefing_view(_par(), worksheet=_sheet())
        self.assertEqual(out["sections"][0]["title"], "Scoping")
        rows = out["sections"][0]["rows"]
        self.assertIn("Does the ML component ensure a safety function",
                      rows["question"])
        self.assertEqual(rows["ml_safety_function"], "Y")
        self.assertIn("notified-body", rows["guidance"])
        self.assertIn("review required", rows["guidance"])

    def test_scoping_negative_route(self):
        sheet = _sheet(
            answers={"ml_safety_function": False,
                     "self_evolving": False,
                     "frozen_weight_ota": False},
            implied_route="OUT_OF_SCOPE_CANDIDATE")
        rows = briefing_view(_par(), worksheet=sheet)["sections"][0]["rows"]
        self.assertEqual(rows["ml_safety_function"], "N")
        self.assertIn("independent safety architecture",
                      rows["guidance"])

    def test_scoping_missing_worksheet(self):
        out = briefing_view(_par())
        rows = out["sections"][0]["rows"]
        self.assertEqual(rows["ml_safety_function"], "UNANSWERED")
        self.assertIn("worksheet: missing (route unimplied)",
                      out["attention"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
