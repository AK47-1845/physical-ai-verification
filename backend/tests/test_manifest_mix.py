"""Provenance tests: batch manifests + mix ledger.

Run from meta bro root:  python backend/tests/test_manifest_mix.py
(stdlib only; backend + packages both on path below)
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from backend.provenance.manifest import ManifestError, stamp_batch, verify_manifest  # noqa: E402
from backend.provenance.mixtrack import (  # noqa: E402
    MixError,
    add_generation,
    build_dataset_card,
    enforce_alpha,
    lineage_risk,
    new_corpus,
    reanchor_status,
    registry_verify,
)

GEN = {"name": "axiom-tabular", "version": "0.3.0"}
HASH = "a" * 64
INGS = [{"kind": "real", "n_rows": 1000, "content_hash": "b" * 64}]


def _stamp(**kw):
    args = {"generator": GEN, "seed": 7, "content_hash": HASH,
            "n_rows": 500, "ingredients": INGS}
    args.update(kw)
    return stamp_batch(**args)


class TestManifest(unittest.TestCase):
    def test_stamp_and_verify_ok(self):
        manifest = _stamp()
        result = verify_manifest(manifest)
        self.assertTrue(result["ok"])
        self.assertFalse(result["signed"])
        self.assertEqual(result["manifest_id"], manifest["manifest_id"])

    def test_deterministic_ids(self):
        self.assertEqual(_stamp(), _stamp())

    def test_seed_changes_id(self):
        self.assertNotEqual(_stamp()["manifest_id"],
                            _stamp(seed=8)["manifest_id"])

    def test_tampered_body_fails(self):
        manifest = _stamp()
        manifest["body"]["seed"] = 999
        result = verify_manifest(manifest)
        self.assertFalse(result["ok"])

    def test_tampered_id_fails(self):
        manifest = _stamp()
        manifest["manifest_id"] = "0" * 64
        self.assertFalse(verify_manifest(manifest)["ok"])

    def test_bad_inputs_raise(self):
        with self.assertRaises(ManifestError):
            _stamp(generator={"name": "x"})
        with self.assertRaises(ManifestError):
            _stamp(content_hash="not-a-hash")
        with self.assertRaises(ManifestError):
            _stamp(ingredients=[])
        with self.assertRaises(ManifestError):
            _stamp(ingredients=[{"kind": "alien", "n_rows": 1}])

    def test_bool_seed_and_seq_rejected(self):
        with self.assertRaises(ManifestError):
            _stamp(seed=True)
        with self.assertRaises(ManifestError):
            _stamp(batch_seq=False)

    def test_garbage_verifies_false_not_raise(self):
        self.assertFalse(verify_manifest({})["ok"])
        self.assertFalse(verify_manifest("nope")["ok"])


class TestMixTrack(unittest.TestCase):
    def test_alpha_math(self):
        corpus = new_corpus("c1")
        gen = add_generation(corpus, real_rows=100,
                             synth_batches=[{"manifest_id": "m1",
                                             "n_rows": 300}])
        self.assertEqual(gen["alpha"], 0.25)
        self.assertEqual(gen["gen"], 0)

    def test_accumulate_verdict(self):
        corpus = new_corpus("c1")
        add_generation(corpus, real_rows=1000, synth_batches=[])
        add_generation(corpus, real_rows=1000,
                       synth_batches=[{"manifest_id": "m1", "n_rows": 500}])
        risk = lineage_risk(corpus)
        self.assertEqual(risk["verdict"], "ACCUMULATE")
        self.assertEqual(risk["replace_events"], [])

    def test_replace_detected(self):
        corpus = new_corpus("c1")
        add_generation(corpus, real_rows=1000, synth_batches=[])
        add_generation(corpus, real_rows=0,
                       synth_batches=[{"manifest_id": "m1", "n_rows": 500}])
        risk = lineage_risk(corpus)
        self.assertEqual(risk["verdict"], "SYNTHETIC_ONLY")
        self.assertEqual(risk["replace_events"], [1])

    def test_unstamped_synthetic_rejected(self):
        corpus = new_corpus("c1")
        with self.assertRaises(MixError):
            add_generation(corpus, real_rows=10,
                           synth_batches=[{"n_rows": 5}])

    def test_empty_guards(self):
        with self.assertRaises(MixError):
            new_corpus("")
        with self.assertRaises(MixError):
            add_generation(new_corpus("c"), real_rows=0, synth_batches=[])
        risk = lineage_risk(new_corpus("c"))
        self.assertEqual(risk["verdict"], "INSUFFICIENT")

    def test_mistyped_history_rejected(self):
        base = {"gen": 0, "real_rows": 10, "synth_rows": 0,
                "alpha": 1.0, "manifest_ids": []}
        for bad in ({"real_rows": "10"}, {"synth_rows": 1.5},
                    {"alpha": "high"}, {"manifest_ids": "m1"}):
            corpus = {"corpus_id": "c",
                      "generations": [dict(base, **bad)]}
            with self.assertRaises(MixError, msg=bad):
                lineage_risk(corpus)


class TestDatasetCard(unittest.TestCase):
    def test_card_fields(self):
        card = build_dataset_card(
            dataset_id="d1", generator={"id": "axiom", "version": "0.3"},
            verifier={"id": "collapse-watch", "version": "1"},
            real_rows=800, synth_rows=200, pass_rate=0.97,
            manifest_ids=["m-1"])
        self.assertEqual(card["alpha"], 0.8)
        self.assertEqual(card["pass_rate"], 0.97)
        self.assertEqual(len(card["card_hash"]), 64)
        self.assertEqual(card["verifier"]["id"], "collapse-watch")

    def test_pure_real_needs_no_manifests(self):
        card = build_dataset_card(
            dataset_id="d2", generator={"id": "g", "version": "1"},
            verifier={"id": "v"}, real_rows=50, synth_rows=0,
            pass_rate=1.0)
        self.assertEqual(card["alpha"], 1.0)
        self.assertEqual(card["manifest_ids"], [])

    def test_refusals(self):
        good = {"dataset_id": "d", "generator": {"id": "g", "version": "1"},
                "verifier": {"id": "v"}, "real_rows": 10, "synth_rows": 5,
                "pass_rate": 0.9, "manifest_ids": ["m"]}
        with self.assertRaises(MixError):  # unstamped synthetic
            build_dataset_card(**dict(good, manifest_ids=[]))
        with self.assertRaises(MixError):  # manifests but no synth
            build_dataset_card(**dict(good, synth_rows=0))
        with self.assertRaises(MixError):  # empty dataset
            build_dataset_card(**dict(good, real_rows=0, synth_rows=0,
                                      manifest_ids=[]))
        for bad_rate in (-0.1, 1.1, True, "high"):
            with self.assertRaises(MixError):
                build_dataset_card(**dict(good, pass_rate=bad_rate))
        for bad_ids in ("m1", {"m1"}, 42):
            with self.assertRaises(MixError, msg=repr(bad_ids)):
                build_dataset_card(**dict(good, manifest_ids=bad_ids))


class TestEnforceAlpha(unittest.TestCase):
    def _corpus(self):
        corpus = new_corpus("c")
        add_generation(corpus, real_rows=800,
                       synth_batches=[{"manifest_id": "m", "n_rows": 200}])
        return corpus

    def test_breach_blocks(self):
        out = enforce_alpha(profile_max_synth=0.1,
                            corpus=self._corpus())
        self.assertEqual(out["status"], "BLOCKED")
        self.assertAlmostEqual(out["measured_synth_frac"], 0.2)
        self.assertEqual(out["profile_max_synth"], 0.1)

    def test_within_passes(self):
        out = enforce_alpha(profile_max_synth=0.5,
                            corpus=self._corpus())
        self.assertEqual(out["status"], "PASS")
        self.assertAlmostEqual(out["measured_synth_frac"], 0.2)

    def test_empty_is_insufficient(self):
        out = enforce_alpha(profile_max_synth=0.5,
                            corpus=new_corpus("empty"))
        self.assertEqual(out["status"], "INSUFFICIENT")

    def test_bad_max_raises(self):
        for bad in (-0.1, 1.5, True, "half"):
            with self.assertRaises(MixError):
                enforce_alpha(profile_max_synth=bad,
                              corpus=self._corpus())

    def test_corrupt_alpha_raises(self):
        corpus = {"corpus_id": "c", "generations": [
            {"gen": 0, "real_rows": 1, "synth_rows": 1, "alpha": 5.0,
             "manifest_ids": ["m"]}]}
        with self.assertRaises(MixError):
            enforce_alpha(profile_max_synth=0.5, corpus=corpus)


class TestRegistry(unittest.TestCase):
    def test_record_and_verify(self):
        corpus = new_corpus("c")
        rec = add_generation(
            corpus, real_rows=10,
            synth_batches=[{"manifest_id": "m", "n_rows": 3,
                            "sample_ids": ["s1", "s2", "s3"]}])
        self.assertEqual(rec["sample_registry"]["m"]["n"], 3)
        out = registry_verify(corpus, 0, "m", ["s3", "s1", "s2"])
        self.assertTrue(out["ok"])
        self.assertEqual(out["n"], 3)

    def test_tamper_detected(self):
        corpus = new_corpus("c")
        add_generation(
            corpus, real_rows=10,
            synth_batches=[{"manifest_id": "m", "n_rows": 2,
                            "sample_ids": ["s1", "s2"]}])
        out = registry_verify(corpus, 0, "m", ["s1", "s2", "s3"])
        self.assertFalse(out["ok"])
        out = registry_verify(corpus, 0, "m", ["s1", "other"])
        self.assertFalse(out["ok"])

    def test_missing_registry_is_outcome(self):
        corpus = new_corpus("c")
        add_generation(corpus, real_rows=10,
                       synth_batches=[{"manifest_id": "m", "n_rows": 2}])
        out = registry_verify(corpus, 0, "m", ["s1", "s2"])
        self.assertFalse(out["ok"])
        self.assertIn("no sample registry", out["reason"])

    def test_dupes_and_empties_raise(self):
        corpus = new_corpus("c")
        with self.assertRaises(MixError):
            add_generation(
                corpus, real_rows=10,
                synth_batches=[{"manifest_id": "m", "n_rows": 2,
                                "sample_ids": ["s1", "s1"]}])
        with self.assertRaises(MixError):
            add_generation(
                corpus, real_rows=10,
                synth_batches=[{"manifest_id": "m", "n_rows": 0,
                                "sample_ids": []}])

    def test_bad_refs_raise(self):
        corpus = new_corpus("c")
        with self.assertRaises(MixError):
            registry_verify(corpus, 5, "m", ["s1"])
        with self.assertRaises(MixError):
            registry_verify(corpus, 0, "", ["s1"])

    def test_corrupt_registry_shape_raises(self):
        corpus = {"corpus_id": "c",
                  "generations": [{"gen": 0, "sample_registry": ["m"]}]}
        with self.assertRaises(MixError):
            registry_verify(corpus, 0, "m", ["s1"])


class TestReanchor(unittest.TestCase):
    def test_fresh_is_ok(self):
        out = reanchor_status(created_ts=1_000_000, cadence_days=30,
                              now_ts=1_000_000 + 10 * 86400)
        self.assertEqual((out["status"], out["stale"]), ("OK", False))
        self.assertAlmostEqual(out["age_days"], 10.0)

    def test_stale_is_review(self):
        out = reanchor_status(created_ts=1_000_000, cadence_days=30,
                              now_ts=1_000_000 + 31 * 86400)
        self.assertEqual((out["status"], out["stale"]), ("REVIEW", True))

    def test_bad_inputs_raise(self):
        with self.assertRaises(MixError):
            reanchor_status(created_ts=2_000_000, cadence_days=30,
                            now_ts=1_000_000)
        with self.assertRaises(MixError):
            reanchor_status(created_ts=1_000_000, cadence_days=0,
                            now_ts=1_000_000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
