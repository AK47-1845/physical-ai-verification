"""Regression tests for night-audit fixes 008-046+ (stdlib only).

Run from meta bro root:  python backend/tests/test_audit_regressions.py
Covers refusal/hardening behavior added during the audit loop. Service
level fixes (_not_found, 422 wraps, verdict mapping) are covered by
router-path assertions in test_contracts_store.py, not here.

UNRUN in this environment (no shell); goes green on the RUN QUEUE.
"""

import os
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.guard import GuardError, check_chunk  # noqa: E402
from engine.hunt import HuntError, grid_search, random_search  # noqa: E402
from engine.ledger import LedgerError, append  # noqa: E402
from engine.ota import OTAError, children_of, new_vault, register_release, rollout_line  # noqa: E402
from engine.panel import PanelError, build_panel  # noqa: E402
from engine.release import ReleaseError, compare  # noqa: E402
from engine.sensitivity import SensitivityError, action_sensitivity  # noqa: E402

from backend.eval.failure_modes import FailureModeError, executability_proxy  # noqa: E402
from backend.eval.xembodiment import XEmbodimentError, transfer_score  # noqa: E402


class _CalmBackend:
    def evaluate(self, params):
        return {"breaks": False, "measurement": 0.0}


_WHASH = "sha256:" + "0" * 64


def _card(frame):
    return {"embodiment_id": "r1", "space": "task",
            "position_scale": 1.0, "frame_id": frame}


def _gates(status="PASS"):
    return [{"gate": "g1", "measurement": 1.0, "status": status}]


class TestHuntSeed(unittest.TestCase):
    def test_grid_rejects_none_seed(self):
        with self.assertRaises(HuntError):
            grid_search(_CalmBackend(), {"a": [1.0]}, seed=None, trial_cap=1)

    def test_random_rejects_float_seed(self):
        with self.assertRaises(HuntError):
            random_search(_CalmBackend(), {"a": (0.0, 1.0)}, seed=0.5,
                          trial_cap=1)

    def test_int_seed_still_runs(self):
        out = grid_search(_CalmBackend(), {"a": [1.0]}, seed=7, trial_cap=1)
        self.assertEqual(len(out["trials"]), 1)


class TestSensitivityGuards(unittest.TestCase):
    def _predict(self, z, actions):
        return [0.0, 0.0]

    def test_none_seed_rejected(self):
        with self.assertRaises(SensitivityError):
            action_sensitivity(self._predict, None, [[0.0], [1.0]],
                               seed=None)

    def test_nan_threshold_rejected(self):
        with self.assertRaises(SensitivityError):
            action_sensitivity(self._predict, None, [[0.0], [1.0]],
                               seed=1, threshold=float("nan"))

    def test_negative_threshold_rejected(self):
        with self.assertRaises(SensitivityError):
            action_sensitivity(self._predict, None, [[0.0], [1.0]],
                               seed=1, threshold=-0.5)

    def test_non_sequence_actions_rejected(self):
        with self.assertRaises(SensitivityError):
            action_sensitivity(self._predict, None, 5, seed=1)

    def test_single_action_rejected(self):
        with self.assertRaises(SensitivityError):
            action_sensitivity(self._predict, None, [[0.0]], seed=1)


class TestGuardShapes(unittest.TestCase):
    def test_position_must_be_list(self):
        with self.assertRaises(GuardError):
            check_chunk([[0.0, 0.0]], {"position": "xx"}, dt=0.1)

    def test_caps_must_be_list(self):
        with self.assertRaises(GuardError):
            check_chunk([[0.0, 0.0], [0.1, 0.1]],
                        {"position": [[-1.0, 1.0], [-1.0, 1.0]],
                         "velocity": 5},
                        dt=0.1)


class TestOtaVaultShape(unittest.TestCase):
    def _reg(self, vault):
        return register_release(vault, policy_id="p", weights_hash=_WHASH,
                                parent_hash=None,
                                regression_verdict="TRUSTED",
                                regression_flag=None, seed=1,
                                profile_version="v")

    def test_register_rejects_bare_dict(self):
        with self.assertRaises(OTAError):
            self._reg({})

    def test_children_rejects_none_vault(self):
        with self.assertRaises(OTAError):
            children_of(None, _WHASH)

    def test_rollout_rejects_bad_releases(self):
        with self.assertRaises(OTAError):
            rollout_line({"releases": []}, _WHASH)

    def test_good_vault_still_registers(self):
        record = self._reg(new_vault())
        self.assertTrue(record["release_id"].startswith("rel_"))


class TestPanelCases(unittest.TestCase):
    def test_set_case_rejected(self):
        with self.assertRaises(PanelError):
            build_panel("s", 1, lambda rng, i: {1, 2})


class TestReleaseTolerances(unittest.TestCase):
    def test_string_tolerances_rejected(self):
        with self.assertRaises(ReleaseError):
            compare(_gates(), _gates(), parent_weights_hash="a",
                    child_weights_hash="b", tolerances="x")


class TestJerkFloor(unittest.TestCase):
    def test_short_traj_jerk_none_bounds_count(self):
        out = executability_proxy([[0.0, 0.0], [9.0, 0.0], [0.0, -9.0]],
                                  bounds=(-2.0, 2.0))
        self.assertIsNone(out["max_jerk"])
        self.assertIsNone(out["mean_jerk"])
        self.assertEqual(out["bound_violations"], 2)

    def test_single_point_jerk_none(self):
        out = executability_proxy([[0.0, 0.0]])
        self.assertIsNone(out["max_jerk"])
        self.assertEqual(out["bound_violations"], 0)


class TestFramesMatch(unittest.TestCase):
    def test_same_frame_true(self):
        out = transfer_score(_card("a"), [[0.0], [1.0]],
                             _card("a"), [[0.0], [1.0]])
        self.assertTrue(out["frames_match"])

    def test_diff_frame_false(self):
        out = transfer_score(_card("a"), [[0.0], [1.0]],
                             _card("b"), [[0.0], [1.0]])
        self.assertFalse(out["frames_match"])
        self.assertEqual(out["frames"], ["a", "b"])

    def test_joint_still_refused(self):
        card = _card("a")
        card["space"] = "joint"
        with self.assertRaises(XEmbodimentError):
            transfer_score(card, [[0.0], [1.0]],
                           _card("a"), [[0.0], [1.0]])


class TestLedgerUnhashable(unittest.TestCase):
    def test_set_payload_wrapped(self):
        with self.assertRaises(LedgerError):
            append([], "T", {"s": {1, 2}}, "2026-01-01")


class TestBriefingShapes(unittest.TestCase):
    def _envelope(self):
        from engine.par import build_par
        return build_par(
            policy={"id": "p", "weights": _WHASH},
            release={"parent": _WHASH, "delta": "IN-ODD"},
            gates=[{"id": "g1", "verdict": "PASS"}],
            ledger_head="0" * 64, odd="test cell",
            independence={"builder": "b", "funder": "f",
                          "relationship": "r"})

    def test_string_cards_rejected(self):
        from backend.eval.briefing import BriefingError, briefing_view
        with self.assertRaises(BriefingError):
            briefing_view(self._envelope(), cards="x")

    def test_none_card_flagged_not_crash(self):
        from backend.eval.briefing import briefing_view
        out = briefing_view(self._envelope(), cards=[None])
        self.assertIn("credibility: ? cannot lift DRAFT",
                      out["attention"])

    def test_string_worksheet_rejected(self):
        from backend.eval.briefing import BriefingError, briefing_view
        with self.assertRaises(BriefingError):
            briefing_view(self._envelope(), worksheet="x")

    def test_string_ledger_verdict_rejected(self):
        from backend.eval.briefing import BriefingError, briefing_view
        with self.assertRaises(BriefingError):
            briefing_view(self._envelope(), ledger_verdict="x")

    def test_minimal_briefing_flags_gaps_first(self):
        from backend.eval.briefing import briefing_view
        out = briefing_view(self._envelope())
        self.assertEqual(out["blocked_count"], 0)
        self.assertTrue(any("worksheet: missing" in a
                            for a in out["attention"]))
        self.assertTrue(any("ledger: unverified" in a
                            for a in out["attention"]))


class TestSentinelThresholds(unittest.TestCase):
    def test_string_floor_rejected(self):
        from backend.provenance.sentinels import SentinelError, collapse_report
        with self.assertRaises(SentinelError):
            collapse_report({"a": [1.0, 2.0]}, {"a": [1.0]},
                            var_floor="x")

    def test_negative_cap_rejected(self):
        from backend.provenance.sentinels import SentinelError, collapse_report
        with self.assertRaises(SentinelError):
            collapse_report({"a": [1.0, 2.0]}, {"a": [1.0]},
                            drift_cap=-1)

    def test_identical_columns_ok(self):
        from backend.provenance.sentinels import collapse_report
        out = collapse_report({"a": [1.0, 2.0, 3.0]},
                              {"a": [1.0, 2.0, 3.0]})
        self.assertEqual(out["overall"], "OK")


class TestManifestShapes(unittest.TestCase):
    def _stamp(self, **over):
        from backend.provenance.manifest import stamp_batch
        kw = {"generator": {"name": "g", "version": "v"},
              "seed": 1, "content_hash": "0" * 64, "n_rows": 5,
              "ingredients": [{"kind": "real", "n_rows": 5}]}
        kw.update(over)
        return stamp_batch(**kw)

    def test_list_params_rejected(self):
        from backend.provenance.manifest import ManifestError
        with self.assertRaises(ManifestError):
            self._stamp(generator={"name": "g", "version": "v",
                                   "params": []})

    def test_int_content_kind_rejected(self):
        from backend.provenance.manifest import ManifestError
        with self.assertRaises(ManifestError):
            self._stamp(generator={"name": "g", "version": "v",
                                   "content_kind": 5})

    def test_string_batch_seq_rejected(self):
        from backend.provenance.manifest import ManifestError
        with self.assertRaises(ManifestError):
            self._stamp(batch_seq="x")

    def test_string_actions_rejected(self):
        from backend.provenance.manifest import ManifestError
        with self.assertRaises(ManifestError):
            self._stamp(actions="x")

    def test_minimal_stamp_seals(self):
        out = self._stamp()
        self.assertEqual(len(out["manifest_id"]), 64)
        self.assertIsNone(out["signature"])
        self.assertEqual(out["signature_note"], "UNSIGNED v1")


class TestDuplicateShapes(unittest.TestCase):
    def test_exact_rejects_non_sequence(self):
        from backend.provenance.duplicates import DupError, exact_dup_rate
        with self.assertRaises(DupError):
            exact_dup_rate(5)

    def test_exact_rejects_nested(self):
        from backend.provenance.duplicates import DupError, exact_dup_rate
        with self.assertRaises(DupError):
            exact_dup_rate([{"a": [1]}])

    def test_near_rejects_non_sequence(self):
        from backend.provenance.duplicates import DupError, near_dup_rate
        with self.assertRaises(DupError):
            near_dup_rate(5)

    def test_near_rejects_nan_resolution(self):
        from backend.provenance.duplicates import DupError, near_dup_rate
        with self.assertRaises(DupError):
            near_dup_rate([[0.0]], resolution=float("nan"))

    def test_exact_rate_counts(self):
        from backend.provenance.duplicates import exact_dup_rate
        out = exact_dup_rate([{"a": 1}, {"a": 1}, {"a": 2}])
        self.assertEqual((out["unique"], out["total"]), (2, 3))
        self.assertAlmostEqual(out["rate"], 1.0 - 2.0 / 3.0)


class TestBridgeShapes(unittest.TestCase):
    def _bridge(self, **over):
        from backend.provenance.axiom_bridge import bridge_generation
        kw = {"generator_name": "g", "generator_version": "v",
              "seed": 1, "n_rows": 5, "content_hash": "0" * 64,
              "real_ingredients": [{"kind": "real", "n_rows": 5}]}
        kw.update(over)
        return bridge_generation(**kw)

    def test_non_list_ingredients_rejected(self):
        from backend.provenance.axiom_bridge import BridgeError
        with self.assertRaises(BridgeError):
            self._bridge(real_ingredients=5)

    def test_string_datacard_rejected(self):
        from backend.provenance.axiom_bridge import BridgeError
        with self.assertRaises(BridgeError):
            self._bridge(axiom_datacard="x")

    def test_minimal_bridge_wraps(self):
        out = self._bridge()
        self.assertEqual(len(out["manifest"]["manifest_id"]), 64)
        self.assertEqual(out["mix_batch"]["n_rows"], 5)


class TestEnvelopeShapes(unittest.TestCase):
    def test_non_sequence_trials_rejected(self):
        from backend.eval.envelope import EnvelopeError, infer_envelope
        with self.assertRaises(EnvelopeError):
            infer_envelope(5, param_names=["a"])

    def test_string_names_rejected(self):
        from backend.eval.envelope import EnvelopeError, infer_envelope
        trials = [{"breaks": False, "params": {"a": 1.0}}]
        with self.assertRaises(EnvelopeError):
            infer_envelope(trials, param_names="a")

    def test_nan_value_rejected(self):
        from backend.eval.envelope import EnvelopeError, infer_envelope
        trials = [{"breaks": True, "params": {"f": float("nan")}}]
        with self.assertRaises(EnvelopeError):
            infer_envelope(trials, param_names=["f"])

    def test_marginal_boundary_maps(self):
        from backend.eval.envelope import infer_envelope
        trials = [{"breaks": True, "params": {"f": 2.0}},
                  {"breaks": False, "params": {"f": 1.0}}]
        out = infer_envelope(trials, param_names=["f"])
        self.assertEqual(out["params"]["f"]["min_break"], 2.0)
        self.assertEqual(out["params"]["f"]["max_hold"], 1.0)

    def test_bool_params_and_bool_trials_rejected(self):
        from backend.eval.envelope import EnvelopeError, infer_envelope
        with self.assertRaises(EnvelopeError):
            infer_envelope([{"breaks": True, "params": {"f": True}}],
                           param_names=["f"])
        with self.assertRaises(EnvelopeError):
            infer_envelope([{"breaks": 1, "params": {"f": 1.0}}],
                           param_names=["f"])
        with self.assertRaises(EnvelopeError):
            infer_envelope([{"breaks": None, "params": {"f": 1.0}}],
                           param_names=["f"])
        with self.assertRaises(EnvelopeError):
            infer_envelope(5, param_names=["f"])
        with self.assertRaises(EnvelopeError):
            infer_envelope([5], param_names=["f"])
        with self.assertRaises(EnvelopeError):
            infer_envelope([{"breaks": True, "params": {"f": 1.0}}],
                           param_names="f")


class TestContractShapes(unittest.TestCase):
    def test_tuple_states_accepted(self):
        from backend.eval.skill_contracts import check_skill
        contract = {"skill_id": "s", "pre": lambda s: True,
                    "post": lambda s: True}
        out = check_skill(contract, ({"x": 1},))
        self.assertTrue(out["holds"])

    def test_int_node_id_rejected(self):
        from backend.eval.skill_contracts import SkillContractError, ingest_task_graph
        with self.assertRaises(SkillContractError):
            ingest_task_graph({"nodes": [{"id": 1}], "edges": []})

    def test_dag_orders_deterministically(self):
        from backend.eval.skill_contracts import ingest_task_graph
        out = ingest_task_graph({"nodes": [{"id": "b"}, {"id": "a"}],
                                 "edges": [["a", "b"]]})
        self.assertEqual(out["order"], ["a", "b"])


class TestBackendConstructors(unittest.TestCase):
    def test_fixture_unknown_policy(self):
        from engine.hunt import HuntError as EngineHuntError

        from backend.eval.hunt_backends import FixtureBackend, HuntError
        self.assertIs(HuntError, EngineHuntError)
        with self.assertRaises(HuntError):
            FixtureBackend("nope")

    def test_fixture_seed_type(self):
        from backend.eval.hunt_backends import FixtureBackend, HuntError
        with self.assertRaises(HuntError):
            FixtureBackend("nope", seed="x")

    def test_fixture_threshold_finite(self):
        from backend.eval.hunt_backends import FixtureBackend, HuntError
        with self.assertRaises(HuntError):
            FixtureBackend("nope", threshold=float("nan"))

    def _red(self, **over):
        from backend.eval.hunt_backends import RedTeamBackend
        spec = {"rollout": lambda *a: [], "must_block": True}
        kw = {"policies": {"p": dict(spec)},
              "score_fn": lambda *a: {"label": "BLOCKED"}}
        kw.update(over)
        return RedTeamBackend(**kw)

    def test_red_empty_policies(self):
        from backend.eval.hunt_backends import HuntError
        with self.assertRaises(HuntError):
            self._red(policies={})

    def test_red_int_policy_id(self):
        from backend.eval.hunt_backends import HuntError
        spec = {"rollout": lambda *a: [], "must_block": True}
        with self.assertRaises(HuntError):
            self._red(policies={1: spec})

    def test_red_n_seeds_positive(self):
        from backend.eval.hunt_backends import HuntError
        with self.assertRaises(HuntError):
            self._red(n_seeds=0)

    def test_red_seed_type(self):
        from backend.eval.hunt_backends import HuntError
        with self.assertRaises(HuntError):
            self._red(seed="x")


class TestSpreadCiShapes(unittest.TestCase):
    def test_spread_rejects_non_sequence(self):
        from engine.spread import SpreadError, ensemble_spread
        with self.assertRaises(SpreadError):
            ensemble_spread(5)

    def test_ci_rejects_non_sequence(self):
        from engine.ci import CIError, bootstrap_ci
        with self.assertRaises(CIError):
            bootstrap_ci(5, seed=1)

    def test_ci_rejects_none_seed(self):
        from engine.ci import CIError, bootstrap_ci
        with self.assertRaises(CIError):
            bootstrap_ci([1.0, 2.0], seed=None)

    def test_ci_brackets_mean(self):
        from engine.ci import bootstrap_ci
        out = bootstrap_ci([1.0, 2.0, 3.0], seed=7)
        self.assertLessEqual(out["lo"], out["mean"])
        self.assertLessEqual(out["mean"], out["hi"])
        self.assertEqual(out["n"], 3)


class TestPropertyTimeShapes(unittest.TestCase):
    def test_property_rejects_non_sequence(self):
        from engine.property import PropertyError, check_property
        spec = {"op": "always", "predicate": lambda s: 1.0,
                "name": "n"}
        with self.assertRaises(PropertyError):
            check_property(spec, 5)

    def test_times_rejects_non_sequence(self):
        from engine.success_time import SuccessTimeError, first_success_times
        with self.assertRaises(SuccessTimeError):
            first_success_times(5, lambda s: True)

    def test_summarize_rejects_non_sequence(self):
        from engine.success_time import SuccessTimeError, summarize_times
        with self.assertRaises(SuccessTimeError):
            summarize_times(5)

    def test_censored_counts_as_data(self):
        from engine.success_time import first_success_times, summarize_times
        times = first_success_times([[0, 1], [0, 0]], lambda s: s == 1)
        self.assertEqual(times, [1, None])
        out = summarize_times(times)
        self.assertEqual(out["success_rate"], 0.5)
        self.assertEqual(out["censored"], 1)
        self.assertEqual(out["median_time"], 1.0)


class TestMixShapes(unittest.TestCase):
    def test_add_rejects_bare_dict(self):
        from backend.provenance.mixtrack import MixError, add_generation
        with self.assertRaises(MixError):
            add_generation({}, real_rows=1, synth_batches=[])

    def test_add_rejects_none_batches(self):
        from backend.provenance.mixtrack import MixError, add_generation, new_corpus
        with self.assertRaises(MixError):
            add_generation(new_corpus("c"), real_rows=1,
                           synth_batches=None)

    def test_lineage_rejects_none(self):
        from backend.provenance.mixtrack import MixError, lineage_risk
        with self.assertRaises(MixError):
            lineage_risk(None)

    def test_lineage_rejects_corrupt_gen(self):
        from backend.provenance.mixtrack import MixError, lineage_risk
        with self.assertRaises(MixError):
            lineage_risk({"generations": [{"gen": 0}]})

    def test_accumulate_path(self):
        from backend.provenance.mixtrack import add_generation, lineage_risk, new_corpus
        corpus = new_corpus("c")
        record = add_generation(
            corpus, real_rows=10,
            synth_batches=[{"manifest_id": "m1", "n_rows": 5}])
        self.assertAlmostEqual(record["alpha"], 10.0 / 15.0)
        out = lineage_risk(corpus)
        self.assertEqual(out["verdict"], "ACCUMULATE")


class TestFixtureShapes(unittest.TestCase):
    def test_probe_rejects_non_sequence(self):
        from backend.eval import policy_fixtures as fixtures
        with self.assertRaises(ValueError):
            fixtures.probe_actions(5)

    def test_clean_rejects_none_seed(self):
        from backend.eval import policy_fixtures as fixtures
        with self.assertRaises(ValueError):
            fixtures.clean_rollout([[0, 0]], seed=None)

    def test_playback_rejects_single(self):
        from backend.eval import policy_fixtures as fixtures
        with self.assertRaises(ValueError):
            fixtures.playback_rollout([[0, 0]])

    def test_clean_rejects_non_sequence(self):
        from backend.eval import policy_fixtures as fixtures
        with self.assertRaises(ValueError):
            fixtures.clean_rollout(5, seed=1)

    def test_synthfed_rejects_short_rows(self):
        from backend.eval import policy_fixtures as fixtures
        with self.assertRaises(ValueError):
            fixtures.synthfed_rollout([[0]], seed=1)

    def test_playback_rejects_non_sequence(self):
        from backend.eval import policy_fixtures as fixtures
        with self.assertRaises(ValueError):
            fixtures.playback_rollout(5)

    def test_bool_seeds_and_bool_actions_rejected(self):
        from backend.eval import policy_fixtures as fixtures
        with self.assertRaises(ValueError):
            fixtures.clean_rollout([[0, 0]], seed=True)
        with self.assertRaises(ValueError):
            fixtures.drifty_rollout([[0, 0]], seed=False)
        with self.assertRaises(ValueError):
            fixtures.synthfed_rollout([[0, 0]], seed=False)
        with self.assertRaises(ValueError):
            fixtures.playback_rollout([[0, 0], [1, 1]], seed=True)
        with self.assertRaises(ValueError):
            fixtures.clean_rollout([[0, 0]], seed=1, noise_scale=True)
        with self.assertRaises(ValueError):
            fixtures.clean_rollout([[0, 0]], seed=1, noise_scale="x")
        with self.assertRaises(ValueError):
            fixtures.clean_rollout([[0, 0]], seed=1,
                                   noise_scale=float("nan"))
        with self.assertRaises(ValueError):
            fixtures.drifty_rollout([[0, 0]], seed=1, noise_scale=-1.0)
        with self.assertRaises(ValueError):
            fixtures.playback_rollout([[0, 0], [1, 1]], noise_scale=None)
        with self.assertRaises(ValueError):
            fixtures.reference_actions(horizon=True)
        with self.assertRaises(ValueError):
            fixtures.probe_actions([True])


class TestLiftSummarizeShapes(unittest.TestCase):
    def test_lift_rejects_non_dict_card(self):
        from engine import canonical_hash
        from engine.credibility import can_lift_draft
        envelope = {"card": 5, "card_hash": canonical_hash(5)}
        out = can_lift_draft(envelope)
        self.assertFalse(out["lift"])
        self.assertTrue(any("dict" in r for r in out["reasons"]))

    def test_lift_fail_closed_on_bad_shape(self):
        from engine import canonical_hash
        from engine.credibility import can_lift_draft
        card = {"n": "lots"}
        envelope = {"card": card, "card_hash": canonical_hash(card)}
        out = can_lift_draft(envelope)
        self.assertFalse(out["lift"])
        self.assertTrue(any("fail-closed" in r for r in out["reasons"]))

    def test_summarize_rejects_non_dict(self):
        from engine.hunt import HuntError, summarize
        with self.assertRaises(HuntError):
            summarize(5)

    def test_summarize_rejects_non_list_trials(self):
        from engine.hunt import HuntError, summarize
        with self.assertRaises(HuntError):
            summarize({"trials": 5})


class TestParCliContract(unittest.TestCase):
    def _run(self, argv):
        import contextlib
        import io

        from backend.par_cli import main
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_no_args_usage(self):
        code, out = self._run(["par_cli.py"])
        self.assertEqual(code, 2)
        self.assertIn("usage:", out)

    def test_missing_file(self):
        code, out = self._run(["par_cli.py", "definitely-not-here.json"])
        self.assertEqual(code, 2)
        self.assertIn("cannot read PAR file", out)

    def test_invalid_par_file(self):
        import json
        path = os.path.join(tempfile.gettempdir(), "vv-bad-par.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"nope": 1}, handle)
        try:
            code, out = self._run(["par_cli.py", path])
        finally:
            os.remove(path)
        self.assertEqual(code, 2)
        self.assertIn("PAR INVALID", out)

    def test_valid_par_file(self):
        import json

        from engine.par import build_par
        envelope = build_par(
            policy={"id": "p", "weights": _WHASH},
            release={"parent": _WHASH, "delta": "IN-ODD"},
            gates=[{"id": "g1", "verdict": "PASS"}],
            ledger_head="0" * 64, odd="test cell",
            independence={"builder": "b", "funder": "f",
                          "relationship": "r"})
        path = os.path.join(tempfile.gettempdir(), "vv-good-par.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(envelope, handle)
        try:
            code, out = self._run(["par_cli.py", path])
        finally:
            os.remove(path)
        self.assertEqual(code, 0)
        self.assertIn("policy p", out)


class TestSortedKeySafety(unittest.TestCase):
    def test_grid_rejects_int_param(self):
        from engine.hunt import HuntError, grid_search
        with self.assertRaises(HuntError):
            grid_search(_CalmBackend(), {1: [1.0]}, seed=7, trial_cap=1)

    def test_random_rejects_int_param(self):
        from engine.hunt import HuntError, random_search
        with self.assertRaises(HuntError):
            random_search(_CalmBackend(), {1: (0.0, 1.0)}, seed=7,
                          trial_cap=1)

    def test_compare_rejects_int_gate(self):
        from engine.release import ReleaseError, compare
        gates = [{"gate": 1, "measurement": 1.0, "status": "PASS"}]
        with self.assertRaises(ReleaseError):
            compare(gates, gates, parent_weights_hash="a",
                    child_weights_hash="b")

    def test_exact_rejects_mixed_keys(self):
        from backend.provenance.duplicates import DupError, exact_dup_rate
        with self.assertRaises(DupError):
            exact_dup_rate([{1: "x", "a": "y"}])

    def test_near_rejects_mixed_keys(self):
        from backend.provenance.duplicates import DupError, near_dup_rate
        with self.assertRaises(DupError):
            near_dup_rate([{1: "x", "a": "y"}])


class TestFilelayoutStoreErrors(unittest.TestCase):
    """074: persist layer speaks StoreError only (service maps to 422)."""

    def _store(self):
        from backend.persist.filelayout import FileLayoutStore
        root = tempfile.mkdtemp(prefix="vv-store-")
        self.addCleanup(__import__("shutil").rmtree, root,
                        ignore_errors=True)
        return root, FileLayoutStore(root)

    def test_save_non_serializable_raises_store_error(self):
        from backend.persist.filelayout import StoreError
        root, store = self._store()
        with self.assertRaises(StoreError):
            store.save("runs", "bad", {"x": object()})
        leftovers = [n for n in os.listdir(os.path.join(root, "runs"))]
        self.assertEqual(leftovers, [])

    def test_save_non_dict_raises_store_error(self):
        from backend.persist.filelayout import StoreError
        _, store = self._store()
        with self.assertRaises(StoreError):
            store.save("runs", "bad", ["not", "a", "dict"])

    def test_init_unwritable_root_raises_store_error(self):
        from backend.persist.filelayout import FileLayoutStore, StoreError
        blocker = os.path.join(tempfile.gettempdir(),
                               "vv-blocker-%d" % os.getpid())
        with open(blocker, "w", encoding="utf-8") as handle:
            handle.write("x")
        self.addCleanup(os.remove, blocker)
        with self.assertRaises(StoreError):
            FileLayoutStore(os.path.join(blocker, "sub"))


class TestBoolCounts(unittest.TestCase):
    """087: bool is not a count. True==1 must 422, never silently shrink."""

    def test_hunt_trial_cap_bool(self):
        from engine.hunt import HuntError, grid_search
        with self.assertRaises(HuntError):
            grid_search(_CalmBackend(), {"p": [1.0]}, seed=7,
                        trial_cap=True)

    def test_ci_resamples_bool(self):
        from engine.ci import CIError, bootstrap_ci
        with self.assertRaises(CIError):
            bootstrap_ci([1.0] * 10, seed=1, resamples=True)

    def test_panel_counts_bool(self):
        from engine.panel import PanelError, build_panel, commit
        with self.assertRaises(PanelError):
            commit("s", True)
        with self.assertRaises(PanelError):
            build_panel("s", True, lambda i: {})

    def test_breach_run_bool(self):
        from backend.eval.failure_modes import drift_gate
        with self.assertRaises(FailureModeError):
            drift_gate([[0, 0]], [[0, 0]], threshold=0.5,
                       breach_run=True)

    def test_n_seeds_bool(self):
        from backend.eval.hunt_backends import HuntError, RedTeamBackend
        with self.assertRaises(HuntError):
            RedTeamBackend({"p": {}}, lambda *a: {"label": "x"},
                           n_seeds=True)

    def test_hamming_bool(self):
        from backend.provenance.duplicates import DupError, near_dup_rate
        with self.assertRaises(DupError):
            near_dup_rate([{"x": 1.0}], hamming=True)

    def test_manifest_rows_bool(self):
        from backend.provenance.manifest import ManifestError, stamp_batch
        base = {"generator": {"name": "g", "version": "1"}, "seed": 1,
                "content_hash": "1" * 64}
        with self.assertRaises(ManifestError):
            stamp_batch(n_rows=True,
                        ingredients=[{"kind": "real", "n_rows": 5}],
                        **base)
        with self.assertRaises(ManifestError):
            stamp_batch(n_rows=5,
                        ingredients=[{"kind": "real", "n_rows": True}],
                        **base)

    def test_mixtrack_rows_bool(self):
        from backend.provenance.mixtrack import MixError, add_generation, new_corpus
        corpus = new_corpus("c")
        with self.assertRaises(MixError):
            add_generation(corpus, real_rows=True, synth_batches=[])
        with self.assertRaises(MixError):
            add_generation(corpus, real_rows=0,
                           synth_batches=[{"manifest_id": "m",
                                           "n_rows": True}])


class TestMongoShapes(unittest.TestCase):
    """116: mongo/filelayout error parity, via stub db (no server)."""

    def _store(self, collections):
        from backend.persist.mongo import MongoStore
        store = object.__new__(MongoStore)
        store._db = collections
        return store

    def test_save_failure_is_value_error(self):
        class Boom:
            def replace_one(self, *a, **k):
                raise RuntimeError("bson refused")
        store = self._store({"runs": Boom()})
        with self.assertRaises(ValueError):
            store.save("runs", "r1", {"a": 1})

    def test_save_roundtrip_shape(self):
        saved = {}

        class Mem:
            def replace_one(self, filt, env, upsert=True):
                saved[filt["_id"]] = env

            def find_one(self, filt):
                return saved.get(filt["_id"])

        store = self._store({"runs": Mem()})
        out = store.save("runs", "r1", {"a": 1})
        self.assertEqual(out["doc"], {"a": 1})
        self.assertIn("stored_at", out)
        self.assertNotIn("_id", out)
        self.assertEqual(store.get("runs", "r1")["doc"], {"a": 1})

    def test_get_never_raises(self):
        class Boom:
            def find_one(self, *a):
                raise RuntimeError("down")

        store = self._store({"runs": Boom()})
        self.assertIsNone(store.get("runs", "r1"))
        self.assertIsNone(store.get("nope", "r1"))

    def test_list_ids_propagates_infra(self):
        class Boom:
            def find(self, *a):
                raise RuntimeError("down")

        store = self._store({"runs": Boom()})
        with self.assertRaises(RuntimeError):
            store.list_ids("runs")

    def test_read_ledger_corrupt_is_value_error(self):
        class Cur:
            def sort(self, *a):
                return [{"seq": 1}]

        class Coll:
            def find(self, *a):
                return Cur()

        store = self._store({"ledger": Coll()})
        with self.assertRaises(ValueError) as ctx:
            store.read_ledger()
        self.assertIn("corrupt", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
