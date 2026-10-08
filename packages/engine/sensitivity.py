"""Action sensitivity (FM4 shuffle test): does the model steer or play back?

If shuffling the action stream leaves predictions (nearly) unchanged, the
model marginalizes actions: plausible motion, unsteerable playback.
Seeded shuffle => deterministic verdict for a fixed seed. Stdlib only.
"""

import math
import random

from engine import InputError


class SensitivityError(InputError):
    """Itemized validation failure. Server formats these, never stack traces."""


def _as_vector(vec, name: str) -> list:
    if not isinstance(vec, (list, tuple)) or len(vec) == 0:
        raise SensitivityError(f"{name}: need a non-empty numeric vector")
    out = []
    for i, v in enumerate(vec):
        if (isinstance(v, bool) or not isinstance(v, (int, float))
                or not math.isfinite(v)):
            raise SensitivityError(
                f"{name}[{i}]: need finite number, got {v!r}")
        out.append(float(v))
    return out


def action_sensitivity(predict, z, actions, *, seed, threshold=1e-9) -> dict:
    """Mean squared prediction shift under a seeded action shuffle.

    predict(z, actions) -> vector. statistic ~= 0 means the action stream
    is ignored (marginalized=True). NOTE: a shuffle can theoretically come
    back identical (p=1/n!); verdicts are per-seed and seeds are recorded.
    Bytes seeds echo raw (hash callers normalize first; prefer int|str).
    """
    if not callable(predict):
        raise SensitivityError("predict must be callable(z, actions)")
    if (isinstance(seed, bool)
            or not isinstance(seed, (int, str, bytes))):
        raise SensitivityError(
            f"seed must be an explicit int, str, or bytes: {seed!r}")
    if (isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(threshold) or not threshold >= 0):
        raise SensitivityError(
            f"threshold: finite number >= 0 required: {threshold!r}")
    if isinstance(actions, (str, bytes, dict)):
        raise SensitivityError(
            f"actions: sequence required, got {type(actions).__name__}")
    try:
        actions = list(actions)
    except TypeError:
        raise SensitivityError(
            f"actions: sequence required, got {type(actions).__name__}")
    if len(actions) < 2:
        raise SensitivityError("need >= 2 actions (a 1-action shuffle "
                               "is identical by construction)")
    try:
        base = _as_vector(predict(z, actions), "predict()")
    except SensitivityError:
        raise
    except Exception as exc:
        raise SensitivityError(f"predict() crashed on base actions: {exc}")
    rng = random.Random(seed)
    shuffled = actions[:]
    rng.shuffle(shuffled)
    try:
        alt = _as_vector(predict(z, shuffled), "predict() shuffled")
    except SensitivityError:
        raise
    except Exception as exc:
        raise SensitivityError(f"predict() crashed on shuffled actions: "
                               f"{exc}")
    if len(alt) != len(base):
        raise SensitivityError(
            "predict() changed output dim under shuffle: "
            f"{len(base)} != {len(alt)}")
    statistic = math.fsum((a - b) ** 2 for a, b in zip(base, alt)) / len(base)
    return {"statistic": statistic,
            "marginalized": statistic <= threshold,
            "threshold": threshold,
            "seed": seed}
