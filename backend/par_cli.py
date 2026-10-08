"""Offline PAR reader + ledger anchor CLI (FR-38, B4).

Stdlib only, no network, third-party safe. From meta bro root:
    python backend/par_cli.py path/to/par.json
    python backend/par_cli.py anchor <ledger.jsonl>
    python backend/par_cli.py verify <ledger.jsonl> [--anchor <file>]
Exit 0 + summary lines when the input verifies; exit 2 + reason when
it does not. Any machine with Python, zero vendor contact.
Store anchor files OUT-OF-BAND (separate repo, email, printout):
an anchor next to its chain detects accidents, not attackers.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))), "packages"))

from engine import canonical_str  # noqa: E402
from engine.ledger import LedgerError
from engine.ledger import anchor as make_anchor  # noqa: E402
from engine.ledger import loads as loads_chain
from engine.ledger import verify as verify_chain
from engine.par import read_par  # noqa: E402


def _usage() -> int:
    print("usage:")
    print("  python backend/par_cli.py path/to/par.json")
    print("  python backend/par_cli.py anchor <ledger.jsonl>")
    print("  python backend/par_cli.py verify <ledger.jsonl> "
          "[--anchor <file>]")
    return 2


def _load_chain(path: str):
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        return None, f"cannot read ledger file: {exc}"
    try:
        return loads_chain(text), ""
    except LedgerError as exc:
        return None, f"ledger unparsable: {exc}"


def _cmd_anchor(ledger_path: str) -> int:
    chain, error = _load_chain(ledger_path)
    if chain is None:
        print(error)
        return 2
    try:
        pack = make_anchor(chain)
    except LedgerError as exc:
        print(f"cannot anchor: {exc}")
        return 2
    out_path = ledger_path + ".anchor.json"
    try:
        with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_str(pack) + "\n")
    except OSError as exc:
        print(f"cannot write anchor file: {exc}")
        return 2
    print(f"anchor written: {out_path}")
    print(canonical_str(pack))
    print("store this file OUT-OF-BAND (separate repo, email, printout)")
    return 0


def _cmd_verify(ledger_path: str, anchor_path) -> int:
    chain, error = _load_chain(ledger_path)
    if chain is None:
        print(error)
        return 2
    pack = None
    if anchor_path is not None:
        try:
            with open(anchor_path, encoding="utf-8") as handle:
                pack = json.load(handle)
        except (OSError, ValueError) as exc:
            print(f"cannot read anchor file: {exc}")
            return 2
    result = verify_chain(chain, anchor=pack)
    if not result["ok"]:
        print(f"LEDGER INVALID: {result['reason']}")
        return 2
    suffix = " (anchor matched)" if pack is not None else ""
    print(f"LEDGER OK ({result['entries']} entries{suffix})")
    return 0


def main(argv) -> int:
    if len(argv) >= 2 and argv[1] == "anchor":
        if len(argv) != 3:
            return _usage()
        return _cmd_anchor(argv[2])
    if len(argv) >= 2 and argv[1] == "verify":
        if len(argv) not in (3, 5) or (len(argv) == 5
                                       and argv[3] != "--anchor"):
            return _usage()
        anchor_path = argv[4] if len(argv) == 5 else None
        return _cmd_verify(argv[2], anchor_path)
    if len(argv) != 2:
        return _usage()
    try:
        with open(argv[1], encoding="utf-8") as handle:
            envelope = json.load(handle)
    except (OSError, ValueError) as exc:
        print(f"cannot read PAR file: {exc}")
        return 2
    result = read_par(envelope)
    if not result["ok"]:
        print(f"PAR INVALID: {result['reason']}")
        return 2
    for line in result["lines"]:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
