"""Console preset proof: EVERY UI preset body through its real handler.

Run from meta bro root:  python backend/tests/test_console_presets_live.py
(stdlib only: installs a minimal fastapi stub so service_app imports
without the service deps. Bodies come from backend/tools/presets.json
via backend/tools/presets.py - the SAME file smoke_live.py replays.
site/src/lib/console-endpoints.ts is a hand-kept mirror for the UI.)
"""

import os
import sys
import tempfile
import unittest

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
    import fastapi  # noqa: F401 - availability probe; except-branch installs stub
except ImportError:
    sys.modules.setdefault("fastapi", _StubFastAPI())

from engine import canonical_hash  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import backend.service_app as service  # noqa: E402
from backend.persist.filelayout import FileLayoutStore  # noqa: E402
from backend.tools.presets import base_context, load  # noqa: E402

_CONSTANTS, _CALLS = load()
_BY_ID = {call["id"]: call for call in _CALLS}


def body(call_id, ctx=None):
    call = _BY_ID[call_id]
    from backend.tools.presets import resolve
    return resolve(call.get("body", {}),
                   ctx if ctx is not None else base_context(_CONSTANTS))


def fresh_ctx():
    return base_context(_CONSTANTS)


class PresetProof(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        store = FileLayoutStore(root=self._tmp.name)
        old, service._STORE = service._STORE, store
        self.addCleanup(setattr, service, "_STORE", old)
        self.store = store
        self.ctx = fresh_ctx()

    def test_01_eval_score(self):
        out = service.eval_score(body("eval-score-nominal", self.ctx))
        self.assertIn("payload", out)
        out = service.eval_score(body("eval-score-drifted", self.ctx))
        self.assertIn("payload", out)

    def test_02_runs_chain(self):
        run = service.runs_evaluate(body("runs-evaluate", self.ctx))
        self.assertTrue(run["run_id"].startswith("run_"))
        self.ctx["RUN_ID"] = run["run_id"]
        fetched = service.runs_get(self.ctx["RUN_ID"])
        self.assertEqual(fetched["run_id"], run["run_id"])
        dos = service.dossiers_compile(body("dossiers-compile", self.ctx))
        self.assertTrue(dos["dossier_id"].startswith("dos_"))
        self.ctx["DOSSIER_ID"] = dos["dossier_id"]
        self.assertIn("par", dos)
        listed = service.list_runs()
        self.assertIn(run["run_id"], listed["run_ids"])
        dossiers = service.list_dossiers()
        self.assertIn(dos["dossier_id"], dossiers["dossier_ids"])
        again = service.dossiers_get(dos["dossier_id"])
        self.assertEqual(again["doc"]["ledger_index"],
                         dos["ledger_index"])

    def test_03_ledger_verify(self):
        out = service.ledger_verify()
        self.assertIn("ok", out)

    def test_04_governance(self):
        out = service.governance()
        self.assertIn("days_left", out)

    def test_05_pilots_chain(self):
        created = service.create_pilot(body("pilots-create", self.ctx))
        self.assertEqual(created["status"], "RECEIVED")
        self.ctx["PILOT_ID"] = created["pilot_id"]
        listed = service.list_pilots()
        self.assertIn(created["pilot_id"], listed["pilot_ids"])
        fetched = service.get_pilot(self.ctx["PILOT_ID"])
        self.assertEqual(fetched["doc"]["email"], "smoke@consolelabs.dev")

    def test_06_batches(self):
        out = service.stamp_batch_route(body("batches", self.ctx))
        self.assertIn("manifest_id", out)
        self.ctx["MANIFEST_ID"] = out["manifest_id"]

    def test_07_bridge(self):
        out = service.bridge_route(body("bridge", self.ctx))
        self.assertIn("manifest", out)
        self.assertIn("mix_batch", out)

    def test_08_sentinels(self):
        healthy = service.sentinels_route(
            body("sentinels-healthy", self.ctx))
        self.assertIn("overall", healthy)
        collapsed = service.sentinels_route(
            body("sentinels-collapsed", self.ctx))
        self.assertIn("overall", collapsed)

    def test_09_corpus_chain(self):
        corpus = service.create_corpus(body("corpora-create", self.ctx))
        self.assertEqual(corpus["corpus_id"], "smoke-corpus-1")
        self.ctx["CORPUS_ID"] = corpus["corpus_id"]
        manifest = service.stamp_batch_route(body("batches", self.ctx))
        self.ctx["MANIFEST_ID"] = manifest["manifest_id"]
        gen = service.add_generation_route(
            self.ctx["CORPUS_ID"], body("generations", self.ctx))
        self.assertAlmostEqual(gen["alpha"], 0.8)
        risk = service.corpus_risk(self.ctx["CORPUS_ID"])
        self.assertIn("verdict", risk)

    def test_10_par_shapes(self):
        built = service.par_build(body("par-build", self.ctx))
        self.assertIn("par_hash", built)

    def test_11_hardcoded_par_validates(self):
        valid = service.par_validate(body("par-validate", self.ctx))
        self.assertTrue(valid["ok"], valid)
        read = service.par_read(body("par-read", self.ctx))
        self.assertIsInstance(read, dict)

    def test_12_worksheet(self):
        out = service.worksheet_record(body("worksheet", self.ctx))
        self.assertEqual(out["implied_route"],
                         "PART_A_5_6_NOTIFIED_BODY_ROUTE")

    def test_13_panel_chain(self):
        stamp = service.panel_commit(body("panel-commit", self.ctx))
        self.ctx["COMMITMENT_RT"] = stamp["commitment"]
        honest = service.panel_reveal(
            body("panel-reveal-honest", self.ctx))
        self.assertTrue(honest["verified"])
        lying = service.panel_reveal(body("panel-reveal-wrong", self.ctx))
        self.assertFalse(lying["verified"])
        self.assertEqual(
            service.panel_commit({"seed": "console-seed-1",
                                  "case_count": 8})["commitment"],
            _CONSTANTS["COMMITMENT"])

    def test_14_releases(self):
        same = service.release_compare(
            body("releases-identical", self.ctx))
        self.assertTrue(same["identical"])
        reg = service.release_compare(
            body("releases-regression", self.ctx))
        self.assertEqual(reg["flag"],
                         "SUBSTANTIAL_MODIFICATION_CANDIDATE")

    def test_15_transfer(self):
        same = service.eval_transfer(body("transfer-same", self.ctx))
        self.assertTrue(same["transfers"])
        morph = service.eval_transfer(body("transfer-morph", self.ctx))
        self.assertIn("transfers", morph)
        with self.assertRaises(HTTPException):
            service.eval_transfer(body("transfer-joint", self.ctx))

    def test_16_failure_modes(self):
        out = service.eval_failure_modes(
            body("failure-modes", self.ctx))
        self.assertIn("fm1_drift", out)
        self.assertIn("fm5_sim_real_gap", out)

    def test_17_property(self):
        holds = service.eval_property(body("property-holds", self.ctx))
        self.assertTrue(holds["satisfied"])
        breaks = service.eval_property(
            body("property-violates", self.ctx))
        self.assertFalse(breaks["satisfied"])

    def test_18_bounded(self):
        proven = service.eval_bounded(body("bounded-proven", self.ctx))
        self.assertEqual(proven["verdict"], "PROVEN")
        violated = service.eval_bounded(
            body("bounded-violated", self.ctx))
        self.assertEqual(violated["verdict"], "VIOLATED")

    def test_19_credibility(self):
        resolved_card = dict(fresh_ctx()["CARD"])
        self.assertNotIn("$HEX_a", repr(resolved_card))
        self.assertEqual(canonical_hash(resolved_card),
                         _CONSTANTS["CARD_HASH"])
        out = service.eval_credibility(body("credibility", self.ctx))
        self.assertIn("lift", out)

    def test_20_rank(self):
        out = service.eval_rank(body("rank", self.ctx))
        self.assertEqual(out["ranking"], ["p2", "p3", "p1"])

    def test_21_hunt(self):
        default = service.eval_hunt(body("hunt-default", self.ctx))
        self.assertTrue(default["trials"])
        self.ctx["HUNT_CATALOGUE"] = default
        random = service.eval_hunt(body("hunt-random", self.ctx))
        self.assertEqual(len(random["trials"]), 8)

    def test_22_redteam(self):
        broken = service.eval_redteam(body("redteam-broken", self.ctx))
        self.assertTrue(broken["breaks"])
        sane = service.eval_redteam(body("redteam-sane", self.ctx))
        self.assertEqual(sane["breaks"], [])

    def test_23_hunt_summarize(self):
        catalogue = service.eval_hunt(body("hunt-default", self.ctx))
        self.ctx["HUNT_CATALOGUE"] = catalogue
        out = service.eval_hunt_summarize(
            body("hunt-summarize", self.ctx))
        self.assertEqual(out["summary"]["trials"],
                         len(catalogue["trials"]))
        self.assertEqual(out["sealed"]["trials"],
                         len(catalogue["trials"]))

    def test_24_envelope(self):
        out = service.eval_envelope(body("envelope", self.ctx))
        self.assertEqual(out["params"]["noise_scale"]["min_break"], 2.0)

    def test_25_contracts(self):
        holds = service.eval_contract_check(
            body("contracts-holds", self.ctx))
        self.assertTrue(holds["holds"])
        violates = service.eval_contract_check(
            body("contracts-violates", self.ctx))
        self.assertFalse(violates["holds"])

    def test_26_task_graph(self):
        chain = service.eval_task_graph(body("taskgraph-chain", self.ctx))
        self.assertEqual(chain["order"], ["approach", "grasp", "lift"])
        with self.assertRaises(HTTPException):
            service.eval_task_graph(body("taskgraph-cycle", self.ctx))

    def test_27_briefing(self):
        plain = service.eval_briefing(body("briefing-plain", self.ctx))
        self.assertTrue(plain["sections"])
        with_sheet = service.eval_briefing(
            body("briefing-sheet", self.ctx))
        self.assertTrue(with_sheet["sections"])

    def test_28_duplicates(self):
        near = service.duplicates_route(
            body("duplicates-near", self.ctx))
        self.assertGreater(near["rate"], 0.0)
        exact = service.duplicates_route(
            body("duplicates-exact", self.ctx))
        self.assertIn("rate", exact)

    def test_29_adapters(self):
        derived = service.adapters_ingest(
            body("adapters-libero", self.ctx))
        self.assertEqual(derived["provenance"]["schema_status"],
                         "DERIVED")
        with self.assertRaises(HTTPException):
            service.adapters_ingest(body("adapters-halos", self.ctx))
        board = service.adapters_status()
        self.assertEqual(len(board["adapters"]), 5)

    def test_30_history_lists(self):
        run = service.runs_evaluate(body("runs-evaluate", self.ctx))
        runs = service.list_runs()
        self.assertIn(run["run_id"], runs["run_ids"])
        self.ctx["RUN_ID"] = run["run_id"]
        dos = service.dossiers_compile(
            body("dossiers-compile", self.ctx))
        dossiers = service.list_dossiers()
        self.assertIn(dos["dossier_id"], dossiers["dossier_ids"])
        fetched = service.dossiers_get(dos["dossier_id"])
        self.assertEqual(fetched["doc"]["ledger_index"],
                         dos["ledger_index"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
