from __future__ import annotations

import math
import random

from backend.schemas import Trace

SCENARIOS = {
    "nominal": ("Nominal reach", "Controlled task-space tracking"),
    "drift": ("Thermal drift", "Progressive end-effector displacement"),
    "perception": ("Perception disagreement", "Uncorroborated high-confidence observations"),
    "playback": ("Frozen action response", "Control perturbations produce no response"),
    "contact": ("Contact instability", "Tangential load exceeds the declared friction cone"),
    "collapse": ("Recursive data degradation", "Declared diversity contracts across synthetic generations"),
    "boundary": ("Workspace excursion", "Task trajectory crosses the configured envelope"),
}


def make_trace(scenario: str = "nominal", seed: int = 7, severity: float = 1.0, embodiment: str = "franka-panda") -> Trace:
    if scenario not in SCENARIOS:
        raise ValueError("Unknown scenario")
    generator = random.Random(seed)
    count = 120
    reference = []
    observed = []
    phases = [generator.uniform(0.0, 2.0 * math.pi) for _ in range(3)]
    for index in range(count):
        progress = index / (count - 1)
        angle = progress * 2.0 * math.pi
        intended = [0.42 + 0.20 * math.sin(angle), 0.18 * math.cos(angle), 0.40 + 0.12 * math.sin(angle / 2)]
        measured = [value + 0.003 * math.sin(angle + phase) for value, phase in zip(intended, phases)]
        if scenario == "drift":
            measured[0] += severity * 0.28 * progress ** 2
            measured[1] += severity * 0.06 * progress
        if scenario == "boundary":
            measured[0] += severity * 0.85 * math.sin(math.pi * progress) ** 4
        if embodiment == "ur5e":
            measured = [value * (0.95 if axis < 2 else 1.0) for axis, value in enumerate(measured)]
        if embodiment == "g1-task-space":
            measured = [value * (0.70 if axis < 2 else 1.0) for axis, value in enumerate(measured)]
        reference.append(intended)
        observed.append(measured)
    generations = []
    for generation in range(6):
        synthetic = 150 + generation * (170 if scenario == "collapse" else 45)
        generations.append({
            "generation": generation, "real_samples": max(60, 1000 - synthetic), "synthetic_samples": synthetic,
            "diversity": max(0.1, 1.0 - generation * (0.16 if scenario == "collapse" else 0.018)),
            "quality": max(0.05, 0.95 - generation * (0.12 if scenario == "collapse" else 0.009)),
        })
    return Trace.model_validate({
        "name": SCENARIOS[scenario][0], "task": "task-space-reach", "embodiment_id": embodiment,
        "policy_version": "demonstrator/1.0", "evidence_kind": "synthetic", "reference_kind": "simulator",
        "units": "m", "coordinate_frame": "task", "reference": reference, "observed": observed,
        "timestamps_s": [index * 0.05 for index in range(count)],
        "probed": [[value + (0.05 if axis == 0 and scenario != "playback" else 0.0) for axis, value in enumerate(point)] for point in observed],
        "probe_method": "Synthetic paired replay, identical seed, +0.05 m response in x; not a learned policy",
        "rollouts": [[[value + 0.002 * math.sin(index * 0.08 + rollout) for value in point] for index, point in enumerate(observed)] for rollout in range(4)],
        "perception": {"confidence": [0.95] * count, "corroborated": [not (scenario == "perception" and 40 <= index < 40 + int(20 * severity)) for index in range(count)], "method": "Synthetic agreement labels"},
        "lineage": {"generations": generations, "metric_definition": "Synthetic comparable diversity and quality values; not a training experiment", "evidence_kind": "synthetic"},
        "contact": {"normal_force_n": [12.0] * count, "tangential_force_n": [9.0 * severity if scenario == "contact" and 45 <= index < 70 else 2.0 for index in range(count)], "friction_coefficient": 0.5, "method": "Synthetic contact telemetry"},
        "provenance": {"source": "verification:fixtures/1", "license": "Project-authored synthetic data", "transforms": [f"seed={seed}", f"severity={severity}"], "attribution": "Deterministic analytic fixture. No physics simulator or robot executed."},
    })