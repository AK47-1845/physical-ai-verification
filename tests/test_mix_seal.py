"""Mix-ledger seals: in-place mutation of history fails loudly.

Run from meta bro root:  python tests/test_mix_seal.py
Each generation carries a seal chained to the previous seal
(minimal fix for D-night-10). lineage_risk and registry_verify
re-verify seals on read: mutating a stored mix file in place
raises MixError. Pre-seal (legacy) histories still read, flagged
with sealed/legacy counts. Known residuals (documented, not
fixed here): tail truncation and full seal-stripping are
invisible without an externally pinned head.
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from backend.provenance.mixtrack import (  # noqa: E402
    MixError,
    add_generation,
    lineage_risk,
    new_corpus,
    registry_verify,
)

GEN = "m-test"


def sealed_corpus():
    corpus = new_corpus("sealed-c")
    add_generation(corpus, real_rows=100, synth_batches=[])
    add_generation(corpus, real_rows=50,
                   synth_batches=[{"manifest_id": GEN, "n_rows": 50,
                                   "sample_ids": ["s1", "s2"]}])
    return corpus


class TestMixSeal(unittest.TestCase):
    def test_round_trip_counts(self):
        risk = lineage_risk(sealed_corpus())
        self.assertEqual(risk["verdict"], "ACCUMULATE")
        self.assertEqual(risk["sealed"], 2)
        self.assertEqual(risk["legacy"], 0)

    def test_mutated_alpha_fails(self):
        corpus = sealed_corpus()
        corpus["generations"][0]["alpha"] = 0.99
        with self.assertRaises(MixError):
            lineage_risk(corpus)

    def test_mutated_rows_fail(self):
        corpus = sealed_corpus()
        corpus["generations"][1]["real_rows"] = 51
        with self.assertRaises(MixError):
            lineage_risk(corpus)

    def test_mutated_manifests_fail(self):
        corpus = sealed_corpus()
        corpus["generations"][1]["manifest_ids"].append("m-evil")
        with self.assertRaises(MixError):
            lineage_risk(corpus)

    def test_mutated_registry_fails(self):
        corpus = sealed_corpus()
        entry = corpus["generations"][1]["sample_registry"][GEN]
        entry["ids_hash"] = "0" * 64
        with self.assertRaises(MixError):
            lineage_risk(corpus)
        with self.assertRaises(MixError):
            registry_verify(corpus, 1, GEN, ["s1", "s2"])

    def test_mutated_seal_value_fails(self):
        corpus = sealed_corpus()
        corpus["generations"][0]["seal"] = "f" * 64
        with self.assertRaises(MixError):
            lineage_risk(corpus)

    def test_deleted_middle_gen_fails(self):
        corpus = sealed_corpus()
        add_generation(corpus, real_rows=10, synth_batches=[])
        del corpus["generations"][1]
        with self.assertRaises(MixError):
            lineage_risk(corpus)

    def test_registry_verify_still_ok_when_pristine(self):
        corpus = sealed_corpus()
        result = registry_verify(corpus, 1, GEN, ["s1", "s2"])
        self.assertTrue(result["ok"])

    def test_legacy_history_reads_flagged(self):
        corpus = {"corpus_id": "legacy-c", "generations": [
            {"gen": 0, "real_rows": 10, "synth_rows": 0,
             "alpha": 1.0, "manifest_ids": []}]}
        risk = lineage_risk(corpus)
        self.assertEqual(risk["verdict"], "ACCUMULATE")
        self.assertEqual(risk["sealed"], 0)
        self.assertEqual(risk["legacy"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
