"""Time the M2 guard (check_chunk) on representative chunk shapes.

Founder/dev runs from meta bro root (no server needed):
  python backend/tools/bench_guard.py [--iters N] [--warmup N]
Prints p50/p95/p99 per-call latency in microseconds per shape.
Stdlib only. Numbers are descriptive, not a safety claim.
"""

import argparse
import os
import platform
import random
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.guard import check_chunk  # noqa: E402

SHAPES = [(16, 7), (50, 7), (100, 30)]


def _workload(steps: int, joints: int, seed: int):
    rng = random.Random(seed)
    positions = [[rng.uniform(-1.0, 1.0) for _ in range(joints)]
                 for _ in range(steps)]
    limits = {"position": [[-2.0, 2.0]] * joints,
              "velocity": [5.0] * joints,
              "acceleration": [50.0] * joints}
    return positions, limits


def bench_shape(steps: int, joints: int, iters: int, warmup: int):
    positions, limits = _workload(steps, joints, seed=7)
    for _ in range(warmup):
        check_chunk(positions, limits, dt=0.01)
    samples = []
    for _ in range(iters):
        start = time.perf_counter()
        check_chunk(positions, limits, dt=0.01)
        samples.append((time.perf_counter() - start) * 1e6)
    samples.sort()
    def pick(q):
        return samples[min(len(samples) - 1, int(q * len(samples)))]
    return {"shape": f"{steps}x{joints}", "iters": iters,
            "p50_us": round(pick(0.50), 1),
            "p95_us": round(pick(0.95), 1),
            "p99_us": round(pick(0.99), 1)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="bench the M2 guard")
    parser.add_argument("--iters", type=int, default=2000)
    parser.add_argument("--warmup", type=int, default=200)
    args = parser.parse_args(argv)
    if args.iters < 1 or args.warmup < 0:
        print("need --iters >= 1 and --warmup >= 0")
        return 2
    print(f"python {platform.python_version()} on {platform.system()} "
          f"{platform.machine()}")
    print("MEASURED on this machine - Python reference implementation, "
          "not a safety-rated runtime")
    print(f"{'shape':<10}{'p50_us':>10}{'p95_us':>10}{'p99_us':>10}")
    for steps, joints in SHAPES:
        row = bench_shape(steps, joints, args.iters, args.warmup)
        print(f"{row['shape']:<10}{row['p50_us']:>10}"
              f"{row['p95_us']:>10}{row['p99_us']:>10}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
