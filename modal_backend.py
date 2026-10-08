"""Modal deployment for the Physical AI Verification public demo backend (ASGI).

Usage (from this directory):
    modal secret create verification-env LAB_SECRET=<64+ chars> ALLOWED_HOSTS=<modal-host>,127.0.0.1,localhost,testserver [CORS_ORIGINS=<frontend>]
    modal deploy modal_backend.py
"""
import modal
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent)

app = modal.App("verification")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("fastapi==0.142.2", "uvicorn==0.54.0", "pydantic==2.13.5")
    .add_local_dir(
        ROOT + "\\backend",
        "/app/backend",
        ignore=["tests", "__pycache__", "demo-data", "docs", ".venv"],
    )
    .add_local_dir(ROOT + "\\packages", "/app/packages", ignore=["__pycache__"])
)


@app.function(image=image, secrets=[modal.Secret.from_name("verification-env2")])
@modal.asgi_app()
def api():
    import sys

    sys.path.insert(0, "/app")
    from backend.public_app import create_public_app

    return create_public_app()
