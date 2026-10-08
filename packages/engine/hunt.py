"""M4 adversarial hunt: seeded search over perturbation spaces.

A HuntBackend is any object with:
    evaluate(params: dict) -> {"breaks": bool, "measurement": float, ...}
`breaks` True means the perturbation broke the gate under test.
`measurement` carries the breaking magnitude (higher = worse).

grid_search evaluates the cartesian product in canonical (sorted-name)
order: exhaustive and reviewable. random_search samples uniformly with
a seeded RNG: deterministic per seed. Both honor trial_cap. The catalogue
is the edge-case record engineers triage from. Stdlib only.
"""

import itertools
import math
import random

from engine import InputError, canonical_hash


class HuntError(InputError):
    """Itemized validation failure. Server formats these, never stack traces."""


def _check_cap(trial_cap):
    if (isinstance(trial_cap, bool)
            or not isinstance(trial_cap, int) or trial_cap < 1):
        raise HuntError(f"trial_cap must be a positive int: {trial_cap!r}")


def _check_seed(seed):
    if (isinstance(seed, bool)
            or not isinstance(seed, (int, str, bytes))):
        raise HuntError(
            f"seed must be an explicit int, str, or bytes: {seed!r} "
            f"(unseeded hunts are non-deterministic and unrecordable; "
            f"bools are not seeds)")


def _run_trial(backend, params, trial_no):
    try:
        result = backend.evaluate(dict(params))
    except HuntError:
        raise
    except Exception as exc:  # backend bugs must not forge catalogues
        raise HuntError(f"trial {trial_no}: backend raised {exc!r}")
    if not isinstance(result, dict):
        raise HuntError(f"trial {trial_no}: backend must return a dict")
    if "breaks" not in result or not isinstance(result["breaks"], bool):
        raise HuntError(f"trial {trial_no}: 'breaks' bool required")
    measurement = result.get("measurement")
    if (not isinstance(measurement, (int, float))
            or not math.isfinite(measurement)):
        raise HuntError(f"trial {trial_no}: finite 'measurement' required")
    return {"trial": trial_no, "params": dict(params),
            "breaks": result["breaks"], "measurement": measurement}


def grid_search(backend, space: dict, *, seed, trial_cap) -> dict:
    """Exhaustive cartesian search in canonical order (seed recorded)."""
    _check_cap(trial_cap)
    _check_seed(seed)
    if not isinstance(space, dict) or not space:
        raise HuntError("space must be a non-empty {name: [values]} dict")
    if not all(isinstance(k, str) for k in space):
        raise HuntError("space: string parameter names required")
    names = sorted(space)
    for name in names:
        vals = space[name]
        if not isinstance(vals, (list, tuple)) or not vals:
            raise HuntError(f"space[{name!r}]: need a non-empty value list")
        for v in vals:
            if (isinstance(v, bool) or not isinstance(v, (int, float))
                    or not math.isfinite(v)):
                raise HuntError(f"space[{name!r}]: finite numbers only "
                                f"(bools are not values), got {v!r}")
    trials, breaks = [], []
    exhausted = True
    for combo in itertools.product(*(space[n] for n in names)):
        if len(trials) >= trial_cap:
            exhausted = False
            break
        trial = _run_trial(backend, dict(zip(names, combo)), len(trials))
        trials.append(trial)
        if trial["breaks"]:
            breaks.append(trial)
    return {"mode": "grid", "seed": seed, "trial_cap": trial_cap,
            "exhausted": exhausted, "trials": trials, "breaks": breaks}


def random_search(backend, space: dict, *, seed, trial_cap) -> dict:
    """Uniform random search. Deterministic for a fixed seed."""
    _check_cap(trial_cap)
    _check_seed(seed)
    if not isinstance(space, dict) or not space:
        raise HuntError("space must be a non-empty {name: (lo, hi)} dict")
    if not all(isinstance(k, str) for k in space):
        raise HuntError("space: string parameter names required")
    names = sorted(space)
    bounds = {}
    for name in names:
        bound = space[name]
        if (not isinstance(bound, (list, tuple)) or len(bound) != 2):
            raise HuntError(f"space[{name!r}]: need a (lo, hi) pair")
        lo, hi = bound
        if (isinstance(lo, bool) or isinstance(hi, bool)
                or not isinstance(lo, (int, float))
                or not isinstance(hi, (int, float))
                or not math.isfinite(lo) or not math.isfinite(hi)
                or not lo < hi):
            raise HuntError(f"space[{name!r}]: need finite lo < hi "
                            f"(bools are not bounds)")
        bounds[name] = (float(lo), float(hi))
    rng = random.Random(seed)
    trials, breaks = [], []
    for num in range(trial_cap):
        params = {n: rng.uniform(*bounds[n]) for n in names}
        trial = _run_trial(backend, params, num)
        trials.append(trial)
        if trial["breaks"]:
            breaks.append(trial)
    return {"mode": "random", "seed": seed, "trial_cap": trial_cap,
            "exhausted": True, "trials": trials, "breaks": breaks}


def refine_search(backend, breaks: list, ranges: dict, *, seed,
                  trial_cap, zoom=0.25, subdiv=3) -> dict:
    """Deterministic zoom around breaking params (FR-8 refine step).

    breaks: non-empty list of param dicts from a prior catalogue.
    ranges: {name: (lo, hi)} bounds the zoom (from the original space:
    grid min/max or random-search bounds; the service layer derives and
    records them). Each break spawns a subdiv^dims sub-grid spanning
    break +/- zoom*(hi-lo)/2, clamped to bounds. Order: break index,
    then canonical (sorted-name) product. trial_cap is global.
    """
    _check_cap(trial_cap)
    _check_seed(seed)
    if not isinstance(breaks, list) or not breaks:
        raise HuntError("breaks: non-empty list of param dicts required")
    if not isinstance(ranges, dict) or not ranges:
        raise HuntError("ranges: non-empty {name: (lo, hi)} dict required")
    if not all(isinstance(k, str) for k in ranges):
        raise HuntError("ranges: string parameter names required")
    bounds = {}
    for name, bound in ranges.items():
        if (not isinstance(bound, (list, tuple)) or len(bound) != 2):
            raise HuntError(f"ranges[{name!r}]: need a (lo, hi) pair")
        lo, hi = bound
        if (isinstance(lo, bool) or isinstance(hi, bool)
                or not isinstance(lo, (int, float))
                or not isinstance(hi, (int, float))
                or not math.isfinite(lo) or not math.isfinite(hi)
                or not lo < hi):
            raise HuntError(f"ranges[{name!r}]: need finite lo < hi")
        bounds[name] = (float(lo), float(hi))
    names = sorted(bounds)
    for i, params in enumerate(breaks):
        if not isinstance(params, dict):
            raise HuntError(f"breaks[{i}]: dict required")
        if sorted(params) != names:
            raise HuntError(f"breaks[{i}]: keys must match ranges "
                            f"{names}, got {sorted(params)}")
        for name in names:
            val = params[name]
            if (isinstance(val, bool) or not isinstance(val, (int, float))
                    or not math.isfinite(val)):
                raise HuntError(f"breaks[{i}][{name!r}]: finite number "
                                f"required")
    if (isinstance(zoom, bool) or not isinstance(zoom, (int, float))
            or not 0.0 < zoom < 1.0):
        raise HuntError(f"zoom: fraction in (0, 1) required: {zoom!r}")
    if isinstance(subdiv, bool) or not isinstance(subdiv, int) or subdiv < 2:
        raise HuntError(f"subdiv: int >= 2 required: {subdiv!r}")
    trials, new_breaks = [], []
    exhausted = True
    for parent, params in enumerate(breaks):
        axes = []
        for name in names:
            lo, hi = bounds[name]
            center = min(max(float(params[name]), lo), hi)
            half = zoom * (hi - lo) / 2.0
            span_lo, span_hi = center - half, center + half
            pts = []
            for step in range(subdiv):
                frac = step / (subdiv - 1)
                pt = min(max(span_lo + frac * (span_hi - span_lo), lo),
                         hi)
                if pt not in pts:
                    pts.append(pt)
            axes.append(pts)
        for combo in itertools.product(*axes):
            if len(trials) >= trial_cap:
                exhausted = False
                break
            trial = _run_trial(backend, dict(zip(names, combo)),
                               len(trials))
            trial["parent"] = parent
            trials.append(trial)
            if trial["breaks"]:
                new_breaks.append(trial)
        if not exhausted:
            break
    return {"mode": "refine", "seed": seed, "trial_cap": trial_cap,
            "zoom": zoom, "subdiv": subdiv,
            "refined_from": len(breaks), "exhausted": exhausted,
            "trials": trials, "breaks": new_breaks}


def seal_trials(catalogue: dict) -> dict:
    """Ledger-ready trial seals (FR-9 lib half: params hash + outcome).

    Pure: validates a catalogue and returns per-trial seals plus a
    catalogue hash. The service layer appends HUNT_TRIAL seals to the
    ledger (route pending morning decision 2); this shape is the
    contract it appends.
    """
    if not isinstance(catalogue, dict):
        raise HuntError("catalogue: dict required")
    trials = catalogue.get("trials")
    if not isinstance(trials, list):
        raise HuntError("catalogue.trials: list required")
    sealed = []
    for pos, trial in enumerate(trials):
        if not isinstance(trial, dict):
            raise HuntError(f"trials[{pos}]: dict required")
        num = trial.get("trial")
        if isinstance(num, bool) or not isinstance(num, int) or num < 0:
            raise HuntError(f"trials[{pos}].trial: non-negative int")
        params = trial.get("params")
        if (not isinstance(params, dict) or not params
                or not all(isinstance(k, str) for k in params)):
            raise HuntError(f"trials[{pos}].params: non-empty str-key "
                            f"dict required")
        for key, val in params.items():
            if (isinstance(val, bool) or not isinstance(val, (int, float))
                    or not math.isfinite(val)):
                raise HuntError(f"trials[{pos}].params[{key!r}]: finite "
                                f"number required")
        if not isinstance(trial.get("breaks"), bool):
            raise HuntError(f"trials[{pos}].breaks: bool required")
        meas = trial.get("measurement")
        if (not isinstance(meas, (int, float))
                or not math.isfinite(meas)):
            raise HuntError(f"trials[{pos}].measurement: finite number")
        sealed.append({"trial": num,
                       "params_hash": canonical_hash(params),
                       "breaks": trial["breaks"], "measurement": meas})
    return {"sealed": sealed, "trials": len(sealed),
            "catalogue_hash": canonical_hash(sealed)}


def summarize(catalogue: dict) -> dict:
    """Counts + worst trial (max measurement) for triage headers."""
    if not isinstance(catalogue, dict):
        raise HuntError("catalogue: dict required")
    trials = catalogue.get("trials", [])
    breaks = catalogue.get("breaks", [])
    if not isinstance(trials, list) or not isinstance(breaks, list):
        raise HuntError("catalogue trials/breaks: lists required")
    worst = None
    if trials:
        worst = max(trials, key=lambda t: t["measurement"])
    return {"trials": len(trials), "breaks": len(breaks),
            "break_rate": (len(breaks) / len(trials)) if trials else 0.0,
            "worst": worst}
