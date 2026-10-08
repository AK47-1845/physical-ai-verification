from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT.parent / "5th oct"
MARKER = DESTINATION / ".verification-oct5-transfer"
ROOTS = ("backend", "packages", "site", "web", "tests", "tools", "docs", "handoff")
SKIP_DIRS = {"node_modules", ".venv", ".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".backups", "test-results", "playwright-report", "dist", "out"}
SKIP_NAMES = {".instance-secret", ".lab-secret", "tsconfig.tsbuildinfo", ".DS_Store"}


def excluded(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in SKIP_DIRS or part.startswith(".next") for part in relative.parts):
        return True
    if path.name in SKIP_NAMES or path.name.startswith("RECON_"):
        return True
    if path.name.startswith(".env") and path.name != ".env.example":
        return True
    if path.suffix in {".pyc", ".log", ".db", ".sqlite3", ".zip"} or path.name.endswith(("-wal", "-shm")):
        return True
    return False


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    if DESTINATION.exists() and not MARKER.exists():
        raise SystemExit("Refusing to overwrite an unrecognized 5th oct directory")
    DESTINATION.mkdir(exist_ok=True)
    MARKER.write_text("verification-oct5-transfer-v1\n", encoding="ascii")
    paths = [path for path in ROOT.iterdir() if path.is_file() and not excluded(path)]
    for folder in ROOTS:
        base = ROOT / folder
        if base.exists():
            paths.extend(path for path in base.rglob("*") if path.is_file() and not path.is_symlink() and not excluded(path))
    evidence = ROOT / "design-intel" / "astra"
    if evidence.exists():
        paths.extend(path for path in evidence.rglob("*") if path.is_file() and not excluded(path))
    records = []
    for source in sorted(set(paths)):
        relative = source.relative_to(ROOT)
        target = DESTINATION / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        before = digest(source)
        shutil.copy2(source, target)
        if digest(target) != before or digest(source) != before:
            raise SystemExit(f"Source changed or copy verification failed: {relative}")
        records.append({"path": relative.as_posix(), "bytes": target.stat().st_size, "sha256": before})
    partner = ROOT.parent / "real claude bro"
    partner_manifest = partner / "FRONTEND_PARTNER_MANIFEST.json"
    if partner_manifest.exists():
        manifest = json.loads(partner_manifest.read_text(encoding="utf-8-sig"))
        partner_files = [partner_manifest, partner / "FRONTEND_PARTNER_HANDOFF.md"]
        partner_files.extend(partner / item["path"] for item in manifest["files"])
        for source in partner_files:
            if not source.exists():
                continue
            relative = Path("partner-candidate") / source.relative_to(partner)
            target = DESTINATION / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            before = digest(source)
            shutil.copy2(source, target)
            if digest(target) != before:
                raise SystemExit(f"Partner copy failed: {relative}")
            records.append({"path": relative.as_posix(), "bytes": target.stat().st_size, "sha256": before})
    report = {"schema": "verification.oct5-transfer/1", "created_at": datetime.now(timezone.utc).isoformat(), "files": records, "bytes": sum(row["bytes"] for row in records), "excluded": ["dependencies", "runtime databases", "secrets", "build caches", "redundant source research", "older reconnaissance logs"], "installation": "uv sync --frozen; npm.cmd --prefix site ci", "source": "gpt astra bro integrated implementation; partner-candidate retained separately for review"}
    (DESTINATION / "TRANSFER_MANIFEST.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"TRANSFER VERIFIED: {len(records)} files; {report['bytes'] / 1048576:.2f} MiB; {DESTINATION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())