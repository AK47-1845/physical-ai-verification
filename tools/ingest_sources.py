from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pypdf import PdfReader

PROJECT = Path(__file__).resolve().parents[1]


def ingest(source_directory: Path, output_directory: Path) -> list[dict]:
    sources = sorted(source_directory.glob("*.pdf"))
    if not sources:
        raise ValueError("No source PDFs found")
    output_directory.mkdir(parents=True, exist_ok=True)
    manifest = []
    for source in sources:
        with source.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        reader = PdfReader(source)
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
        slug = re.sub(r"[^a-z0-9]+", "-", source.stem.lower()).strip("-")
        destination = output_directory / f"{slug}.md"
        sections = [f"# {source.name}\n\nSHA256: {digest}\n"]
        for number, text in enumerate(pages, start=1):
            sections.append(f"## Page {number}\n\n{text or '[NO EXTRACTABLE TEXT: visual review required]'}\n")
        destination.write_text("\n".join(sections), encoding="utf-8")
        entry = {
            "source": source.name,
            "sha256": digest,
            "pages": len(pages),
            "characters": sum(map(len, pages)),
            "visual_review_pages": [number for number, text in enumerate(pages, 1) if len(text) < 40],
            "extracted_file": destination.relative_to(PROJECT).as_posix(),
            "extraction": "pypdf; text layer only; no OCR inference",
        }
        if len(pages) != len(reader.pages):
            raise AssertionError("Page count mismatch")
        manifest.append(entry)
    (output_directory.parent / "source-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    result = ingest(PROJECT.parent, PROJECT / "knowledge" / "source-text")
    print(json.dumps(result, indent=2, ensure_ascii=True))