"""Ensemble spread: per-sample positional std across K rollout runs.

Same frame, same units, same length per rollout. Spread widens where the
policy is uncertain or multi-modal. K=1 defines zero spread. Stdlib only.
"""

import math

from engine import InputError


class SpreadError(InputError):
    """Itemized validation failure. Server formats these, never stack traces."""


def ensemble_spread(rollouts) -> dict:
    """Per-sample spread = sqrt(mean over dims of population variance)."""
    try:
        rollouts = [list(r) for r in rollouts]
    except TypeError:
        raise SpreadError("rollouts: sequence of point sequences required")
    if not rollouts:
        raise SpreadError("need at least one rollout")
    length = len(rollouts[0])
    if length == 0:
        raise SpreadError("rollouts must be non-empty sequences of points")
    dim = None
    for k, run in enumerate(rollouts):
        if len(run) != length:
            raise SpreadError(
                f"rollout {k}: length {len(run)} != {length}")
        for i, pt in enumerate(run):
            if not isinstance(pt, (list, tuple)) or len(pt) == 0:
                raise SpreadError(
                    f"rollout {k}[{i}]: point must be a non-empty tuple")
            if dim is None:
                dim = len(pt)
            elif len(pt) != dim:
                raise SpreadError(
                    f"rollout {k}[{i}]: dim {len(pt)} != {dim}")
            for j, v in enumerate(pt):
                if (isinstance(v, bool)
                        or not isinstance(v, (int, float))
                        or not math.isfinite(v)):
                    raise SpreadError(
                        f"rollout {k}[{i}][{j}]: need finite number, "
                        f"got {v!r}")
    k = len(rollouts)
    per_sample = []
    for i in range(length):
        var_sum = 0.0
        for d in range(dim):
            vals = [float(run[i][d]) for run in rollouts]
            mean = math.fsum(vals) / k
            var_sum += math.fsum((v - mean) ** 2 for v in vals) / k
        per_sample.append(math.sqrt(var_sum / dim))
    return {"per_sample": per_sample,
            "max": max(per_sample),
            "mean": math.fsum(per_sample) / len(per_sample),
            "rollouts": k}
