from __future__ import annotations

import math

from backend.schemas import GateProfile, Telemetry

MAX_SAMPLE_AGE_MS = 250.0
MAX_FUTURE_SKEW_MS = 50.0


def runtime_decision(sample: Telemetry, previous: dict, profile: GateProfile, server_ms: float) -> dict:
    if profile.units != "m" or profile.dimension != 3:
        raise ValueError("Runtime supervision requires a registered 3D meter profile")
    reasons = []
    age = server_ms - sample.timestamp_ms
    if age > MAX_SAMPLE_AGE_MS:
        reasons.append("Stale telemetry")
    if age < -MAX_FUTURE_SKEW_MS:
        reasons.append("Clock skew exceeds contract")
    last_sequence = previous.get("last_sequence")
    if last_sequence is not None and sample.sequence != last_sequence + 1:
        reasons.append("Telemetry sequence gap or replay")
    if any(value < lower or value > upper for value, lower, upper in zip(sample.position_m, profile.workspace_lower, profile.workspace_upper)):
        reasons.append("Workspace envelope exceeded")
    speed = math.sqrt(sum(value * value for value in sample.velocity_m_s))
    speed_rule = next((rule for rule in profile.rules if rule.metric == "max_speed"), None)
    if speed_rule is None:
        reasons.append("Required speed policy missing")
    elif speed > speed_rule.pass_limit:
        reasons.append("Speed envelope exceeded")
    if sample.sensor_agreement < 0.8:
        reasons.append("Sensor corroboration below threshold")
    if sample.emergency_stop:
        reasons.append("Emergency-stop input asserted")
    if previous.get("latched"):
        reasons.append("Incident latched; independent reset required")
    decision = "HOLD" if reasons else "ALLOW"
    expires_at = server_ms + max(0.0, MAX_SAMPLE_AGE_MS - max(age, 0.0)) if decision == "ALLOW" else server_ms
    return {"decision": decision, "reasons": reasons, "latched": bool(reasons),
            "last_sequence": max(sample.sequence, last_sequence if last_sequence is not None else sample.sequence),
            "issued_at_ms": server_ms, "expires_at_ms": expires_at, "sample_age_ms": age,
            "sample": sample.model_dump(), "speed_m_s": speed,
            "scope": "Supervisory decision only. No actuator command. A certified local safety controller remains mandatory."}


def current_runtime(state: dict, server_ms: float) -> dict:
    if state.get("decision") == "ALLOW" and server_ms >= state.get("expires_at_ms", 0):
        return {**state, "decision": "HOLD", "reasons": ["Decision lease expired; telemetry unavailable"], "lease_expired": True}
    return {**state, "lease_expired": state.get("expires_at_ms", 0) <= server_ms}