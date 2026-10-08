"""Bench-guard smoke: the tool runs and reports the right shape.

Run from meta bro root:  python tests/test_bench_guard.py
Fast flags (--iters 20) so this stays a smoke test, not a benchmark.
Asserts the header, the caveat line, and one row per shape.
"""

import os
import subprocess
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestBenchGuard(unittest.TestCase):
    def test_runs_and_reports(self):
        proc = subprocess.run(
            [sys.executable, "backend/tools/bench_guard.py",
             "--iters", "20", "--warmup", "5"],
            cwd=BASE, capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1000:])
        lines = proc.stdout.splitlines()
        self.assertTrue(lines[0].startswith("python "))
        self.assertIn("MEASURED on this machine", lines[1])
        self.assertIn("not a safety-rated runtime", lines[1])
        rows = [line.split() for line in lines[3:6]]
        self.assertEqual([row[0] for row in rows],
                         ["16x7", "50x7", "100x30"])
        for row in rows:
            p50, p95, p99 = (float(row[1]), float(row[2]), float(row[3]))
            self.assertGreater(p50, 0.0)
            self.assertLessEqual(p50, p95)
            self.assertLessEqual(p95, p99)


if __name__ == "__main__":
    unittest.main(verbosity=2)
