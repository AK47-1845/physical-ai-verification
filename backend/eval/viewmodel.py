"""Release view-model: one run rendered for humans (and thin UI).

build_release_view() takes stored docs (run, optional compare run,
optional dossier) and returns the render-ready view-model: verdict,
plain-language guidance, per-gate reasons, smallest improving
moves, chips, deltas, offline-verify command, and scope (ODD +
model hash). Pure function, no store access; the route loads docs.
All strings come from plainlang templates. Display only: the
view-model is never hashed.
"""

from engine import InputError

from backend.eval.plainlang import BAND_RANK, change_text, headline, reason_text, scope_line, verdict_plain
from backend.eval.score_trace import PROFILES


class ViewError(InputError):
    """Stored run/dossier failed shape checks (corrupt store entry)."""


def _need_run(run_doc, run_id: str) -> dict:
    if not isinstance(run_doc, dict):
        raise ViewError(f"run {run_id}: stored doc must be a dict")
    card = run_doc.get("scorecard")
    if not isinstance(card, dict) or not isinstance(
            card.get("payload"), dict):
        raise ViewError(f"run {run_id}: stored scorecard incomplete")
    payload = card["payload"]
    if payload.get("verdict") not in ("TRUSTED", "REVIEW", "BLOCKED"):
        raise ViewError(f"run {run_id}: bad verdict "
                        f"{payload.get('verdict')!r}")
    if not isinstance(payload.get("gates"), list):
        raise ViewError(f"run {run_id}: gates list required")
    return payload


def _thresholds(profile_version):
    gates = PROFILES.get(profile_version, {}).get("gates", [])
    return {g["id"]: (g.get("green"), g.get("amber"),
                      bool(g.get("higher", False))) for g in gates
            if isinstance(g, dict) and g.get("id")}


def _worst_of(gates, statuses):
    ranked = sorted(
        ((BAND_RANK.get(g.get("band"), 9), g.get("gate"), g)
         for g in gates if g.get("status") in statuses),
        key=lambda t: (-t[0], t[1] or ""))
    return ranked[0][2] if ranked else None


def _reasons(gates, edges):
    rows = []
    for gate in gates:
        gid = gate.get("gate", "?")
        band = gate.get("band", "?")
        green, amber, higher = edges.get(gid, (None, None, False))
        rows.append({"gate": gid, "band": band,
                     "plain_text": reason_text(
                         gid, band, gate.get("measurement"),
                         green=green, amber=amber, higher=higher,
                         note=gate.get("note")),
                     "evidence_ref": gate.get("evidence")})
    return rows


def _changes(gates, edges):
    moves = []
    for gate in gates:
        if gate.get("band") not in ("red", "amber"):
            continue
        gid = gate.get("gate", "?")
        green, amber, higher = edges.get(gid, (None, None, False))
        if green is None or amber is None:
            moves.append({"gate": gid,
                          "move": f"thresholds unrecorded for {gid}; "
                                  f"re-score with a pinned profile."})
        else:
            moves.append({"gate": gid,
                          "move": change_text(
                              gid, gate["measurement"], green=green,
                              amber=amber, higher=higher,
                              band=gate["band"])})
    return moves


def _chips(profile_version, gates, dossier):
    chips = []
    if isinstance(profile_version, str) and \
            profile_version.startswith("draft"):
        chips.append({"label": "DRAFT", "kind": "caution"})
    if any(g.get("status") == "INSUFFICIENT" for g in gates):
        chips.append({"label": "INSUFFICIENT", "kind": "bad"})
    par = (dossier or {}).get("par") or {}
    sig = par.get("signature")
    signed = isinstance(sig, dict) and sig.get("key_id") \
        and sig.get("value")
    if not signed:
        # No dossier/PAR at all, or a PAR without a signature:
        # either way no signed artifact covers this release.
        chips.append({"label": "UNSIGNED", "kind": "caution"})
    return chips


def _deltas(gates, other):
    base = {g.get("gate"): g for g in other}
    rows = []
    for gate in gates:
        gid = gate.get("gate")
        prev = base.get(gid)
        if prev is None:
            rows.append({"gate": gid, "band_from": None,
                         "band_to": gate.get("band"),
                         "delta": None, "regression": False})
            continue
        now, was = gate.get("band"), prev.get("band")
        regression = (now in BAND_RANK and was in BAND_RANK
                      and BAND_RANK[now] > BAND_RANK[was])
        both = gate.get("measurement"), prev.get("measurement")
        delta = None
        if all(isinstance(v, (int, float)) and not isinstance(v, bool)
               for v in both):
            delta = both[0] - both[1]
        rows.append({"gate": gid, "band_from": prev.get("band"),
                     "band_to": gate.get("band"), "delta": delta,
                     "regression": bool(regression)})
    return rows


def build_release_view(run_doc, run_id, *, compare=None,
                       compare_id=None, dossier=None) -> dict:
    """Assemble the release view-model for one run."""
    payload = _need_run(run_doc, run_id)
    gates = payload["gates"]
    label = payload["verdict"]
    profile_version = run_doc["scorecard"].get("profile_version")
    edges = _thresholds(profile_version)
    blocked = sorted(g.get("gate", "?") for g in gates
                     if g.get("status") == "BLOCKED")
    review = sorted(g.get("gate", "?") for g in gates
                    if g.get("status") == "REVIEW")
    insufficient = sorted(g.get("gate", "?") for g in gates
                          if g.get("status") == "INSUFFICIENT")
    worst_gate = (_worst_of(gates, ("BLOCKED",)) or
                  _worst_of(gates, ("REVIEW",)) or
                  _worst_of(gates, ("INSUFFICIENT",)))
    worst = {"blocked": len(blocked), "review": len(review),
             "insufficient": len(insufficient),
             "gate": worst_gate.get("gate", "?") if worst_gate else "?",
             "m": worst_gate.get("measurement") if worst_gate else None,
             "amber": edges.get(worst_gate.get("gate"), (None, None,
                               False))[1] if worst_gate else None}
    par = (dossier or {}).get("par", {}).get("par", {})
    model_hash = (par.get("policy") or {}).get("weights")
    odd = par.get("odd")
    par_hash = (dossier or {}).get("par", {}).get("par_hash")
    deltas = []
    if compare is not None:
        other = _need_run(compare, compare_id or "?")
        deltas = _deltas(gates, other["gates"])
    return {"run_id": run_id, "verdict": label,
            "verdict_plain": verdict_plain(
                label, blocked=blocked, review=review,
                insufficient=insufficient),
            "headline": headline(label, len(gates), worst=worst),
            "reasons": _reasons(gates, edges),
            "what_would_change": _changes(gates, edges),
            "chips": _chips(profile_version, gates, dossier),
            "deltas": deltas, "compare_id": compare_id,
            "offline_verify": {
                "command": "python backend/par_cli.py <par.json>",
                "hash": par_hash},
            "scope": scope_line(model_hash, odd),
            "odd": odd, "model_hash": model_hash,
            "profile_version": profile_version}
