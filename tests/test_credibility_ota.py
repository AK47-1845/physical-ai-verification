"""Credibility + OTA tests: FR-32 cards, vault lineage.

Run from meta bro root:  python tests/test_credibility_ota.py
(stdlib only)
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.credibility import CredibilityError, build_card, can_lift_draft  # noqa: E402
from engine.ota import OTAError, children_of, new_vault, register_release, rollout_line  # noqa: E402

SHA = "a" * 64
W1 = "sha256:" + "b" * 64
W2 = "sha256:" + "c" * 64


def _card(**kw):
    args = {"gate_id": "tracking", "gate_version": "1.0",
            "corpus_hash": SHA, "n": 120, "false_positives": 2,
            "false_negatives": 1, "label_counts": {"pass": 100, "fail": 20},
            "calibration_bins": [{"lo": 0.0, "hi": 0.5, "predicted": 0.2,
                                  "observed": 0.22, "n": 60}],
            "rollout_types": {"policy-sampled": 120},
            "transfer_error": 0.03, "search_hits": 0,
            "date": "2026-10-04", "analyst": "qa"}
    args.update(kw)
    return build_card(**args)


class TestCredibility(unittest.TestCase):
    def test_lifts_when_floors_met(self):
        out = can_lift_draft(_card())
        self.assertTrue(out["lift"])
        self.assertEqual(out["reasons"], [])

    def test_small_n_blocks(self):
        out = can_lift_draft(_card(n=5))
        self.assertFalse(out["lift"])
        self.assertTrue(any("n=5" in r for r in out["reasons"]))

    def test_search_hits_block(self):
        out = can_lift_draft(_card(search_hits=2))
        self.assertFalse(out["lift"])

    def test_optimised_against_blocks(self):
        out = can_lift_draft(_card(optimised_against=True))
        self.assertFalse(out["lift"])

    def test_tamper_blocks(self):
        envelope = _card()
        envelope["card"]["n"] = 9999
        out = can_lift_draft(envelope)
        self.assertFalse(out["lift"])

    def test_fp_rate_blocks(self):
        out = can_lift_draft(_card(false_positives=50))
        self.assertFalse(out["lift"])

    def test_bad_inputs_raise(self):
        with self.assertRaises(CredibilityError):
            _card(corpus_hash="nope")
        with self.assertRaises(CredibilityError):
            _card(label_counts={})

    def test_bool_and_nonfinite_rejected(self):
        for kw in ({"n": True}, {"false_positives": False},
                   {"search_hits": True},
                   {"label_counts": {"pass": True}},
                   {"transfer_error": True},
                   {"transfer_error": float("inf")},
                   {"calibration_bins": [{"lo": True, "hi": 0.5,
                                          "predicted": 0.2,
                                          "observed": 0.22, "n": 60}]}):
            with self.assertRaises(CredibilityError, msg=kw):
                _card(**kw)

    def test_unhashable_card_yields_verdict_not_raise(self):
        out = can_lift_draft({"card": {"n": float("nan")},
                              "card_hash": "0" * 64})
        self.assertFalse(out["lift"])
        self.assertTrue(any("unhashable" in r for r in out["reasons"]))
        out = can_lift_draft({"card": {"n": {1, 2}},
                              "card_hash": "0" * 64})
        self.assertFalse(out["lift"])
        self.assertTrue(any("unhashable" in r for r in out["reasons"]))

    def test_nonstring_keys_rejected(self):
        with self.assertRaises(CredibilityError):
            _card(label_counts={1: 5})
        with self.assertRaises(CredibilityError):
            _card(rollout_types={"": 3})

    def test_malformed_bins_rejected(self):
        bad_n = {"lo": 0.0, "hi": 0.5, "predicted": 0.2,
                 "observed": 0.22, "n": 60.5}
        with self.assertRaises(CredibilityError):
            _card(calibration_bins=[bad_n])
        flipped = {"lo": 0.9, "hi": 0.1, "predicted": 0.2,
                   "observed": 0.22, "n": 60}
        with self.assertRaises(CredibilityError):
            _card(calibration_bins=[flipped])

    def test_empty_exchangeability_rejected(self):
        with self.assertRaises(CredibilityError):
            _card(exchangeability="")
        out = _card(exchangeability="iid rollouts, same policy")
        self.assertEqual(out["card"]["exchangeability"],
                         "iid rollouts, same policy")

    def test_bad_params_raise(self):
        card = _card()
        for kw in ({"min_n": True}, {"min_n": -1},
                   {"max_fp_rate": 2.0}, {"max_fp_rate": "low"},
                   {"require_bins": "yes"}):
            with self.assertRaises(CredibilityError, msg=kw):
                can_lift_draft(card, **kw)


class TestOTA(unittest.TestCase):
    def _vault2(self):
        vault = new_vault()
        genesis = register_release(vault, policy_id="arm", weights_hash=W1,
                                   parent_hash=None,
                                   regression_verdict="TRUSTED",
                                   regression_flag=None, seed=1,
                                   profile_version="v1")
        child = register_release(vault, policy_id="arm", weights_hash=W2,
                                 parent_hash=W1,
                                 regression_verdict="REVIEW",
                                 regression_flag="SUBSTANTIAL_"
                                                 "MODIFICATION_CANDIDATE",
                                 seed=1, profile_version="v1")
        return vault, genesis, child

    def test_lineage_and_flags(self):
        vault, genesis, child = self._vault2()
        self.assertTrue(genesis["deployable"])
        self.assertFalse(child["deployable"])
        self.assertEqual(children_of(vault, W1), [child["release_id"]])
        self.assertEqual(rollout_line(vault, W2),
                         [genesis["release_id"], child["release_id"]])

    def test_orphan_rejected(self):
        vault = new_vault()
        with self.assertRaises(OTAError):
            register_release(vault, policy_id="arm", weights_hash=W2,
                             parent_hash=W1, regression_verdict="TRUSTED",
                             regression_flag=None, seed=1,
                             profile_version="v1")

    def test_duplicate_content_rejected(self):
        vault, genesis, _ = self._vault2()
        with self.assertRaises(OTAError):
            register_release(vault, policy_id="arm", weights_hash=W1,
                             parent_hash=None,
                             regression_verdict="TRUSTED",
                             regression_flag=None, seed=1,
                             profile_version="v1")

    def test_bad_hashes_raise(self):
        vault = new_vault()
        with self.assertRaises(OTAError):
            register_release(vault, policy_id="arm", weights_hash="raw",
                             parent_hash=None,
                             regression_verdict="TRUSTED",
                             regression_flag=None, seed=1,
                             profile_version="v1")

    def test_corrupt_records_raise_ota_error(self):
        vault = {"releases": {"rel_x": {"release_id": "rel_x"}}}
        with self.assertRaises(OTAError):
            children_of(vault, W1)
        with self.assertRaises(OTAError):
            rollout_line(vault, W1)
        with self.assertRaises(OTAError):
            register_release(vault, policy_id="arm", weights_hash=W2,
                             parent_hash=W1,
                             regression_verdict="TRUSTED",
                             regression_flag=None, seed=1,
                             profile_version="v1")

    def test_mistyped_records_raise_ota_error(self):
        good = {"release_id": "rel_a", "weights_hash": W1,
                "parent_hash": None}
        for bad in ({"release_id": 7}, {"weights_hash": 9},
                    {"parent_hash": 5}):
            rec = dict(good, **bad)
            vault = {"releases": {"rel_a": rec, "rel_b": dict(good)}}
            with self.assertRaises(OTAError, msg=bad):
                children_of(vault, W1)

    def test_bool_seed_rejected(self):
        vault = new_vault()
        for boolean in (True, False):
            with self.assertRaises(OTAError):
                register_release(vault, policy_id="arm",
                                 weights_hash=W1, parent_hash=None,
                                 regression_verdict="TRUSTED",
                                 regression_flag=None, seed=boolean,
                                 profile_version="v1")

    def test_garbage_flag_rejected(self):
        vault = new_vault()
        for bad in (0, "", "SHIPPED", [], True):
            with self.assertRaises(OTAError, msg=repr(bad)):
                register_release(vault, policy_id="arm",
                                 weights_hash=W1, parent_hash=None,
                                 regression_verdict="TRUSTED",
                                 regression_flag=bad, seed=1,
                                 profile_version="v1")

    def test_key_id_mismatch_raises(self):
        rec = {"release_id": "rel_a", "weights_hash": W1,
               "parent_hash": None}
        vault = {"releases": {"rel_WRONG": rec}}
        with self.assertRaises(OTAError):
            children_of(vault, W1)
        with self.assertRaises(OTAError):
            rollout_line(vault, W1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
