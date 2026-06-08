"""CSD (DFHCSDUP / CEDA) Pass-1 deterministic extractor.

Implements RUL-CSD-* from `artifacts/deterministic_rules.md`.

CSD syntax (free-form): each resource definition is a block beginning with
` DEFINE <type>(<name>) ...` and continues across lines until the next top-level
DEFINE. Operands are key(value) pairs. Comments are stripped (HLASM-format,
col-1 '*').
"""

from __future__ import annotations

import re

from carddemo_graph.extract.observation import (
    Observation, ObservationSink, ProvenanceItem,
)
from carddemo_graph.extract.sources import SourceFile


_RE_DEFINE_HEAD = re.compile(
    r"^\s*DEFINE\s+(?P<type>TRANSACTION|PROGRAM|MAPSET|FILE|TYPETERM|TDQUEUE|TSMODEL|LIBRARY|GROUP|LIST)"
    r"\s*\(\s*(?P<name>[A-Z0-9.&_$#@-]+)\s*\)",
    re.IGNORECASE,
)
_RE_PROGRAM_OP = re.compile(r"\bPROGRAM\s*\(\s*([A-Z0-9_$#@-]+)\s*\)", re.IGNORECASE)
_RE_DSNAME_OP = re.compile(r"\bDSNAME\s*\(\s*([^)]+?)\s*\)", re.IGNORECASE)
_RE_DESCRIPTION_OP = re.compile(r"\bDESCRIPTION\s*\(\s*([^)]+?)\s*\)", re.IGNORECASE)
_RE_GROUP_OP = re.compile(r"\bGROUP\s*\(\s*([A-Z0-9_$#@-]+)\s*\)", re.IGNORECASE)


def _split_define_blocks(lines: list[str]) -> list[tuple[int, int, str]]:
    """Group CSD lines into DEFINE-blocks.

    Returns list of (start_line_1based, end_line_1based, joined_text).
    """
    blocks: list[tuple[int, int, str]] = []
    cur_start: int | None = None
    cur_lines: list[str] = []
    for i, raw in enumerate(lines, start=1):
        if _RE_DEFINE_HEAD.match(raw):
            if cur_start is not None and cur_lines:
                blocks.append((cur_start, i - 1, " ".join(cur_lines)))
            cur_start = i
            cur_lines = [raw]
        else:
            if cur_start is not None:
                cur_lines.append(raw)
    if cur_start is not None and cur_lines:
        blocks.append((cur_start, len(lines), " ".join(cur_lines)))
    return blocks


class CsdExtractor:
    def __init__(self, source: SourceFile, sink: ObservationSink):
        self.src = source
        self.sink = sink
        self.lines = source.lines
        self.src_id = source.record.id
        self.src_hash = source.record.source_hash
        self.src_path = source.record.path

    def _prov(self, s: int, e: int, role: str | None = None) -> list[ProvenanceItem]:
        snippet = "\n".join(self.lines[s - 1:min(e, s + 2)])  # cap snippet to ~3 lines
        return [ProvenanceItem(
            source_path=self.src_path, start_line=s, end_line=e,
            snippet=snippet, role=role,
            source_file_id=self.src_id, source_hash=self.src_hash,
        )]

    def _emit(self, *, kind: str, rule_id: str, data: dict,
              s: int, e: int, role: str | None = None) -> None:
        self.sink.add(Observation(
            id=self.sink.next_id(), kind=kind, evidence_kind="deterministic",
            rule_id=rule_id, provenance=self._prov(s, e, role),
            data=data,
        ))

    def extract(self) -> None:
        for s, e, text in _split_define_blocks(self.lines):
            m = _RE_DEFINE_HEAD.match(self.lines[s - 1])
            if not m:
                continue
            rtype = m.group("type").upper()
            name = m.group("name").upper()
            if rtype == "TRANSACTION":
                self._handle_transaction(name, text, s, e)
            elif rtype == "PROGRAM":
                self._handle_program(name, text, s, e)
            elif rtype == "MAPSET":
                self._handle_mapset(name, text, s, e)
            elif rtype == "FILE":
                self._handle_file(name, text, s, e)
            # GROUP/LIST/TYPETERM/etc.: informational, not modeled in v1

    def _handle_transaction(self, tranid: str, text: str, s: int, e: int) -> None:
        m_pgm = _RE_PROGRAM_OP.search(text)
        m_desc = _RE_DESCRIPTION_OP.search(text)
        self._emit(
            kind="entity_candidate", rule_id="RUL-CSD-001",
            data={
                "entity_type": "CICSTransaction",
                "name": tranid,
                "id_candidate": f"transaction:{tranid}",
                "description": m_desc.group(1) if m_desc else None,
            },
            s=s, e=e, role="declaration",
        )
        if m_pgm:
            pgm = m_pgm.group(1).upper()
            self._emit(
                kind="edge_candidate", rule_id="RUL-CSD-001",
                data={
                    "edge_type": "IS_TRANSACTION_FOR",
                    "from": f"transaction:{tranid}",
                    "to_candidate": f"program:{pgm}",
                },
                s=s, e=e, role="binding",
            )

    def _handle_program(self, name: str, text: str, s: int, e: int) -> None:
        self._emit(
            kind="entity_candidate", rule_id="RUL-CSD-002",
            data={
                "entity_type": "Program",
                "name": name,
                "id_candidate": f"program:{name}",
                "csd_only_until_resolved": True,  # Pass 3 sets partial:true if no source body
            },
            s=s, e=e, role="declaration",
        )

    def _handle_mapset(self, name: str, text: str, s: int, e: int) -> None:
        self._emit(
            kind="entity_candidate", rule_id="RUL-CSD-003",
            data={
                "entity_type": "BMSMapset",
                "name": name,
                "id_candidate": f"bms-mapset:{name}",
                "csd_confirmed": True,
            },
            s=s, e=e, role="declaration",
        )

    def _handle_file(self, file_name: str, text: str, s: int, e: int) -> None:
        m_dsn = _RE_DSNAME_OP.search(text)
        if not m_dsn:
            # CSD FILE without DSNAME: still emit but flag as partial
            self._emit(
                kind="entity_candidate", rule_id="RUL-CSD-004",
                data={
                    "entity_type": "LogicalFile",
                    "name": file_name,
                    "id_candidate": f"logical-file:CSD/{file_name}",
                    "scope": "cics",
                    "binding_source": "CSD",
                    "csd_dsname_missing": True,
                },
                s=s, e=e, role="declaration",
            )
            return
        dsn = m_dsn.group(1).strip()
        # Emit Dataset entity
        self._emit(
            kind="entity_candidate", rule_id="RUL-CSD-004",
            data={
                "entity_type": "Dataset",
                "name": dsn,
                "id_candidate": f"dataset:{dsn}",
            },
            s=s, e=e, role="declaration",
        )
        # Pass 3 will create LogicalFile entities (one per program × csd-file usage)
        # plus emit BINDS_TO edges. For Pass 1, emit a binding hint that Pass 3 uses:
        self._emit(
            kind="property_observation", rule_id="RUL-CSD-004",
            data={
                "binding_kind": "csd_file_to_dataset",
                "cics_file_name": file_name,
                "dataset_id": f"dataset:{dsn}",
            },
            s=s, e=e, role="binding-hint",
        )


def extract_csd(source: SourceFile, sink: ObservationSink) -> None:
    CsdExtractor(source, sink).extract()
