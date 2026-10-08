"""Golden-story builder: deterministic end-to-end artifacts per story.

Shared by tests/test_golden.py, tests/test_determinism_hashseed.py and
backend/tools/golden_check.py so all three assert the SAME pipeline.
No wall clock, no randomness except explicit fixed seeds. Stdlib only.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "packages"))

from engine import ENGINE_VERSION  # noqa: E402
from engine.credibility import build_card  # noqa: E402
from engine.hunt import grid_search, seal_trials  # noqa: E402
from engine.ledger import append as ledger_append  # noqa: E402
from engine.ledger import head as ledger_head
from engine.par import build_par  # noqa: E402

from backend.eval import policy_fixtures as fixtures  # noqa: E402
from backend.eval.hunt_backends import FixtureBackend  # noqa: E402
from backend.eval.score_trace import score_trace  # noqa: E402

STORIES = (("clean", 11), ("drifty", 12), ("playback", 13),
           ("synthfed", 14))
HORIZON = 32
FIXED_DAY = "2026-01-01"


def build_story(policy, seed):
    """Build all golden artifacts for one fixture story."""
    intended = fixtures.reference_actions(horizon=HORIZON)
    rollout = fixtures.get_policy(policy)["fn"]
    observed = rollout(intended, seed=seed, noise_scale=1.0)
    scorecard = score_trace(
        intended, observed, profile="draft-0", seed=seed,
        evidence_prefix="golden", threshold=0.5, breach_run=3)
    gates = [{"id": g["gate"], "verdict": g["status"],
              "measurement": g["measurement"], "evidence": g["evidence"]}
             for g in scorecard["payload"]["gates"]]
    chain = []
    ledger_append(chain, "RUN_SEALED",
                  {"policy": policy, "seed": seed,
                   "inputs": scorecard["inputs_hash"]},
                  f"{FIXED_DAY}T00:00:00+00:00")
    ledger_append(chain, "CARD_SEALED",
                  {"policy": policy, "verdict":
                   scorecard["payload"]["verdict"]},
                  f"{FIXED_DAY}T00:00:01+00:00")
    head = ledger_head(chain)
    par = build_par(
        policy={"id": f"golden-{policy}",
                "weights": "sha256:" + f"{seed:02d}" * 32},
        release={"parent": "sha256:" + f"{seed:02d}" * 32,
                 "delta": "IN-ODD"},
        gates=gates, ledger_head=head,
        odd=f"golden fixture envelope for {policy}, seed {seed}",
        independence={"builder": "golden", "funder": "golden",
                      "relationship": "none"})
    card = build_card(
        gate_id="tracking", gate_version="1.0",
        corpus_hash=scorecard["inputs_hash"], n=120,
        false_positives=2, false_negatives=1,
        label_counts={"pass": 100, "fail": 20},
        calibration_bins=[{"lo": 0.0, "hi": 0.5, "predicted": 0.2,
                           "observed": 0.22, "n": 60}],
        rollout_types={"policy-sampled": 120}, transfer_error=0.03,
        search_hits=0, date=FIXED_DAY, analyst="golden")
    backend = FixtureBackend(policy, horizon=16, seed=seed)
    catalogue = grid_search(backend, {"noise_scale": [0.5, 1.0],
                                      "bias": [0.0]},
                            seed=seed, trial_cap=4)
    sealed = seal_trials(catalogue)
    return {"scorecard": scorecard, "par": par, "chain": chain,
            "head": head, "card": card, "sealed": sealed}


def hashes_of(artifacts):
    """Small hash record per story: the golden file content."""
    return {
        "scorecard_envelope": artifacts["scorecard"]["envelope_hash"],
        "par": artifacts["par"]["par_hash"],
        "ledger_head": artifacts["head"],
        "card": artifacts["card"]["card_hash"],
        "catalogue": artifacts["sealed"]["catalogue_hash"],
        "verdict": artifacts["scorecard"]["payload"]["verdict"],
    }


def build_all():
    """{story: artifacts} for all four stories + engine version."""
    return {"engine_version": ENGINE_VERSION,
            "stories": {policy: build_story(policy, seed)
                        for policy, seed in STORIES}}
