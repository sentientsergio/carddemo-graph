"""BMS Pass-1 deterministic extractor.

Implements RUL-BMS-* from `artifacts/deterministic_rules.md`.

BMS source is HLASM-format. Comment lines (col 1 = '*') were stripped. Continuation
is indicated by a non-blank char at column 72 (typically '-'), making the next line a
continuation. We fold continuation lines into a single logical statement before parsing.

Macros of interest:
  <name> DFHMSD operands...     — mapset definition (name in cols 1-8)
  <name> DFHMDI operands...     — map within mapset
  <name> DFHMDF operands...     — field within map (name optional; blank = filler)
"""

from __future__ import annotations

import re

from carddemo_graph.extract.observation import (
    Observation, ObservationSink, ProvenanceItem,
)
from carddemo_graph.extract.sources import SourceFile


# Header-name token: cols 1-N (alphanumeric), optional. Empty = filler.
_RE_BMS_STMT = re.compile(
    r"^(?P<name>\S*)\s+(?P<macro>DFHMSD|DFHMDI|DFHMDF)\b(?P<rest>.*)$",
    re.IGNORECASE,
)

# Operand patterns within the folded statement body
_RE_OP_INITIAL = re.compile(r"\bINITIAL\s*=\s*'([^']*)'", re.IGNORECASE)
_RE_OP_PROMPT = re.compile(r"\bPROMPT\s*=\s*'([^']*)'", re.IGNORECASE)
_RE_OP_LENGTH = re.compile(r"\bLENGTH\s*=\s*(\d+)", re.IGNORECASE)
_RE_OP_POS = re.compile(r"\bPOS\s*=\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)", re.IGNORECASE)
_RE_OP_LINE = re.compile(r"\bLINE\s*=\s*(\d+)", re.IGNORECASE)
_RE_OP_COLUMN = re.compile(r"\bCOLUMN\s*=\s*(\d+)", re.IGNORECASE)
_RE_OP_SIZE = re.compile(r"\bSIZE\s*=\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)", re.IGNORECASE)
_RE_OP_ATTRB = re.compile(r"\bATTRB\s*=\s*(?:\(([^)]+)\)|([A-Z]+))", re.IGNORECASE)
_RE_OP_COLOR = re.compile(r"\bCOLOR\s*=\s*([A-Z]+)", re.IGNORECASE)
_RE_OP_LANG = re.compile(r"\bLANG\s*=\s*([A-Z]+)", re.IGNORECASE)
_RE_OP_MODE = re.compile(r"\bMODE\s*=\s*([A-Z]+)", re.IGNORECASE)
_RE_OP_CTRL = re.compile(r"\bCTRL\s*=\s*\(([^)]+)\)", re.IGNORECASE)


def _fold_continuations(lines: list[str]) -> list[tuple[int, int, str]]:
    """Fold continuation lines (col-72 non-blank) into logical statements.

    Returns list of (start_line_1based, end_line_1based, folded_text).
    """
    out: list[tuple[int, int, str]] = []
    i = 0
    n = len(lines)
    while i < n:
        start_line = i + 1
        parts = [lines[i]]
        # Continuation iff col-72 (index 71) is non-blank in the current line.
        # If the line is shorter than 72 chars, no continuation.
        while True:
            cur = parts[-1]
            if len(cur) > 71 and cur[71] != " ":
                # consume next line
                if i + 1 < n:
                    i += 1
                    parts.append(lines[i])
                    continue
            break
        # When folding, strip the column-72 continuation marker from each part
        # except the last; concatenate cleanly.
        folded_parts = []
        for k, p in enumerate(parts):
            if k < len(parts) - 1 and len(p) > 71:
                folded_parts.append(p[:71].rstrip())
            else:
                folded_parts.append(p.rstrip())
        out.append((start_line, i + 1, " ".join(folded_parts)))
        i += 1
    return out


class BmsExtractor:
    def __init__(self, source: SourceFile, sink: ObservationSink):
        self.src = source
        self.sink = sink
        self.lines = source.lines
        self.src_id = source.record.id
        self.src_hash = source.record.source_hash
        self.src_path = source.record.path
        self.current_mapset: str | None = None
        self.current_map: str | None = None
        self.filler_counter: int = 0

    def _prov(self, s: int, e: int, snippet: str | None = None,
              role: str | None = None) -> list[ProvenanceItem]:
        if snippet is None:
            snippet = "\n".join(self.lines[s - 1:e])
        return [ProvenanceItem(
            source_path=self.src_path, start_line=s, end_line=e,
            snippet=snippet, role=role,
            source_file_id=self.src_id, source_hash=self.src_hash,
        )]

    def _emit(self, *, kind: str, rule_id: str, data: dict,
              start_line: int, end_line: int, role: str | None = None) -> None:
        self.sink.add(Observation(
            id=self.sink.next_id(), kind=kind, evidence_kind="deterministic",
            rule_id=rule_id, provenance=self._prov(start_line, end_line, role=role),
            data=data,
        ))

    def extract(self) -> None:
        for s, e, text in _fold_continuations(self.lines):
            m = _RE_BMS_STMT.match(text)
            if not m:
                continue
            name = m.group("name").upper()
            macro = m.group("macro").upper()
            rest = m.group("rest")
            if macro == "DFHMSD":
                self._handle_mapset(name, rest, s, e)
            elif macro == "DFHMDI":
                self._handle_map(name, rest, s, e)
            elif macro == "DFHMDF":
                self._handle_field(name, rest, s, e)

    def _handle_mapset(self, name: str, rest: str, s: int, e: int) -> None:
        if not name:
            return
        self.current_mapset = name
        self.current_map = None
        self.filler_counter = 0
        props = {}
        if (m := _RE_OP_LANG.search(rest)): props["lang"] = m.group(1).upper()
        if (m := _RE_OP_MODE.search(rest)): props["mode"] = m.group(1).upper()
        if (m := _RE_OP_CTRL.search(rest)): props["ctrl"] = m.group(1).strip()
        self._emit(
            kind="entity_candidate", rule_id="RUL-BMS-001",
            data={
                "entity_type": "BMSMapset",
                "name": name,
                "id_candidate": f"bms-mapset:{name}",
                **props,
            },
            start_line=s, end_line=e, role="declaration",
        )

    def _handle_map(self, name: str, rest: str, s: int, e: int) -> None:
        if not name or not self.current_mapset:
            return
        self.current_map = name
        self.filler_counter = 0
        props = {}
        if (m := _RE_OP_LINE.search(rest)): props["line_pos"] = int(m.group(1))
        if (m := _RE_OP_COLUMN.search(rest)): props["column_pos"] = int(m.group(1))
        if (m := _RE_OP_SIZE.search(rest)):
            props["size_rows"] = int(m.group(1))
            props["size_cols"] = int(m.group(2))
        self._emit(
            kind="entity_candidate", rule_id="RUL-BMS-002",
            data={
                "entity_type": "BMSMap",
                "name": name,
                "id_candidate": f"bms-map:{self.current_mapset}/{name}",
                "mapset_id": f"bms-mapset:{self.current_mapset}",
                **props,
            },
            start_line=s, end_line=e, role="declaration",
        )

    def _handle_field(self, name: str, rest: str, s: int, e: int) -> None:
        if not self.current_mapset or not self.current_map:
            return
        is_filler = not bool(name)
        if is_filler:
            self.filler_counter += 1
            field_name = f"FILLER_{self.filler_counter}"
        else:
            field_name = name
        props = {"is_filler": is_filler}
        if (m := _RE_OP_POS.search(rest)):
            props["pos_row"] = int(m.group(1))
            props["pos_col"] = int(m.group(2))
        if (m := _RE_OP_LENGTH.search(rest)):
            props["length"] = int(m.group(1))
        if (m := _RE_OP_ATTRB.search(rest)):
            props["attrb"] = (m.group(1) or m.group(2) or "").strip()
        if (m := _RE_OP_COLOR.search(rest)):
            props["color"] = m.group(1).upper()
        if (m := _RE_OP_INITIAL.search(rest)):
            props["initial_value"] = m.group(1)
            props["label"] = m.group(1)
        if (m := _RE_OP_PROMPT.search(rest)):
            props["prompt_value"] = m.group(1)
            if "label" not in props:
                props["label"] = m.group(1)
        if "label" not in props:
            props["label"] = ""
        self._emit(
            kind="entity_candidate", rule_id="RUL-BMS-003",
            data={
                "entity_type": "BMSField",
                "name": field_name,
                "id_candidate": f"bms-field:{self.current_mapset}/{self.current_map}/{field_name}",
                "map_id": f"bms-map:{self.current_mapset}/{self.current_map}",
                "mapset_id": f"bms-mapset:{self.current_mapset}",
                **props,
            },
            start_line=s, end_line=e, role="declaration",
        )


def extract_bms(source: SourceFile, sink: ObservationSink) -> None:
    BmsExtractor(source, sink).extract()
