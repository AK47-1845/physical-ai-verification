"""FR-20 regmap tests: regulation-row draft mappings.

Run from meta bro root:  python tests/test_regmap.py
(stdlib only)
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.regmap import BANNER, ROWS, RegmapError, map_rows  # noqa: E402


def _row(out, rid):
    return next(r for r in out["rows"] if r["id"] == rid)


class TestRegmap(unittest.TestCase):
    def test_banner_always_attached(self):
        out = map_rows({})
        self.assertEqual(out["banner"], BANNER)
        self.assertIn("HUMAN AND LEGAL REVIEW REQUIRED", out["banner"])

    def test_blocked_propagates(self):
        out = map_rows({"G2": "BLOCKED", "G1": "PASS"})
        self.assertEqual(_row(out, "MR-ANNEX-IV")["evidence"], "BLOCKED")

    def test_review_and_insufficient_propagate(self):
        out = map_rows({"G7": "INSUFFICIENT"})
        self.assertEqual(_row(out, "AI-ART-10")["evidence"], "REVIEW")
        out = map_rows({"G1": "REVIEW"})
        self.assertEqual(_row(out, "AI-ART-15")["evidence"], "REVIEW")

    def test_best_is_evidence_present_never_pass(self):
        out = map_rows({"G1": "PASS", "G2": "PASS"})
        row = _row(out, "MR-ANNEX-IV")
        self.assertEqual(row["evidence"], "EVIDENCE_PRESENT")
        for r in out["rows"]:
            self.assertNotIn(r["evidence"], ("PASS", "CONFORMANT",
                                             "COMPLIANT"))

    def test_unlinked_when_nothing_scored(self):
        out = map_rows({})
        self.assertEqual(_row(out, "AI-ART-12")["evidence"], "UNLINKED")
        self.assertEqual(_row(out, "MR-ANNEX-IV")["evidence"], "UNLINKED")

    def test_unknown_gates_ignored(self):
        out = map_rows({"G99": "BLOCKED", "G1": "PASS"})
        self.assertEqual(_row(out, "MR-ANNEX-IV")["evidence"],
                         "EVIDENCE_PRESENT")

    def test_bad_verdict_raises(self):
        with self.assertRaises(RegmapError):
            map_rows({"G1": "TRUSTED"})
        with self.assertRaises(RegmapError):
            map_rows({"G1": "PASS"}, release_delta="SHIPPED")

    def test_release_candidate_is_review(self):
        out = map_rows({}, release_delta="SUBSTANTIAL_MODIFICATION"
                                         "_CANDIDATE")
        self.assertEqual(_row(out, "MR-SUBSTANTIAL")["evidence"], "REVIEW")
        out = map_rows({}, release_delta="IN-ODD")
        self.assertEqual(_row(out, "MR-SUBSTANTIAL")["evidence"],
                         "EVIDENCE_PRESENT")

    def test_draft_honesty(self):
        row = _row(map_rows({"G11": "PASS"}), "ISO-25785-1")
        self.assertEqual(row["mapping"], "UNDER_DEVELOPMENT")
        text = " ".join(r["topic"] + " " + r["gap"] for r in ROWS).lower()
        self.assertNotIn("shall", text)  # no clause text, ever

    def test_deterministic(self):
        kw = {"gate_verdicts": {"G1": "PASS", "G5": "REVIEW"}}
        self.assertEqual(map_rows(**kw), map_rows(**kw))

    def test_part_a_row(self):
        row = _row(map_rows({}), "MR-PART-A")
        self.assertEqual(row["route"], "PRIMARY")
        self.assertEqual(row["mapping"], "DRAFT_MAPPING")
        self.assertEqual(row["applies"], "2027-01-20")
        self.assertIn("UNVERIFIED-CLAUSE", row["gap"])

    def test_route_priorities(self):
        out = map_rows({})
        for rid in ("MR-ANNEX-IV", "MR-SUBSTANTIAL", "MR-EHSR-CTRL",
                    "MR-PART-A"):
            self.assertEqual(_row(out, rid)["route"], "PRIMARY", rid)
        for rid in ("AI-ART-10", "AI-ART-12", "AI-ART-14", "AI-ART-15"):
            self.assertEqual(_row(out, rid)["route"], "SECONDARY", rid)
        for rid in ("ISO-10218-535", "ISO-25785-1"):
            self.assertIsNone(_row(out, rid)["route"], rid)

    def test_item_numbers_labeled_unverified(self):
        out = map_rows({})
        sub = _row(out, "MR-SUBSTANTIAL")
        self.assertIn("UNVERIFIED-CLAUSE", sub["gap"])
        iso = _row(out, "ISO-10218-535")
        self.assertIn("UNVERIFIED-CLAUSE", iso["gap"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
