"""G11 fall/impact placeholder: DRAFT until ISO 25785-1 publishes.

The standard is unpublished, so this gate judges NOTHING: every call
returns INSUFFICIENT with DRAFT_PLACEHOLDER status. Caller-supplied
impact metrics are validated and echoed (recorded, never judged) so
future calibration has somewhere to land. No clause text exists here
because no clause text exists anywhere yet.
"""

import math

from engine import InputError

GATE_ID = "G11_fall_impact"
STATUS = "DRAFT_PLACEHOLDER"
REASON = ("ISO 25785-1 unpublished: no clause text exists, so no "
          "threshold can be set. Placeholder only.")


class FallImpactError(InputError):
    """Itemized validation failure. Server formats these, never traces."""


def assess_fall_impact(metrics=None) -> dict:
    """Record (never judge) fall/impact metrics. Always INSUFFICIENT."""
    if metrics is None:
        metrics = {}
    if not isinstance(metrics, dict):
        raise FallImpactError("metrics: {name: number} dict or None")
    for name, val in metrics.items():
        if not isinstance(name, str) or not name:
            raise FallImpactError(f"metric name must be a non-empty "
                                  f"string: {name!r}")
        if (isinstance(val, bool) or not isinstance(val, (int, float))
                or not math.isfinite(val)):
            raise FallImpactError(f"metric {name!r}: finite number "
                                  f"required, got {val!r}")
    return {"gate": GATE_ID, "status": STATUS, "verdict": "INSUFFICIENT",
            "reason": REASON, "metrics": dict(metrics)}
