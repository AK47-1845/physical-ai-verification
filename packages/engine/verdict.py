"""Verdict precedence + bands. Fail-closed law lives here.

Precedence (locked, PRD FR-5): any BLOCKED => BLOCKED; else any REVIEW or
INSUFFICIENT => REVIEW; else TRUSTED. Missing evidence can never PASS.
"""

from engine import InputError

TRUSTED, REVIEW, BLOCKED = "TRUSTED", "REVIEW", "BLOCKED"
PASS, INSUFFICIENT = "PASS", "INSUFFICIENT"

_BAND_OF = {TRUSTED: "green", REVIEW: "amber", BLOCKED: "red"}

_BADGE_COLORS = {TRUSTED: "green", REVIEW: "yellow", BLOCKED: "red"}


def verdict_badge(label: str) -> dict:
    """CI badge JSON for an overall verdict (FR-31 hook contract).

    Contract: POST a run, poll its status, render this JSON as the
    badge. Labels are overall only (TRUSTED/REVIEW/BLOCKED); gate
    statuses (PASS/INSUFFICIENT) are never badge labels.
    """
    if label not in _BADGE_COLORS:
        raise InputError(f"badge label must be TRUSTED/REVIEW/BLOCKED, "
                         f"got {label!r}")
    return {"label": label, "color": _BADGE_COLORS[label],
            "badge_version": "1"}


def _is_num(v) -> bool:
    import math
    return (not isinstance(v, bool) and isinstance(v, (int, float))
            and math.isfinite(v))


def band_for(measurement: float, green: float, amber: float) -> str:
    """Lower-is-better banding: green < amber < red. Thresholds from profile.

    All three inputs must be finite non-bool numbers with green < amber.
    NaN can never reach the comparisons (nan < x is False and would
    silently mis-band); garbage raises ValueError, never bands.
    """
    for name, value in (("measurement", measurement), ("green", green),
                        ("amber", amber)):
        if not _is_num(value):
            raise InputError(f"band_for: {name} must be a finite "
                             f"number, got {value!r} (bools are not "
                             f"measurements)")
    if not green < amber:
        raise InputError(f"band_for: need green < amber, got "
                         f"{green!r}, {amber!r}")
    if measurement < green:
        return "green"
    if measurement < amber:
        return "amber"
    return "red"


# Verdict lattice (locked, PRD FR-5 - spec-literal, documented here
# because a reviewer hypothesized BLOCKED > INSUFFICIENT > REVIEW):
# any BLOCKED => BLOCKED; else any REVIEW or INSUFFICIENT => REVIEW;
# else TRUSTED. INSUFFICIENT collapses to REVIEW at the overall level
# (missing evidence can never PASS, but it is not a proven breach).
# Worst-of combining; order-independent by construction.
def decide(gate_outcomes) -> tuple:
    """Decide overall label from per-gate statuses.

    gate_outcomes: iterable of (gate_id, status) with gate_id a
    non-empty string and status in {PASS, REVIEW, BLOCKED,
    INSUFFICIENT}. Only ValueError escapes (malformed input is a
    caller bug, never a crash).
    Returns (label, band, reasons[]) with reasons naming deciding gates.
    """
    try:
        outcomes = list(gate_outcomes)
    except TypeError:
        raise InputError("decide: gate_outcomes must be an iterable "
                         f"of (gate_id, status), got "
                         f"{type(gate_outcomes).__name__}")
    if not outcomes:
        return REVIEW, "amber", ["no gates evaluated: INSUFFICIENT"]
    valid = {PASS, REVIEW, BLOCKED, INSUFFICIENT}
    pairs = []
    for pos, entry in enumerate(outcomes):
        try:
            gid, st = entry
        except (TypeError, ValueError):
            raise InputError(f"decide: entry {pos} must be a "
                             f"(gate_id, status) pair, got {entry!r}")
        if not gid or not isinstance(gid, str):
            raise InputError(f"decide: entry {pos} gate_id must be a "
                             f"non-empty string, got {gid!r}")
        pairs.append((gid, st))
    for gid, st in pairs:
        if st not in valid:
            raise InputError(f"gate {gid!r}: bad status {st!r}")
    blocked = [g for g, s in outcomes if s == BLOCKED]
    if blocked:
        return BLOCKED, "red", [f"{g}=BLOCKED" for g in blocked]
    weak = [(g, s) for g, s in outcomes if s in (REVIEW, INSUFFICIENT)]
    if weak:
        return REVIEW, "amber", [f"{g}={s}" for g, s in weak]
    return TRUSTED, "green", ["all gates PASS"]
