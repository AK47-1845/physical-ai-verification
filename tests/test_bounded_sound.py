"""Bounded-verifier soundness: outward rounding + fuzz + certificates.

Run from meta bro root:  python tests/test_bounded_sound.py
H5.1: naive float intervals can exclude the TRUE range by rounding
(1e16+1 rounds to 1e16), making PROVEN false. The fix widens every
interval op by 1ulp outward (math.nextafter). Directed cases use
Fraction-exact references (float sampling can never catch 1-ulp
unsoundness: samples share the same rounding). Seeded fuzz checks
float intervals against exact Fraction propagation, PROVEN =>
no sampled counterexample, and VIOLATED witness replay in exact
arithmetic. Completeness cost, documented: boundary-exact proofs
flip PROVEN -> UNKNOWN (D-night-19); over-budget grids keep
raising instead of guessing (D-night-18).
"""

import itertools
import os
import random
import sys
import unittest
from fractions import Fraction

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine import ENGINE_VERSION  # noqa: E402
from engine.bounded import BoundedError, verify_affine_relu  # noqa: E402


def _mult():
    """Trial multiplier (VV_FUZZ_MULT=10 for B11 depth). Capped."""
    try:
        return min(max(1, int(os.environ.get("VV_FUZZ_MULT", "1"))),
                   100)
    except ValueError:
        return 1


MULT = _mult()


def _layer(weights, bias, activation="linear"):
    return {"weights": weights, "bias": bias, "activation": activation}


def _exact_affine(weights, bias, box):
    out = []
    for row, offset in zip(weights, bias):
        lo = Fraction(offset)
        hi = Fraction(offset)
        for w, (blo, bhi) in zip(row, box):
            w = Fraction(w)
            if w >= 0:
                lo += w * Fraction(blo)
                hi += w * Fraction(bhi)
            else:
                lo += w * Fraction(bhi)
                hi += w * Fraction(blo)
        out.append([lo, hi])
    return out


def _exact_relu(box):
    return [[max(Fraction(0), lo), max(Fraction(0), hi)] for lo, hi in box]


def _exact_interval(layers, box):
    cur = [[[Fraction(lo), Fraction(hi)] for lo, hi in box]][0]
    for layer in layers:
        cur = _exact_affine(layer["weights"], layer["bias"], cur)
        if layer["activation"] == "relu":
            cur = _exact_relu(cur)
    return cur


def _exact_eval(layers, point):
    vals = [Fraction(v) for v in point]
    for layer in layers:
        nxt = []
        for row, offset in zip(layer["weights"], layer["bias"]):
            nxt.append(Fraction(offset) + sum(
                Fraction(w) * v for w, v in zip(row, vals)))
        if layer["activation"] == "relu":
            nxt = [max(Fraction(0), v) for v in nxt]
        vals = nxt
    return vals


class TestOutwardRounding(unittest.TestCase):
    def test_hi_side_rounding_covered(self):
        out = verify_affine_relu([_layer([[1e16]], [1.0])], [[1, 1]],
                                 [[0.0, 2e16]])
        self.assertGreaterEqual(out["output_box"][0][1], 10000000000000001)

    def test_lo_side_rounding_covered(self):
        out = verify_affine_relu([_layer([[1.0]], [-1e16])], [[-1, -1]],
                                 [[-2e16, 0.0]])
        self.assertLessEqual(out["output_box"][0][0], -10000000000000001)

    def test_exact_range_inside_float_interval(self):
        out = verify_affine_relu([_layer([[1e16]], [1.0])], [[1, 1]],
                                 [[0.0, 2e16]])
        lo, hi = out["output_box"][0]
        self.assertLessEqual(lo, 10000000000000001)
        self.assertGreaterEqual(hi, 10000000000000001)


class TestCertificate(unittest.TestCase):
    def test_scope_fields_present(self):
        out = verify_affine_relu(
            [_layer([[0.5]], [0.0])], [[0.0, 1.0]], [[-0.5, 1.0]],
            model_hash="sha256:" + "ab" * 32)
        cert = out["certificate"]
        self.assertEqual(cert["model_hash"], "sha256:" + "ab" * 32)
        self.assertEqual(cert["domain"], [[0.0, 1.0]])
        self.assertEqual(cert["method"], "interval+grid")
        self.assertEqual(cert["engine_version"], ENGINE_VERSION)
        self.assertTrue(cert["assumptions"])
        self.assertIn("ab" * 8, out["scope"])
        self.assertIn("PROVEN", out["scope"])

    def test_unpinned_model_noted(self):
        out = verify_affine_relu([_layer([[0.5]], [0.0])], [[0.0, 1.0]],
                                 [[-0.5, 1.0]])
        cert = out["certificate"]
        self.assertIsNone(cert["model_hash"])
        self.assertTrue(any("NOT pinned" in a
                            for a in cert["assumptions"]))
        self.assertIn("UNPINNED", out["scope"])


class TestSoundnessFuzz(unittest.TestCase):
    def test_fuzz_against_exact(self):
        rng = random.Random(1234)
        for _case in range(60 * MULT):
            n_layers = rng.choice([1, 2])
            dims = [rng.randint(1, 3)]
            for _ in range(n_layers):
                dims.append(rng.randint(1, 3))
            layers = []
            for li in range(n_layers):
                weights = [[rng.randint(-3, 3) for _ in range(dims[li])]
                           for _ in range(dims[li + 1])]
                bias = [rng.randint(-2, 2) for _ in range(dims[li + 1])]
                layers.append(_layer(weights, bias,
                                     rng.choice(["linear", "relu"])))
            box = []
            for _ in range(dims[0]):
                a, b = rng.randint(-2, 2), rng.randint(-2, 2)
                box.append([min(a, b), max(a, b)])
            exact = _exact_interval(layers, box)
            out = verify_affine_relu(layers, box,
                                     [[0.0, 0.0]] * dims[-1],
                                     grid_per_dim=2)
            for (lo, hi), (elo, ehi) in zip(out["output_box"], exact):
                self.assertLessEqual(lo, elo)
                self.assertGreaterEqual(hi, ehi)
            # PROVEN with margin: no sampled counterexample allowed.
            margin_bounds = [[float(elo) - 0.5, float(ehi) + 0.5]
                             for elo, ehi in exact]
            proved = verify_affine_relu(layers, box, margin_bounds,
                                        grid_per_dim=2)
            self.assertEqual(proved["verdict"], "PROVEN")
            for _ in range(300 * MULT):
                pt = [rng.uniform(lo, hi) for lo, hi in box]
                vals = _exact_eval(layers, [Fraction(v) for v in pt])
                for v, (blo, bhi) in zip(vals, margin_bounds):
                    self.assertLessEqual(float(blo) - 1e-9, float(v))
                    self.assertGreaterEqual(float(bhi) + 1e-9, float(v))
            # VIOLATED via a corner-anchored cut: the grid's exact
            # lo-corner provably violates, so the witness exists and
            # must replay in exact arithmetic (0.5 deep; float noise
            # is ~1e-15 and cannot fake it).
            corners = list(itertools.product(*[[lo, hi] for lo, hi in box]))
            corner_outs = [_exact_eval(layers, list(c)) for c in corners]
            cut = []
            for d in range(dims[-1]):
                vals_d = [o[d] for o in corner_outs]
                cut.append([float(min(vals_d)) + 0.5,
                            float(max(vals_d)) + 0.5])
            bad = verify_affine_relu(layers, box, cut, grid_per_dim=5)
            self.assertEqual(bad["verdict"], "VIOLATED")
            wit = bad["witness"]
            exact_out = _exact_eval(layers, wit["input"])
            hit = any(float(v) < blo - 1e-9 or float(v) > bhi + 1e-9
                      for v, (blo, bhi) in zip(exact_out, cut))
            self.assertTrue(hit, f"spurious witness {wit}")


class TestBudgetHonesty(unittest.TestCase):
    def test_over_budget_raises_not_guesses(self):
        # D-night-18: over-budget grids raise (caller coarsens);
        # returning UNKNOWN would claim a search that never ran.
        with self.assertRaises(BoundedError):
            verify_affine_relu([_layer([[1.0] * 6], [0.0])],
                               [[0.0, 2.0]] * 6, [[0.0, 11.0]],
                               grid_per_dim=10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
