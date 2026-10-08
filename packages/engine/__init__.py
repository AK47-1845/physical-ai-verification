"""Physical AI Verification engine core v0.1 (M1 slice 1): canonical hashing.

Determinism law: same inputs + profile + seed = byte-identical
canonical bytes on the same platform+Python (cross-platform: run
golden_check on the second machine).
Timestamps and analyst notes live OUTSIDE the hashed body, always.
Stdlib only. No I/O. No network. No wall-clock reads.
"""

import hashlib


class InputError(ValueError):
    """Deliberate validation failure: the CALLER's input was wrong.

    Subclasses ValueError so old except-clauses keep working. The
    service maps InputError (and StoreError) to 422; every other
    exception is a 500 with a logged traceback. Defined before the
    canon import so engine.canon can raise it during package init.
    """


from engine.canon import canonical_bytes, canonical_str  # noqa: E402

ENGINE_VERSION = "0.1.0"


def canonical_json(obj) -> str:
    """Serialize to canonical JSON: sorted keys, compact separators, utf-8 safe.

    Raises ValueError on non-finite floats (NaN/inf are rejected, never hashed).
    Single implementation lives in engine.canon (this is a thin wrapper).
    """
    return canonical_str(obj)


def sha256_hex(data) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical_hash(obj) -> str:
    """sha256 over canonical bytes. Stable across runs and machines."""
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def pin_artifact(payload: dict, *, profile_version: str,
                 code_version: str = ENGINE_VERSION) -> dict:
    """Return artifact envelope with hashes pinned (timestamps stay outside)."""
    body_hash = canonical_hash(payload)
    envelope = {
        "payload": payload,
        "inputs_hash": body_hash,
        "profile_version": profile_version,
        "code_version": code_version,
    }
    envelope["envelope_hash"] = sha256_hex(canonical_json({
        "payload": payload,
        "inputs_hash": body_hash,
        "profile_version": profile_version,
        "code_version": code_version,
    }))
    return envelope
