from __future__ import annotations

import asyncio
import hmac
import json
import logging
import math
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from backend import service_app
from backend.free_lab import LabService, create_lab_router
from backend.persist.filelayout import FileLayoutStore
from backend.tools.reset_demo import seed_stories


@dataclass(frozen=True)
class PublicSettings:
    root: Path
    secret: str
    origins: tuple[str, ...] = ()
    hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "testserver")
    admin_token: str = ""
    pilot_intake: bool = False
    body_limit: int = 262144

    def __post_init__(self):
        if len(self.secret) < 32:
            raise ValueError("Public demo secret must contain at least 32 characters")
        if any(origin == "*" or not origin.startswith(("https://", "http://127.0.0.1:", "http://localhost:")) for origin in self.origins):
            raise ValueError("Explicit HTTPS or local development origins are required")
        if self.admin_token and len(self.admin_token) < 32:
            raise ValueError("Operator token must contain at least 32 characters")
        if "*" in self.hosts:
            raise ValueError("Explicit allowed hosts are required")

    @classmethod
    def from_environment(cls):
        root = Path(os.environ.get("PUBLIC_DATA_DIR", str(Path(__file__).resolve().parents[1] / "var" / "public-demo")))
        root.mkdir(parents=True, exist_ok=True)
        secret = os.environ.get("LAB_SECRET", "")
        if not secret:
            secret_file = root / ".lab-secret"
            if not secret_file.exists():
                try:
                    descriptor = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(descriptor, "w", encoding="ascii") as handle:
                        handle.write(secrets.token_urlsafe(48))
                except FileExistsError:
                    pass
            secret = secret_file.read_text(encoding="ascii").strip()
        space_host = os.environ.get("SPACE_HOST", "")
        hosts = tuple(value.strip() for value in os.environ.get("ALLOWED_HOSTS", f"127.0.0.1,localhost,testserver{',' + space_host if space_host else ''}").split(",") if value.strip())
        origins = tuple(value.strip().rstrip("/") for value in os.environ.get("CORS_ORIGINS", "").split(",") if value.strip())
        return cls(root, secret, origins, hosts, os.environ.get("PUBLIC_ADMIN_TOKEN", ""), os.environ.get("PUBLIC_PILOT_INTAKE") == "on")


def validate_budget(value, depth=0, counter=None, key=""):
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > 20000 or depth > 16:
        raise ValueError("Request structure exceeds the public demo budget")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite numbers are refused")
    if isinstance(value, str) and len(value) > (262144 if key == "csv" else 4096):
        raise ValueError("A request string exceeds 4096 characters")
    caps = {"trial_cap": 50, "horizon": 512, "grid_per_dim": 5, "n_resamples": 1000, "n_bootstrap": 1000}
    if key in caps and (isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= caps[key]):
        raise ValueError(f"{key}: integer 1..{caps[key]} required on the public demo")
    if isinstance(value, dict):
        if len(value) > 128:
            raise ValueError("Too many object fields")
        for name, child in value.items():
            validate_budget(child, depth + 1, counter, name)
    if isinstance(value, list):
        cap = 2048
        if key in {"intended", "observed", "trace", "trace_a", "trace_b", "actions", "states", "trials"}:
            cap = 512
        if key == "layers":
            cap = 8
        if key == "input_box":
            cap = 6
        if key in {"gates", "weights", "bias"}:
            cap = 64
        if len(value) > cap:
            raise ValueError(f"{key or 'array'}: maximum {cap} items on the public demo")
        for child in value:
            validate_budget(child, depth + 1, counter)


class PublicPerimeter:
    def __init__(self, app, settings: PublicSettings, lab: LabService):
        self.app = app
        self.settings = settings
        self.lab = lab
        self.active = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope, receive)
        path = request.url.path
        method = request.method
        request_id = secrets.token_hex(8)

        async def reject(status, message, kind="refused"):
            await JSONResponse({"detail": {"error": kind, "message": message}, "request_id": request_id}, status_code=status, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})(scope, receive, send)

        if method == "OPTIONS":
            return await self.app(scope, receive, send)
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") not in self.settings.origins:
            return await reject(403, "Origin is not in the configured allowlist")
        if path.startswith("/api/v2/pilots"):
            if method == "GET":
                token = request.headers.get("authorization", "").removeprefix("Bearer ")
                if not self.settings.admin_token or not hmac.compare_digest(token.encode(), self.settings.admin_token.encode()):
                    return await reject(401, "Operator authorization required")
            elif method == "POST" and not self.settings.pilot_intake:
                return await reject(503, "Pilot intake is not configured. Download a local pilot brief instead.")
        if path.startswith("/api/"):
            try:
                await asyncio.to_thread(self.lab.throttle, request.client.host if request.client else "unknown", "public", limit=240)
            except Exception as error:
                status = getattr(error, "status", 503)
                return await reject(status, "Public request capacity reached; retry later")
        if self.active >= 2 and method == "POST":
            return await reject(429, "Two computations are already running. Retry shortly.")
        chunks = []
        size = 0
        if method in {"POST", "PUT", "PATCH"}:
            try:
                async with asyncio.timeout(12):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        content = message.get("body", b"")
                        size += len(content)
                        if size > self.settings.body_limit:
                            return await reject(413, "Request exceeds 256 KB")
                        chunks.append(content)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                return await reject(408, "Request body timed out")
            body = b"".join(chunks)
            if body:
                try:
                    def refuse_constant(value):
                        raise ValueError(f"Non-finite number {value} refused")
                    decoded = json.loads(body, parse_constant=refuse_constant)
                    validate_budget(decoded)
                except (ValueError, UnicodeError, RecursionError) as error:
                    return await reject(422, str(error)[:240], "budget")
            sent_body = False

            async def replay():
                nonlocal sent_body
                if not sent_body:
                    sent_body = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()
            upstream_receive = replay
        else:
            upstream_receive = receive

        async def secure_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([(b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer"), (b"x-request-id", request_id.encode())])
                message["headers"] = headers
            await send(message)

        if self.active >= 2 and method == "POST":
            return await reject(429, "Two computations are already running. Retry shortly.")
        self.active += int(method == "POST")
        try:
            await self.app(scope, upstream_receive, secure_send)
        finally:
            self.active -= int(method == "POST")


def create_public_app(settings: PublicSettings | None = None):
    config = settings or PublicSettings.from_environment()
    store = FileLayoutStore(str(config.root / "engine"))
    service_app._STORE = store
    if not store.list_ids("runs"):
        seed_stories(store)
    lab = LabService(config.root / "lab", secret=config.secret)
    app = FastAPI(title="Physical AI Verification public demonstration", version="0.2", docs_url=None, redoc_url=None)
    app.state.lab = lab
    app.state.settings = config
    app.include_router(service_app.router)
    app.include_router(create_lab_router(lab))

    @app.get("/healthz")
    def health():
        return {"status": "ok", "mode": "PUBLIC_DEMO", "hardware_connected": False}

    @app.get("/readyz")
    def ready():
        return {"ready": bool(store.list_ids("runs")), "storage": "ephemeral unless a persistent volume is configured", "labels": ["DRAFT", "SYNTHETIC", "UNSIGNED"]}

    @app.exception_handler(Exception)
    async def internal_error(_request, error):
        error_id = secrets.token_hex(8)
        logging.getLogger("verification.public").error("Internal failure id=%s type=%s", error_id, type(error).__name__)
        return JSONResponse({"detail": {"error": "internal", "error_id": error_id}}, status_code=500)

    app.add_middleware(PublicPerimeter, settings=config, lab=lab)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(config.hosts))
    app.add_middleware(CORSMiddleware, allow_origins=list(config.origins), allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "Authorization"], expose_headers=["X-Request-ID"], max_age=600)
    return app