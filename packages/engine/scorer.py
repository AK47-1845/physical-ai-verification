"""Gate evaluation + scorecard assembly (M1 capstone).

Ties measurements to bands, bands to statuses, statuses to verdicts, and
verdicts to pinned envelopes. Fail-closed: below-minimum-n gates report
INSUFFICIENT (band grey), which can only ever resolve to REVIEW or worse.
"""

from engine import InputError, pin_artifact
from engine.verdict import BLOCKED, INSUFFICIENT, PASS, REVIEW, band_for, decide


class ScorerError(InputError):
    """Itemized validation failure. Server formats these, never stack traces."""


def _is_num(v) -> bool:
    import math
    return (not isinstance(v, bool) and isinstance(v, (int, float))
            and math.isfinite(v))


def evaluate_gate(gate_id, measurement, *, green, amber, evidence,
                  min_n=None, n=None, higher_is_better=False) -> dict:
    """Score one gate. Thresholds always given green < amber (natural order).

    higher_is_better flips the comparison (e.g. success rates) while bands
    keep their lower-is-better engine. evidence is an opaque pointer string.
    """
    if not gate_id or not isinstance(gate_id, str):
        raise ScorerError(f"gate_id must be a non-empty string: {gate_id!r}")
    if not _is_num(measurement):
        raise ScorerError(f"{gate_id}: measurement must be finite: "
                          f"{measurement!r}")
    if not _is_num(green) or not _is_num(amber) or not green < amber:
        raise ScorerError(
            f"{gate_id}: need green < amber thresholds: {green!r}, {amber!r}")
    if not evidence or not isinstance(evidence, str):
        raise ScorerError(f"{gate_id}: evidence pointer required")
    if min_n is not None:
        if (isinstance(min_n, bool) or not isinstance(min_n, int)
                or min_n < 0):
            raise ScorerError(f"{gate_id}: min_n must be a non-negative "
                              f"int: {min_n!r}")
        if n is not None and (isinstance(n, bool)
                              or not isinstance(n, int)):
            raise ScorerError(f"{gate_id}: n must be an int or None: "
                              f"{n!r}")
        if n is None or n < min_n:
            return {"gate": gate_id, "measurement": measurement,
                    "band": "grey", "status": INSUFFICIENT,
                    "evidence": evidence,
                    "note": f"n={n} below minimum {min_n}"}
    m, lo, hi = measurement, green, amber
    if higher_is_better:
        m, lo, hi = -measurement, -amber, -green
    band = band_for(m, lo, hi)
    status = PASS if band == "green" else (REVIEW if band == "amber"
                                           else BLOCKED)
    return {"gate": gate_id, "measurement": measurement, "band": band,
            "status": status, "evidence": evidence}


_LABEL_RANK = {"BLOCKED": 0, "REVIEW": 1, "TRUSTED": 2}


def rank_policies(entries) -> dict:
    """Batch rank N policies worst-first by worst-gate margin (FR-6).

    entries: [{policy_id, verdict, gates: [{status, ...}]}] with
    verdict an overall label (TRUSTED/REVIEW/BLOCKED) and status a
    gate status. Order: worst label first, then most BLOCKED gates,
    then most REVIEW/INSUFFICIENT, then policy_id (deterministic).
    Triage reads top-down: the top row needs engineers first.
    """
    try:
        entries = list(entries)
    except TypeError:
        raise ScorerError("entries: non-empty list required")
    if not entries:
        raise ScorerError("entries: non-empty list required")
    seen, rows = set(), []
    for pos, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ScorerError(f"entry {pos}: dict required")
        pid = entry.get("policy_id")
        if not pid or not isinstance(pid, str):
            raise ScorerError(f"entry {pos}: policy_id non-empty "
                              f"string required")
        if pid in seen:
            raise ScorerError(f"entry {pos}: duplicate policy_id "
                              f"{pid!r}")
        seen.add(pid)
        verdict = entry.get("verdict")
        if verdict not in _LABEL_RANK:
            raise ScorerError(f"entry {pos}: verdict must be "
                              f"TRUSTED/REVIEW/BLOCKED, got {verdict!r}")
        gates = entry.get("gates")
        if not isinstance(gates, list) or not gates:
            raise ScorerError(f"entry {pos}: non-empty gates list "
                              f"required")
        blocked = review = 0
        for gpos, gate in enumerate(gates):
            if not isinstance(gate, dict):
                raise ScorerError(f"entry {pos} gate {gpos}: dict "
                                  f"required")
            status = gate.get("status")
            if status == BLOCKED:
                blocked += 1
            elif status in (REVIEW, INSUFFICIENT):
                review += 1
            elif status != PASS:
                raise ScorerError(f"entry {pos} gate {gpos}: bad "
                                  f"status {status!r}")
        rows.append({"policy_id": pid, "verdict": verdict,
                     "gates": len(gates), "blocked": blocked,
                     "review": review})
    rows.sort(key=lambda r: (_LABEL_RANK[r["verdict"]], -r["blocked"],
                             -r["review"], r["policy_id"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return {"ranking": [r["policy_id"] for r in rows], "rows": rows,
            "policies": len(rows)}


def evaluate_scorecard(gate_dicts, *, profile_version, seed) -> dict:
    """Assemble + pin a scorecard. Verdict precedence lives in decide().

    Speaks ScorerError only: malformed gates and bad statuses are
    itemized here (decide()'s raw ValueError is translated). Seeds
    are pinned int|str (bytes/dicts hash badly); profile versions
    are non-empty strings.
    """
    if isinstance(seed, bool) or not isinstance(seed, (int, str)):
        raise ScorerError(f"seed: pinnable int|str required, got "
                          f"{seed!r} (bools are not seeds)")
    if not profile_version or not isinstance(profile_version, str):
        raise ScorerError(f"profile_version: non-empty string required, "
                          f"got {profile_version!r}")
    try:
        gate_dicts = list(gate_dicts)
    except TypeError:
        raise ScorerError("gate_dicts: iterable of gate dicts required")
    outcomes = []
    for pos, gate in enumerate(gate_dicts):
        if not isinstance(gate, dict):
            raise ScorerError(f"gate {pos}: dict required")
        try:
            outcomes.append((gate["gate"], gate["status"]))
        except KeyError as exc:
            raise ScorerError(f"gate {pos}: missing {exc} "
                              f"(need 'gate' + 'status')")
    try:
        label, band, reasons = decide(outcomes)
    except ValueError as exc:
        raise ScorerError(str(exc))
    payload = {"gates": gate_dicts, "verdict": label, "band": band,
               "reasons": reasons, "seed": seed}
    return pin_artifact(payload, profile_version=profile_version)
