"""Structural invariants validator for entity/edge/observation artifacts.

Implements the invariants from spec v4 §Validation §Structural invariants. Used at
Gate 1 to confirm samples pass; used at every gate thereafter on whatever artifacts
exist.

Pure stdlib — no jsonschema dependency. The JSON Schema in artifacts/schema.json is the
declarative reference; this module enforces the must-hold invariants directly.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Per artifacts/schema.json: entity-type prefixes that an EntityId may use
_ENTITY_ID_PREFIXES = {
    "program", "copybook", "jcl-job", "jcl-step", "jcl-proc",
    "jcl-proc-inv", "logical-file", "dataset", "bms-mapset",
    "bms-map", "bms-field", "transaction", "unresolved", "dataitem",
}
_ENTITY_ID_RE = re.compile(r"^([a-z][a-z-]*):.+$")
_RULE_ID_RE = re.compile(r"^RUL-[A-Z]+(?:-[A-Z]+)*-\d{3}$")

_ENTITY_TYPES = {
    "Program", "Copybook", "JCLJob", "JCLStep", "JCLProc",
    "JCLProcInvocation", "LogicalFile", "Dataset", "BMSMapset",
    "BMSMap", "BMSField", "CICSTransaction", "DataItem",
}
_EDGE_TYPES = {
    "INCLUDES", "EXPANDS_TO", "DEFINES_LAYOUT_FOR",
    "CALLS", "LINKS_TO", "XCTLS_TO", "RETURNS_TO_TRANSID",
    "SENDS_MAP", "RECEIVES_MAP",
    "DECLARES_FILE", "BINDS_TO",
    "READS", "WRITES", "UPDATES", "DELETES", "STARTS_BROWSE",
    "INVOKES", "USES_DATASET", "USES_PROC", "PASSES_SYSIN_TO",
    "IS_TRANSACTION_FOR",
    "HAS_FIELD", "CONTAINS_ITEM",
}
_EVIDENCE_KINDS = {"deterministic", "llm_candidate", "resolved", "derived", "manual"}

# Spec §Negative gold-set tests: direct Program → Dataset edges must not exist.
# Enforced indirectly: there is no edge type connecting Program to Dataset; this check
# is here to make the invariant explicit if a future schema change introduces one.
_DIRECT_PROG_DATASET_EDGE_TYPES = set()  # always empty per spec


@dataclass
class Issue:
    level: str            # "error" | "warning"
    artifact: str         # path to artifact
    where: str            # locator within the artifact (e.g., "entities[3]" or "edges[12]")
    message: str
    rule: str             # invariant name


@dataclass
class Report:
    artifact: str
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    def ok(self) -> bool:
        return not self.errors


def _check_provenance(prov: Any, artifact: str, where: str, rule: str) -> list[Issue]:
    issues: list[Issue] = []
    if not isinstance(prov, list) or not prov:
        issues.append(Issue("error", artifact, where,
                            "provenance must be a non-empty array",
                            rule))
        return issues
    for i, item in enumerate(prov):
        if not isinstance(item, dict):
            issues.append(Issue("error", artifact, f"{where}.provenance[{i}]",
                                "provenance item must be an object", rule))
            continue
        required = ("source_path", "start_line", "end_line",
                    "source_file_id", "source_hash")
        for key in required:
            if key not in item:
                issues.append(Issue("error", artifact, f"{where}.provenance[{i}]",
                                    f"missing required field: {key}", rule))
        start, end = item.get("start_line"), item.get("end_line")
        if isinstance(start, int) and isinstance(end, int) and start > end:
            issues.append(Issue("error", artifact, f"{where}.provenance[{i}]",
                                f"start_line ({start}) > end_line ({end})", rule))
    return issues


def _check_id_pattern(id_value: Any, artifact: str, where: str) -> list[Issue]:
    if not isinstance(id_value, str):
        return [Issue("error", artifact, where, "id must be a string", "id-shape")]
    m = _ENTITY_ID_RE.match(id_value)
    if not m:
        return [Issue("error", artifact, where,
                      f"id '{id_value}' does not match pattern <prefix>:<value>",
                      "id-shape")]
    if m.group(1) not in _ENTITY_ID_PREFIXES:
        return [Issue("error", artifact, where,
                      f"id prefix '{m.group(1)}' not in allowed set",
                      "id-shape")]
    return []


def _check_rule_id(rule_id: Any, artifact: str, where: str) -> list[Issue]:
    if rule_id is None:
        return [Issue("error", artifact, where, "rule_id missing", "rule_id-required")]
    if not isinstance(rule_id, str) or not _RULE_ID_RE.match(rule_id):
        return [Issue("error", artifact, where,
                      f"rule_id '{rule_id}' does not match RUL-<LANG>(-<SUB>)*-NNN",
                      "rule_id-shape")]
    return []


def validate_entities(payload: dict, artifact: str) -> Report:
    r = Report(artifact=artifact)
    if "entities" not in payload:
        r.issues.append(Issue("error", artifact, "$", "no entities[] array", "envelope"))
        return r
    seen_ids: set[str] = set()
    for i, ent in enumerate(payload["entities"]):
        where = f"entities[{i}]"
        # required fields
        for key in ("id", "type", "name", "provenance"):
            if key not in ent:
                r.issues.append(Issue("error", artifact, where,
                                      f"missing required entity field: {key}",
                                      "entity-required"))
        # id pattern + duplicates
        r.issues.extend(_check_id_pattern(ent.get("id"), artifact, f"{where}.id"))
        eid = ent.get("id")
        if eid in seen_ids:
            r.issues.append(Issue("error", artifact, f"{where}.id",
                                  f"duplicate entity id: {eid}",
                                  "entity-unique-id"))
        elif isinstance(eid, str):
            seen_ids.add(eid)
        # type in allowed enum
        etype = ent.get("type")
        if etype is not None and etype not in _ENTITY_TYPES:
            r.issues.append(Issue("error", artifact, f"{where}.type",
                                  f"unknown entity type: {etype}",
                                  "entity-type-enum"))
        # rule_id optional on entities, but if present must match shape
        if "rule_id" in ent:
            r.issues.extend(_check_rule_id(ent["rule_id"], artifact, f"{where}.rule_id"))
        # evidence_kind optional on entities; if present must be in enum
        if "evidence_kind" in ent and ent["evidence_kind"] not in _EVIDENCE_KINDS:
            r.issues.append(Issue("error", artifact, f"{where}.evidence_kind",
                                  f"unknown evidence_kind: {ent['evidence_kind']}",
                                  "evidence-kind-enum"))
        # provenance shape
        r.issues.extend(_check_provenance(ent.get("provenance"), artifact, where,
                                          "entity-provenance"))
    return r


def validate_edges(payload: dict, artifact: str, *,
                   entity_ids: set[str] | None = None) -> Report:
    r = Report(artifact=artifact)
    if "edges" not in payload:
        r.issues.append(Issue("error", artifact, "$", "no edges[] array", "envelope"))
        return r
    seen_ids: set[str] = set()
    for i, edge in enumerate(payload["edges"]):
        where = f"edges[{i}]"
        # required: id, type, from, to, confidence, evidence_kind, rule_id, provenance
        for key in ("id", "type", "from", "to", "confidence",
                    "evidence_kind", "rule_id", "provenance"):
            if key not in edge:
                r.issues.append(Issue("error", artifact, where,
                                      f"missing required edge field: {key}",
                                      "edge-required"))
        # edge id uniqueness
        edge_id = edge.get("id")
        if isinstance(edge_id, str):
            if edge_id in seen_ids:
                r.issues.append(Issue("error", artifact, f"{where}.id",
                                      f"duplicate edge id: {edge_id}",
                                      "edge-unique-id"))
            else:
                seen_ids.add(edge_id)
        # type in enum
        etype = edge.get("type")
        if etype is not None and etype not in _EDGE_TYPES:
            r.issues.append(Issue("error", artifact, f"{where}.type",
                                  f"unknown edge type: {etype}",
                                  "edge-type-enum"))
        # confidence in [0,1]
        conf = edge.get("confidence")
        if conf is not None and not (isinstance(conf, (int, float)) and 0.0 <= conf <= 1.0):
            r.issues.append(Issue("error", artifact, f"{where}.confidence",
                                  f"confidence must be number in [0,1]; got {conf!r}",
                                  "confidence-range"))
        # evidence_kind in enum; llm_candidate never in edges
        ev = edge.get("evidence_kind")
        if ev is not None:
            if ev not in _EVIDENCE_KINDS:
                r.issues.append(Issue("error", artifact, f"{where}.evidence_kind",
                                      f"unknown evidence_kind: {ev}",
                                      "evidence-kind-enum"))
            if ev == "llm_candidate":
                r.issues.append(Issue("error", artifact, f"{where}.evidence_kind",
                                      "llm_candidate must never appear in edges.json",
                                      "no-llm-candidate-in-edges"))
        # rule_id shape
        r.issues.extend(_check_rule_id(edge.get("rule_id"), artifact, f"{where}.rule_id"))
        # from/to id patterns
        r.issues.extend(_check_id_pattern(edge.get("from"), artifact, f"{where}.from"))
        r.issues.extend(_check_id_pattern(edge.get("to"), artifact, f"{where}.to"))
        # provenance
        r.issues.extend(_check_provenance(edge.get("provenance"), artifact, where,
                                          "edge-provenance"))
        # If we have a known entity universe, both endpoints should resolve
        # (warning only; merged-artifact validation is the strict check)
        if entity_ids is not None:
            for end in ("from", "to"):
                v = edge.get(end)
                if isinstance(v, str) and not v.startswith("unresolved:") and v not in entity_ids:
                    r.issues.append(Issue("warning", artifact, f"{where}.{end}",
                                          f"endpoint '{v}' has no matching entity in this artifact set",
                                          "edge-endpoint-resolution"))
    return r


def validate_enrichments(payload: dict, artifact: str) -> Report:
    r = Report(artifact=artifact)
    if "enrichments" not in payload:
        r.issues.append(Issue("error", artifact, "$", "no enrichments[] array", "envelope"))
        return r
    seen_ids: set[str] = set()
    for i, enr in enumerate(payload["enrichments"]):
        where = f"enrichments[{i}]"
        for key in ("id", "entity_id", "property", "value", "evidence_kind",
                    "prompt_template_id", "source_observations", "confidence",
                    "provenance"):
            if key not in enr:
                r.issues.append(Issue("error", artifact, where,
                                      f"missing required enrichment field: {key}",
                                      "enrichment-required"))
        # evidence_kind must be 'inferred'
        if enr.get("evidence_kind") != "inferred":
            r.issues.append(Issue("error", artifact, f"{where}.evidence_kind",
                                  "enrichment evidence_kind must be 'inferred'",
                                  "enrichment-evidence-kind"))
        # entity_id pattern
        r.issues.extend(_check_id_pattern(enr.get("entity_id"), artifact, f"{where}.entity_id"))
        # confidence range
        conf = enr.get("confidence")
        if conf is not None and not (isinstance(conf, (int, float)) and 0.0 <= conf <= 1.0):
            r.issues.append(Issue("error", artifact, f"{where}.confidence",
                                  f"confidence must be in [0,1]; got {conf!r}",
                                  "confidence-range"))
        # source_observations is a list of strings
        srcs = enr.get("source_observations")
        if srcs is not None and not (isinstance(srcs, list) and all(isinstance(s, str) for s in srcs)):
            r.issues.append(Issue("error", artifact, f"{where}.source_observations",
                                  "source_observations must be an array of observation-id strings",
                                  "enrichment-source-shape"))
        # enrichment id uniqueness
        eid = enr.get("id")
        if isinstance(eid, str):
            if eid in seen_ids:
                r.issues.append(Issue("error", artifact, f"{where}.id",
                                      f"duplicate enrichment id: {eid}",
                                      "enrichment-unique-id"))
            else:
                seen_ids.add(eid)
        # provenance shape
        r.issues.extend(_check_provenance(enr.get("provenance"), artifact, where,
                                          "enrichment-provenance"))
    return r


def validate_observations(payload: dict, artifact: str) -> Report:
    r = Report(artifact=artifact)
    if "observations" not in payload:
        r.issues.append(Issue("error", artifact, "$", "no observations[] array", "envelope"))
        return r
    for i, obs in enumerate(payload["observations"]):
        where = f"observations[{i}]"
        for key in ("id", "kind", "evidence_kind", "rule_id", "provenance"):
            if key not in obs:
                r.issues.append(Issue("error", artifact, where,
                                      f"missing required observation field: {key}",
                                      "obs-required"))
        # llm_candidate must have prompt_template_id and category
        if obs.get("evidence_kind") == "llm_candidate":
            for key in ("prompt_template_id", "category"):
                if key not in obs:
                    r.issues.append(Issue("error", artifact, where,
                                          f"llm_candidate missing required field: {key}",
                                          "llm-candidate-required"))
        r.issues.extend(_check_rule_id(obs.get("rule_id"), artifact, f"{where}.rule_id"))
        r.issues.extend(_check_provenance(obs.get("provenance"), artifact, where,
                                          "obs-provenance"))
    return r


def validate_file(path: Path) -> Report:
    """Auto-detect artifact kind from top-level keys and validate."""
    data = json.loads(path.read_text())
    if "entities" in data:
        return validate_entities(data, str(path))
    if "edges" in data:
        return validate_edges(data, str(path))
    if "observations" in data:
        return validate_observations(data, str(path))
    if "enrichments" in data:
        return validate_enrichments(data, str(path))
    r = Report(artifact=str(path))
    r.issues.append(Issue("error", str(path), "$",
                          "could not detect artifact kind (no entities/edges/observations/enrichments key)",
                          "envelope"))
    return r


def main(paths: list[str]) -> int:
    rc = 0
    for p in paths:
        report = validate_file(Path(p))
        for issue in report.issues:
            line = f"[{issue.level.upper()}] {issue.artifact} {issue.where}: {issue.message} ({issue.rule})"
            print(line)
        status = "OK" if report.ok() else "FAIL"
        print(f"{p}: {status} ({len(report.errors)} errors, {len(report.warnings)} warnings)")
        if not report.ok():
            rc = 1
    return rc


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
