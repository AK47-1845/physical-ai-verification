"""Environment doctor: PASS/FAIL table before any server runs.

Usage (from hi bro/meta bro):  python backend/tools/doctor.py
Exit 0: all critical checks pass (warnings allowed). Exit 1: a critical
check failed - fix it before booting. Stdlib only.
"""

import os
import platform
import socket
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

EXPECT_ROUTES = 44


def check_python():
    ver = sys.version_info
    ok = ver >= (3, 10)
    return ("PASS" if ok else "WARN",
            f"python {platform.python_version()} on {platform.system()} "
            f"{platform.machine()}" + ("" if ok else " (want >= 3.10)"))


def check_import(mod):
    try:
        module = __import__(mod)
    except ImportError as exc:
        return ("FAIL", f"{mod}: IMPORT FAILED: {exc}")
    version = getattr(module, "__version__", "installed (no __version__)")
    return ("PASS", f"{mod} {version}")


def check_create_app():
    try:
        from backend.api import create_app
    except Exception:
        return ("FAIL", "import backend.api:create_app failed:\n"
                + traceback.format_exc())
    try:
        app = create_app()
    except Exception:
        return ("FAIL", "create_app() raised:\n" + traceback.format_exc())
    return ("PASS", f"create_app() ok ({type(app).__name__})", app)


def check_routes(app):
    try:
        if callable(getattr(app, "openapi", None)):
            paths = sorted(f"{method.upper()} {path}" for path, operations in app.openapi().get("paths", {}).items() if path.startswith("/api/v2") for method in operations if method in ("get", "post"))
        else:
            paths = sorted(r.path for r in app.routes
                           if getattr(r, "path", "").startswith("/api/v2"))
    except Exception as exc:
        return ("FAIL", f"route list failed: {exc!r}")
    if len(paths) != EXPECT_ROUTES:
        return ("FAIL", f"{len(paths)} routes under /api/v2, want "
                f"{EXPECT_ROUTES}:\n  " + "\n  ".join(paths))
    return ("PASS", f"{len(paths)} routes under /api/v2")


def check_store_writable():
    try:
        import backend.persist  # noqa: F401
    except Exception as exc:
        return ("FAIL", f"import backend.persist failed: {exc!r}")
    if os.environ.get("MONGO_URL"):
        try:
            import backend.persist.mongo  # noqa: F401
        except Exception as exc:
            return ("FAIL", f"MONGO_URL set but mongo store failed: {exc!r}")
        return ("WARN", "MONGO_URL set: mongo mode (connectivity verified "
                "only at boot)")
    try:
        root = os.path.join(os.getcwd(), "data")
        os.makedirs(root, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=root, prefix=".doctor-")
        os.close(fd)
        os.remove(tmp)
    except OSError as exc:
        return ("FAIL", f"store dir {root} not writable: {exc}")
    return ("PASS", f"file store writable: {root}")


def check_port(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    try:
        if sock.connect_ex(("127.0.0.1", port)) == 0:
            return ("WARN", f"port {port}: SOMETHING RESPONDS "
                    f"(already running?)")
        return ("PASS", f"port {port}: free")
    finally:
        sock.close()


def run_checks():
    """Run all checks. Returns (lines, failed: bool)."""
    lines = []
    failed = False

    def emit(name, status, detail):
        lines.append(f"[{status:4}] {name}: {detail.splitlines()[0]}")
        for extra in detail.splitlines()[1:]:
            lines.append(f"        {extra}")

    status, detail = check_python()
    emit("python", status, detail)
    for mod in ("fastapi", "uvicorn", "pydantic"):
        status, detail = check_import(mod)
        emit(f"import {mod}", status, detail)
        if status == "FAIL":
            failed = True
    app = None
    if not failed:
        status, detail, *rest = check_create_app()
        emit("create_app", status, detail)
        if status == "FAIL":
            failed = True
        else:
            app = rest[0]
            status, detail = check_routes(app)
            emit("routes", status, detail)
            if status == "FAIL":
                failed = True
    else:
        emit("create_app", "SKIP", "imports failed; fix pip install first")
        emit("routes", "SKIP", "imports failed; fix pip install first")
    status, detail = check_store_writable()
    emit("store", status, detail)
    if status == "FAIL":
        failed = True
    for port in (8000, 5194):
        emit(f"port {port}", *check_port(port))
    return lines, failed


def main():
    lines, failed = run_checks()
    print("VERIFICATION DOCTOR")
    for line in lines:
        print(line)
    print("RESULT:", "FAIL - fix the FAIL lines above" if failed
          else "PASS - safe to boot")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
