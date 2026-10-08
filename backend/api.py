import asyncio
import hmac
import json
import logging
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager, contextmanager
from typing import Annotated, Literal

from argon2.exceptions import VerificationError
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.catalog import STANDARDS
from backend.config import ROOT, Settings, load_settings
from backend.engine import METRICS, fingerprint
from backend.evidence import verify_bundle
from backend.formal import BoundQuery
from backend.schemas import Embodiment, GateProfile, Identifier, StrictModel, Telemetry, Trace
from backend.service import DEMO_TENANT, PASSWORDS, Conflict, Governance
from backend.store import AccessSession, MissingRecord, Store, User, new_id, serialize, token_hash

LOGGER = logging.getLogger("verification.api")
COOKIE = "verification_session"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class Login(StrictModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class DemoLogin(StrictModel):
    role: Literal["engineer", "reviewer", "admin", "viewer"] = "engineer"


class EvaluationRequest(StrictModel):
    dataset_id: Identifier
    profile_id: Identifier


class ExperimentRequest(StrictModel):
    scenario: Literal["drift", "perception", "contact", "boundary"] = "drift"
    profile_id: Identifier
    budget: Annotated[int, Field(strict=True, ge=2, le=12)] = 6
    maximum: Annotated[float, Field(strict=True, ge=0.1, le=3, allow_inf_nan=False)] = 1.5
    seed: Annotated[int, Field(strict=True, ge=0, le=2**31 - 1)] = 7


class ReviewRequest(StrictModel):
    decision: Literal["request_review", "accept_evidence", "reject"]
    note: str = Field(min_length=12, max_length=2000)
    expected_revision: Annotated[int, Field(strict=True, ge=0)]


class TransferRequest(StrictModel):
    baseline_id: Identifier
    candidate_id: Identifier


class RuntimeRequest(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    profile_id: Identifier
    embodiment_id: Identifier


class NoteRequest(StrictModel):
    note: str = Field(min_length=12, max_length=2000)


class TokenRequest(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    days: Annotated[int, Field(strict=True, ge=1, le=30)] = 7


class UserRequest(StrictModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    name: str = Field(min_length=1, max_length=120)
    role: Literal["admin", "engineer", "reviewer", "viewer"]
    password: str = Field(min_length=14, max_length=128)


class BodyLimit:
    def __init__(self, app, limit: int):
        self.app = app
        self.limit = limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in SAFE_METHODS:
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse({"detail": "Invalid content length"}, 400)(scope, receive, send)
        if length < 0 or length > self.limit:
            return await JSONResponse({"detail": "Request body exceeds 2 MiB limit"}, 413)(scope, receive, send)
        chunks = []
        size = 0
        try:
            async with asyncio.timeout(10):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    size += len(chunk)
                    if size > self.limit:
                        return await JSONResponse({"detail": "Request body exceeds 2 MiB limit"}, 413)(scope, receive, send)
                    chunks.append(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            return await JSONResponse({"detail": "Request body timeout"}, 408)(scope, receive, send)
        consumed = False

        async def replay():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)


def require(actor: dict, *roles: str) -> None:
    if actor["role"] not in roles:
        raise HTTPException(403, "Your role does not permit this action")


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings or load_settings()
    store = Store(configuration.database_url)
    service = Governance(store, configuration.secret)
    compute_slots = threading.BoundedSemaphore(2)
    attempts: dict[tuple[str, str], deque] = defaultdict(deque)

    @asynccontextmanager
    async def lifespan(_app):
        if configuration.environment == "production":
            store.check_schema()
        else:
            store.migrate()
        if configuration.demo:
            service.seed_demo()
        yield
        store.engine.dispose()

    app = FastAPI(title="Physical AI Verification API", version="1.0.0", lifespan=lifespan, docs_url=None, redoc_url=None,
                  openapi_url=None if configuration.environment == "production" else "/openapi.json")
    app.state.store = store
    app.state.service = service
    app.state.settings = configuration

    @contextmanager
    def compute_slot():
        if not compute_slots.acquire(blocking=False):
            raise HTTPException(429, "Evaluation capacity reached; retry shortly", headers={"Retry-After": "2"})
        try:
            yield
        finally:
            compute_slots.release()

    @app.middleware("http")
    async def perimeter(request: Request, call_next):
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        origin = request.headers.get("origin")
        expected_origin = configuration.public_origin or f"{request.url.scheme}://{request.headers.get('host', '')}"
        if request.method not in SAFE_METHODS and origin and origin != expected_origin:
            return JSONResponse({"detail": "Cross-origin mutation rejected", "request_id": request_id}, 403)
        category = "auth" if request.url.path.startswith("/api/auth/") else "telemetry" if request.url.path.endswith("/telemetry") else "api"
        limit = 15 if category == "auth" else 600 if category == "telemetry" else configuration.rate_limit
        if request.url.path.startswith("/api/"):
            key = (request.client.host if request.client else "unknown", category)
            current_time = time.monotonic()
            bucket = attempts[key]
            while bucket and current_time - bucket[0] > 60:
                bucket.popleft()
            if len(bucket) >= limit:
                return JSONResponse({"detail": "Rate limit exceeded", "request_id": request_id}, 429, headers={"Retry-After": "60"})
            bucket.append(current_time)
            if len(attempts) > 4096:
                for old_key in list(attempts):
                    if not attempts[old_key] or current_time - attempts[old_key][-1] > 60:
                        attempts.pop(old_key, None)
        try:
            response = await call_next(request)
        except Exception:
            LOGGER.error("Unhandled request failure; request_id=%s", request_id)
            response = JSONResponse({"detail": "Internal error; contact the operator with the request ID", "request_id": request_id}, 500)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data: blob:; connect-src 'self'; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; object-src 'none'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if configuration.secure_cookie:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.exception_handler(MissingRecord)
    async def missing_handler(_request, _error):
        return JSONResponse({"detail": "Record not found in this workspace"}, 404)

    @app.exception_handler(Conflict)
    async def conflict_handler(_request, error):
        return JSONResponse({"detail": str(error)}, 409)

    @app.exception_handler(ValueError)
    async def value_handler(_request, error):
        return JSONResponse({"detail": str(error)[:500]}, 422)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request, error):
        return JSONResponse({"detail": [{"location": list(entry["loc"]), "message": entry["msg"]} for entry in error.errors()]}, 422)

    def actor(request: Request) -> dict:
        authorization = request.headers.get("authorization", "")
        bearer = authorization.startswith("Bearer ")
        raw_token = authorization[7:] if bearer else request.cookies.get(COOKIE, "")
        resolved = store.resolve_session(raw_token)
        if resolved is None:
            raise HTTPException(401, "Sign in to access this workspace")
        user, access = resolved
        if bearer and access["kind"] != "api":
            raise HTTPException(401, "API token required for bearer authentication")
        if not bearer and request.method not in SAFE_METHODS:
            csrf = request.headers.get("x-csrf-token", "")
            if not csrf or not access["csrf_hash"] or not hmac.compare_digest(token_hash(csrf), access["csrf_hash"]):
                raise HTTPException(403, "CSRF token missing or invalid")
        request.state.session_token = raw_token
        return user

    Actor = Annotated[dict, Depends(actor)]

    def issue_session(user_id: str, response: Response) -> dict:
        raw_token = secrets.token_urlsafe(48)
        csrf = secrets.token_urlsafe(32)
        with Session(store.engine) as session, session.begin():
            session.execute(delete(AccessSession).where(AccessSession.expires_at <= time.time()))
            session.add(AccessSession(token_hash=token_hash(raw_token), user_id=user_id, csrf_hash=token_hash(csrf),
                                      expires_at=time.time() + configuration.session_seconds, kind="browser"))
        response.set_cookie(COOKIE, raw_token, max_age=configuration.session_seconds, httponly=True,
                            secure=configuration.secure_cookie, samesite="strict", path="/")
        user, _access = store.resolve_session(raw_token)
        return {"user": user, "csrf_token": csrf, "demo": configuration.demo}

    @app.get("/healthz")
    def health():
        return {"status": "ok", "version": "1.0.0"}

    @app.get("/readyz")
    def ready():
        with Session(store.engine) as session:
            session.execute(text("SELECT 1"))
        return {"status": "ready"}

    @app.get("/api/config")
    def public_config():
        return {"demo": configuration.demo, "version": "1.0.0", "name": "Physical AI Verification"}

    @app.post("/api/auth/demo")
    def demo_login(body: DemoLogin, request: Request, response: Response):
        if not configuration.demo or not request.client or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            raise HTTPException(403, "Demo access is only available in local development")
        return issue_session(f"demo-{body.role}", response)

    @app.post("/api/auth/login")
    def login(body: Login, response: Response):
        with Session(store.engine) as session:
            user = session.scalar(select(User).where(User.email == body.email.lower().strip(), User.enabled.is_(True)))
            try:
                if user is None:
                    PASSWORDS.hash(body.password)
                    raise HTTPException(401, "Invalid sign-in")
                PASSWORDS.verify(user.password_hash, body.password)
            except VerificationError:
                raise HTTPException(401, "Invalid sign-in") from None
            return issue_session(user.id, response)

    @app.get("/api/session")
    def session_info(request: Request, user: Actor):
        csrf = secrets.token_urlsafe(32)
        with Session(store.engine) as session, session.begin():
            saved = session.get(AccessSession, token_hash(request.state.session_token))
            saved.csrf_hash = token_hash(csrf)
        return {"user": user, "csrf_token": csrf, "demo": configuration.demo}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response, user: Actor):
        with Session(store.engine) as session, session.begin():
            session.execute(delete(AccessSession).where(AccessSession.token_hash == token_hash(request.state.session_token)))
        response.delete_cookie(COOKIE, path="/")
        return {"signed_out": True}

    @app.get("/api/workspace")
    def workspace(user: Actor):
        return service.workspace(user)

    @app.get("/api/datasets/{dataset_id}")
    def dataset(dataset_id: str, user: Actor):
        return store.get(user["tenant_id"], dataset_id, "dataset")

    @app.post("/api/datasets", status_code=201)
    def upload_dataset(body: Trace, user: Actor):
        require(user, "engineer", "admin")
        return service.add_dataset(body, user)

    @app.post("/api/embodiments", status_code=201)
    def register_embodiment(body: Embodiment, user: Actor):
        require(user, "admin", "engineer")
        with store.transaction(user["tenant_id"]) as (session, tenant):
            return serialize(store.add_record(session, tenant, "embodiment", body.model_dump(), user["id"]))

    @app.post("/api/profiles", status_code=201)
    def add_profile(body: GateProfile, user: Actor):
        require(user, "admin")
        if any(rule.metric not in METRICS for rule in body.rules):
            raise ValueError("Unknown metric")
        if not any(rule.required for rule in body.rules):
            raise ValueError("At least one required gate is mandatory")
        with store.transaction(user["tenant_id"]) as (session, tenant):
            from backend.store import Record
            existing = [record.data for record in session.scalars(select(Record).where(Record.tenant_id == tenant.id, Record.kind == "profile"))]
            expected_version = max((profile["version"] for profile in existing if profile["name"] == body.name), default=0) + 1
            if body.version != expected_version:
                raise Conflict(f"Next immutable profile version must be {expected_version}")
            return serialize(store.add_record(session, tenant, "profile", body.model_dump(), user["id"]))

    @app.post("/api/runs", status_code=201)
    def create_run(body: EvaluationRequest, user: Actor, idempotency_key: Annotated[str | None, Header(max_length=100)] = None):
        require(user, "engineer", "admin")
        with compute_slot():
            return service.evaluate_dataset(body.dataset_id, body.profile_id, user, idempotency_key)

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, user: Actor):
        run = store.get(user["tenant_id"], run_id, "run")
        run["reviews"] = [record for record in store.list(user["tenant_id"], "review", 500) if record["data"]["run_id"] == run_id]
        return run

    @app.post("/api/runs/{run_id}/reviews", status_code=201)
    def review(run_id: str, body: ReviewRequest, user: Actor):
        require(user, *(('engineer', 'admin') if body.decision == "request_review" else ('reviewer', 'admin')))
        return service.review(run_id, body.decision, body.note.strip(), body.expected_revision, user)

    @app.post("/api/experiments", status_code=201)
    def experiment(body: ExperimentRequest, user: Actor):
        require(user, "engineer", "admin")
        with compute_slot():
            return service.experiment(body.scenario, body.profile_id, body.budget, body.maximum, body.seed, user)

    @app.post("/api/transfers", status_code=201)
    def transfer(body: TransferRequest, user: Actor):
        require(user, "engineer", "admin")
        with compute_slot():
            return service.transfer(body.baseline_id, body.candidate_id, user)

    @app.post("/api/proofs", status_code=201)
    def formal(body: BoundQuery, user: Actor):
        require(user, "engineer", "admin")
        with compute_slot():
            return service.formal(body, user)

    @app.post("/api/runtime", status_code=201)
    def start_runtime(body: RuntimeRequest, user: Actor):
        require(user, "engineer", "admin")
        return service.start_runtime(body.name, body.profile_id, body.embodiment_id, user)

    @app.get("/api/runtime/{runtime_id}")
    def runtime_state(runtime_id: str, user: Actor):
        return service.get_runtime(runtime_id, user)

    @app.post("/api/runtime/{runtime_id}/telemetry")
    def telemetry(runtime_id: str, body: Telemetry, user: Actor):
        require(user, "engineer", "admin")
        return service.telemetry(runtime_id, body, user)

    @app.post("/api/runtime/{runtime_id}/reset")
    def reset_runtime(runtime_id: str, body: NoteRequest, user: Actor):
        require(user, "reviewer", "admin")
        return service.reset_runtime(runtime_id, body.note.strip(), user)

    @app.get("/api/audit")
    def audit(user: Actor, limit: Annotated[int, Query(ge=1, le=500)] = 100):
        return {"entries": store.audit(user["tenant_id"], limit)}

    @app.get("/api/audit/verify")
    def audit_verify(user: Actor):
        return store.verify_audit(user["tenant_id"])

    @app.post("/api/runs/{run_id}/export")
    def evidence_export(run_id: str, user: Actor):
        content, manifest = service.export(run_id, user)
        return Response(content, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="verification-{run_id}.zip"', "X-Evidence-ID": manifest["id"]})

    @app.post("/api/evidence/verify")
    async def evidence_verify(request: Request, user: Actor):
        return verify_bundle(await request.body(), configuration.secret)

    @app.get("/api/records/{kind}")
    def records(kind: Literal["experiment", "transfer", "proof", "review", "runtime"], user: Actor, offset: Annotated[int, Query(ge=0, le=10000)] = 0):
        return {"records": store.list(user["tenant_id"], kind, 100, offset)}

    @app.get("/api/standards")
    def standards(user: Actor):
        return {"mappings": STANDARDS, "qualification": "Evidence mapping only; no certification or legal opinion"}

    @app.get("/api/knowledge")
    def knowledge(user: Actor):
        if not configuration.demo or user["tenant_id"] != DEMO_TENANT:
            return {"nodes": [], "edges": [], "scope": "Source graph is only bundled with the local research workspace"}
        source = ROOT / "graphify-out" / "graph.json"
        if not source.exists():
            return {"nodes": [], "edges": [], "scope": "Source graph not built"}
        graph = json.loads(source.read_text(encoding="utf-8"))
        nodes = [{key: node.get(key) for key in ("id", "label", "file_type", "source_file", "source_location", "community", "community_name", "rationale")} for node in graph.get("nodes", [])[:1000]]
        identifiers = {node["id"] for node in nodes}
        edges = [entry for entry in graph.get("edges", graph.get("links", [])) if entry.get("source") in identifiers and entry.get("target") in identifiers]
        return {"nodes": nodes, "edges": edges[:2000], "scope": "Source-grounded reference graph; code remains executable truth", "truncated": len(graph.get("nodes", [])) > 1000}

    @app.get("/api/admin/users")
    def users(user: Actor):
        require(user, "admin")
        with Session(store.engine) as session:
            return {"users": [{"id": row.id, "name": row.display_name, "email": row.email, "role": row.role, "enabled": row.enabled}
                for row in session.scalars(select(User).where(User.tenant_id == user["tenant_id"]))]}

    @app.post("/api/admin/users", status_code=201)
    def add_user(body: UserRequest, user: Actor):
        require(user, "admin")
        with store.transaction(user["tenant_id"]) as (session, tenant):
            email = body.email.lower().strip()
            if session.scalar(select(User.id).where(User.email == email)):
                raise Conflict("Email is already registered")
            identifier = new_id("user")
            session.add(User(id=identifier, tenant_id=tenant.id, email=email, display_name=body.name,
                             role=body.role, password_hash=PASSWORDS.hash(body.password)))
            store.append_audit(session, tenant, user["id"], "user.created", identifier, fingerprint({"email": email, "role": body.role}))
            return {"id": identifier, "email": email, "name": body.name, "role": body.role}

    @app.post("/api/tokens", status_code=201)
    def issue_token(body: TokenRequest, user: Actor):
        require(user, "admin", "engineer")
        raw = "gv_" + secrets.token_urlsafe(40)
        with store.transaction(user["tenant_id"]) as (session, tenant):
            session.add(AccessSession(token_hash=token_hash(raw), user_id=user["id"], csrf_hash=None,
                expires_at=time.time() + body.days * 86400, kind="api", name=body.name))
            store.append_audit(session, tenant, user["id"], "token.created", token_hash(raw)[:16], fingerprint({"name": body.name, "days": body.days}))
        return {"token": raw, "name": body.name, "expires_in_days": body.days, "display_once": True}

    @app.get("/api/tokens")
    def tokens(user: Actor):
        with Session(store.engine) as session:
            return {"tokens": [{"id": access.token_hash, "name": access.name, "expires_at": access.expires_at}
                for access in session.scalars(select(AccessSession).where(AccessSession.user_id == user["id"], AccessSession.kind == "api", AccessSession.expires_at > time.time()))]}

    @app.delete("/api/tokens/{identifier}")
    def revoke_token(identifier: str, user: Actor):
        with store.transaction(user["tenant_id"]) as (session, tenant):
            result = session.execute(delete(AccessSession).where(AccessSession.user_id == user["id"], AccessSession.kind == "api", AccessSession.token_hash == identifier))
            if result.rowcount != 1:
                raise MissingRecord()
            store.append_audit(session, tenant, user["id"], "token.revoked", identifier[:16], fingerprint({"revoked": True}))
        return {"revoked": True}

    from backend.service_app import router as night_router
    app.include_router(night_router)
    from backend.free_lab import LabService, create_lab_router
    app.include_router(create_lab_router(LabService(ROOT / "var" / "free-lab", secret=configuration.secret)))

    distribution = ROOT / "web" / "dist"
    if (distribution / "assets").exists():
        app.mount("/assets", StaticFiles(directory=distribution / "assets"), name="assets")

    @app.get("/{path:path}")
    def frontend(path: str):
        if path.startswith("api/") or not (distribution / "index.html").exists():
            raise HTTPException(404, "Not found")
        return FileResponse(distribution / "index.html", headers={"Cache-Control": "no-cache"})

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(configuration.allowed_hosts))
    app.add_middleware(BodyLimit, limit=configuration.body_limit)
    return app