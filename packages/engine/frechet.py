"""Discrete Frechet distance (Eiter-Mannila DP). IP-roadmap vector 1
(filing planned, nothing granted).

Sim-to-real degradation metric over end-effector paths in the SAME coordinate
frame. Frames are checked by the caller contract (mismatched frames must be
rejected before calling); this module validates lengths, dims, finiteness.
Complexity O(n*m) time (~1.4us/cell), O(m) space; inputs over
MAX_CELLS refuse loudly (stride-downsample big traces and record the
stride; silent subsampling would forge the metric). Stdlib only.
"""

import math

from engine import InputError


class FrechetError(InputError):
    """Itemized validation failure. Server formats these, never stack traces."""


MAX_CELLS = 1000000


def _dist(a, b) -> float:
    return math.sqrt(math.fsum((x - y) ** 2 for x, y in zip(a, b)))


def _check_sequence(seq, name: str) -> int:
    if not isinstance(seq, (list, tuple)) or len(seq) == 0:
        raise FrechetError(f"{name}: need a non-empty sequence of points")
    dim = None
    for i, pt in enumerate(seq):
        if not isinstance(pt, (list, tuple)) or len(pt) == 0:
            raise FrechetError(f"{name}[{i}]: point must be a non-empty tuple")
        if dim is None:
            dim = len(pt)
        elif len(pt) != dim:
            raise FrechetError(
                f"{name}[{i}]: dim {len(pt)} != {dim} (ragged trace)")
        for j, v in enumerate(pt):
            if (isinstance(v, bool) or not isinstance(v, (int, float))
                    or not math.isfinite(v)):
                raise FrechetError(
                    f"{name}[{i}][{j}]: need finite number, got {v!r}")
    return dim


def discrete_frechet(p, q) -> float:
    """Discrete Frechet distance between two same-frame point sequences."""
    dim_p = _check_sequence(p, "p")
    dim_q = _check_sequence(q, "q")
    if dim_p != dim_q:
        raise FrechetError(f"dim mismatch: p dim {dim_p} != q dim {dim_q}")
    n, m = len(p), len(q)
    if n * m > MAX_CELLS:
        raise FrechetError(
            f"trace product {n}x{m}={n * m} exceeds "
            f"MAX_CELLS={MAX_CELLS} (~1.4us/cell): stride-downsample "
            f"and record the stride (silent subsampling forges it)")
    prev = [0.0] * m
    for j in range(m):
        d = _dist(p[0], q[j])
        prev[j] = d if j == 0 else max(prev[j - 1], d)
    for i in range(1, n):
        curr = [0.0] * m
        for j in range(m):
            d = _dist(p[i], q[j])
            if j == 0:
                curr[j] = max(prev[j], d)
            else:
                curr[j] = max(min(prev[j], prev[j - 1], curr[j - 1]), d)
        prev = curr
    return prev[m - 1]
