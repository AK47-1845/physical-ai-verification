"""Seeded percentile bootstrap confidence intervals (FR-35 support).

Every gate reports a seeded CI over independent rollouts; below-minimum-n
inputs never reach here (the scorer returns INSUFFICIENT first).
Deterministic for a fixed seed. Stdlib only.

Seed note: bytes seeds are accepted (RNG handles them) and echoed raw
in the output dict; hashing callers must normalize first (bytes are
not JSON-canonicalizable). Prefer int|str seeds for pinnable records.
"""

import math
import random

from engine import InputError


class CIError(InputError):
    """Itemized validation failure. Server formats these, never stack traces."""


def bootstrap_ci(values, *, seed, alpha=0.05, resamples=1000) -> dict:
    """Percentile CI over resampled means. Nearest-rank on sorted means."""
    if isinstance(values, (str, bytes, dict)):
        raise CIError(f"values: sequence required, got "
                      f"{type(values).__name__}")
    try:
        vals = list(values)
    except TypeError:
        raise CIError(f"values: sequence required, got {type(values).__name__}")
    if not vals:
        raise CIError("need at least one value")
    if (isinstance(seed, bool)
            or not isinstance(seed, (int, str, bytes))):
        raise CIError(f"seed must be an explicit int, str, or bytes: {seed!r}")
    for i, v in enumerate(vals):
        if (isinstance(v, bool) or not isinstance(v, (int, float))
                or not math.isfinite(v)):
            raise CIError(f"values[{i}]: need finite number, got {v!r}")
    if (isinstance(alpha, bool)
            or not isinstance(alpha, (int, float))
            or not 0.0 < alpha < 1.0):
        raise CIError(f"alpha must be in (0, 1), got {alpha!r}")
    if (isinstance(resamples, bool)
            or not isinstance(resamples, int) or resamples < 1):
        raise CIError(f"resamples must be a positive int, got {resamples!r}")
    vals = [float(v) for v in vals]
    n = len(vals)
    rng = random.Random(seed)
    means = sorted(math.fsum(rng.choice(vals) for _ in range(n)) / n
                   for _ in range(resamples))
    lo_i = min(max(int((alpha / 2.0) * resamples), 0), resamples - 1)
    hi_i = min(max(int(math.ceil((1.0 - alpha / 2.0) * resamples)) - 1, 0),
               resamples - 1)
    return {"lo": means[lo_i],
            "hi": means[hi_i],
            "mean": math.fsum(vals) / n,
            "n": n,
            "alpha": alpha,
            "resamples": resamples,
            "seed": seed}
