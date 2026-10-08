"""Hazard trace: customer hazards mapped to covering gates.

Run from meta bro root:  python tests/test_hazard_trace.py
build_par accepts an optional hazard_trace (customer's risk
assessment, ISO 12100-style, reference only): each entry maps a
hazard_id to gate_ids. briefing_view renders a Hazard coverage
section with explicit gaps, and flags each uncovered hazard in
attention. Absent trace: no section (old PARs unaffected).
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.par import PARError, build_par  # noqa: E402

from backend.eval.briefing import briefing_view  # noqa: E402

W = "sha256:" + "ab" * 32


def _par(**kw):
    args = {"policy": {"id": "p", "weights": W},
            "release": {"parent": W, "delta": "IN-ODD"},
            "gates": [{"id": "g1", "verdict": "PASS"},
                      {"id": "g2", "verdict": "REVIEW"}],
            "ledger_head": "cd" * 32, "odd": "test cell",
            "independence": {"builder": "b", "funder": "f",
                             "relationship": "none"}}
    args.update(kw)
    return build_par(**args)


class TestHazardTrace(unittest.TestCase):
    def test_covered_and_gaps(self):
        par = _par(hazard_trace=[
            {"hazard_id": "H1", "gate_ids": ["g1"]},
            {"hazard_id": "H2", "gate_ids": ["g9"]},
            {"hazard_id": "H3", "gate_ids": []}])
        out = briefing_view(par)
        section = [s for s in out["sections"]
                   if s["title"] == "Hazard coverage"][0]
        self.assertEqual(section["rows"]["covered"], ["H1"])
        self.assertEqual(section["rows"]["gaps"], ["H2", "H3"])
        self.assertIn("hazard H2 has no covering gate",
                      out["attention"])
        self.assertIn("hazard H3 has no covering gate",
                      out["attention"])

    def test_absent_trace_no_section(self):
        out = briefing_view(_par())
        titles = [s["title"] for s in out["sections"]]
        self.assertNotIn("Hazard coverage", titles)

    def test_empty_trace_empty_section(self):
        out = briefing_view(_par(hazard_trace=[]))
        section = [s for s in out["sections"]
                   if s["title"] == "Hazard coverage"][0]
        self.assertEqual(section["rows"], {"covered": [], "gaps": []})

    def test_malformed_trace_rejected(self):
        for bad in ("xx", [{"hazard_id": "", "gate_ids": []}],
                    [{"hazard_id": "H", "gate_ids": "g1"}],
                    [{"hazard_id": "H"}],
                    [{"gate_ids": []}], ["xx"]):
            with self.assertRaises(PARError, msg=f"accepted: {bad!r}"):
                _par(hazard_trace=bad)


if __name__ == "__main__":
    unittest.main(verbosity=2)
