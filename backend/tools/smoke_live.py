"""Live smoke: replay every console preset against a running server.

Usage (from hi bro/meta bro, backend already booted):
  python backend/tools/smoke_live.py --base http://127.0.0.1:8000
  python backend/tools/smoke_live.py --base http://127.0.0.1:8000 \
      --via-proxy http://127.0.0.1:5194/api/play --out triage_report.txt
Exit 0: every call matched its expected status. Exit 1: anything else.
Stdlib only (urllib).
"""

import argparse
import datetime
import json
import os
import platform
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from backend.tools.presets import PresetError, base_context, dig, load, resolve  # noqa: E402

TIMEOUT = 20.0
EXPECT_ROUTES = 42


def _opener():
    # Never use env proxies: localhost calls must not route via a proxy
    # (a proxy env var turns "backend down" into a 20s hang, and breaks
    # Windows machines with corporate proxies set).
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_call(base, method, path, body):
    """Returns (status|None, data, ms, err). err set on transport fail."""
    url = base.rstrip("/") + "/" + path.lstrip("/")
    data = None
    headers = {}
    if method != "GET":
        data = json.dumps(body if body is not None else {}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method=method)
    start = time.monotonic()
    try:
        with _opener().open(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            ms = (time.monotonic() - start) * 1000.0
            try:
                return resp.status, json.loads(raw), ms, None
            except ValueError:
                return resp.status, {"_text": raw[:500]}, ms, None
    except urllib.error.HTTPError as exc:
        ms = (time.monotonic() - start) * 1000.0
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
        try:
            parsed = json.loads(raw) if raw else {}
        except ValueError:
            parsed = {"_text": raw[:500]}
        return exc.code, parsed, ms, None
    except Exception as exc:
        ms = (time.monotonic() - start) * 1000.0
        return None, {}, ms, f"{type(exc).__name__}: {exc}"


def snippet(data):
    try:
        text = json.dumps(data, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        text = repr(data)
    return text[:160]


def check_openapi(base, call_fn=None):
    call = call_fn or http_call
    status, data, _, err = call(base, "GET", "openapi.json", None)
    if err is not None:
        return False, f"unreachable: {err}"
    if status != 200 or not isinstance(data, dict):
        return False, (f"HTTP {status} (docs may be disabled; "
                       f"continuing with preset list)")
    paths = [f"{method} {path}" for path, operations in data.get("paths", {}).items() if path.startswith("/api/v2") for method in operations if method in ("get", "post")]
    if len(paths) != EXPECT_ROUTES:
        return False, (f"{len(paths)} /api/v2 routes in openapi, want "
                       f"{EXPECT_ROUTES}")
    return True, f"{len(paths)} /api/v2 routes in openapi"


def run_chain(base, constants, calls, call_fn=None):
    """Replay calls in order. Returns (results, ctx)."""
    call = call_fn or http_call
    ctx = base_context(constants)
    results = []
    for step in calls:
        cid = step["id"]
        try:
            path = resolve(step["path"], ctx)
            body = resolve(step.get("body"), ctx)
        except PresetError as exc:
            results.append({"id": cid, "ok": False, "status": None,
                            "expect": step["expect"], "ms": 0.0,
                            "detail": f"placeholder: {exc}"})
            continue
        status, data, ms, err = call(base, step["method"], path, body)
        if err is not None:
            results.append({"id": cid, "ok": False, "status": None,
                            "expect": step["expect"], "ms": ms,
                            "detail": f"transport: {err}"})
            continue
        ok = status == step["expect"]
        detail = snippet(data)
        if ok and status == 200 and "save" in step:
            try:
                for name, dotpath in step["save"].items():
                    ctx[name] = dig(data, dotpath)
            except PresetError as exc:
                ok = False
                detail = f"save rule failed: {exc}"
        results.append({"id": cid, "ok": ok, "status": status,
                        "expect": step["expect"], "ms": ms,
                        "detail": detail, "data": data})
    return results, ctx


def classify(result):
    """Exact classification rules for the footer."""
    if result["status"] is None:
        return "BACKEND DOWN or not booted"
    if result["ok"]:
        return "OK"
    status = result["status"]
    if status == 422:
        return "PRESET/PAYLOAD BUG (see body)"
    if status == 500:
        return "BACKEND BUG (see server log)"
    if status == 404:
        return "ROUTE NOT MOUNTED"
    return f"UNEXPECTED HTTP {status} (want {result['expect']})"


def proxy_diff(via_base, constants, calls, direct, call_fn=None, direct_base=None):
    """Re-run via the Next proxy; return divergence lines."""
    call = call_fn or http_call
    lines = []
    by_id = {r["id"]: r for r in direct}
    ctx = base_context(constants)
    for step in calls:
        cid = step["id"]
        try:
            path = resolve(step["path"], ctx)
            body = resolve(step.get("body"), ctx)
        except PresetError:
            continue
        status, data, _, err = call(via_base, step["method"], path,
                                    body)
        if err is not None:
            lines.append(f"PROXY DIVERGENCE {cid}: proxy transport "
                         f"failed: {err} (direct was "
                         f"{by_id[cid]['status']}) -> PROXY BUG")
            continue
        if not isinstance(data, dict) or data.get("up") is not True:
            lines.append(f"PROXY DIVERGENCE {cid}: proxy reports "
                         f"backend down: {snippet(data)} -> PROXY BUG")
            continue
        mine, theirs = by_id[cid], {"status": data.get("status"),
                                    "data": data.get("data")}
        if direct_base and (step["method"] == "GET" or path == "ledger/verify"):
            fresh_status, fresh_data, _, fresh_error = call(direct_base, step["method"], path, body)
            if fresh_error:
                lines.append(f"PROXY DIVERGENCE {cid}: direct read-back failed -> PROXY BUG")
                continue
            mine = {"status": fresh_status, "data": fresh_data}
        elif direct_base and path == "dossiers/compile" and theirs["status"] == 200:
            from engine.par import validate_par
            artifact = theirs["data"]
            identifier = artifact.get("dossier_id") if isinstance(artifact, dict) else None
            if not identifier or not validate_par(artifact.get("par"))["ok"]:
                lines.append(f"PROXY DIVERGENCE {cid}: returned dossier integrity failed -> PROXY BUG")
                continue
            saved_status, saved, _, saved_error = call(direct_base, "GET", f"dossiers/{identifier}", None)
            if saved_error or saved_status != 200:
                lines.append(f"PROXY DIVERGENCE {cid}: dossier read-back failed -> PROXY BUG")
                continue
            doc = saved.get("doc", {})
            mine = {"status": 200, "data": {"dossier_id": identifier, "par": doc.get("par"), "ledger_index": doc.get("ledger_index")}}
        if mine["status"] != theirs["status"]:
            lines.append(f"PROXY DIVERGENCE {cid}: status direct="
                         f"{mine['status']} proxy={theirs['status']} "
                         f"-> PROXY BUG")
        elif mine.get("data") != theirs["data"]:
            lines.append(f"PROXY DIVERGENCE {cid}: same status "
                         f"{mine['status']} but bodies differ -> "
                         f"PROXY BUG")
        if "save" in step and isinstance(theirs["data"], dict):
            try:
                for name, dotpath in step["save"].items():
                    ctx[name] = dig(theirs["data"], dotpath)
            except PresetError:
                pass
    return lines


def read_log_tail(path, count=40):
    if not path:
        return ["(no server log configured)"]
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError as exc:
        return [f"(cannot read server log {path}: {exc})"]
    return lines[-count:] or ["(server log empty)"]


def build_report(args):
    out = []
    out.append("VERIFICATION SMOKE REPORT")
    out.append("date: " + datetime.datetime.now().isoformat(
        timespec="seconds"))
    out.append(f"python: {platform.python_version()} "
               f"{platform.system()} {platform.machine()}")
    out.append(f"base: {args.base}")
    out.append("")
    try:
        from backend.tools import doctor
        doc_lines, doc_failed = doctor.run_checks()
    except Exception as exc:  # noqa: BLE001 - report must survive
        doc_lines, doc_failed = [f"doctor crashed: {exc!r}"], True
    out.append("--- doctor ---")
    out.extend(doc_lines)
    out.append("")
    try:
        constants, calls = load()
    except PresetError as exc:
        out.append(f"presets.json INVALID: {exc}")
        return out, False
    out.append(f"--- openapi ({len(calls)} preset calls loaded) ---")
    ok, detail = check_openapi(args.base)
    out.append(("OPENAPI " if ok else "OPENAPI-WARN ") + detail)
    out.append("")
    results, _ = run_chain(args.base.rstrip("/") + "/api/v2", constants, calls)
    out.append("--- calls (direct) ---")
    failed = False
    for result in results:
        flag = "ok " if result["ok"] else "FAIL"
        if not result["ok"]:
            failed = True
        out.append(f"[{flag}] {result['id']}: HTTP {result['status']} "
                   f"(want {result['expect']}) {result['ms']:.0f}ms "
                   f"{result['detail']}")
    out.append("")
    if args.via_proxy:
        out.append(f"--- proxy diff via {args.via_proxy} ---")
        diverged = proxy_diff(args.via_proxy, constants, calls, results, direct_base=args.base.rstrip("/") + "/api/v2")
        if diverged:
            failed = True
            out.extend(diverged)
        else:
            out.append("no divergences: immutable responses match; mutable reads match current direct state; compiled dossier validates and matches stored artifact")
        out.append("")
    out.append("--- classification ---")
    buckets = {}
    for result in results:
        buckets.setdefault(classify(result), []).append(result["id"])
    for label in ("BACKEND DOWN or not booted", "PROXY BUG",
                  "PRESET/PAYLOAD BUG (see body)",
                  "BACKEND BUG (see server log)", "ROUTE NOT MOUNTED",
                  "OK"):
        if label in buckets:
            out.append(f"{label}: {len(buckets[label])} call(s)")
    for label, ids in sorted(buckets.items()):
        if label not in ("BACKEND DOWN or not booted", "PROXY BUG",
                         "PRESET/PAYLOAD BUG (see body)",
                         "BACKEND BUG (see server log)",
                         "ROUTE NOT MOUNTED", "OK"):
            out.append(f"{label}: {', '.join(ids)}")
    out.append("")
    out.append(f"--- server log tail ({args.server_log}) ---")
    out.extend(read_log_tail(args.server_log))
    out.append("")
    out.append("SMOKE RESULT: " + ("FAIL" if failed else "PASS"))
    return out, (not failed) and not doc_failed


def main(argv=None):
    parser = argparse.ArgumentParser(description="Replay console presets")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--via-proxy", default=None)
    parser.add_argument("--out", default="triage_report.txt")
    parser.add_argument("--server-log", default="backend.log")
    args = parser.parse_args(argv)
    out, passed = build_report(args)
    text = "\n".join(out) + "\n"
    print(text)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"wrote {args.out}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
