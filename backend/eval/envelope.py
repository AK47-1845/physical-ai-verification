"""Behavioural envelope inferrer: boundary maps from hunt trials.

Honest "reverse engineering": given M4 hunt trials (params + breaks),
infer the MARGINAL break boundary per parameter (smallest breaking value,
largest holding value, observed ranges). Marginal means one-parameter-at-
a-time: interactions need joint analysis (M4b, not claimed here). The
output is the failure-boundary map stakeholders asked for, labeled with
exactly what it is and is not.
"""

import math

from engine import InputError


class EnvelopeError(InputError):
    """Itemized validation failure. Server formats these, never traces."""


def infer_envelope(trials: list, *, param_names: list) -> dict:
    """Marginal break/hold boundaries per parameter from hunt trials."""
    try:
        trials = list(trials)
    except TypeError:
        raise EnvelopeError(
            f"trials: sequence required, got {type(trials).__name__}")
    if not trials:
        raise EnvelopeError("need at least one trial")
    if isinstance(param_names, str):
        raise EnvelopeError("param_names: list of names, not one string")
    try:
        param_names = list(param_names)
    except TypeError:
        raise EnvelopeError("param_names: sequence of names required")
    if not param_names:
        raise EnvelopeError("param_names: non-empty list required")
    for num, trial in enumerate(trials):
        if not isinstance(trial, dict):
            raise EnvelopeError(f"trial {num}: dict required")
        if "breaks" not in trial or not isinstance(trial["breaks"], bool):
            raise EnvelopeError(f"trial {num}: 'breaks' bool required")
        params = trial.get("params")
        if not isinstance(params, dict):
            raise EnvelopeError(f"trial {num}: params dict required")
        for name in param_names:
            v = params.get(name)
            if (isinstance(v, bool) or not isinstance(v, (int, float))
                    or not math.isfinite(v)):
                raise EnvelopeError(
                    f"trial {num}: params[{name!r}] finite numeric "
                    f"required")
    params = {}
    for name in param_names:
        breaking = [t["params"][name] for t in trials if t["breaks"]]
        holding = [t["params"][name] for t in trials if not t["breaks"]]
        params[name] = {
            "n_breaks": len(breaking),
            "n_holds": len(holding),
            "min_break": min(breaking) if breaking else None,
            "max_break": max(breaking) if breaking else None,
            "min_hold": min(holding) if holding else None,
            "max_hold": max(holding) if holding else None,
        }
    return {"params": params, "trials": len(trials),
            "note": ("MARGINAL boundaries (one parameter at a time); "
                     "interactions need joint analysis (M4b)")}
