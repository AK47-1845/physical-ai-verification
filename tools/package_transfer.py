from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT.parent / "Verification-TRANSFER-2026-10-01.zip"


def git(*arguments: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *arguments])


def main() -> None:
    if git("status", "--porcelain").strip():
        raise SystemExit("Commit or preserve pending changes before packaging; refusing an ambiguous baseline")
    preview = ROOT / "site" / ".next-transfer"
    if not (preview / "index.html").exists():
        raise SystemExit("Build the static preview first with VERIFICATION_STATIC_EXPORT=1")
    commit = git("rev-parse", "HEAD").decode().strip()
    tracked = [ROOT / name for name in git("ls-files", "-z").decode().split("\0") if name]
    files = {f"claude bro/{source.relative_to(ROOT).as_posix()}": source for source in tracked}
    for source in preview.rglob("*"):
        if source.is_file():
            files[f"claude bro/portable-preview/{source.relative_to(preview).as_posix()}"] = source
    for source in ROOT.parent.glob("*.pdf"):
        files[source.name] = source
    manifest = {"schema": "verification.transfer/1", "commit": commit, "created_at": datetime.now(timezone.utc).isoformat(),
                "excludes": ["installed dependencies", "virtual environments", "runtime database", "session/signing secrets", "machine-local build cache"], "files": {}}
    with tempfile.TemporaryDirectory() as temporary:
        bundle = Path(temporary) / "Verification-history.bundle"
        subprocess.run(["git", "-C", str(ROOT), "bundle", "create", str(bundle), "--all"], check=True)
        subprocess.run(["git", "-C", str(ROOT), "bundle", "verify", str(bundle)], check=True, capture_output=True)
        files[bundle.name] = bundle
        with zipfile.ZipFile(ARCHIVE, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name, source in sorted(files.items()):
                content = source.read_bytes()
                manifest["files"][name] = {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
                archive.writestr(name, content)
            archive.writestr("TRANSFER_MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
        with zipfile.ZipFile(ARCHIVE) as archive:
            if archive.testzip() is not None:
                raise RuntimeError("Archive CRC verification failed")
            for name, entry in manifest["files"].items():
                if hashlib.sha256(archive.read(name)).hexdigest() != entry["sha256"]:
                    raise RuntimeError(f"Archive checksum mismatch: {name}")
    with ARCHIVE.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    receipt = {"archive": ARCHIVE.name, "sha256": digest, "bytes": ARCHIVE.stat().st_size,
               "files_verified": len(files), "commit": commit, "git_bundle_verified": True}
    ARCHIVE.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()