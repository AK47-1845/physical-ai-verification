"""Horizon drift (FM1): per-sample Euclidean gap, intended vs observed trace.

Same frame, same units, same length. Frame pinning is the caller's contract
(mismatched frames are rejected before calling); this module validates
lengths, dims, and finiteness. Stdlib only.
"""

import math

from engine import InputError


class DriftError(InputError):
    """Itemized validation failure. Server formats these, never stack traces."""


def _check(seq, name: str) -> int:
    if not isinstance(seq, (list, tuple)) or len(seq) == 0:
        raise DriftError(f"{name}: need a non-empty sequence of points")
    dim = None
    for i, pt in enumerate(seq):
        if not isinstance(pt, (list, tuple)) or len(pt) == 0:
            raise DriftError(f"{name}[{i}]: point must be a non-empty tuple")
        if dim is None:
            dim = len(pt)
        elif len(pt) != dim:
            raise DriftError(
                f"{name}[{i}]: dim {len(pt)} != {dim} (ragged trace)")
        for j, v in enumerate(pt):
            if (isinstance(v, bool) or not isinstance(v, (int, float))
                    or not math.isfinite(v)):
                raise DriftError(
                    f"{name}[{i}][{j}]: need finite number, got {v!r}")
    return dim


def drift_series(intended, observed) -> list:
    """Per-sample Euclidean distance. Lengths and dims must match exactly."""
    dim_i = _check(intended, "intended")
    dim_o = _check(observed, "observed")
    if dim_i != dim_o:
        raise DriftError(
            f"dim mismatch: intended dim {dim_i} != observed dim {dim_o}")
    if len(intended) != len(observed):
        raise DriftError(
            f"length mismatch: {len(intended)} != {len(observed)}")
    return [math.sqrt(math.fsum((a - b) ** 2 for a, b in zip(p, q)))
            for p, q in zip(intended, observed)]


def summarize(series) -> dict:
    """Max/mean over a drift series. Elements validated (never trust)."""
    if isinstance(series, (str, bytes, dict)):
        raise DriftError(f"series: sequence required, got "
                         f"{type(series).__name__}")
    try:
        series = list(series)
    except TypeError:
        raise DriftError(f"series: sequence required, got "
                         f"{type(series).__name__}")
    if not series:
        raise DriftError("cannot summarize an empty series")
    for i, v in enumerate(series):
        if (isinstance(v, bool) or not isinstance(v, (int, float))
                or not math.isfinite(v)):
            raise DriftError(f"series[{i}]: finite number required, "
                             f"got {v!r}")
    return {"horizon": len(series),
            "max": max(series),
            "mean": math.fsum(series) / len(series)}


def drift_report(intended, observed) -> dict:
    """Per-sample series plus summary. The M1 drift gate consumes this."""
    series = drift_series(intended, observed)
    report = {"per_sample": series}
    report.update(summarize(series))
    return report
