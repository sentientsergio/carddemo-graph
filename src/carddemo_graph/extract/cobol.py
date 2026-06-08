"""COBOL Pass-1 deterministic extractor.

Implements rules RUL-COBOL-* from `artifacts/deterministic_rules.md`.
Works against the comment-stripped CardDemo source — column 7 indicator is gone,
columns 1-6 (sequence) and 73-80 (identification) are preserved but ignored here.

Strategy: line-oriented scanning with section state. Multi-line constructs
(EXEC CICS ... END-EXEC, multi-line COPY ... REPLACING ..., multi-line PROGRAM-ID)
are folded into single logical statements before matching.
"""

from __future__ import annotations

import re
from typing import Iterator

from carddemo_graph.extract.observation import (
    Observation, ObservationSink, ProvenanceItem,
)
from carddemo_graph.extract.sources import SourceFile, cobol_code_text


# Section markers
_RE_FILE_CONTROL_START = re.compile(r"\bFILE-CONTROL\b\s*\.?", re.IGNORECASE)
_RE_INPUT_OUTPUT_SECTION = re.compile(r"\bINPUT-OUTPUT\s+SECTION\b", re.IGNORECASE)
_RE_DATA_DIVISION = re.compile(r"\bDATA\s+DIVISION\b", re.IGNORECASE)
_RE_PROCEDURE_DIVISION = re.compile(r"\bPROCEDURE\s+DIVISION\b", re.IGNORECASE)
_RE_FILE_SECTION = re.compile(r"\bFILE\s+SECTION\b", re.IGNORECASE)
_RE_WORKING_STORAGE = re.compile(r"\bWORKING-STORAGE\s+SECTION\b", re.IGNORECASE)
_RE_LINKAGE_SECTION = re.compile(r"\bLINKAGE\s+SECTION\b", re.IGNORECASE)

# Program-ID
_RE_PROGRAM_ID = re.compile(r"\bPROGRAM-ID\b\s*\.?\s*(?P<name>[A-Z][A-Z0-9-]*)?\s*\.?",
                            re.IGNORECASE)

# COPY (handles plain, quoted, REPLACING terminated by period)
_RE_COPY_HEAD = re.compile(
    r"^\s*COPY\s+(?:'([A-Z][A-Z0-9-]*)'|\"([A-Z][A-Z0-9-]*)\"|([A-Z][A-Z0-9-]*))"
    r"(?P<rest>.*?)\.\s*$",
    re.IGNORECASE | re.DOTALL,
)

# Standalone copy-line (when we don't see period yet — multi-line copy)
_RE_COPY_BEGIN = re.compile(
    r"^\s*COPY\s+(?:'([A-Z][A-Z0-9-]*)'|\"([A-Z][A-Z0-9-]*)\"|([A-Z][A-Z0-9-]*))",
    re.IGNORECASE,
)

# SELECT / ASSIGN / ORGANIZATION / ACCESS MODE / RECORD KEY / ALTERNATE RECORD KEY
_RE_SELECT = re.compile(r"\bSELECT\s+(?P<lf>[A-Z][A-Z0-9-]*)", re.IGNORECASE)
_RE_ASSIGN = re.compile(r"\bASSIGN\s+(?:TO\s+)?(?P<dd>[A-Z][A-Z0-9-]*)", re.IGNORECASE)
_RE_ORG = re.compile(r"\bORGANIZATION\s+(?:IS\s+)?(?P<org>INDEXED|SEQUENTIAL|RELATIVE|LINE\s+SEQUENTIAL)",
                     re.IGNORECASE)
_RE_ACCESS = re.compile(r"\bACCESS\s+MODE\s+(?:IS\s+)?(?P<mode>SEQUENTIAL|RANDOM|DYNAMIC)",
                        re.IGNORECASE)
_RE_RECORD_KEY = re.compile(r"\bRECORD\s+KEY\s+(?:IS\s+)?(?P<key>[A-Z][A-Z0-9-]*)",
                            re.IGNORECASE)
_RE_ALT_RECORD_KEY = re.compile(
    r"\bALTERNATE\s+RECORD\s+KEY\s+(?:IS\s+)?(?P<key>[A-Z][A-Z0-9-]*)",
    re.IGNORECASE,
)

# FD / SD
_RE_FD = re.compile(r"^\s*FD\s+(?P<fd>[A-Z][A-Z0-9-]*)", re.IGNORECASE)
_RE_SD = re.compile(r"^\s*SD\s+(?P<sd>[A-Z][A-Z0-9-]*)", re.IGNORECASE)

# 01-level record start
_RE_01 = re.compile(r"^\s*01\s+(?P<rec>[A-Z][A-Z0-9-]*)", re.IGNORECASE)
_RE_02_PLUS = re.compile(r"^\s*(?P<level>02|03|04|05|06|07|08|10|15|20|49)\s+", re.IGNORECASE)

# CALL (literal vs identifier)
_RE_CALL_LITERAL = re.compile(
    r"\bCALL\s+(?:'([A-Z][A-Z0-9-]*)'|\"([A-Z][A-Z0-9-]*)\")",
    re.IGNORECASE,
)
_RE_CALL_IDENT = re.compile(
    r"\bCALL\s+(?P<id>[A-Z][A-Z0-9-]*)\b(?!\s*[\'\"])",
    re.IGNORECASE,
)

def _strip_string_literals(code: str) -> str:
    """Replace COBOL string literals (single or double quoted) with placeholder space.

    Prevents false positives like `DISPLAY 'START OF EXECUTION ...'` matching the
    `START <name>` batch-I/O regex.
    """
    # Single-quoted strings
    code = re.sub(r"'[^']*'", lambda m: " " * len(m.group(0)), code)
    # Double-quoted strings
    code = re.sub(r'"[^"]*"', lambda m: " " * len(m.group(0)), code)
    return code


# Batch I/O verbs against a logical-file or record name
_RE_READ = re.compile(r"\bREAD\s+(?P<lf>[A-Z][A-Z0-9-]*)\b", re.IGNORECASE)
_RE_WRITE = re.compile(r"\bWRITE\s+(?P<rec>[A-Z][A-Z0-9-]*)\b", re.IGNORECASE)
_RE_REWRITE = re.compile(r"\bREWRITE\s+(?P<rec>[A-Z][A-Z0-9-]*)\b", re.IGNORECASE)
_RE_DELETE = re.compile(r"\bDELETE\s+(?P<lf>[A-Z][A-Z0-9-]*)\b", re.IGNORECASE)
_RE_START = re.compile(r"\bSTART\s+(?P<lf>[A-Z][A-Z0-9-]*)\b", re.IGNORECASE)

# EXEC CICS block — match full block end-to-end
_RE_EXEC_CICS_BLOCK = re.compile(
    r"EXEC\s+CICS\s+(?P<verb>[A-Z]+)(?P<body>.*?)END-EXEC",
    re.IGNORECASE | re.DOTALL,
)

# EXEC CICS operands (within a matched block body).
# CRITICAL: distinguish literal-quoted from identifier-form PROGRAM operands.
# Per the project's skeleton/enrichment directive: literal `PROGRAM('NAME')` is deductive
# and produces a typed edge (LINKS_TO / XCTLS_TO → program:NAME); identifier
# `PROGRAM(WS-VAR)` requires MOVE-chain analysis to resolve, so it must stay
# Unresolved with breadcrumb (parallel to dynamic CALL handling in RUL-COBOL-012).
_RE_PROGRAM_OP_LITERAL = re.compile(
    r"\bPROGRAM\s*\(\s*['\"](?P<v>[A-Z][A-Z0-9-]*)['\"]\s*\)",
    re.IGNORECASE,
)
_RE_PROGRAM_OP_IDENT = re.compile(
    r"\bPROGRAM\s*\(\s*(?P<v>[A-Z][A-Z0-9-]*)\s*\)",
    re.IGNORECASE,
)
_RE_TRANSID_OP = re.compile(r"\bTRANSID\s*\(\s*'?(?P<v>[A-Z0-9]+)'?\s*\)", re.IGNORECASE)
_RE_MAP_OP = re.compile(r"\bMAP\s*\(\s*'?(?P<v>[A-Z][A-Z0-9-]*)'?\s*\)", re.IGNORECASE)
_RE_MAPSET_OP = re.compile(r"\bMAPSET\s*\(\s*'?(?P<v>[A-Z][A-Z0-9-]*)'?\s*\)", re.IGNORECASE)
_RE_FILE_OP = re.compile(r"\b(?:FILE|DATASET)\s*\(\s*'?(?P<v>[A-Z][A-Z0-9-]*)'?\s*\)", re.IGNORECASE)

# Working-storage literal constants: pattern
#   <level> NAME PIC X(N) VALUE 'literal'.
# Capture for constant propagation when CICS file operands reference a WS identifier.
_RE_WS_CONSTANT = re.compile(
    r"^\s*(?:\d+)\s+(?P<name>[A-Z][A-Z0-9-]*)\s+"
    r"PIC[A-Z]?\s+X\(\s*\d+\s*\)\s+VALUE\s+['\"](?P<val>[^'\"]+)['\"]\s*\.",
    re.IGNORECASE,
)

# --- Data-description entry parsing (RUL-COBOL-021/022; v2.2 KU-9) ---
# A logical entry (after period-termination accumulation) begins with a level
# number + a data-name (or FILLER). Clauses (PIC/USAGE/OCCURS/REDEFINES) follow in
# COBOL's conventional order; parsed with targeted sub-patterns rather than one
# monolithic regex.
_RE_DATA_LEVEL = re.compile(
    r"^(?P<level>\d{1,2})\s+(?P<name>FILLER|[A-Z][A-Z0-9-]*)\b", re.IGNORECASE)
_RE_PIC = re.compile(r"\bPIC(?:TURE)?\s+(?:IS\s+)?(?P<pic>[-A-Z0-9()V$S.,/]+)", re.IGNORECASE)
_RE_OCCURS = re.compile(r"\bOCCURS\s+(?P<n>\d+)", re.IGNORECASE)
_RE_REDEFINES = re.compile(r"\bREDEFINES\s+(?P<tgt>[A-Z][A-Z0-9-]*)", re.IGNORECASE)
_RE_USAGE = re.compile(
    r"\b(?:USAGE\s+(?:IS\s+)?)?(COMP-3|COMPUTATIONAL-3|PACKED-DECIMAL|"
    r"COMP-4|COMPUTATIONAL-4|COMP-5|COMPUTATIONAL-5|COMP|COMPUTATIONAL|"
    r"BINARY|DISPLAY)\b", re.IGNORECASE)

_USAGE_NORMALIZE = {
    "COMPUTATIONAL-3": "COMP-3", "PACKED-DECIMAL": "COMP-3",
    "COMPUTATIONAL-4": "COMP-4", "COMPUTATIONAL-5": "COMP-5",
    "COMPUTATIONAL": "COMP",
}
_COMP_BINARY_USAGES = {"COMP", "COMP-4", "COMP-5", "BINARY"}


def _normalize_usage(u: str) -> str:
    u = u.upper()
    return _USAGE_NORMALIZE.get(u, u)


def _count_symbol(pic_part: str, sym: str) -> int:
    """Count occurrences of a PIC symbol, expanding `<sym>(n)` repeat factors."""
    total = 0
    for m in re.finditer(rf"{re.escape(sym)}\((\d+)\)", pic_part):
        total += int(m.group(1))
    stripped = re.sub(rf"{re.escape(sym)}\(\d+\)", "", pic_part)
    total += stripped.count(sym)
    return total


def _count_digit_positions(pic_part: str) -> int:
    """Digit positions in a (possibly edited) numeric PIC part: 9, Z (zero-suppress),
    and * (check-protect) all occupy one digit each; (n) repeat factors expand."""
    return sum(_count_symbol(pic_part, s) for s in ("9", "Z", "*"))


def _suggested_sql_type(picture: str | None, usage: str | None) -> str | None:
    """RUL-DERIV: advisory Aurora/Postgres column type from PIC + USAGE.

    Deterministic rule-table — NOT authoritative DDL (downstream decides). Handles
    raw numerics (9/S/V), alphanumeric (X/A), and numeric-edited pictures
    (Z zero-suppress, * check-protect, '.' edited decimal, insertion ',' '/' 'B' and
    sign chars '- + CR DB' ignored). COMP/binary integer split is by explicit digit
    count (<=9 INTEGER, <=18 BIGINT). Exotic floating-insertion currency pics ($$$)
    are not specially handled (none in this corpus).
    """
    if not picture:
        return None
    p = picture.upper()
    has_digit_pos = any(ch in p for ch in ("9", "Z", "*"))
    # alphanumeric / alphabetic: X/A with no numeric digit positions
    if ("X" in p or "A" in p) and not has_digit_pos:
        n = _count_symbol(p, "X") + _count_symbol(p, "A")
        return f"CHAR({n})" if n else "CHAR"
    # numeric (raw or edited): strip sign + insertion chars; split on V or edited '.'
    body = p
    for tok in ("CR", "DB"):
        body = body.replace(tok, "")
    body = (body.replace("S", "").replace("+", "").replace("-", "")
                .replace(",", "").replace("/", "").replace("B", "").replace("$", ""))
    if "V" in body:
        int_part, _, dec_part = body.partition("V")
    elif "." in body:
        int_part, _, dec_part = body.partition(".")
    else:
        int_part, dec_part = body, ""
    int_digits = _count_digit_positions(int_part)
    dec_digits = _count_digit_positions(dec_part)
    if int_digits == 0 and dec_digits == 0:
        return None  # not a recognizable numeric PIC
    if dec_digits == 0:
        if usage in _COMP_BINARY_USAGES:
            return "INTEGER" if int_digits <= 9 else ("BIGINT" if int_digits <= 18
                                                      else f"NUMERIC({int_digits})")
        return f"NUMERIC({int_digits})"
    return f"NUMERIC({int_digits + dec_digits},{dec_digits})"


# Mapping CICS verb → (edge_type, role) tuples
_CICS_FILE_VERBS = {
    "READ":       ("READS",         "CICS_READ"),
    "WRITE":      ("WRITES",        "CICS_WRITE"),
    "REWRITE":    ("UPDATES",       "CICS_REWRITE"),
    "DELETE":     ("DELETES",       "CICS_DELETE"),
    "STARTBR":    ("STARTS_BROWSE", "CICS_STARTBR"),
    "READNEXT":   ("READS",         "CICS_READNEXT"),
    "READPREV":   ("READS",         "CICS_READPREV"),
}


class CobolExtractor:
    """Stateful per-file COBOL extractor. One instance per source file."""

    def __init__(self, source: SourceFile, sink: ObservationSink,
                 *, current_source_role: str = "program"):
        self.src = source
        self.sink = sink
        # 'program' for .cbl / .CBL; 'copybook' for .cpy / .CPY
        self.source_role = (
            "copybook"
            if source.path.suffix in (".cpy", ".CPY") or "/cpy" in str(source.path)
            else "program"
        )
        # Section state
        self.in_file_control = False
        self.in_file_section = False
        self.in_working_storage = False
        self.in_linkage = False
        self.in_procedure = False
        # SELECT/FD tracking
        self.current_select: dict | None = None     # collected SELECT block
        self.selects: dict[str, dict] = {}          # lf_name -> {dd, organization, access, record_key, ...}
        self.fd_to_records: dict[str, list[str]] = {}  # fd_name -> [01-record-names]
        self.record_to_fd: dict[str, str] = {}      # record name -> fd name
        self.current_fd: str | None = None
        self.current_record: str | None = None
        # Program identity
        self.program_name: str | None = None
        self.program_decl_lines: tuple[int, int] | None = None
        # Working-storage literal-constant table (for CICS operand resolution)
        self.ws_constants: dict[str, str] = {}
        # Convenience for snippets
        self.lines = source.lines
        self.src_id = source.record.id
        self.src_hash = source.record.source_hash
        self.src_path = source.record.path

    # -------------------------- top-level --------------------------

    def extract(self) -> None:
        """Drive the extraction pass over the source file."""
        self._scan_program_id()
        self._scan_ws_constants()
        self._scan_data_items()
        self._scan_sections_and_statements()

    def _scan_data_items(self) -> None:
        """RUL-COBOL-021: parse copybook data-description entries into DataItem
        entity_candidates + parent/child hierarchy (CONTAINS_ITEM) + record-root
        (HAS_FIELD) edges. v2.2 KU-9 scope: copybooks (where record layouts live).

        Multi-line entries are accumulated to the period terminator (same discipline
        as _scan_ws_constants). 88-level condition names are deferred to the KU9 stretch
        seam (not emitted here). OCCURS/REDEFINES are captured as facts only.
        """
        if self.source_role != "copybook":
            return
        # Scope: file/data record layouts in app/cpy/. Exclude BMS-generated symbolic
        # maps in app/cpy-bms/ — those are screen-field structures already modeled as
        # BMSField entities (modeling them again as DataItems would double-count and
        # isn't the KU-9 goal of record-layout-> Aurora-DDL).
        if "cpy-bms" in str(self.src.path).lower():
            return
        cb = self.src.path.stem.upper()
        cb_id = f"copybook:{cb}"
        stack: list[tuple[int, str]] = []   # (level, dataitem_id) ancestor chain
        buf = ""
        buf_start = 0
        filler_seq = 0
        for i, raw in enumerate(self.lines, start=1):
            code = cobol_code_text(raw).strip()
            if not code:
                continue
            if not buf:
                buf_start = i
            buf = f"{buf} {code}" if buf else code
            if not code.endswith("."):
                continue
            entry = buf.rstrip(".").strip()
            buf = ""
            m = _RE_DATA_LEVEL.match(entry)
            if not m:
                continue
            level = int(m.group("level"))
            name = m.group("name").upper()
            if level == 88:
                continue  # condition names: KU9 stretch seam, not core
            # Pop ancestors at the same-or-deeper level; remaining top is the parent.
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent_id = stack[-1][1] if stack else None
            if name == "FILLER":
                filler_seq += 1
                item_id = f"dataitem:{cb}/FILLER#{filler_seq}"
            else:
                item_id = f"dataitem:{cb}/{name}"
            pic = (_RE_PIC.search(entry).group("pic") if _RE_PIC.search(entry) else None)
            # REDEFINES/OCCURS tokens can sit before PIC; usage after. Strip a leading
            # REDEFINES target out of PIC false-matches by parsing fields independently.
            mu = _RE_USAGE.search(entry)
            usage = _normalize_usage(mu.group(1)) if mu else None
            mo = _RE_OCCURS.search(entry)
            occurs = int(mo.group("n")) if mo else None
            mr = _RE_REDEFINES.search(entry)
            redefines = mr.group("tgt").upper() if mr else None
            is_group = pic is None
            data = {
                "entity_type": "DataItem",
                "name": name,
                "id_candidate": item_id,
                "level": level,
                "picture": pic,
                "usage": usage or (None if is_group else "DISPLAY"),
                "occurs": occurs,
                "redefines": redefines,
                "is_filler": name == "FILLER",
                "is_group": is_group,
                "suggested_sql_type": None if is_group else _suggested_sql_type(pic, usage),
                "parent_item": parent_id,
                "copybook_id": cb_id,
            }
            self._emit(self._make_obs(
                kind="entity_candidate", rule_id="RUL-COBOL-021",
                data=data, start_line=buf_start, end_line=i, role="declaration"))
            if parent_id is None:
                self._emit(self._make_obs(
                    kind="edge_candidate", rule_id="RUL-COBOL-021",
                    data={"edge_type": "HAS_FIELD", "from": cb_id, "to_candidate": item_id},
                    start_line=buf_start, end_line=i, role="use-site"))
            else:
                self._emit(self._make_obs(
                    kind="edge_candidate", rule_id="RUL-COBOL-021",
                    data={"edge_type": "CONTAINS_ITEM", "from": parent_id,
                          "to_candidate": item_id},
                    start_line=buf_start, end_line=i, role="use-site"))
            stack.append((level, item_id))

    def _scan_ws_constants(self) -> None:
        """Build the WORKING-STORAGE literal-constant table.

        Captures the narrow form `<level> NAME PIC X(N) VALUE 'literal'.` within
        WORKING-STORAGE SECTION, including the common two-line layout where the
        `VALUE` clause continues on the next physical line:

            05 LIT-ACCTFILENAME    PIC X(8)
                                   VALUE 'ACCTDAT '.

        Physical lines are accumulated into one logical data-description entry
        (terminated by a period) before matching, so continuation lines resolve.
        Used by CICS-verb handlers to resolve identifier-form FILE/DATASET operands
        like `DATASET(WS-USRSEC-FILE)`.

        Constant propagation is intentionally narrow: only literal VALUE in WS,
        no MOVE-target tracking, no nested IF. Anything beyond this falls to Pass 2.
        """
        markers = self._scan_section_boundaries()
        buf = ""
        for i, raw in enumerate(self.lines, start=1):
            if not self._in_section(i, markers, ("WORKING-STORAGE",),
                                    exit_on=("LINKAGE", "PROCEDURE DIVISION")):
                buf = ""
                continue
            code = cobol_code_text(raw).strip()
            if not code:
                continue
            buf = f"{buf} {code}" if buf else code
            if not code.endswith("."):
                continue        # data-description entry continues on the next line
            m = _RE_WS_CONSTANT.match(buf)
            if m:
                name = m.group("name").upper()
                val = m.group("val").rstrip()
                self.ws_constants[name] = val
            buf = ""

    # -------------------------- helpers ----------------------------

    def _prov(self, start_line: int, end_line: int | None = None,
              snippet: str | None = None, role: str | None = None) -> list[ProvenanceItem]:
        if end_line is None:
            end_line = start_line
        if snippet is None:
            snip_lines = self.lines[start_line - 1:end_line]
            snippet = "\n".join(snip_lines)
        return [ProvenanceItem(
            source_path=self.src_path,
            start_line=start_line,
            end_line=end_line,
            snippet=snippet,
            role=role,
            source_file_id=self.src_id,
            source_hash=self.src_hash,
        )]

    def _emit(self, obs: Observation) -> None:
        self.sink.add(obs)

    def _make_obs(self, *, kind: str, rule_id: str, data: dict,
                  start_line: int, end_line: int | None = None,
                  snippet: str | None = None, role: str | None = None) -> Observation:
        return Observation(
            id=self.sink.next_id(),
            kind=kind,
            evidence_kind="deterministic",
            rule_id=rule_id,
            provenance=self._prov(start_line, end_line, snippet, role),
            data=data,
        )

    # -------------------------- PROGRAM-ID -------------------------

    def _scan_program_id(self) -> None:
        """RUL-COBOL-001 — handle both same-line and multi-line PROGRAM-ID."""
        for i, raw_line in enumerate(self.lines, start=1):
            code = cobol_code_text(raw_line)
            if not code:
                continue
            m = re.search(r"\bPROGRAM-ID\b", code, re.IGNORECASE)
            if not m:
                continue
            # Try same-line form first
            same_line = re.search(
                r"\bPROGRAM-ID\b\s*\.?\s*(?P<name>[A-Z][A-Z0-9-]*)\s*\.",
                code, re.IGNORECASE,
            )
            if same_line:
                self.program_name = same_line.group("name").upper()
                self.program_decl_lines = (i, i)
                break
            # Multi-line: name appears on a following non-blank line, terminated by period
            for j in range(i + 1, min(i + 8, len(self.lines) + 1)):
                next_code = cobol_code_text(self.lines[j - 1])
                if not next_code.strip():
                    continue
                m2 = re.match(r"^\s*(?P<name>[A-Z][A-Z0-9-]*)\s*\.", next_code, re.IGNORECASE)
                if m2:
                    self.program_name = m2.group("name").upper()
                    self.program_decl_lines = (i, j)
                    break
            break
        if self.program_name and self.source_role == "program":
            start, end = self.program_decl_lines
            self._emit(self._make_obs(
                kind="entity_candidate",
                rule_id="RUL-COBOL-001",
                data={
                    "entity_type": "Program",
                    "name": self.program_name,
                    "id_candidate": f"program:{self.program_name}",
                    "filename_match": self.program_name == self.src.path.stem.upper(),
                },
                start_line=start,
                end_line=end,
                role="declaration",
            ))
        elif self.source_role == "copybook":
            # Emit a Copybook entity_candidate with file-presence provenance.
            # Without this, Pass 3 only sees copybooks as INCLUDES-edge targets and
            # materializes them as `partial: true`. With it, the copybook's body
            # provenance lands on the entity and `partial` flips to false.
            cb_name = self.src.path.stem.upper()
            self._emit(self._make_obs(
                kind="entity_candidate",
                rule_id="RUL-COBOL-002",
                data={
                    "entity_type": "Copybook",
                    "name": cb_name,
                    "id_candidate": f"copybook:{cb_name}",
                },
                start_line=1,
                end_line=1,
                role="file-presence",
            ))

    # -------------------------- sections & statements --------------

    def _scan_sections_and_statements(self) -> None:
        i = 1
        n = len(self.lines)
        # First, do a single linear pass for section markers
        section_starts = self._scan_section_boundaries()
        # Then walk, processing each line in its section context
        while i <= n:
            raw_line = self.lines[i - 1]
            code = cobol_code_text(raw_line)
            in_ws_or_linkage = self._in_section(i, section_starts,
                                                ("WORKING-STORAGE", "LINKAGE"))
            in_fc = self._in_section(i, section_starts, ("FILE-CONTROL",),
                                     exit_on=("FILE SECTION", "DATA DIVISION",
                                              "PROCEDURE DIVISION"))
            in_file_section = self._in_section(i, section_starts, ("FILE SECTION",),
                                               exit_on=("WORKING-STORAGE", "LINKAGE",
                                                        "PROCEDURE DIVISION"))
            in_procedure = self._in_section(i, section_starts, ("PROCEDURE DIVISION",))

            # FD tracking
            mfd = _RE_FD.match(code)
            if mfd and in_file_section:
                self.current_fd = mfd.group("fd").upper()
                self.fd_to_records.setdefault(self.current_fd, [])
                self.current_record = None
                i += 1
                continue
            msd = _RE_SD.match(code)
            if msd and in_file_section:
                self.current_fd = None
                self.current_record = None
                i += 1
                continue

            # 01-level record in FD context
            m01 = _RE_01.match(code)
            if m01 and in_file_section and self.current_fd:
                rec = m01.group("rec").upper()
                self.fd_to_records[self.current_fd].append(rec)
                self.record_to_fd[rec] = self.current_fd
                self.current_record = rec
                i += 1
                continue

            # COPY (anywhere): RUL-COBOL-002 / 003 / 004 / 020
            # Try a "logical-statement" view: join lines from i until we see a period terminator
            # (within reasonable window).
            if _RE_COPY_BEGIN.search(code):
                end_idx = self._consume_through_period(i, max_lines=10)
                stmt = self._logical_statement(i, end_idx)
                handled = self._handle_copy(stmt, i, end_idx, in_file_section=in_file_section,
                                            in_fd_record_area=self.current_fd is not None and self.current_record is not None)
                if handled:
                    i = end_idx + 1
                    continue

            # FILE-CONTROL section: parse SELECT block
            if in_fc:
                msel = _RE_SELECT.search(code)
                if msel and self.source_role == "program":
                    # Accumulate the SELECT block until next SELECT or end of section
                    self._absorb_select(i)
                # advance regardless — _absorb_select consumed forward through next SELECT
                # but here we just step by 1 since absorbed view doesn't change i
                i += 1
                continue

            # PROCEDURE DIVISION: scan statements
            if in_procedure and self.source_role == "program":
                # CALL literal
                mlit = _RE_CALL_LITERAL.search(code)
                if mlit:
                    target = (mlit.group(1) or mlit.group(2)).upper()
                    self._emit(self._make_obs(
                        kind="edge_candidate",
                        rule_id="RUL-COBOL-011",
                        data={
                            "edge_type": "CALLS",
                            "from": f"program:{self.program_name}" if self.program_name else "program:UNKNOWN",
                            "to_candidate": f"program:{target}",
                            "call_kind": "static",
                        },
                        start_line=i,
                        role="use-site",
                    ))
                else:
                    # CALL identifier — only if no literal matched and this is a real CALL
                    mid = _RE_CALL_IDENT.search(code)
                    if mid:
                        ident = mid.group("id").upper()
                        # Skip false positives: CALL not followed by identifier syntax
                        if ident not in ("USING",):
                            self._emit(self._make_obs(
                                kind="edge_candidate",
                                rule_id="RUL-COBOL-012",
                                data={
                                    "edge_type": "CALLS",
                                    "from": f"program:{self.program_name}" if self.program_name else "program:UNKNOWN",
                                    "to_candidate": f"unresolved:{ident}",
                                    "call_kind": "dynamic",
                                    "breadcrumb": ident,
                                },
                                start_line=i,
                                role="use-site",
                            ))

                # Batch I/O verbs (only when not within EXEC CICS — check below)
                self._maybe_batch_io(code, i)

            # EXEC CICS block handling — look forward for END-EXEC
            if "EXEC" in code.upper() and "CICS" in code.upper():
                # find block end
                end_idx = self._consume_through_token(i, "END-EXEC", max_lines=30)
                stmt = self._logical_statement(i, end_idx)
                self._handle_cics_block(stmt, i, end_idx)
                i = end_idx + 1
                continue

            i += 1

    # -------------------------- section boundaries -----------------

    def _scan_section_boundaries(self) -> list[tuple[int, str]]:
        """Return list of (line_no, section_name) for section markers."""
        markers: list[tuple[int, str]] = []
        for i, raw in enumerate(self.lines, start=1):
            code = cobol_code_text(raw)
            if _RE_FILE_CONTROL_START.search(code):
                markers.append((i, "FILE-CONTROL"))
            if _RE_FILE_SECTION.search(code):
                markers.append((i, "FILE SECTION"))
            if _RE_WORKING_STORAGE.search(code):
                markers.append((i, "WORKING-STORAGE"))
            if _RE_LINKAGE_SECTION.search(code):
                markers.append((i, "LINKAGE"))
            if _RE_PROCEDURE_DIVISION.search(code):
                markers.append((i, "PROCEDURE DIVISION"))
            if _RE_DATA_DIVISION.search(code):
                markers.append((i, "DATA DIVISION"))
        return markers

    def _in_section(self, line_no: int, markers: list[tuple[int, str]],
                    names: tuple[str, ...],
                    *, exit_on: tuple[str, ...] = ()) -> bool:
        """Is `line_no` inside any section named in `names`?"""
        current = None
        for m_line, m_name in markers:
            if m_line > line_no:
                break
            current = m_name
        if current is None:
            return False
        if current in names:
            return True
        if exit_on and current in exit_on:
            return False
        return current in names

    # -------------------------- multi-line helpers -----------------

    def _consume_through_period(self, start: int, max_lines: int = 10) -> int:
        for j in range(start, min(start + max_lines, len(self.lines)) + 1):
            code = cobol_code_text(self.lines[j - 1] if j <= len(self.lines) else "")
            if code.rstrip().endswith("."):
                return j
        return start  # fallback

    def _consume_through_token(self, start: int, token: str,
                               max_lines: int = 30) -> int:
        end_line_max = min(start + max_lines, len(self.lines))
        for j in range(start, end_line_max + 1):
            code = cobol_code_text(self.lines[j - 1] if j <= len(self.lines) else "")
            if token.upper() in code.upper():
                return j
        return start

    def _logical_statement(self, start: int, end: int) -> str:
        return " ".join(cobol_code_text(self.lines[j - 1]).strip()
                        for j in range(start, end + 1)
                        if 1 <= j <= len(self.lines))

    # -------------------------- COPY handling ----------------------

    def _handle_copy(self, stmt: str, start: int, end: int,
                     *, in_file_section: bool, in_fd_record_area: bool) -> bool:
        m_full = _RE_COPY_HEAD.match(stmt)
        if not m_full:
            # Fallback: match just the begin form to extract target name
            mbeg = _RE_COPY_BEGIN.match(stmt)
            if not mbeg:
                return False
            target = (mbeg.group(1) or mbeg.group(2) or mbeg.group(3)).upper()
            replacing = None
        else:
            target = (m_full.group(1) or m_full.group(2) or m_full.group(3)).upper()
            rest = m_full.group("rest") or ""
            replacing = self._parse_replacing(rest) if "REPLACING" in rest.upper() else None

        from_id = self._self_id()
        if from_id is None:
            return False  # no PROGRAM-ID context — skip silently
        # FD-context COPY?
        fd_context = in_fd_record_area
        rule_id = "RUL-COBOL-003" if replacing else (
            "RUL-COBOL-004" if fd_context else
            ("RUL-COBOL-020" if self.source_role == "copybook" else "RUL-COBOL-002")
        )
        edge_obs = self._make_obs(
            kind="edge_candidate",
            rule_id=rule_id,
            data={
                "edge_type": "INCLUDES",
                "from": from_id,
                "to_candidate": f"copybook:{target}",
                "fd_context": fd_context,
                "replacing_terms": replacing,
            },
            start_line=start,
            end_line=end,
            role="use-site",
        )
        self._emit(edge_obs)
        if fd_context and self.current_fd:
            # Also emit DEFINES_LAYOUT_FOR observation
            if self.program_name:
                lf_id = f"logical-file:{self.program_name}/{self.current_fd}"
                self._emit(self._make_obs(
                    kind="edge_candidate",
                    rule_id="RUL-COBOL-004",
                    data={
                        "edge_type": "DEFINES_LAYOUT_FOR",
                        "from": f"copybook:{target}",
                        "to_candidate": lf_id,
                    },
                    start_line=start,
                    end_line=end,
                    role="fd-context",
                ))
        return True

    def _parse_replacing(self, rest: str) -> list[dict]:
        """Best-effort parse of REPLACING ... BY ... terms. Returns list of dicts."""
        terms = []
        # Pattern: ==X== BY ==Y== or LEADING/TRAILING qualifiers
        for m in re.finditer(
            r"(?:(LEADING|TRAILING)\s+)?(=+[^=]+=+|'[^']+'|\"[^\"]+\")\s+BY\s+"
            r"(=+[^=]+=+|'[^']+'|\"[^\"]+\")",
            rest, re.IGNORECASE | re.DOTALL,
        ):
            terms.append({
                "qualifier": (m.group(1) or "").upper() or None,
                "find": m.group(2).strip(),
                "by": m.group(3).strip(),
            })
        return terms or [{"raw": rest.strip()}]

    def _self_id(self) -> str | None:
        if self.source_role == "program" and self.program_name:
            return f"program:{self.program_name}"
        if self.source_role == "copybook":
            return f"copybook:{self.src.path.stem.upper()}"
        return None

    # -------------------------- SELECT/FILE-CONTROL ----------------

    def _absorb_select(self, line_no: int) -> None:
        """Collect a SELECT block (up to next SELECT or section end)."""
        end = line_no
        for j in range(line_no, len(self.lines) + 1):
            code = cobol_code_text(self.lines[j - 1])
            if code.rstrip().endswith("."):
                end = j
                break
            end = j
        stmt = self._logical_statement(line_no, end)
        msel = _RE_SELECT.search(stmt)
        if not msel:
            return
        lf = msel.group("lf").upper()
        m_assign = _RE_ASSIGN.search(stmt)
        m_org = _RE_ORG.search(stmt)
        m_access = _RE_ACCESS.search(stmt)
        m_rec = _RE_RECORD_KEY.search(stmt)
        m_alt = list(_RE_ALT_RECORD_KEY.finditer(stmt))
        dd = m_assign.group("dd").upper() if m_assign else None
        org = m_org.group("org").upper().replace(" ", "_") if m_org else None
        access = m_access.group("mode").upper() if m_access else None
        rec_key = m_rec.group("key").upper() if m_rec else None
        alt_keys = [a.group("key").upper() for a in m_alt]

        self.selects[lf] = {
            "dd": dd, "organization": org, "access_mode": access,
            "record_key": rec_key, "alternate_record_keys": alt_keys,
        }
        # entity candidate: LogicalFile
        if self.program_name:
            lf_id = f"logical-file:{self.program_name}/{lf}"
            self._emit(self._make_obs(
                kind="entity_candidate",
                rule_id="RUL-COBOL-005",
                data={
                    "entity_type": "LogicalFile",
                    "name": lf,
                    "id_candidate": lf_id,
                    "program_id": f"program:{self.program_name}",
                    "scope": "batch",
                    "assign_dd": dd,
                    "organization": org,
                    "access_mode": access,
                    "record_key": rec_key,
                    "alternate_record_keys": alt_keys,
                },
                start_line=line_no,
                end_line=end,
                role="declaration",
            ))
            # edge candidate: DECLARES_FILE
            self._emit(self._make_obs(
                kind="edge_candidate",
                rule_id="RUL-COBOL-005",
                data={
                    "edge_type": "DECLARES_FILE",
                    "from": f"program:{self.program_name}",
                    "to_candidate": lf_id,
                },
                start_line=line_no,
                end_line=end,
                role="declaration",
            ))

    # -------------------------- batch I/O --------------------------

    def _maybe_batch_io(self, code: str, line_no: int) -> None:
        if not self.program_name:
            return
        from_id = f"program:{self.program_name}"
        # Strip string literals to prevent false positives from DISPLAY/MOVE statements
        # whose string contents contain verb-like words ("START OF...", "READ THE...").
        code = _strip_string_literals(code)

        m = _RE_READ.search(code)
        if m and not re.search(r"\bEXEC\s+CICS", code, re.IGNORECASE):
            self._emit_batch_io("READS", "RUL-COBOL-006", from_id,
                                m.group("lf").upper(), line_no, "COBOL_READ")
            return

        m = _RE_WRITE.search(code)
        if m and not re.search(r"\bEXEC\s+CICS", code, re.IGNORECASE):
            # Map record name back to logical file via FD
            rec = m.group("rec").upper()
            lf = self.record_to_fd.get(rec, rec)  # fallback to rec if no FD mapping
            self._emit_batch_io("WRITES", "RUL-COBOL-007", from_id, lf, line_no, "COBOL_WRITE")
            return

        m = _RE_REWRITE.search(code)
        if m and not re.search(r"\bEXEC\s+CICS", code, re.IGNORECASE):
            rec = m.group("rec").upper()
            lf = self.record_to_fd.get(rec, rec)
            self._emit_batch_io("UPDATES", "RUL-COBOL-008", from_id, lf, line_no, "COBOL_REWRITE")
            return

        m = _RE_DELETE.search(code)
        if m and not re.search(r"\bEXEC\s+CICS", code, re.IGNORECASE):
            self._emit_batch_io("DELETES", "RUL-COBOL-009", from_id,
                                m.group("lf").upper(), line_no, "COBOL_DELETE")
            return

        m = _RE_START.search(code)
        if m and not re.search(r"\bEXEC\s+CICS", code, re.IGNORECASE):
            self._emit_batch_io("STARTS_BROWSE", "RUL-COBOL-010", from_id,
                                m.group("lf").upper(), line_no, "COBOL_START")
            return

    def _emit_batch_io(self, edge_type: str, rule_id: str, from_id: str,
                       lf_name: str, line_no: int, access_form: str) -> None:
        lf_id = f"logical-file:{self.program_name}/{lf_name}"
        self._emit(self._make_obs(
            kind="edge_candidate",
            rule_id=rule_id,
            data={
                "edge_type": edge_type,
                "from": from_id,
                "to_candidate": lf_id,
                "access_form": access_form,
            },
            start_line=line_no,
            role="use-site",
        ))

    # -------------------------- EXEC CICS --------------------------

    def _handle_cics_program_op(self, body: str, edge_type: str, rule_id: str,
                                from_id: str, start: int, end: int) -> None:
        """Resolve EXEC CICS LINK/XCTL PROGRAM(...) operand.

        Literal-quoted form (`PROGRAM('NAME')`) → typed edge to program:NAME (deductive).
        Identifier form (`PROGRAM(WS-VAR)`) → edge to unresolved:<IDENTIFIER> with
        breadcrumb. Per the project's directive: MOVE-chain identifier-form XCTL/LINK targets
        stay Unresolved; Pass 2 may annotate; never promoted to typed edge.
        """
        m_lit = _RE_PROGRAM_OP_LITERAL.search(body)
        if m_lit:
            self._emit(self._make_obs(
                kind="edge_candidate", rule_id=rule_id,
                data={"edge_type": edge_type, "from": from_id,
                      "to_candidate": f"program:{m_lit.group('v').upper()}",
                      "call_kind": "static"},
                start_line=start, end_line=end, role="use-site",
            ))
            return
        m_id = _RE_PROGRAM_OP_IDENT.search(body)
        if m_id:
            ident = m_id.group("v").upper()
            self._emit(self._make_obs(
                kind="edge_candidate", rule_id=rule_id,
                data={"edge_type": edge_type, "from": from_id,
                      "to_candidate": f"unresolved:{ident}",
                      "call_kind": "dynamic",
                      "breadcrumb": ident,
                      "must_not_promote": True},
                start_line=start, end_line=end, role="use-site",
            ))

    def _handle_cics_block(self, stmt: str, start: int, end: int) -> None:
        m = _RE_EXEC_CICS_BLOCK.search(stmt)
        if not m:
            return  # malformed — not parseable in deterministic pass
        verb = m.group("verb").upper()
        body = m.group("body")
        from_id = f"program:{self.program_name}" if self.program_name else "program:UNKNOWN"

        if verb == "LINK":
            self._handle_cics_program_op(body, "LINKS_TO", "RUL-COBOL-013",
                                         from_id, start, end)
        elif verb == "XCTL":
            self._handle_cics_program_op(body, "XCTLS_TO", "RUL-COBOL-014",
                                         from_id, start, end)
        elif verb == "RETURN":
            m_tr = _RE_TRANSID_OP.search(body)
            if m_tr:
                self._emit(self._make_obs(
                    kind="edge_candidate", rule_id="RUL-COBOL-015",
                    data={"edge_type": "RETURNS_TO_TRANSID", "from": from_id,
                          "to_candidate": f"transaction:{m_tr.group('v').upper()}"},
                    start_line=start, end_line=end, role="use-site",
                ))
        elif verb == "SEND":
            m_map = _RE_MAP_OP.search(body)
            m_mset = _RE_MAPSET_OP.search(body)
            if m_map:
                mapname = m_map.group("v").upper()
                mapset = m_mset.group("v").upper() if m_mset else None
                to_id = (f"bms-map:{mapset}/{mapname}" if mapset
                         else f"bms-map:UNKNOWN/{mapname}")
                self._emit(self._make_obs(
                    kind="edge_candidate", rule_id="RUL-COBOL-016",
                    data={"edge_type": "SENDS_MAP", "from": from_id,
                          "to_candidate": to_id, "mapset_op": mapset, "map_op": mapname},
                    start_line=start, end_line=end, role="use-site",
                ))
        elif verb == "RECEIVE":
            m_map = _RE_MAP_OP.search(body)
            m_mset = _RE_MAPSET_OP.search(body)
            if m_map:
                mapname = m_map.group("v").upper()
                mapset = m_mset.group("v").upper() if m_mset else None
                to_id = (f"bms-map:{mapset}/{mapname}" if mapset
                         else f"bms-map:UNKNOWN/{mapname}")
                self._emit(self._make_obs(
                    kind="edge_candidate", rule_id="RUL-COBOL-017",
                    data={"edge_type": "RECEIVES_MAP", "from": from_id,
                          "to_candidate": to_id, "mapset_op": mapset, "map_op": mapname},
                    start_line=start, end_line=end, role="use-site",
                ))
        elif verb in _CICS_FILE_VERBS:
            edge_type, access_form = _CICS_FILE_VERBS[verb]
            m_file = _RE_FILE_OP.search(body)
            if m_file and self.program_name:
                operand = m_file.group("v").upper()
                # Constant propagation: if operand is a WS variable bound to a literal,
                # resolve to the literal. Otherwise emit edge with unresolved-id form.
                resolved = self.ws_constants.get(operand)
                if resolved:
                    fname = resolved.upper()
                    operand_kind = "ws_constant"
                else:
                    fname = operand
                    operand_kind = "literal" if not operand.startswith("WS-") else "ws_unresolved"
                lf_id = f"logical-file:{self.program_name}/{fname}"
                obs_data = {
                    "edge_type": edge_type, "from": from_id,
                    "to_candidate": lf_id, "access_form": access_form,
                    "scope_hint": "cics",
                    "operand_kind": operand_kind,
                    "operand_surface": operand,
                }
                if operand_kind == "ws_unresolved":
                    # Still emit the edge but flag it: Pass 2 may improve resolution.
                    obs_data["needs_pass2"] = True
                self._emit(self._make_obs(
                    kind="edge_candidate", rule_id="RUL-COBOL-018",
                    data=obs_data,
                    start_line=start, end_line=end, role="use-site",
                ))


def extract_cobol(source: SourceFile, sink: ObservationSink) -> None:
    """Entry point: extract one COBOL source file (.cbl / .cpy) into sink."""
    CobolExtractor(source, sink).extract()
