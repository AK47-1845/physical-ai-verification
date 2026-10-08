"""Deterministic fixture policies (MVP steal, production-hardened).

Four trajectory fixtures as functions of (actions, seed): clean, drifty,
playback, synthfed. Same stories as the MVP, generalized horizon T and
validated inputs. These are rollout FUNCTIONS for hunts and probes;
backend/fixtures.py (mirror) holds Trace SCENARIOS instead. The two
complement: scenarios stage datasets, these drive searches.
Stdlib only.
"""

import math
import random

from engine import InputError

PROBE_OFFSET = (0.5, -0.3)


def _check_actions(actions) -> list:
    try:
        rows = [list(row) for row in actions]
    except TypeError:
        raise InputError("actions: sequence of 2-vectors required")
    if not rows:
        raise InputError("actions: non-empty sequence required")
    for row in rows:
        if (len(row) < 2 or any(isinstance(v, bool) for v in row[:2])
                or not all(isinstance(v, (int, float))
                           for v in row[:2])):
            raise InputError("actions: 2-vectors required "
                             "(bools are not commands)")
    return rows


def _check_seed(seed) -> int:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise InputError(f"seed: int required, got {seed!r} "
                         f"(bools are not seeds)")
    return seed


def _check_noise(noise_scale) -> float:
    if (isinstance(noise_scale, bool)
            or not isinstance(noise_scale, (int, float))
            or not math.isfinite(noise_scale) or noise_scale < 0):
        raise InputError(f"noise_scale: finite number >= 0 required, got "
                         f"{noise_scale!r} (bools are not scales)")
    return float(noise_scale)


def reference_actions(horizon: int = 200) -> list:
    """Sin/cos command path. horizon >= 4 required."""
    if (isinstance(horizon, bool) or not isinstance(horizon, int)
            or horizon < 4):
        raise InputError(f"horizon: int >= 4, got {horizon!r} "
                         f"(bools are not horizons)")
    return [[math.sin(4 * math.pi * t / (horizon - 1)),
             math.cos(2 * math.pi * t / (horizon - 1))]
            for t in range(horizon)]


def probe_actions(actions: list) -> list:
    """Step-offset the second half (FM4 probe). Returns a new list."""
    try:
        out = [list(row) for row in actions]
    except TypeError:
        raise InputError("actions: sequence of 2-vectors required")
    for row in out:
        if (len(row) < 2 or any(isinstance(v, bool) for v in row[:2])
                or not all(isinstance(v, (int, float))
                           for v in row[:2])):
            raise InputError("actions: 2-vectors required "
                             "(bools are not commands)")
    for t in range(len(out) // 2, len(out)):
        out[t][0] += PROBE_OFFSET[0]
        out[t][1] += PROBE_OFFSET[1]
    return out


def clean_rollout(actions, seed: int = 0, noise_scale: float = 1.0) -> list:
    """Tracks commands with small Gaussian noise. Expected: TRUSTED."""
    actions = _check_actions(actions)
    seed = _check_seed(seed)
    noise_scale = _check_noise(noise_scale)
    rng = random.Random(seed)
    s = 0.03 * noise_scale
    return [[a[0] + rng.gauss(0.0, s), a[1] + rng.gauss(0.0, s)]
            for a in actions]


def drifty_rollout(actions, seed: int = 0, noise_scale: float = 1.0) -> list:
    """Random-walk error compounds down-horizon. Expected: BLOCKED."""
    actions = _check_actions(actions)
    seed = _check_seed(seed)
    noise_scale = _check_noise(noise_scale)
    rng = random.Random(seed)
    s = 0.05 * noise_scale
    wx, wy, out = 0.0, 0.0, []
    for a in actions:
        wx += rng.gauss(0.0, s)
        wy += rng.gauss(0.0, s)
        out.append([a[0] + wx, a[1] + wy])
    return out


def playback_rollout(actions, seed: int = 0, noise_scale: float = 1.0) -> list:
    """Fixed tape, ignores controls. Expected: BLOCKED, response 0.0."""
    actions = _check_actions(actions)
    # Validated then ignored: a fixed tape takes no seed, but a bool/str
    # seed must fail loudly like on every sibling, not slip through.
    _check_seed(seed)
    _check_noise(noise_scale)
    n = len(actions)
    if n < 2:
        raise InputError("playback needs >= 2 actions")
    return [[t / (n - 1), 0.0] for t in range(n)]


def synthfed_rollout(actions, seed: int = 0, noise_scale: float = 1.0) -> list:
    """Responsive but spiky with sim bias ramp. Expected: REVIEW."""
    actions = _check_actions(actions)
    seed = _check_seed(seed)
    noise_scale = _check_noise(noise_scale)
    rng = random.Random(seed)
    s = 0.08 * noise_scale
    n = len(actions)
    out = []
    for t, a in enumerate(actions):
        x = a[0] + rng.gauss(0.0, s) + 0.10 * (t / n)
        y = a[1] + rng.gauss(0.0, s) - 0.06 * (t / n)
        if rng.random() < 0.05:
            sx = 1.0 if rng.random() < 0.5 else -1.0
            sy = 1.0 if rng.random() < 0.5 else -1.0
            x += sx * rng.uniform(0.35, 0.55) * noise_scale
            y += sy * rng.uniform(0.35, 0.55) * noise_scale
        out.append([x, y])
    return out


POLICIES = {
    "clean": {"fn": clean_rollout, "title": "Clean policy",
              "story": "Tracks commands with small noise. Expected: TRUSTED."},
    "drifty": {"fn": drifty_rollout, "title": "Drifty policy",
               "story": "Random-walk error compounds. Expected: BLOCKED."},
    "playback": {"fn": playback_rollout, "title": "Playback policy",
                 "story": "Fixed tape, ignores controls. Expected: BLOCKED."},
    "synthfed": {"fn": synthfed_rollout, "title": "Synthetic-trained",
                 "story": "Responsive but spiky. Expected: REVIEW."},
}


def get_policy(policy_id: str):
    """Look up a fixture by id. Unknown ids raise KeyError (fail-closed)."""
    try:
        return POLICIES[policy_id]
    except KeyError:
        raise KeyError(f"unknown fixture policy {policy_id!r}; known: "
                       f"{sorted(POLICIES)}")
