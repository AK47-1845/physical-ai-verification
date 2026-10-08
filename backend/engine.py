from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import numpy as np
from scipy.stats import wasserstein_distance

from backend.schemas import GateProfile, GateRule, Trace

ENGINE_VERSION = "verification-engine/1.0.0"
METRICS = {
    "frechet": ("Trajectory distance", "Transfer", "m", "Discrete Frechet; supplied reference is not necessarily a simulator."),
    "mean_drift": ("Mean tracking error", "Drift", "m", "Aligned Euclidean position error; no unobserved axes inferred."),
    "horizon_ratio": ("Coherence horizon", "Drift", "fraction", "First sustained breach; isolated excursions remain visible."),
    "action_sensitivity": ("Control response", "Control", "ratio", "Paired controlled-probe response; not a controllability proof."),
    "ensemble_spread": ("Rollout uncertainty", "Uncertainty", "m2", "Variance among supplied rollouts; not calibrated epistemic uncertainty."),
    "max_speed": ("Peak speed", "Executability", "m/s", "Finite differences require actual timestamps."),
    "max_jerk": ("Peak jerk", "Executability", "m/s3", "Kinematic diagnostic, not a contact-dynamics proof."),
    "workspace_violation_rate": ("Workspace containment", "Executability", "fraction", "Axis-aligned task-space box only; not collision avoidance."),
    "unsupported_perception_rate": ("Uncorroborated perception", "Perception", "fraction", "High-confidence claims without supplied corroboration; not an image detector."),
    "contact_violation_rate": ("Friction-cone violations", "Contact", "fraction", "Coulomb inequality on supplied forces; not full contact stability."),
    "synthetic_fraction": ("Synthetic-data fraction", "Data lineage", "fraction", "Sample-weighted fraction in the latest declared generation; not proof of collapse."),
    "diversity_loss": ("Diversity contraction", "Data lineage", "fraction", "Change in declared comparable diversity statistics; inspect metric definition."),
    "distribution_shift": ("Error distribution shift", "Drift", "m", "Wasserstein distance between first and last error windows; descriptive, not a hypothesis test."),
}


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def default_profile() -> GateProfile:
    settings = [
        ("frechet", "upper", 0.04, 0.10, True),
        ("mean_drift", "upper", 0.02, 0.06, True),
        ("horizon_ratio", "lower", 0.90, 0.65, True),
        ("action_sensitivity", "lower", 0.004, 0.0005, True),
        ("ensemble_spread", "upper", 0.0002, 0.001, False),
        ("max_speed", "upper", 0.8, 1.5, True),
        ("max_jerk", "upper", 100.0, 250.0, True),
        ("workspace_violation_rate", "upper", 0.0, 0.005, True),
        ("unsupported_perception_rate", "upper", 0.02, 0.08, False),
        ("contact_violation_rate", "upper", 0.0, 0.01, False),
        ("synthetic_fraction", "upper", 0.50, 0.80, False),
        ("diversity_loss", "upper", 0.15, 0.40, False),
        ("distribution_shift", "upper", 0.02, 0.06, False),
    ]
    return GateProfile(name="Task-space assurance", rules=[
        GateRule(metric=metric, direction=direction, pass_limit=passing, review_limit=review, required=required)
        for metric, direction, passing, review, required in settings
    ])


def discrete_frechet(reference: np.ndarray, observed: np.ndarray) -> float:
    previous = np.full(len(observed), math.inf)
    for row_index, reference_point in enumerate(reference):
        current = np.full(len(observed), math.inf)
        distances = np.linalg.norm(observed - reference_point, axis=1)
        for column_index, distance in enumerate(distances):
            if row_index == 0 and column_index == 0:
                current[column_index] = distance
            else:
                before = previous[column_index]
                if column_index:
                    before = min(before, current[column_index - 1], previous[column_index - 1])
                current[column_index] = max(before, distance)
        previous = current
    return float(previous[-1])


def derivative(values: np.ndarray, timestamps: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return np.diff(values, axis=0) / np.diff(timestamps)[:, None], (timestamps[1:] + timestamps[:-1]) / 2


def gate_status(value: float | None, rule: GateRule) -> str:
    if value is None or not math.isfinite(value):
        return "MISSING" if rule.required else "NOT_OBSERVED"
    if rule.direction == "upper":
        return "PASS" if value <= rule.pass_limit else "REVIEW" if value <= rule.review_limit else "BLOCK"
    return "PASS" if value >= rule.pass_limit else "REVIEW" if value >= rule.review_limit else "BLOCK"


def evaluate(trace: Trace, profile: GateProfile) -> dict:
    if trace.units != profile.units or trace.coordinate_frame != profile.coordinate_frame:
        raise ValueError("Trace units/frame must match the gate profile; explicit adapters are required")
    if len(trace.observed[0]) != profile.dimension:
        raise ValueError("Trace dimension must match the gate profile")
    if any(rule.metric not in METRICS for rule in profile.rules):
        raise ValueError("Unknown metric in gate profile")
    reference = np.asarray(trace.reference, dtype=float)
    observed = np.asarray(trace.observed, dtype=float)
    count = len(observed)
    errors = np.linalg.norm(observed - reference, axis=1)
    breaches = errors > profile.drift_breach_m
    horizon = count
    for sample in range(count - profile.breach_run + 1):
        if bool(np.all(breaches[sample:sample + profile.breach_run])):
            horizon = sample
            break
    outside = np.any((observed < profile.workspace_lower) | (observed > profile.workspace_upper), axis=1)
    window = max(4, count // 4)
    values: dict[str, float | None] = dict.fromkeys(METRICS)
    values.update({
        "frechet": discrete_frechet(reference, observed),
        "mean_drift": float(np.mean(errors)),
        "horizon_ratio": horizon / count,
        "workspace_violation_rate": float(np.mean(outside)),
        "distribution_shift": float(wasserstein_distance(errors[:window], errors[-window:])),
    })
    speed = []
    jerk = []
    if trace.timestamps_s is not None and trace.units == "m":
        velocity, velocity_times = derivative(observed, np.asarray(trace.timestamps_s))
        acceleration, acceleration_times = derivative(velocity, velocity_times)
        jerk_vectors, _ = derivative(acceleration, acceleration_times)
        speed = np.linalg.norm(velocity, axis=1).tolist()
        jerk = np.linalg.norm(jerk_vectors, axis=1).tolist()
        values["max_speed"] = max(speed)
        values["max_jerk"] = max(jerk)
    if trace.probed is not None:
        response = np.asarray(trace.probed) - observed
        energy = float(np.mean(np.sum(observed ** 2, axis=1)))
        values["action_sensitivity"] = float(np.mean(np.sum(response ** 2, axis=1))) / (energy + 1e-9)
    if trace.rollouts is not None:
        values["ensemble_spread"] = float(np.mean(np.var(np.asarray(trace.rollouts), axis=0)))
    perception_indices = []
    if trace.perception:
        perception_indices = [index for index, (confidence, supported) in enumerate(
            zip(trace.perception.confidence, trace.perception.corroborated)
        ) if confidence >= 0.8 and not supported]
        values["unsupported_perception_rate"] = len(perception_indices) / count
    if trace.contact:
        normal = np.asarray(trace.contact.normal_force_n)
        tangent = np.asarray(trace.contact.tangential_force_n)
        values["contact_violation_rate"] = float(np.mean(tangent > normal * trace.contact.friction_coefficient))
    if trace.lineage:
        first = trace.lineage.generations[0]
        latest = trace.lineage.generations[-1]
        values["synthetic_fraction"] = latest.synthetic_samples / (latest.real_samples + latest.synthetic_samples)
        if len(trace.lineage.generations) > 1 and first.diversity > 0:
            values["diversity_loss"] = max(0.0, 1 - latest.diversity / first.diversity)
    gates = []
    for rule in profile.rules:
        label, layer, unit, limitation = METRICS[rule.metric]
        value = values[rule.metric]
        gates.append({
            **rule.model_dump(), "label": label, "layer": layer, "unit": unit if trace.units == "m" else "abstract",
            "value": value, "status": gate_status(value, rule), "limitation": limitation,
        })
    statuses = {gate["status"] for gate in gates}
    verdict = "BLOCK" if "BLOCK" in statuses else "INSUFFICIENT" if "MISSING" in statuses else "REVIEW" if "REVIEW" in statuses else "PASS"
    events = []
    if horizon < count:
        events.append({"index": horizon, "kind": "drift", "metric": "horizon_ratio", "label": "Sustained drift begins"})
    for sample in np.flatnonzero(outside).tolist()[:8]:
        events.append({"index": sample, "kind": "workspace", "metric": "workspace_violation_rate", "label": "Workspace boundary exceeded"})
    for sample in perception_indices[:8]:
        events.append({"index": sample, "kind": "perception", "metric": "unsupported_perception_rate", "label": "Uncorroborated high-confidence perception"})
    if speed and values["max_speed"] is not None:
        events.append({"index": int(np.argmax(speed)) + 1, "kind": "speed", "metric": "max_speed", "label": "Peak speed"})
    limitations = [
        "Draft thresholds: no safety qualification or certification is implied.",
        "Kinematic and supplied-evidence checks do not establish full-system safety.",
        "No collision geometry, actuator torque model, stability proof, or hardware timing guarantee is included.",
    ]
    if trace.evidence_kind == "synthetic":
        limitations.append("Synthetic demonstration. Not evidence of physical robot performance.")
    if trace.reference_kind == "commanded":
        limitations.append("Reference is commanded motion, not simulator output; this is tracking error, not measured sim-to-real transfer.")
    if trace.timestamps_s is None:
        limitations.append("Physical timestamps unavailable: speed and jerk cannot be evaluated.")
    result = {
        "engine_version": ENGINE_VERSION, "input_hash": fingerprint(trace.model_dump()),
        "profile_hash": fingerprint(profile.model_dump()), "verdict": verdict,
        "gates": gates, "events": sorted(events, key=lambda event: event["index"]),
        "series": {"error_m": errors.tolist(), "speed_m_s": speed, "jerk_m_s3": jerk},
        "coverage": {"observed": sum(gate["value"] is not None for gate in gates), "total": len(gates)},
        "release_eligible": False, "release_blockers": ["Uncalibrated gate profile", "Hardware validation absent", "Independent conformity assessment not supplied"],
        "limitations": limitations,
    }
    result["result_hash"] = fingerprint(result)
    return result


def compare_embodiments(baseline: Trace, candidate: Trace) -> dict:
    if (baseline.units, baseline.coordinate_frame, baseline.task, len(baseline.observed[0])) != (
        candidate.units, candidate.coordinate_frame, candidate.task, len(candidate.observed[0])
    ):
        raise ValueError("Transfer comparison requires matching task, units, registered frame, and dimension")
    first = np.asarray(baseline.observed)
    second = np.asarray(candidate.observed)
    first_centered = first - first.mean(axis=0)
    second_centered = second - second.mean(axis=0)
    first_span = float(np.linalg.norm(np.ptp(first, axis=0)))
    second_span = float(np.linalg.norm(np.ptp(second, axis=0)))
    ratio = min(first_span, second_span) / max(first_span, second_span) if max(first_span, second_span) > 1e-12 else None
    distance = discrete_frechet(first_centered, second_centered)
    return {
        "centered_frechet_m": distance, "workspace_span_ratio": ratio,
        "baseline_span_m": first_span, "candidate_span_m": second_span,
        "same_embodiment": baseline.embodiment_id == candidate.embodiment_id,
        "status": "INSUFFICIENT" if ratio is None else "BLOCK" if distance > 0.12 or ratio < 0.6 else "REVIEW" if distance > 0.05 or ratio < 0.8 else "PASS",
        "qualification": "draft geometric comparison; not demonstrated zero-shot policy transfer",
        "transform": "translation removed; scale preserved; sample order preserved",
    }