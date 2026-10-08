"""Ops tools tests: doctor/smoke/reset + presets lib (stdlib only).

Run from meta bro root:  python backend/tests/test_ops_tools.py
HTTP behavior is verified against fake in-process servers; no network.
"""

import copy
import json
import os
import socket
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))


class _StubRouter:
    def __init__(self, *args, **kwargs):
        self.routes = []

    def _add(self, path):
        def deco(fn):
            self.routes.append(type("R", (), {"path": path})())
            return fn
        return deco

    def get(self, path):
        return self._add(path)

    def post(self, path):
        return self._add(path)


class _StubHTTPException(Exception):
    def __init__(self, status_code, detail=None):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


class _StubFastAPI:
    APIRouter = _StubRouter
    HTTPException = _StubHTTPException


try:
    import fastapi  # noqa: F401
except ImportError:
    sys.modules.setdefault("fastapi", _StubFastAPI())

from engine.par import build_par  # noqa: E402

from backend.tools import demo_rehearsal as rehearsal  # noqa: E402
from backend.tools import doctor  # noqa: E402
from backend.tools.golden_lib import build_all as golden_build_all  # noqa: E402
from backend.tools.presets import PresetError, base_context, dig, load, resolve  # noqa: E402
from backend.tools.smoke_live import check_openapi, classify, http_call, proxy_diff, run_chain  # noqa: E402


def closed_port():
    """An (almost surely) closed localhost port. Bind-only, no listen."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def canned(plan, default=(404, {"e": "no"}, 1.0, None)):
    """In-process transport: (method, path) -> (status, data, ms, err).

    NOTE: the sandbox forbids listening sockets (WinError 10013), so
    live fake-servers are impossible here. Classification logic is
    verified through this injected transport instead; exactly one test
    below exercises the real urllib path (connection refused).
    """
    def call(base, method, path, body):
        del base, body
        return plan.get((method, path), default)
    return call


class TestPresetsLib(unittest.TestCase):
    def test_load_shape(self):
        constants, calls = load()
        self.assertEqual(len(calls), 58)
        self.assertEqual(len({c["id"] for c in calls}), 58)
        self.assertIn("CARD_HASH", constants)

    def test_resolve_nested_and_raw(self):
        ctx = {"A": {"x": 1}, "B": 5}
        self.assertEqual(resolve({"v": "$A", "n": "$B"}, ctx),
                         {"v": {"x": 1}, "n": 5})
        self.assertEqual(resolve(["$B", 1], ctx), [5, 1])
        with self.assertRaises(PresetError):
            resolve("$NOPE", ctx)

    def test_resolve_interpolates_paths(self):
        ctx = {"RUN_ID": "run_x", "N": 7}
        self.assertEqual(resolve("runs/$RUN_ID", ctx), "runs/run_x")
        self.assertEqual(
            resolve("ui/release/$RUN_ID?compare=$RUN_ID", ctx),
            "ui/release/run_x?compare=run_x")
        self.assertEqual(resolve("n=$N!", ctx), "n=7!")
        self.assertEqual(resolve("$RUN_ID", ctx), "run_x")

    def test_resolve_embedded_failures_loud(self):
        with self.assertRaises(PresetError):
            resolve("runs/$NOPE", {"RUN_ID": "run_x"})
        with self.assertRaises(PresetError):
            resolve("x/$D", {"D": {"nested": 1}})
        with self.assertRaises(PresetError):
            resolve("x/$L", {"L": [1]})

    def test_resolve_plain_passthrough(self):
        self.assertEqual(resolve("no placeholders", {}), "no placeholders")
        self.assertEqual(resolve(7, {}), 7)
        self.assertEqual(resolve(None, {}), None)

    def test_all_preset_paths_resolve(self):
        constants, calls = load()
        ctx = base_context(constants)
        ctx.update({"RUN_ID": "run_x", "PILOT_ID": "pilot_x",
                    "CORPUS_ID": "c_x", "MANIFEST_ID": "m_x",
                    "DOSSIER_ID": "d_x", "HUNT_CATALOGUE": {},
                    "COMMITMENT_RT": "k_x"})
        for call in calls:
            path = resolve(call["path"], ctx)
            body = resolve(call.get("body"), ctx)
            self.assertNotIn("$", path, call["id"])
            self.assertNotIn("$", json.dumps(body), call["id"])

    def test_dig(self):
        self.assertEqual(dig({"a": {"b": 2}}, "a.b"), 2)
        self.assertEqual(dig({"a": 1}, ""), {"a": 1})
        with self.assertRaises(PresetError):
            dig({"a": 1}, "a.b")

    def test_base_context_resolves_nested(self):
        constants, _ = load()
        ctx = base_context(constants)
        self.assertEqual(ctx["CARD"]["corpus_hash"], ctx["HEX_a"])
        self.assertNotIn("$", json.dumps(ctx["PAR"]))


class TestClassify(unittest.TestCase):
    def test_smoke_report_uses_v2_namespace_for_preset_chain(self):
        from backend.tools.smoke_live import build_report
        args = SimpleNamespace(base="http://127.0.0.1:8011", via_proxy=None, server_log=None)
        with patch("backend.tools.doctor.run_checks", return_value=([], False)), patch("backend.tools.smoke_live.check_openapi", return_value=(True, "ok")), patch("backend.tools.smoke_live.run_chain", return_value=([], {})) as chain:
            build_report(args)
        self.assertEqual(chain.call_args.args[0], "http://127.0.0.1:8011/api/v2")

    def test_rules(self):
        self.assertEqual(classify({"status": None, "ok": False}),
                         "BACKEND DOWN or not booted")
        self.assertEqual(classify({"status": 200, "ok": True}), "OK")
        self.assertEqual(classify({"status": 422, "ok": False}),
                         "PRESET/PAYLOAD BUG (see body)")
        self.assertEqual(classify({"status": 500, "ok": False}),
                         "BACKEND BUG (see server log)")
        self.assertEqual(classify({"status": 404, "ok": False}),
                         "ROUTE NOT MOUNTED")


class TestSmokeLive(unittest.TestCase):
    def test_real_transport_failure(self):
        # The ONE genuine urllib test: unroutable target, no listener.
        # (Sandbox forbids even localhost connect, so any transport
        # error proves the mapping; founder machines get refused fast.)
        base = f"http://127.0.0.1:{closed_port()}"
        status, _, ms, err = http_call(base, "GET", "api/v2/ok", None)
        self.assertIsNone(status)
        self.assertTrue(err)
        self.assertLess(ms, 20000.0)
        self.assertEqual(
            classify({"status": None, "ok": False}),
            "BACKEND DOWN or not booted")

    def test_statuses_and_snippets(self):
        call = canned({("GET", "api/v2/ok"): (200, {"a": 1}, 2.0, None),
                       ("POST", "api/v2/bad"): (
                           422, {"detail": {"error": "x"}}, 2.0, None),
                       ("GET", "api/v2/boom"): (
                           500, {"e": 1}, 2.0, None)})
        calls = [{"id": "ok", "method": "GET", "path": "api/v2/ok",
                  "expect": 200},
                 {"id": "bad", "method": "POST", "path": "api/v2/bad",
                  "body": {"z": 0}, "expect": 422},
                 {"id": "boom", "method": "GET", "path": "api/v2/boom",
                  "expect": 200},
                 {"id": "gone", "method": "GET", "path": "api/v2/nope",
                  "expect": 200}]
        results, _ = run_chain("http://x", {}, calls, call_fn=call)
        by_id = {r["id"]: r for r in results}
        self.assertTrue(by_id["ok"]["ok"])
        self.assertTrue(by_id["bad"]["ok"])
        self.assertEqual(classify(by_id["boom"]),
                         "BACKEND BUG (see server log)")
        self.assertEqual(classify(by_id["gone"]), "ROUTE NOT MOUNTED")
        self.assertLessEqual(len(by_id["ok"]["detail"]), 160)

    def test_transport_failure_in_chain(self):
        def dead(base, method, path, body):
            del base, method, path, body
            return None, {}, 1.0, "ConnectionRefusedError: [WinError 10061]"
        results, _ = run_chain("http://x", {}, [{"id": "x", "method": "GET",
                                                 "path": "api/v2/ok",
                                                 "expect": 200}],
                               call_fn=dead)
        self.assertEqual(classify(results[0]),
                         "BACKEND DOWN or not booted")

    def test_save_rules_apply(self):
        call = canned({("GET", "api/v2/make"): (
            200, {"rid": "r1"}, 1.0, None)})
        results, ctx = run_chain(
            "http://x", {}, [{"id": "make", "method": "GET",
                              "path": "api/v2/make", "expect": 200,
                              "save": {"RID": "rid"}}],
            call_fn=call)
        self.assertTrue(results[0]["ok"])
        self.assertEqual(ctx["RID"], "r1")

    def test_openapi_count(self):
        paths = {f"/api/v2/r{i}": {"get": {}} for i in range(42)}
        good = canned({("GET", "openapi.json"): (
            200, {"paths": paths}, 1.0, None)})
        ok, detail = check_openapi("http://x", call_fn=good)
        self.assertTrue(ok, detail)
        thin = canned({("GET", "openapi.json"): (
            200, {"paths": {}}, 1.0, None)})
        ok, _ = check_openapi("http://x", call_fn=thin)
        self.assertFalse(ok)

    def test_proxy_match_and_diverge(self):
        direct = [{"id": "ok", "ok": True, "status": 200, "expect": 200,
                   "data": {"a": 1}}]
        calls = [{"id": "ok", "method": "GET", "path": "api/v2/ok",
                  "expect": 200}]
        same = canned({("GET", "api/v2/ok"): (
            200, {"up": True, "status": 200, "data": {"a": 1}}, 1.0,
            None)})
        self.assertEqual(proxy_diff("http://px", {}, calls, direct,
                                    call_fn=same), [])
        diff = canned({("GET", "api/v2/ok"): (
            200, {"up": True, "status": 500, "data": {}}, 1.0, None)})
        lines = proxy_diff("http://px", {}, calls, direct, call_fn=diff)
        self.assertEqual(len(lines), 1)
        self.assertIn("PROXY DIVERGENCE", lines[0])
        self.assertIn("PROXY BUG", lines[0])

        def dead(base, method, path, body):
            del base, method, path, body
            return None, {}, 1.0, "ConnectionRefusedError: refused"
        lines = proxy_diff("http://px", {}, calls, direct, call_fn=dead)
        self.assertIn("PROXY BUG", lines[0])

    def test_proxy_body_differs(self):
        direct = [{"id": "ok", "ok": True, "status": 200, "expect": 200,
                   "data": {"a": 1}}]
        calls = [{"id": "ok", "method": "GET", "path": "api/v2/ok",
                  "expect": 200}]
        quiet = canned({("GET", "api/v2/ok"): (
            200, {"up": True, "status": 200, "data": {"a": 2}}, 1.0,
            None)})
        lines = proxy_diff("http://px", {}, calls, direct, call_fn=quiet)
        self.assertEqual(len(lines), 1)
        self.assertIn("bodies differ", lines[0])


class TestDoctor(unittest.TestCase):
    def test_python_check(self):
        status, detail = doctor.check_python()
        self.assertIn(status, ("PASS", "WARN"))
        self.assertIn("python", detail)

    def test_import_check(self):
        self.assertEqual(doctor.check_import("sys")[0], "PASS")
        status, detail = doctor.check_import("missing_mod_xyz_123")
        self.assertEqual(status, "FAIL")
        self.assertIn("IMPORT FAILED", detail)

    def test_store_writable_file_mode(self):
        old_cwd = os.getcwd()
        old_mongo = os.environ.pop("MONGO_URL", None)
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                status, detail = doctor.check_store_writable()
            finally:
                os.chdir(old_cwd)
                if old_mongo is not None:
                    os.environ["MONGO_URL"] = old_mongo
        self.assertEqual(status, "PASS")
        self.assertIn("file store writable", detail)

    def test_store_mongo_mode_mentions_mongo(self):
        old = os.environ.get("MONGO_URL")
        os.environ["MONGO_URL"] = "mongodb://localhost:27017/x"
        try:
            status, detail = doctor.check_store_writable()
        finally:
            if old is None:
                os.environ.pop("MONGO_URL", None)
            else:
                os.environ["MONGO_URL"] = old
        self.assertIn(status, ("WARN", "FAIL"))
        self.assertIn("mongo", detail.lower())

    def test_port_free_and_responding(self):
        port = closed_port()
        self.assertEqual(doctor.check_port(port)[0], "PASS")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", 0))
            sock.listen(1)
        except PermissionError:
            raise unittest.SkipTest("sandbox forbids listen()")
        live = sock.getsockname()[1]
        try:
            self.assertEqual(doctor.check_port(live)[0], "WARN")
        finally:
            sock.close()

    def test_run_checks_shape(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                lines, failed = doctor.run_checks()
            finally:
                os.chdir(old_cwd)
        self.assertIsInstance(lines, list)
        self.assertIsInstance(failed, bool)
        self.assertTrue(any(line.startswith("[") for line in lines))


class TestResetDemo(unittest.TestCase):
    def test_refuses_unmarked(self):
        from backend.tools import reset_demo
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "store")
            os.mkdir(target)
            with open(os.path.join(target, "keep.txt"), "w") as handle:
                handle.write("x")
            with self.assertRaises(SystemExit):
                reset_demo.reset_store(target)
            self.assertTrue(os.path.isfile(
                os.path.join(target, "keep.txt")))

    def test_seed_twice_identical(self):
        from backend.persist.filelayout import FileLayoutStore
        from backend.tools import reset_demo
        with tempfile.TemporaryDirectory() as tmp:
            store = FileLayoutStore(root=tmp)
            first = reset_demo.seed_stories(store, horizon=16)
            second = reset_demo.seed_stories(store, horizon=16)
        self.assertEqual([r for _, r, _ in first],
                         [r for _, r, _ in second])
        self.assertEqual(len(first), 4)

    def test_service_and_stdlib_paths_agree(self):
        import backend.service_app  # noqa: F401 - stub or real
        from backend.persist.filelayout import FileLayoutStore
        from backend.tools import reset_demo
        body = {"intended": [[0, 0], [1, 0], [2, 0], [3, 0]],
                "observed": [[0, 0], [1, 0.1], [2, 0], [3, 0.1]],
                "policy_id": "agree-probe", "seed": 5, "threshold": 0.5,
                "profile": "draft-0", "evidence_prefix": "ev://t/",
                "breach_run": 3}
        with tempfile.TemporaryDirectory() as tmp:
            store = FileLayoutStore(root=tmp)
            via_service = reset_demo.evaluate_run(
                dict(body), store, prefer_service=True)
            via_stdlib = reset_demo.evaluate_run(
                dict(body), store, prefer_service=False)
        self.assertEqual(via_service["run_id"], via_stdlib["run_id"])
        self.assertEqual(via_service["scorecard"],
                         via_stdlib["scorecard"])

    def test_reset_wipes_marked_only(self):
        from backend.tools import reset_demo
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "demo")
            os.mkdir(target)
            with open(os.path.join(target, ".verification-demo-store"),
                      "w") as handle:
                handle.write("demo-store-v1")
            with open(os.path.join(target, "junk.json"), "w") as handle:
                handle.write("{}")
            removed = reset_demo.reset_store(target)
        self.assertEqual(removed, ["junk.json"])


class TestDemoRehearsal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built = golden_build_all()["stories"]
        clean = cls.built["clean"]["scorecard"]
        gates = [{"id": g["gate"], "verdict": g["status"],
                  "measurement": g["measurement"],
                  "evidence": g["evidence"]}
                 for g in clean["payload"]["gates"]]
        cls.par_env = build_par(
            policy={"id": "golden-clean",
                    "weights": "sha256:" + "11" * 32},
            release={"parent": "sha256:" + "11" * 32,
                     "delta": "IN-ODD"},
            gates=gates, ledger_head="0" * 64,
            odd="rehearsal test odd",
            independence={"builder": "t", "funder": "t",
                          "relationship": "none"})

    def _router(self, verdict_override=None, transfer_status=422):
        built = self.built
        par_env = self.par_env

        def call(base, method, path, body):
            del base
            if (method, path) == ("GET", "api/v2/governance"):
                return 200, {"days_left": 100}, 1.0, None
            if (method, path) == ("GET", "api/v2/runs"):
                return 200, {"run_ids": []}, 1.0, None
            if (method, path) == ("POST", "api/v2/runs/evaluate"):
                policy = (body.get("policy_id") or "").replace(
                    "golden-", "")
                card = built[policy]["scorecard"]
                if verdict_override and policy in verdict_override:
                    card = copy.deepcopy(card)
                    card["payload"]["verdict"] = verdict_override[policy]
                return 200, {"run_id": f"run_{policy}",
                             "verdict": card["payload"]["verdict"],
                             "scorecard": card}, 1.0, None
            if (method, path) == ("POST", "api/v2/eval/hunt"):
                return 200, {"breaks": [{"trial": 0}],
                             "trials": []}, 1.0, None
            if (method, path) == ("POST", "api/v2/eval/transfer"):
                if transfer_status == 422:
                    return 422, {"detail": {
                        "error": "input",
                        "message": "joint refused"}}, 1.0, None
                return 200, {"score": 0.1}, 1.0, None
            if (method, path) == ("POST", "api/v2/dossiers/compile"):
                return 200, {"dossier_id": "dos_x", "par": par_env,
                             "ledger_index": 0}, 1.0, None
            if (method, path) == ("POST", "api/v2/ledger/verify"):
                return 200, {"ok": True, "entries": 3}, 1.0, None
            if (method, path) == ("POST", "api/v2/eval/briefing"):
                return 200, {"sections": [{"title": "Scoping"},
                                          {"title": "More"}]}, 1.0, None
            return 404, {"e": "no"}, 1.0, None

        return call

    def test_full_pass_and_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows, all_ok = rehearsal.run_all(
                "http://x", call_fn=self._router(), sleep=False,
                record_dir=tmp)
            self.assertTrue(all_ok)
            self.assertEqual(
                [r["step"] for r in rows],
                ["local-goldens", "overview", "clean", "drifty",
                 "playback", "hunt-replay", "joint-refusal",
                 "par-tamper", "briefing"])
            self.assertTrue(all(r["ok"] for r in rows))
            files = sorted(os.listdir(tmp))
            self.assertEqual(len(files), 9)
            with open(os.path.join(tmp, files[2]),
                      encoding="utf-8") as handle:
                raw = handle.read()
            self.assertEqual(raw, json.dumps(json.loads(raw), indent=2,
                                             sort_keys=True) + "\n")

    def test_verdict_mismatch_fails_only_that_step(self):
        rows, all_ok = rehearsal.run_all(
            "http://x",
            call_fn=self._router(
                verdict_override={"playback": "TRUSTED"}),
            sleep=False)
        self.assertFalse(all_ok)
        by_step = {r["step"]: r for r in rows}
        self.assertFalse(by_step["playback"]["ok"])
        self.assertTrue(by_step["clean"]["ok"])
        self.assertTrue(by_step["local-goldens"]["ok"])

    def test_wrong_refusal_status_fails(self):
        rows, all_ok = rehearsal.run_all(
            "http://x", call_fn=self._router(transfer_status=200),
            sleep=False)
        self.assertFalse(all_ok)
        by_step = {r["step"]: r for r in rows}
        self.assertFalse(by_step["joint-refusal"]["ok"])

    def test_transport_dead_fails_http_only(self):
        def dead(base, method, path, body):
            del base, method, path, body
            return None, {}, 1.0, "refused"

        rows, all_ok = rehearsal.run_all(
            "http://x", call_fn=dead, sleep=False)
        self.assertFalse(all_ok)
        by_step = {r["step"]: r for r in rows}
        self.assertTrue(by_step["local-goldens"]["ok"])
        self.assertFalse(by_step["overview"]["ok"])
        self.assertFalse(by_step["par-tamper"]["ok"])

    def test_bad_goldens_file_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "stories.json")
            with open(bad, "w", encoding="utf-8") as handle:
                handle.write("{}")
            with self.assertRaises(SystemExit):
                rehearsal.load_goldens(bad)
            with self.assertRaises(SystemExit):
                rehearsal.load_goldens(os.path.join(tmp, "nope.json"))

    def test_render_table(self):
        rows = [{"step": "a", "ok": True, "ms": 1.5, "detail": "x"},
                {"step": "b", "ok": False, "ms": 2.5, "detail": "y"}]
        lines = rehearsal.render(rows)
        self.assertTrue(lines[0].startswith("STEP"))
        self.assertIn("PASS", lines[1])
        self.assertIn("FAIL", lines[2])
        self.assertEqual(lines[-1], "REHEARSAL RESULT: FAIL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
