"""FR-34 release-over-release compare: parent/child deltas + mod flag.

CALLER CONTRACT (unenforced, by design): both gate lists come from the
same profile + same seed on the two weight sets. Given that, per-gate
deltas with conservative CIs (when both sides carry bootstrap CIs) and
a SUBSTANTIAL_MODIFICATION_CANDIDATE flag on any worsening or tolerance
breach. Evidence vanishing (scored -> INSUFFICIENT) always worsens:
a release that loses its proof is a regression, never an improvement.
Identical weight hashes short-circuit to a zero-delta proof, but gates
are still shape-validated first (no proof on garbage inputs).
"""

import math

from engine import InputError


class ReleaseError(InputError):
    """Itemized validation failure. Server formats these, never traces."""


FLAG = "SUBSTANTIAL_MODIFICATION_CANDIDATE"

_RANK = {"PASS": 0, "REVIEW": 1, "INSUFFICIENT": 1, "BLOCKED": 2}


def _check_gates(gates, name: str) -> dict:
    if not isinstance(gates, (list, tuple)) or not gates:
        raise ReleaseError(f"{name}: non-empty gate list required")
    out = {}
    for gate in gates:
        if not isinstance(gate, dict):
            raise ReleaseError(f"{name}: gate dicts required")
        gid = gate.get("gate")
        if not gid or not isinstance(gid, str) or gid in out:
            raise ReleaseError(f"{name}: unique string gate ids required")
        m = gate.get("measurement")
        if (isinstance(m, bool) or not isinstance(m, (int, float))
                or not math.isfinite(m)):
            raise ReleaseError(f"{name}[{gid}]: finite measurement required")
        status = gate.get("status")
        if not isinstance(status, str) or status not in _RANK:
            raise ReleaseError(f"{name}[{gid}]: bad status "
                               f"{status!r}")
        out[gid] = gate
    return out


def _delta_ci(parent: dict, child: dict):
    pci, cci = parent.get("ci"), child.get("ci")
    try:
        plo, phi = pci["lo"], pci["hi"]
        clo, chi = cci["lo"], cci["hi"]
    except (TypeError, KeyError):
        return None
    for v in (plo, phi, clo, chi):
        if (isinstance(v, bool) or not isinstance(v, (int, float))
                or not math.isfinite(v)):
            return None
    return [clo - phi, chi - plo]


def compare(parent_gates, child_gates, *, parent_weights_hash: str,
            child_weights_hash: str, tolerances: dict | None = None) -> dict:
    """Compare two scorecards. Flags candidates, decides nothing legal."""
    for label, value in (("parent_weights_hash", parent_weights_hash),
                         ("child_weights_hash", child_weights_hash)):
        if not value or not isinstance(value, str):
            raise ReleaseError(f"{label}: non-empty string required")
    parent = _check_gates(parent_gates, "parent_gates")
    child = _check_gates(child_gates, "child_gates")
    if parent_weights_hash == child_weights_hash:
        return {"identical": True, "hash_proof": parent_weights_hash,
                "deltas": [], "flag": None,
                "reasons": ["identical weight hashes: zero delta by proof"]}
    if set(parent) != set(child):
        raise ReleaseError("parent/child gate sets differ: "
                           f"{sorted(set(parent) ^ set(child))}")
    if tolerances is None:
        tolerances = {}
    if not isinstance(tolerances, dict):
        raise ReleaseError("tolerances: {gate_id: number} dict or None")
    deltas, reasons, flag = [], [], None
    for gid in sorted(parent):
        p, c = parent[gid], child[gid]
        delta = c["measurement"] - p["measurement"]
        shift = (p["status"], c["status"])
        vanished = (c["status"] == "INSUFFICIENT"
                    and p["status"] != "INSUFFICIENT")
        worsened = _RANK[c["status"]] > _RANK[p["status"]] or vanished
        entry = {"gate": gid, "parent": p["measurement"],
                 "child": c["measurement"], "delta": delta,
                 "delta_ci": _delta_ci(p, c), "status_shift": list(shift),
                 "worsened": worsened}
        deltas.append(entry)
        if worsened:
            flag = FLAG
            note = " (evidence vanished)" if vanished else ""
            reasons.append(f"{gid}: {p['status']} -> {c['status']}{note}")
        tol = tolerances.get(gid)
        if tol is not None:
            if (isinstance(tol, bool)
                    or not isinstance(tol, (int, float))
                    or not math.isfinite(tol) or tol < 0):
                raise ReleaseError(f"tolerances[{gid}]: finite number >= 0")
            if abs(delta) > tol:
                flag = FLAG
                reasons.append(f"{gid}: |delta| {abs(delta)} exceeds {tol}")
    return {"identical": False, "parent_hash": parent_weights_hash,
            "child_hash": child_weights_hash, "deltas": deltas,
            "flag": flag, "reasons": reasons}
