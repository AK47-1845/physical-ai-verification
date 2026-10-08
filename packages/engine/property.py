"""G9 property-margin gate: STL-lite Always/Eventually with robustness.

A spec pins {op, name, version, window}; predicates map state -> margin
float (positive = holds). Always returns the MINIMUM margin (worst
moment), Eventually the MAXIMUM (best moment). Zero margin TOUCHES the
boundary and does NOT satisfy (fail-closed). Estimated states label the
whole verdict PROXY. Predicate CODE is pinned by name+version contract;
the spec hash covers the checkable fields.
"""

import math

from engine import InputError, sha256_hex


class PropertyError(InputError):
    """Itemized validation failure. Server formats these, never traces."""


def check_property(spec: dict, trace: list, *,
                   state_origin: str = "measured") -> dict:
    """Evaluate one property over a trace window. Returns margin verdict."""
    if not isinstance(spec, dict):
        raise PropertyError("spec: dict required")
    op = spec.get("op")
    if op not in ("always", "eventually"):
        raise PropertyError(f"spec.op: 'always'|'eventually', got {op!r}")
    predicate = spec.get("predicate")
    if not callable(predicate):
        raise PropertyError("spec.predicate: callable(state)->margin")
    name = spec.get("name")
    if not name or not isinstance(name, str):
        raise PropertyError("spec.name: non-empty string required")
    version = spec.get("version", "?")
    if isinstance(trace, (str, bytes, dict)):
        raise PropertyError(
            f"trace: state sequence required, got "
            f"{type(trace).__name__} (strings/dicts are caller bugs, "
            f"not traces)")
    try:
        trace = list(trace)
    except TypeError:
        raise PropertyError(
            f"trace: sequence required, got {type(trace).__name__}")
    if not trace:
        raise PropertyError("trace: non-empty state list required")
    window = spec.get("window")
    if window is None:
        window = [0, len(trace) - 1]
    if (not isinstance(window, (list, tuple)) or len(window) != 2
            or any(isinstance(v, bool) for v in window)
            or not all(isinstance(v, int) for v in window)):
        raise PropertyError("spec.window: [a, b] int pair required "
                            "(bools are not indices)")
    a, b = window
    if not 0 <= a <= b < len(trace):
        raise PropertyError(f"spec.window [{a}, {b}] outside trace "
                            f"length {len(trace)}")
    if state_origin not in ("measured", "estimated"):
        raise PropertyError("state_origin: 'measured'|'estimated'")
    margins = []
    for i in range(a, b + 1):
        try:
            margin = predicate(trace[i])
        except Exception as exc:
            raise PropertyError(f"predicate raised at index {i}: {exc!r}")
        if (isinstance(margin, bool)
                or not isinstance(margin, (int, float))
                or not math.isfinite(margin)):
            raise PropertyError(f"predicate must return finite margin "
                                f"(index {i}); bools are not margins")
        margins.append(float(margin))
    if op == "always":
        margin = min(margins)
        witness = a + margins.index(margin)
    else:
        margin = max(margins)
        witness = a + margins.index(margin)
    vtag = f"{type(version).__name__}:{version}"
    spec_hash = sha256_hex(f"prop:{op}:{name}:{vtag}:{a}:{b}")
    return {"satisfied": margin > 0.0, "margin": margin,
            "witness": witness, "op": op, "window": [a, b],
            "spec_hash": spec_hash,
            "label": "PROXY" if state_origin == "estimated" else "MEASURED"}


def _clearance_margin(state):
    """Margin = state['clearance'] (positive = clear)."""
    if not isinstance(state, dict):
        raise PropertyError("clearance: state dict required")
    value = state.get("clearance")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PropertyError("clearance: state['clearance'] number "
                            "required (bools are not margins)")
    return float(value)


def _speed_cap_2_margin(state):
    """Margin = 2.0 - state['speed'] (positive = under the cap)."""
    if not isinstance(state, dict):
        raise PropertyError("speed_cap_2: state dict required")
    value = state.get("speed")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PropertyError("speed_cap_2: state['speed'] number "
                            "required (bools are not margins)")
    return 2.0 - float(value)


PREDICATES = {"clearance": (_clearance_margin, "clearance/v1"),
              "speed_cap_2": (_speed_cap_2_margin, "speed_cap_2/v1")}


def get_predicate(name: str):
    """Look up a named margin predicate (name, version, callable).

    Custom predicates stay library-only (callables cannot cross HTTP
    honestly); named presets are pinned by name+version contract.
    """
    if not isinstance(name, str) or name not in PREDICATES:
        raise PropertyError(f"predicate: unknown preset {name!r}; "
                            f"known: {sorted(PREDICATES)} (custom "
                            f"predicates are library-only)")
    fn, version = PREDICATES[name]
    return {"name": name, "version": version, "fn": fn}
