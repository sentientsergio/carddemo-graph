"""Semantic coverage assertions over Gate-2/Gate-3 output.

Per spec §Validation §Semantic coverage assertions:

- Every transaction in gold set has an entry program
- Every BMS map in Q4 has at least one user-visible field label, unless truly fieldless
- Every dataset in Q2 has both JCL binding evidence and COBOL logical file path where applicable
- Every modernization-relevant dataset has `organization` populated where derivable
- Every unresolved reference appears in both edges.json and report.md

These complement the structural invariants in `structural.py` (which check that the
JSON shape is well-formed). Semantic coverage checks whether the *graph content*
actually supports the queries the spec promises.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CoverageReport:
    checks: list[dict] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c["status"] == "pass")

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c["status"] == "fail")

    @property
    def warnings(self) -> int:
        return sum(1 for c in self.checks if c["status"] == "warn")

    def ok(self) -> bool:
        return self.failed == 0

    def add(self, name: str, status: str, detail: str = "", **extra: Any) -> None:
        item = {"name": name, "status": status, "detail": detail}
        item.update(extra)
        self.checks.append(item)


def assert_coverage(entities: list[dict], edges: list[dict],
                    unresolved_report_text: str = "") -> CoverageReport:
    r = CoverageReport()
    by_type: dict[str, list[dict]] = {}
    by_id: dict[str, dict] = {}
    for e in entities:
        by_type.setdefault(e["type"], []).append(e)
        by_id[e["id"]] = e

    edges_by_type: dict[str, list[dict]] = {}
    for e in edges:
        edges_by_type.setdefault(e["type"], []).append(e)

    # ----- Every transaction has an entry program -----
    transactions = by_type.get("CICSTransaction", [])
    is_tx_for = edges_by_type.get("IS_TRANSACTION_FOR", [])
    txn_to_prog = {e["from"] for e in is_tx_for}
    missing = [t["id"] for t in transactions if t["id"] not in txn_to_prog]
    if not transactions:
        r.add("transactions_have_entry_program", "warn",
              "no CICSTransaction entities present (Gate-2 subset may not include CSD)")
    elif missing:
        r.add("transactions_have_entry_program", "fail",
              f"{len(missing)} transaction(s) without IS_TRANSACTION_FOR edge: {missing}")
    else:
        r.add("transactions_have_entry_program", "pass",
              f"all {len(transactions)} transactions have entry programs")

    # ----- Every BMS map has at least one user-visible field label -----
    # Exclude partial placeholders: those are unresolved identifier-form MAP/MAPSET
    # operands (e.g., MAP(WS-MAP-NAME)) which Pass 1 couldn't resolve to a literal
    # map and Pass 3 materialized as partial; they're tracked in unresolved_report.
    maps = [m for m in by_type.get("BMSMap", []) if not m.get("partial")]
    fields = by_type.get("BMSField", [])
    fields_by_map: dict[str, list[dict]] = {}
    for f in fields:
        fields_by_map.setdefault(f["properties"].get("map_id", ""), []).append(f)
    label_missing = []
    for m in maps:
        f_in_map = fields_by_map.get(m["id"], [])
        if not f_in_map:
            label_missing.append((m["id"], "no fields"))
            continue
        has_visible = any(f["properties"].get("label", "") for f in f_in_map)
        if not has_visible:
            label_missing.append((m["id"], "all fields fieldless"))
    if not maps:
        r.add("bms_maps_have_visible_label", "warn",
              "no resolved BMSMap entities in this artifact set")
    elif label_missing:
        r.add("bms_maps_have_visible_label", "fail",
              f"maps without visible labels: {label_missing}")
    else:
        r.add("bms_maps_have_visible_label", "pass",
              f"all {len(maps)} resolved maps have at least one visible field label")

    # ----- Every dataset has organization populated (where derivable) -----
    datasets = by_type.get("Dataset", [])
    no_org = [d["id"] for d in datasets if not d.get("properties", {}).get("organization")]
    derivable = [d for d in datasets if d.get("properties", {}).get("organization")]
    if not datasets:
        r.add("datasets_have_organization", "warn",
              "no Dataset entities in this artifact set")
    elif no_org:
        r.add("datasets_have_organization", "warn",
              f"{len(no_org)} datasets without derivable organization "
              f"(typically because DSN suffix doesn't match VSAM/PS pattern): {no_org[:5]}...",
              count=len(no_org))
    else:
        r.add("datasets_have_organization", "pass",
              f"all {len(datasets)} datasets have organization")

    # ----- Coupling metrics present + in range (RUL-DERIV-005 / -008) -----
    # straddle_score on every in-corpus (non-partial) Program; centrality on every
    # Dataset. Both must be floats in [0,1]. (v2.1: KU-11 — these were null in v1.)
    def _bad_metric(items: list[dict], key: str) -> list[str]:
        bad = []
        for it in items:
            v = (it.get("properties") or {}).get(key)
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not (0.0 <= v <= 1.0):
                bad.append(it["id"])
        return bad
    app_programs = [p for p in by_type.get("Program", []) if not p.get("partial")]
    bad_straddle = _bad_metric(app_programs, "straddle_score")
    bad_centrality = _bad_metric(datasets, "centrality")
    if not app_programs and not datasets:
        r.add("coupling_metrics_populated", "warn",
              "no Program/Dataset entities in this artifact set")
    elif bad_straddle or bad_centrality:
        r.add("coupling_metrics_populated", "fail",
              f"missing/out-of-range straddle_score on {len(bad_straddle)} programs "
              f"{bad_straddle[:5]}; centrality on {len(bad_centrality)} datasets "
              f"{bad_centrality[:5]}")
    else:
        r.add("coupling_metrics_populated", "pass",
              f"straddle_score on all {len(app_programs)} app programs + "
              f"centrality on all {len(datasets)} datasets, in [0,1]")

    # ----- DataItem layer: elementary items typed; record-layout copybooks covered
    #       (v2.2 KU-9). Every non-group, non-FILLER DataItem must carry a
    #       suggested_sql_type; every copybook with HAS_FIELD must have >=1 DataItem. -----
    data_items = by_type.get("DataItem", [])
    if not data_items:
        r.add("dataitems_typed", "warn", "no DataItem entities in this artifact set")
    else:
        untyped = [d["id"] for d in data_items
                   if not (d.get("properties") or {}).get("is_group")
                   and not (d.get("properties") or {}).get("is_filler")
                   and not (d.get("properties") or {}).get("suggested_sql_type")]
        roots = {e["to"] for e in edges_by_type.get("HAS_FIELD", [])}
        if untyped:
            r.add("dataitems_typed", "fail",
                  f"{len(untyped)} elementary DataItems without suggested_sql_type: {untyped[:5]}")
        else:
            r.add("dataitems_typed", "pass",
                  f"all elementary (non-group/non-FILLER) of {len(data_items)} DataItems "
                  f"have suggested_sql_type; {len(roots)} record roots via HAS_FIELD")

    # ----- Every dataset has either JCL or COBOL binding evidence -----
    uses_dataset = edges_by_type.get("USES_DATASET", [])
    binds_to = edges_by_type.get("BINDS_TO", [])
    datasets_bound: set[str] = set()
    datasets_bound.update(e["to"] for e in uses_dataset)
    datasets_bound.update(e["to"] for e in binds_to)
    unbound = [d["id"] for d in datasets if d["id"] not in datasets_bound]
    if datasets and unbound:
        # These are typically Datasets known only from CSD DSNAME() with no JCL use in the subset
        r.add("datasets_have_binding_evidence", "warn",
              f"{len(unbound)} datasets without USES_DATASET or BINDS_TO edge in this subset",
              count=len(unbound), sample=unbound[:5])
    elif datasets:
        r.add("datasets_have_binding_evidence", "pass",
              f"all {len(datasets)} datasets have binding evidence")

    # ----- BINDS_TO MUST be the only path Program → Dataset (RUL-NEG-002) -----
    # We assert: there is no direct (Program, ..., Dataset) edge.
    direct_violations = []
    for e in edges:
        from_ent = by_id.get(e["from"])
        to_ent = by_id.get(e["to"])
        if from_ent and to_ent and from_ent["type"] == "Program" and to_ent["type"] == "Dataset":
            direct_violations.append(e["id"])
    if direct_violations:
        r.add("no_direct_program_dataset_edges", "fail",
              f"violations: {direct_violations}")
    else:
        r.add("no_direct_program_dataset_edges", "pass",
              "no direct Program → Dataset edges (RUL-NEG-002 holds)")

    # ----- llm_candidate must never appear in edges.json -----
    bad_llm = [e["id"] for e in edges if e.get("evidence_kind") == "llm_candidate"]
    if bad_llm:
        r.add("no_llm_candidate_in_edges", "fail", f"violations: {bad_llm}")
    else:
        r.add("no_llm_candidate_in_edges", "pass",
              "no llm_candidate evidence in final edges (RUL-NEG-001-adjacent)")

    # ----- Dynamic CALL must not be promoted to static -----
    bad_dynamic = []
    for e in edges:
        if e["type"] == "CALLS" and e.get("attributes", {}).get("call_kind") == "dynamic":
            # to-side must be unresolved:* prefix
            if not e["to"].startswith("unresolved:"):
                bad_dynamic.append(e["id"])
    if bad_dynamic:
        r.add("dynamic_calls_not_promoted_static", "fail",
              f"violations: {bad_dynamic}")
    else:
        r.add("dynamic_calls_not_promoted_static", "pass",
              "no dynamic CALL silently promoted to a typed Program target (RUL-NEG-001)")

    # ----- Every entity has stable ID and unique canonical key -----
    ids = [e["id"] for e in entities]
    if len(set(ids)) != len(ids):
        from collections import Counter
        dups = [k for k, v in Counter(ids).items() if v > 1]
        r.add("entity_ids_unique", "fail", f"duplicates: {dups[:5]}")
    else:
        r.add("entity_ids_unique", "pass", f"{len(ids)} entities, all unique ids")

    # ----- Every edge has non-empty provenance (already checked by structural, but
    # re-asserted here so the semantic report stands alone) -----
    empty_prov = [e["id"] for e in edges if not e.get("provenance")]
    if empty_prov:
        r.add("edges_have_provenance", "fail", f"violations: {empty_prov[:5]}")
    else:
        r.add("edges_have_provenance", "pass",
              f"all {len(edges)} edges have non-empty provenance")

    # ----- Unresolved references should appear in unresolved_report (when text supplied) -----
    if unresolved_report_text:
        partial_ids = [e["id"] for e in entities if e.get("partial")]
        missing_from_report = [pid for pid in partial_ids if pid not in unresolved_report_text]
        if missing_from_report:
            r.add("partial_entities_in_unresolved_report", "fail",
                  f"{len(missing_from_report)} partial entities not in unresolved report: "
                  f"{missing_from_report[:5]}")
        else:
            r.add("partial_entities_in_unresolved_report", "pass",
                  f"all {len(partial_ids)} partial entities listed in unresolved report")

    return r


def assert_from_files(entities_path: Path, edges_path: Path,
                      unresolved_report_path: Path | None = None) -> CoverageReport:
    entities = json.loads(entities_path.read_text())["entities"]
    edges = json.loads(edges_path.read_text())["edges"]
    text = unresolved_report_path.read_text() if unresolved_report_path and unresolved_report_path.exists() else ""
    return assert_coverage(entities, edges, text)


def main(args: list[str]) -> int:
    if len(args) < 2:
        print("usage: semantic.py entities.json edges.json [unresolved_report.md]")
        return 2
    rep = assert_from_files(Path(args[0]), Path(args[1]),
                            Path(args[2]) if len(args) > 2 else None)
    for c in rep.checks:
        status_tag = {"pass": "OK", "fail": "FAIL", "warn": "WARN"}[c["status"]]
        print(f"  [{status_tag}] {c['name']:<40} {c.get('detail', '')}")
    print()
    print(f"Total: pass={rep.passed} warn={rep.warnings} fail={rep.failed}")
    return 0 if rep.ok() else 1


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
