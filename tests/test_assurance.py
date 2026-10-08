import io
import zipfile

import pytest

from backend.engine import default_profile, evaluate
from backend.evidence import make_bundle, verify_bundle
from backend.fixtures import make_trace
from backend.formal import BoundQuery, verify_bounds
from backend.runtime import current_runtime, runtime_decision
from backend.schemas import Telemetry


def bounded_query(bound=0.5):
    return BoundQuery.model_validate({"name": "Scoped stabilizer", "input_lower": [-1.0, -1.0], "input_upper": [1.0, 1.0],
        "layers": [{"weights": [[0.4, 0.0], [0.0, 0.4]], "bias": [0.0, 0.0], "activation": "linear"}],
        "output_lower": [-bound, -bound], "output_upper": [bound, bound]})


def test_formal_bounded_proof_and_real_counterexample():
    verified = verify_bounds(bounded_query())
    assert verified["status"] == "VERIFIED_BOX"
    assert verified["counterexample"] is None
    violation = verify_bounds(bounded_query(0.3))
    assert violation["status"] == "COUNTEREXAMPLE"
    assert violation["counterexample"]["input_exact"]
    assert verified["release_eligible"] is False


def test_relu_semantics():
    query = bounded_query().model_dump()
    query["layers"][0]["activation"] = "relu"
    query["output_lower"] = [0.0, 0.0]
    assert verify_bounds(BoundQuery.model_validate(query))["status"] == "VERIFIED_BOX"


def sample(**changes):
    values = {"sequence": 0, "timestamp_ms": 1000.0, "position_m": [0.4, 0.0, 0.4], "velocity_m_s": [0.1, 0.0, 0.0], "sensor_agreement": 0.95}
    values.update(changes)
    return Telemetry.model_validate(values)


def test_runtime_allow_is_a_short_lease_not_a_persistent_state():
    state = runtime_decision(sample(), {}, default_profile(), 1000.0)
    assert state["decision"] == "ALLOW"
    assert current_runtime(state, 1249.0)["decision"] == "ALLOW"
    assert current_runtime(state, 1250.0)["decision"] == "HOLD"


@pytest.mark.parametrize("changes,now", [({}, 1251.0), ({}, 949.0), ({"position_m": [2.0, 0.0, 0.4]}, 1000.0), ({"velocity_m_s": [2.0, 0.0, 0.0]}, 1000.0), ({"sensor_agreement": 0.5}, 1000.0), ({"emergency_stop": True}, 1000.0)])
def test_runtime_holds_for_real_contract_failures(changes, now):
    decision = runtime_decision(sample(**changes), {}, default_profile(), now)
    assert decision["decision"] == "HOLD"
    assert decision["latched"] is True


def test_runtime_replay_and_latch():
    previous = runtime_decision(sample(), {}, default_profile(), 1000.0)
    replay = runtime_decision(sample(), previous, default_profile(), 1000.0)
    assert replay["decision"] == "HOLD"
    resumed = runtime_decision(sample(sequence=1), replay, default_profile(), 1000.0)
    assert resumed["decision"] == "HOLD"
    assert any("latched" in reason for reason in resumed["reasons"])


def bundle():
    trace = make_trace()
    profile = default_profile()
    run = {"id": "run_test", "data": {"trace": trace.model_dump(), "profile": profile.model_dump(), "result": evaluate(trace, profile)}}
    return make_bundle(run, [], [], "test-only-secret" * 4)[0]


def test_evidence_roundtrip_distinguishes_integrity_and_origin():
    archive = bundle()
    assert verify_bundle(archive)["valid"] is True
    assert verify_bundle(archive)["origin_verified"] is False
    assert verify_bundle(archive, "test-only-secret" * 4)["origin_verified"] is True
    assert verify_bundle(archive, "different-test-secret" * 3)["valid"] is False


def test_evidence_tampering_rejected():
    archive = bundle()
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(archive)) as original, zipfile.ZipFile(output, "w") as modified:
        for name in original.namelist():
            modified.writestr(name, b"{}" if name == "trace.json" else original.read(name))
    assert verify_bundle(output.getvalue())["valid"] is False


def test_zip_traversal_and_invalid_archives_rejected_without_extraction():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("../escape.json", "{}")
    assert verify_bundle(output.getvalue())["valid"] is False
    assert verify_bundle(b"not a zip")["valid"] is False