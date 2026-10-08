"""NB briefing view data (A4 backend): dossier walkthrough JSON.

Assembles the read-only auditor walkthrough from a PAR envelope plus
optional worksheet, credibility cards, and ledger verdict: policy and
release, gate table, independence, worksheet route, card lift status,
ledger state. Anything missing or failing lands in `attention` FIRST:
auditors read the gaps before the glory. Frontend renders; this module
only assembles + validates (invalid PAR = loud refusal).
"""

from engine import InputError
from engine.credibility import can_lift_draft
from engine.ota import par_currency
from engine.par import validate_par


class BriefingError(InputError):
    """Refusals. A briefing on bad evidence is worse than none."""


_SCOPING_QUESTION = ("Does the ML component ensure a safety "
                       "function? (Y -> Part A route, notified-body "
                       "type-examination; N -> document the independent "
                       "safety architecture)")

_ROUTE_GUIDANCE = {
    "PART_A_5_6_NOTIFIED_BODY_ROUTE":
        "Part A route candidate: notified-body type-examination "
        "(human + legal review required).",
    "SUBSTANTIAL_MODIFICATION_REVIEW":
        "Substantial-modification review candidate "
        "(human + legal review required).",
    "OUT_OF_SCOPE_CANDIDATE":
        "Out-of-scope candidate: document the independent safety "
        "architecture (human + legal review required).",
    "UNRESOLVED_INPUTS":
        "Inputs unresolved: answer all three worksheet questions.",
    "STANDARD_CONFORMITY_ROUTE":
        "Standard conformity route candidate "
        "(human + legal review required).",
}


def _scoping(worksheet) -> dict:
    """First-section rows: the scoping question + recorded answers."""
    if worksheet is None:
        return {"question": _SCOPING_QUESTION,
                "ml_safety_function": "UNANSWERED",
                "implied_route": None,
                "guidance": "Answer the worksheet: the route cannot "
                           "be implied.",
                "banner": None}
    answers = worksheet.get("answers", {})
    if not isinstance(answers, dict):
        raise BriefingError("worksheet.answers: dict required")
    ml = answers.get("ml_safety_function")
    route = worksheet.get("implied_route")
    return {"question": _SCOPING_QUESTION,
            "ml_safety_function": "Y" if ml is True
            else ("N" if ml is False else "UNANSWERED"),
            "implied_route": route,
            "guidance": _ROUTE_GUIDANCE.get(route, "Route unimplied."),
            "banner": worksheet.get("banner")}


def _sections(body: dict) -> tuple:
    """Build the three PAR-owned sections. May KeyError; caller wraps."""
    attention = []
    if body["release"]["delta"] == "SUBSTANTIAL_MODIFICATION_CANDIDATE":
        attention.append("release: SUBSTANTIAL_MODIFICATION_CANDIDATE")
    blocked = [g["id"] for g in body["gates"]
               if g["verdict"] == "BLOCKED"]
    for gid in blocked:
        attention.append(f"gate BLOCKED: {gid}")
    insufficient = [g["id"] for g in body["gates"]
                    if g["verdict"] == "INSUFFICIENT"]
    for gid in insufficient:
        attention.append(f"gate INSUFFICIENT (missing evidence): {gid}")
    sections = [
        {"title": "Policy and release",
         "rows": {"policy": body["policy"]["id"],
                  "weights": body["policy"]["weights"],
                  "release_delta": body["release"]["delta"],
                  "odd": body["odd"]}},
        {"title": "Gates",
         "rows": [{"id": g["id"], "verdict": g["verdict"],
                   "evidence": g.get("evidence")} for g in body["gates"]]},
        {"title": "Independence register", "rows": body["independence"]},
    ]
    trace = body.get("hazard_trace")
    if trace is not None:
        gate_ids = {g["id"] for g in body["gates"]}
        covered = sorted(h["hazard_id"] for h in trace
                         if set(h["gate_ids"]) & gate_ids)
        gaps = sorted(h["hazard_id"] for h in trace
                      if not (set(h["gate_ids"]) & gate_ids))
        sections.append({"title": "Hazard coverage",
                         "rows": {"covered": covered, "gaps": gaps}})
        for hid in gaps:
            attention.append(f"hazard {hid} has no covering gate")
    return sections, attention, blocked


def briefing_view(par_envelope: dict, *, worksheet: dict | None = None,
                  cards: list | None = None,
                  ledger_verdict: dict | None = None,
                  vault: dict | None = None) -> dict:
    """Assemble ordered sections + attention list for the NB walkthrough."""
    check = validate_par(par_envelope)
    if not check["ok"]:
        raise BriefingError(f"cannot brief on invalid PAR: {check['reason']}")
    try:
        sections, attention, blocked = _sections(par_envelope["par"])
    except (KeyError, TypeError, IndexError) as exc:
        raise BriefingError(f"PAR body incomplete: {exc}") from exc
    if vault is not None:
        if not isinstance(vault, dict):
            raise BriefingError("vault: dict or None required")
        try:
            currency = par_currency(
                vault, par_envelope["par"]["policy"]["weights"])
        except (KeyError, TypeError) as exc:
            raise BriefingError(f"PAR body incomplete: {exc}") from exc
        sections.append({"title": "PAR currency vs OTA vault",
                         "rows": currency})
        if currency["status"] == "SUPERSEDED":
            attention.append(
                "par SUPERSEDED by " + ",".join(currency["by"]))
        elif currency["status"] == "UNKNOWN_WEIGHTS":
            attention.append("par weights unknown to the given vault")
    if worksheet is not None and not isinstance(worksheet, dict):
        raise BriefingError("worksheet: dict or None required")
    sections.insert(0, {"title": "Scoping", "rows": _scoping(worksheet)})
    if worksheet is None:
        attention.append("worksheet: missing (route unimplied)")
        sections.append({"title": "Applicability worksheet",
                         "rows": {"status": "MISSING"}})
    else:
        sections.append({"title": "Applicability worksheet",
                         "rows": {"route": worksheet.get("implied_route"),
                                  "banner": worksheet.get("banner")}})
    if cards is not None and not isinstance(cards, list):
        raise BriefingError("cards: list of card envelopes or None")
    card_rows = []
    for card in cards or []:
        lift = can_lift_draft(card)
        inner = card.get("card") if isinstance(card, dict) else None
        gate = (inner or {}).get("gate_id", "?")
        card_rows.append({"gate": gate, "lift": lift["lift"],
                          "reasons": lift["reasons"]})
        if not lift["lift"]:
            attention.append(f"credibility: {gate} cannot lift DRAFT")
    sections.append({"title": "Credibility cards", "rows": card_rows})
    if ledger_verdict is None:
        attention.append("ledger: unverified in this briefing")
        sections.append({"title": "Ledger",
                         "rows": {"status": "UNVERIFIED_HERE"}})
    else:
        if not isinstance(ledger_verdict, dict):
            raise BriefingError("ledger_verdict: dict or None required")
        ok = bool(ledger_verdict.get("ok"))
        sections.append({"title": "Ledger", "rows": ledger_verdict})
        if not ok:
            attention.append("ledger: CHAIN INVALID "
                             f"(first bad: {ledger_verdict.get('first_bad')})")
    return {"sections": sections, "attention": attention,
            "blocked_count": len(blocked)}
