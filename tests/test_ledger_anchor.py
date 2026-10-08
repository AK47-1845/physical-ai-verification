"""Ledger anchor: out-of-band truncation/rollback detection.

Run from meta bro root:  python tests/test_ledger_anchor.py
verify() alone checks internal links: a chain cut short, or fully
rewritten as self-consistent, still verifies. anchor() captures
(schema, length, head_hash) to store OUT-OF-BAND (separate repo,
email, printout); verify(chain, anchor=...) then detects truncation
and wholesale forgery. This test documents exactly what is and is
not detected in each mode. par_cli gains `anchor` / `verify` subs.
"""

import copy
import json
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.ledger import anchor, append, dumps, verify  # noqa: E402

from backend.par_cli import main as par_cli_main  # noqa: E402


def build_chain(n=5):
    chain = []
    for i in range(n):
        append(chain, "EVT", {"seq": i}, f"2026-10-04T00:00:0{i}Z")
    return chain


def tamper_each_field(chain):
    """Yield (label, tampered-chain) with one byte changed per field."""
    for pos, entry in enumerate(chain):
        for key in ("index", "timestamp", "type", "payload_hash",
                    "prev", "hash"):
            bad = copy.deepcopy(chain)
            val = bad[pos][key]
            if isinstance(val, int):
                bad[pos][key] = val + 1
            else:
                bad[pos][key] = val[:-1] + ("X" if val[-1:] != "X" else "Y")
            yield f"entry {pos} field {key}", bad


class TestAnchor(unittest.TestCase):
    def test_anchor_shape(self):
        pack = anchor(build_chain(5))
        self.assertEqual(pack["schema"], "ledger-anchor/1")
        self.assertEqual(pack["length"], 5)
        self.assertEqual(len(pack["head_hash"]), 64)

    def test_anchor_empty_chain(self):
        pack = anchor([])
        self.assertEqual(pack["length"], 0)
        self.assertTrue(verify([], anchor=pack)["ok"])

    def test_pristine_with_anchor(self):
        chain = build_chain()
        self.assertTrue(verify(chain, anchor=anchor(chain))["ok"])

    def test_truncate_detected_with_anchor(self):
        chain = build_chain()
        pack = anchor(chain)
        for cut in (chain[:-1], chain[: len(chain) // 2], []):
            result = verify(cut, anchor=pack)
            self.assertFalse(result["ok"], f"cut to {len(cut)} undetected")
            self.assertIn("anchor", result["reason"].lower())

    def test_truncate_not_detected_without_anchor(self):
        # Honest gap, documented: internal links cannot see a cut tail.
        chain = build_chain()
        self.assertTrue(verify(chain[:-1])["ok"])

    def test_forged_chain_detected_with_anchor(self):
        chain = build_chain()
        pack = anchor(chain)
        forged = []
        for i in range(len(chain)):
            append(forged, "EVT", {"seq": i, "evil": True},
                   f"2026-10-04T00:00:0{i}Z")
        self.assertTrue(verify(forged)["ok"])  # self-consistent: passes
        result = verify(forged, anchor=pack)
        self.assertFalse(result["ok"])
        self.assertIn("anchor", result["reason"].lower())

    def test_reorder_dupe_detected_both_modes(self):
        chain = build_chain()
        pack = anchor(chain)
        swapped = copy.deepcopy(chain)
        swapped[1], swapped[2] = swapped[2], swapped[1]
        duped = copy.deepcopy(chain)
        duped.insert(2, copy.deepcopy(chain[2]))
        for bad in (swapped, duped):
            self.assertFalse(verify(bad)["ok"])
            self.assertFalse(verify(bad, anchor=pack)["ok"])

    def test_byte_edits_detected_both_modes(self):
        chain = build_chain()
        pack = anchor(chain)
        count = 0
        for _label, bad in tamper_each_field(chain):
            self.assertFalse(verify(bad)["ok"], _label)
            self.assertFalse(verify(bad, anchor=pack)["ok"], _label)
            count += 1
        self.assertEqual(count, 5 * 6)

    def test_malformed_anchor_fails_loudly(self):
        chain = build_chain()
        for bad in ({"schema": "nope", "length": 5,
                         "head_hash": "x"},
                    {"schema": "ledger-anchor/1", "length": -1,
                     "head_hash": "x" * 64},
                    {"schema": "ledger-anchor/1", "length": 99,
                     "head_hash": "x" * 64},
                    {"schema": "ledger-anchor/1"},
                    "not-a-dict",
                    {"schema": "ledger-anchor/1", "length": 5,
                     "head_hash": "x" * 64, "note": "human text ok"}):
            result = verify(chain, anchor=bad)
            self.assertFalse(result["ok"], f"anchor {bad!r} accepted")

    def test_anchor_note_field_ignored(self):
        chain = build_chain()
        pack = anchor(chain)
        pack["note"] = "mailed to auditor 2026-10-04 (human text, unhashed)"
        self.assertTrue(verify(chain, anchor=pack)["ok"])

    def test_wrong_head_hash_detected(self):
        chain = build_chain()
        pack = anchor(chain)
        pack["head_hash"] = "0" * 64
        result = verify(chain, anchor=pack)
        self.assertFalse(result["ok"])
        self.assertIn("anchor", result["reason"].lower())


class TestParCliLedgerSubs(unittest.TestCase):
    def setUp(self):
        self.scratch = os.path.join(BASE, "tests", "_anchor_tmp")
        os.makedirs(self.scratch, exist_ok=True)
        self.addCleanup(self._wipe)

    def _wipe(self):
        for name in os.listdir(self.scratch):
            os.remove(os.path.join(self.scratch, name))
        os.rmdir(self.scratch)

    def _write_chain(self, name="chain.jsonl"):
        path = os.path.join(self.scratch, name)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(dumps(build_chain()))
        return path

    def test_anchor_sub_writes_file(self):
        ledger = self._write_chain()
        code = par_cli_main(["par_cli.py", "anchor", ledger])
        self.assertEqual(code, 0)
        with open(ledger + ".anchor.json", encoding="utf-8") as handle:
            pack = json.load(handle)
        self.assertEqual(pack["schema"], "ledger-anchor/1")
        self.assertEqual(pack["length"], 5)

    def test_verify_sub_with_anchor(self):
        ledger = self._write_chain()
        self.assertEqual(par_cli_main(["par_cli.py", "anchor", ledger]), 0)
        anchor_path = ledger + ".anchor.json"
        self.assertEqual(par_cli_main(
            ["par_cli.py", "verify", ledger, "--anchor", anchor_path]), 0)
        with open(ledger, encoding="utf-8") as handle:
            lines = [line for line in handle if line.strip()]
        with open(ledger, "w", encoding="utf-8", newline="\n") as handle:
            handle.writelines(lines[:-1])  # truncate the tail
        self.assertEqual(par_cli_main(
            ["par_cli.py", "verify", ledger, "--anchor", anchor_path]), 2)

    def test_verify_sub_without_anchor(self):
        ledger = self._write_chain()
        self.assertEqual(par_cli_main(["par_cli.py", "verify", ledger]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
