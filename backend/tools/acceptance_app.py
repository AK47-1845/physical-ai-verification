from dataclasses import replace

from backend.api import create_app as create_mirror_app
from backend.config import load_settings


def create_app():
    settings = load_settings()
    if settings.environment != "development":
        raise ValueError("The browser acceptance entry point is development-only")
    return create_mirror_app(replace(settings, rate_limit=1200))