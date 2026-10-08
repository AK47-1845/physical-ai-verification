from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from graphify.analyze import god_nodes, suggest_questions, surprising_connections
from graphify.build import build_from_json
from graphify.cache import save_semantic_cache
from graphify.cli import _stamped_manifest_files
from graphify.cluster import cluster, score_all
from graphify.detect import detect, save_manifest
from graphify.diagnostics import diagnose_extraction, format_diagnostic_report
from graphify.export import to_html, to_json
from graphify.extract import extract
from graphify.report import generate

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "graphify-out"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    detection = detect(ROOT)
    if detection["total_files"] > 500 or detection["total_words"] > 2_000_000:
        raise SystemExit("Corpus exceeds review budget; narrow the source scope before rebuilding")
    write_json(OUTPUT / ".graphify_detect.json", detection)
    semantic = {"nodes": [], "edges": [], "hyperedges": []}
    chunks = sorted(OUTPUT.glob(".graphify_chunk_*.json"))
    if not chunks:
        raise SystemExit("Semantic source fragments are missing; do not replace the graph with AST-only content")
    for path in chunks:
        fragment = json.loads(path.read_text(encoding="utf-8"))
        for key in semantic:
            semantic[key].extend(fragment.get(key, []))
    semantic_path = ROOT / "knowledge" / "semantic-sources.json"
    write_json(semantic_path, semantic)
    specification = Path.home() / ".claude" / "skills" / "graphify" / "references" / "extraction-spec.md"
    if specification.exists():
        save_semantic_cache(semantic["nodes"], semantic["edges"], semantic["hyperedges"], root=str(ROOT),
                            allowed_source_files=sorted({node["source_file"] for node in semantic["nodes"]}),
                            prompt_file=str(specification))
    ast = extract([Path(path) for path in detection["files"].get("code", [])], cache_root=ROOT, parallel=False)
    nodes = {node["id"]: node for node in ast["nodes"] + semantic["nodes"]}
    edges = {}
    for edge in ast["edges"] + semantic["edges"]:
        if edge["target"] not in nodes:
            nodes[edge["target"]] = {
                "id": edge["target"], "label": f"Referenced symbol: {edge['target']}",
                "file_type": "concept", "source_file": edge.get("source_file"),
                "source_location": edge.get("source_location"),
                "definition_status": "Referenced by source; definition not resolved in this corpus",
            }
        key = (edge["source"], edge["target"])
        if key not in edges:
            edges[key] = {**edge, "relations": [edge.get("relation", "related")], "evidence_locations": []}
        stored = edges[key]
        relation = edge.get("relation", "related")
        if relation not in stored["relations"]:
            stored["relations"].append(relation)
        location = {"source_file": edge.get("source_file"), "source_location": edge.get("source_location"),
                    "relation": relation, "confidence": edge.get("confidence")}
        if location not in stored["evidence_locations"]:
            stored["evidence_locations"].append(location)
    extraction = {"nodes": list(nodes.values()), "edges": list(edges.values()), "hyperedges": semantic["hyperedges"],
                  "input_tokens": 0, "output_tokens": 0, "token_accounting": "unavailable from host; zero placeholders are not measured usage"}
    diagnostic = diagnose_extraction(extraction, directed=True, root=str(ROOT))
    print(format_diagnostic_report(diagnostic))
    if diagnostic.get("dangling_endpoint_edges") or diagnostic.get("missing_endpoint_edges"):
        raise SystemExit("Graph contains dangling endpoints; preserve the last good graph and repair the fragments")
    graph = build_from_json(extraction, root=str(ROOT), directed=True)
    if not graph.number_of_nodes():
        raise SystemExit("Empty graph; refusing to replace existing evidence")
    communities = cluster(graph)
    cohesion = score_all(graph, communities)
    labels = {}
    for community, members in communities.items():
        counts = Counter()
        for member in members:
            source = str(graph.nodes[member].get("source_file", "")).replace("\\", "/")
            if "scrollcraft" in source:
                counts["Design And Verification"] += 1
            elif "source-text" in source:
                counts["Physical AI Research"] += 1
            elif "original-mvp" in source:
                counts["Original MVP Evidence"] += 1
            elif "tests/" in source:
                counts["Verification Contracts"] += 1
            elif "web/" in source:
                counts["Operations Interface"] += 1
            else:
                counts["Governance Implementation"] += 1
        labels[community] = counts.most_common(1)[0][0]
    gods = god_nodes(graph)
    surprises = surprising_connections(graph, communities)
    questions = suggest_questions(graph, communities, labels)
    if not to_json(graph, communities, str(OUTPUT / "graph.json"), community_labels=labels):
        raise SystemExit("Graph shrink guard refused this update; inspect differences before explicitly rebuilding")
    report = generate(graph, communities, cohesion, labels, gods, surprises, detection,
                      {"input": 0, "output": 0}, str(ROOT), suggested_questions=questions)
    report += "\n## Accounting And Coverage\n\nHost token usage was not exposed; zero token fields are placeholders, not measured cost.\n"
    report += "Semantic extraction covers the 34 original document/image inputs. PDF text preserves page boundaries; not all diagrams have been visually reviewed.\n"
    report += "Parallel relationships retain their distinct relation names and evidence locations on one directed edge.\n"
    report += "Referenced-symbol nodes preserve explicit code references whose definitions are outside the scanned corpus; their implementations were not inspected.\n"
    report += "New code is AST-extracted. Newly added prose needs a reviewed semantic fragment before it can claim full semantic coverage.\n"
    (OUTPUT / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
    if graph.number_of_nodes() > 5000:
        raise SystemExit("Graph exceeds 5000 nodes; confirm an aggregated visualization before exporting")
    to_html(graph, communities, str(OUTPUT / "graph.html"), community_labels=labels)
    write_json(OUTPUT / ".graphify_analysis.json", {"communities": communities, "cohesion": cohesion,
                                                    "labels": labels, "gods": gods, "surprises": surprises})
    write_json(OUTPUT / ".graphify_extract.json", extraction)
    corpus = detection["files"]
    stamped = _stamped_manifest_files(corpus, extraction, ROOT)
    save_manifest(stamped, root=str(ROOT), scan_corpus={name for files in corpus.values() for name in files})
    write_json(OUTPUT / "build-receipt.json", {"built_at": datetime.now(timezone.utc).isoformat(),
               "nodes": graph.number_of_nodes(), "edges": graph.number_of_edges(), "communities": len(communities),
               "semantic_fragments": len(chunks), "diagnostic": diagnostic, "token_usage": None})
    (OUTPUT / ".graphify_python").write_text(sys.executable, encoding="utf-8")
    (OUTPUT / ".graphify_root").write_text(str(ROOT), encoding="utf-8")
    print(f"Graph built: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges, {len(communities)} communities")


if __name__ == "__main__":
    main()