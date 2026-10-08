"""M6 tests: hash chain append, tamper detection, JSONL round-trip.

Run from meta bro root:  python tests/test_m6.py
(runs under unittest and pytest alike; stdlib only)
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.ledger import GENESIS_PREV, LedgerError, append, dumps, head, loads, verify  # noqa: E402


def _chain3():
    entries = []
    append(entries, "RUN_SEALED", {"run": "r1"}, "2026-10-04T00:00:00Z")
    append(entries, "PROFILE", {"v": "1.0"}, "2026-10-04T00:01:00Z")
    append(entries, "REVIEW", {"by": "qa"}, "2026-10-04T00:02:00Z")
    return entries


class TestLedger(unittest.TestCase):
    def test_append_and_verify_ok(self):
        entries = _chain3()
        self.assertEqual([e["index"] for e in entries], [0, 1, 2])
        self.assertEqual(entries[0]["prev"], GENESIS_PREV)
        self.assertEqual(entries[1]["prev"], entries[0]["hash"])
        result = verify(entries)
        self.assertEqual(result, {"ok": True, "entries": 3})

    def test_empty_chain_verifies(self):
        self.assertEqual(verify([]), {"ok": True, "entries": 0})

    def test_tampered_payload_hash_detected(self):
        entries = _chain3()
        entries[1]["payload_hash"] = "0" * 64
        result = verify(entries)
        self.assertFalse(result["ok"])
        self.assertEqual(result["first_bad"], 1)

    def test_tampered_type_detected(self):
        entries = _chain3()
        entries[2]["type"] = "FORGED"
        self.assertEqual(verify(entries)["first_bad"], 2)

    def test_reordered_chain_detected(self):
        entries = _chain3()
        entries[0], entries[1] = entries[1], entries[0]
        self.assertFalse(verify(entries)["ok"])

    def test_truncated_prev_detected(self):
        entries = _chain3()
        entries[2]["prev"] = GENESIS_PREV
        result = verify(entries)
        self.assertFalse(result["ok"])
        self.assertEqual(result["first_bad"], 2)

    def test_dumps_loads_roundtrip(self):
        entries = _chain3()
        clone = loads(dumps(entries))
        self.assertEqual(clone, entries)
        self.assertTrue(verify(clone)["ok"])

    def test_loads_rejects_garbage(self):
        with self.assertRaises(LedgerError):
            loads("{not json\n")
        with self.assertRaises(LedgerError):
            loads("[1, 2]\n")

    def test_deterministic_rebuild(self):
        self.assertEqual(_chain3(), _chain3())

    def test_bad_inputs_raise(self):
        with self.assertRaises(LedgerError):
            append([], "", {"a": 1}, "t")
        with self.assertRaises(LedgerError):
            append([], "T", {"a": 1}, "")
        with self.assertRaises(LedgerError):
            append([], "T", ["not", "dict"], "t")
        with self.assertRaises(LedgerError):
            append([], "T", {"v": float("nan")}, "t")

    def test_unhashable_entry_yields_verdict(self):
        entries = _chain3()
        entries[1]["timestamp"] = float("nan")
        result = verify(entries)  # must return, not raise
        self.assertFalse(result["ok"])
        self.assertEqual(result["first_bad"], 1)
        self.assertIn("unhashable", result["reason"])

    def test_append_validates_chain_container(self):
        with self.assertRaises(LedgerError):
            append({}, "T", {"a": 1}, "t")
        with self.assertRaises(LedgerError):
            append(["not-a-dict"], "T", {"a": 1}, "t")
        with self.assertRaises(LedgerError):
            append([{"index": 0}], "T", {"a": 1}, "t")

    def test_dumps_wraps_errors(self):
        with self.assertRaises(LedgerError):
            dumps([{"x": float("nan")}])
        with self.assertRaises(LedgerError):
            dumps({"not": "a list"})

    def test_verify_rejects_non_list(self):
        with self.assertRaises(LedgerError):
            verify(42)
        with self.assertRaises(LedgerError):
            verify("[]")

    def test_head_anchor_pattern(self):
        entries = _chain3()
        self.assertEqual(head(entries), entries[-1]["hash"])
        self.assertIsNone(head([]))
        cut = entries[:2]
        self.assertTrue(verify(cut)["ok"])  # links fine...
        self.assertNotEqual(head(cut), head(entries))  # ...anchor catches it
        with self.assertRaises(LedgerError):
            head([{"index": 0}])


if __name__ == "__main__":
    unittest.main(verbosity=2)
