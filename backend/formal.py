from __future__ import annotations

import time
from typing import Annotated, Literal, Self

import z3
from pydantic import Field, model_validator

from backend.engine import fingerprint
from backend.schemas import Number, StrictModel


class NetworkLayer(StrictModel):
    weights: list[Annotated[list[Number], Field(min_length=1, max_length=8)]] = Field(min_length=1, max_length=8)
    bias: list[Number] = Field(min_length=1, max_length=8)
    activation: Literal["relu", "linear"] = "linear"


class BoundQuery(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    input_lower: list[Number] = Field(min_length=1, max_length=6)
    input_upper: list[Number] = Field(min_length=1, max_length=6)
    layers: list[NetworkLayer] = Field(min_length=1, max_length=3)
    output_lower: list[Number] = Field(min_length=1, max_length=8)
    output_upper: list[Number] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def compatible(self) -> Self:
        if len(self.input_lower) != len(self.input_upper):
            raise ValueError("Input bounds must align")
        if len(self.output_lower) != len(self.output_upper):
            raise ValueError("Output bounds must align")
        for lower, upper in zip(self.input_lower + self.output_lower, self.input_upper + self.output_upper):
            if lower > upper:
                raise ValueError("Lower bounds must not exceed upper bounds")
        width = len(self.input_lower)
        for layer in self.layers:
            if len(layer.weights) != len(layer.bias) or any(len(row) != width for row in layer.weights):
                raise ValueError("Network layer shapes must align exactly")
            width = len(layer.bias)
        if width != len(self.output_lower):
            raise ValueError("Output bounds must match final layer width")
        return self


def verify_bounds(query: BoundQuery) -> dict:
    started = time.perf_counter()
    context = z3.Context()
    solver = z3.Solver(ctx=context)
    solver.set(timeout=2000, rlimit=500_000)
    inputs = [z3.Real(f"input_{index}", ctx=context) for index in range(len(query.input_lower))]
    for variable, lower, upper in zip(inputs, query.input_lower, query.input_upper):
        solver.add(variable >= z3.RealVal(str(lower), ctx=context), variable <= z3.RealVal(str(upper), ctx=context))
    outputs = inputs
    for layer in query.layers:
        next_outputs = []
        for weights, bias in zip(layer.weights, layer.bias):
            value = z3.Sum([z3.RealVal(str(weight), ctx=context) * variable for weight, variable in zip(weights, outputs)]) + z3.RealVal(str(bias), ctx=context)
            next_outputs.append(z3.If(value >= 0, value, z3.RealVal(0, ctx=context)) if layer.activation == "relu" else value)
        outputs = next_outputs
    solver.add(z3.Or([z3.Or(value < z3.RealVal(str(lower), ctx=context), value > z3.RealVal(str(upper), ctx=context))
                      for value, lower, upper in zip(outputs, query.output_lower, query.output_upper)]))
    smt = solver.to_smt2()
    outcome = solver.check()
    status = "VERIFIED_BOX" if outcome == z3.unsat else "COUNTEREXAMPLE" if outcome == z3.sat else "INCONCLUSIVE"
    counterexample = None
    if outcome == z3.sat:
        model = solver.model()
        counterexample = {"input_exact": [str(model.eval(variable, model_completion=True)) for variable in inputs],
                          "output_exact": [str(model.eval(value, model_completion=True)) for value in outputs]}
    return {"status": status, "query_hash": fingerprint(query.model_dump()), "solver": f"Z3 {z3.get_version_string()}",
            "duration_ms": round((time.perf_counter() - started) * 1000, 3), "counterexample": counterexample,
            "reason": solver.reason_unknown() if outcome == z3.unknown else None,
            "smt2": smt, "semantics": "Exact rational feedforward affine/ReLU network within the supplied input box",
            "limitations": ["Not a full VLA, closed-loop, collision, or robot safety proof.",
                            "Decimal coefficients are interpreted as exact rationals; floating-point execution and quantization are not verified.",
                            "The caller must establish that this scoped network matches the deployed component."],
            "release_eligible": False}