"""M3 slice 1: bounded verifier for affine+ReLU sub-policies (stdlib).

Interval propagation over boxes: affine layers push intervals through
weight signs, ReLU clamps at zero. Output box inside the bounds =>
PROVEN. Otherwise a deterministic grid search hunts a concrete witness:
found => VIOLATED (with the witness input/output); none found =>
UNKNOWN (intervals over-approximate; absence of a coarse-grid witness
proves nothing). Z3/alpha-beta-CROWN stay last in M3; this slice covers
small sub-policies honestly today.

Soundness contract: every interval op widens 1ulp outward
(math.nextafter), so the computed box always contains the TRUE range
and PROVEN is rigorous for affine+relu over float64 inputs.
Completeness cost: proofs that touch a bound exactly now return
UNKNOWN (the widened box exceeds the bound by ~1ulp); restate such
bounds with margin. Z3/alpha-beta-CROWN stay last in M3 for exact
boundary proofs and richer activations.
"""

import itertools
import math
import re

from engine import ENGINE_VERSION, InputError


class BoundedError(InputError):
    """Itemized validation failure. Server formats these, never traces."""


MAX_GRID_POINTS = 20000

MODEL_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}")


def _is_num(v) -> bool:
    return (not isinstance(v, bool) and isinstance(v, (int, float))
            and math.isfinite(v))


def _check_box(box, name: str) -> list:
    if not isinstance(box, (list, tuple)) or not box:
        raise BoundedError(f"{name}: non-empty [(lo, hi)] list required")
    clean = []
    for i, pair in enumerate(box):
        if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                or not _is_num(pair[0]) or not _is_num(pair[1])
                or not pair[0] <= pair[1]):
            raise BoundedError(f"{name}[{i}]: need lo <= hi finite pair")
        clean.append([float(pair[0]), float(pair[1])])
    return clean


def _check_layers(layers, in_dim: int) -> list:
    if not isinstance(layers, (list, tuple)) or not layers:
        raise BoundedError("layers: non-empty list required")
    dim = in_dim
    clean = []
    for num, layer in enumerate(layers):
        if not isinstance(layer, dict):
            raise BoundedError(f"layers[{num}]: dict required")
        weights = layer.get("weights")
        bias = layer.get("bias")
        act = layer.get("activation", "linear")
        if act not in ("relu", "linear"):
            raise BoundedError(f"layers[{num}]: activation relu|linear")
        if not isinstance(weights, (list, tuple)) or not weights:
            raise BoundedError(f"layers[{num}]: weights rows required")
        if (not isinstance(bias, (list, tuple))
                or len(bias) != len(weights)):
            raise BoundedError(f"layers[{num}]: bias must match rows")
        for row in weights:
            if not isinstance(row, (list, tuple)) or len(row) != dim:
                raise BoundedError(
                    f"layers[{num}]: each row must have dim {dim}")
            if not all(_is_num(v) for v in row):
                raise BoundedError(f"layers[{num}]: finite weights only")
        if not all(_is_num(v) for v in bias):
            raise BoundedError(f"layers[{num}]: finite bias only")
        clean.append({"weights": weights, "bias": [float(v) for v in bias],
                      "activation": act})
        dim = len(weights)
    return clean


def _outward(lo: float, hi: float) -> list:
    """Widen 1ulp each side (infinite endpoints stay infinite)."""
    if math.isfinite(lo):
        lo = math.nextafter(lo, -math.inf)
    if math.isfinite(hi):
        hi = math.nextafter(hi, math.inf)
    return [lo, hi]


def _affine_box(weights, bias, box: list) -> list:
    out = []
    for row, offset in zip(weights, bias):
        lo, hi = _outward(float(offset), float(offset))
        for w, (blo, bhi) in zip(row, box):
            if w >= 0:
                lo += w * blo
                hi += w * bhi
            else:
                lo += w * bhi
                hi += w * blo
            lo, hi = _outward(lo, hi)
        out.append([lo, hi])
    return out


def _relu_box(box: list) -> list:
    return [[max(0.0, lo), max(0.0, hi)] for lo, hi in box]


def _eval_point(layers: list, point: list) -> list:
    values = [float(v) for v in point]
    for layer in layers:
        nxt = []
        for row, offset in zip(layer["weights"], layer["bias"]):
            total = float(offset) + math.fsum(w * v for w, v in zip(row, values))
            nxt.append(total)
        if layer["activation"] == "relu":
            nxt = [max(0.0, v) for v in nxt]
        values = nxt
    return values


def _violates(output: list, bounds: list) -> bool:
    return any(v < lo or v > hi for v, (lo, hi) in zip(output, bounds))


def _certificate(verdict: str, input_box: list,
                 model_hash, witness) -> tuple:
    """Scope the verdict: what was proved, for which model, over what."""
    assumptions = [
        "float64 outward-rounded intervals over affine+relu ops",
        "input box is the full domain (nothing outside was checked)",
        "grid witness search is deterministic (no RNG; seed n/a)",
    ]
    if model_hash is None:
        assumptions.append(
            "model weights NOT pinned: binds only to the weights "
            "passed in this call")
    cert = {"model_hash": model_hash, "domain": input_box,
            "assumptions": assumptions, "method": "interval+grid",
            "engine_version": ENGINE_VERSION, "seed": None}
    who = model_hash if model_hash is not None else "UNPINNED"
    if verdict == "PROVEN":
        scope = (f"PROVEN for model {who} over {input_box} under "
                 f"{len(assumptions)} assumptions")
    elif verdict == "VIOLATED":
        scope = (f"VIOLATED for model {who} over {input_box}: "
                 f"witness at {witness['input']}")
    else:
        scope = (f"UNKNOWN for model {who} over {input_box}: "
                 f"neither proved nor disproved")
    return cert, scope


def verify_affine_relu(layers: list, input_box, output_bounds,
                       *, grid_per_dim: int = 5,
                       model_hash=None) -> dict:
    """PROVEN (box inside) / VIOLATED (witness) / UNKNOWN (neither).

    Over-budget grids raise instead of guessing (D-night-18): an
    UNKNOWN would claim a search that never ran.
    """
    box = _check_box(input_box, "input_box")
    bounds = _check_box(output_bounds, "output_bounds")
    clean = _check_layers(layers, len(box))
    if not isinstance(grid_per_dim, int) or grid_per_dim < 2:
        raise BoundedError("grid_per_dim: int >= 2 required")
    if model_hash is not None and (
            not isinstance(model_hash, str)
            or MODEL_HASH_RE.fullmatch(model_hash) is None):
        raise BoundedError("model_hash: None or 'sha256:<64hex>' required")
    if len(clean[-1]["bias"]) != len(bounds):
        raise BoundedError("output dim must match output_bounds length")
    interval = box
    for layer in clean:
        interval = _affine_box(layer["weights"], layer["bias"], interval)
        if layer["activation"] == "relu":
            interval = _relu_box(interval)
    inside = all(lo >= blo and hi <= bhi
                 for (lo, hi), (blo, bhi) in zip(interval, bounds))
    if inside:
        cert, scope = _certificate("PROVEN", box, model_hash, None)
        return {"verdict": "PROVEN", "output_box": interval,
                "witness": None, "certificate": cert, "scope": scope}
    points = grid_per_dim ** len(box)
    if points > MAX_GRID_POINTS:
        raise BoundedError(
            f"grid {points} exceeds MAX_GRID_POINTS={MAX_GRID_POINTS}: "
            f"coarsen grid_per_dim or split the input box")
    axes = []
    for lo, hi in box:
        axes.append([lo + (hi - lo) * k / (grid_per_dim - 1)
                     for k in range(grid_per_dim)])
    for combo in itertools.product(*axes):
        output = _eval_point(clean, list(combo))
        if _violates(output, bounds):
            witness = {"input": list(combo), "output": output}
            cert, scope = _certificate("VIOLATED", box, model_hash,
                                       witness)
            return {"verdict": "VIOLATED", "output_box": interval,
                    "witness": witness, "certificate": cert,
                    "scope": scope}
    cert, scope = _certificate("UNKNOWN", box, model_hash, None)
    return {"verdict": "UNKNOWN", "output_box": interval, "witness": None,
            "certificate": cert, "scope": scope}
