"""FR-20 regulation-row mapping: dossier rows -> draft mappings.

Honesty law: this table carries NO clause text and NO conformity
claims. Every row has a static mapping status (DRAFT_MAPPING /
REFERENCE_MAPPING / UNDER_DEVELOPMENT) + a gap note, and map_rows()
derives an evidence status from linked gate verdicts. The best
evidence status is EVIDENCE_PRESENT: evidence exists and is linked.
It is never a pass, a finding, or a conformity claim.
"""

from engine import InputError

BANNER = ("DRAFT MAPPING - HUMAN AND LEGAL REVIEW REQUIRED: row links "
          "are engineering cross-references, not conformity findings.")


class RegmapError(InputError):
    """Itemized validation failure. Server formats these, never traces."""


_VERDICTS = ("PASS", "REVIEW", "BLOCKED", "INSUFFICIENT")
_DELTAS = ("IN-ODD", "SUBSTANTIAL_MODIFICATION_CANDIDATE", "UNASSESSED")

ROWS = (
    {"id": "MR-ANNEX-IV", "framework": "EU Machinery Regulation 2023/1230",
     "topic": "Technical file shape (Annex IV)",
     "mapping": "DRAFT_MAPPING", "applies": "2027-01-20",
     "route": "PRIMARY",
     "gates": ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9",
               "G10", "G11"),
     "gap": "Product applicability + assessor acceptance need review."},
    {"id": "MR-PART-A", "framework": "EU Machinery Regulation 2023/1230",
     "topic": "Annex I Part A: ML safety-component route reference",
     "mapping": "DRAFT_MAPPING", "applies": "2027-01-20",
     "route": "PRIMARY",
     "gates": (),
     "gap": "Item numbering (5/6) UNVERIFIED-CLAUSE: check the OJ text. "
            "Third-party assessment route needs legal review."},
    {"id": "MR-SUBSTANTIAL", "framework": "EU Machinery Regulation 2023/1230",
     "topic": "OTA / substantial-modification reference",
     "mapping": "DRAFT_MAPPING", "applies": "2027-01-20",
     "route": "PRIMARY",
     "gates": (), "release": True,
     "gap": "Route (Part A 5/6 UNVERIFIED-CLAUSE vs modification) "
            "needs legal review."},
    {"id": "MR-EHSR-CTRL", "framework": "EU Machinery Regulation 2023/1230",
     "topic": "Control-system behaviour bounds reference",
     "mapping": "DRAFT_MAPPING", "applies": "2027-01-20",
     "route": "PRIMARY",
     "gates": ("G3", "G5"),
     "gap": "Clause-level mapping needs legal review."},
    {"id": "AI-ART-10", "framework": "EU AI Act 2024/1689",
     "topic": "Data governance reference mapping",
     "mapping": "REFERENCE_MAPPING", "applies": None,
     "route": "SECONDARY",
     "gates": ("G7",),
     "gap": "Expected to fold into Machinery Reg (Omnibus); interim ref."},
    {"id": "AI-ART-12", "framework": "EU AI Act 2024/1689",
     "topic": "Record-keeping reference mapping",
     "mapping": "REFERENCE_MAPPING", "applies": None,
     "route": "SECONDARY",
     "gates": (),
     "gap": "Fed by ledger excerpts, not gates (wiring open)."},
    {"id": "AI-ART-14", "framework": "EU AI Act 2024/1689",
     "topic": "Human oversight reference mapping",
     "mapping": "REFERENCE_MAPPING", "applies": None,
     "route": "SECONDARY",
     "gates": ("G5",),
     "gap": "Workflow evidence supports, never satisfies, obligations."},
    {"id": "AI-ART-15", "framework": "EU AI Act 2024/1689",
     "topic": "Robustness reference mapping",
     "mapping": "REFERENCE_MAPPING", "applies": None,
     "route": "SECONDARY",
     "gates": ("G1", "G4"),
     "gap": "Expected to fold into Machinery Reg (Omnibus); interim ref."},
    {"id": "ISO-10218-535", "framework": "ISO 10218-1:2025",
     "topic": "Software-update control checklist reference",
     "mapping": "DRAFT_MAPPING", "applies": None,
     "gates": (), "release": True,
     "gap": "UNVERIFIED-CLAUSE: use licensed standard text + "
            "qualified assessor."},
    {"id": "ISO-25785-1", "framework": "ISO/CD 25785-1 (draft)",
     "topic": "Dynamic balancing / humanoid safety placeholder",
     "mapping": "UNDER_DEVELOPMENT", "applies": None,
     "gates": ("G11",),
     "gap": "Standard unpublished: no clause text, no claims, ever."},
)


def _derive(scored: list) -> str:
    if "BLOCKED" in scored:
        return "BLOCKED"
    if "REVIEW" in scored or "INSUFFICIENT" in scored:
        return "REVIEW"
    return "EVIDENCE_PRESENT"


def _release_evidence(delta) -> str:
    if delta == "SUBSTANTIAL_MODIFICATION_CANDIDATE":
        return "REVIEW"
    if delta == "IN-ODD":
        return "EVIDENCE_PRESENT"
    return "UNLINKED"


def map_rows(gate_verdicts: dict, *, release_delta=None) -> dict:
    """Map gate verdicts onto regulation rows. Banner always attached."""
    if not isinstance(gate_verdicts, dict):
        raise RegmapError("gate_verdicts: {gate_id: verdict} dict required")
    for gid, verdict in gate_verdicts.items():
        if not isinstance(gid, str) or not gid:
            raise RegmapError(f"gate id must be a non-empty string: "
                              f"{gid!r}")
        if verdict not in _VERDICTS:
            raise RegmapError(f"gate {gid!r}: bad verdict {verdict!r}")
    if release_delta is not None and release_delta not in _DELTAS:
        raise RegmapError(f"release_delta: one of {_DELTAS} or None")
    rows = []
    for row in ROWS:
        linked = [g for g in row["gates"] if g in gate_verdicts]
        unscored = [g for g in row["gates"] if g not in gate_verdicts]
        if row.get("release"):
            evidence = _release_evidence(release_delta)
        elif not linked:
            evidence = "UNLINKED"
        else:
            evidence = _derive([gate_verdicts[g] for g in linked])
        rows.append({"id": row["id"], "framework": row["framework"],
                     "topic": row["topic"], "mapping": row["mapping"],
                     "applies": row["applies"], "route": row.get("route"),
                     "evidence": evidence,
                     "linked_gates": linked, "unscored": unscored,
                     "gap": row["gap"]})
    return {"banner": BANNER, "rows": rows}
