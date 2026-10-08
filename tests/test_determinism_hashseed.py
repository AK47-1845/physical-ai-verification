"""Determinism across hash seeds: same bytes under PYTHONHASHSEED.

Run from meta bro root:  python tests/test_determinism_hashseed.py
Builds the full 4-story pipeline in fresh subprocesses under three
different hash seeds and requires byte-identical canonical output
on the same platform.
Catches set-iteration / str-hash order leaks into artifacts.
"""

import os
import subprocess
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKGS = os.path.join(BASE, "packages")

CHILD = (
    "import sys; "
    f"sys.path.insert(0, {BASE!r}); "
    f"sys.path.insert(0, {PKGS!r}); "
    "from backend.tools.golden_lib import build_all; "
    "from engine.canon import canonical_bytes; "
    "sys.stdout.buffer.write(canonical_bytes(build_all()))"
)


def run_with_seed(seed):
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = str(seed)
    proc = subprocess.run(
        [sys.executable, "-c", CHILD], env=env, cwd=BASE,
        capture_output=True, timeout=180)
    if proc.returncode != 0:
        raise AssertionError(
            f"seed {seed}: child failed:\n{proc.stderr.decode()[-2000:]}")
    return proc.stdout


class TestHashseedDeterminism(unittest.TestCase):
    def test_identical_bytes_across_seeds(self):
        outs = [run_with_seed(seed) for seed in (0, 1, 12345)]
        self.assertTrue(outs[0])
        self.assertEqual(outs[1], outs[0])
        self.assertEqual(outs[2], outs[0])

    def test_output_is_canonical_json(self):
        out = run_with_seed(0)
        self.assertTrue(out.startswith(b'{"engine_version"'))
        self.assertNotIn(b" ", out[:200])


if __name__ == "__main__":
    unittest.main(verbosity=2)
