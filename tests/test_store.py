from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.store import AuditEvent, MissingRecord, Record, Store


@pytest.fixture
def store(tmp_path):
    database = Store(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    database.migrate()
    database.ensure_tenant("alpha", "Alpha workspace")
    database.ensure_tenant("beta", "Beta workspace")
    yield database
    database.engine.dispose()


def test_record_and_audit_commit_atomically(store):
    with store.transaction("alpha") as (session, tenant):
        record = store.add_record(session, tenant, "run", {"verdict": "PASS"}, "tester")
    assert store.get("alpha", record.id)["data"]["verdict"] == "PASS"
    assert store.verify_audit("alpha")["valid"] is True
    assert store.verify_audit("alpha")["checked"] == 1


def test_failed_transaction_leaves_no_partial_evidence(store):
    with pytest.raises(RuntimeError):
        with store.transaction("alpha") as (session, tenant):
            store.add_record(session, tenant, "run", {"verdict": "PASS"}, "tester")
            raise RuntimeError("Injected commit failure")
    assert store.list("alpha", "run") == []
    assert store.verify_audit("alpha")["checked"] == 0


def test_concurrent_writers_preserve_chain(store):
    def append(value):
        with store.transaction("alpha") as (session, tenant):
            store.add_record(session, tenant, "run", {"value": value}, "tester")
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(append, range(20)))
    result = store.verify_audit("alpha")
    assert result["valid"] is True
    assert result["checked"] == 20


def test_tenant_boundary(store):
    with store.transaction("alpha") as (session, tenant):
        record = store.add_record(session, tenant, "run", {"value": 1}, "tester")
    with pytest.raises(MissingRecord):
        store.get("beta", record.id)
    assert store.list("beta", "run") == []


def test_tampering_and_tail_truncation_detected(store):
    with store.transaction("alpha") as (session, tenant):
        store.add_record(session, tenant, "run", {"value": 1}, "tester")
    with Session(store.engine) as session, session.begin():
        session.execute(delete(AuditEvent).where(AuditEvent.tenant_id == "alpha"))
    assert store.verify_audit("alpha")["valid"] is False


def test_record_mutation_detected(store):
    with store.transaction("alpha") as (session, tenant):
        record = store.add_record(session, tenant, "run", {"value": 1}, "tester")
    with Session(store.engine) as session, session.begin():
        saved = session.scalar(select(Record).where(Record.id == record.id))
        saved.data = {"value": 2}
    with pytest.raises(RuntimeError, match="integrity"):
        store.get("alpha", record.id)


@pytest.mark.parametrize("change", [{"demo": True}, {"public_origin": "http://localhost"}, {"allowed_hosts": ("*",)}])
def test_production_configuration_rejects_unsafe_defaults(change):
    values = {"database_url": "sqlite:///test.db", "secret": "test-only-" * 8, "environment": "production", "demo": False, "public_origin": "https://verify.example", "allowed_hosts": ("verify.example",)}
    values.update(change)
    with pytest.raises(ValueError):
        Settings(**values)