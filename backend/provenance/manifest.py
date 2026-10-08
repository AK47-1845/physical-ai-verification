"""Generation-level batch manifests (C2PA vocabulary, JSON sidecars).

Every synthetic batch is stamped AT GENERATION with: who made it
(generator id + version + params), how (seed, batch sequence), from what
(ingredient list with real/synthetic split), and a hard binding
(sha256 of the content). C2PA uses JUMBF inside media files; our
artifacts are JSON/trajectories, so the manifest travels as a sidecar
`<batch>.manifest.json` plus an optional invisible seed-stamp inside the
data itself (see axiom_bridge.seed_stamp).

Unsigned in v1 (signature: null, honestly labeled); Ed25519 signing is
M7b. Timestamps live OUTSIDE the hashed body, always.
"""

from engine import InputError, canonical_hash


class ManifestError(InputError):
    """Itemized validation failure. Server formats these, never traces."""


FORMAT = "verification.batch-manifest/1"


def _need_str(d: dict, key: str, where: str) -> str:
    v = d.get(key)
    if not v or not isinstance(v, str):
        raise ManifestError(f"{where}.{key}: non-empty string required")
    return v


def _need_hash(v, where: str) -> str:
    import re
    if not isinstance(v, str) or re.fullmatch(r"[0-9a-f]{64}", v) is None:
        raise ManifestError(f"{where}: sha256 hex required, got {v!r}")
    return v


def stamp_batch(*, generator: dict, seed: int, content_hash: str,
                n_rows: int, ingredients: list,
                actions: list | None = None,
                batch_seq: int | None = None) -> dict:
    """Build + seal a batch manifest. Deterministic for fixed inputs."""
    if not isinstance(generator, dict):
        raise ManifestError("generator: dict required")
    name = _need_str(generator, "name", "generator")
    version = _need_str(generator, "version", "generator")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ManifestError(f"seed: int required, got {seed!r} "
                            f"(bools are not seeds)")
    _need_hash(content_hash, "content_hash")
    if (isinstance(n_rows, bool)
            or not isinstance(n_rows, int) or n_rows < 0):
        raise ManifestError(f"n_rows: non-negative int required: {n_rows!r}")
    if not isinstance(ingredients, list) or not ingredients:
        raise ManifestError("ingredients: non-empty list required")
    clean_ings = []
    for i, ing in enumerate(ingredients):
        if not isinstance(ing, dict):
            raise ManifestError(f"ingredients[{i}]: dict required")
        kind = ing.get("kind")
        if kind not in ("real", "synthetic"):
            raise ManifestError(
                f"ingredients[{i}].kind: 'real'|'synthetic', got {kind!r}")
        rows = ing.get("n_rows")
        if (isinstance(rows, bool)
                or not isinstance(rows, int) or rows < 0):
            raise ManifestError(f"ingredients[{i}].n_rows: non-negative int")
        clean_ings.append({
            "kind": kind,
            "n_rows": rows,
            "manifest_id": ing.get("manifest_id"),
            "content_hash": ing.get("content_hash"),
        })
        for key in ("manifest_id", "content_hash"):
            if clean_ings[-1][key] is not None:
                _need_hash(clean_ings[-1][key], f"ingredients[{i}].{key}")
    params = generator.get("params", {})
    if not isinstance(params, dict):
        raise ManifestError("generator.params: dict required")
    content_kind = generator.get("content_kind", "rows")
    if not content_kind or not isinstance(content_kind, str):
        raise ManifestError(
            "generator.content_kind: non-empty string required")
    if batch_seq is not None and (isinstance(batch_seq, bool)
                                      or not isinstance(batch_seq, int)):
        raise ManifestError(f"batch_seq: int or None, got {batch_seq!r}")
    if actions is not None and not isinstance(actions, list):
        raise ManifestError("actions: list or None required")
    body = {
        "format": FORMAT,
        "generator": {"name": name, "version": version,
                      "params": params},
        "seed": seed,
        "batch_seq": batch_seq,
        "content": {"kind": content_kind,
                    "n_rows": n_rows, "content_hash": content_hash},
        "ingredients": clean_ings,
        "assertions": [
            {"label": "c2pa.actions",
             "data": {"actions": actions or [{"action": "synthetic.generation",
                                              "softwareAgent": f"{name} {version}"}]}},
        ],
    }
    manifest_id = canonical_hash({
        "format": FORMAT, "generator": body["generator"], "seed": seed,
        "content_hash": content_hash, "n_rows": n_rows,
        "batch_seq": batch_seq})
    return {"manifest_id": manifest_id, "body": body,
            "body_hash": canonical_hash(body),
            "signature": None, "signature_note": "UNSIGNED v1"}


def verify_manifest(manifest: dict) -> dict:
    """Recompute + structural check. Returns ok or reason (never raises)."""
    try:
        if not isinstance(manifest, dict):
            return {"ok": False, "reason": "manifest must be a dict"}
        for key in ("manifest_id", "body", "body_hash"):
            if key not in manifest:
                return {"ok": False, "reason": f"missing key {key!r}"}
        body = manifest["body"]
        if canonical_hash(body) != manifest["body_hash"]:
            return {"ok": False, "reason": "body_hash mismatch (tampered?)"}
        expect_id = canonical_hash({
            "format": body.get("format"), "generator": body.get("generator"),
            "seed": body.get("seed"),
            "content_hash": body.get("content", {}).get("content_hash"),
            "n_rows": body.get("content", {}).get("n_rows"),
            "batch_seq": body.get("batch_seq")})
        if expect_id != manifest["manifest_id"]:
            return {"ok": False, "reason": "manifest_id mismatch (tampered?)"}
        if body.get("format") != FORMAT:
            return {"ok": False,
                    "reason": f"unknown format {body.get('format')!r}"}
        return {"ok": True, "manifest_id": manifest["manifest_id"],
                "signed": manifest.get("signature") is not None}
    except Exception as exc:  # unhashable bodies fail closed, never crash
        return {"ok": False, "reason": f"unverifiable body: {exc}"}
