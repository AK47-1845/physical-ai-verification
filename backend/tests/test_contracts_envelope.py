"""Contract + envelope tests: skills, task DAGs, boundary maps.

Run from meta bro root:  python backend/tests/test_contracts_envelope.py
(stdlib only)
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from backend.eval.envelope import EnvelopeError, infer_envelope  # noqa: E402
from backend.eval.skill_contracts import SkillContractError, check_skill, ingest_task_graph  # noqa: E402

PICK = {"skill_id": "pick", "version": "1",
        "pre": lambda s: s["gripper"] == "open",
        "post": lambda s: s["holding"] is True,
        "invariant": lambda s: s["x"] >= 0.0}


class TestSkillContracts(unittest.TestCase):
    def test_holds(self):
        states = [{"gripper": "open", "holding": False, "x": 1.0},
                  {"gripper": "open", "holding": True, "x": 2.0}]
        out = check_skill(PICK, states)
        self.assertTrue(out["holds"])
        self.assertIsNone(out["failing_index"])

    def test_pre_fails(self):
        states = [{"gripper": "closed", "holding": True, "x": 1.0}]
        out = check_skill(PICK, states)
        self.assertFalse(out["pre"])
        self.assertFalse(out["holds"])

    def test_invariant_first_failure_index(self):
        states = [{"gripper": "open", "holding": False, "x": 1.0},
                  {"gripper": "open", "holding": False, "x": -2.0},
                  {"gripper": "open", "holding": True, "x": -3.0}]
        out = check_skill(PICK, states)
        self.assertFalse(out["invariant"])
        self.assertEqual(out["failing_index"], 1)
        self.assertFalse(out["holds"])

    def test_no_invariant(self):
        contract = {"skill_id": "s", "pre": lambda s: True,
                    "post": lambda s: True}
        out = check_skill(contract, [{"a": 1}])
        self.assertIsNone(out["invariant"])
        self.assertTrue(out["holds"])

    def test_raising_predicate_raises(self):
        bad = {"skill_id": "s", "pre": lambda s: 1 / 0,
               "post": lambda s: True}
        with self.assertRaises(SkillContractError):
            check_skill(bad, [{"a": 1}])

    def test_nonbool_predicate_raises(self):
        bad = {"skill_id": "s", "pre": lambda s: "yes",
               "post": lambda s: True}
        with self.assertRaises(SkillContractError):
            check_skill(bad, [{"a": 1}])


class TestTaskGraph(unittest.TestCase):
    def test_deterministic_order(self):
        graph = {"nodes": [{"id": "c"}, {"id": "a"}, {"id": "b"}],
                 "edges": [["a", "b"], ["b", "c"]]}
        out = ingest_task_graph(graph)
        self.assertEqual(out["order"], ["a", "b", "c"])
        self.assertEqual([c["task"] for c in out["ingredient_chain"]],
                         ["a", "b", "c"])

    def test_diamond_tiebreak_sorted(self):
        graph = {"nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"},
                           {"id": "d"}],
                 "edges": [["a", "b"], ["a", "c"], ["b", "d"], ["c", "d"]]}
        out = ingest_task_graph(graph)
        self.assertEqual(out["order"], ["a", "b", "c", "d"])

    def test_cycle_rejected(self):
        graph = {"nodes": [{"id": "a"}, {"id": "b"}],
                 "edges": [["a", "b"], ["b", "a"]]}
        with self.assertRaises(SkillContractError):
            ingest_task_graph(graph)

    def test_dangling_edge_rejected(self):
        graph = {"nodes": [{"id": "a"}], "edges": [["a", "ghost"]]}
        with self.assertRaises(SkillContractError):
            ingest_task_graph(graph)

    def test_duplicate_id_rejected(self):
        graph = {"nodes": [{"id": "a"}, {"id": "a"}], "edges": []}
        with self.assertRaises(SkillContractError):
            ingest_task_graph(graph)

    def test_unhashable_endpoints_rejected(self):
        nodes = [{"id": "a"}, {"id": "b"}]
        for bad in ([["a"], "b"], ["a", {"id": "b"}], [None, "b"]):
            graph = {"nodes": nodes, "edges": [bad]}
            with self.assertRaises(SkillContractError, msg=bad):
                ingest_task_graph(graph)


class TestEnvelope(unittest.TestCase):
    TRIALS = [
        {"params": {"noise": 0.0, "bias": 0.0}, "breaks": False},
        {"params": {"noise": 0.2, "bias": 0.1}, "breaks": False},
        {"params": {"noise": 0.4, "bias": 0.1}, "breaks": True},
        {"params": {"noise": 0.3, "bias": 0.5}, "breaks": True},
    ]

    def test_marginal_boundaries(self):
        out = infer_envelope(self.TRIALS, param_names=["noise", "bias"])
        noise = out["params"]["noise"]
        self.assertEqual((noise["min_break"], noise["max_break"]),
                         (0.3, 0.4))
        self.assertEqual((noise["min_hold"], noise["max_hold"]), (0.0, 0.2))
        bias = out["params"]["bias"]
        self.assertEqual((bias["min_break"], bias["max_break"]), (0.1, 0.5))
        self.assertIn("MARGINAL", out["note"])

    def test_no_breaks_none_boundaries(self):
        trials = [{"params": {"x": 1.0}, "breaks": False}]
        out = infer_envelope(trials, param_names=["x"])
        self.assertIsNone(out["params"]["x"]["min_break"])
        self.assertEqual(out["params"]["x"]["max_hold"], 1.0)

    def test_empty_raises(self):
        with self.assertRaises(EnvelopeError):
            infer_envelope([], param_names=["x"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
