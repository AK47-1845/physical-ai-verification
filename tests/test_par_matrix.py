"""PAR tamper matrix: every leaf mutation must fail the offline reader.

Run from meta bro root:  python tests/test_par_matrix.py
Takes valid PAR envelopes (B11: 11 of them - synthetic variants,
the 4 golden PARs, the pinned console PAR), mutates EVERY leaf
(char change, +1, bool flip, None swap, key delete, sibling-key
add at every dict level) and requires read_par (the offline reader
par_cli uses) to report non-OK. An empty survivor list means full
tamper coverage; anything deliberately unhashed must be allowlisted
in par-schema.json as "unhashed-informational" (currently: none).
"""

import copy
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.par import build_par, read_par  # noqa: E402

from backend.tools.golden_lib import build_all as golden_build_all  # noqa: E402
from backend.tools.presets import base_context  # noqa: E402
from backend.tools.presets import load as load_presets  # noqa: E402

W = "sha256:" + "ab" * 32


def valid_envelope():
    return build_par(
        policy={"id": "matrix-policy", "weights": W},
        release={"parent": W, "delta": "IN-ODD"},
        gates=[{"id": "g1", "verdict": "PASS", "measurement": 0.25,
                "evidence": "run:1"},
               {"id": "g2", "verdict": "REVIEW", "measurement": None,
                "evidence": None}],
        ledger_head="cd" * 32,
        independence={"builder": "b", "funder": "f",
                      "relationship": "none"},
        credibility={"gate": "g1", "n": 40, "ok": True},
        worksheet={"route": "part-a", "reviewed": False},
        odd="matrix cell")


def _variant(gates, odd="matrix cell", drop=()):
    kwargs = {"policy": {"id": "matrix-policy", "weights": W},
              "release": {"parent": W, "delta": "IN-ODD"},
              "gates": gates, "ledger_head": "cd" * 32,
              "independence": {"builder": "b", "funder": "f",
                               "relationship": "none"},
              "credibility": {"gate": "g1", "n": 40, "ok": True},
              "worksheet": {"route": "part-a", "reviewed": False},
              "odd": odd}
    for key in drop:
        del kwargs[key]
    return build_par(**kwargs)


def all_envelopes():
    """11 valid envelopes: 6 synthetic + 4 golden + 1 pinned."""
    out = [("synthetic", valid_envelope()),
           ("all-blocked", _variant(
               [{"id": "g1", "verdict": "BLOCKED",
                 "measurement": 0.9, "evidence": "run:2"},
                {"id": "g2", "verdict": "BLOCKED",
                 "measurement": 0.7, "evidence": "run:2"}])),
           ("insufficient", _variant(
               [{"id": "g1", "verdict": "INSUFFICIENT",
                 "measurement": None, "evidence": None}])),
           ("no-optional", _variant(
               [{"id": "g1", "verdict": "PASS",
                 "measurement": 0.1, "evidence": "run:1"}],
               drop=("credibility", "worksheet"))),
           ("odd-long", _variant(
               [{"id": "g1", "verdict": "PASS",
                 "measurement": 0.1, "evidence": "run:1"}],
               odd="cell-" + "x" * 500)),
           ("many-gates", _variant(
               [{"id": f"g{i}", "verdict": v,
                 "measurement": 0.1 * i, "evidence": f"run:{i}"}
                for i, v in enumerate(
                    ["PASS", "REVIEW", "BLOCKED", "INSUFFICIENT",
                     "PASS", "REVIEW"])]))]
    golden = golden_build_all()["stories"]
    for story in ("clean", "drifty", "playback", "synthfed"):
        out.append((f"golden-{story}", golden[story]["par"]))
    pinned = base_context(load_presets()[0])["PAR"]
    out.append(("console-pinned", pinned))
    return out


def mutate_leaf(value):
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value + 1.0
    if isinstance(value, str):
        return value + "X" if value else "X"
    if value is None:
        return "MUT"
    raise AssertionError(f"unhandled leaf type: {type(value).__name__}")


def dicts_and_leaves(node, path=()):
    """Yield (kind, path) for every dict and every leaf under node."""
    if isinstance(node, dict):
        yield ("dict", path)
        for key in sorted(node):
            yield from dicts_and_leaves(node[key], path + (key,))
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            yield from dicts_and_leaves(item, path + (idx,))
    else:
        yield ("leaf", path)


def get_at(root, path):
    node = root
    for step in path:
        node = node[step]
    return node


def set_at(root, path, value):
    node = root
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value


def del_at(root, path):
    node = root
    for step in path[:-1]:
        node = node[step]
    del node[path[-1]]


class TestParMatrix(unittest.TestCase):
    def test_pristine_reads_ok(self):
        envelopes = all_envelopes()
        self.assertEqual(len(envelopes), 11)
        for name, envelope in envelopes:
            result = read_par(envelope)
            self.assertTrue(result["ok"], f"{name}: {result.get('reason')}")

    def test_matrix_no_survivors(self):
        for name, pristine in all_envelopes():
            nodes = list(dicts_and_leaves(pristine))
            self.assertGreater(len(nodes), 20, name)
            survivors = []
            tried = 0
            for kind, path in nodes:
                if kind == "leaf":
                    bad = copy.deepcopy(pristine)
                    set_at(bad, path, mutate_leaf(get_at(bad, path)))
                    tried += 1
                    if read_par(bad)["ok"]:
                        survivors.append(f"leaf {path}")
                else:
                    target_keys = sorted(get_at(pristine, path))
                    for key in target_keys:
                        bad = copy.deepcopy(pristine)
                        del_at(bad, path + (key,))
                        tried += 1
                        if read_par(bad)["ok"]:
                            survivors.append(f"del {path + (key,)}")
                    bad = copy.deepcopy(pristine)
                    set_at(bad, path + ("__evil__",), 1)
                    tried += 1
                    if read_par(bad)["ok"]:
                        survivors.append(f"add-sibling {path}")
            self.assertGreater(tried, 40, name)
            self.assertEqual(survivors, [], name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
