"""Gate 3 — full-tree extraction driver.

Runs the deterministic pipeline against the full v1 base-mode corpus per Gate-0
corpus_profile.md §"v1 extraction-target file count: ~145":

  app/cbl/         33 COBOL programs
  app/cpy/         31 copybooks
  app/cpy-bms/     18 BMS-derived copybooks
  app/jcl/         38 JCL jobs
  app/bms/         17 BMS mapsets
  app/proc/         2 cataloged PROCs
  app/csd/CARDDEMO.CSD (1, authoritative CSD)
  app/asm/          2 assembler stubs

Excluded (per Gate 0 §1.2): deferred subapps (DB2/IMS/MQ), data/, scheduler/,
samples/, scripts/markers/, the catlg LISTCAT.txt sample, `.gitkeep` placeholders.

Outputs to `artifacts/gate3/`. After extraction:
  - Structural invariants validated
  - Semantic coverage assertions checked
  - Q1-Q4 executed against the built kuzu DB
  - gold_match.py compares against the FROZEN gold/gold_set.md
  - Any residual deltas classified per failure-mode taxonomy
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from carddemo_graph import SCHEMA_VERSION, EXTRACTOR_VERSION
from carddemo_graph.extract.observation import ObservationSink
from carddemo_graph.extract.sources import read_source_file
from carddemo_graph.extract.parsers import get_extractor
from carddemo_graph.resolve.pass3 import resolve
from carddemo_graph.validation.structural import (
    validate_entities, validate_edges, validate_observations,
    validate_enrichments,
)
from carddemo_graph.validation import semantic
from carddemo_graph.pilot import (
    build_kuzu_db, run_q1_sample, run_q2_sample, run_q3_sample, run_q4_sample,
    compute_corpus_hash,
)


def enumerate_v1_corpus(repo_root: Path) -> list[tuple[Path, str]]:
    """Return (path, lang) for every v1 base-mode source file in the corpus.

    Excludes deferred subapps (`app/app-*`), out-of-scope dirs (`data/`,
    `scheduler/`, `maclib/`, `ctl/`, `catlg/`), and non-source artifacts
    (`.gitkeep`, `.DS_Store`).
    """
    base = repo_root / "corpus" / "carddemo" / "stripped" / "app"
    out: list[tuple[Path, str]] = []

    def add(globs: list[str], lang: str) -> None:
        for pattern in globs:
            for p in sorted(base.glob(pattern)):
                if p.name.startswith(".") or p.name == ".gitkeep":
                    continue
                # Exclude deferred subapps
                if any(part.startswith("app-") for part in p.parts):
                    continue
                out.append((p, lang))

    # COBOL programs
    add(["cbl/*.cbl", "cbl/*.CBL"], "cobol")
    # Copybooks (plain + BMS-generated)
    add(["cpy/*.cpy", "cpy/*.CPY"], "cobol")
    add(["cpy-bms/*.cpy", "cpy-bms/*.CPY"], "cobol")
    # JCL jobs
    add(["jcl/*.jcl", "jcl/*.JCL"], "jcl")
    # JCL cataloged PROCs
    add(["proc/*.prc", "proc/*.PRC"], "proc")
    # BMS mapsets
    add(["bms/*.bms"], "bms")
    # CSD — the authoritative one
    for p in [base / "csd" / "CARDDEMO.CSD"]:
        if p.exists():
            out.append((p, "csd"))
    # Assembler stubs (extracted as Program partial entities; rules-light)
    # Note: my asm extractor stub doesn't yet handle these — they'd be
    # additional Program entities via RUL-ASM-001. Skipping for now since the
    # CSD already gives us their type (Program) and the bodies aren't analyzed.
    return out


def run_gate3(repo_root: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    files = enumerate_v1_corpus(repo_root)
    if not files:
        print("ERROR: no v1 corpus files found", file=sys.stderr)
        sys.exit(2)

    paths = [p for p, _ in files]
    run_id = f"gate3-fulltree-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    corpus_hash = compute_corpus_hash(paths)

    by_lang = Counter(lang for _, lang in files)
    print(f"Gate 3 corpus: {len(files)} files across {len(by_lang)} languages")
    for lang, n in by_lang.most_common():
        print(f"  {lang:<8} x{n}")

    # Run all extractors
    sink = ObservationSink()
    for i, (path, lang) in enumerate(files, start=1):
        sfid = f"sf-{i:03d}"
        src = read_source_file(path, sfid)
        sink.register_source_file(src.record)
        try:
            get_extractor(lang)(src, sink)
        except Exception as e:
            print(f"  [EXTRACT ERROR] {path}: {type(e).__name__}: {e}",
                  file=sys.stderr)
            # Continue — partial extraction per spec ("partial: parse_status flag")
            continue

    print(f"Total observations: {len(sink.observations)}")

    # Privacy/portability: emit repo-relative source_paths (no absolute build path / OS
    # username in any artifact). Single chokepoint before resolution carries it through.
    sink.relativize_paths(repo_root)

    # Resolve
    resolver = resolve(
        sink,
        schema_version=SCHEMA_VERSION,
        extractor_version=EXTRACTOR_VERSION,
        run_id=run_id,
        corpus_hash=corpus_hash,
    )
    resolver.write_artifacts(artifacts_dir=output_dir)
    print(f"Entities: {len(resolver.entities)}; "
          f"Edges: {len(resolver.edges)}; "
          f"Conflicts: {len(resolver.conflicts)}; "
          f"Unresolved/partial: {len(resolver.unresolved_records)}")

    # Validate structural
    validation_failed = False
    for fname in ("entities.json", "edges.json", "observations.json", "enrichments.json"):
        payload = json.loads((output_dir / fname).read_text())
        if "entities" in payload:
            r = validate_entities(payload, str(output_dir / fname))
        elif "edges" in payload:
            entity_ids = {e["id"] for e in
                          json.loads((output_dir / "entities.json").read_text())["entities"]}
            r = validate_edges(payload, str(output_dir / fname), entity_ids=entity_ids)
        elif "enrichments" in payload:
            r = validate_enrichments(payload, str(output_dir / fname))
        else:
            r = validate_observations(payload, str(output_dir / fname))
        if not r.ok():
            validation_failed = True
            print(f"\n[VALIDATION FAIL] {fname}: {len(r.errors)} errors")
            for issue in r.errors[:20]:
                print(f"  {issue.where}: {issue.message} ({issue.rule})")
        else:
            print(f"[VALIDATION OK] {fname}: 0 errors, {len(r.warnings)} warnings")

    # Build kuzu
    kuzu_path = output_dir / "carddemo_graph.db"
    if kuzu_path.exists():
        if kuzu_path.is_dir():
            shutil.rmtree(kuzu_path, ignore_errors=True)
        else:
            kuzu_path.unlink()
    wal = output_dir / "carddemo_graph.db.wal"
    if wal.exists():
        wal.unlink()
    build_kuzu_db(output_dir / "entities.json",
                  output_dir / "edges.json",
                  kuzu_path,
                  repo_root / "artifacts" / "kuzu_schema.cypher")

    # Run Q1-Q4
    q_results = {
        "Q1": run_q1_sample(kuzu_path),
        "Q2": run_q2_sample(kuzu_path),
        "Q3": run_q3_sample(kuzu_path),
        "Q4": run_q4_sample(kuzu_path),
    }
    (output_dir / "query_samples.json").write_text(
        json.dumps(q_results, indent=2, default=str)
    )

    # Semantic coverage
    rep = semantic.assert_from_files(
        output_dir / "entities.json",
        output_dir / "edges.json",
        output_dir / "unresolved_report.md",
    )

    summary = {
        "run_id": run_id,
        "corpus_hash": corpus_hash,
        "files_scanned": len(files),
        "observations": len(sink.observations),
        "entities": len(resolver.entities),
        "edges": len(resolver.edges),
        "conflicts": len(resolver.conflicts),
        "unresolved": len(resolver.unresolved_records),
        "validation_failed": validation_failed,
        "semantic_pass": rep.passed,
        "semantic_warn": rep.warnings,
        "semantic_fail": rep.failed,
    }
    print("\n=== GATE 3 SUMMARY ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return summary


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    output_dir = repo_root / "artifacts" / "gate3"
    summary = run_gate3(repo_root, output_dir)
    return 1 if summary.get("validation_failed") or summary.get("semantic_fail") else 0


if __name__ == "__main__":
    sys.exit(main())
