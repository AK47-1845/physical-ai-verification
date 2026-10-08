"""Claims lint: no unqualified marketing words in shipped strings.

Run from meta bro root:  python tests/test_claims_lint.py
Scans engine/backend sources, shipped docs, regmap rows, and site
copy (incl. chatbot intents) for words the code cannot back:
real-time, byte-identical, proven, certified, compliant,
accepted/approved by, guaranteed, tamper-proof, is-safe. A hit
passes when negated nearby ("never certified") or when an entry
in backend/docs/claims_allowlist.json excuses that line with a
written justification. Every allowlist entry must still match at
least one hit (no stale excuses). Excluded: RECON intel logs,
changelogs (history), the inventory itself (it quotes hits), and
this file + the allowlist (self-hosting).
"""

import json
import os
import re
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "packages"))

PATTERNS = [
    ("real-time", re.compile(r"real\s*-\s*time|realtime",
                             re.IGNORECASE)),
    ("byte-identical", re.compile(r"byte\s*-\s*identical",
                                  re.IGNORECASE)),
    ("proven", re.compile(r"\bproven\b", re.IGNORECASE)),
    ("certified", re.compile(r"\bcertified\b", re.IGNORECASE)),
    ("compliant", re.compile(r"\bcompliant\b", re.IGNORECASE)),
    ("accepted-by", re.compile(r"\baccepted by\b", re.IGNORECASE)),
    ("approved-by", re.compile(r"\bapproved by\b", re.IGNORECASE)),
    ("guaranteed", re.compile(r"\bguarantee[sd]?\b", re.IGNORECASE)),
    ("tamper-proof", re.compile(r"tamper\s*-\s*proof", re.IGNORECASE)),
    ("is-safe", re.compile(r"\bis safe\b", re.IGNORECASE)),
]

NEGATION = re.compile(
    r"(not|never|no|isn't|is not|aren't|are not|without|cannot|"
    r"can not|can't|won't|don't|do not|doesn't|does not|n't|non|"
    r"falsely)\W*$", re.IGNORECASE)

ALLOWLIST_PATH = os.path.join(BASE, "backend", "docs",
                              "claims_allowlist.json")

SKIP_DIRS = {"__pycache__", "node_modules", ".next", ".git",
             "_anchor_tmp", "_ids_tmp", "_writes_tmp", "_err_tmp",
             "_dow_tmp"}
SKIP_FILES = {"test_claims_lint.py", "claims_allowlist.json",
              "CLAIMS_INVENTORY.md", "BACKEND_CHANGELOG.md",
              "FRONTEND_CHANGELOG.md", "NIGHT_SHIFT_EXPLAINED.md"}
SKIP_PREFIXES = ("RECON_",)


def iter_files():
    roots = [(os.path.join(BASE, "packages", "engine"), (".py",)),
             (os.path.join(BASE, "backend"), (".py", ".md", ".json")),
             (os.path.join(BASE, "tests"), (".py",)),
             (os.path.join(BASE, "site", "src"), (".ts", ".tsx"))]
    for root, exts in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in sorted(filenames):
                if not name.endswith(exts) or name in SKIP_FILES:
                    continue
                if name.startswith(SKIP_PREFIXES):
                    continue
                yield os.path.join(dirpath, name)


def load_allowlist():
    with open(ALLOWLIST_PATH, encoding="utf-8") as handle:
        doc = json.load(handle)
    entries = doc.get("entries", [])
    for entry in entries:
        assert set(entry) >= {"path", "snippet", "why"}, entry
        assert entry["snippet"] and entry["why"], entry
    return entries


def scan():
    entries = load_allowlist()
    used = [False] * len(entries)
    bad = []
    for path in iter_files():
        try:
            with open(path, encoding="utf-8", errors="strict") as handle:
                lines = handle.read().splitlines()
        except (OSError, UnicodeError):
            bad.append((path, 0, "unreadable",
                        "file not UTF-8 or unreadable"))
            continue
        rel = os.path.relpath(path, BASE)
        for num, line in enumerate(lines, 1):
            for word, regex in PATTERNS:
                match = regex.search(line)
                if not match:
                    continue
                before = line[max(0, match.start() - 40):match.start()]
                if NEGATION.search(before):
                    continue
                excused = False
                for idx, entry in enumerate(entries):
                    if rel.replace(os.sep, "/").endswith(
                            entry["path"]) and entry["snippet"] in line:
                        used[idx] = True
                        excused = True
                if not excused:
                    bad.append((rel, num, word, line.strip()[:160]))
    stale = [entries[i] for i, flag in enumerate(used) if not flag]
    return bad, stale


class TestClaimsLint(unittest.TestCase):
    def test_no_unqualified_claims(self):
        bad, _stale = scan()
        if bad:
            sample = "\n".join(f"{path}:{num} [{word}] {line}"
                               for path, num, word, line in bad[:40])
            self.fail(f"{len(bad)} unqualified claim hits:\n{sample}\n"
                      f"Reword the line or add a justified entry to "
                      f"backend/docs/claims_allowlist.json.")

    def test_allowlist_fresh(self):
        _bad, stale = scan()
        self.assertEqual(stale, [])

    def test_regmap_rows_clean(self):
        from engine.regmap import ROWS
        for row in ROWS:
            text = f"{row['id']} {row['topic']} {row['gap']}"
            for word, regex in PATTERNS:
                match = regex.search(text)
                self.assertIsNone(
                    match, f"regmap {row['id']}: {word} in {text!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
