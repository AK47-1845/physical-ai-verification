"""FR-38 Policy Assurance Record: open artifact, offline reader.

The PAR is the unit of trust: policy identity, release delta, per-gate
verdicts, ledger head, independence register, plus optional credibility
and worksheet attachments. Schema is published open (see
backend/docs/par-schema.json); this module builds, hashes, validates,
and reads PARs with stdlib only so ANY third party can check our work
with zero vendor contact.
"""

import math
import re

from engine import InputError, canonical_hash


class PARError(InputError):
    """Itemized validation failure. Server formats these, never traces."""


PAR_VERSION = "0.1"

_VERDICTS = ("PASS", "REVIEW", "BLOCKED", "INSUFFICIENT")
_DELTAS = ("IN-ODD", "SUBSTANTIAL_MODIFICATION_CANDIDATE", "UNASSESSED")

_SHA_RE = re.compile(r"[0-9a-f]{64}")


def _need_sha(value, where: str) -> str:
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise PARError(f"{where}: sha256 hex required")
    return value


def _need_weight(value, where: str) -> str:
    if (not isinstance(value, str) or not value.startswith("sha256:")
            or _SHA_RE.fullmatch(value[7:]) is None):
        raise PARError(f"{where}: 'sha256:<64hex>' required")
    return value


def build_par(*, policy: dict, release: dict, gates: list,
              ledger_head: str, independence: dict, odd: str,
              credibility: dict | None = None,
              worksheet: dict | None = None,
              hazard_trace: list | None = None) -> dict:
    """Build + hash a PAR. Strict validation; nothing half-shaped ships.

    The PAR binds to its model weights (policy.weights) and its
    operating envelope (odd): it is VALID only for that model in
    that envelope. See ota.par_currency for supersession checks.
    """
    if not isinstance(policy, dict) or not policy.get("id"):
        raise PARError("policy.id: non-empty string required")
    policy = {"id": policy["id"],
              "weights": _need_weight(policy.get("weights"),
                                       "policy.weights")}
    if not isinstance(release, dict):
        raise PARError("release: dict required")
    if release.get("delta") not in _DELTAS:
        raise PARError(f"release.delta: one of {_DELTAS}")
    release = {"parent": _need_weight(release.get("parent"),
                                       "release.parent"),
               "delta": release["delta"]}
    gates = list(gates)
    if not gates:
        raise PARError("gates: non-empty list required")
    clean_gates = []
    for gate in gates:
        if not isinstance(gate, dict) or not gate.get("id"):
            raise PARError("every gate needs a string id")
        if gate.get("verdict") not in _VERDICTS:
            raise PARError(f"gate {gate.get('id')!r}: bad verdict "
                           f"{gate.get('verdict')!r}")
        measure = gate.get("measurement")
        if (measure is not None
                and (isinstance(measure, bool)
                     or not isinstance(measure, (int, float))
                     or not math.isfinite(measure))):
            raise PARError(f"gate {gate.get('id')!r}: measurement must "
                           f"be a finite number or null")
        evidence = gate.get("evidence")
        if evidence is not None and not isinstance(evidence, str):
            raise PARError(f"gate {gate.get('id')!r}: evidence must "
                           f"be a string or null")
        clean_gates.append({"id": gate["id"], "verdict": gate["verdict"],
                            "measurement": measure, "evidence": evidence})
    if not isinstance(independence, dict):
        raise PARError("independence: dict required (FR-41)")
    for key in ("builder", "funder", "relationship"):
        if (not independence.get(key)
                or not isinstance(independence[key], str)):
            raise PARError(f"independence.{key}: non-empty string required")
    if not isinstance(odd, str) or not odd.strip() or len(odd) > 2000:
        raise PARError("odd: non-empty string (<=2000 chars) required: "
                       "a PAR without its operating envelope is INSUFFICIENT")
    body = {"par_version": PAR_VERSION, "policy": policy,
            "release": release, "gates": clean_gates,
            "ledger_head": _need_sha(ledger_head, "ledger_head"),
            "odd": odd,
            "independence": {k: independence[k]
                             for k in ("builder", "funder", "relationship")}}
    if credibility is not None:
        if not isinstance(credibility, dict):
            raise PARError("credibility: dict or None")
        body["credibility"] = credibility
    if worksheet is not None:
        if not isinstance(worksheet, dict):
            raise PARError("worksheet: dict or None")
        body["worksheet"] = worksheet
    if hazard_trace is not None:
        if not isinstance(hazard_trace, list):
            raise PARError("hazard_trace: list or None required")
        for pos, link in enumerate(hazard_trace):
            if not isinstance(link, dict):
                raise PARError(f"hazard_trace[{pos}]: dict required")
            hid = link.get("hazard_id")
            gids = link.get("gate_ids")
            if not hid or not isinstance(hid, str):
                raise PARError(f"hazard_trace[{pos}]: non-empty "
                               f"hazard_id required")
            if not isinstance(gids, list) or any(
                    not isinstance(g, str) for g in gids):
                raise PARError(f"hazard_trace[{pos}]: gate_ids must be "
                               f"a list of strings")
        body["hazard_trace"] = hazard_trace
    return {"par": body, "par_hash": canonical_hash(body)}


def validate_par(envelope: dict) -> dict:
    """Recompute + structural check. Returns ok/reason, never raises."""
    try:
        if not isinstance(envelope, dict):
            return {"ok": False, "reason": "PAR envelope must be a dict"}
        if set(envelope) != {"par", "par_hash"}:
            return {"ok": False,
                    "reason": "PAR envelope must hold exactly "
                             "par + par_hash (no unhashed siblings)"}
        body = envelope.get("par")
        if not isinstance(body, dict):
            return {"ok": False, "reason": "missing par body"}
        if body.get("par_version") != PAR_VERSION:
            return {"ok": False,
                    "reason": f"unsupported par_version "
                             f"{body.get('par_version')!r}"}
        odd = body.get("odd")
        if not isinstance(odd, str) or not odd.strip():
            return {"ok": False,
                    "reason": "missing operational_design_domain "
                             "(INSUFFICIENT evidence)"}
        if canonical_hash(body) != envelope.get("par_hash"):
            restored = {**body, "gates": [
                {**gate, "measurement": float(gate["measurement"])}
                if isinstance(gate.get("measurement"), int)
                and not isinstance(gate["measurement"], bool)
                and abs(gate["measurement"]) <= 2 ** 53
                else gate for gate in body.get("gates", [])
            ]}
            if canonical_hash(restored) != envelope.get("par_hash"):
                return {"ok": False, "reason": "par_hash mismatch (tampered?)"}
        verdicts = [g.get("verdict") for g in body.get("gates", [])]
        if any(v not in _VERDICTS for v in verdicts):
            return {"ok": False, "reason": "gate verdict outside enum"}
        return {"ok": True, "gates": len(verdicts),
                "blocked": sum(1 for v in verdicts if v == "BLOCKED")}
    except Exception as exc:
        return {"ok": False, "reason": f"unverifiable body: {exc}"}


def read_par(envelope: dict) -> dict:
    """Offline reader: verify, then render summary lines. No network.

    Total function: never raises on dict input (validate_par only
    pins version/hash/verdicts, so rendering guards the rest).
    """
    check = validate_par(envelope)
    if not check["ok"]:
        return {"ok": False, "reason": check["reason"], "lines": []}
    try:
        return _render_par(envelope, check)
    except (KeyError, TypeError, IndexError) as exc:
        return {"ok": False, "reason": f"PAR body incomplete: {exc}",
                "lines": []}


def _render_par(envelope: dict, check: dict) -> dict:
    body = envelope["par"]
    lines = [
        f"PAR {body['par_version']} / policy {body['policy']['id']}",
        f"weights {body['policy']['weights'][:19]}...",
        f"odd: {body['odd'][:77]}...",
        f"release delta: {body['release']['delta']}",
        f"gates: {check['gates']} scored, {check['blocked']} BLOCKED",
    ]
    for gate in body["gates"]:
        lines.append(f"  [{gate['verdict']:12s}] {gate['id']} "
                     f"(evidence: {gate.get('evidence')})")
    indep = body["independence"]
    lines.append(f"independence: builder={indep['builder']} "
                 f"funder={indep['funder']} rel={indep['relationship']}")
    lines.append(f"ledger head: {body['ledger_head'][:16]}...")
    lines.append(f"par_hash: {envelope['par_hash'][:16]}...")
    return {"ok": True, "lines": lines}
