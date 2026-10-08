"""OTA PAR currency: a PAR is valid only for its model weights.

Run from meta bro root:  python tests/test_ota_currency.py
par_currency() judges a PAR's weights against the OTA vault: a
PAR whose weights were followed by a substantial-modification
release is SUPERSEDED; unknown weights are UNKNOWN_WEIGHTS;
otherwise CURRENT. briefing_view surfaces this as a section
(+ attention) when given a vault; substantial modification stays
a FLAG for humans, never a legal conclusion.
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.ota import OTAError, new_vault, par_currency, register_release  # noqa: E402
from engine.par import build_par  # noqa: E402

from backend.eval.briefing import briefing_view  # noqa: E402

W1 = "sha256:" + "11" * 32
W2 = "sha256:" + "22" * 32
W3 = "sha256:" + "33" * 32


def _vault(flag_on_w3=True):
    vault = new_vault()
    register_release(vault, policy_id="p", weights_hash=W1,
                     parent_hash=None, regression_verdict="TRUSTED",
                     regression_flag=None, seed=1,
                     profile_version="draft-0")
    register_release(vault, policy_id="p", weights_hash=W2,
                     parent_hash=W1, regression_verdict="TRUSTED",
                     regression_flag=None, seed=2,
                     profile_version="draft-0")
    register_release(vault, policy_id="p", weights_hash=W3,
                     parent_hash=W2, regression_verdict="REVIEW",
                     regression_flag="SUBSTANTIAL_MODIFICATION_CANDIDATE"
                     if flag_on_w3 else None,
                     seed=3, profile_version="draft-0")
    return vault


def _par(weights):
    return build_par(
        policy={"id": "p", "weights": weights},
        release={"parent": weights, "delta": "IN-ODD"},
        gates=[{"id": "g1", "verdict": "PASS"}],
        ledger_head="cd" * 32, odd="test cell",
        independence={"builder": "b", "funder": "f",
                      "relationship": "none"})


class TestParCurrency(unittest.TestCase):
    def test_superseded_by_substantial_descendant(self):
        out = par_currency(_vault(), W1)
        self.assertEqual(out["status"], "SUPERSEDED")
        self.assertTrue(out["by"])

    def test_current_without_substantial_flag(self):
        out = par_currency(_vault(flag_on_w3=False), W1)
        self.assertEqual(out["status"], "CURRENT")

    def test_tip_is_current(self):
        out = par_currency(_vault(), W3)
        self.assertEqual(out["status"], "CURRENT")

    def test_unknown_weights(self):
        out = par_currency(_vault(), "sha256:" + "ff" * 32)
        self.assertEqual(out["status"], "UNKNOWN_WEIGHTS")

    def test_bad_inputs_raise(self):
        with self.assertRaises(OTAError):
            par_currency({}, W1)
        with self.assertRaises(OTAError):
            par_currency(_vault(), "nope")


class TestBriefingCurrency(unittest.TestCase):
    def test_section_and_attention_on_superseded(self):
        view = briefing_view(_par(W1), vault=_vault())
        titles = [s["title"] for s in view["sections"]]
        self.assertIn("PAR currency vs OTA vault", titles)
        self.assertTrue(any("SUPERSEDED" in a
                            for a in view["attention"]))

    def test_current_par_no_attention(self):
        view = briefing_view(_par(W1),
                             vault=_vault(flag_on_w3=False))
        self.assertFalse(any("SUPERSEDED" in a
                             for a in view["attention"]))

    def test_vault_must_be_dict(self):
        from backend.eval.briefing import BriefingError
        with self.assertRaises(BriefingError):
            briefing_view(_par(W1), vault=[])


if __name__ == "__main__":
    unittest.main(verbosity=2)
