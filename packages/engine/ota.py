"""M7 OTA vault: weight lineage with regression verdicts.

Every release pins policy id, weight hash, parent hash (None = genesis),
regression scorecard summary, and seed/profile. register() enforces the
lineage chain (unknown parents rejected: no orphan releases) and derives
deterministic release ids from content. children_of() walks the rollout
tree. Pure dict state; the store layer persists.
"""

from engine import InputError, canonical_hash
from engine.release import FLAG as SUBSTANTIAL_FLAG


class OTAError(InputError):
    """Itemized validation failure. Server formats these, never traces."""


def _need_weight(value, where: str) -> str:
    import re
    if (not isinstance(value, str) or not value.startswith("sha256:")
            or re.fullmatch(r"[0-9a-f]{64}", value[7:]) is None):
        raise OTAError(f"{where}: 'sha256:<64hex>' required")
    return value


def new_vault() -> dict:
    """Empty vault: {releases: {release_id: record}}."""
    return {"releases": {}}


def _releases(vault: dict) -> dict:
    try:
        releases = vault["releases"]
    except (TypeError, KeyError):
        raise OTAError("vault: {'releases': {...}} dict required")
    if not isinstance(releases, dict):
        raise OTAError("vault['releases']: dict required")
    return releases


_RECORD_KEYS = ("release_id", "weights_hash", "parent_hash")


def _records(vault: dict) -> list:
    """Validated release records. Corrupt stores raise, never KeyError."""
    out = []
    for rid, record in _releases(vault).items():
        if not isinstance(record, dict):
            raise OTAError(f"vault release {rid!r}: dict required "
                           f"(corrupt store?)")
        for key in _RECORD_KEYS:
            if key not in record:
                raise OTAError(f"vault release {rid!r}: missing {key!r} "
                               f"(corrupt store?)")
        if not isinstance(record["release_id"], str):
            raise OTAError(f"vault release {rid!r}: release_id must be "
                           f"str (corrupt store?)")
        if rid != record["release_id"]:
            raise OTAError(f"vault key {rid!r} != record release_id "
                           f"{record['release_id']!r} (corrupt store?)")
        if not isinstance(record["weights_hash"], str):
            raise OTAError(f"vault release {rid!r}: weights_hash must be "
                           f"str (corrupt store?)")
        parent = record["parent_hash"]
        if parent is not None and not isinstance(parent, str):
            raise OTAError(f"vault release {rid!r}: parent_hash must be "
                           f"str or None (corrupt store?)")
        out.append(record)
    return out


def register_release(vault: dict, *, policy_id: str, weights_hash: str,
                     parent_hash: str | None, regression_verdict: str,
                     regression_flag: str | None, seed: int,
                     profile_version: str) -> dict:
    """Register one release. Lineage enforced, id derived from content.

    Same weights re-registered under new seed/profile is allowed (new
    release id); lineage walks resolve a shared weights_hash to the
    most recently registered release.
    """
    _releases(vault)
    if not policy_id or not isinstance(policy_id, str):
        raise OTAError("policy_id: non-empty string required")
    _need_weight(weights_hash, "weights_hash")
    if parent_hash is not None:
        _need_weight(parent_hash, "parent_hash")
        known = {r["weights_hash"] for r in _records(vault)}
        if parent_hash not in known:
            raise OTAError("parent_hash unknown to vault: no orphan "
                           "releases (register parent first)")
    if regression_verdict not in ("TRUSTED", "REVIEW", "BLOCKED"):
        raise OTAError(f"regression_verdict: bad label {regression_verdict!r}")
    if regression_flag is not None and regression_flag != SUBSTANTIAL_FLAG:
        raise OTAError(f"regression_flag: None or {SUBSTANTIAL_FLAG!r}, "
                       f"got {regression_flag!r}")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise OTAError("seed: int required (bools are not seeds)")
    if not profile_version or not isinstance(profile_version, str):
        raise OTAError("profile_version: non-empty string required")
    release_id = "rel_" + canonical_hash({
        "policy": policy_id, "weights": weights_hash, "parent": parent_hash,
        "seed": seed, "profile": profile_version})[:12]
    if release_id in vault["releases"]:
        raise OTAError(f"release already registered: {release_id} "
                       f"(identical content replays the same id)")
    record = {"release_id": release_id, "policy_id": policy_id,
              "weights_hash": weights_hash, "parent_hash": parent_hash,
              "regression_verdict": regression_verdict,
              "regression_flag": regression_flag, "seed": seed,
              "profile_version": profile_version,
              "deployable": regression_verdict == "TRUSTED"
              and regression_flag is None}
    vault["releases"][release_id] = record
    return record


def children_of(vault: dict, weights_hash: str) -> list:
    """Direct children of a weight hash, sorted by release id."""
    _need_weight(weights_hash, "weights_hash")
    return sorted(r["release_id"] for r in _records(vault)
                  if r["parent_hash"] == weights_hash)


def par_currency(vault: dict, par_weights_hash: str) -> dict:
    """Is a PAR's weights still current? CURRENT/SUPERSEDED/UNKNOWN.

    A PAR is VALID only for its model weights: when the vault holds
    a transitively-newer release carrying the substantial-modification
    FLAG, the PAR is SUPERSEDED (re-verify on the new weights). The
    flag stays a flag for humans, never a legal conclusion.
    """
    _need_weight(par_weights_hash, "par_weights_hash")
    records = _records(vault)
    known = {r["weights_hash"] for r in records}
    if par_weights_hash not in known:
        return {"status": "UNKNOWN_WEIGHTS",
                "detail": "PAR weights unknown to this vault",
                "by": []}
    children = {}
    for record in records:
        children.setdefault(record["parent_hash"], []).append(record)
    flagged, seen, stack = [], set(), [par_weights_hash]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        for child in children.get(current, []):
            if child["regression_flag"] == SUBSTANTIAL_FLAG:
                flagged.append(child["release_id"])
            stack.append(child["weights_hash"])
    if flagged:
        return {"status": "SUPERSEDED",
                "detail": "newer release(s) carry the "
                         "substantial-modification flag",
                "by": sorted(flagged)}
    return {"status": "CURRENT",
            "detail": "no substantial-modification descendant",
            "by": []}


def rollout_line(vault: dict, weights_hash: str) -> list:
    """Genesis-to-target chain of release ids (for NB walkthroughs)."""
    _need_weight(weights_hash, "weights_hash")
    by_weight = {r["weights_hash"]: r for r in _records(vault)}
    if weights_hash not in by_weight:
        raise OTAError("weights_hash unknown to vault")
    line, seen = [], set()
    current = weights_hash
    while current is not None:
        if current in seen:
            raise OTAError("vault lineage cycle (corrupt store?)")
        seen.add(current)
        record = by_weight[current]
        line.append(record["release_id"])
        current = record["parent_hash"]
    line.reverse()
    return line
