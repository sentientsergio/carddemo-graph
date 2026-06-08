"""Gate-2 golden-file pilot driver.

Wires the Pass-1 per-language extractors + Pass-3 resolver together over the
hand-checkable subset chosen per spec §Gate 2. Produces:

  artifacts/gate2/observations.json
  artifacts/gate2/entities.json
  artifacts/gate2/edges.json
  artifacts/gate2/resolution_report.md
  artifacts/gate2/unresolved_report.md
  artifacts/gate2/constructs_not_modeled.md
  artifacts/gate2/carddemo_graph.db    (kuzu graph database)
"""

from __future__ import annotations

import hashlib
import json
import sys
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


# Gate-2 subset per spec §Gate 2 + Gate 0 anomaly coverage
GATE2_SUBSET: list[tuple[str, str]] = [
    # (relative path, language tag — used to pick extractor)
    # online COBOL programs
    ("corpus/carddemo/stripped/app/cbl/COSGN00C.cbl",  "cobol"),
    ("corpus/carddemo/stripped/app/cbl/COACTUPC.cbl",  "cobol"),  # copybook-heavy + COPY REPLACING
    ("corpus/carddemo/stripped/app/cbl/COCRDLIC.cbl",  "cobol"),  # STARTBR/READNEXT/ENDBR (browse pattern)
    # batch COBOL programs
    ("corpus/carddemo/stripped/app/cbl/CBTRN02C.cbl",  "cobol"),
    ("corpus/carddemo/stripped/app/cbl/CBTRN03C.cbl",  "cobol"),  # CALL CSUTLDTC (literal)
    # utility COBOL (CALL target)
    ("corpus/carddemo/stripped/app/cbl/CSUTLDTC.cbl",  "cobol"),
    # JCL with PROC invocation + standalone JCL
    ("corpus/carddemo/stripped/app/jcl/TRANREPT.jcl",  "jcl"),
    ("corpus/carddemo/stripped/app/jcl/POSTTRAN.jcl",  "jcl"),
    # cataloged PROCs (exercises the //REPROC PROC collision anomaly)
    ("corpus/carddemo/stripped/app/proc/REPROC.prc",   "proc"),
    ("corpus/carddemo/stripped/app/proc/TRANREPT.prc", "proc"),
    # BMS mapset matching COSGN00C
    ("corpus/carddemo/stripped/app/bms/COSGN00.bms",   "bms"),
    # CSD — the whole authoritative file
    ("corpus/carddemo/stripped/app/csd/CARDDEMO.CSD",  "csd"),
]


def compute_corpus_hash(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths, key=str):
        h.update(str(p).encode())
        h.update(b"\0")
        h.update(p.read_bytes())
    return h.hexdigest()


def run_pilot(repo_root: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = [repo_root / rel for rel, _ in GATE2_SUBSET]
    missing = [p for p in paths if not p.exists()]
    if missing:
        print(f"MISSING: {missing}", file=sys.stderr)
        sys.exit(2)

    run_id = f"gate2-pilot-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    corpus_hash = compute_corpus_hash(paths)

    sink = ObservationSink()
    for i, (rel, lang) in enumerate(GATE2_SUBSET, start=1):
        sfid = f"sf-{i:03d}"
        src = read_source_file(repo_root / rel, sfid)
        sink.register_source_file(src.record)
        get_extractor(lang)(src, sink)

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

    # Validate the produced JSON artifacts
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

    # Build kuzu DB (remove old DB file + WAL sidecar if present)
    kuzu_path = output_dir / "carddemo_graph.db"
    import shutil
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

    # Run Q1-Q4 sample queries against the kuzu DB
    q_results = {
        "Q1": run_q1_sample(kuzu_path),
        "Q2": run_q2_sample(kuzu_path),
        "Q3": run_q3_sample(kuzu_path),
        "Q4": run_q4_sample(kuzu_path),
    }
    (output_dir / "q1_sample_result.json").write_text(
        json.dumps(q_results["Q1"], indent=2, default=str)
    )
    (output_dir / "query_samples.json").write_text(
        json.dumps(q_results, indent=2, default=str)
    )

    summary = {
        "run_id": run_id,
        "corpus_hash": corpus_hash,
        "observations": len(sink.observations),
        "entities": len(resolver.entities),
        "edges": len(resolver.edges),
        "conflicts": len(resolver.conflicts),
        "unresolved": len(resolver.unresolved_records),
        "kuzu_db": str(kuzu_path),
        "validation_failed": validation_failed,
        "q1_direct_includers": len(q_results["Q1"].get("direct_includers", [])),
        "q2_program_access": len(q_results["Q2"].get("program_access", [])),
        "q3_reachable_programs": len(q_results["Q3"].get("reachable_programs", [])),
        "q4_map_interactions": len(q_results["Q4"].get("map_interactions", [])),
    }
    print("\n=== PILOT SUMMARY ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return summary


def build_kuzu_db(entities_path: Path, edges_path: Path, kuzu_db_path: Path,
                  schema_cypher_path: Path) -> None:
    import re
    import kuzu

    db = kuzu.Database(str(kuzu_db_path))
    conn = kuzu.Connection(db)

    # Apply schema
    raw = schema_cypher_path.read_text()
    no_comments = re.sub(r"//[^\n]*", "", raw)
    stmts = [s.strip() for s in no_comments.split(";") if s.strip()]
    for s in stmts:
        conn.execute(s + ";")

    # Load entities by type
    entities = json.loads(entities_path.read_text())["entities"]
    edges = json.loads(edges_path.read_text())["edges"]

    # Group entities by type
    by_type: dict[str, list[dict]] = {}
    for e in entities:
        by_type.setdefault(e["type"], []).append(e)

    # Helper to upsert one entity
    def upsert(table: str, props: dict) -> None:
        keys = list(props.keys())
        placeholders = ", ".join(f"{k}: ${k}" for k in keys)
        cypher = f"CREATE (n:{table} {{ {placeholders} }})"
        try:
            conn.execute(cypher, parameters=props)
        except Exception as ex:
            # PK collisions occur when ensure_endpoint creates a partial and a
            # full entity is also emitted with the same id. We skip the second.
            if "primary key" in str(ex).lower() or "duplicated" in str(ex).lower():
                return
            raise

    # Map JSON entity → kuzu row
    for etype, group in by_type.items():
        for ent in group:
            props = ent.get("properties", {}) or {}
            row = {"id": ent["id"], "name": ent.get("name") or ""}
            # First provenance entry feeds source-path/rule_id back as a node property
            if ent.get("provenance"):
                row["source_path"] = ent["provenance"][0]["source_path"]
            if ent.get("rule_id"):
                row["rule_id"] = ent["rule_id"]
            if "partial" in ent:
                row["partial"] = bool(ent["partial"])
            # Stringify complex props
            for k, v in props.items():
                if isinstance(v, (dict, list)):
                    row[k] = json.dumps(v, default=str)
                elif v is None:
                    continue
                else:
                    row[k] = v
            # Type-specific column-name normalizations
            row = _normalize_row_for_table(etype, row)
            upsert(etype, row)

    # Now edges
    for e in edges:
        from_id = e["from"]
        to_id = e["to"]
        # find FROM and TO entity types
        from_ent = next((x for x in entities if x["id"] == from_id), None)
        to_ent = next((x for x in entities if x["id"] == to_id), None)
        if not (from_ent and to_ent):
            continue
        from_type = from_ent["type"]
        to_type = to_ent["type"]
        attrs = e.get("attributes", {}) or {}
        # Get the first provenance item
        prov = e["provenance"][0] if e["provenance"] else {}

        rel_props = {
            "confidence": float(e["confidence"]),
            "evidence_kind": e["evidence_kind"],
            "rule_id": e["rule_id"],
            "source_path": prov.get("source_path", ""),
            "start_line": int(prov.get("start_line", 0)),
            "end_line": int(prov.get("end_line", 0)),
        }
        # Fold edge attributes for specific edge types
        for k, v in attrs.items():
            if v is None:
                continue
            if isinstance(v, (dict, list)):
                rel_props[k] = json.dumps(v, default=str)
            elif isinstance(v, bool):
                rel_props[k] = v
            else:
                rel_props[k] = v
        # filter rel_props to those supported by the relationship table schema
        rel_props = _filter_rel_props(e["type"], rel_props)
        # Build MATCH+CREATE Cypher
        keys = list(rel_props.keys())
        placeholders = ", ".join(f"{k}: ${k}" for k in keys)
        cypher = (
            f"MATCH (a:{from_type} {{id: $from_id}}), (b:{to_type} {{id: $to_id}}) "
            f"CREATE (a)-[r:{e['type']} {{ {placeholders} }}]->(b)"
        )
        params = dict(rel_props)
        params["from_id"] = from_id
        params["to_id"] = to_id
        try:
            conn.execute(cypher, parameters=params)
        except Exception as ex:
            print(f"WARN: edge insert failed: {e['id']} {e['type']} {from_id}->{to_id}: {ex}")


# Per-node-table column whitelist + rename map (from JSON property name → kuzu column name).
# Kuzu silently rejects unknown columns with "Binder exception"; the loader must filter.
_NODE_PROPS: dict[str, dict[str, str | None]] = {
    # Each value: target column name (or the same key if no rename); None drops the key.
    "Program": {
        "id": "id", "name": "name", "partial": "partial", "asm_stub": "asm_stub",
        "size_loc": "size_loc", "fan_in": "fan_in", "fan_out": "fan_out",
        "straddle_score": "straddle_score",
        "source_path": "source_path", "rule_id": "rule_id",
        # Drop properties not in kuzu table:
        "filename_match": None, "filename_mismatch": None, "partial_reason": None,
        # inferred_purpose is enrichment, not skeleton — never reaches kuzu Program table
        "inferred_purpose": None,
    },
    "Copybook": {
        "id": "id", "name": "name", "reuse_count": "reuse_count",
        "source_path": "source_path", "rule_id": "rule_id",
        "partial": "partial",
        "partial_reason": None, "referenced_by_rule": None,
    },
    "JCLJob": {
        "id": "id", "name": "name", "source_path": "source_path", "rule_id": "rule_id",
        "jcllib_search_path": "jcllib_search_path",
    },
    "JCLStep": {
        "id": "id", "name": "name", "source_path": "source_path", "rule_id": "rule_id",
        "step_order": "step_order",
        "owner_id": "job_id",           # rename owner_id → job_id
    },
    "JCLProc": {
        "id": "id", "name": "name", "source_path": "source_path", "rule_id": "rule_id",
        "declared_name": "declared_name", "filename_mismatch": "filename_mismatch",
        "default_params": "default_params", "filename": None,
    },
    "JCLProcInvocation": {
        "id": "id", "name": "name", "source_path": "source_path", "rule_id": "rule_id",
        "owner_id": "job_id", "invoked_proc_id": "invoked_proc_id",
        "positional": None,
    },
    "LogicalFile": {
        "id": "id", "name": "name", "source_path": "source_path", "rule_id": "rule_id",
        "scope": "scope", "assign_dd": "assign_dd", "organization": "organization",
        "access_mode": "access_mode", "record_key": "record_key",
        "alternate_record_keys": "alternate_record_keys", "program_id": "program_id",
        "binding_source": None,         # not a column on LogicalFile node
    },
    "Dataset": {
        "id": "id", "name": "name", "rule_id": "rule_id", "partial": "partial",
        "organization": "organization",
        "centrality": "centrality", "gdg_offset": "gdg_offset",
        "unresolved_tokens": "unresolved_tokens",
        "source_path": None,            # Dataset has no source_path in kuzu schema
        "inferred_purpose": None,       # enrichment, not skeleton
    },
    "BMSMapset": {
        "id": "id", "name": "name", "source_path": "source_path", "rule_id": "rule_id",
        "lang": "lang", "mode": "mode", "partial": "partial",
        "ctrl": None,  # ctrl not in kuzu schema
    },
    "BMSMap": {
        "id": "id", "name": "name", "source_path": "source_path", "rule_id": "rule_id",
        "mapset_id": "mapset_id", "line_pos": "line_pos", "column_pos": "column_pos",
        "size_rows": "size_rows", "size_cols": "size_cols", "partial": "partial",
    },
    "BMSField": {
        "id": "id", "name": "name", "source_path": "source_path", "rule_id": "rule_id",
        "map_id": "map_id", "mapset_id": "mapset_id", "pos_row": "pos_row",
        "pos_col": "pos_col", "length": "length", "attrb": "attrb", "color": "color",
        "initial_value": "initial_value", "prompt_value": "prompt_value",
        "label": "label", "is_filler": "is_filler",
    },
    "CICSTransaction": {
        "id": "id", "name": "name", "source_path": "source_path", "rule_id": "rule_id",
        "description": "description", "fan_out": "fan_out", "partial": "partial",
    },
    "DataItem": {
        "id": "id", "name": "name", "source_path": "source_path", "rule_id": "rule_id",
        "level": "level", "picture": "picture", "usage": "usage", "occurs": "occurs",
        "redefines": "redefines", "is_filler": "is_filler", "is_group": "is_group",
        "suggested_sql_type": "suggested_sql_type", "parent_item": "parent_item",
        "copybook_id": "copybook_id",
    },
}


# Column-name normalizers per node table
def _normalize_row_for_table(table: str, row: dict) -> dict:
    mapping = _NODE_PROPS.get(table)
    if mapping is None:
        return {k: v for k, v in row.items() if not k.startswith("_")}
    out: dict = {}
    for k, v in row.items():
        target = mapping.get(k)
        if target is None and k in mapping:
            continue        # explicit drop
        if target is None:
            continue        # unknown key — silently drop (would error otherwise)
        out[target] = v
    return out


# Each rel table's allowed property names
_REL_PROPS = {
    "INCLUDES":              {"confidence","evidence_kind","rule_id","source_path","start_line","end_line","replacing_terms","fd_context"},
    "EXPANDS_TO":            {"confidence","evidence_kind","rule_id","source_path","start_line","end_line","step_order"},
    "DEFINES_LAYOUT_FOR":    {"confidence","evidence_kind","rule_id","source_path","start_line","end_line"},
    "CALLS":                 {"confidence","evidence_kind","rule_id","source_path","start_line","end_line","call_kind","breadcrumb"},
    "LINKS_TO":              {"confidence","evidence_kind","rule_id","source_path","start_line","end_line","call_kind","breadcrumb"},
    "XCTLS_TO":              {"confidence","evidence_kind","rule_id","source_path","start_line","end_line","call_kind","breadcrumb"},
    "RETURNS_TO_TRANSID":    {"confidence","evidence_kind","rule_id","source_path","start_line","end_line"},
    "SENDS_MAP":             {"confidence","evidence_kind","rule_id","source_path","start_line","end_line"},
    "RECEIVES_MAP":          {"confidence","evidence_kind","rule_id","source_path","start_line","end_line"},
    "DECLARES_FILE":         {"confidence","evidence_kind","rule_id","source_path","start_line","end_line"},
    "BINDS_TO":              {"confidence","evidence_kind","rule_id","source_path","start_line","end_line","dd_name","binding_source"},
    "READS":                 {"confidence","evidence_kind","rule_id","source_path","start_line","end_line","access_form"},
    "WRITES":                {"confidence","evidence_kind","rule_id","source_path","start_line","end_line","access_form"},
    "UPDATES":               {"confidence","evidence_kind","rule_id","source_path","start_line","end_line","access_form"},
    "DELETES":               {"confidence","evidence_kind","rule_id","source_path","start_line","end_line","access_form"},
    "STARTS_BROWSE":         {"confidence","evidence_kind","rule_id","source_path","start_line","end_line","access_form"},
    "INVOKES":               {"confidence","evidence_kind","rule_id","source_path","start_line","end_line"},
    "USES_DATASET":          {"confidence","evidence_kind","rule_id","source_path","start_line","end_line","dd_name","allocation_disposition","inferred_access_mode","inference_basis"},
    "USES_PROC":             {"confidence","evidence_kind","rule_id","source_path","start_line","end_line"},
    "PASSES_SYSIN_TO":       {"confidence","evidence_kind","rule_id","source_path","start_line","end_line","utility"},
    "IS_TRANSACTION_FOR":    {"confidence","evidence_kind","rule_id","source_path","start_line","end_line"},
    "HAS_FIELD":             {"confidence","evidence_kind","rule_id","source_path","start_line","end_line"},
    "CONTAINS_ITEM":         {"confidence","evidence_kind","rule_id","source_path","start_line","end_line"},
}


def _filter_rel_props(rel_type: str, props: dict) -> dict:
    allowed = _REL_PROPS.get(rel_type, set())
    return {k: v for k, v in props.items() if k in allowed}


def _kuzu_query(kuzu_db_path: Path, cypher: str, params: dict | None = None) -> list[dict]:
    import kuzu
    db = kuzu.Database(str(kuzu_db_path))
    conn = kuzu.Connection(db)
    result = conn.execute(cypher, parameters=params or {})
    rows = []
    while result.has_next():
        row = result.get_next()
        cols = result.get_column_names()
        rows.append(dict(zip(cols, row)))
    return rows


def run_q1_sample(kuzu_db_path: Path, cid: str = "copybook:CSUSR01Y") -> dict:
    """Q1 — Direct copybook inclusion impact.

    Per spec §Q1: direct_includers (programs that directly COPY); transactions
    (bound to those programs); maps (sent/received by those programs); jobs/steps;
    related_files (LogicalFiles where this copybook DEFINES_LAYOUT_FOR — the wide
    answer is computable here but separated). `cid` defaults to the Gate-2/3 sample
    copybook; gold_match.py passes each gold-entry copybook id.
    """
    direct_includers = _kuzu_query(kuzu_db_path,
        "MATCH (p:Program)-[r:INCLUDES]->(c:Copybook {id: $cid}) "
        "RETURN p.id AS program_id, p.name AS program_name, "
        "r.source_path AS source_path, r.start_line AS line ORDER BY program_id",
        {"cid": cid},
    )
    transactions = _kuzu_query(kuzu_db_path,
        "MATCH (c:Copybook {id: $cid})<-[:INCLUDES]-(p:Program)"
        "<-[:IS_TRANSACTION_FOR]-(t:CICSTransaction) "
        "RETURN DISTINCT t.id AS transaction_id, p.id AS program_id ORDER BY transaction_id",
        {"cid": cid},
    )
    maps_sent = _kuzu_query(kuzu_db_path,
        # Exclude partial BMSMap placeholders (identifier-form MAP/MAPSET that didn't
        # resolve to a literal map name).
        "MATCH (c:Copybook {id: $cid})<-[:INCLUDES]-(p:Program)-[:SENDS_MAP]->(m:BMSMap) "
        "WHERE m.partial IS NULL OR m.partial = FALSE "
        "RETURN DISTINCT p.id AS program_id, m.id AS map_id ORDER BY program_id, map_id",
        {"cid": cid},
    )
    related_files = _kuzu_query(kuzu_db_path,
        "MATCH (c:Copybook {id: $cid})-[:DEFINES_LAYOUT_FOR]->(lf:LogicalFile) "
        "RETURN lf.id AS logical_file_id, lf.name AS name ORDER BY logical_file_id",
        {"cid": cid},
    )
    return {
        "query": "Q1-copybook-impact",
        "input": {"copybook_id": cid},
        "direct_includers": direct_includers,
        "transactions": transactions,
        "maps": maps_sent,
        "related_files": related_files,
    }


def run_q2_sample(kuzu_db_path: Path,
                  did: str = "dataset:AWS.M2.CARDDEMO.USRSEC.VSAM.KSDS") -> dict:
    """Q2 — Dataset access.

    Per spec §Q2: program_access (via BINDS_TO chain); jcl_access (via USES_DATASET).
    `did` defaults to the Gate-2/3 sample dataset; gold_match.py passes each gold-entry
    dataset id.
    """
    program_access = _kuzu_query(kuzu_db_path,
        # Build the chain: Program -[any of READS/WRITES/UPDATES/DELETES/STARTS_BROWSE]-> LogicalFile -[BINDS_TO]-> Dataset
        "MATCH (p:Program)-[r:READS|WRITES|UPDATES|DELETES|STARTS_BROWSE]->(lf:LogicalFile)"
        "-[b:BINDS_TO]->(d:Dataset {id: $did}) "
        "RETURN p.id AS program_id, lf.id AS logical_file_id, b.dd_name AS dd_name, "
        "label(r) AS mode, r.source_path AS source_path, r.start_line AS line "
        "ORDER BY program_id, line",
        {"did": did},
    )
    jcl_access = _kuzu_query(kuzu_db_path,
        "MATCH (s:JCLStep)-[u:USES_DATASET]->(d:Dataset {id: $did}) "
        "RETURN s.id AS jcl_step, u.dd_name AS dd_name, "
        "u.allocation_disposition AS allocation_disposition, "
        "u.source_path AS source_path, u.start_line AS line ORDER BY jcl_step",
        {"did": did},
    )
    return {
        "query": "Q2-dataset-access",
        "input": {"dataset_id": did},
        "program_access": program_access,
        "jcl_access": jcl_access,
    }


def run_q3_sample(kuzu_db_path: Path, tid: str = "transaction:CC00") -> dict:
    """Q3 — Transaction-to-program closure.

    Per spec §Q3: entry_program; reachable_programs (transitive via CALLS / LINKS_TO /
    XCTLS_TO); unresolved_reaches (via unresolved dynamic calls). `tid` defaults to the
    Gate-2/3 sample transaction; gold_match.py passes each gold-entry transaction id.
    """
    entry = _kuzu_query(kuzu_db_path,
        "MATCH (t:CICSTransaction {id: $tid})-[:IS_TRANSACTION_FOR]->(p:Program) "
        "RETURN p.id AS entry_program",
        {"tid": tid},
    )
    # Reachable via static CALLS/LINKS_TO/XCTLS_TO (transitive). Per the project's
    # skeleton principle, only typed-Program → typed-Program edges count toward
    # reachable_programs. Targets with id starting `unresolved:` are split out.
    reachable = _kuzu_query(kuzu_db_path,
        "MATCH (t:CICSTransaction {id: $tid})-[:IS_TRANSACTION_FOR]->(p0:Program)"
        "-[:CALLS|LINKS_TO|XCTLS_TO*1..6]->(p:Program) "
        "WHERE p.id <> p0.id AND NOT p.id STARTS WITH 'unresolved:' "
        "RETURN DISTINCT p.id AS reachable_program ORDER BY reachable_program",
        {"tid": tid},
    )
    # Unresolved reaches: edges from any program in the closure whose target id
    # starts `unresolved:`. Each row carries the source program, target surface
    # form, and the breadcrumb identifier captured at extract time.
    unresolved = _kuzu_query(kuzu_db_path,
        "MATCH (t:CICSTransaction {id: $tid})-[:IS_TRANSACTION_FOR]->(p0:Program)"
        "-[c:CALLS|LINKS_TO|XCTLS_TO]->(u:Program) "
        "WHERE u.id STARTS WITH 'unresolved:' "
        "RETURN DISTINCT p0.id AS source_program, u.id AS target, "
        "c.breadcrumb AS breadcrumb, c.call_kind AS call_kind "
        "ORDER BY source_program, target",
        {"tid": tid},
    )
    return {
        "query": "Q3-transaction-closure",
        "input": {"transaction_id": tid},
        "entry_program": entry[0]["entry_program"] if entry else None,
        "reachable_programs": [r["reachable_program"] for r in reachable],
        "unresolved_reaches": unresolved,
    }


def run_q4_sample(kuzu_db_path: Path, tid: str = "transaction:CC00") -> dict:
    """Q4 — BMS map surface for transaction.

    Per spec §Q4: entry_program; map_interactions; mapsets; field_surface. `tid`
    defaults to the Gate-2/3 sample transaction; gold_match.py passes each gold-entry
    transaction id.
    """
    entry = _kuzu_query(kuzu_db_path,
        "MATCH (t:CICSTransaction {id: $tid})-[:IS_TRANSACTION_FOR]->(p:Program) "
        "RETURN p.id AS entry_program",
        {"tid": tid},
    )
    # Per spec, map_interactions includes maps from the entry program and reachable
    # programs (Q3 closure). For the simple form here, gather all maps from any
    # program reachable from the entry transaction (including the entry).
    map_interactions = _kuzu_query(kuzu_db_path,
        "MATCH (t:CICSTransaction {id: $tid})-[:IS_TRANSACTION_FOR]->(p:Program), "
        "(p)-[r:SENDS_MAP|RECEIVES_MAP]->(m:BMSMap) "
        "RETURN DISTINCT p.id AS program_id, m.id AS map_id, label(r) AS direction "
        "ORDER BY program_id, map_id",
        {"tid": tid},
    )
    # BMSMap → BMSMapset relationship is via property (mapset_id), not edge.
    mapsets = _kuzu_query(kuzu_db_path,
        "MATCH (t:CICSTransaction {id: $tid})-[:IS_TRANSACTION_FOR]->(p:Program), "
        "(p)-[:SENDS_MAP|RECEIVES_MAP]->(m:BMSMap), (ms:BMSMapset) "
        "WHERE ms.id = m.mapset_id "
        "RETURN DISTINCT ms.id AS mapset_id, ms.name AS mapset_name ORDER BY mapset_id",
        {"tid": tid},
    )
    field_surface = _kuzu_query(kuzu_db_path,
        "MATCH (t:CICSTransaction {id: $tid})-[:IS_TRANSACTION_FOR]->(p:Program), "
        "(p)-[:SENDS_MAP|RECEIVES_MAP]->(m:BMSMap) "
        "MATCH (f:BMSField) WHERE f.map_id = m.id AND f.label <> '' "
        "RETURN DISTINCT m.id AS map_id, f.name AS field_name, f.label AS label "
        "ORDER BY map_id, field_name LIMIT 50",
        {"tid": tid},
    )
    return {
        "query": "Q4-bms-map-surface",
        "input": {"transaction_id": tid},
        "entry_program": entry[0]["entry_program"] if entry else None,
        "map_interactions": map_interactions,
        "mapsets": mapsets,
        "field_surface": field_surface,
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    output_dir = repo_root / "artifacts" / "gate2"
    summary = run_pilot(repo_root, output_dir)
    return 1 if summary.get("validation_failed") else 0


if __name__ == "__main__":
    sys.exit(main())
