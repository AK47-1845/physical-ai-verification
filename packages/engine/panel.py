"""FR-37 held-out panel: commit-reveal so benchmarks cannot leak.

Per release: commit(seed hash + case count) appends to the ledger BEFORE
scoring; after the verdict, reveal publishes seed + cases for
re-verification. Clients never see seeds up front. If panel content ever
appears in training corpora, that panel version is disclosed + rotated.

Seeds are str|int, normalized with str(). Commitments bind seed AND
count: revealing with a different count fails closed.
"""

import random

from engine import InputError, canonical_hash, sha256_hex


class PanelError(InputError):
    """Itemized validation failure. Server formats these, never traces."""


def commit(seed, case_count: int) -> dict:
    """Bind seed + count. Append the result to the ledger pre-scoring."""
    if (isinstance(seed, bool) or not isinstance(seed, (str, int))
            or seed == ""):
        raise PanelError("seed: non-empty str|int required (bools are "
                         "not seeds)")
    if (isinstance(case_count, bool)
            or not isinstance(case_count, int) or case_count < 1):
        raise PanelError(f"case_count: positive int, got {case_count!r}")
    commitment = sha256_hex(f"panel-commit:{seed}:{case_count}")
    return {"commitment": commitment, "case_count": case_count,
            "note": "ledger this BEFORE scoring; reveal seed after verdict"}


def reveal(commitment: str, seed, case_count: int) -> dict:
    """Verify a reveal against the commitment. Never raises on mismatch."""
    try:
        if not isinstance(commitment, str):
            return {"verified": False, "reason": "commitment must be a str"}
        expect = commit(seed, case_count)["commitment"]
    except PanelError as exc:
        return {"verified": False, "reason": str(exc)}
    if expect != commitment:
        return {"verified": False,
                "reason": "commitment mismatch (wrong seed or count?)"}
    return {"verified": True, "case_count": case_count}


def build_panel(seed, count: int, make_case) -> dict:
    """Deterministically build `count` cases. make_case(rng, i) -> JSONable.

    No count cap: no service route calls this (panels are built
    offline); cap it the day a client-controlled path arrives.
    """
    if (isinstance(seed, bool) or not isinstance(seed, (str, int))
            or seed == ""):
        raise PanelError("seed: non-empty str|int required (bools are "
                         "not seeds)")
    if (isinstance(count, bool)
            or not isinstance(count, int) or count < 1):
        raise PanelError(f"count: positive int, got {count!r}")
    if not callable(make_case):
        raise PanelError("make_case: callable(rng, i) required")
    rng = random.Random(str(seed))
    cases = []
    for i in range(count):
        try:
            case = make_case(rng, i)
        except Exception as exc:
            raise PanelError(f"make_case raised at {i}: {exc!r}")
        try:
            canonical_hash(case)
        except (TypeError, ValueError):
            raise PanelError(f"case {i}: must be JSON-canonicalizable")
        cases.append(case)
    return {"cases": cases, "count": count,
            "seed_hash": sha256_hex(f"panel-seed:{seed}")}
