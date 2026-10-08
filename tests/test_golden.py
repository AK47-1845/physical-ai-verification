"""Golden hashes for the 4-story pipeline.

Run from meta bro root:  python tests/test_golden.py
Updating: add a D-night-N entry to backend/docs/DECISIONS.md FIRST,
then:  python tests/test_golden.py --update-golden
The updater refuses unless DECISIONS.md is newer than the golden file
(no silent re-baselining).
"""

import json
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from backend.tools.golden_lib import build_all, hashes_of  # noqa: E402

GOLDEN_PATH = os.path.join(BASE, "tests", "golden", "stories.json")
DECISIONS_PATH = os.path.join(BASE, "backend", "docs", "DECISIONS.md")


def load_golden():
    with open(GOLDEN_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def current_hashes():
    built = build_all()
    return {"version": 1, "engine_version": built["engine_version"],
            "stories": {name: hashes_of(art)
                        for name, art in built["stories"].items()}}


def write_golden(doc):
    os.makedirs(os.path.dirname(GOLDEN_PATH), exist_ok=True)
    text = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    with open(GOLDEN_PATH, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


class TestGolden(unittest.TestCase):
    def test_hashes_match(self):
        golden = load_golden()
        now = current_hashes()
        self.assertEqual(now["engine_version"], golden["engine_version"])
        self.assertEqual(set(now["stories"]), set(golden["stories"]))
        for story in sorted(now["stories"]):
            self.assertEqual(
                now["stories"][story], golden["stories"][story],
                f"golden drift in {story}: add a DECISIONS.md entry, "
                f"then run with --update-golden")

    def test_golden_file_canonical(self):
        with open(GOLDEN_PATH, encoding="utf-8", newline="") as handle:
            raw = handle.read()
        self.assertEqual(raw, json.dumps(json.loads(raw), indent=2,
                                         sort_keys=True) + "\n")


def maybe_update(argv):
    if "--update-golden" not in argv:
        return False
    if not os.path.isfile(DECISIONS_PATH) or not os.path.isfile(
            GOLDEN_PATH):
        print("need DECISIONS.md and an existing golden file")
        return True
    if os.path.getmtime(DECISIONS_PATH) <= os.path.getmtime(GOLDEN_PATH):
        print("REFUSED: add a D-night-N entry to backend/docs/"
              "DECISIONS.md first (it must be newer than stories.json)")
        return True
    write_golden(current_hashes())
    print(f"updated {GOLDEN_PATH}")
    return True


if __name__ == "__main__":
    if not maybe_update(sys.argv):
        unittest.main(verbosity=2)
