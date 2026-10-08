"""Morning demo client: the composition story, end to end (stdlib only).

Run AFTER the server is up (RUN QUEUE steps 14-15):
    python backend/demo_client.py
Needs: fastapi + uvicorn installed, server on 127.0.0.1:8000.
File store is the default (./data); set MONGO_URL to demo Mongo.

UNRUN in this environment (no server here). Every assert below encodes
a code reading; a failure on his machine is a bug report, not a demo
flaw. Exit 0 = all steps green.

Flow: governance -> score -> run -> compare -> compile -> verify ->
pilots -> provenance -> transfer (+ joint refusal) -> PAR file for
par_cli. The compare->dossier threading is MANUAL and shown as such.
"""

import json
import os
import sys
import tempfile
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000/api/v2"
_ZERO = "sha256:" + "0" * 64


def _call(method, path, body=None):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers,
                                 method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _step(name):
    print(f"\n=== {name} ===")


def main() -> int:
    _step("1. governance snapshot")
    try:
        code, gov = _call("GET", "/governance")
    except urllib.error.URLError as exc:
        print(f"server not reachable: {exc.reason}. Start it first:")
        print("  uvicorn backend.api:create_app --factory --port 8000")
        return 3
    assert code == 200, (code, gov)
    print("deadline:", gov["eu_deadline"], "| days_left:", gov["days_left"])

    intended = [[0, 0], [1, 1], [2, 2], [3, 3]]
    observed = [[0, 0], [1.05, 1], [2, 2.1], [3, 3]]

    _step("2. score one trace pair")
    code, card = _call("POST", "/eval/score",
                       {"intended": intended, "observed": observed})
    assert code == 200, (code, card)
    print("verdict:", card["payload"]["verdict"])

    _step("3. persist as a run")
    code, run = _call("POST", "/runs/evaluate",
                      {"intended": intended, "observed": observed,
                       "policy_id": "demo-policy"})
    assert code == 200, (code, run)
    run_id = run["run_id"]
    print("run_id:", run_id, "| verdict:", run["verdict"])
    code, fetched = _call("GET", f"/runs/{run_id}")
    assert code == 200 and fetched["run_id"] == run_id, (code, fetched)

    _step("4. release-over-release compare (manual threading demo)")
    gates = [{"gate": g["gate"], "measurement": g["measurement"],
              "status": g["status"]}
             for g in run["scorecard"]["payload"]["gates"]]
    code, cmp = _call("POST", "/releases/compare",
                      {"parent_gates": gates, "child_gates": gates,
                       "parent_weights_hash": "weights-v1",
                       "child_weights_hash": "weights-v2"})
    assert code == 200, (code, cmp)
    print("flag:", cmp["flag"], "| reasons:", cmp["reasons"])
    # MANUAL THREADING (by design, see changelog 017): the caller maps
    # the compare flag onto the dossier release delta. Nothing automatic.
    delta = ("SUBSTANTIAL_MODIFICATION_CANDIDATE" if cmp["flag"]
             else "IN-ODD")
    print("mapped delta:", delta)

    _step("5. compile dossier (seals RUN_SEALED to the ledger)")
    code, dos = _call("POST", "/dossiers/compile",
                      {"run_ids": [run_id],
                       "weights": "sha256:" + "2" * 64,
                       "release": {"parent": _ZERO, "delta": delta},
                       "independence": {"builder": "Verification",
                                        "funder": "pilot",
                                        "relationship": "independent"}})
    assert code == 200, (code, dos)
    print("dossier:", dos["dossier_id"],
          "| ledger_index:", dos["ledger_index"])

    _step("6. verify the chain")
    code, chain = _call("POST", "/ledger/verify")
    assert code == 200 and chain["ok"], (code, chain)
    print("chain ok:", chain["ok"])

    _step("7. pilot intake")
    code, pilot = _call("POST", "/pilots",
                        {"name": "Ada Lovelace",
                         "org": "Analytical Engines",
                         "email": "ada@example.com", "robot": "arm-6dof",
                         "failure_mode": "FM1 drift"})
    assert code == 200, (code, pilot)
    print("pilot:", pilot["pilot_id"], pilot["status"])

    _step("8. provenance: stamp -> corpus -> risk")
    code, man = _call("POST", "/provenance/batches",
                      {"generator": {"name": "axiom", "version": "0.3"},
                       "seed": 7, "content_hash": "1" * 64,
                       "n_rows": 100,
                       "ingredients": [{"kind": "real", "n_rows": 100}]})
    assert code == 200, (code, man)
    mid = man["manifest_id"]
    print("manifest:", mid[:16], "...")
    code, _ = _call("POST", "/provenance/corpora",
                    {"corpus_id": "demo-corpus"})
    assert code == 200, (code, _)
    code, _ = _call("POST", "/provenance/corpora/demo-corpus/generations",
                    {"real_rows": 100,
                     "synth_batches": [{"manifest_id": mid,
                                        "n_rows": 50}]})
    assert code == 200, (code, _)
    code, risk = _call("GET", "/provenance/corpora/demo-corpus/risk")
    assert code == 200, (code, risk)
    print("lineage verdict:", risk["verdict"])

    _step("9. cross-embodiment transfer (+ joint refusal)")
    card_a = {"embodiment_id": "r1", "space": "task",
              "position_scale": 1.0, "frame_id": "world"}
    code, rep = _call("POST", "/eval/transfer",
                      {"card_a": card_a, "trace_a": [[0.0], [1.0]],
                       "card_b": dict(card_a, embodiment_id="r2"),
                       "trace_b": [[0.0], [1.05]]})
    assert code == 200, (code, rep)
    print("centered_frechet:", round(rep["centered_frechet"], 4),
          "| frames_match:", rep["frames_match"])
    code, refused = _call("POST", "/eval/transfer",
                          {"card_a": dict(card_a, space="joint"),
                           "trace_a": [[0.0], [1.0]],
                           "card_b": dict(card_a, space="joint"),
                           "trace_b": [[0.0], [1.0]]})
    assert code == 422, (code, refused)
    print("joint-space refused (422) as designed")

    _step("10. PAR file for the offline reader")
    path = os.path.join(tempfile.gettempdir(), "vv-demo-par.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(dos["par"], handle)  # compile returns the envelope as-is
    print("wrote:", path)
    print("run: python backend/par_cli.py", path)

    print("\nALL DEMO STEPS GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
