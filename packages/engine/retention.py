"""FR-43 safety-decision log retention: configurable, default 12 months.

Pure policy helpers; the store layer enforces, this module decides.
Timestamps are explicit epoch ints (offline law: no wall-clock reads).
A month counts as 30 days: a documented approximation for policy
math, not a legal definition. The IES-guide basis for the 12-month
default is still [VERIFY] (PRD FR-43); the default stands until an
external reviewer says otherwise.
"""

from engine import InputError

DEFAULT_MONTHS = 12
_MIN_MONTHS, _MAX_MONTHS = 1, 120


class RetentionError(InputError):
    """Itemized validation failure. Server formats these, never traces."""


def _need_months(months) -> int:
    if months is None:
        return DEFAULT_MONTHS
    if (isinstance(months, bool) or not isinstance(months, int)
            or not _MIN_MONTHS <= months <= _MAX_MONTHS):
        raise RetentionError(f"months: int in "
                             f"[{_MIN_MONTHS}, {_MAX_MONTHS}] required: "
                             f"{months!r}")
    return months


def retention_policy(*, months=None) -> dict:
    """Declare the retention window. Default 12 months when unset."""
    resolved = _need_months(months)
    return {"months": resolved, "days": resolved * 30,
            "default_applied": months is None}


def due_for_purge(*, decided_ts: int, now_ts: int,
                  months=None) -> dict:
    """Is a decision log past retention? Boundary day keeps the log.

    due flips only once age strictly exceeds the window: a log aged
    exactly the window is kept (grace to the boundary, fail-closed
    toward retention, never toward early deletion).
    """
    for label, val in (("decided_ts", decided_ts), ("now_ts", now_ts)):
        if isinstance(val, bool) or not isinstance(val, int) or val < 0:
            raise RetentionError(f"{label}: non-negative epoch int "
                                 f"required")
    if now_ts < decided_ts:
        raise RetentionError("clock skew: now_ts precedes decided_ts")
    resolved = _need_months(months)
    age_days = (now_ts - decided_ts) / 86400.0
    due = age_days > resolved * 30
    return {"due": due, "age_days": age_days, "months": resolved,
            "window_days": resolved * 30}
