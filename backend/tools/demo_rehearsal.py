"""Demo rehearsal: dry-run the stakeholder path over HTTP.

Usage (backend booted, from hi bro/meta bro):
  python backend/tools/demo_rehearsal.py --base http://127.0.0.1:8000
  python backend/tools/demo_rehearsal.py --base ... --fast
  python backend/tools/demo_rehearsal.py --base ... --record demo_recording

Steps: local golden-hash check (no server), then over HTTP: overview,
clean vs drifty (golden verdict + envelope hash), playback
(executability breach => BLOCKED + hash), hunt + exactly-equal
replay hashes, joint-space 422 refusal, PAR compile + LOCAL
offline verify
+ one-byte tamper that must FAIL, ledger verify, briefing view.
Golden traces are rebuilt locally (policy_fixtures, fixed seeds) and
sent through runs/evaluate, so verdict AND envelope hash must match
tests/golden/stories.json exactly. Prints a PASS/FAIL table with
timings; exit 0 only if every step passes. --record keeps every
response as JSON (offline fallback if the live server dies).
Stdlib only (urllib via smoke_live.http_call).
"""

import argparse
import copy
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "packages"))

from engine import canonical_hash  # noqa: E402
from engine.par import validate_par  # noqa: E402

from backend.eval import policy_fixtures as fixtures  # noqa: E402
from backend.tools.golden_lib import STORIES, build_all, hashes_of  # noqa: E402
from backend.tools.presets import base_context  # noqa: E402
from backend.tools.presets import load as load_presets  # noqa: E402
from backend.tools.smoke_live import http_call  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
GOLDEN_PATH = os.path.join(BASE_DIR, "tests", "golden", "stories.json")
HORIZON = 32
SLEEP_SECS = 1.0
ODD = "rehearsal cell, 2D reacher, supervised"
INDEPENDENCE = {"builder": "rehearsal", "funder": "rehearsal",
                "relationship": "none"}


def story_inputs(policy, seed):
    """Golden-identical runs/evaluate body for one fixture story."""
    intended = fixtures.reference_actions(horizon=HORIZON)
    rollout = fixtures.get_policy(policy)["fn"]
    observed = rollout(intended, seed=seed, noise_scale=1.0)
    return {"intended": intended, "observed": observed,
            "profile": "draft-0", "seed": seed,
            "evidence_prefix": "golden", "threshold": 0.5,
            "breach_run": 3, "policy_id": f"golden-{policy}"}


def load_goldens(path=GOLDEN_PATH):
    """Committed golden hashes + engine version (shape-checked)."""
    try:
        with open(path, encoding="utf-8") as handle:
            goldens = json.load(handle)
        stories = goldens["stories"]
        for policy, _ in STORIES:
            record = stories[policy]
            record["verdict"]
            record["scorecard_envelope"]
        goldens["engine_version"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"golden file unusable ({path}): {exc}")
    return goldens


def step_local_goldens():
    """Rebuild the pipeline locally; every hash must match goldens."""
    expected = load_goldens()
    if expected.get("engine_version") != build_all()["engine_version"]:
        return ("local-goldens", False, "engine_version drift",
                {"expected": expected.get("engine_version")})
    built = build_all()["stories"]
    bad = [s for s, seed in STORIES
           if hashes_of(built[s]) != expected["stories"][s]]
    if bad:
        return ("local-goldens", False,
                "hash drift: " + ",".join(bad), {"bad": bad})
    return ("local-goldens", True, "4/4 stories match",
            {"stories": sorted(hashes_of(built[s])["verdict"]
                               for s, _ in STORIES)})


def _call(base, method, path, body, call_fn):
    status, data, ms, err = call_fn(base, method, path, body)
    if err is not None:
        return None, {}, ms, f"transport: {err}"
    return status, data if isinstance(data, dict) else {}, ms, ""


def step_overview(base, call_fn):
    status, data, ms, err = _call(base, "GET", "api/v2/governance",
                                  None, call_fn)
    if err or status != 200:
        return ("overview", False, err or f"HTTP {status}",
                {"ms": ms}, None)
    lstatus, ldata, lms, lerr = _call(base, "GET", "api/v2/runs",
                                      None, call_fn)
    if lerr or lstatus != 200:
        return ("overview", False, lerr or f"runs HTTP {lstatus}",
                {"ms": ms + lms}, None)
    detail = f"days_left={data.get('days_left')} runs={ldata}"
    return ("overview", True, detail,
            {"governance": data, "runs": ldata}, None)


def step_story(base, call_fn, policy, seed, goldens):
    """One golden story over HTTP: verdict + envelope hash must match."""
    body = story_inputs(policy, seed)
    status, data, ms, err = _call(base, "POST", "api/v2/runs/evaluate",
                                  body, call_fn)
    record = {"request_seed": seed}
    if err or status != 200:
        return (policy, False, err or f"HTTP {status}",
                record, None)
    card = data.get("scorecard") or {}
    payload = card.get("payload") or {}
    want = goldens["stories"][policy]
    ok_v = payload.get("verdict") == want["verdict"]
    ok_h = card.get("envelope_hash") == want["scorecard_envelope"]
    record["run_id"] = data.get("run_id")
    record["verdict"] = payload.get("verdict")
    record["envelope_hash"] = card.get("envelope_hash")
    detail = (f"verdict={record['verdict']}(want {want['verdict']}) "
              f"hash={'match' if ok_h else 'MISMATCH'}")
    return (policy, bool(ok_v and ok_h), detail, record,
            data.get("run_id"))


def step_hunt_replay(base, call_fn):
    status, first, ms1, err = _call(base, "POST", "api/v2/eval/hunt",
                                    {}, call_fn)
    if err or status != 200:
        return ("hunt-replay", False, err or f"HTTP {status}",
                {"ms": ms1})
    status2, second, ms2, err2 = _call(base, "POST", "api/v2/eval/hunt",
                                       {}, call_fn)
    if err2 or status2 != 200:
        return ("hunt-replay", False, err2 or f"replay HTTP {status2}",
                {"ms": ms1 + ms2})
    breaks = first.get("breaks")
    if not isinstance(breaks, list) or not breaks:
        return ("hunt-replay", False, "no breaks found",
                {"first": first})
    same = canonical_hash(first) == canonical_hash(second)
    detail = (f"breaks={len(breaks)} "
              f"replay={'identical' if same else 'DIFFERS'}")
    return ("hunt-replay", same, detail,
            {"breaks": len(breaks), "hash": canonical_hash(first)})


def step_joint_refusal(base, call_fn, constants):
    ctx = base_context(constants)
    body = {"card_a": ctx["JOINT"], "trace_a": ctx["TRACE3"],
            "card_b": ctx["ARM"], "trace_b": ctx["TRACE3"],
            "threshold": 0.1}
    status, data, ms, err = _call(base, "POST", "api/v2/eval/transfer",
                                  body, call_fn)
    if err:
        return ("joint-refusal", False, err, {"ms": ms})
    detail = data.get("detail") if isinstance(data, dict) else None
    tagged = isinstance(detail, dict) and detail.get("error") == "input"
    ok = status == 422 and tagged
    return ("joint-refusal", ok,
            f"HTTP {status} error=input" if ok
            else f"HTTP {status} (want 422 input)",
            {"status": status, "tagged": tagged})


def step_par_offline_tamper(base, call_fn, run_id):
    if not run_id:
        return ("par-tamper", False, "no run_id from clean step",
                {}, None)
    body = {"run_ids": [run_id], "independence": INDEPENDENCE,
            "odd": ODD}
    status, data, ms, err = _call(base, "POST",
                                  "api/v2/dossiers/compile", body,
                                  call_fn)
    if err or status != 200:
        return ("par-tamper", False, err or f"HTTP {status}",
                {"ms": ms}, None)
    envelope = data.get("par")
    check = validate_par(envelope)
    if not check.get("ok"):
        return ("par-tamper", False,
                f"offline verify failed: {check.get('reason')}",
                {"dossier_id": data.get("dossier_id")}, None)
    tampered = copy.deepcopy(envelope)
    tampered["par"]["odd"] = tampered["par"]["odd"] + "X"
    tamper = validate_par(tampered)
    if tamper.get("ok"):
        return ("par-tamper", False, "tampered PAR still verifies",
                {"dossier_id": data.get("dossier_id")}, None)
    lstatus, ldata, lms, lerr = _call(base, "POST",
                                      "api/v2/ledger/verify", {},
                                      call_fn)
    if lerr or lstatus != 200 or not ldata.get("ok"):
        return ("par-tamper", False,
                lerr or f"ledger HTTP {lstatus} ok={ldata.get('ok')}",
                {"dossier_id": data.get("dossier_id")}, None)
    return ("par-tamper", True,
            f"dossier {data.get('dossier_id')} verifies, 1-byte "
            f"tamper fails ({tamper.get('reason')}), ledger ok",
            {"dossier_id": data.get("dossier_id"),
             "par_hash": envelope.get("par_hash"),
             "tamper_reason": tamper.get("reason")},
            envelope)


def step_briefing(base, call_fn, envelope):
    if not envelope:
        return ("briefing", False, "no PAR from compile step", {})
    status, data, ms, err = _call(base, "POST", "api/v2/eval/briefing",
                                  {"par_envelope": envelope}, call_fn)
    if err or status != 200:
        return ("briefing", False, err or f"HTTP {status}",
                {"ms": ms})
    sections = data.get("sections")
    first = (sections or [{}])[0].get("title")
    if first != "Scoping":
        return ("briefing", False,
                f"first section {first!r} (want 'Scoping')",
                {"sections": [s.get("title") for s in sections or []]})
    return ("briefing", True,
            f"{len(sections)} sections, Scoping first",
            {"titles": [s.get("title") for s in sections]})


def run_all(base, call_fn=None, sleep=True, record_dir=None):
    """Run every step. Returns (rows, all_ok). Rows are dicts."""
    call = call_fn or http_call
    constants, _ = load_presets()
    goldens = load_goldens()
    rows = []

    def _record(name, record):
        if not record_dir:
            return
        os.makedirs(record_dir, exist_ok=True)
        path = os.path.join(record_dir, f"{len(rows):02d}_{name}.json")
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
            handle.write("\n")

    def _pause():
        if sleep:
            time.sleep(SLEEP_SECS)

    started = time.perf_counter()
    name, ok, detail, record = step_local_goldens()
    rows.append({"step": name, "ok": ok,
                 "ms": (time.perf_counter() - started) * 1000.0,
                 "detail": detail})
    _record(name, {"ok": ok, "detail": detail, "record": record})

    clean_id = None
    http_steps = [
        ("overview", lambda: step_overview(base, call)[:4] + (None,)),
        ("clean", lambda: step_story(base, call, "clean", 11,
                                     goldens)),
        ("drifty", lambda: step_story(base, call, "drifty", 12,
                                      goldens)),
        ("playback", lambda: step_story(base, call, "playback", 13,
                                        goldens)),
        ("hunt-replay", lambda: step_hunt_replay(base, call) + (None,)),
        ("joint-refusal",
         lambda: step_joint_refusal(base, call, constants) + (None,)),
    ]
    for _label, thunk in http_steps:
        _pause()
        started = time.perf_counter()
        name, ok, detail, record, extra = thunk()
        rows.append({"step": name, "ok": bool(ok),
                     "ms": (time.perf_counter() - started) * 1000.0,
                     "detail": detail})
        _record(name, {"ok": bool(ok), "detail": detail,
                       "record": record})
        if name == "clean":
            clean_id = extra
    _pause()
    started = time.perf_counter()
    name, ok, detail, record, envelope = step_par_offline_tamper(
        base, call, clean_id)
    rows.append({"step": name, "ok": bool(ok),
                 "ms": (time.perf_counter() - started) * 1000.0,
                 "detail": detail})
    _record(name, {"ok": bool(ok), "detail": detail, "record": record})
    _pause()
    started = time.perf_counter()
    name, ok, detail, record = step_briefing(base, call, envelope)
    rows.append({"step": name, "ok": bool(ok),
                 "ms": (time.perf_counter() - started) * 1000.0,
                 "detail": detail})
    _record(name, {"ok": bool(ok), "detail": detail, "record": record})
    return rows, all(r["ok"] for r in rows)


def render(rows):
    """PASS/FAIL table lines."""
    lines = [f"{'STEP':<14}{'RESULT':<8}{'MS':>9}  DETAIL"]
    for row in rows:
        lines.append(f"{row['step']:<14}"
                     f"{'PASS' if row['ok'] else 'FAIL':<8}"
                     f"{row['ms']:>9.1f}  {row['detail']}")
    lines.append("REHEARSAL RESULT: "
                 + ("PASS" if all(r['ok'] for r in rows) else "FAIL"))
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Dry-run the stakeholder demo path over HTTP.")
    parser.add_argument("--base", required=True,
                        help="live backend, e.g. http://127.0.0.1:8000")
    parser.add_argument("--fast", action="store_true",
                        help="skip the 1s pauses between steps")
    parser.add_argument("--record", default=None, metavar="DIR",
                        help="write every step response as JSON into DIR")
    args = parser.parse_args(argv)
    rows, all_ok = run_all(args.base, sleep=not args.fast,
                           record_dir=args.record)
    for line in render(rows):
        print(line)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
