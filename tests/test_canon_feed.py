"""Hash-preimage choke point: hashlib fed only by canon or raw bytes.

Run from meta bro root:  python tests/test_canon_feed.py
Every hashlib call in engine + night-shift backend code must feed on
canonical bytes (single serialization contract) or on raw validated
bytes (file content, tokens). Mirror-app files (backend/*.py top
level) are out of scope per D-night-1 and not scanned.
"""

import os
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCAN_DIRS = [os.path.join(BASE, "packages", "engine"),
             os.path.join(BASE, "backend", "provenance"),
             os.path.join(BASE, "backend", "eval"),
             os.path.join(BASE, "backend", "persist"),
             os.path.join(BASE, "backend", "tools")]

# (substring, justification): raw-byte feeds that need no serialization.
RAW_ALLOWLIST = [
    ("hashlib.sha256(data)",
     "engine.sha256_hex is the byte primitive; JSON callers pass canon bytes"),
    ('token.encode("utf-8")',
     "duplicates SimHash: raw UTF-8 of a validated token, no structure"),
]


def iter_py_files():
    for root in SCAN_DIRS:
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in sorted(filenames):
                if name.endswith(".py"):
                    yield os.path.join(dirpath, name)


def offenders():
    bad = []
    for path in iter_py_files():
        with open(path, encoding="utf-8") as handle:
            for num, line in enumerate(handle, 1):
                if "hashlib." not in line:
                    continue
                if any(fn in line for fn in ("canonical_bytes",
                                             "canonical_str",
                                             "canonical_hash",
                                             "canonical_json")):
                    continue
                if any(snippet in line
                       for snippet, _ in RAW_ALLOWLIST):
                    continue
                bad.append(f"{os.path.relpath(path, BASE)}:{num}: "
                           f"{line.strip()}")
    return bad


class TestCanonFeed(unittest.TestCase):
    def test_no_ad_hoc_hash_preimages(self):
        self.assertEqual(offenders(), [])

    def test_allowlist_still_used(self):
        seen = {snippet: False for snippet, _ in RAW_ALLOWLIST}
        for path in iter_py_files():
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            for snippet in seen:
                if snippet in text:
                    seen[snippet] = True
        for snippet, used in seen.items():
            self.assertTrue(used, f"stale allowlist entry: {snippet}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
