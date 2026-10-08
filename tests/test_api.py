import time

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.config import Settings
from backend.fixtures import make_trace


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    directory = tmp_path_factory.mktemp("api")
    settings = Settings(database_url=f"sqlite:///{(directory / 'api.db').as_posix()}", secret="test-only-api-key-" * 4, rate_limit=1000)
    with TestClient(create_app(settings)) as browser:
        yield browser


def sign_in(client, role="engineer"):
    response = client.post("/api/auth/demo", json={"role": role})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_authentication_required(client):
    client.cookies.clear()
    assert client.get("/api/workspace").status_code == 401


def test_workspace_and_security_headers(client):
    sign_in(client)
    response = client.get("/api/workspace")
    assert response.status_code == 200
    assert len(response.json()["runs"]) >= 13
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_v2_score_and_dossier_bind_json_bodies(client, tmp_path, monkeypatch):
    from backend import service_app
    from backend.persist.filelayout import FileLayoutStore

    monkeypatch.setattr(service_app, "_STORE", FileLayoutStore(str(tmp_path / "v2")))
    scored = client.post("/api/v2/runs/evaluate", json={
        "intended": [[0, 0], [1, 0], [2, 0]],
        "observed": [[0, 0], [1, 0.8], [2, 1.4]],
        "policy_id": "http-regression", "seed": 7,
    })
    assert scored.status_code == 200, scored.text
    assert scored.json()["verdict"] == "BLOCKED"
    dossier = client.post("/api/v2/dossiers/compile", json={
        "run_ids": [scored.json()["run_id"]],
        "independence": {"builder": "fixture", "funder": "fixture", "relationship": "none"},
        "odd": "Synthetic HTTP regression, world-frame 2D trace, supervised",
    })
    assert dossier.status_code == 200, dossier.text
    assert dossier.json()["dossier_id"].startswith("dos_")
    refused = client.post("/api/v2/dossiers/compile", json={
        "run_ids": [scored.json()["run_id"]], "independence": {},
    })
    assert refused.status_code == 422
    assert "odd" in str(refused.json()).lower()


def test_csrf_and_cross_origin_rejected(client):
    headers = sign_in(client)
    request = {"dataset_id": "dataset-nominal", "profile_id": "profile-default"}
    assert client.post("/api/runs", json=request).status_code == 403
    assert client.post("/api/runs", json=request, headers={**headers, "Origin": "https://evil.example"}).status_code == 403


def test_upload_evaluate_idempotency_and_export(client):
    headers = sign_in(client)
    uploaded = client.post("/api/datasets", json=make_trace().model_dump(), headers=headers)
    assert uploaded.status_code == 201, uploaded.text
    body = {"dataset_id": uploaded.json()["id"], "profile_id": "profile-default"}
    run = client.post("/api/runs", json=body, headers={**headers, "Idempotency-Key": "api-repeat"})
    assert run.status_code == 201, run.text
    repeated = client.post("/api/runs", json=body, headers={**headers, "Idempotency-Key": "api-repeat"})
    assert run.json()["id"] == repeated.json()["id"]
    conflicting = client.post("/api/runs", json={**body, "dataset_id": "dataset-drift"}, headers={**headers, "Idempotency-Key": "api-repeat"})
    assert conflicting.status_code == 409
    export = client.post(f"/api/runs/{run.json()['id']}/export", headers=headers)
    assert export.status_code == 200
    verification = client.post("/api/evidence/verify", content=export.content, headers={**headers, "Content-Type": "application/zip"})
    assert verification.json()["origin_verified"] is True
    assert client.get("/api/audit/verify").json()["valid"] is True


def test_viewer_cannot_mutate(client):
    headers = sign_in(client, "viewer")
    assert client.get("/api/workspace").status_code == 200
    assert client.post("/api/runs", json={"dataset_id": "dataset-nominal", "profile_id": "profile-default"}, headers=headers).status_code == 403


def test_malformed_and_oversized_inputs(client):
    headers = sign_in(client)
    payload = make_trace().model_dump()
    payload["observed"].pop()
    assert client.post("/api/datasets", json=payload, headers=headers).status_code == 422
    assert client.post("/api/datasets", content=b"x" * (2 * 1024 * 1024 + 1), headers=headers).status_code == 413
    assert client.post("/api/datasets", content="{bad", headers={**headers, "Content-Type": "application/json"}).status_code == 422


def test_review_requires_independent_authority_and_revision(client):
    engineer = sign_in(client)
    run = client.post("/api/runs", json={"dataset_id": "dataset-nominal", "profile_id": "profile-default"}, headers=engineer).json()
    body = {"decision": "accept_evidence", "note": "Reviewed scoped evidence and its limitations.", "expected_revision": 0}
    assert client.post(f"/api/runs/{run['id']}/reviews", json=body, headers=engineer).status_code == 403
    reviewer = sign_in(client, "reviewer")
    response = client.post(f"/api/runs/{run['id']}/reviews", json=body, headers=reviewer)
    assert response.status_code == 201, response.text
    assert response.json()["data"]["release_eligible"] is False
    assert client.post(f"/api/runs/{run['id']}/reviews", json=body, headers=reviewer).status_code == 409


def test_runtime_and_actual_lease_expiry(client):
    headers = sign_in(client)
    started = client.post("/api/runtime", json={"name": "Contract test", "profile_id": "profile-default", "embodiment_id": "franka-panda"}, headers=headers)
    assert started.status_code == 201, started.text
    identifier = started.json()["id"]
    telemetry = {"sequence": 0, "timestamp_ms": time.time() * 1000, "position_m": [0.4, 0.0, 0.4], "velocity_m_s": [0.1, 0.0, 0.0], "sensor_agreement": 0.95}
    accepted = client.post(f"/api/runtime/{identifier}/telemetry", json=telemetry, headers=headers)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["decision"] == "ALLOW"
    replayed = client.post(f"/api/runtime/{identifier}/telemetry", json=telemetry, headers=headers)
    assert replayed.json()["decision"] == "HOLD"


def test_api_tokens_are_scoped_and_revocable(client):
    headers = sign_in(client)
    issued = client.post("/api/tokens", json={"name": "Test integration", "days": 1}, headers=headers)
    assert issued.status_code == 201
    bearer = {"Authorization": f"Bearer {issued.json()['token']}"}
    assert client.get("/api/workspace", headers=bearer).status_code == 200
    identifier = client.get("/api/tokens").json()["tokens"][0]["id"]
    assert client.delete(f"/api/tokens/{identifier}", headers=headers).status_code == 200
    assert client.get("/api/workspace", headers=bearer).status_code == 401