"""Live error-contract check against a REAL running server.

Founder runs from meta bro root with the backend up:
  python backend/tools/live_contract.py --base http://127.0.0.1:8000
Posts one malformed body per route class and classifies the 422
shape: IN-HANDLER-422 (our {"error": "input"} shape), NATIVE-422
(FastAPI's own request validation), or MIRROR-VALUE-422 (a
ValueError escaped to the mirror handler: a BUG, report it).
Also checks the 404 shape and that no body leaks a traceback.
Exit 0 when every case 422/404s with a known shape; exit 1 else.
Note: the 500 shape cannot be triggered on demand against a live
server; it is verified in-process by test_error_contract.py.
Stdlib only.
"""

import argparse
import json
import sys
import urllib.request

CASES = [
    ("POST", "api/v2/runs/evaluate", {}),
    ("POST", "api/v2/dossiers/compile", {"run_ids": []}),
    ("POST", "api/v2/pilots", {}),
    ("POST", "api/v2/provenance/batches", {}),
    ("POST", "api/v2/provenance/bridge", {}),
    ("POST", "api/v2/provenance/sentinels", {}),
    ("POST", "api/v2/provenance/corpora", {}),
    ("POST", "api/v2/par/build", {}),
    ("POST", "api/v2/par/validate", "xx"),
    ("POST", "api/v2/par/read", "xx"),
    ("POST", "api/v2/worksheet/record", {}),
    ("POST", "api/v2/panel/commit", {}),
    ("POST", "api/v2/panel/reveal", "xx"),
    ("POST", "api/v2/releases/compare", {}),
    ("POST", "api/v2/eval/score", {}),
    ("POST", "api/v2/eval/transfer", {}),
    ("POST", "api/v2/eval/failure-modes", {}),
    ("POST", "api/v2/eval/hunt", {"trial_cap": 999}),
    ("POST", "api/v2/eval/redteam", {"trial_cap": 0}),
    ("POST", "api/v2/eval/hunt/summarize", {}),
    ("POST", "api/v2/eval/envelope", {}),
    ("POST", "api/v2/eval/briefing", {}),
    ("POST", "api/v2/eval/contracts/check", {}),
    ("POST", "api/v2/eval/task-graph", {}),
    ("POST", "api/v2/eval/rank", {}),
    ("POST", "api/v2/eval/credibility", {"min_n": "xx"}),
    ("POST", "api/v2/eval/bounded", {}),
    ("POST", "api/v2/eval/property", {}),
    ("POST", "api/v2/adapters/ingest",
     {"harness": "nope", "document": {}}),
    ("POST", "api/v2/provenance/duplicates",
     {"rows": [], "mode": "near"}),
    ("GET", "api/v2/runs/run_missing0000", None),
]

TIMEOUT = 10


def _opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(base, method, path, body):
    url = base.rstrip("/") + "/" + path.lstrip("/")
    data = None
    headers = {}
    if method != "GET":
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method=method)
    try:
        with _opener().open(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - transport report
        return None, f"TRANSPORT FAIL: {exc!r}"


def classify(status, raw):
    if status is None:
        return "TRANSPORT FAIL", raw[:160]
    if "Traceback" in raw:
        return "LEAK: traceback in body", raw[:160]
    try:
        doc = json.loads(raw)
    except ValueError:
        return f"UNEXPECTED: status {status}, non-JSON", raw[:160]
    Detail = doc.get("Detail", doc.get("detail"))
    if status == 404:
        if isinstance(Detail, dict) and Detail.get("error") == "not_found":
            return "NOT-FOUND-404", ""
        return "UNEXPECTED 404 shape", raw[:160]
    if status != 422:
        return f"UNEXPECTED: status {status}", raw[:160]
    if isinstance(Detail, dict) and Detail.get("error") == "input":
        return "IN-HANDLER-422", ""
    if isinstance(Detail, list):
        return ("NATIVE-422 (FastAPI request validation)", "")
    if isinstance(Detail, str):
        return ("MIRROR-VALUE-422: ValueError escaped handler (BUG)",
                Detail[:160])
    return "UNKNOWN 422 shape", raw[:160]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="live error contract")
    parser.add_argument("--base", required=True)
    parser.add_argument("--out", default="contract_report.txt")
    args = parser.parse_args(argv)
    lines = [f"base: {args.base}"]
    bad = 0
    for method, path, body in CASES:
        status, raw = call(args.base, method, path, body)
        verdict, note = classify(status, raw)
        flag = "ok" if verdict in ("IN-HANDLER-422", "NOT-FOUND-404",
                                   "NATIVE-422 (FastAPI request "
                                   "validation)") else "PROBLEM"
        if flag == "PROBLEM":
            bad += 1
        lines.append(f"[{flag}] {method} {path} -> {status} {verdict}"
                     + (f" | {note}" if note else ""))
    lines.append(f"CONTRACT RESULT: {'PASS' if not bad else 'FAIL'} "
                 f"({len(CASES) - bad}/{len(CASES)} clean)")
    if bad:
        lines.append("Paste contract_report.txt back: the fix is on us.")
    report = "\n".join(lines) + "\n"
    print(report)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(report)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
