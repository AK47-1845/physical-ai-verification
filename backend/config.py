from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    database_url: str
    secret: str
    environment: str = "development"
    demo: bool = True
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "testserver")
    public_origin: str | None = None
    body_limit: int = 2 * 1024 * 1024
    session_seconds: int = 8 * 60 * 60
    rate_limit: int = 120

    def __post_init__(self) -> None:
        if len(self.secret) < 32:
            raise ValueError("The instance signing secret must contain at least 32 characters")
        if self.environment == "production":
            if self.demo:
                raise ValueError("Demo authentication is forbidden in production")
            if not self.public_origin or not self.public_origin.startswith("https://"):
                raise ValueError("Production requires an HTTPS PUBLIC_ORIGIN")
            if "*" in self.allowed_hosts:
                raise ValueError("Production requires explicit allowed hosts")

    @property
    def secure_cookie(self) -> bool:
        return self.environment == "production"


def load_settings() -> Settings:
    environment = os.getenv("APP_ENV", "development")
    state = ROOT / "var"
    state.mkdir(mode=0o700, exist_ok=True)
    secret = os.getenv("APP_SECRET", "")
    if not secret:
        if environment == "production":
            raise ValueError("APP_SECRET must be provided by the deployment secret store")
        secret_file = state / ".instance-secret"
        if not secret_file.exists():
            try:
                descriptor = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w", encoding="ascii") as handle:
                    handle.write(secrets.token_urlsafe(48))
            except FileExistsError:
                pass
        secret = secret_file.read_text(encoding="ascii").strip()
    try:
        rate_limit = int(os.getenv("VV_RATE_LIMIT", "120"))
    except ValueError:
        rate_limit = 120
    if rate_limit <= 0:
        rate_limit = 120
    return Settings(
        database_url=os.getenv("DATABASE_URL", f"sqlite:///{(state / 'verification.db').as_posix()}"),
        secret=secret, environment=environment, rate_limit=rate_limit,
        demo=os.getenv("DEMO_MODE", "false" if environment == "production" else "true").lower() == "true",
        allowed_hosts=tuple(value.strip() for value in os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if value.strip()),
        public_origin=os.getenv("PUBLIC_ORIGIN"),
    )