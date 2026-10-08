"""FM1..FM5 production harnesses over the engine core (+ MVP steals).

FM1 drift gate: per-sample gaps with debounced coherence horizon (MVP
steal: breach_run consecutive breaches; single-frame spikes are glitches).
FM2 executability: joint chunks go to engine.guard (proof-grade);
task-space paths get the jerk/bounds PROXY (labeled, never a proof).
FM3 hallucination: encode/decode round-trip residual gate (codebook
collapse / OOD detector) over caller-supplied model callables.
FM4 marginalization: shuffle variant (engine) + probe variant (MVP steal:
second-half action offset, normalized response; playback reads 0.0).
FM5 sim-to-real: discrete Frechet gap in identical reference frames.
"""

import math

from engine import InputError
from engine.drift import drift_series
from engine.frechet import discrete_frechet
from engine.sensitivity import action_sensitivity


class FailureModeError(InputError):
    """Itemized validation failure. Server formats these, never traces."""


def _is_num(v) -> bool:
    return (not isinstance(v, bool) and isinstance(v, (int, float))
            and math.isfinite(v))


def _check_points(seq, name: str) -> int:
    if not isinstance(seq, (list, tuple)) or len(seq) == 0:
        raise FailureModeError(f"{name}: non-empty point sequence required")
    dim = None
    for i, pt in enumerate(seq):
        if not isinstance(pt, (list, tuple)) or len(pt) == 0:
            raise FailureModeError(f"{name}[{i}]: non-empty tuple required")
        if dim is None:
            dim = len(pt)
        elif len(pt) != dim:
            raise FailureModeError(f"{name}[{i}]: ragged trace")
        for v in pt:
            if not _is_num(v):
                raise FailureModeError(f"{name}[{i}]: finite numbers only")
    return dim


def drift_gate(intended, observed, *, threshold, breach_run=3) -> dict:
    """FM1: gaps + debounced coherence horizon. breach = sustained exceed."""
    if not _is_num(threshold) or threshold < 0:
        raise FailureModeError("threshold: finite number >= 0 required "
                               "(gaps are non-negative)")
    if (isinstance(breach_run, bool)
            or not isinstance(breach_run, int) or breach_run < 1):
        raise FailureModeError("breach_run: positive int required")
    try:
        series = drift_series(intended, observed)
    except Exception as exc:
        raise FailureModeError(f"drift_series refused: {exc}")
    horizon = len(series)
    for i in range(len(series) - breach_run + 1):
        if all(e > threshold for e in series[i:i + breach_run]):
            horizon = i
            break
    return {"per_sample": series,
            "mean_err": math.fsum(series) / len(series),
            "final_err": series[-1],
            "coherence_horizon": horizon,
            "horizon_ratio": horizon / len(series),
            "breach": horizon < len(series)}


def executability_proxy(traj, *, bounds=(-2.0, 2.0)) -> dict:
    """FM2 task-space PROXY: jerk + workspace violations. NOT a proof.

    Proof-grade joint checking is engine.guard.check_chunk. This proxy
    catches wild motion in task space only; the proxy_warning is load
    bearing and must surface in every dossier row that cites it.
    Differences are per-step (dt is implicitly 1): rescale for
    physical jerk at any other control rate.
    """
    dim = _check_points(traj, "traj")
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
        raise FailureModeError("bounds: (lo, hi) pair required")
    lo, hi = bounds
    if not _is_num(lo) or not _is_num(hi) or not lo < hi:
        raise FailureModeError("bounds: finite (lo, hi) with lo < hi")
    pts = [[float(v) for v in p] for p in traj]

    def _diff(rows):
        return [[b[d] - a[d] for d in range(dim)]
                for a, b in zip(rows, rows[1:])]
    acc = _diff(_diff(pts))
    jerk = _diff(acc)
    jmags = [math.sqrt(math.fsum(j * j for j in row)) for row in jerk]
    violations = sum(1 for p in pts for v in p if v < lo or v > hi)
    if jmags:
        max_jerk: float | None = max(jmags)
        mean_jerk: float | None = math.fsum(jmags) / len(jmags)
    else:
        # < 4 points: jerk is UNCOMPUTABLE, not zero. Bounds still count.
        max_jerk = None
        mean_jerk = None
    return {"max_jerk": max_jerk, "mean_jerk": mean_jerk,
            "bound_violations": violations,
            "violation_rate": violations / (len(pts) * dim),
            "proxy_warning": "PROXY: not a contact-dynamics proof"}


def hallucination_gate(encode, decode, samples, *, threshold) -> dict:
    """FM3: round-trip residual E = ||x - D(E(x))||^2 per sample.

    OOD inputs collapse to seen codebook entries; the residual trips the
    gate before control executes. encode/decode are caller callables.
    """
    if not callable(encode) or not callable(decode):
        raise FailureModeError("encode and decode must both be callable")
    if not _is_num(threshold) or threshold < 0:
        raise FailureModeError("threshold: finite number >= 0 required "
                               "(residuals are non-negative)")
    dim = _check_points(samples, "samples")
    residuals = []
    for i, sample in enumerate(samples):
        try:
            latent = encode(list(sample))
            recon = decode(latent)
        except Exception as exc:
            raise FailureModeError(f"sample {i}: model raised {exc!r}")
        if not isinstance(recon, (list, tuple)) or len(recon) != dim:
            raise FailureModeError(
                f"sample {i}: decode must return dim-{dim} vector")
        if not all(_is_num(v) for v in recon):
            raise FailureModeError(f"sample {i}: non-finite reconstruction")
        residuals.append(math.fsum((a - b) ** 2
                                   for a, b in zip(sample, recon)))
    trips = [i for i, r in enumerate(residuals) if r > threshold]
    return {"residuals": residuals, "trips": trips,
            "trip_rate": len(trips) / len(residuals),
            "worst": max(residuals)}


def marginalization_shuffle(predict, z, actions, *, seed,
                            threshold=1e-9) -> dict:
    """FM4 shuffle variant: predictions must MOVE with shuffled actions."""
    try:
        return action_sensitivity(predict, z, actions, seed=seed,
                                  threshold=threshold)
    except Exception as exc:
        raise FailureModeError(f"sensitivity refused: {exc}")


def marginalization_probe(rollout_fn, actions, *, probe_offsets, seed,
                          threshold=0.01) -> dict:
    """FM4 probe variant (MVP steal): offset second-half actions, measure.

    rollout_fn(actions, seed) -> trajectory. Returns normalized response;
    playback policies read exactly 0.0 (responsive False = BAD).
    """
    if not callable(rollout_fn):
        raise FailureModeError("rollout_fn must be callable(actions, seed)")
    dim = _check_points(actions, "actions")
    if (not isinstance(probe_offsets, (list, tuple))
            or len(probe_offsets) != dim
            or not all(_is_num(v) for v in probe_offsets)):
        raise FailureModeError("probe_offsets: finite per-dim vector")
    if not any(probe_offsets):
        raise FailureModeError("probe_offsets all zero: a null probe "
                               "measures nothing (refusing a fake verdict)")
    if not _is_num(threshold) or threshold < 0:
        raise FailureModeError("threshold: finite number >= 0 required "
                               "(response is non-negative)")
    acts = [[float(v) for v in row] for row in actions]
    probed = [row[:] for row in acts]
    for t in range(len(acts) // 2, len(acts)):
        for d in range(dim):
            probed[t][d] += probe_offsets[d]
    try:
        nominal = rollout_fn(acts, seed)
        moved = rollout_fn(probed, seed)
    except Exception as exc:
        raise FailureModeError(f"rollout_fn raised {exc!r}")
    nom_dim = _check_points(nominal, "rollout nominal")
    mov_dim = _check_points(moved, "rollout probed")
    if nom_dim != dim or mov_dim != dim:
        raise FailureModeError(
            f"rollout_fn must preserve action dim {dim}, got "
            f"nominal {nom_dim} / probed {mov_dim} (zip would truncate)")
    if len(nominal) != len(acts) or len(moved) != len(acts):
        raise FailureModeError("rollout_fn must preserve horizon length")
    diffs = [math.fsum((a - b) ** 2 for a, b in zip(p, q))
             for p, q in zip(nominal, moved)]
    raw = math.fsum(diffs) / len(diffs)
    energy = (math.fsum(v * v for row in nominal for v in row)
              / len(nominal)) + 1e-9
    normalized = raw / energy
    return {"raw": raw, "normalized": normalized,
            "responsive": normalized > threshold, "threshold": threshold,
            "seed": seed}


def sim_real_gap(sim, real) -> dict:
    """FM5: discrete Frechet gap in IDENTICAL reference frames."""
    try:
        gap = discrete_frechet(sim, real)
    except Exception as exc:
        raise FailureModeError(f"frechet refused: {exc}")
    return {"frechet": gap, "sim_len": len(sim), "real_len": len(real)}
