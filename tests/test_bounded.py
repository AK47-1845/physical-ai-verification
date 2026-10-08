"""M3 bounded-verifier tests: PROVEN / VIOLATED / UNKNOWN.

Run from meta bro root:  python tests/test_bounded.py
(stdlib only)
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "packages"))

from engine.bounded import BoundedError, verify_affine_relu  # noqa: E402


def _layer(weights, bias, activation="linear"):
    return {"weights": weights, "bias": bias, "activation": activation}


class TestBounded(unittest.TestCase):
    def test_proven_inside(self):
        out = verify_affine_relu([_layer([[0.5]], [0.0])], [[0.0, 1.0]],
                                 [[-0.5, 1.0]])
        self.assertEqual(out["verdict"], "PROVEN")
        self.assertIsNone(out["witness"])

    def test_boundary_exact_is_unknown(self):
        # D-night-19: outward rounding costs boundary-exact proofs.
        # True range [0, 0.5] sits inside [0, 1], but the widened
        # interval exceeds the bound by ~1ulp, so the honest answer
        # is UNKNOWN (restate with margin to prove).
        out = verify_affine_relu([_layer([[0.5]], [0.0])], [[0.0, 1.0]],
                                 [[0.0, 1.0]])
        self.assertEqual(out["verdict"], "UNKNOWN")
        self.assertIsNone(out["witness"])

    def test_violated_with_witness(self):
        out = verify_affine_relu([_layer([[2.0]], [0.0])], [[0.0, 1.0]],
                                 [[0.0, 1.0]], grid_per_dim=3)
        self.assertEqual(out["verdict"], "VIOLATED")
        self.assertEqual(out["witness"]["input"], [1.0])
        self.assertEqual(out["witness"]["output"], [2.0])

    def test_unknown_overapprox(self):
        # y = relu(x) - relu(x - 0.6): interval [-0.4, 1] exceeds [0, 0.6]
        # but the true range is [0, 0.6] and the coarse grid misses nothing
        out = verify_affine_relu(
            [_layer([[1.0], [1.0]], [0.0, -0.6], "relu"),
             _layer([[1.0, -1.0]], [0.0])],
            [[0.0, 1.0]], [[0.0, 0.6]], grid_per_dim=3)
        self.assertEqual(out["verdict"], "UNKNOWN")
        self.assertIsNone(out["witness"])

    def test_relu_clamps(self):
        out = verify_affine_relu([_layer([[-1.0]], [0.0], "relu")],
                                 [[0.0, 1.0]], [[0.0, 0.5]])
        self.assertEqual(out["verdict"], "PROVEN")

    def test_shape_errors_raise(self):
        with self.assertRaises(BoundedError):
            verify_affine_relu([_layer([[1.0, 2.0]], [0.0])], [[0.0, 1.0]],
                               [[0.0, 1.0]])
        with self.assertRaises(BoundedError):
            verify_affine_relu([], [[0.0, 1.0]], [[0.0, 1.0]])

    def test_grid_cap_raises(self):
        # interval [0, 12] exceeds [0, 11]: must reach the grid, then refuse
        with self.assertRaises(BoundedError):
            verify_affine_relu([_layer([[1.0] * 6], [0.0])],
                               [[0.0, 2.0]] * 6, [[0.0, 11.0]],
                               grid_per_dim=10)

    def test_bool_values_rejected(self):
        with self.assertRaises(BoundedError):
            verify_affine_relu([_layer([[True]], [0.0])], [[0.0, 1.0]],
                               [[0.0, 1.0]])
        with self.assertRaises(BoundedError):
            verify_affine_relu([_layer([[0.5]], [0.0])], [[True, 1.0]],
                               [[0.0, 1.0]])

    def test_tuple_structures_accepted(self):
        as_list = verify_affine_relu([_layer([[0.5]], [0.0])],
                                     [[0.0, 1.0]], [[0.0, 1.0]])
        as_tuple = verify_affine_relu(
            ({"weights": ((0.5,),), "bias": (0.0,),
              "activation": "linear"},),
            ((0.0, 1.0),), ((0.0, 1.0),))
        self.assertEqual(as_tuple["verdict"], as_list["verdict"])
        self.assertEqual(as_tuple["output_box"], as_list["output_box"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
