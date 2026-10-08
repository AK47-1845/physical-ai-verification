from __future__ import annotations

import hashlib
import hmac
import io
import json
import zipfile

from backend.engine import canonical, fingerprint
from backend.store import ZERO_HASH, new_id, now_iso

MAX_EXPANDED_BYTES = 16 * 1024 * 1024
MEMBERS = {"trace.json", "assessment.json", "gate-profile.json", "run.json", "reviews.json", "audit.json", "README.txt"}


def make_bundle(run: dict, audit: list[dict], reviews: list[dict], secret: str) -> tuple[bytes, dict]:
    data = run["data"]
    files = {
        "trace.json": canonical(data["trace"]).encode(),
        "assessment.json": canonical(data["result"]).encode(),
        "gate-profile.json": canonical(data["profile"]).encode(),
        "run.json": canonical({key: value for key, value in run.items() if key != "data"}).encode(),
        "reviews.json": canonical(reviews).encode(),
        "audit.json": canonical(sorted(audit, key=lambda entry: entry["sequence"])).encode(),
        "README.txt": ("PHYSICAL AI VERIFICATION | EVIDENCE PACKAGE\n\n"
                       "This is an engineering evidence package, not a safety certificate or CE declaration.\n"
                       "Draft thresholds and synthetic inputs retain their original qualification labels.\n"
                       "SHA256 checks establish internal consistency. HMAC origin verification needs the issuing instance.\n"
                       "A local audit chain is not WORM storage or independent notarization.\n"
                       "Run tools/verify_bundle.py against this ZIP for offline integrity checks.\n").encode(),
    }
    manifest = {"schema": "verification.evidence/1", "id": new_id("bundle"), "run_id": run["id"], "created_at": now_iso(),
                "files": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}}
    manifest_bytes = canonical(manifest).encode()
    signature = {"algorithm": "HMAC-SHA256", "key_id": hashlib.sha256(secret.encode()).hexdigest()[:16],
                 "value": hmac.new(secret.encode(), manifest_bytes, hashlib.sha256).hexdigest()}
    if sum(map(len, files.values())) > MAX_EXPANDED_BYTES:
        raise ValueError("Evidence package exceeds bounded export size; archive and checkpoint the audit history")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        archive.writestr("manifest.json", manifest_bytes)
        archive.writestr("signature.json", canonical(signature))
    return buffer.getvalue(), manifest


def verify_bundle(content: bytes, secret: str | None = None) -> dict:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(names) != len(set(names)) or set(names) != MEMBERS | {"manifest.json", "signature.json"}:
                raise ValueError("Unexpected, duplicate, or missing package members")
            if any(entry.flag_bits & 1 for entry in entries) or sum(entry.file_size for entry in entries) > MAX_EXPANDED_BYTES:
                raise ValueError("Encrypted or oversized package")
            files = {name: archive.read(name) for name in names}
        manifest = json.loads(files["manifest.json"])
        if manifest.get("schema") != "verification.evidence/1" or set(manifest["files"]) != MEMBERS:
            raise ValueError("Unsupported manifest")
        for name, digest in manifest["files"].items():
            if not hmac.compare_digest(hashlib.sha256(files[name]).hexdigest(), digest):
                raise ValueError(f"Content mismatch: {name}")
        assessment = json.loads(files["assessment.json"])
        trace = json.loads(files["trace.json"])
        profile = json.loads(files["gate-profile.json"])
        if assessment["input_hash"] != fingerprint(trace) or assessment["profile_hash"] != fingerprint(profile):
            raise ValueError("Assessment inputs or profile do not match")
        stored_result_hash = assessment.pop("result_hash")
        if fingerprint(assessment) != stored_result_hash:
            raise ValueError("Assessment result hash mismatch")
        audit = json.loads(files["audit.json"])
        head = ZERO_HASH
        for sequence, entry in enumerate(audit, start=1):
            event_hash = entry.pop("event_hash")
            if entry["sequence"] != sequence or entry["previous_hash"] != head or fingerprint(entry) != event_hash:
                raise ValueError("Audit chain mismatch")
            head = event_hash
        signature = json.loads(files["signature.json"])
        origin = False
        if secret is not None:
            expected = hmac.new(secret.encode(), canonical(manifest).encode(), hashlib.sha256).hexdigest()
            origin = signature.get("algorithm") == "HMAC-SHA256" and hmac.compare_digest(expected, signature["value"])
            if not origin:
                raise ValueError("Issuing-instance signature not verified")
        return {"valid": True, "origin_verified": origin, "files_checked": len(MEMBERS), "audit_entries": len(audit),
                "audit_head": head, "run_id": manifest["run_id"], "bundle_id": manifest["id"],
                "qualification": "Internal integrity and issuing-instance HMAC" if origin else "Internal integrity only; origin is not independently verified"}
    except (ValueError, KeyError, TypeError, AttributeError, RuntimeError, OSError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        return {"valid": False, "origin_verified": False, "reason": str(error)[:300]}