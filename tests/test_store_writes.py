"""Store write integrity: fsync, single-writer lock, orphan cleanup.

Run from meta bro root:  python tests/test_store_writes.py
Doc writes are tmp+flush+fsync+replace; the ledger appends are
flushed+fsynced; a second concurrent writer is refused LOUDLY via
store.lock (per-operation lock, pid inside); stale .tmp orphans
from a crashed write are ignored and cleaned on next open.
"""

import os
import shutil
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from backend.persist.filelayout import FileLayoutStore, StoreError  # noqa: E402


class TestStoreWrites(unittest.TestCase):
    def setUp(self):
        self.root = os.path.join(BASE, "tests", "_writes_tmp")
        self.store = FileLayoutStore(self.root)
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_round_trip(self):
        self.store.save("runs", "run_w1", {"v": [1, 2, 3]})
        found = self.store.get("runs", "run_w1")
        self.assertEqual(found["doc"], {"v": [1, 2, 3]})
        self.assertIn("stored_at", found)

    def test_no_lock_left_after_ops(self):
        self.store.save("runs", "run_w1", {"v": 1})
        self.store.append_ledger({"index": 0, "type": "T"})
        self.assertFalse(os.path.exists(
            os.path.join(self.root, "store.lock")))

    def test_second_writer_refused_loudly(self):
        lock = os.path.join(self.root, "store.lock")
        with open(lock, "w", encoding="utf-8") as handle:
            handle.write("999999")
        with self.assertRaises(StoreError) as ctx:
            self.store.save("runs", "run_w2", {"v": 1})
        self.assertIn("store.lock", str(ctx.exception))
        with self.assertRaises(StoreError) as ctx2:
            self.store.append_ledger({"index": 0, "type": "T"})
        self.assertIn("store.lock", str(ctx2.exception))
        self.assertTrue(os.path.exists(lock))  # we do not clear it
        self.assertIsNone(self.store.get("runs", "run_w2"))
        os.remove(lock)
        self.store.save("runs", "run_w2", {"v": 1})  # works again
        self.assertIsNotNone(self.store.get("runs", "run_w2"))

    def test_orphan_tmp_cleaned_on_open(self):
        orphan = os.path.join(self.root, "runs", "run_x.json.tmp")
        with open(orphan, "w", encoding="utf-8") as handle:
            handle.write('{"partial": ')
        reopened = FileLayoutStore(self.root)
        self.assertFalse(os.path.exists(orphan))
        self.assertEqual(reopened.list_ids("runs"), [])
        reopened.save("runs", "run_ok", {"v": 1})
        self.assertEqual(reopened.list_ids("runs"), ["run_ok"])

    def test_ledger_append_readback(self):
        for i in range(5):
            count = self.store.append_ledger({"index": i, "type": "E"})
            self.assertEqual(count, i + 1)
        entries = self.store.read_ledger()
        self.assertEqual(len(entries), 5)
        self.assertEqual([e["index"] for e in entries], list(range(5)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
