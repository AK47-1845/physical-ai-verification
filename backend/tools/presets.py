"""Shared preset library for smoke_live + the live-preset test.

Single source of truth lives in presets.json (same directory).
 Placeholders: a string exactly equal to "$NAME" resolves to the raw
context value (any JSON type); "$NAME" embedded in a longer string
(paths, query strings) interpolates the string form of a scalar value.
Constants preload the context. Unknown placeholder, or a dict/list
embedded in text -> PresetError (fail loudly, never send "$FOO").
Dot-paths for save rules: "a.b.c" walks dicts; "" means whole body.
Stdlib only.
"""

import copy
import json
import os
import re

_TOKEN = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")

HERE = os.path.dirname(os.path.abspath(__file__))
PRESETS_PATH = os.path.join(HERE, "presets.json")


class PresetError(ValueError):
    """Bad preset library or unresolvable placeholder."""


def load():
    """Load + validate presets.json. Returns (constants, calls)."""
    with open(PRESETS_PATH, encoding="utf-8") as handle:
        doc = json.load(handle)
    if doc.get("version") != 1:
        raise PresetError("presets.json: version 1 required")
    constants = doc.get("constants")
    calls = doc.get("calls")
    if not isinstance(constants, dict) or not isinstance(calls, list):
        raise PresetError("presets.json: constants dict + calls list")
    seen = set()
    for pos, call in enumerate(calls):
        if not isinstance(call, dict):
            raise PresetError(f"calls[{pos}]: dict required")
        cid = call.get("id")
        if not cid or not isinstance(cid, str) or cid in seen:
            raise PresetError(f"calls[{pos}]: unique string id required")
        seen.add(cid)
        if call.get("method") not in ("GET", "POST"):
            raise PresetError(f"{cid}: method GET|POST required")
        if not call.get("path") or not isinstance(call["path"], str):
            raise PresetError(f"{cid}: path string required")
        if ("expect" not in call or isinstance(call["expect"], bool)
                or not isinstance(call["expect"], int)):
            raise PresetError(f"{cid}: expect int status required")
    return constants, calls


def resolve(node, ctx):
    """Deep-resolve $VAR placeholders against ctx.

    Exact "$NAME" returns the raw value (any JSON type, copied).
    "$NAME" inside a longer string interpolates scalars only.
    """
    if isinstance(node, str):
        if _TOKEN.fullmatch(node):
            name = node[1:]
            if name not in ctx:
                raise PresetError(f"unknown placeholder ${name}")
            return copy.deepcopy(ctx[name])
        if "$" in node:
            def _sub(match):
                name = match.group(1)
                if name not in ctx:
                    raise PresetError(f"unknown placeholder ${name}")
                value = ctx[name]
                if isinstance(value, (dict, list)):
                    raise PresetError(
                        f"placeholder ${name} is not a scalar")
                return str(value)

            return _TOKEN.sub(_sub, node)
        return node
    if isinstance(node, dict):
        return {key: resolve(val, ctx) for key, val in node.items()}
    if isinstance(node, list):
        return [resolve(val, ctx) for val in node]
    return node


def dig(body, dotpath):
    """Walk dot-path through dicts. '' returns the whole body."""
    if dotpath == "":
        return body
    node = body
    for part in dotpath.split("."):
        if not isinstance(node, dict) or part not in node:
            raise PresetError(f"save path {dotpath!r} missing in response")
        node = node[part]
    return node


def base_context(constants):
    """Fresh chain context preloaded with (resolved) constants."""
    ctx = {}
    for key, val in constants.items():
        ctx[key] = resolve(val, ctx)
    return ctx
