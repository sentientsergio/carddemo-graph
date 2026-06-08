"""Pass 3 — resolution.

Reads Pass-1/Pass-2 observations and writes:
  - entities.json     (final entity records, one per canonical id)
  - edges.json        (final edge records, with resolved from/to)
  - resolution_report.md (narrative of merge decisions + conflict ledger)
  - unresolved_report.md (Unresolved entities and why)

Resolution rules implemented:
  RUL-RES-001  COBOL LogicalFile → JCL DD → Dataset chain (batch)
  RUL-RES-002  CICS logical file → CSD DEFINE FILE → Dataset chain (online)
  RUL-RES-003  Transaction → Program (CSD authoritative)
  RUL-RES-005  PROGRAM-ID authoritative over filename (handled implicitly: COBOL extractor uses PROGRAM-ID for entity name)
  RUL-RES-006  PROC declared-name authoritative; filename mismatch → conflict ledger
  RUL-RES-010  Logical file → dataset conflicts
  RUL-DERIV-*  Derived properties (size_loc, fan_in, fan_out, reuse_count, organization, etc.)

Negation guards:
  RUL-NEG-001  dynamic CALL never promotes to static
  RUL-NEG-002  no direct Program → Dataset edge (enforced by edge vocabulary)
  RUL-NEG-006  COPY outside FD record area never produces DEFINES_LAYOUT_FOR (handled by COBOL extractor)
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from carddemo_graph.extract.observation import Observation, ObservationSink


# ---------------------------------------------------------------------------
# Conflict ledger
# ---------------------------------------------------------------------------

@dataclass
class ConflictEntry:
    canonical_id: str
    conflict_type: str
    rule_id: str
    description: str
    competing_sources: list[dict] = field(default_factory=list)
    resolution: str = ""

    def to_dict(self) -> dict:
        return {
            "canonical_id": self.canonical_id,
            "conflict_type": self.conflict_type,
            "rule_id": self.rule_id,
            "description": self.description,
            "competing_sources": self.competing_sources,
            "resolution": self.resolution,
        }


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

class Resolver:
    def __init__(self, observations: list[Observation],
                 source_files: dict[str, dict],
                 *,
                 schema_version: str,
                 extractor_version: str,
                 run_id: str,
                 corpus_hash: str):
        self.observations = observations
        self.source_files = source_files
        self.schema_version = schema_version
        self.extractor_version = extractor_version
        self.run_id = run_id
        self.corpus_hash = corpus_hash

        # Output containers
        self.entities: dict[str, dict] = {}    # id -> entity record
        self.edges: list[dict] = []
        self.conflicts: list[ConflictEntry] = []
        self.unresolved_records: list[dict] = []
        self.merge_decisions: list[dict] = []  # narrative log
        self.constructs_not_modeled: set[str] = set()

        # Pass-1 hint indices
        self.csd_file_to_dataset: dict[str, str] = {}  # cics_file_name -> dataset_id

    # ----------------------- main pipeline ------------------------

    def run(self) -> None:
        self._index_csd_bindings()
        self._merge_entity_candidates()
        self._resolve_partial_programs()
        self._materialize_online_logical_files()
        self._resolve_edges()
        self._derive_expands_to()
        self._derive_properties()
        self._collect_remaining_partials()
        self._note_constructs_not_modeled()

    def _collect_remaining_partials(self) -> None:
        """Ensure every partial entity is in unresolved_records (so unresolved_report
        lists them per spec §Validation §Unresolved). Some partials come from JCL
        DSN normalization (DSN containing unresolved `&PARM`) — these aren't picked
        up by other paths."""
        already = {u.get("id") for u in self.unresolved_records}
        for ent in self.entities.values():
            if not ent.get("partial"):
                continue
            if ent["id"] in already:
                continue
            reason = ent.get("properties", {}).get("partial_reason") or "partial_entity"
            prov = ent.get("provenance", [{}])
            self.unresolved_records.append({
                "id": ent["id"],
                "type": ent.get("type"),
                "reason": reason,
                "first_seen": prov[0] if prov else {},
                "surface_form": ent.get("properties", {}).get("surface_form"),
            })

    # ----------------------- EXPANDS_TO derivation ----------------

    def _derive_expands_to(self) -> None:
        """Per RUL-JCL-PROC-004: at each JCLProcInvocation, emit EXPANDS_TO edges
        to every JCLStep belonging to the invoked PROC's body.

        Reads JCLStep.properties.owner_id == the invoked JCLProc id.
        """
        # Build owner_id -> [step entities] index
        steps_by_owner: dict[str, list[dict]] = defaultdict(list)
        for ent in self.entities.values():
            if ent["type"] == "JCLStep":
                owner = ent.get("properties", {}).get("owner_id")
                if owner:
                    steps_by_owner[owner].append(ent)

        # For each JCLProcInvocation entity, find invoked PROC and emit EXPANDS_TO
        for ent in self.entities.values():
            if ent["type"] != "JCLProcInvocation":
                continue
            invoked = ent.get("properties", {}).get("invoked_proc_id")
            if not invoked:
                continue
            proc_steps = steps_by_owner.get(invoked, [])
            for step_ent in proc_steps:
                self.edges.append({
                    "id": self._next_edge_id(),
                    "type": "EXPANDS_TO",
                    "from": ent["id"],
                    "to": step_ent["id"],
                    "confidence": 1.0,
                    "evidence_kind": "derived",
                    "rule_id": "RUL-JCL-PROC-004",
                    "provenance": ent.get("provenance", [])[:1] + step_ent.get("provenance", [])[:1],
                    "attributes": {
                        "step_order": step_ent.get("properties", {}).get("step_order"),
                    },
                })

    # ----------------------- indexing -----------------------------

    def _index_csd_bindings(self) -> None:
        for o in self.observations:
            if (o.kind == "property_observation"
                    and o.data.get("binding_kind") == "csd_file_to_dataset"):
                fn = o.data["cics_file_name"].upper()
                self.csd_file_to_dataset[fn] = o.data["dataset_id"]

    # ----------------------- merge entity_candidates --------------

    def _merge_entity_candidates(self) -> None:
        candidates_by_id: dict[str, list[Observation]] = defaultdict(list)
        for o in self.observations:
            if o.kind == "entity_candidate":
                candidates_by_id[o.data["id_candidate"]].append(o)

        for cand_id, obs_list in candidates_by_id.items():
            self._merge_one_id(cand_id, obs_list)

    def _merge_one_id(self, cand_id: str, obs_list: list[Observation]) -> None:
        # Group provenance from all candidates
        provenance: list[dict] = []
        rule_ids: set[str] = set()
        all_data: dict[str, Any] = {}
        for o in obs_list:
            rule_ids.add(o.rule_id)
            for p in o.provenance:
                provenance.append(p.to_dict())
            # Last-wins merge for simple keys; specific keys merged differently
            for k, v in o.data.items():
                if v is None:
                    continue
                if k in ("filename_match", "filename_mismatch", "csd_only_until_resolved",
                         "csd_confirmed", "partial"):
                    # OR-semantics for flag-like keys
                    all_data[k] = bool(all_data.get(k)) or bool(v)
                elif k in ("alternate_record_keys", "competing_sources"):
                    cur = all_data.get(k) or []
                    cur.extend(v if isinstance(v, list) else [v])
                    all_data[k] = cur
                else:
                    all_data.setdefault(k, v)

        # Detect conflicts: PROC-name collision (different source files, same id)
        entity_type = all_data.get("entity_type")
        if entity_type == "JCLProc":
            sources = {p["source_path"] for p in provenance}
            if len(sources) > 1:
                # PROC-name collision
                self._record_proc_collision(cand_id, obs_list, sources)

        # Build the final entity record
        entity = {
            "id": cand_id,
            "type": entity_type,
            "name": all_data.get("name"),
            "provenance": provenance,
            "evidence_kind": "resolved" if len(obs_list) > 1 else "deterministic",
            "rule_id": _canonical_rule_id(rule_ids),
            "properties": self._extract_entity_properties(entity_type, all_data),
        }
        # When an entity is merged from >1 distinct rule, the canonical rule_id is a
        # deterministic LABEL; retain the full contributing set so nothing is lost
        # (single-rule entities omit this — rule_id alone is already complete).
        if len(rule_ids) > 1:
            entity["contributing_rule_ids"] = sorted(rule_ids)
        if all_data.get("partial"):
            entity["partial"] = True
        if all_data.get("filename_mismatch"):
            entity.setdefault("properties", {})["filename_mismatch"] = True

        self.entities[cand_id] = entity
        self.merge_decisions.append({
            "canonical_id": cand_id,
            "merged_observations": len(obs_list),
            "rule_ids": sorted(rule_ids),
            "sources": sorted({p["source_path"] for p in provenance}),
        })

    def _record_proc_collision(self, cand_id: str, obs_list: list[Observation],
                               sources: set[str]) -> None:
        primary, alts = self._partition_proc_candidates(obs_list)
        self.conflicts.append(ConflictEntry(
            canonical_id=cand_id,
            conflict_type="proc_name_collision",
            rule_id="RUL-RES-006",
            description=(
                f"Multiple source files declare the same PROC canonical id "
                f"`{cand_id}`. Per RUL-RES-006, the declared name on the "
                f"`//<name> PROC` line is authoritative over filename. "
                f"All sources retained as provenance; an entity is materialized "
                f"with merged provenance; downstream `USES_PROC` edges point to "
                f"this canonical id. Filename-mismatch source flagged."
            ),
            competing_sources=[
                {
                    "source_path": o.provenance[0].source_path,
                    "declared_name": o.data.get("declared_name"),
                    "filename": o.data.get("filename"),
                    "filename_mismatch": o.data.get("filename_mismatch", False),
                }
                for o in obs_list
            ],
            resolution=(
                f"Primary: {primary['source_path'] if primary else 'none'}; "
                f"alternates: {[a['source_path'] for a in alts]}. "
                f"Conflict retained for human review; entity created with merged provenance."
            ),
        ))

    def _partition_proc_candidates(self, obs_list: list[Observation]) -> tuple[dict | None, list[dict]]:
        primary = None
        alts = []
        for o in obs_list:
            entry = {
                "source_path": o.provenance[0].source_path,
                "filename_mismatch": o.data.get("filename_mismatch", False),
            }
            if not o.data.get("filename_mismatch") and primary is None:
                primary = entry
            else:
                alts.append(entry)
        return primary, alts

    def _extract_entity_properties(self, etype: str, data: dict) -> dict:
        # Map raw observation data to entity properties per type. Skeleton-only:
        # LLM-inferred properties (e.g. inferred_purpose) live in enrichments.json,
        # NOT here. Per the project's skeleton/enrichment principle.
        if etype == "Program":
            return {
                k: data[k] for k in ("size_loc", "filename_match", "asm_stub")
                if k in data
            }
        if etype == "Copybook":
            return {k: data[k] for k in ("reuse_count",) if k in data}
        if etype == "JCLJob":
            return {}
        if etype == "JCLStep":
            return {k: data[k] for k in ("owner_id", "step_order") if k in data}
        if etype == "JCLProc":
            return {k: data[k] for k in ("declared_name", "default_params",
                                         "filename_mismatch", "filename") if k in data}
        if etype == "JCLProcInvocation":
            return {k: data[k] for k in ("owner_id", "invoked_proc_id", "positional")
                    if k in data}
        if etype == "LogicalFile":
            return {k: data[k] for k in ("scope", "assign_dd", "organization",
                                         "access_mode", "record_key",
                                         "alternate_record_keys", "program_id",
                                         "binding_source") if k in data}
        if etype == "Dataset":
            # NB: 'inferred_purpose' deliberately omitted — it's enrichment, not skeleton.
            return {k: data[k] for k in ("organization", "gdg_offset",
                                         "unresolved_tokens", "partial") if k in data}
        if etype == "BMSMapset":
            return {k: data[k] for k in ("lang", "mode", "ctrl") if k in data}
        if etype == "BMSMap":
            return {k: data[k] for k in ("mapset_id", "line_pos", "column_pos",
                                         "size_rows", "size_cols") if k in data}
        if etype == "BMSField":
            return {k: data[k] for k in ("map_id", "mapset_id", "pos_row", "pos_col",
                                         "length", "attrb", "color", "initial_value",
                                         "prompt_value", "label", "is_filler")
                    if k in data}
        if etype == "CICSTransaction":
            return {k: data[k] for k in ("description",) if k in data}
        if etype == "DataItem":
            return {k: data[k] for k in ("level", "picture", "usage", "occurs",
                                         "redefines", "is_filler", "is_group",
                                         "suggested_sql_type", "parent_item",
                                         "copybook_id") if k in data}
        return {}

    # ----------------------- partial Programs (CSD-only) ----------

    def _resolve_partial_programs(self) -> None:
        """Mark Programs `partial: true` when they exist only in CSD with no source body."""
        program_sources: dict[str, set[str]] = defaultdict(set)
        for o in self.observations:
            if o.kind == "entity_candidate" and o.data.get("entity_type") == "Program":
                rule = o.rule_id
                program_sources[o.data["id_candidate"]].add(rule)
        for pid, rules in program_sources.items():
            if rules == {"RUL-CSD-002"}:
                # CSD-only: no .cbl or .asm source
                if pid in self.entities:
                    self.entities[pid]["partial"] = True
                    props = self.entities[pid].setdefault("properties", {})
                    props["partial_reason"] = "csd_only_no_source_body"
                    # Record into unresolved_records so unresolved_report.md lists it
                    prov = self.entities[pid].get("provenance", [{}])
                    self.unresolved_records.append({
                        "id": pid,
                        "type": "Program",
                        "reason": "csd_only_no_source_body",
                        "first_seen": prov[0] if prov else {},
                    })

    # ----------------------- online LogicalFile materialization ---

    def _materialize_online_logical_files(self) -> None:
        """Create LogicalFile entities for online (CICS) file references.

        Each online program's `EXEC CICS verb FILE(<name>)` produces an edge_candidate
        pointing at `logical-file:<PROGRAM>/<NAME>`. We materialize that LogicalFile
        and, if a CSD csd_file_to_dataset hint exists for <NAME>, emit BINDS_TO.
        """
        seen_lfs: set[str] = set()
        for o in self.observations:
            if o.kind != "edge_candidate":
                continue
            if o.data.get("scope_hint") != "cics":
                continue
            to_id = o.data.get("to_candidate")
            if not to_id or not to_id.startswith("logical-file:"):
                continue
            if to_id in seen_lfs or to_id in self.entities:
                continue
            seen_lfs.add(to_id)
            # Parse logical-file:<PROGRAM>/<NAME>
            tail = to_id[len("logical-file:"):]
            if "/" not in tail:
                continue
            program, name = tail.split("/", 1)
            lf_entity = {
                "id": to_id,
                "type": "LogicalFile",
                "name": name,
                "provenance": [p.to_dict() for p in o.provenance],
                "evidence_kind": "resolved",
                "rule_id": "RUL-RES-002",
                "properties": {
                    "scope": "cics",
                    "program_id": f"program:{program}",
                    "binding_source": "CSD",
                },
            }
            self.entities[to_id] = lf_entity

            # BINDS_TO if CSD knows this file name
            ds_id = self.csd_file_to_dataset.get(name.upper())
            if ds_id:
                self.edges.append({
                    "id": self._next_edge_id(),
                    "type": "BINDS_TO",
                    "from": to_id,
                    "to": ds_id,
                    "confidence": 1.0,
                    "evidence_kind": "resolved",
                    "rule_id": "RUL-RES-002",
                    "provenance": [p.to_dict() for p in o.provenance],
                    "attributes": {
                        "dd_name": name,
                        "binding_source": "CSD",
                    },
                })

    # ----------------------- edge resolution ----------------------

    _edge_counter = 0

    def _next_edge_id(self) -> str:
        self._edge_counter += 1
        return f"edge-{self._edge_counter:06d}"

    def _resolve_edges(self) -> None:
        for o in self.observations:
            if o.kind != "edge_candidate":
                continue
            edge_type = o.data.get("edge_type")
            from_id = o.data.get("from")
            to_id = o.data.get("to_candidate") or o.data.get("to")
            if not (edge_type and from_id and to_id):
                continue
            # Resolve to-side: dynamic CALLs become Unresolved entities
            if o.data.get("call_kind") == "dynamic":
                to_id = self._materialize_unresolved(
                    to_id, target_type_hint="Program",
                    reason="dynamic_call",
                    breadcrumb=o.data.get("breadcrumb"),
                    provenance=o.provenance,
                )
            else:
                to_id = self._ensure_endpoint(to_id, o)
            from_id = self._ensure_endpoint(from_id, o)

            # Build final attributes. Keep call_kind + breadcrumb (per spec edge
            # model: "CALLS carries kind ∈ {static, dynamic} and breadcrumb if
            # dynamic"). Exclude internal/debug-only keys.
            attrs = {k: v for k, v in o.data.items()
                     if k not in ("edge_type", "from", "to_candidate", "to",
                                  "needs_pass2", "scope_hint", "operand_kind",
                                  "operand_surface",
                                  "csd_only_until_resolved", "csd_confirmed",
                                  "filename_match", "must_not_promote")}
            edge = {
                "id": self._next_edge_id(),
                "type": edge_type,
                "from": from_id,
                "to": to_id,
                "confidence": 1.0,
                "evidence_kind": "deterministic",
                "rule_id": o.rule_id,
                "provenance": [p.to_dict() for p in o.provenance],
                "attributes": attrs,
            }
            self.edges.append(edge)

    def _materialize_unresolved(self, sid: str, *, target_type_hint: str,
                                reason: str, breadcrumb: str | None,
                                provenance) -> str:
        if not sid.startswith("unresolved:"):
            return sid
        if sid in self.entities:
            return sid
        surface = sid[len("unresolved:"):]
        self.entities[sid] = {
            "id": sid,
            "type": "Unresolved" if False else target_type_hint,  # see note below
            "name": surface,
            "provenance": [p.to_dict() for p in provenance],
            "evidence_kind": "deterministic",
            "rule_id": "RUL-RES-006",
            "partial": True,
            "properties": {
                "surface_form": surface,
                "target_type_hint": target_type_hint,
                "reason": reason,
                "breadcrumb": breadcrumb,
            },
        }
        # Note above: schema.json's EntityType enum doesn't include "Unresolved"; the
        # kuzu schema has an Unresolved node table. For JSON artifacts we encode
        # Unresolved-ness via `partial: true` on a typed entity (Program here) plus
        # properties.reason. The kuzu loader detects partial=true + reason and routes
        # to the Unresolved node table.
        self.unresolved_records.append({
            "id": sid,
            "surface_form": surface,
            "target_type_hint": target_type_hint,
            "reason": reason,
            "breadcrumb": breadcrumb,
            "first_seen": provenance[0].to_dict(),
        })
        return sid

    def _ensure_endpoint(self, eid: str, obs: Observation) -> str:
        """If endpoint id doesn't exist as an entity, create a partial placeholder.

        Common cases:
          - DFHAID/DFHBMSCA copybooks (IBM-supplied, no source in corpus)
          - Programs referenced by INVOKES but not in our cbl set (LE runtimes etc.)
          - bms-map references when the mapset isn't in our subset
        """
        if eid in self.entities:
            return eid
        if eid.startswith("unresolved:"):
            return eid
        # Materialize a partial entity matching the prefix
        prefix, _, name = eid.partition(":")
        type_for_prefix = {
            "program": "Program",
            "copybook": "Copybook",
            "jcl-job": "JCLJob",
            "jcl-step": "JCLStep",
            "jcl-proc": "JCLProc",
            "jcl-proc-inv": "JCLProcInvocation",
            "logical-file": "LogicalFile",
            "dataset": "Dataset",
            "bms-mapset": "BMSMapset",
            "bms-map": "BMSMap",
            "bms-field": "BMSField",
            "transaction": "CICSTransaction",
            "dataitem": "DataItem",
        }.get(prefix)
        if not type_for_prefix:
            return eid  # cannot type — leave as-is (will fail validator if no entity)
        self.entities[eid] = {
            "id": eid,
            "type": type_for_prefix,
            "name": name.rsplit("/", 1)[-1] if "/" in name else name,
            "provenance": [p.to_dict() for p in obs.provenance],
            "evidence_kind": "deterministic",
            "rule_id": "RUL-RES-005",
            "partial": True,
            "properties": {
                "partial_reason": "referenced_but_not_directly_observed",
                "referenced_by_rule": obs.rule_id,
            },
        }
        self.unresolved_records.append({
            "id": eid,
            "type": type_for_prefix,
            "reason": "external_reference_no_source_body",
            "first_seen": obs.provenance[0].to_dict(),
        })
        return eid

    # ----------------------- derived properties -------------------

    def _derive_properties(self) -> None:
        # fan_in / fan_out
        fan_in: dict[str, int] = defaultdict(int)
        fan_out: dict[str, int] = defaultdict(int)
        reuse_count: dict[str, int] = defaultdict(int)
        for e in self.edges:
            fan_in[e["to"]] += 1
            fan_out[e["from"]] += 1
            if e["type"] == "INCLUDES":
                reuse_count[e["to"]] += 1
        for eid, ent in self.entities.items():
            props = ent.setdefault("properties", {})
            if ent["type"] == "Program":
                props["fan_in"] = fan_in[eid]
                props["fan_out"] = fan_out[eid]
            if ent["type"] == "Copybook":
                props["reuse_count"] = reuse_count.get(eid, 0)
            if ent["type"] == "CICSTransaction":
                props["fan_out"] = fan_out[eid]
            if ent["type"] == "Dataset":
                props["organization"] = _derive_dataset_organization(ent["name"])

        self._derive_coupling_metrics()

    # Data-coupling metrics — deterministic, skeleton-class derivations over the
    # data-access graph (deductive over existing edges, not inference). Scope is
    # in-corpus application programs (non-partial Program entities); system
    # utilities / phantoms / asm-stubs are out of analytical scope, matching the
    # application-program scope of Q5 / clustering_report.md.
    _PLUMBING_DD = {"STEPLIB", "JOBLIB"}   # load-library concatenation, not data access
    _FILE_ACCESS = {"READS", "WRITES", "UPDATES", "DELETES", "STARTS_BROWSE"}

    def _derive_coupling_metrics(self) -> None:
        """RUL-DERIV-005 (Program.straddle_score) + RUL-DERIV-008 (Dataset.centrality).

        Each program's accessed-dataset set is composed two ways:
          - online: Program -[READS|WRITES|UPDATES|DELETES|STARTS_BROWSE]-> LogicalFile
                    -[BINDS_TO]-> Dataset
          - batch:  Program <-[INVOKES]- JCLStep -[USES_DATASET]-> Dataset
                    (STEPLIB/JOBLIB DD allocations excluded — load-library plumbing,
                    not data access; this is the deterministic form of the LOADLIB
                    filter described in clustering_report.md §1).

        Over P = in-corpus app programs with >=1 such dataset access:
          - Dataset.centrality     = |app programs accessing it| / |P|            in [0,1]
          - Program.straddle_score = |other app programs sharing >=1 dataset| / (|P|-1) in [0,1]

        straddle_score is data-coupling breadth (a skeleton-pure proxy for the
        bounded-context straddle notion), NOT the naming-convention cluster-relative
        straddle of the informational Q5 report — that heuristic is not skeleton-class.
        """
        lf_to_ds: dict[str, set[str]] = defaultdict(set)
        step_to_prog: dict[str, set[str]] = defaultdict(set)
        for e in self.edges:
            if e["type"] == "BINDS_TO":
                lf_to_ds[e["from"]].add(e["to"])
            elif e["type"] == "INVOKES":
                step_to_prog[e["from"]].add(e["to"])

        def is_app_program(pid: str) -> bool:
            ent = self.entities.get(pid)
            return bool(ent) and ent["type"] == "Program" and not ent.get("partial")

        prog_to_ds: dict[str, set[str]] = defaultdict(set)
        for e in self.edges:
            if e["type"] in self._FILE_ACCESS and is_app_program(e["from"]):
                for d in lf_to_ds.get(e["to"], ()):
                    prog_to_ds[e["from"]].add(d)
            elif e["type"] == "USES_DATASET":
                if (e.get("attributes") or {}).get("dd_name") in self._PLUMBING_DD:
                    continue
                for p in step_to_prog.get(e["from"], ()):
                    if is_app_program(p):
                        prog_to_ds[p].add(e["to"])

        P = {p for p, ds in prog_to_ds.items() if ds}
        n = len(P)

        ds_accessors: dict[str, set[str]] = defaultdict(set)
        for p in P:
            for d in prog_to_ds[p]:
                ds_accessors[d].add(p)

        for eid, ent in self.entities.items():
            if ent["type"] == "Dataset":
                acc = len(ds_accessors.get(eid, ()))
                ent.setdefault("properties", {})["centrality"] = (
                    round(acc / n, 4) if n else 0.0
                )
            elif ent["type"] == "Program" and not ent.get("partial"):
                mine = prog_to_ds.get(eid, set())
                if not mine or n <= 1:
                    score = 0.0
                else:
                    coupled = {q for q in P if q != eid and (prog_to_ds[q] & mine)}
                    score = round(len(coupled) / (n - 1), 4)
                ent.setdefault("properties", {})["straddle_score"] = score

    # ----------------------- constructs not modeled ----------------

    def _note_constructs_not_modeled(self) -> None:
        # If we see any HANDLE/ABEND/ASKTIME/WRITEQ in observations, flag them.
        # In Pass 1 the COBOL extractor doesn't emit observations for these (correct
        # by spec — closed edge vocabulary). The list is informational for report.md.
        self.constructs_not_modeled.update({
            "EXEC CICS HANDLE (operational; no closed-vocab edge)",
            "EXEC CICS ABEND (operational; no closed-vocab edge)",
            "EXEC CICS ASKTIME / FORMATTIME (operational; no closed-vocab edge)",
            "EXEC CICS WRITEQ / READQ TS|TD (TS/TD queues; not in v1 closed vocab)",
            "EXEC CICS ASSIGN (operational; no closed-vocab edge)",
            "EXEC CICS INQUIRE (operational; no closed-vocab edge)",
            "DCLGEN copybooks (.dcl) — DB2 schema, not in v1 base mode",
            "DB2 EXEC SQL — needs-ext per spec §Deferred extensions",
            "IMS DBD/PSB — needs-ext per spec §Deferred extensions",
            "MQ EXEC MQ — needs-ext per spec §Deferred extensions",
            "COBOL paragraphs/sections (intra-program control flow) — out-of-scope per v1 design decisions",
            "DataItem (field-level) — out-of-scope per v1 design decisions",
        })

    # ----------------------- output -------------------------------

    def write_artifacts(self, *, artifacts_dir: Path) -> None:
        header = {
            "schema_version": self.schema_version,
            "extractor_version": self.extractor_version,
            "run_id": self.run_id,
            "corpus_hash": self.corpus_hash,
            "source_files": list(self.source_files.values()),
        }

        # entities.json
        entities_artifact = {**header, "entities": list(self.entities.values())}
        (artifacts_dir / "entities.json").write_text(
            json.dumps(entities_artifact, indent=2, default=str)
        )

        # edges.json
        edges_artifact = {**header, "edges": self.edges}
        (artifacts_dir / "edges.json").write_text(
            json.dumps(edges_artifact, indent=2, default=str)
        )

        # observations.json (all Pass-1 observations)
        observations_artifact = {
            **header,
            "observations": [o.to_dict() for o in self.observations],
        }
        (artifacts_dir / "observations.json").write_text(
            json.dumps(observations_artifact, indent=2, default=str)
        )

        # enrichments.json — empty in v1 by design. Pass 2's promotion step will
        # populate it later. The empty artifact establishes the architectural
        # commitment: skeleton (entities/edges) is provenanced ground truth,
        # enrichments are separate. See artifacts/schema.json §EnrichmentsArtifact.
        enrichments_artifact = {**header, "enrichments": []}
        (artifacts_dir / "enrichments.json").write_text(
            json.dumps(enrichments_artifact, indent=2, default=str)
        )

        # resolution_report.md
        self._write_resolution_report(artifacts_dir / "resolution_report.md")

        # unresolved_report.md
        self._write_unresolved_report(artifacts_dir / "unresolved_report.md")

        # constructs_not_modeled.md
        self._write_constructs_not_modeled(artifacts_dir / "constructs_not_modeled.md")

    def _write_resolution_report(self, path: Path) -> None:
        lines: list[str] = []
        lines.append("# Resolution Report")
        lines.append("")
        lines.append(f"- run_id: `{self.run_id}`")
        lines.append(f"- schema_version: `{self.schema_version}`")
        lines.append(f"- extractor_version: `{self.extractor_version}`")
        lines.append(f"- entities: **{len(self.entities)}**")
        lines.append(f"- edges: **{len(self.edges)}**")
        lines.append(f"- conflict-ledger entries: **{len(self.conflicts)}**")
        lines.append(f"- unresolved/partial records: **{len(self.unresolved_records)}**")
        lines.append("")
        lines.append("## Merge decisions")
        lines.append("")
        for md in sorted(self.merge_decisions, key=lambda d: d["canonical_id"]):
            if md["merged_observations"] > 1:
                lines.append(f"- `{md['canonical_id']}` — merged from "
                             f"{md['merged_observations']} observations, "
                             f"rules: {', '.join(md['rule_ids'])}, "
                             f"sources: {', '.join(md['sources'])}")
        lines.append("")
        lines.append("## Conflict ledger")
        lines.append("")
        if not self.conflicts:
            lines.append("_(no conflicts)_")
        for c in self.conflicts:
            lines.append(f"### Conflict — `{c.canonical_id}` ({c.conflict_type})")
            lines.append("")
            lines.append(f"- **rule:** `{c.rule_id}`")
            lines.append(f"- **description:** {c.description}")
            lines.append("- **competing sources:**")
            for s in c.competing_sources:
                lines.append(f"  - `{s.get('source_path')}` "
                             f"(filename_mismatch={s.get('filename_mismatch')})")
            lines.append(f"- **resolution:** {c.resolution}")
            lines.append("")
        path.write_text("\n".join(lines))

    def _write_unresolved_report(self, path: Path) -> None:
        lines: list[str] = []
        lines.append("# Unresolved References Report")
        lines.append("")
        lines.append("Per spec §Conflict handling: 'Unresolved references emit as `Unresolved` placeholders. Never dropped.'")
        lines.append("")
        lines.append(f"Total unresolved/partial: **{len(self.unresolved_records)}**")
        lines.append("")
        # Group by reason
        by_reason: dict[str, list[dict]] = defaultdict(list)
        for u in self.unresolved_records:
            by_reason[u.get("reason", "unspecified")].append(u)
        for reason in sorted(by_reason):
            lines.append(f"## Reason: `{reason}` ({len(by_reason[reason])})")
            lines.append("")
            for u in by_reason[reason]:
                bits = [f"- **{u.get('id')}** ({u.get('type', 'Program')})"]
                sf = u.get("surface_form")
                if sf:
                    bits.append(f" — surface_form: `{sf}`")
                bc = u.get("breadcrumb")
                if bc:
                    bits.append(f" — breadcrumb: `{bc}`")
                lines.append("".join(bits))
                fs = u.get("first_seen", {})
                if fs:
                    lines.append(f"  - first seen: `{fs.get('source_path')}:{fs.get('start_line')}`")
            lines.append("")
        path.write_text("\n".join(lines))

    def _write_constructs_not_modeled(self, path: Path) -> None:
        lines: list[str] = []
        lines.append("# Constructs Not Modeled")
        lines.append("")
        lines.append("Per spec §Out of scope and §Deferred extensions, the following constructs are observed in CardDemo (or in adjacent contexts) but **not** modeled in v1 base-mode extraction:")
        lines.append("")
        for c in sorted(self.constructs_not_modeled):
            lines.append(f"- {c}")
        lines.append("")
        path.write_text("\n".join(lines))


# Canonical rule_id precedence for a merged entity. The canonical rule_id labels
# where an entity is DEFINED / most-concretely-attested, not where it's merely
# referenced: COBOL/BMS source > JCL (physical allocation) > CSD (CICS catalog
# binding) > resolution-synthesized; lexicographic within a family. Deterministic
# and seed-independent (replaces a hash-ordered `next(iter(set))` pick that violated
# the byte-identical reproducibility guarantee). See deterministic_rules.md.
_RULE_FAMILY_RANK = {
    "RUL-COBOL": 1,
    "RUL-BMS": 2,
    "RUL-JCL-PROC": 3,
    "RUL-JCL": 3,
    "RUL-CSD": 4,
    "RUL-RES": 5,
}


def _rule_rank(rule_id: str) -> int:
    # longest matching family prefix wins (RUL-JCL-PROC before RUL-JCL)
    for fam in sorted(_RULE_FAMILY_RANK, key=len, reverse=True):
        if rule_id.startswith(fam):
            return _RULE_FAMILY_RANK[fam]
    return 6  # unknown family: after known families, then lexicographic


def _canonical_rule_id(rule_ids: set[str]) -> str:
    """Deterministic pick of the canonical rule_id for a merged entity."""
    return min(rule_ids, key=lambda r: (_rule_rank(r), r))


def _derive_dataset_organization(dsn: str) -> str:
    """RUL-DERIV-006: cascade of suffix/name heuristics on the normalized DSN base.

    See artifacts/deterministic_rules.md §RUL-DERIV-006 for the precedence ordering.
    DSN is the base name (per-generation tokens like `(+1)` are already normalized
    away by RUL-JCL-004).
    """
    if dsn.endswith(".VSAM.KSDS"):
        return "VSAM_KSDS"
    if dsn.endswith(".VSAM.AIX.PATH"):
        return "VSAM_AIX_PATH"
    if dsn.endswith(".PS"):
        return "PS"
    if "VSAM" in dsn:
        return "VSAM"
    # GDG base: BKUP / DALY suffixes are conventional GDG names in CardDemo
    if dsn.endswith(".BKUP") or dsn.endswith(".DALY"):
        return "GDG_BASE"
    # PDS: LOADLIB convention (load-module library)
    qualifiers = dsn.split(".")
    if dsn.endswith(".LOADLIB") or "LOADLIB" in qualifiers:
        return "PDS"
    # Sentinels: NULLFILE (z/OS magic), unresolved symbolic param
    if dsn == "NULLFILE" or dsn.startswith("&"):
        return "UNKNOWN_SENTINEL"
    # Fallback: multi-qualifier DSN with no recognized suffix → PS (sequential is
    # the default classification for plain-named flat datasets in this corpus
    # context). Single-token DSNs without a qualifier hierarchy stay unclassified.
    if len(qualifiers) >= 2:
        return "PS"
    return "UNKNOWN"


def resolve(sink: ObservationSink, *,
            schema_version: str,
            extractor_version: str,
            run_id: str,
            corpus_hash: str) -> Resolver:
    source_files = {sf.id: sf.to_dict() for sf in sink.source_files.values()}
    r = Resolver(
        observations=sink.observations,
        source_files=source_files,
        schema_version=schema_version,
        extractor_version=extractor_version,
        run_id=run_id,
        corpus_hash=corpus_hash,
    )
    r.run()
    return r
