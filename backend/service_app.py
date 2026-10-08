"""Night-shift API router: provenance, PAR, panel, release, pilots, transfer.

Mounts into the mirror FastAPI app (backend/api.py) under /api/v2 with:
    from backend.service_app import router as night_router
    app.include_router(night_router)
Zero collision with mirror routes by construction (new prefix). All
handlers translate engine ValueErrors to 422 JSON; unexpected errors to
500 without stack traces (via the mirror perimeter, with request
ids). Caveat: store infra faults (disk-full etc.) arrive as
StoreError, a ValueError, so the mirror ValueError handler renders
them 422 {"detail"} instead of 500. Message stays truthful; status
is approximate on that one path. Store is a lazy singleton (file
layout by default, Mongo when MONGO_URL is set).
"""

import datetime
import functools
import inspect
import sys
import threading
import traceback
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))

from engine import InputError as _InputError
from engine import canonical_hash

from backend.persist.filelayout import StoreError as _StoreError
from backend.persist.filelayout import validate_id as _check_id

router = APIRouter(prefix="/api/v2", tags=["night"])

_STORE = None
_SERVICE_LOCK = threading.RLock()


def get_store():
    """Lazy singleton store (persist.open_store factory)."""
    global _STORE
    if _STORE is None:
        from backend.persist import open_store
        _STORE = open_store()
    return _STORE


def _unprocessable(exc: Exception) -> HTTPException:
    """Stable 422 body: the CALLER's input was wrong."""
    return HTTPException(status_code=422, detail={"error": "input",
                                                 "message": str(exc)})


def _not_found(kind: str, ident: str) -> HTTPException:
    return HTTPException(status_code=404,
                         detail={"error": "not_found",
                                 "message": f"unknown {kind}: {ident}"})


def _internal(exc: Exception) -> HTTPException:
    """Stable 500 body: WE are broken. Traceback to the log only."""
    error_id = uuid.uuid4().hex[:8]
    traceback.print_exc()
    print(f"[verification] internal error {error_id}: {exc!r}",
          file=sys.stderr)
    return HTTPException(status_code=500,
                         detail={"error": "internal",
                                 "error_id": error_id})


def _guarded(func):
    """Outer error boundary for every handler (422 vs 500).

    InputError/_StoreError -> 422; HTTPException passes through;
    anything else -> logged traceback + safe 500 (no leak).
    functools.wraps preserves the signature for FastAPI.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            with _SERVICE_LOCK:
                return func(*args, **kwargs)
        except HTTPException:
            raise
        except (_InputError, _StoreError) as exc:
            raise _unprocessable(exc)
        except Exception as exc:
            raise _internal(exc)
    return wrapper


def _bind(fn, body, required: tuple, where: str) -> None:
    """Validate a **body call: object, required keys, no extras."""
    if not isinstance(body, dict):
        raise _unprocessable(f"{where}: JSON object required")
    missing = [key for key in required if key not in body]
    if missing:
        raise _unprocessable(f"{where}: missing keys {missing}")
    try:
        inspect.signature(fn).bind(**body)
    except TypeError as exc:
        raise _unprocessable(f"{where}: {exc}")


def _need_id(value: str, where: str) -> str:
    """Route-level id choke: attack strings become 422, never a path."""
    try:
        return _check_id(value)
    except _StoreError as exc:
        raise _unprocessable(f"{where}: {exc}")


def _stored_doc(found, kind: str, ident: str) -> dict:
    doc = found.get("doc") if isinstance(found, dict) else None
    if not isinstance(doc, dict):
        raise _unprocessable(f"stored {kind} {ident!r} is corrupt")
    return doc


def _pilot_id(body: dict) -> str:
    return "pilot_" + canonical_hash(body)[:12]


@router.post("/runs/evaluate")
@_guarded
def runs_evaluate(body: dict):
    """Score one intended/observed pair and persist it as a run."""
    from backend.eval.score_trace import score_trace
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    try:
        card = score_trace(
            body.get("intended"),
            body.get("observed"),
            profile=body.get("profile") or "draft-0",
            seed=body.get("seed", 0),
            evidence_prefix=body.get("evidence_prefix", "ev://runs/"),
            threshold=body.get("threshold", 0.5),
            breach_run=body.get("breach_run", 3),
        )
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)
    policy_id = body.get("policy_id") or "unregistered"
    run_id = "run_" + canonical_hash({"card": card, "policy": policy_id})[:12]
    get_store().save("runs", run_id, {"scorecard": card, "policy_id": policy_id})
    return {"run_id": run_id, "verdict": card["payload"]["verdict"], "scorecard": card}


@router.get("/ui/release/{run_id}")
@_guarded
def ui_release(run_id: str, compare: str | None = None) -> dict:
    """Render-ready release view-model for one run (thin-UI feed)."""
    from backend.eval.viewmodel import build_release_view
    _need_id(run_id, "run_id")
    found = get_store().get("runs", run_id)
    if not found:
        raise _not_found("run", run_id)
    run = _stored_doc(found, "run", run_id)
    other = None
    if compare is not None:
        _need_id(compare, "compare")
        cfound = get_store().get("runs", compare)
        if not cfound:
            raise _not_found("run", compare)
        other = _stored_doc(cfound, "run", compare)
    try:
        return build_release_view(run, run_id, compare=other,
                                  compare_id=compare,
                                  dossier=_dossier_for(run_id))
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


def _dossier_for(run_id: str):
    """Latest stored dossier containing run_id, or None."""
    store = get_store()
    best, best_ts = None, ""
    for did in store.list_ids("dossiers"):
        found = store.get("dossiers", did)
        if not found or not isinstance(found.get("doc"), dict):
            continue
        runs = found["doc"].get("runs")
        if not isinstance(runs, list) or run_id not in runs:
            continue
        stamp = found.get("stored_at") or ""
        if best is None or stamp >= best_ts:
            best, best_ts = found["doc"], stamp
    return best


@router.get("/runs/{run_id}")
@_guarded
def runs_get(run_id):
    _need_id(run_id, "run_id")
    found = get_store().get("runs", run_id)
    if not found:
        raise _not_found("run", run_id)
    doc = _stored_doc(found, "run", run_id)
    return {"run_id": run_id, "doc": doc,
            "stored_at": found.get("stored_at")}


@router.get("/runs")
@_guarded
def list_runs() -> dict:
    """List stored run ids (console history)."""
    return {"run_ids": get_store().list_ids("runs")}


@router.get("/dossiers")
@_guarded
def list_dossiers() -> dict:
    """List compiled dossier ids (console history)."""
    return {"dossier_ids": get_store().list_ids("dossiers")}


@router.get("/dossiers/{dossier_id}")
@_guarded
def dossiers_get(dossier_id: str) -> dict:
    """Fetch one compiled dossier envelope or 404."""
    _need_id(dossier_id, "dossier_id")
    found = get_store().get("dossiers", dossier_id)
    if not found:
        raise _not_found("dossier", dossier_id)
    return found


@router.post("/dossiers/compile")
@_guarded
def dossiers_compile(body: dict):
    """Compile stored runs into a sealed Policy Assurance Record."""
    from engine.ledger import append as ledger_append
    from engine.par import build_par
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    run_ids = body.get("run_ids") or []
    if not run_ids:
        raise _unprocessable("run_ids must be a non-empty list")
    store = get_store()
    runs = []
    for rid in run_ids:
        _need_id(rid, "run_ids[]")
        found = store.get("runs", rid)
        if not found:
            raise _not_found("run", rid)
        runs.append(_stored_doc(found, "run", rid))
    try:
        latest = runs[-1]["scorecard"]
        _PAR_VERDICTS = ("PASS", "REVIEW", "BLOCKED", "INSUFFICIENT")
        gates = []
        for g in latest["payload"]["gates"]:
            if g["status"] not in _PAR_VERDICTS:
                raise _unprocessable(
                    f"gate {g['gate']!r}: status {g['status']!r} "
                    f"outside {_PAR_VERDICTS}")
            gates.append({"id": g["gate"], "verdict": g["status"],
                          "measurement": g.get("measurement"),
                          "evidence": g.get("evidence")})
    except (KeyError, TypeError) as exc:
        raise _unprocessable(f"stored run is corrupt: {exc}")
    release = body.get("release") or {}
    if not isinstance(release, dict):
        raise _unprocessable("release: object required")
    release.setdefault("parent", "sha256:" + "0" * 64)
    release.setdefault("delta", "UNASSESSED")
    weights = body.get("weights") or ("sha256:" + "0" * 64)
    policy = {"id": runs[-1].get("policy_id", "unregistered"), "weights": weights}
    independence = body.get("independence")
    if not isinstance(independence, dict):
        raise _unprocessable("independence register is required")
    odd = body.get("odd")
    if not isinstance(odd, str) or not odd.strip() or len(odd) > 2000:
        raise _unprocessable("odd: non-empty operating-envelope string "
                             "(<=2000 chars) required")
    worksheet = body.get("worksheet")
    if worksheet is not None and not isinstance(worksheet, dict):
        raise _unprocessable("worksheet: object or omitted required")
    try:
        chain = store.read_ledger()
    except (OSError, ValueError) as exc:
        raise _unprocessable(f"stored ledger is corrupt: {exc}")
    try:
        head = chain[-1]["hash"] if chain else "0" * 64
    except (KeyError, TypeError, IndexError) as exc:
        raise _unprocessable(f"ledger head unreadable: {exc} "
                             f"(run ledger/verify)")
    try:
        par = build_par(policy=policy, release=release, gates=gates,
                         ledger_head=head, independence=independence,
                         odd=odd)
    except _InputError as exc:
        raise _unprocessable(exc)
    stamp = body.get("timestamp") or datetime.datetime.now(datetime.timezone.utc).isoformat()
    entry = ledger_append(chain, "RUN_SEALED", {"par_hash": par["par_hash"], "runs": run_ids}, stamp)
    store.append_ledger(entry)
    dossier_id = "dos_" + canonical_hash({"par": par["par_hash"], "runs": run_ids})[:12]
    store.save("dossiers", dossier_id, {"par": par, "runs": run_ids, "ledger_index": entry["index"], "worksheet": worksheet})
    return {"dossier_id": dossier_id, "par": par, "ledger_index": entry["index"]}


@router.post("/ledger/verify")
@_guarded
def ledger_verify():
    """Re-verify the full hash chain from the active store."""
    from engine.ledger import verify
    try:
        chain = get_store().read_ledger()
    except (OSError, ValueError) as exc:
        return {"ok": False, "first_bad": None,
                "reason": f"ledger unreadable: {exc}"}
    return verify(chain)


@router.get("/governance")
@_guarded
def governance() -> dict:
    """V2-fixed governance snapshot: clock, routes, honesty state."""
    today = datetime.date.today()
    deadline = datetime.date(2027, 1, 20)
    return {
        "eu_machinery_reg": "2023/1230",
        "eu_deadline": deadline.isoformat(),
        "days_left": (deadline - today).days,
        "part_a_route": "Annex I Part A items 5 and 6 (ML safety route)",
        "ota_rule": "Safety-shifting OTA update routes to "
                    "substantial-modification review",
        "ai_act_rows": "Reference mappings (Omnibus 2026/1744 fold)",
        "iso_25785_1": "Unpublished draft: placeholder rows only",
        "thresholds": "DRAFT",
        "disclaimer": "Not legal advice. Human and legal review required.",
    }


@router.post("/pilots")
@_guarded
def create_pilot(body: dict[str, Any]) -> dict:
    """Intake a pilot request. Deterministic id (idempotent re-posts)."""
    if not isinstance(body, dict):
        raise _unprocessable(ValueError("JSON object required"))
    for key in ("name", "org", "email", "robot", "failure_mode"):
        value = body.get(key)
        if not value or not isinstance(value, str):
            raise _unprocessable(
                ValueError(f"{key}: non-empty string required"))
    if "@" not in body["email"] or " " in body["email"]:
        raise _unprocessable(ValueError("email: must look like an email"))
    clean = {k: body[k] for k in
             ("name", "org", "email", "robot", "failure_mode")}
    clean["notes"] = body.get("notes", "")
    pilot_id = _pilot_id(clean)
    get_store().save("pilots", pilot_id, {**clean, "status": "RECEIVED"})
    return {"pilot_id": pilot_id, "status": "RECEIVED"}


@router.get("/pilots")
@_guarded
def list_pilots() -> dict:
    """List pilot request ids (newest last; store order is alpha)."""
    return {"pilot_ids": get_store().list_ids("pilots")}


@router.get("/pilots/{pilot_id}")
@_guarded
def get_pilot(pilot_id: str) -> dict:
    """Fetch one pilot request envelope or 404."""
    _need_id(pilot_id, "pilot_id")
    found = get_store().get("pilots", pilot_id)
    if not found:
        raise _not_found("pilot", pilot_id)
    return found


@router.post("/provenance/batches")
@_guarded
def stamp_batch_route(body: dict[str, Any]) -> dict:
    """Stamp a generation-level batch manifest and persist it."""
    from backend.provenance.manifest import stamp_batch
    _bind(stamp_batch, body,
          ("generator", "seed", "content_hash", "n_rows", "ingredients"),
          "provenance/batches")
    try:
        manifest = stamp_batch(**body)
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)
    get_store().save("manifests", manifest["manifest_id"], manifest)
    return manifest


@router.post("/provenance/bridge")
@_guarded
def bridge_route(body: dict[str, Any]) -> dict:
    """Wrap an axiom generation: manifest + mix batch + datacard merge."""
    from backend.provenance.axiom_bridge import bridge_generation
    _bind(bridge_generation, body,
          ("generator_name", "generator_version", "seed", "n_rows",
           "content_hash", "real_ingredients"),
          "provenance/bridge")
    try:
        out = bridge_generation(**body)
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)
    manifest = out["manifest"]
    get_store().save("manifests", manifest["manifest_id"], manifest)
    return out


@router.post("/provenance/sentinels")
@_guarded
def sentinels_route(body: dict[str, Any]) -> dict:
    """Run collapse sentinels over baseline/current column maps."""
    from backend.provenance.sentinels import collapse_report
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    if not isinstance(body.get("thresholds", {}), dict):
        raise _unprocessable("thresholds: object required")
    try:
        return collapse_report(body.get("baseline"), body.get("current"),
                               **body.get("thresholds", {}))
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.post("/provenance/corpora")
@_guarded
def create_corpus(body: dict[str, Any]) -> dict:
    """Open a mix-ledger corpus."""
    from backend.provenance.mixtrack import new_corpus
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    try:
        corpus = new_corpus(body.get("corpus_id", ""))
    except _InputError as exc:
        raise _unprocessable(exc)
    _need_id(corpus["corpus_id"], "corpus_id")
    get_store().save("corpora", corpus["corpus_id"], corpus)
    return corpus


@router.post("/provenance/corpora/{corpus_id}/generations")
@_guarded
def add_generation_route(corpus_id: str, body: dict[str, Any]) -> dict:
    """Append one generation to a corpus mix ledger."""
    from backend.provenance.mixtrack import add_generation
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    _need_id(corpus_id, "corpus_id")
    found = get_store().get("corpora", corpus_id)
    if not found:
        raise _not_found("corpora", corpus_id)
    corpus = _stored_doc(found, "corpora", corpus_id)
    try:
        record = add_generation(corpus, real_rows=body.get("real_rows"),
                                synth_batches=body.get("synth_batches", []))
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)
    get_store().save("corpora", corpus_id, corpus)
    return record


@router.get("/provenance/corpora/{corpus_id}/risk")
@_guarded
def corpus_risk(corpus_id: str) -> dict:
    """Accumulate/replace/synthetic-only verdict over a corpus."""
    from backend.provenance.mixtrack import lineage_risk
    _need_id(corpus_id, "corpus_id")
    found = get_store().get("corpora", corpus_id)
    if not found:
        raise _not_found("corpora", corpus_id)
    try:
        return lineage_risk(_stored_doc(found, "corpora", corpus_id))
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.post("/par/build")
@_guarded
def par_build(body: dict[str, Any]) -> dict:
    """Build + hash a Policy Assurance Record."""
    from engine.par import build_par
    _bind(build_par, body,
          ("policy", "release", "gates", "ledger_head", "independence",
           "odd"),
          "par/build")
    try:
        return build_par(**body)
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.post("/par/validate")
@_guarded
def par_validate(body: dict[str, Any]) -> dict:
    """Recompute + structural check of a PAR envelope."""
    from engine.par import validate_par
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    try:
        return validate_par(body.get("envelope", body))
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.post("/par/read")
@_guarded
def par_read(body: dict[str, Any]) -> dict:
    """Offline-reader rendering of a PAR envelope."""
    from engine.par import read_par
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    try:
        return read_par(body.get("envelope", body))
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.post("/eval/capsule/seal")
@_guarded
def capsule_seal(body: dict[str, Any]) -> dict:
    """Seal a replay capsule: request+envelope+mode under a track hash."""
    from backend.eval.capsule import seal_capsule
    return seal_capsule(body)


@router.post("/eval/capsule/verify")
@_guarded
def capsule_verify(body: dict[str, Any]) -> dict:
    """Verify a replay capsule: recompute the track hash, report."""
    from backend.eval.capsule import verify_capsule
    return verify_capsule(body)


@router.post("/worksheet/record")
@_guarded
def worksheet_record(body: dict[str, Any]) -> dict:
    """Record an applicability worksheet (routes implied, never decided)."""
    from engine.worksheet import record
    _bind(record, body,
          ("product", "analyst", "ml_safety_function", "self_evolving",
           "frozen_weight_ota"),
          "worksheet/record")
    try:
        return record(**body)
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.post("/panel/commit")
@_guarded
def panel_commit(body: dict[str, Any]) -> dict:
    """Commit a held-out panel (ledger BEFORE scoring)."""
    from engine.panel import commit
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    try:
        return commit(body.get("seed"), body.get("case_count"))
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.post("/panel/reveal")
@_guarded
def panel_reveal(body: dict[str, Any]) -> dict:
    """Verify a panel reveal against its commitment."""
    from engine.panel import reveal
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    try:
        return reveal(body.get("commitment"), body.get("seed"),
                      body.get("case_count"))
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.post("/releases/compare")
@_guarded
def release_compare(body: dict[str, Any]) -> dict:
    """Parent/child release compare with mod flag."""
    from engine.release import compare
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    try:
        return compare(body.get("parent_gates"), body.get("child_gates"),
                       parent_weights_hash=body.get("parent_weights_hash"),
                       child_weights_hash=body.get("child_weights_hash"),
                       tolerances=body.get("tolerances"))
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.post("/eval/score")
@_guarded
def eval_score(body: dict[str, Any]) -> dict:
    """Score one intended/observed trace pair into a pinned scorecard."""
    from backend.eval.score_trace import score_trace
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    try:
        return score_trace(body.get("intended"), body.get("observed"),
                           profile=body.get("profile", "draft-0"),
                           seed=body.get("seed", 0),
                           evidence_prefix=body.get("evidence_prefix",
                                                    "trace"),
                           threshold=body.get("threshold", 0.5),
                           breach_run=body.get("breach_run", 3))
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.post("/eval/transfer")
@_guarded
def eval_transfer(body: dict[str, Any]) -> dict:
    """Cross-embodiment transfer report (refuses joint-space)."""
    from backend.eval.xembodiment import transfer_report
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    try:
        return transfer_report(body.get("card_a"), body.get("trace_a"),
                               body.get("card_b"), body.get("trace_b"),
                               threshold=body.get("threshold", 0.1))
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


_SERVICE_HUNT_CAP = 200


def _hunt_cap(body: dict) -> int:
    cap = body.get("trial_cap", 16)
    if isinstance(cap, bool) or not isinstance(cap, int):
        raise _unprocessable(ValueError("trial_cap: int required"))
    if cap < 1 or cap > _SERVICE_HUNT_CAP:
        raise _unprocessable(
            ValueError(f"trial_cap: 1..{_SERVICE_HUNT_CAP} over HTTP "
                       f"(bigger hunts run in-process)"))
    return cap


def _search_fn(body: dict):
    from engine.hunt import grid_search, random_search
    method = body.get("method", "grid")
    if method not in ("grid", "random"):
        raise _unprocessable(ValueError("method: 'grid'|'random'"))
    return grid_search if method == "grid" else random_search


@router.post("/eval/failure-modes")
@_guarded
def eval_failure_modes(body: dict[str, Any]) -> dict:
    """FM1 drift + FM2 executability proxy + FM5 sim-real gap.

    FM3 (hallucination) and FM4 (marginalization) need model
    callables and stay library-only by design (callables cannot
    cross HTTP honestly).
    """
    from backend.eval.failure_modes import drift_gate, executability_proxy, sim_real_gap
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    raw_bounds = body.get("bounds", [-2.0, 2.0])
    if (not isinstance(raw_bounds, (list, tuple))
            or len(raw_bounds) != 2):
        raise _unprocessable("bounds: [lo, hi] pair required")
    try:
        fm1 = drift_gate(body.get("intended"), body.get("observed"),
                         threshold=body.get("threshold", 0.5),
                         breach_run=body.get("breach_run", 3))
        fm2 = executability_proxy(body.get("observed"),
                                  bounds=tuple(raw_bounds))
        fm5 = sim_real_gap(body.get("intended"), body.get("observed"))
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)
    return {"fm1_drift": fm1, "fm2_executability_proxy": fm2,
            "fm5_sim_real_gap": fm5,
            "note": "FM3/FM4 need model callables; library-only"}


@router.post("/eval/hunt")
@_guarded
def eval_hunt(body: dict[str, Any]) -> dict:
    """Seeded M4 falsification hunt over a fixture policy."""
    from backend.eval.hunt_backends import FixtureBackend
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    search = _search_fn(body)
    cap = _hunt_cap(body)
    space = (body.get("space")
             or {"noise_scale": [0.5, 1.0, 2.0], "bias": [0.0, 0.5]})
    try:
        backend = FixtureBackend(
            body.get("policy", "playback"),
            horizon=body.get("horizon", 120),
            seed=body.get("seed", 1),
            threshold=body.get("threshold", 0.5))
        return search(backend, space, seed=body.get("seed", 1),
                      trial_cap=cap)
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.post("/eval/redteam")
@_guarded
def eval_redteam(body: dict[str, Any]) -> dict:
    """FR-36 hunt aimed at OUR scorer (preset sane|broken)."""
    from backend.eval.hunt_backends import RedTeamBackend, fixture_policies, get_score_preset
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    search = _search_fn(body)
    cap = _hunt_cap(body)
    try:
        policies = fixture_policies(
            body.get("policies")
            or [{"id": "clean", "must_block": False},
                {"id": "playback", "must_block": True}])
        score_fn = get_score_preset(body.get("score_fn", "sane"))
        backend = RedTeamBackend(
            policies, score_fn, horizon=body.get("horizon", 120),
            seed=body.get("seed", 1),
            n_seeds=body.get("n_seeds", 3))
        space = (body.get("space")
                 or {"policy_idx": list(range(len(policies))),
                     "noise_scale": [1.0]})
        return search(backend, space, seed=body.get("seed", 1),
                      trial_cap=cap)
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.post("/eval/hunt/summarize")
@_guarded
def eval_hunt_summarize(body: dict[str, Any]) -> dict:
    """Summarize + seal a hunt catalogue (replayable record)."""
    from engine.hunt import seal_trials, summarize
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    try:
        catalogue = body.get("catalogue")
        sealed = seal_trials(catalogue)
        return {"summary": summarize(catalogue), "sealed": sealed}
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.post("/eval/envelope")
@_guarded
def eval_envelope(body: dict[str, Any]) -> dict:
    """Marginal break/hold boundary map from hunt trials."""
    from backend.eval.envelope import infer_envelope
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    try:
        return infer_envelope(body.get("trials"),
                              param_names=body.get("param_names"))
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.post("/eval/briefing")
@_guarded
def eval_briefing(body: dict[str, Any]) -> dict:
    """Notified-Body briefing view over a PAR (+ worksheet/cards)."""
    from backend.eval.briefing import briefing_view
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    try:
        return briefing_view(body.get("par_envelope"),
                             worksheet=body.get("worksheet"),
                             cards=body.get("cards"),
                             ledger_verdict=body.get("ledger_verdict"),
                             vault=body.get("vault"))
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.post("/eval/contracts/check")
@_guarded
def eval_contract_check(body: dict[str, Any]) -> dict:
    """Check a preset skill contract (grasp|release) on states."""
    from backend.eval.skill_contracts import check_skill, get_preset_contract
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    try:
        contract = get_preset_contract(body.get("contract_id"))
        return check_skill(contract, body.get("states"))
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.post("/eval/task-graph")
@_guarded
def eval_task_graph(body: dict[str, Any]) -> dict:
    """Validate a task DAG; deterministic order + PAR chain."""
    from backend.eval.skill_contracts import ingest_task_graph
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    try:
        return ingest_task_graph(body.get("graph"))
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.post("/eval/rank")
@_guarded
def eval_rank(body: dict[str, Any]) -> dict:
    """FR-6 worst-first policy ranking for triage."""
    from engine.scorer import rank_policies
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    try:
        return rank_policies(body.get("entries"))
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.post("/eval/credibility")
@_guarded
def eval_credibility(body: dict[str, Any]) -> dict:
    """FR-32 DRAFT-lift gate over a credibility card envelope."""
    from engine.credibility import can_lift_draft
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    try:
        return can_lift_draft(body.get("card_envelope"),
                              min_n=body.get("min_n", 30),
                              max_fp_rate=body.get("max_fp_rate", 0.05),
                              require_bins=body.get("require_bins", True))
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.post("/eval/bounded")
@_guarded
def eval_bounded(body: dict[str, Any]) -> dict:
    """M3 slice-1 affine/ReLU bound check: PROVEN/VIOLATED/UNKNOWN."""
    from engine.bounded import verify_affine_relu
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    try:
        return verify_affine_relu(
            body.get("layers"), body.get("input_box"),
            body.get("output_bounds"),
            grid_per_dim=body.get("grid_per_dim", 5),
            model_hash=body.get("model_hash"))
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.post("/eval/property")
@_guarded
def eval_property(body: dict[str, Any]) -> dict:
    """G9 property-margin check with a named predicate preset."""
    from engine.property import check_property, get_predicate
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    spec = body.get("spec")
    if not isinstance(spec, dict):
        raise _unprocessable(ValueError("spec: dict required"))
    try:
        resolved = get_predicate(spec.get("predicate"))
        full_spec = dict(spec)
        full_spec["predicate"] = resolved["fn"]
        full_spec.setdefault("version", resolved["version"])
        return check_property(
            full_spec, body.get("trace"),
            state_origin=body.get("state_origin", "measured"))
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.post("/adapters/ingest")
@_guarded
def adapters_ingest(body: dict[str, Any]) -> dict:
    """Parse one external eval document (STUBs refuse loudly)."""
    from backend.adapters.ingest import get_adapter
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    doc = body.get("document")
    try:
        return get_adapter(body.get("harness")).parse(doc)
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)


@router.get("/adapters/status")
@_guarded
def adapters_status() -> dict:
    """Machine-readable adapter board (STUB/DERIVED/VERIFIED)."""
    from backend.adapters.ingest import conformance_report
    return conformance_report()


@router.post("/provenance/duplicates")
@_guarded
def duplicates_route(body: dict[str, Any]) -> dict:
    """Exact or SimHash near-duplicate rate over rows."""
    from backend.provenance.duplicates import exact_dup_rate, near_dup_rate
    if not isinstance(body, dict):
        raise _unprocessable("body must be a JSON object")
    mode = body.get("mode", "near")
    if mode not in ("exact", "near"):
        raise _unprocessable(ValueError("mode: 'exact'|'near'"))
    try:
        if mode == "exact":
            return exact_dup_rate(body.get("rows"))
        return near_dup_rate(body.get("rows"),
                             resolution=body.get("resolution", 0.01),
                             hamming=body.get("hamming", 3))
    except (_InputError, _StoreError) as exc:
        raise _unprocessable(exc)
