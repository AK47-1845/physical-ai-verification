"""Rebuild the 4-story golden pipeline and compare hashes.

Founder runs from meta bro root (no server needed):
  python backend/tools/golden_check.py
Exit 0 = all stories match the committed goldens.
Exit 1 = drift (paste the output back; note the Python version).
Stdlib only.
"""

import json
import os
import platform
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

from backend.tools.golden_lib import build_all, hashes_of  # noqa: E402

GOLDEN_PATH = os.path.join(BASE, "tests", "golden", "stories.json")


def main():
    print(f"python {platform.python_version()} on {platform.system()} "
          f"{platform.machine()}")
    with open(GOLDEN_PATH, encoding="utf-8") as handle:
        golden = json.load(handle)
    built = build_all()
    ok = True
    if built["engine_version"] != golden["engine_version"]:
        print(f"ENGINE VERSION DIFF: built={built['engine_version']} "
              f"golden={golden['engine_version']}")
        ok = False
    rows = []
    for story in sorted(golden["stories"]):
        now = hashes_of(built["stories"][story])
        want = golden["stories"][story]
        diffs = [key for key in sorted(set(now) | set(want))
                 if now.get(key) != want.get(key)]
        rows.append((story, now["verdict"], diffs))
        if diffs:
            ok = False
    print(f"{'story':<10}{'verdict':<10}{'result'}")
    for story, verdict, diffs in rows:
        print(f"{story:<10}{verdict:<10}"
              f"{'PASS' if not diffs else 'FAIL ' + ','.join(diffs)}")
    if not ok:
        print("DRIFT: paste this output back with the python/platform line.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
