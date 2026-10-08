"""M2 executability guard: supervisory joint-space envelope checks.

Validates an action chunk (K steps x J joint positions) against position
bounds, velocity caps, and acceleration caps before anything executes.
Finite differences on the chunk itself: velocity from step 1, acceleration
from step 2. Any breach => halt=True with itemized breach records.

Velocity/acceleration limits are optional keys (absent or null =
unchecked); position bounds are mandatory. Unknown limits keys are
rejected: a typo'd cap name must never silently unenforce a limit.
Singularity/task-space margins need a kinematics backend and land as
M2b, not here. Stdlib only.
"""

import math

from engine import InputError


class GuardError(InputError):
    """Itemized validation failure. Server formats these, never stack traces."""


def _is_num(v) -> bool:
    return (not isinstance(v, bool) and isinstance(v, (int, float))
            and math.isfinite(v))


def check_chunk(positions, limits: dict, *, dt) -> dict:
    """Check one chunk. Returns halt flag + breach records."""
    try:
        positions = [list(step) for step in positions]
    except TypeError:
        raise GuardError("positions: non-empty KxJ nested sequence "
                         "required (flat chunks and scalars rejected)")
    if not positions:
        raise GuardError("need a non-empty chunk of joint positions")
    joints = len(positions[0])
    if joints == 0:
        raise GuardError("joint vectors must be non-empty")
    for i, step in enumerate(positions):
        if len(step) != joints:
            raise GuardError(f"step {i}: dim {len(step)} != {joints}")
        for j, v in enumerate(step):
            if not _is_num(v):
                raise GuardError(f"step {i} joint {j}: need finite number, "
                                 f"got {v!r}")
    if not _is_num(dt) or not dt > 0:
        raise GuardError(f"dt must be a positive finite number: {dt!r}")
    if not isinstance(limits, dict) or "position" not in limits:
        raise GuardError("limits must be a dict with a 'position' key")
    for key in limits:
        if key not in ("position", "velocity", "acceleration"):
            raise GuardError(f"unknown limits key {key!r}: typo'd caps "
                             f"would silently unenforce a limit")
    pos_bounds = limits["position"]
    if not isinstance(pos_bounds, (list, tuple)):
        raise GuardError("'position': list of (lo, hi) pairs required")
    if len(pos_bounds) != joints:
        raise GuardError(f"'position' needs {joints} (lo, hi) pairs, got "
                         f"{len(pos_bounds)}")
    for j, bound in enumerate(pos_bounds):
        if (not isinstance(bound, (list, tuple)) or len(bound) != 2
                or not _is_num(bound[0]) or not _is_num(bound[1])
                or not bound[0] < bound[1]):
            raise GuardError(f"'position'[{j}]: need finite lo < hi pair")
    vel_max = _optional_caps(limits, "velocity", joints)
    acc_max = _optional_caps(limits, "acceleration", joints)

    breaches = []
    for i, step in enumerate(positions):
        for j, v in enumerate(step):
            lo, hi = pos_bounds[j]
            if v < lo or v > hi:
                breaches.append({"step": i, "joint": j, "check": "position",
                                 "value": v, "limit": [lo, hi]})
    velocities = []
    for i in range(1, len(positions)):
        row = [(positions[i][j] - positions[i - 1][j]) / dt
               for j in range(joints)]
        velocities.append(row)
        if vel_max is not None:
            for j, v in enumerate(row):
                if abs(v) > vel_max[j]:
                    breaches.append({"step": i, "joint": j,
                                     "check": "velocity", "value": v,
                                     "limit": vel_max[j]})
    for k in range(1, len(velocities)):
        i = k + 1  # acceleration detected at chunk step i
        if acc_max is None:
            break
        for j in range(joints):
            a = (velocities[k][j] - velocities[k - 1][j]) / dt
            if abs(a) > acc_max[j]:
                breaches.append({"step": i, "joint": j,
                                 "check": "acceleration", "value": a,
                                 "limit": acc_max[j]})
    return {"halt": len(breaches) > 0, "breaches": breaches,
            "steps": len(positions), "joints": joints}


def _optional_caps(limits: dict, key: str, joints: int):
    if key not in limits or limits[key] is None:
        return None
    try:
        caps = list(limits[key])
    except TypeError:
        raise GuardError(f"'{key}': list of per-joint caps required")
    if len(caps) != joints:
        raise GuardError(f"'{key}' needs {joints} caps, got {len(caps)}")
    for j, cap in enumerate(caps):
        if not _is_num(cap) or not cap >= 0:
            raise GuardError(f"'{key}'[{j}]: need finite cap >= 0")
    return caps
