"""Corpus mix (alpha) ledger: the accumulation-vs-replace watchdog.

Each training generation records real rows + synthetic batches (by
manifest id). alpha = real / (real + synthetic). A generation with zero
real rows after real data existed is a REPLACE event: the exact pattern
Shumailov et al. show collapses tails, then everything. Pure functions
over dicts; the store layer persists. Stdlib only.

Also houses: dataset cards (FR-12), ratio enforcement (FR-13),
sample-id registry (FR-14), re-anchor tracking (FR-15). All pure.
"""

from engine import InputError, canonical_hash

GENESIS_SEAL = "0" * 64


class MixError(InputError):
    """Itemized validation failure. Server formats these, never traces."""


def new_corpus(corpus_id: str) -> dict:
    """Empty mix ledger for one training corpus."""
    if not corpus_id or not isinstance(corpus_id, str):
        raise MixError("corpus_id: non-empty string required")
    return {"corpus_id": corpus_id, "generations": []}


def add_generation(corpus: dict, *, real_rows: int,
                   synth_batches: list) -> dict:
    """Record one generation. synth_batches: [{manifest_id, n_rows}]."""
    if (not isinstance(corpus, dict)
            or not isinstance(corpus.get("generations"), list)):
        raise MixError("corpus: {'generations': [...]} dict required")
    if (isinstance(real_rows, bool)
            or not isinstance(real_rows, int) or real_rows < 0):
        raise MixError(f"real_rows: non-negative int required: {real_rows!r}")
    try:
        synth_batches = list(synth_batches)
    except TypeError:
        raise MixError("synth_batches: list required")
    synth_rows = 0
    registry = {}
    for i, batch in enumerate(synth_batches):
        if not isinstance(batch, dict):
            raise MixError(f"synth_batches[{i}]: dict required")
        if not batch.get("manifest_id"):
            raise MixError(f"synth_batches[{i}]: manifest_id required "
                           f"(unstamped synthetic is untraceable)")
        rows = batch.get("n_rows")
        if (isinstance(rows, bool)
                or not isinstance(rows, int) or rows < 0):
            raise MixError(f"synth_batches[{i}].n_rows: non-negative int")
        synth_rows += rows
        if "sample_ids" in batch:
            registry[batch["manifest_id"]] = _registry_entry(
                batch["manifest_id"], batch["sample_ids"], i)
    total = real_rows + synth_rows
    if total == 0:
        raise MixError("empty generation: real_rows + synth_rows must be > 0")
    record = {"gen": len(corpus["generations"]),
              "real_rows": real_rows,
              "synth_rows": synth_rows,
              "alpha": real_rows / total,
              "manifest_ids": [b["manifest_id"] for b in synth_batches]}
    if registry:
        record["sample_registry"] = registry
    prev = GENESIS_SEAL
    for prior in reversed(corpus["generations"]):
        if isinstance(prior, dict) and isinstance(prior.get("seal"), str):
            prev = prior["seal"]
            break
    record["seal"] = canonical_hash({"prev": prev, "record": record})
    corpus["generations"].append(record)
    return record


def _verify_seals(gens: list) -> dict:
    """Replay the seal chain. Raises MixError on the first mismatch.

    Generations without a seal are pre-seal (legacy) history: they
    read fine and are counted, but they neither advance nor break
    the chain. Residuals: tail truncation and full seal-stripping
    are invisible without an externally pinned head (same class as
    a ledger without an anchor).
    """
    prev = GENESIS_SEAL
    sealed = legacy = 0
    for gen in gens:
        seal = gen.get("seal")
        if seal is None:
            legacy += 1
            continue
        body = {key: val for key, val in gen.items() if key != "seal"}
        if not isinstance(seal, str) or canonical_hash(
                {"prev": prev, "record": body}) != seal:
            raise MixError(f"generation {gen.get('gen')}: seal mismatch "
                           f"(history tampered?)")
        prev = seal
        sealed += 1
    return {"sealed": sealed, "legacy": legacy}


def _registry_entry(manifest_id: str, sample_ids, pos: int) -> dict:
    """Hash a batch's sample-id list (FR-14). Audits recompute later."""
    if (not isinstance(sample_ids, list) or not sample_ids
            or not all(isinstance(s, str) and s for s in sample_ids)):
        raise MixError(f"synth_batches[{pos}].sample_ids: non-empty list "
                       f"of non-empty strings required")
    if len(set(sample_ids)) != len(sample_ids):
        raise MixError(f"synth_batches[{pos}].sample_ids: ids must be "
                       f"unique (dupes hide fraction games)")
    digest = canonical_hash(sorted(sample_ids))
    return {"n": len(sample_ids), "ids_hash": digest,
            "manifest_id": manifest_id}


def registry_verify(corpus: dict, gen: int, manifest_id: str,
                    sample_ids: list) -> dict:
    """Recompute a recorded sample registry (FR-14 audit path).

    Structural problems raise; a missing registry or a hash mismatch
    returns ok False (verification outcome, not a crash).
    """
    if not isinstance(corpus, dict):
        raise MixError("corpus: dict required")
    gens = corpus.get("generations")
    if not isinstance(gens, list):
        raise MixError("corpus.generations: list required")
    if isinstance(gen, bool) or not isinstance(gen, int):
        raise MixError(f"gen: int required: {gen!r}")
    if not 0 <= gen < len(gens):
        raise MixError(f"gen {gen}: out of range 0..{len(gens) - 1}")
    if not isinstance(manifest_id, str) or not manifest_id:
        raise MixError("manifest_id: non-empty string required")
    if (not isinstance(sample_ids, list)
            or not all(isinstance(s, str) for s in sample_ids)):
        raise MixError("sample_ids: list of strings required")
    record = gens[gen]
    if not isinstance(record, dict):
        raise MixError(f"generation {gen}: dict required (corrupt?)")
    _verify_seals(gens)
    registry = record.get("sample_registry")
    if registry is not None and not isinstance(registry, dict):
        raise MixError(f"generation {gen} sample_registry: dict or "
                       f"missing required (corrupt history?)")
    entry = (registry or {}).get(manifest_id)
    if entry is None:
        return {"ok": False,
                "reason": "no sample registry recorded for "
                          f"{manifest_id} at gen {gen}"}
    digest = canonical_hash(sorted(sample_ids))
    if digest != entry.get("ids_hash") or len(sample_ids) != entry.get("n"):
        return {"ok": False,
                "reason": f"registry mismatch for {manifest_id} at gen "
                          f"{gen} (ids changed or incomplete?)"}
    return {"ok": True, "gen": gen, "manifest_id": manifest_id,
            "n": entry["n"]}


def build_dataset_card(*, dataset_id: str, generator: dict,
                       verifier: dict, real_rows: int, synth_rows: int,
                       pass_rate: float, manifest_ids=None) -> dict:
    """Machine-readable dataset card per scored dataset (FR-12)."""
    if not dataset_id or not isinstance(dataset_id, str):
        raise MixError("dataset_id: non-empty string required")
    for label, party, keys in (("generator", generator, ("id", "version")),
                               ("verifier", verifier, ("id",))):
        if not isinstance(party, dict):
            raise MixError(f"{label}: dict required")
        for key in keys:
            if not party.get(key) or not isinstance(party[key], str):
                raise MixError(f"{label}.{key}: non-empty string required")
    for label, rows in (("real_rows", real_rows),
                        ("synth_rows", synth_rows)):
        if isinstance(rows, bool) or not isinstance(rows, int) or rows < 0:
            raise MixError(f"{label}: non-negative int required")
    total = real_rows + synth_rows
    if total == 0:
        raise MixError("empty dataset: cards describe scored datasets")
    if (isinstance(pass_rate, bool)
            or not isinstance(pass_rate, (int, float))
            or not 0.0 <= pass_rate <= 1.0):
        raise MixError(f"pass_rate: number in [0, 1] required: "
                       f"{pass_rate!r}")
    if manifest_ids is None:
        manifest_ids = []
    if (isinstance(manifest_ids, str)
            or not isinstance(manifest_ids, (list, tuple))):
        raise MixError("manifest_ids: list of non-empty strings required")
    manifest_ids = list(manifest_ids)
    if synth_rows > 0 and not manifest_ids:
        raise MixError("manifest_ids: required when synth_rows > 0 "
                       "(unstamped synthetic is untraceable)")
    if synth_rows == 0 and manifest_ids:
        raise MixError("manifest_ids: must be empty when synth_rows == 0")
    if not all(isinstance(m, str) and m for m in manifest_ids):
        raise MixError("manifest_ids: non-empty strings required")
    card = {"dataset_id": dataset_id,
            "generator": {"id": generator["id"],
                          "version": generator["version"]},
            "verifier": {"id": verifier["id"],
                         "version": verifier.get("version")},
            "pass_rate": float(pass_rate),
            "real_rows": real_rows, "synth_rows": synth_rows,
            "alpha": real_rows / total,
            "manifest_ids": manifest_ids}
    card["card_hash"] = canonical_hash(card)
    return card


def enforce_alpha(*, profile_max_synth: float, corpus: dict) -> dict:
    """Ratio enforcement (FR-13): profile max vs measured synthetic frac.

    Exceeding the max BLOCKs the dataset gate with the measured
    fraction shown. Empty/unlogged corpora are INSUFFICIENT.
    """
    if (isinstance(profile_max_synth, bool)
            or not isinstance(profile_max_synth, (int, float))
            or not 0.0 <= profile_max_synth <= 1.0):
        raise MixError(f"profile_max_synth: number in [0, 1] required: "
                       f"{profile_max_synth!r}")
    risk = lineage_risk(corpus)
    if risk["verdict"] == "INSUFFICIENT":
        return {"status": "INSUFFICIENT",
                "reason": "no generations logged",
                "profile_max_synth": float(profile_max_synth)}
    alpha_now = risk["alpha_now"]
    if (isinstance(alpha_now, bool)
            or not isinstance(alpha_now, (int, float))
            or not 0.0 <= alpha_now <= 1.0):
        raise MixError(f"alpha_now out of [0, 1]: {alpha_now!r} "
                       f"(corrupt history?)")
    measured = 1.0 - alpha_now
    status = "BLOCKED" if measured > profile_max_synth else "PASS"
    return {"status": status, "measured_synth_frac": measured,
            "profile_max_synth": float(profile_max_synth),
            "alpha_now": risk["alpha_now"],
            "generations": risk["generations"],
            "lineage_verdict": risk["verdict"]}


def reanchor_status(*, created_ts: int, cadence_days: int,
                    now_ts: int) -> dict:
    """Dataset age vs re-anchor cadence (FR-15). Stale reads REVIEW.

    All timestamps explicit epoch seconds; this module never reads the
    wall clock (offline law). The service layer passes now.
    """
    for label, val in (("created_ts", created_ts),
                       ("now_ts", now_ts)):
        if isinstance(val, bool) or not isinstance(val, int) or val < 0:
            raise MixError(f"{label}: non-negative epoch int required")
    if (isinstance(cadence_days, bool)
            or not isinstance(cadence_days, int) or cadence_days <= 0):
        raise MixError("cadence_days: positive int required")
    if now_ts < created_ts:
        raise MixError("clock skew: now_ts precedes created_ts")
    age_days = (now_ts - created_ts) / 86400.0
    stale = age_days > cadence_days
    return {"status": "REVIEW" if stale else "OK", "stale": stale,
            "age_days": age_days, "cadence_days": cadence_days}


def lineage_risk(corpus: dict) -> dict:
    """Verdict over the generation history. Fail-closed on empty."""
    if not isinstance(corpus, dict):
        raise MixError("corpus: dict required")
    gens = corpus.get("generations", [])
    if not isinstance(gens, list):
        raise MixError("corpus.generations: list required")
    if not gens:
        return {"verdict": "INSUFFICIENT", "reason": "no generations logged",
                "generations": 0, "sealed": 0, "legacy": 0}
    for gen in gens:
        if not isinstance(gen, dict):
            raise MixError("every generation must be a dict")
        for key in ("gen", "real_rows", "synth_rows", "alpha",
                    "manifest_ids"):
            if key not in gen:
                raise MixError(f"generation missing key {key!r} "
                               f"(corrupt history?)")
        for key in ("real_rows", "synth_rows"):
            value = gen[key]
            if isinstance(value, bool) or not isinstance(value, int):
                raise MixError(f"generation {key} must be an int, got "
                               f"{value!r} (corrupt history?)")
        alpha = gen["alpha"]
        if (isinstance(alpha, bool)
                or not isinstance(alpha, (int, float))):
            raise MixError(f"generation alpha must be a number, got "
                           f"{alpha!r} (corrupt history?)")
        if not isinstance(gen["manifest_ids"], list):
            raise MixError("generation manifest_ids must be a list "
                           "(corrupt history?)")
    counts = _verify_seals(gens)
    replace_events = []
    saw_real = False
    for gen in gens:
        if gen["real_rows"] > 0:
            saw_real = True
        elif saw_real and gen["synth_rows"] > 0:
            replace_events.append(gen["gen"])
    latest = gens[-1]
    if latest["real_rows"] == 0 and latest["synth_rows"] > 0:
        verdict = "SYNTHETIC_ONLY"
    elif replace_events:
        verdict = "REPLACE_DETECTED"
    else:
        verdict = "ACCUMULATE"
    return {"verdict": verdict,
            "generations": len(gens),
            "alpha_now": latest["alpha"],
            "alpha_trend": [g["alpha"] for g in gens],
            "replace_events": replace_events,
            "latest_manifests": latest["manifest_ids"],
            "sealed": counts["sealed"], "legacy": counts["legacy"]}
