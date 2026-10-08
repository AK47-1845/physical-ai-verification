"""Canonical bytes for hashing: the ONE preimage format.

Every hash in the engine (scorecards, PARs, ledger entries, manifests,
release ids, panel cases) routes through canonical_bytes(). No other
serialization may feed a hash except the documented raw cases (test_canon
locks this list): f-string id tags (panel/property/stamp), SimHash token
bytes, mixtrack registry dumps (format-locked), report HTML bytes, and
mirror-app files (untouched by design).

Rules: sorted keys, compact separators, ASCII-safe, NaN/inf rejected
(never hashed), non-string keys rejected, -0.0 normalized to 0.0 (signed
zero would otherwise fork hashes across platforms for equal values).
Floats serialize via repr (shortest round-trip). No I/O, no clock.
"""

import json
import math

from engine import InputError


def _normalize(obj, path="$"):
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise InputError(f"non-finite float at {path}: {obj!r}")
        if obj == 0.0 and math.copysign(1.0, obj) < 0.0:
            return 0.0
        return obj
    if isinstance(obj, dict):
        out = {}
        for key, val in obj.items():
            if not isinstance(key, str):
                raise InputError(f"non-string key at {path}: {key!r}")
            out[key] = _normalize(val, f"{path}.{key}")
        return out
    if isinstance(obj, (list, tuple)):
        return [_normalize(val, f"{path}[{i}]")
                for i, val in enumerate(obj)]
    return obj


def canonical_str(obj) -> str:
    """Canonical JSON text. Rejects non-finite floats, non-str keys."""
    return json.dumps(_normalize(obj), sort_keys=True,
                      separators=(",", ":"), ensure_ascii=True)


def canonical_bytes(obj) -> bytes:
    """Canonical bytes: THE hash preimage. Same input -> same bytes."""
    return canonical_str(obj).encode("utf-8")
