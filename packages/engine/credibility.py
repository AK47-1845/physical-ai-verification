"""FR-32 gate credibility cards: checkable verifier claims.

No gate lifts DRAFT without a current card. Fields: gate id + version,
corpus hash, n, FP/FN counts, calibration bins, rollout types, transfer
error, search-hit count, date (caller-supplied), analyst. can_lift_draft
enforces minimum floors; CI calls it on DRAFT->v1.0 transitions.
Conformal thresholds ride alongside with exchangeability statements;
any policy optimised against our gates invalidates them (flag here).
"""

import math

from engine import InputError, canonical_hash


class CredibilityError(InputError):
    """Itemized validation failure. Server formats these, never traces."""


def _need_sha(value, where: str) -> str:
    import re
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise CredibilityError(f"{where}: sha256 hex required")
    return value


def _need_count(value, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CredibilityError(f"{where}: non-negative int required")
    return value


def _need_number(value, where: str):
    if (isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)):
        raise CredibilityError(f"{where}: finite number required")
    return value


def build_card(*, gate_id: str, gate_version: str, corpus_hash: str,
               n: int, false_positives: int, false_negatives: int,
               label_counts: dict, calibration_bins: list,
               rollout_types: dict, transfer_error,
               search_hits: int, date: str, analyst: str,
               exchangeability: str | None = None,
               optimised_against: bool = False) -> dict:
    """Build + hash a credibility card. Strict validation throughout."""
    if not gate_id or not isinstance(gate_id, str):
        raise CredibilityError("gate_id: non-empty string required")
    if not gate_version or not isinstance(gate_version, str):
        raise CredibilityError("gate_version: non-empty string required")
    _need_sha(corpus_hash, "corpus_hash")
    _need_count(n, "n")
    _need_count(false_positives, "false_positives")
    _need_count(false_negatives, "false_negatives")
    _need_count(search_hits, "search_hits")
    if not isinstance(label_counts, dict) or not label_counts:
        raise CredibilityError("label_counts: non-empty {label: count} dict")
    for label, count in label_counts.items():
        if not label or not isinstance(label, str):
            raise CredibilityError(f"label_counts: string labels required, "
                                   f"got {label!r}")
        _need_count(count, f"label_counts[{label!r}]")
    if not isinstance(calibration_bins, list):
        raise CredibilityError("calibration_bins: list required")
    for i, entry in enumerate(calibration_bins):
        if not isinstance(entry, dict):
            raise CredibilityError(f"calibration_bins[{i}]: dict required")
        for key in ("lo", "hi", "predicted", "observed"):
            _need_number(entry.get(key),
                         f"calibration_bins[{i}].{key}")
        _need_count(entry.get("n"), f"calibration_bins[{i}].n")
        if not entry["lo"] <= entry["hi"]:
            raise CredibilityError(f"calibration_bins[{i}]: need lo <= hi, "
                                   f"got {entry['lo']!r}, {entry['hi']!r}")
    if not isinstance(rollout_types, dict) or not rollout_types:
        raise CredibilityError("rollout_types: non-empty {type: count} dict")
    for kind, count in rollout_types.items():
        if not kind or not isinstance(kind, str):
            raise CredibilityError(f"rollout_types: string kinds required, "
                                   f"got {kind!r}")
        _need_count(count, f"rollout_types[{kind!r}]")
    if transfer_error is not None:
        _need_number(transfer_error, "transfer_error")
    if not date or not isinstance(date, str):
        raise CredibilityError("date: caller-supplied non-empty string")
    if not analyst or not isinstance(analyst, str):
        raise CredibilityError("analyst: non-empty string required")
    if exchangeability is not None and (
            not isinstance(exchangeability, str) or not exchangeability):
        raise CredibilityError("exchangeability: non-empty string or None "
                               "(conformal thresholds need an explicit "
                               "statement)")
    card = {"gate_id": gate_id, "gate_version": gate_version,
            "corpus_hash": corpus_hash, "n": n,
            "false_positives": false_positives,
            "false_negatives": false_negatives, "label_counts": label_counts,
            "calibration_bins": calibration_bins,
            "rollout_types": rollout_types, "transfer_error": transfer_error,
            "search_hits": search_hits, "date": date, "analyst": analyst,
            "exchangeability": exchangeability,
            "optimised_against": bool(optimised_against)}
    return {"card": card, "card_hash": canonical_hash(card)}


def can_lift_draft(card_envelope: dict, *, min_n: int = 30,
                   max_fp_rate: float = 0.05,
                   require_bins: bool = True) -> dict:
    """DRAFT->v1.0 gate: floors + freshness + optimisation tripwire.

    Bad CARDS yield fail-closed verdicts (returned, never raised).
    Bad PARAMS raise CredibilityError (programmer error, not data).
    """
    if isinstance(min_n, bool) or not isinstance(min_n, int) or min_n < 0:
        raise CredibilityError(f"min_n: non-negative int required: "
                               f"{min_n!r}")
    if (isinstance(max_fp_rate, bool)
            or not isinstance(max_fp_rate, (int, float))
            or not 0.0 <= max_fp_rate <= 1.0):
        raise CredibilityError(f"max_fp_rate: number in [0, 1] required: "
                               f"{max_fp_rate!r}")
    if not isinstance(require_bins, bool):
        raise CredibilityError(f"require_bins: bool required: "
                               f"{require_bins!r}")
    try:
        card = card_envelope["card"]
    except (TypeError, KeyError):
        return {"lift": False, "reasons": ["missing card body"]}
    try:
        sealed = canonical_hash(card) == card_envelope.get("card_hash")
    except (TypeError, ValueError):
        return {"lift": False,
                "reasons": ["card unhashable (non-finite float? bad shape?)"]}
    if not sealed:
        return {"lift": False, "reasons": ["card_hash mismatch (tampered?)"]}
    if not isinstance(card, dict):
        return {"lift": False, "reasons": ["card body must be a dict"]}
    try:
        reasons = []
        if card.get("n", 0) < min_n:
            reasons.append(f"n={card.get('n')} below minimum {min_n}")
        labels = card.get("label_counts", {})
        if not isinstance(labels, dict):
            raise TypeError("label_counts must be a dict")
        total = sum(v for v in labels.values() if isinstance(v, int))
        if total > 0 and card.get("false_positives", 0) / total > max_fp_rate:
            reasons.append("false-positive rate exceeds "
                           f"{max_fp_rate} on {total} labels")
        if require_bins and not card.get("calibration_bins"):
            reasons.append("calibration bins required")
        if not card.get("rollout_types"):
            reasons.append("rollout types required")
        if card.get("optimised_against"):
            reasons.append("policy optimised against gates: thresholds void")
        if card.get("search_hits", 0) > 0:
            reasons.append(f"{card['search_hits']} unresolved search hits: "
                           f"fix or convert to sev-1 tests first")
    except (TypeError, ValueError) as exc:
        return {"lift": False,
                "reasons": [f"card shape invalid (fail-closed): {exc}"]}
    return {"lift": not reasons, "reasons": reasons}
