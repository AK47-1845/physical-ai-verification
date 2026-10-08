"""Collapse sentinels: variance, tail-mass, and quantile drift per column.

Early collapse (Shumailov) eats tails and variance first. These sentinels
compare a baseline (trusted, usually real) column distribution against a
current (candidate, usually synthetic-heavy) one and say OK, COLLAPSE_RISK,
or INSUFFICIENT. Plain lists of numbers in; no pandas, no numpy. The
service layer projects DataFrames to columns before calling.
"""

import math

from engine import InputError


class SentinelError(InputError):
    """Itemized validation failure. Server formats these, never traces."""


def _clean(values, where: str) -> list:
    if not isinstance(values, (list, tuple)):
        raise SentinelError(f"{where}: list of numbers required")
    out = []
    for i, v in enumerate(values):
        if (isinstance(v, bool) or not isinstance(v, (int, float))
                or not math.isfinite(v)):
            raise SentinelError(f"{where}[{i}]: finite number required, "
                                f"got {v!r}")
        out.append(float(v))
    return out


def _mean(values: list) -> float:
    return math.fsum(values) / len(values)


def _pvar(values: list, mean: float) -> float:
    return math.fsum((v - mean) ** 2 for v in values) / len(values)


def _median(values: list) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _tail_mass(values: list, mean: float, std: float) -> float:
    if std <= 0:
        return 0.0
    edge = 2.0 * std
    outside = sum(1 for v in values if abs(v - mean) > edge)
    return outside / len(values)


def collapse_report(baseline: dict, current: dict, *, var_floor=0.5,
                    tail_floor=0.5, drift_cap=1.0) -> dict:
    """Per-column collapse verdicts + worst-case overall.

    baseline/current: {column_name: [numbers]}. A column missing from
    current, with < 2 baseline points, or with zero baseline variance is
    INSUFFICIENT (fail-closed: no variance to compare against).
    """
    if not isinstance(baseline, dict) or not baseline:
        raise SentinelError("baseline: non-empty {column: [numbers]} dict")
    if not isinstance(current, dict):
        raise SentinelError("current: {column: [numbers]} dict required")
    for label, floor in (("var_floor", var_floor),
                         ("tail_floor", tail_floor),
                         ("drift_cap", drift_cap)):
        if (isinstance(floor, bool) or not isinstance(floor, (int, float))
                or not math.isfinite(floor) or not floor >= 0):
            raise SentinelError(f"{label}: finite number >= 0 required")
    columns = {}
    for name, raw_base in baseline.items():
        if not isinstance(name, str):
            raise SentinelError(f"baseline: string column names required, "
                                f"got {name!r}")
        base = _clean(raw_base, f"baseline[{name!r}]")
        if name not in current:
            columns[name] = {"status": "INSUFFICIENT",
                             "reason": "column missing from current"}
            continue
        cur = _clean(current[name], f"current[{name!r}]")
        if len(base) < 2 or len(cur) < 1:
            columns[name] = {"status": "INSUFFICIENT",
                             "reason": "need >= 2 baseline and >= 1 current"}
            continue
        b_mean = _mean(base)
        b_var = _pvar(base, b_mean)
        if b_var <= 0:
            columns[name] = {"status": "INSUFFICIENT",
                             "reason": "zero baseline variance"}
            continue
        b_std = math.sqrt(b_var)
        c_mean = _mean(cur)
        variance_ratio = _pvar(cur, c_mean) / b_var
        base_tail = _tail_mass(base, b_mean, b_std)
        if base_tail <= 0:
            tail_ratio = None
        else:
            tail_ratio = _tail_mass(cur, b_mean, b_std) / base_tail
        quantile_drift = abs(_median(cur) - _median(base)) / b_std
        status = "OK"
        if variance_ratio < var_floor:
            status = "COLLAPSE_RISK"
        elif tail_ratio is not None and tail_ratio < tail_floor:
            status = "COLLAPSE_RISK"
        elif quantile_drift > drift_cap:
            status = "COLLAPSE_RISK"
        columns[name] = {"variance_ratio": variance_ratio,
                         "tail_mass_ratio": tail_ratio,
                         "quantile_drift": quantile_drift,
                         "status": status}
    overall = "OK"
    for col in columns.values():
        if col["status"] == "COLLAPSE_RISK":
            overall = "COLLAPSE_RISK"
            break
    if overall == "OK" and any(c["status"] == "INSUFFICIENT"
                               for c in columns.values()):
        overall = "INSUFFICIENT"
    unscored = sorted((k for k in current if k not in baseline),
                      key=repr)
    return {"columns": columns, "overall": overall,
            "unscored_current_columns": unscored,
            "thresholds": {"var_floor": var_floor,
                           "tail_floor": tail_floor,
                           "drift_cap": drift_cap}}
