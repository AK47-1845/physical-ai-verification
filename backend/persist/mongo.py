"""Mongo store: same interface as filelayout, over pymongo.

Collections: pilots, runs, dossiers, corpora, manifests (keyed by
_id = doc_id), ledger (sequence-ordered). Envelopes {doc,
stored_at} match filelayout byte-for-shape. pymongo imports lazily
so the zero-dep path never pays for it. Ledger sequence is
count-based (V1 limitation: single writer).

Error parity with filelayout (114/116): bad docs/shapes ->
ValueError (service renders 422); connection loss propagates raw
(perimeter renders 500 with request id). Same split as files.
"""

from datetime import datetime, timezone

from engine import InputError

_COLLECTIONS = ("pilots", "runs", "dossiers", "corpora", "manifests")


def _check_collection(collection: str) -> None:
    if collection not in _COLLECTIONS:
        raise InputError(f"unknown collection {collection!r}")


class MongoStore:
    """Document persistence for intake + provenance workloads."""

    def __init__(self, uri: str, db: str = "verification"):
        try:
            from pymongo import MongoClient
        except ImportError:
            raise RuntimeError(
                "MONGO_URL is set but pymongo is not installed: "
                "pip install -r backend/requirements-service.txt")
        try:
            self._client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            self._client.admin.command("ping")
        except Exception as exc:
            raise RuntimeError(f"Mongo unreachable at configured URI: {exc!r}")
        self._db = self._client[db]

    @staticmethod
    def _utcnow() -> str:
        return datetime.now(timezone.utc).isoformat()

    def save(self, collection: str, doc_id: str, doc: dict) -> dict:
        """Upsert {doc, stored_at} under _id = doc_id."""
        _check_collection(collection)
        if not isinstance(doc, dict):
            raise InputError("doc: dict required")
        envelope = {"_id": doc_id, "doc": doc,
                    "stored_at": self._utcnow()}
        try:
            self._db[collection].replace_one({"_id": doc_id}, envelope,
                                             upsert=True)
        except Exception as exc:
            raise ValueError(f"save failed: {exc!r}")
        return {"doc": doc, "stored_at": envelope["stored_at"]}

    def get(self, collection: str, doc_id: str):
        """Read one envelope, or None when missing (never raises)."""
        if collection not in _COLLECTIONS:
            return None
        try:
            found = self._db[collection].find_one({"_id": doc_id})
        except Exception:
            return None
        if not found:
            return None
        try:
            return {"doc": found["doc"], "stored_at": found["stored_at"]}
        except (KeyError, TypeError):
            return None

    def list_ids(self, collection: str) -> list:
        """Sorted doc ids in a collection.

        Connection faults propagate raw (500, like filelayout's
        OSError): a dead store is infra, not a client error.
        """
        _check_collection(collection)
        ids = [d["_id"] for d in self._db[collection].find({}, {"_id": 1})]
        return sorted(str(i) for i in ids)

    def append_ledger(self, entry: dict) -> int:
        """Append one ledger entry. Returns the new sequence number."""
        if not isinstance(entry, dict):
            raise InputError("entry: dict required")
        seq = self._db["ledger"].count_documents({}) + 1
        self._db["ledger"].insert_one({"seq": seq, "entry": entry,
                                       "stored_at": self._utcnow()})
        return seq

    def read_ledger(self) -> list:
        """Read the full chain in sequence order.

        Malformed docs -> ValueError (service renders the
        corrupt-ledger 422/verdict, same as bad JSONL lines);
        connection faults propagate raw (500).
        """
        cursor = self._db["ledger"].find({}).sort("seq", 1)
        entries = []
        for doc in cursor:
            try:
                entries.append(doc["entry"])
            except (KeyError, TypeError) as exc:
                raise InputError(
                    f"stored ledger is corrupt: {exc!r}")
        return entries
