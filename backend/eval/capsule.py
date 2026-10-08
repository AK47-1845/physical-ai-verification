"""Evidence Replay Capsule: seal one request+envelope+mode, verify later.

[ASTRA-IDEA 4] as product behavior. The demo could export a track with
a hash but nothing could check it, and workspace runs had no capsule
at all. seal_capsule binds {schema, mode, request, envelope,
backend_host} under a track hash; verify_capsule recomputes it.
Mode is REQUIRED at seal and covered by the hash, so a synthetic
fallback can never silently inherit a live badge. Hash is integrity,
not authorship: capsules are UNSIGNED (no signing story exists).
Stdlib only; service_app maps CapsuleError to HTTP 422.
"""

from engine import InputError, canonical_hash

SCHEMA = "verification.replay-capsule/1"

_VERIFY_ENDPOINT = "POST /api/v2/eval/capsule/verify"

_REPLAY_STEPS = (
    "POST this whole JSON capsule to /api/v2/eval/capsule/verify.",
    "ok=true means the bytes match the sealed track hash.",
    "ok=false names the mismatch; treat the capsule as tampered.",
    "Re-run the embedded request against a live backend to confirm "
    "the evidence still reproduces; a capsule never replaces a run.",
)


class CapsuleError(InputError):
    """Seal/verify refusal. Server formats these, never traces."""


def _need_dict(value, where: str) -> dict:
    if not isinstance(value, dict):
        raise CapsuleError(f"{where}: JSON object required")
    return value


def seal_capsule(body: dict) -> dict:
    """Seal a capsule from {request, envelope, mode, backend_host?}.

    request needs path/method/body keys; envelope needs status/data
    keys. mode is required non-empty (no silent default). Unknown
    top-level keys are refused loudly: the caller controls this input
    now, so typos must fail here, not verify clean later.
    """
    _need_dict(body, "capsule")
    allowed = {"request", "envelope", "mode", "backend_host"}
    unknown = sorted(set(body) - allowed)
    if unknown:
        raise CapsuleError(f"capsule: unknown keys {unknown}")
    for key in ("request", "envelope", "mode"):
        if key not in body:
            raise CapsuleError(f"capsule: missing key {key!r}")
    request = _need_dict(body["request"], "capsule.request")
    for key in ("path", "method", "body"):
        if key not in request:
            raise CapsuleError(f"capsule.request: missing key {key!r}")
    envelope = _need_dict(body["envelope"], "capsule.envelope")
    for key in ("status", "data"):
        if key not in envelope:
            raise CapsuleError(f"capsule.envelope: missing key {key!r}")
    mode = body["mode"]
    if not isinstance(mode, str) or not mode.strip():
        raise CapsuleError("capsule.mode: non-empty string required")
    host = body.get("backend_host", "unrecorded")
    if not isinstance(host, str) or not host.strip():
        raise CapsuleError("capsule.backend_host: non-empty string required")
    core = {"schema": SCHEMA, "mode": mode, "request": request,
            "envelope": envelope, "backend_host": host}
    return {**core,
            "replay": {"verify_endpoint": _VERIFY_ENDPOINT,
                       "steps": list(_REPLAY_STEPS)},
            "track_hash": canonical_hash(core)}


def verify_capsule(body: dict) -> dict:
    """Verify a sealed capsule. Never raises on content; refuses shape.

    Recomputes the track hash over {schema, mode, request, envelope,
    backend_host}. Unknown top-level keys are IGNORED LOUDLY (reported
    in ignored[]) so old verifiers stay readable on newer capsules.
    Structural problems raise CapsuleError (HTTP 422 at the route).
    """
    capsule = _need_dict(body, "capsule")
    if capsule.get("schema") != SCHEMA:
        raise CapsuleError(f"capsule.schema: want {SCHEMA!r}")
    for key in ("mode", "request", "envelope", "track_hash"):
        if key not in capsule:
            raise CapsuleError(f"capsule: missing key {key!r}")
    mode = capsule["mode"]
    if not isinstance(mode, str) or not mode.strip():
        raise CapsuleError("capsule.mode: non-empty string required")
    request = _need_dict(capsule["request"], "capsule.request")
    envelope = _need_dict(capsule["envelope"], "capsule.envelope")
    host = capsule.get("backend_host", "unrecorded")
    if not isinstance(host, str):
        raise CapsuleError("capsule.backend_host: string required")
    if not isinstance(capsule["track_hash"], str):
        raise CapsuleError("capsule.track_hash: string required")
    ignored = sorted(set(capsule) - {"schema", "mode", "request",
                                     "envelope", "backend_host",
                                     "replay", "track_hash"})
    core = {"schema": SCHEMA, "mode": mode, "request": request,
            "envelope": envelope, "backend_host": host}
    expected = canonical_hash(core)
    if capsule["track_hash"] != expected:
        return {"ok": False, "mode": mode, "track_hash": expected,
                "reason": "track_hash mismatch (tampered?)",
                "ignored": ignored,
                "authorship": "UNSIGNED: hash proves integrity, not author"}
    return {"ok": True, "mode": mode, "track_hash": expected,
            "ignored": ignored,
            "authorship": "UNSIGNED: hash proves integrity, not author"}
