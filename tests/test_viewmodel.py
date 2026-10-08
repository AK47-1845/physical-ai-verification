"""Release view-model goldens + behavior.

Run from meta bro root:  python tests/test_viewmodel.py
Builds the release view for the 4 golden stories and pins the full
JSON under tests/golden/viewmodel_<story>.json. Updating: add a
D-night-N entry to backend/docs/DECISIONS.md FIRST, then run with
--update-viewmodel (refused unless DECISIONS.md is newer than the
goldens). Also asserts: clean-vs-drifty deltas flag regressions,
generated strings pass the claims patterns, INSUFFICIENT never
renders pass-like. Route 404/422 paths live in test_error_contract.
"""

import json
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))
sys.path.insert(0, os.path.join(BASE, "tests"))

from engine.scorer import evaluate_gate, evaluate_scorecard  # noqa: E402
from test_claims_lint import NEGATION, PATTERNS  # noqa: E402

from backend.eval.viewmodel import build_release_view  # noqa: E402
from backend.tools.golden_lib import build_all  # noqa: E402

STORIES = ("clean", "drifty", "playback", "synthfed")
DECISIONS_PATH = os.path.join(BASE, "backend", "docs", "DECISIONS.md")


def golden_path(story: str) -> str:
    return os.path.join(BASE, "tests", "golden", f"viewmodel_{story}.json")


_BUILT = None


def fixtures():
    """Seed-equivalent docs per story: {story: (run_id, run, dossier)}."""
    global _BUILT
    if _BUILT is None:
        _BUILT = build_all()["stories"]
    docs = {}
    for story in STORIES:
        art = _BUILT[story]
        run_id = f"run_vm_{story}"
        run = {"scorecard": art["scorecard"],
               "policy_id": f"golden-{story}"}
        dossier = {"par": art["par"], "runs": [run_id],
                   "ledger_index": 0, "worksheet": None}
        docs[story] = (run_id, run, dossier)
    return docs


def current_view(story: str) -> dict:
    run_id, run, dossier = fixtures()[story]
    return build_release_view(run, run_id, dossier=dossier)


def write_goldens():
    for story in STORIES:
        text = json.dumps(current_view(story), indent=2,
                          sort_keys=True) + "\n"
        with open(golden_path(story), "w", encoding="utf-8",
                  newline="\n") as handle:
            handle.write(text)


def iter_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from iter_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from iter_strings(value)


class TestViewmodel(unittest.TestCase):
    def test_goldens_match(self):
        for story in STORIES:
            path = golden_path(story)
            self.assertTrue(os.path.isfile(path),
                            f"missing {path}: run with --update-viewmodel")
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(current_view(story), json.load(handle),
                                 f"viewmodel drift in {story}")

    def test_golden_files_canonical(self):
        for story in STORIES:
            with open(golden_path(story), encoding="utf-8",
                      newline="") as handle:
                raw = handle.read()
            self.assertEqual(raw, json.dumps(json.loads(raw), indent=2,
                                             sort_keys=True) + "\n")

    def test_story_verdicts_and_chips(self):
        clean = current_view("clean")
        self.assertEqual(clean["verdict"], "TRUSTED")
        self.assertEqual(clean["what_would_change"], [])
        self.assertEqual([c["label"] for c in clean["chips"]],
                         ["DRAFT", "UNSIGNED"])
        drifty = current_view("drifty")
        self.assertEqual(drifty["verdict"], "REVIEW")
        self.assertTrue(drifty["what_would_change"])
        self.assertTrue(drifty["headline"])
        blocked = current_view("playback")
        self.assertEqual(blocked["verdict"], "BLOCKED")
        self.assertIn("Do not ship", blocked["verdict_plain"])

    def test_deltas_flag_regressions(self):
        docs = fixtures()
        run_id, run, dossier = docs["drifty"]
        cru_id, cru, _ = docs["clean"]
        worse = build_release_view(run, run_id, compare=cru,
                                   compare_id=cru_id, dossier=dossier)
        self.assertTrue(any(d["regression"] for d in worse["deltas"]),
                        worse["deltas"])
        better = build_release_view(cru, cru_id, compare=run,
                                    compare_id=run_id, dossier=dossier)
        self.assertFalse(any(d["regression"] for d in better["deltas"]))

    def test_generated_strings_pass_claims(self):
        texts = []
        for story in STORIES:
            texts.extend(iter_strings(current_view(story)))
        docs = fixtures()
        run_id, run, dossier = docs["drifty"]
        cru_id, cru, _ = docs["clean"]
        texts.extend(iter_strings(build_release_view(
            run, run_id, compare=cru, compare_id=cru_id,
            dossier=dossier)))
        for text in texts:
            for word, regex in PATTERNS:
                match = regex.search(text)
                if not match:
                    continue
                before = text[max(0, match.start() - 40):match.start()]
                if NEGATION.search(before):
                    continue
                self.fail(f"claim word [{word}] in {text!r}")

    def test_insufficient_never_passlike(self):
        grey = evaluate_gate("g1", 0.1, green=0.2, amber=0.5,
                             evidence="ev:1", min_n=30, n=2)
        green = evaluate_gate("g2", 0.1, green=0.2, amber=0.5,
                              evidence="ev:2")
        card = evaluate_scorecard([grey, green], profile_version="draft-0",
                                  seed=0)
        view = build_release_view({"scorecard": card, "policy_id": "p"},
                                  "run_vm_grey")
        self.assertEqual(view["verdict"], "REVIEW")
        self.assertTrue(view["verdict_plain"].startswith(
            "Not enough evidence"))
        self.assertIn("lack", view["headline"])
        self.assertIn("INSUFFICIENT",
                      [c["label"] for c in view["chips"]])
        self.assertNotIn("Passed", view["verdict_plain"])


def maybe_update(argv):
    if "--update-viewmodel" not in argv:
        return False
    missing = [s for s in STORIES
               if not os.path.isfile(golden_path(s))]
    if not missing:
        oldest = min(os.path.getmtime(golden_path(s)) for s in STORIES)
        if os.path.getmtime(DECISIONS_PATH) <= oldest:
            print("REFUSED: add a D-night-N entry to backend/docs/"
                  "DECISIONS.md first (it must be newer than the goldens)")
            return True
    write_goldens()
    print("viewmodel goldens written"
          + (" (bootstrap)" if missing else ""))
    return True


if __name__ == "__main__":
    if not maybe_update(sys.argv):
        unittest.main(verbosity=2)
