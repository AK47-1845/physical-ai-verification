"""M6 provenance ledger: append-only SHA-256 hash chain (JSONL).

Every run seal, gate profile, dataset card, and review signature appends one
entry. Verification recomputes the chain and names the first bad index.
Timestamps are caller-supplied strings (no wall-clock reads, ever):
determinism law holds end to end. No I/O here, strings only. Stdlib only.
"""

import json

from engine import InputError, canonical_hash, canonical_json, sha256_hex


class LedgerError(InputError):
    """Itemized validation failure. Server formats these, never stack traces."""


GENESIS_PREV = "0" * 64

ANCHOR_SCHEMA = "ledger-anchor/1"

_REQUIRED = ("index", "timestamp", "type", "payload_hash", "prev", "hash")


def _as_list(entries) -> list:
    if isinstance(entries, (list, tuple)):
        return list(entries)
    raise LedgerError(f"entries: list required, got "
                      f"{type(entries).__name__}")


def hash_entry(index: int, timestamp: str, entry_type: str,
               payload_hash: str, prev_hash: str) -> str:
    """Hash over the canonical body. Stable across runs and machines."""
    return sha256_hex(canonical_json({
        "index": index,
        "timestamp": timestamp,
        "type": entry_type,
        "payload_hash": payload_hash,
        "prev": prev_hash,
    }))


def append(entries: list, entry_type: str, payload: dict,
           timestamp: str) -> dict:
    """Append one entry and return it. Mutates `entries` (the chain state).

    Ledger entries are EVENTS, not artifacts: the timestamp is part of
    the hashed event identity (ordering proof), unlike scorecards/PARs
    where timestamps stay outside the hash. Determinism still holds:
    the same event log always rebuilds the same chain."""
    if not entry_type or not isinstance(entry_type, str):
        raise LedgerError(f"entry_type must be a non-empty string: "
                          f"{entry_type!r}")
    if not timestamp or not isinstance(timestamp, str):
        raise LedgerError("timestamp must be a caller-supplied non-empty "
                          f"string: {timestamp!r}")
    if not isinstance(payload, dict):
        raise LedgerError(f"payload must be a dict: {type(payload).__name__}")
    if not isinstance(entries, list):
        raise LedgerError(f"entries: list required, got "
                          f"{type(entries).__name__}")
    try:
        payload_hash = canonical_hash(payload)
    except (TypeError, ValueError) as exc:
        raise LedgerError(f"unhashable payload: {exc}")
    index = len(entries)
    if index == 0:
        prev = GENESIS_PREV
    else:
        tail = entries[-1]
        if not isinstance(tail, dict) or "hash" not in tail:
            raise LedgerError("chain tail corrupt: last entry must be a "
                              "dict with 'hash'")
        prev = tail["hash"]
    entry = {
        "index": index,
        "timestamp": timestamp,
        "type": entry_type,
        "payload_hash": payload_hash,
        "prev": prev,
    }
    entry["hash"] = hash_entry(index, timestamp, entry_type,
                               payload_hash, prev)
    entries.append(entry)
    return entry


def verify(entries: list, anchor=None) -> dict:
    """Recompute the chain. Returns ok or the first bad index + reason.

    Without an anchor this checks internal links only: a chain cut
    short, or fully rewritten as self-consistent, still verifies.
    Pass anchor=anchor(chain) recorded earlier and stored OUT-OF-BAND
    to detect truncation and wholesale forgery.

    Soundness note: every stored hash is recomputed before it is
    trusted (each entry's hash is recomputed in loop order, and each
    prev link is compared against the already-recomputed predecessor),
    so forging one entry breaks its own hash or the next link.
    """
    entries = _as_list(entries)
    for pos, entry in enumerate(entries):
        if not isinstance(entry, dict):
            return {"ok": False, "first_bad": pos,
                    "reason": f"entry {pos}: not a dict"}
        for key in _REQUIRED:
            if key not in entry:
                return {"ok": False, "first_bad": pos,
                        "reason": f"entry {pos}: missing key {key!r}"}
        if entry["index"] != pos:
            return {"ok": False, "first_bad": pos,
                    "reason": f"entry {pos}: index says {entry['index']!r}"}
        want_prev = GENESIS_PREV if pos == 0 else entries[pos - 1]["hash"]
        if entry["prev"] != want_prev:
            return {"ok": False, "first_bad": pos,
                    "reason": f"entry {pos}: prev link broken"}
        try:
            recomputed = hash_entry(entry["index"], entry["timestamp"],
                                    entry["type"], entry["payload_hash"],
                                    entry["prev"])
        except (TypeError, ValueError):
            return {"ok": False, "first_bad": pos,
                    "reason": f"entry {pos}: unhashable entry "
                              f"(non-finite float?)"}
        if entry["hash"] != recomputed:
            return {"ok": False, "first_bad": pos,
                    "reason": f"entry {pos}: hash mismatch"}
    if anchor is not None:
        problem = _check_anchor(entries, anchor)
        if problem is not None:
            reason, first_bad = problem
            return {"ok": False, "first_bad": first_bad, "reason": reason}
    return {"ok": True, "entries": len(entries)}


def anchor(entries: list) -> dict:
    """Capture an out-of-band truncation anchor (schema+length+head).

    Store the returned dict AWAY from the chain (separate repo,
    email, printout): verify(chain, anchor=...) then detects tail
    truncation and wholesale forgery, which internal links alone
    cannot see. The holder may add a human "note"; it is never
    hashed. Empty chains anchor to GENESIS_PREV (the prev the
    first entry must carry).
    """
    entries = _as_list(entries)
    for pos, entry in enumerate(entries):
        if not isinstance(entry, dict) or "hash" not in entry:
            raise LedgerError(f"entry {pos}: dict with 'hash' required "
                              f"(anchor a verifiable chain)")
    return {"schema": ANCHOR_SCHEMA, "length": len(entries),
            "head_hash": entries[-1]["hash"] if entries else GENESIS_PREV}


def _check_anchor(entries: list, pack) -> tuple | None:
    """Validate pack shape and compare. None when satisfied."""
    if not isinstance(pack, dict):
        return ("anchor: dict required", None)
    if pack.get("schema") != ANCHOR_SCHEMA:
        return (f"anchor: schema must be {ANCHOR_SCHEMA!r}", None)
    length = pack.get("length")
    if (isinstance(length, bool) or not isinstance(length, int)
            or length < 0):
        return ("anchor: length must be a non-negative int", None)
    head = pack.get("head_hash")
    if not isinstance(head, str) or not head:
        return ("anchor: head_hash must be a non-empty string", None)
    if len(entries) < length:
        return (f"anchor: chain length {len(entries)} < anchored "
                f"{length} (truncated?)", len(entries))
    if length == 0:
        return None
    if entries[length - 1]["hash"] != head:
        return (f"anchor: head mismatch at index {length - 1} "
                f"(forged or rewound?)", length - 1)
    return None


def head(entries: list):
    """Latest chain hash (the external truncation anchor).

    None on an empty chain. Record heads outside the chain (PAR
    ledger_head, anchor file) and compare on every verify.
    """
    entries = _as_list(entries)
    if not entries:
        return None
    tail = entries[-1]
    if not isinstance(tail, dict) or "hash" not in tail:
        raise LedgerError("chain tail corrupt: last entry must be a "
                          "dict with 'hash'")
    return tail["hash"]


def dumps(entries: list) -> str:
    """Serialize the chain to JSONL (one canonical object per line)."""
    entries = _as_list(entries)
    lines = []
    for pos, entry in enumerate(entries):
        try:
            lines.append(canonical_json(entry))
        except (TypeError, ValueError) as exc:
            raise LedgerError(f"entry {pos}: not canonicalizable: {exc}")
    return "".join(line + "\n" for line in lines)


def loads(text: str) -> list:
    """Parse JSONL back to a chain. Shape-checked, hash-checked by verify()."""
    if not isinstance(text, str):
        raise LedgerError("loads() needs a string")
    entries = []
    for num, line in enumerate(text.split("\n")):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            raise LedgerError(f"line {num}: not valid JSON")
        if not isinstance(entry, dict):
            raise LedgerError(f"line {num}: not an object")
        entries.append(entry)
    return entries
