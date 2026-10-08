"""G10 time-to-success: first-hitting-time distribution over rollouts.

success_fn(state) -> strict bool. Each rollout contributes its first
success index or None (censored: never succeeded in-horizon). Summary
reports rate, censored count, and median/mean/min/max over successes
only (None medians when nothing succeeded: nosuccess is data, not zero).
"""


from engine import InputError


class SuccessTimeError(InputError):
    """Itemized validation failure. Server formats these, never traces."""


def first_success_times(rollouts: list, success_fn) -> list:
    """First success index per rollout, None when censored."""
    if not callable(success_fn):
        raise SuccessTimeError("success_fn: callable(state)->bool required")
    if isinstance(rollouts, (str, bytes, dict)):
        raise SuccessTimeError(
            f"rollouts: sequence of rollouts required, got "
            f"{type(rollouts).__name__}")
    try:
        rollouts = list(rollouts)
    except TypeError:
        raise SuccessTimeError("rollouts: sequence required")
    if not rollouts:
        raise SuccessTimeError("need at least one rollout")
    times = []
    for num, rollout in enumerate(rollouts):
        if isinstance(rollout, (str, bytes, dict)):
            raise SuccessTimeError(
                f"rollout {num}: state sequence required, got "
                f"{type(rollout).__name__}")
        try:
            rollout = list(rollout)
        except TypeError:
            raise SuccessTimeError(f"rollout {num}: sequence required")
        if not rollout:
            raise SuccessTimeError(f"rollout {num}: empty (malformed)")
        first = None
        for i, state in enumerate(rollout):
            try:
                hit = success_fn(state)
            except Exception as exc:
                raise SuccessTimeError(
                    f"success_fn raised at rollout {num}[{i}]: {exc!r}")
            if not isinstance(hit, bool):
                raise SuccessTimeError(
                    f"success_fn must return bool (rollout {num}[{i}])")
            if hit:
                first = i
                break
        times.append(first)
    return times


def summarize_times(times: list) -> dict:
    """Distribution summary over first-success times (None = censored)."""
    try:
        times = list(times)
    except TypeError:
        raise SuccessTimeError("times: sequence required")
    if not times:
        raise SuccessTimeError("need at least one time entry")
    for t in times:
        if (t is not None
                and (isinstance(t, bool) or not isinstance(t, int)
                     or t < 0)):
            raise SuccessTimeError(f"time entries: int >= 0 or None, "
                                   f"got {t!r} (bools are not times)")
    hits = sorted(t for t in times if t is not None)
    n = len(times)
    if not hits:
        median = mean = minimum = maximum = None
    else:
        mid = len(hits) // 2
        if len(hits) % 2:
            median = float(hits[mid])
        else:
            median = (hits[mid - 1] + hits[mid]) / 2.0
        mean = sum(hits) / len(hits)
        minimum, maximum = hits[0], hits[-1]
    return {"n": n, "successes": len(hits),
            "success_rate": len(hits) / n, "censored": n - len(hits),
            "median_time": median, "mean_time": mean,
            "min_time": minimum, "max_time": maximum,
            "times": times}
