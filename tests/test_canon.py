"""Canon tests: -0.0 normalization + hash-preimage routing lock.

Run from meta bro root:  python tests/test_canon.py
Rule: every engine hash feeds on engine.canon bytes, except the
documented raw cases below. If you add a new hash call site, add it
to the allowlist WITH a reason, or route it through canon.
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, os.path.join(BASE, "packages"))

from engine import canonical_hash, canonical_json  # noqa: E402
from engine.canon import canonical_bytes, canonical_str  # noqa: E402

NAN = float("nan")
INF = float("inf")


class TestCanon(unittest.TestCase):
    def test_neg_zero_normalized(self):
        self.assertEqual(canonical_hash({"a": -0.0}),
                         canonical_hash({"a": 0.0}))
        self.assertEqual(canonical_hash({"n": [{"x": -0.0}]}),
                         canonical_hash({"n": [{"x": 0.0}]}))
        self.assertIn('"a":0.0', canonical_str({"a": -0.0}))

    def test_int_zero_not_floated(self):
        self.assertIn('"a":0}', canonical_str({"a": 0}))
        self.assertNotEqual(canonical_hash({"a": 0}),
                            canonical_hash({"a": 0.0}))

    def test_rejections(self):
        for bad in (NAN, INF, -INF):
            with self.assertRaises(ValueError, msg=bad):
                canonical_hash({"a": bad})
            with self.assertRaises(ValueError, msg=bad):
                canonical_hash([bad])
        with self.assertRaises(ValueError):
            canonical_hash({5: "x"})
        with self.assertRaises(ValueError):
            canonical_hash({"a": {"b": NAN}})

    def test_wrappers_agree(self):
        obj = {"b": [1, 2.5, "x"], "a": {"z": None, "y": True}}
        self.assertEqual(canonical_json(obj), canonical_str(obj))
        self.assertIsInstance(canonical_bytes(obj), bytes)
        self.assertEqual(canonical_bytes(obj),
                         canonical_str(obj).encode("utf-8"))

    def test_deterministic_bytes(self):
        obj = {"z": [{"b": 1.5, "a": [3, 2]}], "a": "txt"}
        first = canonical_bytes(obj)
        for _ in range(5):
            self.assertEqual(canonical_bytes(obj), first)


# Allowlist: files that may feed hashes WITHOUT canon bytes, and why.
# Everything else must route through canonical_hash/canonical_bytes.
RAW_OK = {
    # engine files using sha256_hex(f-string id tags / doc bytes):
    "packages/engine/panel.py": "f-string commitment tags (str-only)",
    "packages/engine/property.py": "f-string spec tag (validated parts)",
    "packages/engine/report.py": "report HTML document bytes",
    # direct hashlib users with their own deterministic format:
    "backend/provenance/duplicates.py": "SimHash token bytes (utf-8)",
    "backend/provenance/mixtrack.py": "registry dumps (sorted+separators)",
}


class TestHashRouting(unittest.TestCase):
    def _files(self, root, suffix=".py"):
        for dirpath, _, names in os.walk(root):
            for name in sorted(names):
                if name.endswith(suffix):
                    yield os.path.join(dirpath, name)

    def test_engine_hashlib_only_in_canon_core(self):
        allowed = {"__init__.py", "canon.py"}
        for path in self._files(os.path.join(BASE, "packages", "engine")):
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            if "hashlib" in text:
                self.assertIn(os.path.basename(path), allowed,
                              f"{path}: raw hashlib outside canon core")

    def test_eval_provenance_hashlib_allowlisted(self):
        allowed = {"duplicates.py", "mixtrack.py"}
        for sub in ("backend/eval", "backend/provenance"):
            for path in self._files(os.path.join(BASE, sub)):
                with open(path, encoding="utf-8") as handle:
                    text = handle.read()
                if "hashlib" in text:
                    self.assertIn(os.path.basename(path), allowed,
                                  f"{path}: raw hashlib not allowlisted")

    def test_service_and_tools_use_canonical_only(self):
        paths = [os.path.join(BASE, "backend", "service_app.py")]
        paths.extend(self._files(os.path.join(BASE, "backend", "tools")))
        for path in paths:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            self.assertNotIn("hashlib.", text,
                             f"{path}: use canonical_hash, not hashlib")
            self.assertNotIn("sha256_hex(", text,
                             f"{path}: use canonical_hash, not sha256_hex")

    def test_raw_ok_documents_every_exception(self):
        for rel, reason in RAW_OK.items():
            # Split: the \\?\ extended prefix forbids forward slashes.
            full = os.path.join(BASE, *rel.split("/"))
            self.assertTrue(
                os.path.isfile(full),
                f"allowlist stale: {rel} gone (remove it)")
            self.assertTrue(len(reason) > 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
