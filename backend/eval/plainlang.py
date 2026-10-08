"""Plain-language templates for the release view-model.

Every user-facing string the UI renders comes from here (fixed
templates over measured values; no free-form LLM text). Display
only: nothing here is hashed. Wording obeys the claims lint
(no unqualified assurance superlatives; the banned list lives in
claims_allowlist.json).
"""

BAND_RANK = {"green": 0, "amber": 1, "red": 2}


def fmt(value) -> str:
    """Short display rendering for a measurement or threshold."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def verdict_plain(label, *, blocked, review, insufficient) -> str:
    """One-line shipping guidance for an overall verdict."""
    if insufficient:
        names = ", ".join(insufficient)
        return (f"Not enough evidence to judge: {len(insufficient)} "
                f"gate(s) lack evidence ({names}).")
    if label == "BLOCKED":
        names = ", ".join(blocked)
        return (f"Do not ship: {len(blocked)} gate(s) blocked "
                f"({names}).")
    if label == "REVIEW":
        names = ", ".join(review)
        return (f"Review before shipping: {len(review)} gate(s) need "
                f"review ({names}).")
    return "Passed these checks: all gates green."


def headline(label, total, *, worst=None) -> str:
    """Single-sentence reason line under the banner."""
    if label == "BLOCKED":
        edge = (f"vs amber {fmt(worst['amber'])}"
                if worst["amber"] is not None else "vs unrecorded bands")
        return (f"{worst['blocked']} of {total} gates blocked "
                f"(worst: {worst['gate']} at {fmt(worst['m'])} {edge}).")
    if label == "REVIEW":
        if worst.get("insufficient"):
            return (f"{worst['insufficient']} of {total} gates lack "
                    f"evidence (worst gap: {worst['gate']}).")
        return (f"{worst['review']} of {total} gates need review "
                f"(worst: {worst['gate']} at {fmt(worst['m'])}).")
    return f"All {total} gates passed."


def reason_text(gate, band, measurement, *, green=None, amber=None,
                higher=False, note=None) -> str:
    """Plain sentence for one gate row."""
    if band == "grey":
        return f"{gate}: not enough evidence ({note or 'below minimum n'})."
    if green is None or amber is None:
        return (f"{gate} measured {fmt(measurement)} ({band} band; "
                f"thresholds unrecorded).")
    direction = "at or above" if higher else "at or below"
    if band == "green":
        edge = green if not higher else amber
        return (f"{gate} measured {fmt(measurement)}, inside green "
                f"({direction} {fmt(edge)}).")
    if band == "amber":
        return (f"{gate} measured {fmt(measurement)}, in the review "
                f"band ({fmt(green)}-{fmt(amber)}).")
    edge = amber if not higher else green
    return (f"{gate} measured {fmt(measurement)}, outside amber "
            f"(must be {direction} {fmt(edge)}).")


def change_text(gate, measurement, *, green, amber, higher,
                band) -> str:
    """Smallest movement that improves one blocking gate's band."""
    if higher:
        if band == "red":
            want = green
            move = f"raise {gate} from {fmt(measurement)} to above " \
                f"{fmt(want)} (delta {fmt(want - measurement)})"
        else:
            want = amber
            move = f"raise {gate} from {fmt(measurement)} to above " \
                f"{fmt(want)} for green (delta {fmt(want - measurement)})"
    else:
        if band == "red":
            want = amber
            move = f"reduce {gate} from {fmt(measurement)} to below " \
                f"{fmt(want)} (delta {fmt(measurement - want)})"
        else:
            want = green
            move = f"reduce {gate} from {fmt(measurement)} to below " \
                f"{fmt(want)} for green (delta {fmt(measurement - want)})"
    return move + "."


def scope_line(model_hash, odd) -> str:
    """What this release judgement is scoped to."""
    if model_hash and odd:
        return f"Scoped to model {model_hash[:19]}... in: {odd[:80]}"
    if model_hash:
        return f"Scoped to model {model_hash[:19]}... (no ODD recorded)"
    return "No dossier linked: compile one to pin model + ODD."
