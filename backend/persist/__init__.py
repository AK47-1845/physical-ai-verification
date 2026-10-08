"""Persistence picker: Mongo when MONGO_URL is set, file layout otherwise.

Explicit configuration never degrades silently: MONGO_URL set but
unusable => loud error telling exactly what to install/configure.
"""

import os


def open_store(root: str = "./data"):
    """Return a store with save/get/list_ids/append_ledger/read_ledger."""
    mongo_url = os.environ.get("MONGO_URL")
    if mongo_url:
        from backend.persist.mongo import MongoStore
        return MongoStore(mongo_url)
    from backend.persist.filelayout import FileLayoutStore
    return FileLayoutStore(root=root)
