import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.free_lab import LabError, LabService, create_lab_router


@pytest.fixture
def clock():
    return [datetime(2026, 10, 5, 12, tzinfo=timezone.utc)]


@pytest.fixture
def lab(tmp_path, clock):
    return LabService(tmp_path, secret="test-free-lab-secret-" * 3, clock=lambda: clock[0])


def test_scoring_is_transient_and_server_computed(lab):
    clean = lab.score({"sample_id": "clean"})
    blocked = lab.score({"sample_id": "drifty"})
    assert clean["scorecard"]["payload"]["verdict"] == "TRUSTED"
    assert blocked["scorecard"]["payload"]["verdict"] == "BLOCKED"
    assert blocked["retention"]["trace_retained"] is False
    assert blocked["retention"]["public"] is False
    assert blocked["label"] == "SYNTHETIC"
    assert lab.counts()["shares"] == 0
    assert lab.counts()["contributions"] == 0


@pytest.mark.parametrize("pair, match", [
    ({"intended": [[0, 0], [1, 0]], "observed": [[0, 0], [1, 0]]}, "units"),
    ({"units": "m", "frame_id": "", "intended": [[0, 0], [1, 0]], "observed": [[0, 0], [1, 0]]}, "frame"),
    ({"units": "m", "frame_id": "world", "intended": [[0, 0]] * 513, "observed": [[0, 0]] * 513}, "512"),
    ({"units": "m", "frame_id": "world", "intended": [[0, 0], [1, 0]], "observed": [[0, 0]]}, "same number"),
    ({"units": "m", "frame_id": "world", "intended": [[0, 0], [True, 0]], "observed": [[0, 0], [1, 0]]}, "finite"),
    ({"units": "m", "frame_id": "world", "intended": [[0, 0], [float("inf"), 0]], "observed": [[0, 0], [1, 0]]}, "finite"),
])
def test_upload_refuses_invalid_evidence(lab, pair, match):
    with pytest.raises(LabError, match=match):
        lab.score({"pair": pair})


def test_csv_parser_uses_declared_scope_and_refuses_ragged_rows(lab):
    source = "ref_x,ref_y,obs_x,obs_y,units,frame_id\n0,0,0,0,m,world\n1,0,1,0.2,m,world\n"
    parsed = lab.parse_csv(source)
    assert parsed["pair"]["observed"][1] == [1.0, 0.2]
    with pytest.raises(LabError, match="scope"):
        lab.parse_csv(source.replace("0.2,m,world", "0.2,m,camera"))
    with pytest.raises(LabError):
        lab.parse_csv(source + "2,0,2,0.3,m,world,extra\n")


def test_keys_are_hashed_expire_and_have_enforced_quota(lab, clock):
    issued = lab.issue_key()
    token = issued["key"]
    assert token.startswith("gv_demo_")
    assert token.encode() not in lab.database.read_bytes()
    for _ in range(lab.key_quota):
        lab.consume_key(token)
    with pytest.raises(LabError) as limited:
        lab.consume_key(token)
    assert limited.value.status == 429
    clock[0] += timedelta(days=8)
    with pytest.raises(LabError) as expired:
        lab.consume_key(token)
    assert expired.value.status == 401


def test_sharing_requires_consent_and_never_exposes_raw_trace(lab):
    token = lab.issue_key()["key"]
    with pytest.raises(LabError, match="consent"):
        lab.share({"sample_id": "drifty", "api_key": token})
    created = lab.share({"sample_id": "drifty", "api_key": token, "consent_share": True})
    public = lab.get_share(created["id"])
    assert "intended" not in json.dumps(public)
    assert "observed" not in json.dumps(public)
    assert "api_key" not in json.dumps(public)
    assert public["artifact"]["scorecard"]["payload"]["verdict"] == "BLOCKED"
    assert lab.counts()["contributions"] == 0
    assert lab.ledger()["ok"] is True


def test_contribution_requires_terms_and_emits_consent_receipt(lab):
    token = lab.issue_key()["key"]
    request = {"sample_id": "clean", "api_key": token, "consent_share": True, "consent_benchmark": True}
    with pytest.raises(LabError, match="terms"):
        lab.share(request)
    created = lab.share({**request, "contributor_terms": "v1"})
    assert created["consent_receipt"]["trace_retained"] is True
    assert created["consent_receipt"]["terms_version"] == "v1"
    assert lab.counts()["contributions"] == 1


def test_public_board_duplicate_quarantine_uses_input_hash_not_client_score(lab):
    token = lab.issue_key()["key"]
    request = {"sample_id": "drifty", "api_key": token, "consent_share": True, "consent_board": True, "verdict": "TRUSTED", "gap": 0}
    created = lab.share(request)
    published = next(row for row in lab.board()["entries"] if row.get("share_id") == created["id"])
    assert published["gap"] == 2.5
    assert published["label"] == "SYNTHETIC"
    with pytest.raises(LabError) as duplicate:
        lab.share(request)
    assert duplicate.value.status == 409


def test_weekly_commit_reveal_refuses_current_week_and_verifies_closed_week(lab, clock):
    current = lab.challenge()
    assert "seed" not in current
    assert len(current["commitment"]) == 64
    with pytest.raises(LabError) as early:
        lab.reveal(current["week"])
    assert early.value.status == 409
    clock[0] += timedelta(days=7)
    revealed = lab.reveal(current["week"])
    assert revealed["verified"] is True
    assert revealed["commitment"] == current["commitment"]
    assert lab.challenge()["commitment"] != current["commitment"]


def test_challenge_budget_cannot_be_reset_by_request_fields(lab):
    token = lab.issue_key()["key"]
    request = {"api_key": token, "bias": 1.4, "noise_scale": 1.0, "attempts": 0}
    for attempt in range(50):
        result = lab.trial(request)
        assert result["attempts"] == attempt + 1
        assert "seed" not in result
    with pytest.raises(LabError) as limited:
        lab.trial(request)
    assert limited.value.status == 429


def test_failure_modes_are_scoped_and_callable_fixtures_are_labeled(lab):
    for mode in ["fm1", "fm2", "fm3", "fm4", "fm5"]:
        result = lab.failure_demo({"mode": mode, "sample_id": "drifty"})
        assert result["mode"] == mode
        assert result["label"] == "SYNTHETIC"
    result = lab.failure_demo({"mode": "fm4"})
    assert result["measurement"]["raw"] == 0.0
    with pytest.raises(LabError, match="library-only"):
        lab.failure_demo({"mode": "fm3", "pair": {}})


def test_duel_refuses_cross_frame_and_does_not_blend_verdicts(lab):
    duel = lab.duel({"left": {"sample_id": "clean"}, "right": {"sample_id": "drifty"}})
    assert duel["left"]["scorecard"]["payload"]["verdict"] == "TRUSTED"
    assert duel["right"]["scorecard"]["payload"]["verdict"] == "BLOCKED"
    pair = {"units": "m", "frame_id": "camera", "intended": [[0, 0], [1, 0]], "observed": [[0, 0], [1, 0]]}
    with pytest.raises(LabError, match="same frame"):
        lab.duel({"left": {"sample_id": "clean"}, "right": {"pair": pair}})


def test_extended_metrics_keep_success_separate_and_fall_insufficient(lab):
    result = lab.extended_metrics({"times": [1, 3, None, 5], "impact": {"impact_energy_j": 2.0}})
    assert result["success_time"]["successes"] == 3
    assert result["success_time"]["censored"] == 1
    assert result["fall_impact"]["verdict"] == "INSUFFICIENT"
    assert result["label"] == "DRAFT"
    with pytest.raises(LabError):
        lab.extended_metrics({"times": [1] * 513})


def test_share_expiry_and_missing_ids_fail_closed(lab, clock):
    token = lab.issue_key()["key"]
    created = lab.share({"sample_id": "clean", "api_key": token, "consent_share": True})
    clock[0] += timedelta(days=8)
    with pytest.raises(LabError) as expired:
        lab.get_share(created["id"])
    assert expired.value.status == 404
    with pytest.raises(LabError):
        lab.get_share("../keys")


def test_par_browser_number_roundtrip_preserves_measurement_semantics():
    from engine.par import build_par, validate_par
    envelope = build_par(policy={"id": "fixture", "weights": "sha256:" + "0" * 64}, release={"parent": "sha256:" + "0" * 64, "delta": "UNASSESSED"}, gates=[{"id": "coherence", "verdict": "PASS", "measurement": 1.0, "evidence": "fixture"}], ledger_head="0" * 64, independence={"builder": "fixture", "funder": "fixture", "relationship": "none"}, odd="Synthetic unit-test scope")
    envelope["par"]["gates"][0]["measurement"] = 1
    assert validate_par(envelope)["ok"] is True
    envelope["par"]["gates"][0]["measurement"] = 2
    assert validate_par(envelope)["ok"] is False


def test_free_lab_http_routes_and_uniform_refusals(lab):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(create_lab_router(lab))
    with TestClient(app) as client:
        assert client.post("/api/lab/v1/score", json={"sample_id": "clean"}).status_code == 200
        assert client.post("/api/lab/v1/score", json={"pair": {}}).status_code == 422
        assert client.get("/api/lab/v1/board").status_code == 200
        assert client.get("/api/lab/v1/challenge?seed=1").json().get("seed") is None
        token = client.post("/api/lab/v1/keys", json={}).json()["key"]
        usage = client.post("/api/lab/v1/usage", json={}, headers={"Authorization": f"Bearer {token}"})
        assert usage.status_code == 200
        assert "key" not in usage.json()