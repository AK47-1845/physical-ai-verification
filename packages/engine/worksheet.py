"""FR-39 applicability worksheet: record answers, imply routes, decide nothing.

Three questions (ML safety function? self-evolving after shipment?
frozen-weight OTA?) produce an IMPLIED ROUTE CANDIDATE. The banner is
load-bearing: no legal conclusion is ever stated. Strict bools-or-None;
truthy strings are rejected (worksheets must not guess at types).
"""

from engine import InputError

BANNER = ("HUMAN AND LEGAL REVIEW REQUIRED: this worksheet records "
          "answers, never a legal conclusion.")


class WorksheetError(InputError):
    """Itemized validation failure. Server formats these, never traces."""


def _check_bool(value, name: str):
    if value is not None and not isinstance(value, bool):
        raise WorksheetError(f"{name}: True|False|None required, "
                             f"got {value!r}")
    return value


def record(*, product: str, analyst: str, ml_safety_function,
           self_evolving, frozen_weight_ota) -> dict:
    """Record answers + implied route candidate. Humans decide the route."""
    if not product or not isinstance(product, str):
        raise WorksheetError("product: non-empty string required")
    if not analyst or not isinstance(analyst, str):
        raise WorksheetError("analyst: non-empty string required")
    ml = _check_bool(ml_safety_function, "ml_safety_function")
    evo = _check_bool(self_evolving, "self_evolving")
    ota = _check_bool(frozen_weight_ota, "frozen_weight_ota")
    answers = {"ml_safety_function": ml, "self_evolving": evo,
               "frozen_weight_ota": ota}
    if ml is False:
        route = "OUT_OF_SCOPE_CANDIDATE"
    elif ml is None or evo is None or ota is None:
        route = "UNRESOLVED_INPUTS"
    elif evo is True:
        route = "PART_A_5_6_NOTIFIED_BODY_ROUTE"
    elif ota is True:
        route = "SUBSTANTIAL_MODIFICATION_REVIEW"
    else:
        route = "STANDARD_CONFORMITY_ROUTE"
    return {"product": product, "analyst": analyst, "answers": answers,
            "implied_route": route, "banner": BANNER}
