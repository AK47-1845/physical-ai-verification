"""M5 cross-embodiment transfer scoring (the CTO answer, in math).

Transfer compares traces in NORMALIZED task space: each embodiment card
declares its position scale (meters per unit); traces are scale-divided,
then centroid-subtracted (translation-invariant "centered" form), then
scored with discrete Frechet. Joint-space cross-embodiment comparison is
REFUSED loudly: it is the bad comparison everyone else silently runs.

Cards: {"embodiment_id": str, "space": "task"|"joint",
        "position_scale": float > 0, "frame_id": str}.
Different horizons are fine (Frechet handles n != m); different control
RATES need resampling (M5b, documented limitation, not silent).
"""

import math

from engine import InputError
from engine.frechet import discrete_frechet


class XEmbodimentError(InputError):
    """Refusals + validation failures. Service formats these as 422."""


def check_card(card: dict, name: str) -> dict:
    """Validate an embodiment card. Returns normalized copy."""
    if not isinstance(card, dict):
        raise XEmbodimentError(f"{name}: embodiment card dict required")
    eid = card.get("embodiment_id")
    if not eid or not isinstance(eid, str):
        raise XEmbodimentError(f"{name}.embodiment_id: non-empty string")
    space = card.get("space")
    if space not in ("task", "joint"):
        raise XEmbodimentError(f"{name}.space: 'task'|'joint', got {space!r}")
    scale = card.get("position_scale")
    if (isinstance(scale, bool) or not isinstance(scale, (int, float))
            or not math.isfinite(scale) or not scale > 0):
        raise XEmbodimentError(f"{name}.position_scale: positive finite")
    frame = card.get("frame_id")
    if not frame or not isinstance(frame, str):
        raise XEmbodimentError(f"{name}.frame_id: non-empty string required")
    return {"embodiment_id": eid, "space": space,
            "position_scale": float(scale), "frame_id": frame}


def _check_trace(trace, name: str) -> int:
    if not isinstance(trace, (list, tuple)) or len(trace) == 0:
        raise XEmbodimentError(f"{name}: non-empty point sequence required")
    dim = None
    for i, pt in enumerate(trace):
        if not isinstance(pt, (list, tuple)) or len(pt) == 0:
            raise XEmbodimentError(f"{name}[{i}]: non-empty tuple required")
        if dim is None:
            dim = len(pt)
        elif len(pt) != dim:
            raise XEmbodimentError(f"{name}[{i}]: ragged trace")
        for v in pt:
            if (isinstance(v, bool) or not isinstance(v, (int, float))
                    or not math.isfinite(v)):
                raise XEmbodimentError(f"{name}[{i}]: finite numbers only")
    return dim


def _normalize(trace, scale: float) -> list:
    return [[float(v) / scale for v in pt] for pt in trace]


def _center(trace: list) -> list:
    dim = len(trace[0])
    n = len(trace)
    centroid = [math.fsum(pt[d] for pt in trace) / n for d in range(dim)]
    return [[pt[d] - centroid[d] for d in range(dim)] for pt in trace]


def transfer_score(card_a: dict, trace_a, card_b: dict, trace_b) -> dict:
    """Centered Frechet in normalized task space. Refuses joint-space.

    Frame contract: the caller maps both traces into comparable space
    BEFORE calling. Differing frame_ids are RECORDED (see "frames" and
    "frames_match") and compared as-is; centering removes translation
    only, so cross-frame rotation still inflates the distance. For
    strict transfer, map to one common frame first (M5c note)."""
    card_a = check_card(card_a, "card_a")
    card_b = check_card(card_b, "card_b")
    if card_a["space"] != "task" or card_b["space"] != "task":
        raise XEmbodimentError(
            "REFUSED: cross-embodiment compare needs task-space cards on "
            f"both sides (got {card_a['space']}/{card_b['space']}). "
            "Joint angles do not transfer across morphologies; declare a "
            "task-space card or scope single-embodiment scoring.")
    dim_a = _check_trace(trace_a, "trace_a")
    dim_b = _check_trace(trace_b, "trace_b")
    if dim_a != dim_b:
        raise XEmbodimentError(
            f"task-space dim mismatch: {dim_a} != {dim_b}")
    norm_a = _normalize(trace_a, card_a["position_scale"])
    norm_b = _normalize(trace_b, card_b["position_scale"])
    try:
        raw = discrete_frechet(norm_a, norm_b)
        centered = discrete_frechet(_center(norm_a), _center(norm_b))
    except Exception as exc:
        raise XEmbodimentError(f"frechet refused: {exc}")
    return {"centered_frechet": centered,
            "normalized_frechet": raw,
            "n": len(trace_a), "m": len(trace_b),
            "scales": [card_a["position_scale"], card_b["position_scale"]],
            "frames": [card_a["frame_id"], card_b["frame_id"]],
            "frames_match": card_a["frame_id"] == card_b["frame_id"]}


def transfer_report(card_a: dict, trace_a, card_b: dict, trace_b,
                    *, threshold: float) -> dict:
    """Score + TRANSFERS/REVIEW verdict + the M5b limitation, honestly."""
    if (isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(threshold) or not threshold >= 0):
        raise XEmbodimentError("threshold: finite number >= 0 required")
    score = transfer_score(card_a, trace_a, card_b, trace_b)
    score["threshold"] = threshold
    score["transfers"] = score["centered_frechet"] <= threshold
    score["limitation"] = ("M5b open: control-rate differences need "
                           "resampling; horizons here are compared as-is")
    return score
