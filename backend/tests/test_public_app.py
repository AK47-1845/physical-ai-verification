from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.public_app import PublicSettings, create_public_app


@pytest.fixture
def public(tmp_path, monkeypatch):
    from backend import service_app
    monkeypatch.setattr(service_app, "_STORE", None)
    settings = PublicSettings(root=tmp_path, secret="public-test-only-" * 4, origins=("https://site.example",), admin_token="test-admin-" * 5)
    with TestClient(create_public_app(settings)) as client:
        yield client


def test_public_boot_is_populated_and_health_is_explicit(public):
    assert public.get("/healthz").json()["status"] == "ok"
    assert public.get("/readyz").json()["ready"] is True
    assert len(public.get("/api/v2/runs").json()["run_ids"]) >= 4
    assert len(public.get("/api/lab/v1/board").json()["entries"]) == 10
    assert public.get("/api/workspace").status_code == 404
    assert public.post("/api/auth/demo", json={"role": "admin"}).status_code == 404


def test_cors_is_explicit_and_mutation_default_denies_foreign_origin(public):
    response = public.options("/api/lab/v1/score", headers={"Origin": "https://site.example", "Access-Control-Request-Method": "POST"})
    assert response.headers["access-control-allow-origin"] == "https://site.example"
    foreign = public.post("/api/lab/v1/score", json={"sample_id": "clean"}, headers={"Origin": "https://evil.example"})
    assert foreign.status_code == 403
    assert public.post("/api/lab/v1/score", json={"sample_id": "clean"}).status_code == 200


def test_public_pilot_records_require_operator_auth(public):
    assert public.get("/api/v2/pilots").status_code == 401
    assert public.get("/api/v2/pilots/pilot_unknown").status_code == 401
    assert public.get("/api/v2/pilots", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert public.get("/api/v2/pilots", headers={"Authorization": "Bearer " + "test-admin-" * 5}).status_code == 200
    assert public.post("/api/v2/pilots", json={}).status_code == 503


@pytest.mark.parametrize("body", [
    {"trial_cap": 51}, {"trial_cap": True}, {"horizon": 100000},
    {"trace": [[0, 0]] * 513}, {"layers": [{}] * 9},
    {"input_box": [[0, 1]] * 7}, {"grid_per_dim": 100},
    {"seed": "x" * 9000},
])
def test_public_compute_budgets_refuse_before_dispatch(public, body):
    response = public.post("/api/v2/eval/hunt", json=body)
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "budget"


def test_body_limit_checks_actual_bytes_and_bad_json(public):
    huge = public.post("/api/lab/v1/score", content=b"x" * (262144 + 1), headers={"content-type": "application/json"})
    assert huge.status_code == 413
    invalid = public.post("/api/lab/v1/score", content=b'{"sample_id":NaN}', headers={"content-type": "application/json"})
    assert invalid.status_code == 422
    bad = public.post("/api/lab/v1/score", content=b"{broken", headers={"content-type": "application/json"})
    assert bad.status_code == 422


def test_public_csv_accepts_a_full_bounded_trace(public):
    source = "ref_x,ref_y,obs_x,obs_y,units,frame_id\n" + "0,0,0,0.1,m,world\n" * 512
    result = public.post("/api/lab/v1/parse", json={"csv": source})
    assert result.status_code == 200, result.text
    assert len(result.json()["pair"]["observed"]) == 512


def test_public_errors_do_not_leak_stack_or_local_paths(public):
    result = public.post("/api/lab/v1/score", json={"pair": {}})
    assert result.status_code == 422
    assert "Traceback" not in result.text
    assert "site-packages" not in result.text
    assert "no-store" in result.headers["cache-control"]
    assert result.headers["x-content-type-options"] == "nosniff"


def test_static_space_files_are_present_and_nonroot():
    root = Path(__file__).resolve().parents[2]
    dockerfile = (root / "Dockerfile").read_text()
    assert "USER 1000" in dockerfile
    assert "backend.public_app:create_public_app" in dockerfile
    assert "--workers" in dockerfile
    assert "sdk: docker" in (root / "README.md").read_text()
    assert ".venv" in (root / ".dockerignore").read_text()