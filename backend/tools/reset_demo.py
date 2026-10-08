"""Reset + deterministically seed a DEMO store.

Usage (from hi bro/meta bro):
  mkdir demo-store
  echo demo-store-v1 > demo-store/.verification-demo-store
  python backend/tools/reset_demo.py --store demo-store
Refuses to touch any directory WITHOUT the marker file. Seeds 4 runs
(clean/drifty/playback/synthfed) with fixed seeds: running twice yields
identical run IDs and hashes. Stdlib only.
"""

import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "packages"))

from engine import canonical_hash  # noqa: E402

from backend.eval import policy_fixtures as fixtures  # noqa: E402
from backend.eval.score_trace import score_trace  # noqa: E402
from backend.persist.filelayout import FileLayoutStore  # noqa: E402

MARKER = ".verification-demo-store"
STORIES = (("clean", 11), ("drifty", 12), ("playback", 13),
           ("synthfed", 14))


def _evaluate_stdlib(body, store):
    """Replicates service.runs_evaluate without fastapi.

    COUPLING: defaults and the run_id formula must match
    backend/service_app.runs_evaluate. test_ops_tools asserts both
    paths agree (via the fastapi stub).
    """
    card = score_trace(
        body.get("intended"), body.get("observed"),
        profile=body.get("profile") or "draft-0",
        seed=body.get("seed", 0),
        evidence_prefix=body.get("evidence_prefix", "ev://runs/"),
        threshold=body.get("threshold", 0.5),
        breach_run=body.get("breach_run", 3))
    policy_id = body.get("policy_id") or "unregistered"
    run_id = "run_" + canonical_hash({"card": card,
                                      "policy": policy_id})[:12]
    store.save("runs", run_id, {"scorecard": card,
                                "policy_id": policy_id})
    return {"run_id": run_id, "verdict": card["payload"]["verdict"],
            "scorecard": card}


def evaluate_run(body, store, prefer_service=True):
    """Score + persist one run. Service handler when fastapi exists."""
    if prefer_service:
        try:
            import backend.service_app as service
        except ImportError:
            pass
        else:
            old = service._STORE
            service._STORE = store
            try:
                return service.runs_evaluate(body)
            finally:
                service._STORE = old
    return _evaluate_stdlib(body, store)


def reset_store(root):
    """Wipe a marked demo store. Returns list of removed names."""
    marker = os.path.join(root, MARKER)
    if not os.path.isdir(root) or not os.path.isfile(marker):
        raise SystemExit(
            f"REFUSED: {root} has no {MARKER} marker. Create the "
            f"directory, add the marker file, then re-run. This guard "
            f"exists so the tool can never wipe the wrong folder.")
    removed = []
    for name in sorted(os.listdir(root)):
        if name == MARKER:
            continue
        path = os.path.join(root, name)
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        removed.append(name)
    return removed


def seed_stories(store, horizon=64):
    """Seed the 4 fixture stories. Returns [(policy, run_id, verdict)]."""
    intended = fixtures.reference_actions(horizon=horizon)
    seeded = []
    for policy, seed in STORIES:
        rollout = fixtures.get_policy(policy)["fn"]
        observed = rollout(intended, seed=seed, noise_scale=1.0)
        out = evaluate_run(
            {"intended": intended, "observed": observed,
             "policy_id": f"demo-{policy}", "seed": seed,
             "threshold": 0.5, "profile": "draft-0",
             "evidence_prefix": "ev://demo/", "breach_run": 3},
            store)
        seeded.append((policy, out["run_id"],
                       out["scorecard"]["payload"]["verdict"]))
    return seeded


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reset + seed demo store")
    parser.add_argument("--store", required=True)
    parser.add_argument("--horizon", type=int, default=64)
    args = parser.parse_args(argv)
    removed = reset_store(args.store)
    print(f"wiped {len(removed)} entr(y/ies) from {args.store}")
    store = FileLayoutStore(root=args.store)
    for policy, run_id, verdict in seed_stories(store,
                                                horizon=args.horizon):
        print(f"seeded {policy}: {run_id} {verdict}")
    print("done: re-running yields identical run IDs (deterministic)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
