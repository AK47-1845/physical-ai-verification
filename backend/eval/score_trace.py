"""Trace scoring pipeline: harnesses + gates + pinned scorecard.

score_trace() runs the M1 measurement set (drift mean/final, Frechet
gap, coherence ratio) over one intended/observed pair, bands each gate
against a versioned profile, and pins the scorecard envelope. Single
traces skip min_n (rollout-count gates need the CI path, not this one);
profiles stay versioned strings so every verdict names its thresholds.

Profile gate kinds: drift_mean, drift_final, frechet_gap (all
lower-is-better, green < amber), coherence_ratio (higher-is-better:
green = review floor, amber = pass bar, still green < amber).
"""

from engine import InputError
from engine.scorer import evaluate_gate, evaluate_scorecard

from backend.eval.failure_modes import drift_gate, sim_real_gap


class ScoreError(InputError):
    """Itemized validation failure. Server formats these, never traces."""


DRAFT_0 = {
    "version": "draft-0",
    "gates": [
        {"id": "drift_mean", "kind": "drift_mean",
         "green": 0.15, "amber": 0.5, "higher": False},
        {"id": "drift_final", "kind": "drift_final",
         "green": 0.2, "amber": 0.6, "higher": False},
        {"id": "frechet_gap", "kind": "frechet_gap",
         "green": 0.3, "amber": 0.8, "higher": False},
        {"id": "coherence", "kind": "coherence_ratio",
         "green": 0.5, "amber": 0.8, "higher": True},
    ],
}

PROFILES = {"draft-0": DRAFT_0}

_KINDS = ("drift_mean", "drift_final", "frechet_gap", "coherence_ratio")


def _measurements(intended, observed, *, threshold, breach_run):
    try:
        drift = drift_gate(intended, observed, threshold=threshold,
                           breach_run=breach_run)
    except Exception as exc:
        raise ScoreError(f"drift harness refused: {exc}")
    try:
        gap = sim_real_gap(intended, observed)
    except Exception as exc:
        raise ScoreError(f"frechet harness refused: {exc}")
    return {"drift_mean": drift["mean_err"],
            "drift_final": drift["final_err"],
            "frechet_gap": gap["frechet"],
            "coherence_ratio": drift["horizon_ratio"]}


def _resolve_profile(profile) -> dict:
    if isinstance(profile, str):
        if profile not in PROFILES:
            raise ScoreError(f"unknown profile {profile!r}; known: "
                             f"{sorted(PROFILES)}")
        base = PROFILES[profile]
        return {"version": base["version"],
                "gates": [dict(g) for g in base["gates"]]}
    if not isinstance(profile, dict):
        raise ScoreError("profile: version string or dict required")
    version = profile.get("version")
    if not version or not isinstance(version, str):
        raise ScoreError("profile.version: non-empty string required")
    gates = profile.get("gates")
    if not isinstance(gates, list) or not gates:
        raise ScoreError("profile.gates: non-empty list required")
    for gate in gates:
        if not isinstance(gate, dict) or not gate.get("id"):
            raise ScoreError("every profile gate needs a string id")
        if gate.get("kind") not in _KINDS:
            raise ScoreError(f"gate {gate.get('id')!r}: unknown kind "
                             f"{gate.get('kind')!r} (known: {list(_KINDS)})")
        if "higher" in gate and not isinstance(gate["higher"], bool):
            raise ScoreError(
                f"gate {gate.get('id')!r}: 'higher' must be a bool, "
                f"got {gate['higher']!r} (truthy strings flip bands)")
    return {"version": version, "gates": [dict(g) for g in gates]}


def score_trace(intended, observed, *, profile="draft-0", seed=0,
                evidence_prefix="trace", threshold=0.5,
                breach_run=3) -> dict:
    """Score one trace pair into a pinned scorecard envelope."""
    resolved = _resolve_profile(profile)
    if not evidence_prefix or not isinstance(evidence_prefix, str):
        raise ScoreError("evidence_prefix: non-empty string required")
    if isinstance(seed, bool) or not isinstance(seed, (int, str)):
        raise ScoreError(f"seed: int|str required (pinnable seeds only), "
                         f"got {seed!r}")
    measures = _measurements(intended, observed, threshold=threshold,
                             breach_run=breach_run)
    scored = []
    for gate in resolved["gates"]:
        try:
            scored.append(evaluate_gate(
                gate["id"], measures[gate["kind"]],
                green=gate["green"], amber=gate["amber"],
                evidence=f"{evidence_prefix}:{gate['kind']}",
                higher_is_better=bool(gate.get("higher", False))))
        except Exception as exc:
            raise ScoreError(f"gate {gate.get('id')!r} refused: {exc}")
    return evaluate_scorecard(scored,
                              profile_version=resolved["version"], seed=seed)
