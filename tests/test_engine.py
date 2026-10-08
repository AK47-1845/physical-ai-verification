import copy
import math

import numpy as np
import pytest
from pydantic import ValidationError

from backend.engine import compare_embodiments, default_profile, discrete_frechet, evaluate, gate_status
from backend.fixtures import make_trace
from backend.schemas import GateRule, Trace


def test_identical_and_offset_frechet():
    path = np.asarray([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
    assert discrete_frechet(path, path) == 0.0
    assert discrete_frechet(path, path + [0.0, 0.25]) == pytest.approx(0.25)


@pytest.mark.parametrize("bad", [True, "0.1", math.nan, math.inf, -math.inf])
def test_strict_finite_coordinates(bad):
    payload = make_trace().model_dump()
    payload["observed"][0][0] = bad
    with pytest.raises(ValidationError):
        Trace.model_validate(payload)


@pytest.mark.parametrize("field", ["observed", "probed", "timestamps_s"])
def test_no_implicit_truncation(field):
    payload = make_trace().model_dump()
    payload[field].pop()
    with pytest.raises(ValidationError):
        Trace.model_validate(payload)


def test_dimension_mismatch_rejected():
    payload = make_trace().model_dump()
    payload["observed"][0].pop()
    with pytest.raises(ValidationError):
        Trace.model_validate(payload)


def test_nonmonotonic_timestamps_rejected():
    payload = make_trace().model_dump()
    payload["timestamps_s"][3] = payload["timestamps_s"][2]
    with pytest.raises(ValidationError):
        Trace.model_validate(payload)


def test_nominal_is_repeatable_and_never_release_qualified():
    first = evaluate(make_trace(), default_profile())
    second = evaluate(make_trace(), default_profile())
    assert first == second
    assert first["verdict"] == "PASS"
    assert first["release_eligible"] is False
    assert first["coverage"] == {"observed": 13, "total": 13}


@pytest.mark.parametrize("scenario,metric", [("drift", "frechet"), ("perception", "unsupported_perception_rate"), ("playback", "action_sensitivity"), ("contact", "contact_violation_rate"), ("collapse", "diversity_loss"), ("boundary", "workspace_violation_rate")])
def test_scenarios_fail_their_intended_gate(scenario, metric):
    result = evaluate(make_trace(scenario), default_profile())
    assert result["verdict"] == "BLOCK"
    assert next(gate for gate in result["gates"] if gate["metric"] == metric)["status"] == "BLOCK"


def test_playback_response_exact_zero():
    result = evaluate(make_trace("playback"), default_profile())
    assert next(gate for gate in result["gates"] if gate["metric"] == "action_sensitivity")["value"] == 0.0


def test_missing_timing_and_probe_fail_closed():
    trace = make_trace().model_copy(update={"timestamps_s": None, "probed": None, "probe_method": None})
    result = evaluate(trace, default_profile())
    assert result["verdict"] == "INSUFFICIENT"
    assert {gate["metric"] for gate in result["gates"] if gate["status"] == "MISSING"} == {"max_speed", "max_jerk", "action_sensitivity"}


def test_frame_unit_and_dimension_contracts():
    for update in [{"units": "abstract"}, {"coordinate_frame": "other"}]:
        with pytest.raises(ValueError, match="units/frame"):
            evaluate(make_trace().model_copy(update=update), default_profile())


def test_threshold_boundaries_and_missing():
    rule = GateRule(metric="frechet", direction="upper", pass_limit=0.1, review_limit=0.2)
    assert gate_status(0.1, rule) == "PASS"
    assert gate_status(math.nextafter(0.1, 1.0), rule) == "REVIEW"
    assert gate_status(0.2, rule) == "REVIEW"
    assert gate_status(math.nextafter(0.2, 1.0), rule) == "BLOCK"
    assert gate_status(None, rule) == "MISSING"
    assert gate_status(math.nan, rule) == "MISSING"


def test_physical_derivatives_scale_with_time():
    trace = make_trace()
    slow = trace.model_copy(update={"timestamps_s": [value * 2 for value in trace.timestamps_s]})
    first = {gate["metric"]: gate["value"] for gate in evaluate(trace, default_profile())["gates"]}
    second = {gate["metric"]: gate["value"] for gate in evaluate(slow, default_profile())["gates"]}
    assert second["max_speed"] == pytest.approx(first["max_speed"] / 2)
    assert second["max_jerk"] == pytest.approx(first["max_jerk"] / 8)


def test_debounce_does_not_hide_raw_excursion():
    payload = make_trace().model_dump()
    payload["observed"] = copy.deepcopy(payload["reference"])
    payload["observed"][20][0] += 0.2
    isolated = evaluate(Trace.model_validate(payload), default_profile())
    assert next(gate for gate in isolated["gates"] if gate["metric"] == "horizon_ratio")["value"] == 1.0
    assert isolated["series"]["error_m"][20] == pytest.approx(0.2)
    for sample in [21, 22]:
        payload["observed"][sample][0] += 0.2
    sustained = evaluate(Trace.model_validate(payload), default_profile())
    assert next(gate for gate in sustained["gates"] if gate["metric"] == "horizon_ratio")["value"] == pytest.approx(20 / 120)


def test_transfer_keeps_scale_and_rejects_wrong_frames():
    baseline = make_trace()
    assert compare_embodiments(baseline, baseline)["centered_frechet_m"] == 0.0
    comparison = compare_embodiments(baseline, make_trace(embodiment="g1-task-space"))
    assert comparison["workspace_span_ratio"] < 0.8
    with pytest.raises(ValueError):
        compare_embodiments(baseline, baseline.model_copy(update={"coordinate_frame": "world"}))


def test_lineage_uses_sample_weight_not_ambiguous_alpha():
    result = evaluate(make_trace("collapse"), default_profile())
    fraction = next(gate for gate in result["gates"] if gate["metric"] == "synthetic_fraction")["value"]
    assert fraction == pytest.approx(1000 / 1060)