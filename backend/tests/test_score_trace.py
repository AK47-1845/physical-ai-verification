"""Trace scoring tests: pipeline verdicts, profiles, refusals.

Run from meta bro root:  python backend/tests/test_score_trace.py
(stdlib only)
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from backend.eval.score_trace import ScoreError, score_trace  # noqa: E402

REF = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]


class TestScoreTrace(unittest.TestCase):
    def test_identical_is_trusted(self):
        card = score_trace(REF, REF, seed=1)
        self.assertEqual(card["payload"]["verdict"], "TRUSTED")
        self.assertEqual(len(card["payload"]["gates"]), 4)
        self.assertIn("envelope_hash", card)

    def test_shifted_is_blocked(self):
        moved = [(x + 1.0, y) for x, y in REF]
        card = score_trace(REF, moved, seed=1)
        self.assertEqual(card["payload"]["verdict"], "BLOCKED")

    def test_deterministic(self):
        moved = [(x + 0.1, y) for x, y in REF]
        a = score_trace(REF, moved, seed=2)
        b = score_trace(REF, moved, seed=2)
        self.assertEqual(a, b)

    def test_custom_profile_subset(self):
        profile = {"version": "coherence-only",
                   "gates": [{"id": "coh", "kind": "coherence_ratio",
                              "green": 0.5, "amber": 0.8, "higher": True}]}
        card = score_trace(REF, REF, profile=profile, seed=1)
        self.assertEqual(card["payload"]["verdict"], "TRUSTED")
        self.assertEqual(card["profile_version"], "coherence-only")

    def test_unknown_kind_raises(self):
        profile = {"version": "bad",
                   "gates": [{"id": "x", "kind": "vibes",
                              "green": 0.1, "amber": 0.2}]}
        with self.assertRaises(ScoreError):
            score_trace(REF, REF, profile=profile)

    def test_mismatched_lengths_raise(self):
        with self.assertRaises(ScoreError):
            score_trace(REF, [(0.0, 0.0)], seed=1)

    def test_bad_evidence_prefix_raises(self):
        for bad in (None, "", 5):
            with self.assertRaises(ScoreError, msg=bad):
                score_trace(REF, REF, seed=1, evidence_prefix=bad)

    def test_bad_seeds_rejected(self):
        for bad in (True, b"audit", [1], {"s": 1}):
            with self.assertRaises(ScoreError, msg=repr(bad)):
                score_trace(REF, REF, seed=bad)
        card = score_trace(REF, REF, seed="audit-7")
        self.assertEqual(card["payload"]["seed"], "audit-7")

    def test_nonbool_higher_rejected(self):
        profile = {"version": "evil",
                   "gates": [{"id": "coh", "kind": "coherence_ratio",
                              "green": 0.5, "amber": 0.8,
                              "higher": "false"}]}
        with self.assertRaises(ScoreError):
            score_trace(REF, REF, profile=profile, seed=1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
