"""ID/path safety: one validator, choke point, no escape.

Run from meta bro root:  python tests/test_ids.py
filelayout.validate_id is the single choke every doc_id passes
through before becoming a path: strict charset, length cap, no
leading/trailing dots, no Windows-reserved stems, plus a
resolve-and-assert-inside-root on the final path. Route-level
422 mapping lives in backend/tests/test_ids_routes.py
(fastapi-gated).
"""

import os
import shutil
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from backend.persist.filelayout import FileLayoutStore, StoreError, _fs_path, validate_id  # noqa: E402

ATTACKS = ["../x", "..\\x", "a/b", "C:\\x", ".", "..", "", "con",
           "CON", "NUL.txt", "aux.json", "com1", "LPT9.dat", "x.",
           "x ", ".hidden", "a" * 129, "caf\u00e9",
           "\u0441on", "a/b/c", "\\\\server\\x", "x\x00y"]

VALID = ["a", "run_abc123def456", "dos_0123456789ab",
         "pilot_ffffffffffff", "A-9._x", "x" * 128,
         "UPPER-lower_09.-"]


class TestValidateId(unittest.TestCase):
    def test_attacks_rejected(self):
        for bad in ATTACKS:
            with self.assertRaises(StoreError, msg=f"accepted: {bad!r}"):
                validate_id(bad)

    def test_non_strings_rejected(self):
        for bad in (None, 0, 123, True, [], {}, ("x",)):
            with self.assertRaises(StoreError, msg=f"accepted: {bad!r}"):
                validate_id(bad)

    def test_valid_accepted(self):
        for good in VALID:
            self.assertEqual(validate_id(good), good)


class TestStoreChoke(unittest.TestCase):
    def setUp(self):
        self.root = os.path.join(BASE, "tests", "_ids_tmp")
        self.store = FileLayoutStore(self.root)
        self.before = set(os.listdir(os.path.dirname(self.root)))
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_save_rejects_attacks(self):
        for bad in ATTACKS:
            with self.assertRaises(StoreError, msg=f"saved: {bad!r}"):
                self.store.save("runs", bad, {"x": 1})

    def test_get_never_escapes(self):
        for bad in ATTACKS:
            self.assertIsNone(self.store.get("runs", bad),
                              f"get leaked: {bad!r}")

    def test_no_files_escape_root(self):
        for bad in ATTACKS:
            try:
                self.store.save("runs", bad, {"x": 1})
            except StoreError:
                pass
            self.store.get("runs", bad)
        after = set(os.listdir(os.path.dirname(self.root)))
        self.assertEqual(after, self.before)

    def test_written_files_stay_inside_root(self):
        self.store.save("runs", "run_ok1", {"x": 1})
        self.store.save("dossiers", "dos_ok2", {"x": 2})
        real_root = os.path.realpath(self.root)
        for dirpath, _d, files in os.walk(self.root):
            for name in files:
                full = os.path.realpath(os.path.join(dirpath, name))
                self.assertTrue(full.startswith(real_root + os.sep),
                                f"escaped: {full}")

    def test_valid_round_trip(self):
        for good in VALID:
            self.store.save("runs", good, {"v": good})
            found = self.store.get("runs", good)
            self.assertEqual(found["doc"], {"v": good})
        self.assertEqual(sorted(self.store.list_ids("runs")),
                         sorted(VALID))


class TestFsPath(unittest.TestCase):
    def test_extended_length_mapping(self):
        if os.name != "nt":
            self.assertEqual(_fs_path("/tmp/x.json"), "/tmp/x.json")
            return
        plain = os.path.abspath(os.path.join("some", "dir", "x.json"))
        prefixed = _fs_path(plain)
        self.assertTrue(prefixed.startswith("\\\\?\\"))
        self.assertTrue(prefixed.endswith("x.json"))
        self.assertEqual(_fs_path(prefixed), prefixed)
        unc = _fs_path("\\\\server\\share\\x.json")
        self.assertTrue(unc.startswith("\\\\?\\UNC\\server\\share"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
