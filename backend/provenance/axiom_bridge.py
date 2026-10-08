"""Axiom bridge: wrap a verification-axiom generation in V&V provenance.

Seam (duck-typed, NO pandas import here): the caller passes the axiom
result's generator name/version, seed, row count, a content hash it
computed over canonical bytes (parquet/CSV), real-data ingredients, and
the axiom datacard dict. The bridge stamps a batch manifest, builds the
mix-ledger batch record, and merges the axiom datacard under one envelope.

seed_stamp() is the invisible channel: deterministic per-row stamp ids
from (seed, row_index). Axiom adds them as a tag column at generation;
downstream joins re-verify them. Pure sha256, no state.
"""

from engine import InputError, sha256_hex

from backend.provenance.manifest import stamp_batch
from backend.provenance.mixtrack import MixError, add_generation, new_corpus


class BridgeError(InputError):
    """Itemized validation failure. Server formats these, never traces."""


def seed_stamp(seed: int, row_index: int) -> str:
    """Deterministic 12-hex stamp id for one row. Stateless."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise BridgeError(f"seed: int required, got {seed!r} "
                          f"(bools are not seeds)")
    if (isinstance(row_index, bool)
            or not isinstance(row_index, int) or row_index < 0):
        raise BridgeError(f"row_index: non-negative int, got {row_index!r}")
    return sha256_hex(f"verification-stamp:{seed}:{row_index}")[:12]


def bridge_generation(*, generator_name: str, generator_version: str,
                      seed: int, n_rows: int, content_hash: str,
                      real_ingredients: list,
                      axiom_datacard: dict | None = None,
                      batch_seq: int | None = None,
                      generator_params: dict | None = None,
                      model_id: str | None = None,
                      model_version: str | None = None,
                      batch_id: str | None = None) -> dict:
    """Stamp + mix-record + datacard merge for one axiom run."""
    if not generator_name or not isinstance(generator_name, str):
        raise BridgeError("generator_name: non-empty string required")
    if not generator_version or not isinstance(generator_version, str):
        raise BridgeError("generator_version: non-empty string required")
    try:
        real_ingredients = list(real_ingredients)
    except TypeError:
        raise BridgeError(
            "real_ingredients: list required, "
            f"got {type(real_ingredients).__name__}")
    if not real_ingredients:
        raise BridgeError("real_ingredients: at least one real source "
                          "required (synthetic-from-nothing is untraceable)")
    for i, ing in enumerate(real_ingredients):
        if not isinstance(ing, dict) or ing.get("kind") != "real":
            raise BridgeError(f"real_ingredients[{i}]: dict with kind='real'")
    if axiom_datacard is not None and not isinstance(axiom_datacard,
                                                        dict):
        raise BridgeError("axiom_datacard: dict or None required")
    if generator_params is None:
        generator_params = {}
    if not isinstance(generator_params, dict):
        raise BridgeError("generator_params: dict or None required")
    lineage = {}
    for key, value in (("model_id", model_id), ("model_version", model_version), ("batch_id", batch_id)):
        if value is not None:
            if not isinstance(value, str) or not value.strip() or len(value) > 128:
                raise BridgeError(f"{key}: non-empty string of at most 128 characters required")
            lineage[key] = value
    if (model_id is None) != (model_version is None):
        raise BridgeError("model_id and model_version must be supplied together")
    if lineage:
        if "lineage" in generator_params and generator_params["lineage"] != lineage:
            raise BridgeError("Conflicting generation lineage declarations")
        generator_params = {**generator_params, "lineage": lineage}
    try:
        manifest = stamp_batch(
            generator={"name": generator_name, "version": generator_version,
                       "params": generator_params or {},
                       "content_kind": "axiom-rows"},
            seed=seed, content_hash=content_hash, n_rows=n_rows,
            ingredients=real_ingredients, batch_seq=batch_seq)
    except Exception as exc:
        raise BridgeError(f"manifest refused: {exc}")
    try:
        tmp = new_corpus("bridge-check")
        mix_batch = {"manifest_id": manifest["manifest_id"], "n_rows": n_rows}
        add_generation(tmp, real_rows=sum(i.get("n_rows", 0)
                                          for i in real_ingredients),
                       synth_batches=[mix_batch])
    except MixError as exc:
        raise BridgeError(f"mix record refused: {exc}")
    return {"manifest": manifest, "mix_batch": mix_batch,
            "stamp_recipe": "seed_stamp(seed, row_index) as tag column",
            "axiom_datacard": axiom_datacard}
