"""File-layout store: JSON docs + JSONL ledger. Zero dependencies.

Directory layout under a root (default ./data):
  pilots/<id>.json  runs/<id>.json  dossiers/<id>.json
  corpora/<id>.json  ledger.jsonl (append-only hash chain)
IDs are caller-supplied or content-derived (service uses content hashes).
Wall-clock stamps (stored_at) live OUTSIDE hashed bodies: the store wraps
{doc, stored_at}, and hashes cover doc only. Same interface as mongo.py.
"""

import json
import os
import re
from datetime import datetime, timezone

COLLECTIONS = ("pilots", "runs", "dossiers", "corpora", "manifests")

_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,128}")

_RESERVED_STEMS = frozenset(
    ["con", "prn", "aux", "nul"] +
    [f"com{i}" for i in range(1, 10)] +
    [f"lpt{i}" for i in range(1, 10)])


class StoreError(ValueError):
    """Itemized store failure. Server formats these, never traces."""


def _fs_path(path: str) -> str:
    """OS path for actual file I/O (extended-length on Windows).

    The store promises 128-char IDs, but a deep checkout can push the
    joined path past Win32 MAX_PATH (260) when long paths are off.
    Prefixing absolute paths with ``\\\\?\\`` lifts that ceiling for
    every I/O call without touching the security check in _doc_path
    (which keeps comparing plain realpaths). Idempotent; UNC roots
    map to the ``\\\\?\\UNC\\`` form. Non-Windows paths pass through.
    """
    if os.name != "nt" or path.startswith("\\\\?\\"):
        return path
    apath = os.path.abspath(path)
    if apath.startswith("\\\\"):
        return "\\\\?\\UNC\\" + apath[2:]
    return "\\\\?\\" + apath


def validate_id(doc_id: str) -> str:
    """Single choke: is this string safe to become a filename?

    Strict charset + length, no bare dots, no leading dot (hidden
    files), no trailing dot/space (Windows strips them, aliasing
    distinct ids), no Windows-reserved stems with or without an
    extension. Service routes call this for 422s; _doc_path calls
    it before any path join. Returns the id unchanged.
    """
    if not isinstance(doc_id, str) or _ID_RE.fullmatch(doc_id) is None:
        raise StoreError(f"unsafe doc_id {doc_id!r}")
    if doc_id in (".", "..") or doc_id.startswith("."):
        raise StoreError(f"unsafe doc_id {doc_id!r}")
    if doc_id.endswith((".", " ")):
        raise StoreError(f"unsafe doc_id {doc_id!r}")
    stem = doc_id.split(".", 1)[0].lower()
    if stem in _RESERVED_STEMS:
        raise StoreError(f"unsafe doc_id {doc_id!r}")
    return doc_id


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class FileLayoutStore:
    """JSON-file persistence. Atomic-ish writes via tmp + rename."""

    def __init__(self, root: str = "./data"):
        self.root = os.path.abspath(root)
        try:
            for name in COLLECTIONS:
                os.makedirs(os.path.join(self.root, name), exist_ok=True)
        except OSError as exc:
            raise StoreError(f"store init: {exc}") from exc
        self._ledger_path = os.path.join(self.root, "ledger.jsonl")
        if not os.path.exists(self._ledger_path):
            try:
                open(self._ledger_path, "a", encoding="utf-8",
                     newline="\n").close()
            except OSError as exc:
                raise StoreError(f"ledger init: {exc}") from exc
        self._lock_path = os.path.join(self.root, "store.lock")
        self._clean_orphans()

    def _clean_orphans(self) -> None:
        """Remove stale .tmp files from crashed writes (best effort)."""
        for name in COLLECTIONS:
            folder = os.path.join(self.root, name)
            try:
                files = os.listdir(folder)
            except OSError:
                continue
            for fname in files:
                if fname.endswith(".tmp"):
                    try:
                        os.remove(_fs_path(os.path.join(folder, fname)))
                    except OSError:
                        pass

    def _locked(self, func, *args):
        """Run one write under the single-writer guard (store.lock).

        The lock is held only for the write itself and always
        released. A leftover lock means a crashed writer or a live
        one: we refuse LOUDLY and never clear it ourselves (deleting
        it while a writer runs would corrupt the store). Recovery:
        confirm no writer runs, delete store.lock, retry.
        """
        try:
            fd = os.open(self._lock_path,
                         os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise StoreError(
                f"store locked by another writer ({self._lock_path}); "
                f"if no writer is running, delete it and retry")
        except OSError as exc:
            raise StoreError(f"lock failed: {exc}") from exc
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(str(os.getpid()))
            return func(*args)
        finally:
            try:
                os.remove(self._lock_path)
            except OSError:
                pass

    def _doc_path(self, collection: str, doc_id: str) -> str:
        if collection not in COLLECTIONS:
            raise StoreError(f"unknown collection {collection!r}")
        validate_id(doc_id)
        joined = os.path.join(self.root, collection, doc_id + ".json")
        real_root = os.path.realpath(self.root)
        if os.path.commonpath([real_root, os.path.realpath(joined)]) \
                != real_root:
            raise StoreError(f"unsafe doc_id {doc_id!r}")
        return _fs_path(joined)

    def save(self, collection: str, doc_id: str, doc: dict) -> dict:
        """Write {doc, stored_at} (tmp + fsync + replace). Returns it."""
        if not isinstance(doc, dict):
            raise StoreError("doc: dict required")
        envelope = {"doc": doc, "stored_at": _utcnow()}
        path = self._doc_path(collection, doc_id)
        return self._locked(self._save_locked, path, envelope)

    def _save_locked(self, path: str, envelope: dict) -> dict:
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(envelope, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
        except (OSError, TypeError, ValueError) as exc:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise StoreError(f"save failed: {exc}") from exc
        try:
            os.replace(tmp, path)
        except OSError as exc:
            raise StoreError(f"save failed: {exc}") from exc
        return envelope

    def get(self, collection: str, doc_id: str):
        """Read one envelope, or None when missing (never raises)."""
        try:
            with open(self._doc_path(collection, doc_id),
                      encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return None

    def list_ids(self, collection: str) -> list:
        """Sorted doc ids in a collection."""
        if collection not in COLLECTIONS:
            raise StoreError(f"unknown collection {collection!r}")
        folder = os.path.join(self.root, collection)
        return sorted(name[:-5] for name in os.listdir(folder)
                      if name.endswith(".json"))

    def append_ledger(self, entry: dict) -> int:
        """Append one ledger entry (dict). Returns the new line count."""
        if not isinstance(entry, dict):
            raise StoreError("entry: dict required")
        return self._locked(self._append_locked, entry)

    def _append_locked(self, entry: dict) -> int:
        try:
            with open(self._ledger_path, "a", encoding="utf-8",
                       newline="\n") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise StoreError(f"ledger append failed: {exc}") from exc
        try:
            with open(self._ledger_path, encoding="utf-8") as handle:
                return sum(1 for _ in handle)
        except OSError as exc:
            raise StoreError(f"ledger readback failed: {exc}") from exc

    def read_ledger(self) -> list:
        """Read the full chain (verify with engine.ledger.verify)."""
        entries = []
        with open(self._ledger_path, encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    entries.append(json.loads(line))
        return entries
