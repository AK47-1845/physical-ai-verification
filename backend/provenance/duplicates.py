"""Duplicate + near-duplicate detection (GenProof-style ICS input).

Exact duplicates: tuple rate. Near duplicates: SimHash over quantized
tokens with Hamming clustering (union-find). Pairwise Hamming is O(n^2):
inputs over MAX_ROWS are refused with guidance to sample first (honest
scaling boundary, not a silent slowdown). Powers the "AI repetition"
leg of collapse assessment alongside variance/tail sentinels.
"""

import hashlib
import math

from engine import InputError


class DupError(InputError):
    """Itemized validation failure. Server formats these, never traces."""


MAX_ROWS = 2000


def _tokenize(row, resolution: float) -> list:
    if isinstance(row, dict):
        try:
            items = sorted(row.items())
        except TypeError:
            raise DupError("dict rows need uniformly-typed keys")
        return [f"{k}={v}" for k, v in items]
    if isinstance(row, (list, tuple)):
        tokens = []
        for dim, value in enumerate(row):
            if not isinstance(value, (int, float)):
                raise DupError("numeric vectors required for resolution "
                               "quantization")
            tokens.append(f"{dim}:{round(float(value) / resolution)}")
        return tokens
    raise DupError(f"rows must be dicts or vectors, got {type(row).__name__}")


def _simhash64(tokens: list) -> int:
    bits = [0] * 64
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()[:8]
        word = int.from_bytes(digest, "big")
        for bit in range(64):
            bits[bit] += 1 if (word >> bit) & 1 else -1
    out = 0
    for bit, total in enumerate(bits):
        if total > 0:
            out |= 1 << bit
    return out


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def exact_dup_rate(rows: list) -> dict:
    """1 - unique/total over canonical row keys."""
    try:
        rows = list(rows)
    except TypeError:
        raise DupError(f"rows: sequence required, got {type(rows).__name__}")
    if not rows:
        raise DupError("need at least one row")
    keys = []
    for row in rows:
        if isinstance(row, dict):
            try:
                keys.append(tuple(sorted(row.items())))
            except TypeError:
                raise DupError(
                    "dict rows need uniformly-typed keys")
        elif isinstance(row, (list, tuple)):
            keys.append(tuple(row))
        else:
            raise DupError("rows must be dicts or vectors")
    try:
        unique = len(set(keys))
    except TypeError:
        raise DupError("rows must be flat (nested values are unhashable)")
    return {"rate": 1.0 - unique / len(rows), "unique": unique,
            "total": len(rows)}


def near_dup_rate(rows: list, *, resolution: float = 0.01,
                  hamming: int = 3) -> dict:
    """1 - clusters/total with Hamming<=threshold single-link clustering."""
    try:
        rows = list(rows)
    except TypeError:
        raise DupError(f"rows: sequence required, got {type(rows).__name__}")
    if not rows:
        raise DupError("need at least one row")
    if len(rows) > MAX_ROWS:
        raise DupError(f"n={len(rows)} exceeds MAX_ROWS={MAX_ROWS}: sample "
                       f"first (pairwise Hamming is O(n^2))")
    if (isinstance(resolution, bool)
            or not isinstance(resolution, (int, float))
            or not math.isfinite(resolution) or not resolution > 0):
        raise DupError("resolution: positive finite number required")
    if (isinstance(hamming, bool)
            or not isinstance(hamming, int) or hamming < 0):
        raise DupError("hamming: non-negative int required")
    prints = [_simhash64(_tokenize(row, float(resolution))) for row in rows]
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        parent[find(i)] = find(j)

    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            if _hamming(prints[i], prints[j]) <= hamming:
                union(i, j)
    clusters = len({find(i) for i in range(len(rows))})
    return {"rate": 1.0 - clusters / len(rows), "clusters": clusters,
            "total": len(rows), "resolution": resolution,
            "hamming": hamming}
