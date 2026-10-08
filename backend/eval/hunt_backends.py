"""Hunt backends: fixture-driven falsification + FR-36 self-red-team.

FixtureBackend wraps a policy_fixtures rollout in the HuntBackend
protocol: params {noise_scale, bias} disturb the reference, drift_gate
judges, breach = break. Deterministic per (policy, params, seed).

RedTeamBackend aims the hunt at OUR OWN scorer: given policies flagged
must_block (e.g. playback) and a score_fn under test, a trial breaks
iff a must-block policy scores TRUSTED. Zero hits on a sane scorer;
any hit on a new scorer is a sev-1 test by PRD rule (FR-36).
"""

import math

from engine.hunt import HuntError

from backend.eval import policy_fixtures as fixtures
from backend.eval.failure_modes import drift_gate


def _num(value, name: str) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value)):
        raise HuntError(f"params[{name!r}]: finite number required")
    return float(value)


class FixtureBackend:
    """Falsify a fixture policy over {noise_scale, bias} disturbances."""

    def __init__(self, policy_id: str, *, horizon: int = 120, seed: int = 1,
                 threshold: float = 0.5):
        if (isinstance(horizon, bool) or not isinstance(horizon, int)
                or horizon < 4):
            raise HuntError(f"horizon: int >= 4 required, got {horizon!r} "
                            f"(bools are not horizons)")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise HuntError(f"seed: int required, got {seed!r} "
                            f"(bools are not seeds)")
        if not isinstance(policy_id, str):
            raise HuntError(f"policy_id: string required, got "
                            f"{policy_id!r}")
        threshold = _num(threshold, "threshold")
        try:
            self._fn = fixtures.get_policy(policy_id)["fn"]
        except KeyError as exc:
            raise HuntError(str(exc))
        self._ref = fixtures.reference_actions(horizon=horizon)
        self._seed = seed
        self._threshold = threshold
        self.policy_id = policy_id

    def evaluate(self, params: dict) -> dict:
        """Run one disturbed trial. Breach of drift gate = break."""
        if not isinstance(params, dict):
            raise HuntError("params: dict required")
        noise = _num(params.get("noise_scale"), "noise_scale")
        bias = _num(params.get("bias"), "bias")
        if noise < 0:
            raise HuntError("params['noise_scale']: must be >= 0")
        n = len(self._ref)
        cmds = [[a[0] + bias * (t / n), a[1] - 0.6 * bias * (t / n)]
                for t, a in enumerate(self._ref)]
        pred = self._fn(cmds, seed=self._seed, noise_scale=noise)
        gate = drift_gate(self._ref, pred, threshold=self._threshold)
        return {"breaks": gate["breach"],
                "measurement": gate["final_err"]}


class RedTeamBackend:
    """Hunt OUR scorer for wrongly-TRUSTED verdicts (FR-36).

    policies: {id: {"rollout": fn(actions, seed, noise)->trace,
                    "must_block": bool}}.
    score_fn(pred, ref, probed, seeds) -> {"label": verdict}.
    params: {"policy_idx": int-valued, "noise_scale": float}.
    """

    def __init__(self, policies: dict, score_fn, *, horizon: int = 120,
                 seed: int = 1, n_seeds: int = 3):
        if not isinstance(policies, dict) or not policies:
            raise HuntError("policies: non-empty dict required")
        if not all(isinstance(k, str) for k in policies):
            raise HuntError("policies: string ids required")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise HuntError(f"seed: int required, got {seed!r} "
                            f"(bools are not seeds)")
        if (isinstance(n_seeds, bool)
                or not isinstance(n_seeds, int) or n_seeds < 1):
            raise HuntError(f"n_seeds: positive int, got {n_seeds!r}")
        for pid, spec in policies.items():
            if not isinstance(spec, dict):
                raise HuntError(f"policies[{pid!r}]: spec dict required, "
                                f"got {type(spec).__name__}")
            if not callable(spec.get("rollout")):
                raise HuntError(f"policies[{pid!r}]: rollout callable "
                                f"required")
            if not isinstance(spec.get("must_block"), bool):
                raise HuntError(f"policies[{pid!r}]: must_block bool "
                                f"required")
        if not callable(score_fn):
            raise HuntError("score_fn: callable required")
        if (isinstance(horizon, bool) or not isinstance(horizon, int)
                or horizon < 4):
            raise HuntError(f"horizon: int >= 4 required, got {horizon!r} "
                            f"(bools are not horizons)")
        self._ids = sorted(policies)
        self._policies = policies
        self._score_fn = score_fn
        self._ref = fixtures.reference_actions(horizon=horizon)
        self._seed = seed
        self._n_seeds = n_seeds

    def evaluate(self, params: dict) -> dict:
        """One policy/noise trial. Wrongly-TRUSTED = break."""
        if not isinstance(params, dict):
            raise HuntError("params: dict required")
        idx = _num(params.get("policy_idx"), "policy_idx")
        noise = _num(params.get("noise_scale"), "noise_scale")
        if idx != int(idx) or not 0 <= int(idx) < len(self._ids):
            raise HuntError(f"params['policy_idx']: int in range "
                            f"[0, {len(self._ids)})")
        pid = self._ids[int(idx)]
        spec = self._policies[pid]
        rollout = spec["rollout"]
        try:
            pred = rollout(self._ref, self._seed, noise)
            probed = rollout(fixtures.probe_actions(self._ref), self._seed,
                             noise)
            seeds = [rollout(self._ref, s, noise)
                     for s in range(self._n_seeds)]
            verdict = self._score_fn(pred, self._ref, probed, seeds)
        except HuntError:
            raise
        except Exception as exc:
            raise HuntError(f"trial raised: {exc!r}")
        if not isinstance(verdict, dict):
            raise HuntError(f"score_fn must return a dict with 'label', "
                            f"got {type(verdict).__name__}")
        label = verdict.get("label")
        if label not in ("TRUSTED", "REVIEW", "BLOCKED"):
            raise HuntError(f"score_fn returned bad label {label!r}")
        wrongly_trusted = spec["must_block"] and label == "TRUSTED"
        return {"breaks": wrongly_trusted,
                "measurement": 1.0 if wrongly_trusted else 0.0,
                "policy_id": pid, "label": label}


def sane_score_fn(pred, ref, probed, seeds):
    """Preset FR-36 scorer: drift breach or dead probe => BLOCKED.

    Production twin of the test-suite sane scorer: drift_gate at 0.5
    plus normalized probe-response energy. A must-block policy that
    scores TRUSTED here is a sev-1 test by PRD rule (FR-36).
    """
    for name, trace in (("pred", pred), ("ref", ref),
                        ("probed", probed)):
        if not isinstance(trace, (list, tuple)) or not trace:
            raise HuntError(f"sane scorer: {name} non-empty trace "
                            f"required")
    drift = drift_gate(ref, pred, threshold=0.5)
    pairs = [(p, q) for p, q in zip(pred, probed)]
    if not pairs:
        raise HuntError("sane scorer: pred/probed length mismatch")
    diffs = [math.fsum((a - b) ** 2 for a, b in zip(p, q))
             for p, q in pairs]
    raw = math.fsum(diffs) / len(diffs)
    energy = math.fsum(v * v for row in pred for v in row) / len(pred) + 1e-9
    responsive = (raw / energy) > 0.01
    _ = seeds
    if drift["breach"] or not responsive:
        return {"label": "BLOCKED"}
    return {"label": "TRUSTED"}


def broken_score_fn(pred, ref, probed, seeds):
    """Preset FR-36 broken scorer: TRUSTED no matter what.

    Deliberate strawman: the red-team demo target. Any hunt against
    this scorer MUST report breaks on must-block policies; zero hits
    would mean the hunt itself is broken.
    """
    _ = (pred, ref, probed, seeds)
    return {"label": "TRUSTED"}


SCORE_PRESETS = {"sane": sane_score_fn, "broken": broken_score_fn}

FIXTURE_ROLLOUTS = {
    "clean": fixtures.clean_rollout,
    "drifty": fixtures.drifty_rollout,
    "playback": fixtures.playback_rollout,
    "synthfed": fixtures.synthfed_rollout,
}


def get_score_preset(name: str):
    """Look up a preset scorer by name. Unknown names raise HuntError."""
    if not isinstance(name, str) or name not in SCORE_PRESETS:
        raise HuntError(f"score_fn: unknown preset {name!r}; known: "
                        f"{sorted(SCORE_PRESETS)}")
    return SCORE_PRESETS[name]


def fixture_policies(specs: list) -> dict:
    """Build RedTeam policies from [{id, must_block}] (service use)."""
    if not isinstance(specs, list) or not specs:
        raise HuntError("policies: non-empty [{id, must_block}] list "
                        "required")
    seen = {}
    for pos, spec in enumerate(specs):
        if not isinstance(spec, dict):
            raise HuntError(f"policies[{pos}]: dict required")
        pid = spec.get("id")
        if not isinstance(pid, str) or pid not in FIXTURE_ROLLOUTS:
            raise HuntError(f"policies[{pos}]: unknown fixture {pid!r}; "
                            f"known: {sorted(FIXTURE_ROLLOUTS)}")
        if pid in seen:
            raise HuntError(f"policies[{pos}]: duplicate id {pid!r}")
        flag = spec.get("must_block")
        if not isinstance(flag, bool):
            raise HuntError(f"policies[{pos}]: must_block bool required")
        seen[pid] = {"rollout": FIXTURE_ROLLOUTS[pid],
                     "must_block": flag}
    return seen
