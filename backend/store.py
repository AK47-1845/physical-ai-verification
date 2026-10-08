from __future__ import annotations

import hashlib
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from backend.engine import fingerprint

ZERO_HASH = "0" * 64
SCHEMA_VERSION = "1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class Base(DeclarativeBase):
    pass


class SchemaVersion(Base):
    __tablename__ = "schema_version"
    version: Mapped[str] = mapped_column(String(20), primary_key=True)


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    head: Mapped[str] = mapped_column(String(64), default=ZERO_HASH)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('admin','engineer','reviewer','viewer')", name="valid_user_role"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(default=True)


class AccessSession(Base):
    __tablename__ = "access_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    csrf_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[float] = mapped_column(Float, index=True)
    kind: Mapped[str] = mapped_column(String(20), default="browser")
    name: Mapped[str] = mapped_column(String(120), default="Browser session")


class Record(Base):
    __tablename__ = "records"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    data: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))
    created_by: Mapped[str] = mapped_column(String(80))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (UniqueConstraint("tenant_id", "sequence", name="audit_tenant_sequence"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    event_hash: Mapped[str] = mapped_column(String(64))


class MissingRecord(LookupError):
    pass


def serialize(record: Record) -> dict:
    return {"id": record.id, "kind": record.kind, "data": record.data, "content_hash": record.content_hash,
            "created_at": record.created_at, "created_by": record.created_by}


class Store:
    def __init__(self, database_url: str):
        self.sqlite = database_url.startswith("sqlite")
        options = {"connect_args": {"check_same_thread": False, "timeout": 15}} if self.sqlite else {"pool_pre_ping": True}
        self.engine = create_engine(database_url, **options)
        if self.sqlite:
            event.listen(self.engine, "connect", self._configure_sqlite)

    @staticmethod
    def _configure_sqlite(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.close()

    def migrate(self) -> None:
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session, session.begin():
            version = session.scalar(select(SchemaVersion.version))
            if version is not None and version != SCHEMA_VERSION:
                raise RuntimeError("Unsupported schema version; an explicit migration is required")
            if version is None:
                session.add(SchemaVersion(version=SCHEMA_VERSION))

    def check_schema(self) -> None:
        with Session(self.engine) as session:
            if session.scalar(select(SchemaVersion.version)) != SCHEMA_VERSION:
                raise RuntimeError("Database schema not initialized; run the migrate command")

    def ensure_tenant(self, tenant_id: str, name: str) -> None:
        with Session(self.engine) as session, session.begin():
            if session.get(Tenant, tenant_id) is None:
                session.add(Tenant(id=tenant_id, name=name, sequence=0, head=ZERO_HASH))

    @contextmanager
    def transaction(self, tenant_id: str) -> Iterator[tuple[Session, Tenant]]:
        with Session(self.engine, expire_on_commit=False) as session:
            try:
                if self.sqlite:
                    session.execute(text("BEGIN IMMEDIATE"))
                tenant = session.get(Tenant, tenant_id, with_for_update=True)
                if tenant is None:
                    raise MissingRecord("Workspace not found")
                yield session, tenant
                session.commit()
            except BaseException:
                session.rollback()
                raise

    def append_audit(self, session: Session, tenant: Tenant, actor: str, action: str,
                     resource_id: str, resource_hash: str, details: dict | None = None) -> dict:
        sequence = tenant.sequence + 1
        payload = {"schema": "verification.audit/1", "id": new_id("evt"), "tenant_id": tenant.id,
                   "sequence": sequence, "previous_hash": tenant.head, "created_at": now_iso(),
                   "actor": actor, "action": action, "resource_id": resource_id,
                   "resource_hash": resource_hash, "details": details or {}}
        digest = fingerprint(payload)
        session.add(AuditEvent(id=payload["id"], tenant_id=tenant.id, sequence=sequence, payload=payload, event_hash=digest))
        tenant.sequence = sequence
        tenant.head = digest
        return {**payload, "event_hash": digest}

    def add_record(self, session: Session, tenant: Tenant, kind: str, data: dict, actor: str,
                   record_id: str | None = None, details: dict | None = None) -> Record:
        record = Record(id=record_id or new_id(kind), tenant_id=tenant.id, kind=kind, data=data,
                        content_hash=fingerprint(data), created_at=now_iso(), created_by=actor)
        session.add(record)
        self.append_audit(session, tenant, actor, f"{kind}.created", record.id, record.content_hash, details)
        return record

    @staticmethod
    def find(session: Session, tenant_id: str, record_id: str, kind: str | None = None, lock: bool = False) -> Record:
        query = select(Record).where(Record.tenant_id == tenant_id, Record.id == record_id)
        if kind:
            query = query.where(Record.kind == kind)
        if lock:
            query = query.with_for_update()
        record = session.scalar(query)
        if record is None:
            raise MissingRecord("Record not found in this workspace")
        if fingerprint(record.data) != record.content_hash:
            raise RuntimeError("Stored evidence integrity failure")
        return record

    def get(self, tenant_id: str, record_id: str, kind: str | None = None) -> dict:
        with Session(self.engine) as session:
            return serialize(self.find(session, tenant_id, record_id, kind))

    def list(self, tenant_id: str, kind: str, limit: int = 100, offset: int = 0) -> list[dict]:
        with Session(self.engine) as session:
            query = select(Record).where(Record.tenant_id == tenant_id, Record.kind == kind).order_by(
                Record.created_at.desc(), Record.id.desc()).offset(offset).limit(limit)
            return [serialize(record) for record in session.scalars(query)]

    def audit(self, tenant_id: str, limit: int = 100) -> list[dict]:
        with Session(self.engine) as session:
            query = select(AuditEvent).where(AuditEvent.tenant_id == tenant_id).order_by(AuditEvent.sequence.desc()).limit(limit)
            return [{**entry.payload, "event_hash": entry.event_hash} for entry in session.scalars(query)]

    def verify_audit(self, tenant_id: str) -> dict:
        with self.transaction(tenant_id) as (session, tenant):
            expected_hash = ZERO_HASH
            count = 0
            query = select(AuditEvent).where(AuditEvent.tenant_id == tenant_id).order_by(AuditEvent.sequence)
            for entry in session.scalars(query).yield_per(250):
                count += 1
                if (entry.sequence != count or entry.payload.get("sequence") != count
                        or entry.payload.get("previous_hash") != expected_hash
                        or entry.payload.get("tenant_id") != tenant_id
                        or fingerprint(entry.payload) != entry.event_hash):
                    return {"valid": False, "checked": count, "broken_at": count, "reason": "Chain mismatch"}
                expected_hash = entry.event_hash
            valid = count == tenant.sequence and expected_hash == tenant.head
            return {"valid": valid, "checked": count, "head": expected_hash,
                    "reason": "Consistent with retained database head" if valid else "Head mismatch or truncation",
                    "assurance": "Local tamper evidence; external immutable checkpoints required for independent attestation"}

    def resolve_session(self, raw_token: str) -> tuple[dict, dict] | None:
        if not raw_token or len(raw_token) > 300:
            return None
        with Session(self.engine) as session:
            access = session.get(AccessSession, token_hash(raw_token))
            if access is None or access.expires_at <= time.time():
                return None
            user = session.get(User, access.user_id)
            if user is None or not user.enabled:
                return None
            return ({"id": user.id, "tenant_id": user.tenant_id, "email": user.email,
                     "name": user.display_name, "role": user.role},
                    {"kind": access.kind, "csrf_hash": access.csrf_hash, "expires_at": access.expires_at})