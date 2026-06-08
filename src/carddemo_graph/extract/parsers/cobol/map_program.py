"""Map seam (COBOL program layer) — MAPA CallTree + parse tree → program-construct
Observations, emitting the **existing, unchanged** RUL-COBOL contract.

This is the step-3 counterpart to `map_dataitem` (the data layer). Where the data
layer walks a standalone copybook's parse tree 1:1, the program layer is harder: MAPA's
`CobolParser` requires preprocessed input, so program constructs (CALL / EXEC CICS /
SELECT / I/O verbs) are read from the fully COPY-expanded `-saveTemp` top temp, whose
line numbers are *preprocessed* coordinates. We recover original source/copybook lines
through the proven, content-validated `ProgramConstructResolver` (see
`program_provenance.py`). Every emitted construct's provenance line is resolver-validated
or we FAIL LOUD — a silently-wrong edge is impossible by construction.

Two operand surfaces, per the emission-surface findings (RESUME §3):
- **Structured by the grammar** — file-control (`fileControlEntry` + select/assign/org/
  access/record-key clauses) and CALL/CICS verb *classification* (CallTree CSV). These we
  read from the tree / CSV: the foundation's value is using the standard, not regex.
- **NOT structured by the grammar** — EXEC CICS *operands* (MAPA tokenizes CICS innards
  character-by-character) and dynamic-call/identifier-XCTL breadcrumbs. For those, the
  grammar gives the *block boundary* (the execCicsStatement line) and we extract the
  operand with the existing keyword-paren patterns from the grammar-delimited source
  block — the documented boundary (next to continuation-folding). The construct LINE is
  content-validated and fail-loud (via ProgramConstructResolver); the OPERAND itself is
  taken from the first keyword-paren match WITHOUT operand-level content-validation or
  fail-loud-on-ambiguity — that hardening is deferred to Phase-3 (see RESUME §3). Do not
  read this as "operand content-validated".

No CardDemo-specific handling lives here (the anti-pattern): the only corpus-shaped
assumption is the source-tree *layout* (programs in `…/cbl`, copybooks in sibling
`…/cpy[ -bms]`), which is filesystem convention, flagged here, not language semantics.

Build order (incremental, each validated at facts-parity vs the regex extractor before
the Phase-2 gate): file-control + program-id [this commit] → CALL + COPY/INCLUDES →
batch I/O → structured CICS + CICSOTHER. Until all are at parity the adapter keeps
delegating programs to the regex path (no partial-emission breakage).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from carddemo_graph.extract.observation import (
    Observation, ObservationSink, ProvenanceItem,
)
from carddemo_graph.extract.sources import SourceFile, cobol_code_text
# COPY is a preprocessor directive with no representation in the COPY-expanded grammar
# tree (MAPA consumes it; the CSV over-reports transitive expansions; the per-pass
# .origin chain is the known dead-end). Its analysis is irreducibly lexical-on-source in
# any grammar tool, and the directive's own source line IS its provenance — no
# preprocessing remap. So the COPY scan reuses the FROZEN module-level patterns from the
# regex baseline (the documented keyword-level boundary), re-derived here as an
# independent walk and proven byte-parity across the full corpus by the emission harness.
from carddemo_graph.extract.cobol import (
    _RE_COPY_BEGIN, _RE_COPY_HEAD, _RE_FD, _RE_SD, _RE_01,
    _RE_FILE_SECTION, _RE_WORKING_STORAGE, _RE_LINKAGE_SECTION,
    _RE_PROCEDURE_DIVISION, _RE_DATA_DIVISION, _RE_FILE_CONTROL_START,
    # EXEC CICS operands: MAPA tokenizes CICS innards character-by-character, so operand
    # extraction is keyword-paren on the grammar-DELIMITED block (the documented boundary,
    # next to continuation-folding). These frozen patterns are reused verbatim; only the
    # block boundary comes from the grammar (the execCicsStatement node line).
    _RE_EXEC_CICS_BLOCK, _RE_PROGRAM_OP_LITERAL, _RE_PROGRAM_OP_IDENT,
    _RE_TRANSID_OP, _RE_MAP_OP, _RE_MAPSET_OP, _RE_FILE_OP, _RE_WS_CONSTANT,
    _CICS_FILE_VERBS,
)

from . import parse
from .program_provenance import ProgramConstructResolver, ConstructOrigin


# --- generic parse-tree helpers (rule names are COBOL-grammar, not corpus) ---

def _find_all(node, rule: str, out: list) -> None:
    if isinstance(node, dict):
        if node.get("r") == rule:
            out.append(node)
        for c in node.get("k", []):
            _find_all(c, rule, out)


def _first(node, rule: str) -> dict | None:
    hits: list = []
    _find_all(node, rule, hits)
    return hits[0] if hits else None


def _flat(node) -> list[str]:
    if isinstance(node, str):
        return [node]
    out: list[str] = []
    for c in node.get("k", []):
        out += _flat(c)
    return out


def _first_cobolword(node: dict | None) -> str | None:
    """The first `cobolWord` terminal under `node`, uppercased — the canonical way to
    pull an identifier operand out of a structured clause."""
    if node is None:
        return None
    cw = _first(node, "cobolWord")
    if cw is None:
        return None
    toks = [t for t in _flat(cw) if t.strip()]
    return toks[0].upper() if toks else None


# --- CallTree CSV ---

class CallTreeCsv:
    """Parsed CallTree CSV rows for one program (see parse.call_tree).

    Row vocabulary (comma-separated; field[0] is the row type):
    - PGM,<uuid>,<file-uuid>,<NAME>,<stats…>
    - CALL,<uuid>,<pgm-uuid>,<PGM>,<CALLTYPE>,<TARGET>   (CALLTYPE ∈ CALLBYLITERAL /
      CICSLINK / CICSXCTL / CICSXCTLBYIDENTIFIER / …)
    - DD,<uuid>,<pgm-uuid>,<DDNAME>,<LOGICAL-FILE>,<read>,<write>,<update>,<?>
    - CICS<OP>,<uuid>,<pgm-uuid>,<FILE-OPERAND>   (resolved file ops)
    - COPY,<uuid>,<file-uuid>,<COPYBOOK>
    """

    def __init__(self, csv_text: str):
        self.rows: list[list[str]] = [
            line.split(",") for line in csv_text.splitlines() if line.strip()
        ]

    def of_type(self, t: str) -> list[list[str]]:
        return [r for r in self.rows if r and r[0] == t]

    def program_name(self) -> str | None:
        pgm = self.of_type("PGM")
        return pgm[0][3].upper() if pgm and len(pgm[0]) > 3 else None


# --- emission ---

def _emit(sink: ObservationSink, *, kind: str, rule_id: str, data: dict,
          origin: ConstructOrigin, src: SourceFile,
          program_lines: list[str], end_line: int | None = None,
          role: str) -> None:
    """Emit one Observation with resolver-validated provenance.

    Provenance lands on the originating file (the program, or — for a copybook-origin
    construct — the spliced copybook). The snippet/role/source-file fields mirror the
    regex extractor's `_make_obs` so the Observation shape is byte-identical.
    """
    start_line = origin.line
    end = end_line if end_line is not None else start_line
    if origin.kind == "program":
        # Match the regex extractor exactly: it sources `source_path` from
        # `record.path` (the path string gate3/pilot registered), NOT a re-resolved
        # absolute path — so provenance strings compare equal in the Phase-2 diff.
        source_path = src.record.path
        snippet = "\n".join(program_lines[start_line - 1:end])
    else:
        # Copybook-origin construct (e.g. a CALL inside a PROCEDURE copybook) — the
        # regex path never sees these, so there is no parity baseline; provenance is the
        # copybook's own path/line (an improvement, documented). Pass-3 keys by
        # source_path; the program's source-file id/hash carry the emitting context.
        source_path = origin.source_path
        snippet = _copybook_snippet(origin.source_path, start_line, end)
    source_file_id = src.record.id
    source_hash = src.record.source_hash
    prov = [ProvenanceItem(
        source_path=source_path,
        start_line=start_line,
        end_line=end,
        snippet=snippet,
        role=role,
        source_file_id=source_file_id,
        source_hash=source_hash,
    )]
    sink.add(Observation(
        id=sink.next_id(),
        kind=kind,
        evidence_kind="deterministic",
        rule_id=rule_id,
        provenance=prov,
        data=data,
    ))


def _copybook_snippet(path: str, start: int, end: int) -> str:
    try:
        lines = Path(path).read_text(encoding="latin-1").split("\n")
    except OSError:
        return ""
    return "\n".join(lines[start - 1:end])


# --- the program emitter ---

def emit_program(src: SourceFile, sink: ObservationSink,
                 *, copy_dirs: list[Path] | None = None,
                 workdir: Path | None = None) -> None:
    """Emit program-construct Observations for one COBOL program via MAPA.

    `copy_dirs` defaults to the sibling `cpy` / `cpy-bms` directories (source-tree
    layout convention). `workdir` defaults to a fresh temp dir (CallTree `-saveTemp`
    + the copybook harness live here; caller may pass one to retain artifacts).
    """
    program_path = Path(src.path).resolve()
    if copy_dirs is None:
        copy_dirs = _sibling_copy_dirs(program_path)
    work = workdir or Path(tempfile.mkdtemp(prefix="mapa-prog-"))
    harness = _build_harness(copy_dirs, work / "cpy")

    ct = parse.call_tree(program_path, harness, work)
    tree = parse.parse_temp_tree(ct.top_temp)
    csv = CallTreeCsv(ct.csv_text)
    resolver = ProgramConstructResolver(
        tempdir=ct.tempdir, program_stem=ct.program_stem,
        program_source=program_path, top_temp=ct.top_temp, copy_dir=harness)

    program_name = csv.program_name() or program_path.stem.upper()
    lines = src.lines
    ctx = _Ctx(src=src, sink=sink, tree=tree, csv=csv, resolver=resolver,
               program_name=program_name, program_lines=lines,
               program_path=str(program_path))

    # Resolution-order safety: every tree-anchored construct we emit is resolved here,
    # ONCE, in ascending top-temp line order — so the resolver's document-order woc
    # consumption (popleft per identical content) can never desync, regardless of the
    # order the rule emitters run in. Emitters then read the validated origin from the
    # cache. A content-validation failure on any construct raises here (fail-loud), which
    # is the intended posture: refuse the whole program rather than emit a wrong edge.
    ctx.preresolve(_ANCHORED_RULES)

    _emit_program_id(ctx)
    _emit_file_control(ctx)
    _emit_calls(ctx)
    _emit_copy_includes(ctx)
    _emit_batch_io(ctx)
    _emit_cics(ctx)


# Tree rule-names whose nodes carry a construct line we resolve to source provenance.
# Grows as mappers are added (execCicsStatement next).
_ANCHORED_RULES = ("programIdParagraph", "fileControlEntry", "callStatement",
                   "readStatement", "writeStatement", "rewriteStatement",
                   "deleteStatement", "startStatement", "execCicsStatement")


class _Ctx:
    """Shared per-program emission context (keeps the rule emitters small)."""

    def __init__(self, *, src, sink, tree, csv, resolver, program_name,
                 program_lines, program_path):
        self.src = src
        self.sink = sink
        self.tree = tree
        self.csv = csv
        self.resolver = resolver
        self.program_name = program_name
        self.program_lines = program_lines
        self.program_path = program_path
        self._origin: dict[int, ConstructOrigin] = {}  # id(node) -> origin

    @property
    def from_id(self) -> str:
        return f"program:{self.program_name}"

    def preresolve(self, rules: tuple[str, ...]) -> None:
        """Resolve every node of the given tree rules, in ascending top-temp line order,
        into the origin cache. Single ordered pass = no woc-queue desync."""
        nodes: list[dict] = []
        for rule in rules:
            _find_all(self.tree, rule, nodes)
        for node in sorted(nodes, key=lambda n: int(n["ln"])):
            self._origin[id(node)] = self.resolver.resolve(int(node["ln"]))

    def origin_of(self, node: dict) -> ConstructOrigin:
        o = self._origin.get(id(node))
        if o is None:  # not pre-resolved (rule not in _ANCHORED_RULES) — resolve now
            o = self.resolver.resolve(int(node["ln"]))
            self._origin[id(node)] = o
        return o


# --- RUL-COBOL-001: PROGRAM-ID ---

def _emit_program_id(ctx: _Ctx) -> None:
    node = _first(ctx.tree, "programIdParagraph")
    if node is None:
        return
    name = _first_cobolword(_first(node, "programName")) or ctx.program_name
    origin = ctx.origin_of(node)
    stem_upper = Path(ctx.program_path).stem.upper()
    _emit(ctx.sink, kind="entity_candidate", rule_id="RUL-COBOL-001",
          data={
              "entity_type": "Program",
              "name": name,
              "id_candidate": f"program:{name}",
              "filename_match": name == stem_upper,
          },
          origin=origin, src=ctx.src, program_lines=ctx.program_lines,
          role="declaration")


# --- RUL-COBOL-005: FILE-CONTROL (SELECT) ---

def _emit_file_control(ctx: _Ctx) -> None:
    entries: list[dict] = []
    _find_all(ctx.tree, "fileControlEntry", entries)
    entries.sort(key=lambda n: int(n["ln"]))
    for fce in entries:
        lf = _first_cobolword(_first(fce, "selectClause"))
        if not lf:
            continue
        dd = _first_cobolword(_first(fce, "assignClause"))
        org = _clause_keyword(_first(fce, "organizationClause"),
                              ("INDEXED", "SEQUENTIAL", "RELATIVE", "LINE SEQUENTIAL"))
        access = _clause_keyword(_first(fce, "accessModeClause"),
                                 ("SEQUENTIAL", "RANDOM", "DYNAMIC"))
        rec_key = _first_cobolword(_first(fce, "recordKeyClause"))
        alt_nodes: list[dict] = []
        _find_all(fce, "alternateRecordKeyClause", alt_nodes)
        alt_keys = [k for k in (_first_cobolword(a) for a in alt_nodes) if k]

        origin = ctx.origin_of(fce)
        lf_id = f"logical-file:{ctx.program_name}/{lf}"
        _emit(ctx.sink, kind="entity_candidate", rule_id="RUL-COBOL-005",
              data={
                  "entity_type": "LogicalFile",
                  "name": lf,
                  "id_candidate": lf_id,
                  "program_id": ctx.from_id,
                  "scope": "batch",
                  "assign_dd": dd,
                  "organization": org,
                  "access_mode": access,
                  "record_key": rec_key,
                  "alternate_record_keys": alt_keys,
              },
              origin=origin, src=ctx.src, program_lines=ctx.program_lines,
              role="declaration")
        _emit(ctx.sink, kind="edge_candidate", rule_id="RUL-COBOL-005",
              data={
                  "edge_type": "DECLARES_FILE",
                  "from": ctx.from_id,
                  "to_candidate": lf_id,
              },
              origin=origin, src=ctx.src, program_lines=ctx.program_lines,
              role="declaration")


# --- RUL-COBOL-011 (static) / RUL-COBOL-012 (dynamic): CALL ---

def _emit_calls(ctx: _Ctx) -> None:
    """COBOL `CALL` statements from the tree (literal → static program:, identifier →
    dynamic unresolved:+breadcrumb). The line resolves through the validated origin
    cache; a CALL that lives in a PROCEDURE copybook resolves to copybook provenance —
    the regex extractor never scans copybook bodies, so those surface as documented
    three-way-diff *improvements*, carrying copybook provenance.

    NB: the CardDemo corpus has zero dynamic CALLs (all 14 CALL-bearing programs use the
    literal form), so the RUL-COBOL-012 branch is implemented for generalization but is
    corpus-unexercised — the same honesty caveat as the continuation-line boundary.
    """
    calls: list[dict] = []
    _find_all(ctx.tree, "callStatement", calls)
    calls.sort(key=lambda n: int(n["ln"]))
    for cs in calls:
        target, call_kind = _call_target(cs)
        if not target:
            continue  # a CALL form we cannot read a target from — emit nothing
        origin = ctx.origin_of(cs)
        if call_kind == "static":
            data = {"edge_type": "CALLS", "from": ctx.from_id,
                    "to_candidate": f"program:{target}", "call_kind": "static"}
            rule = "RUL-COBOL-011"
        else:
            data = {"edge_type": "CALLS", "from": ctx.from_id,
                    "to_candidate": f"unresolved:{target}", "call_kind": "dynamic",
                    "breadcrumb": target}
            rule = "RUL-COBOL-012"
        _emit(ctx.sink, kind="edge_candidate", rule_id=rule, data=data,
              origin=origin, src=ctx.src, program_lines=ctx.program_lines,
              role="use-site")


def _call_target(cs: dict) -> tuple[str | None, str | None]:
    """The CALL target = the first direct child before the USING phrase: a `literal`
    (static, quotes stripped) or an identifier (dynamic)."""
    for c in cs.get("k", []):
        if not isinstance(c, dict):
            continue
        r = c.get("r")
        if r == "literal":
            val = "".join(_flat(c)).strip().strip("'\"").upper()
            return (val or None), "static"
        if r in ("identifier", "generalIdentifier", "qualifiedDataName"):
            return _first_cobolword(c), "dynamic"
        if r == "callUsingPhrase":
            break  # target must precede USING; none found
    return None, None


# --- RUL-COBOL-006..010: batch (non-CICS) I/O ---

# tree I/O rule -> (edge_type, rule_id, access_form, operand_rule, operand_is_record)
_BATCH_IO = {
    "readStatement":    ("READS",         "RUL-COBOL-006", "COBOL_READ",    "fileName",   False),
    "writeStatement":   ("WRITES",        "RUL-COBOL-007", "COBOL_WRITE",   "recordName", True),
    "rewriteStatement": ("UPDATES",       "RUL-COBOL-008", "COBOL_REWRITE", "recordName", True),
    "deleteStatement":  ("DELETES",       "RUL-COBOL-009", "COBOL_DELETE",  "fileName",   False),
    "startStatement":   ("STARTS_BROWSE", "RUL-COBOL-010", "COBOL_START",   "fileName",   False),
}


def _emit_batch_io(ctx: _Ctx) -> None:
    """Native COBOL file I/O -> READS/WRITES/UPDATES/DELETES/STARTS_BROWSE, one edge per
    statement occurrence (line via the validated origin cache, document order). CICS file
    ops are `execCicsStatement` nodes, not these — so the grammar naturally excludes them
    (no literal-stripping heuristic needed, unlike the regex path). WRITE/REWRITE name a
    *record*, mapped to its logical file via the source-derived FD/01 map (mirrors regex
    `record_to_fd`, with the same fall-back-to-record-name behaviour)."""
    record_to_fd = _record_to_fd(ctx.program_lines)
    nodes: list[tuple[dict, str]] = []
    for rule in _BATCH_IO:
        hits: list[dict] = []
        _find_all(ctx.tree, rule, hits)
        nodes += [(n, rule) for n in hits]
    for node, rule in sorted(nodes, key=lambda nr: int(nr[0]["ln"])):
        edge_type, rule_id, access_form, operand_rule, is_record = _BATCH_IO[rule]
        operand = _first_cobolword(_first(node, operand_rule))
        if not operand:
            continue
        lf = record_to_fd.get(operand, operand) if is_record else operand
        origin = ctx.origin_of(node)
        _emit(ctx.sink, kind="edge_candidate", rule_id=rule_id,
              data={
                  "edge_type": edge_type,
                  "from": ctx.from_id,
                  "to_candidate": f"logical-file:{ctx.program_name}/{lf}",
                  "access_form": access_form,
              },
              origin=origin, src=ctx.src, program_lines=ctx.program_lines,
              role="use-site")


def _record_to_fd(lines: list[str]) -> dict[str, str]:
    """Map each FD's 01-record name -> the FD (logical-file) name, from the program's
    own FILE SECTION 01-lines in FD context — identical to the regex extractor's
    `record_to_fd`. Source-derived (not the COPY-expanded tree) so a record supplied by
    a COPY falls back to its own name exactly as the regex path does (parity-safe)."""
    markers = _section_markers(lines)
    rec_to_fd: dict[str, str] = {}
    current_fd: str | None = None
    for i, raw in enumerate(lines, 1):
        code = cobol_code_text(raw)
        in_file_section = _in_section(
            i, markers, ("FILE SECTION",),
            exit_on=("WORKING-STORAGE", "LINKAGE", "PROCEDURE DIVISION"))
        if not in_file_section:
            continue
        mfd = _RE_FD.match(code)
        if mfd:
            current_fd = mfd.group("fd").upper()
            continue
        if _RE_SD.match(code):
            current_fd = None
            continue
        m01 = _RE_01.match(code)
        if m01 and current_fd:
            rec_to_fd[m01.group("rec").upper()] = current_fd
    return rec_to_fd


# --- RUL-COBOL-013/014/015/016/017/018: EXEC CICS ---

def _emit_cics(ctx: _Ctx) -> None:
    """EXEC CICS constructs. The grammar gives the *block line* (execCicsStatement node,
    resolver-validated); the operands come from the keyword-paren patterns applied to the
    grammar-DELIMITED EXEC CICS…END-EXEC block reconstructed from source — MAPA tokenizes
    CICS innards char-by-char, so this is the documented keyword-level boundary, not a
    parse. Mirrors the regex `_handle_cics_block` exactly (LINK/XCTL → 013/014;
    RETURN-TRANSID → 015; SEND/RECEIVE-MAP → 016/017; file ops → 018 with WS-constant
    propagation). CICS in a PROCEDURE copybook resolves to copybook provenance (an
    improvement the regex never sees, like copybook-origin CALL)."""
    nodes: list[dict] = []
    _find_all(ctx.tree, "execCicsStatement", nodes)
    if not nodes:
        return
    ws_constants = _ws_constants(ctx.program_lines)
    for node in sorted(nodes, key=lambda n: int(n["ln"])):
        origin = ctx.origin_of(node)
        block_lines = (ctx.program_lines if origin.kind == "program"
                       else _read_lines(origin.source_path))
        stmt, end = _reconstruct_block(block_lines, origin.line)
        m = _RE_EXEC_CICS_BLOCK.search(stmt)
        if not m:
            continue  # not a well-formed EXEC CICS…END-EXEC block — emit nothing
        verb, body = m.group("verb").upper(), m.group("body")
        _dispatch_cics(ctx, verb, body, origin, end, ws_constants)


def _dispatch_cics(ctx: _Ctx, verb: str, body: str, origin: ConstructOrigin,
                   end: int, ws_constants: dict[str, str]) -> None:
    if verb == "LINK":
        _cics_program_op(ctx, body, "LINKS_TO", "RUL-COBOL-013", origin, end)
    elif verb == "XCTL":
        _cics_program_op(ctx, body, "XCTLS_TO", "RUL-COBOL-014", origin, end)
    elif verb == "RETURN":
        m = _RE_TRANSID_OP.search(body)
        if m:
            _cics_emit(ctx, "RUL-COBOL-015", origin, end,
                       {"edge_type": "RETURNS_TO_TRANSID", "from": ctx.from_id,
                        "to_candidate": f"transaction:{m.group('v').upper()}"})
    elif verb == "SEND":
        _cics_map(ctx, body, "SENDS_MAP", "RUL-COBOL-016", origin, end)
    elif verb == "RECEIVE":
        _cics_map(ctx, body, "RECEIVES_MAP", "RUL-COBOL-017", origin, end)
    elif verb in _CICS_FILE_VERBS:
        _cics_file_op(ctx, verb, body, origin, end, ws_constants)


def _cics_program_op(ctx: _Ctx, body: str, edge_type: str, rule_id: str,
                     origin: ConstructOrigin, end: int) -> None:
    """LINK/XCTL PROGRAM(...): literal → typed program: edge (static); identifier → stays
    unresolved:+breadcrumb+must_not_promote (MOVE-chain target, never promoted)."""
    m_lit = _RE_PROGRAM_OP_LITERAL.search(body)
    if m_lit:
        _cics_emit(ctx, rule_id, origin, end,
                   {"edge_type": edge_type, "from": ctx.from_id,
                    "to_candidate": f"program:{m_lit.group('v').upper()}",
                    "call_kind": "static"})
        return
    m_id = _RE_PROGRAM_OP_IDENT.search(body)
    if m_id:
        ident = m_id.group("v").upper()
        _cics_emit(ctx, rule_id, origin, end,
                   {"edge_type": edge_type, "from": ctx.from_id,
                    "to_candidate": f"unresolved:{ident}", "call_kind": "dynamic",
                    "breadcrumb": ident, "must_not_promote": True})


def _cics_map(ctx: _Ctx, body: str, edge_type: str, rule_id: str,
              origin: ConstructOrigin, end: int) -> None:
    m_map = _RE_MAP_OP.search(body)
    if not m_map:
        return
    mapname = m_map.group("v").upper()
    m_mset = _RE_MAPSET_OP.search(body)
    mapset = m_mset.group("v").upper() if m_mset else None
    to_id = f"bms-map:{mapset}/{mapname}" if mapset else f"bms-map:UNKNOWN/{mapname}"
    _cics_emit(ctx, rule_id, origin, end,
               {"edge_type": edge_type, "from": ctx.from_id, "to_candidate": to_id,
                "mapset_op": mapset, "map_op": mapname})


def _cics_file_op(ctx: _Ctx, verb: str, body: str, origin: ConstructOrigin,
                  end: int, ws_constants: dict[str, str]) -> None:
    edge_type, access_form = _CICS_FILE_VERBS[verb]
    m_file = _RE_FILE_OP.search(body)
    if not m_file:
        return
    operand = m_file.group("v").upper()
    resolved = ws_constants.get(operand)
    if resolved:
        fname, operand_kind = resolved.upper(), "ws_constant"
    else:
        fname = operand
        operand_kind = "literal" if not operand.startswith("WS-") else "ws_unresolved"
    data = {"edge_type": edge_type, "from": ctx.from_id,
            "to_candidate": f"logical-file:{ctx.program_name}/{fname}",
            "access_form": access_form, "scope_hint": "cics",
            "operand_kind": operand_kind, "operand_surface": operand}
    if operand_kind == "ws_unresolved":
        data["needs_pass2"] = True
    _cics_emit(ctx, "RUL-COBOL-018", origin, end, data)


def _cics_emit(ctx: _Ctx, rule_id: str, origin: ConstructOrigin, end: int,
               data: dict) -> None:
    _emit(ctx.sink, kind="edge_candidate", rule_id=rule_id, data=data,
          origin=origin, src=ctx.src, program_lines=ctx.program_lines,
          end_line=end, role="use-site")


def _ws_constants(lines: list[str]) -> dict[str, str]:
    """WORKING-STORAGE literal constants (`<lvl> NAME PIC X(n) VALUE 'lit'.`), for CICS
    file-operand propagation. Identical to the regex `_scan_ws_constants` (narrow: literal
    VALUE only, no MOVE-chain — anything beyond falls to Pass 2)."""
    markers = _section_markers(lines)
    out: dict[str, str] = {}
    buf = ""
    for i, raw in enumerate(lines, 1):
        if not _in_section(i, markers, ("WORKING-STORAGE",),
                           exit_on=("LINKAGE", "PROCEDURE DIVISION")):
            buf = ""
            continue
        code = cobol_code_text(raw).strip()
        if not code:
            continue
        buf = f"{buf} {code}" if buf else code
        if not code.endswith("."):
            continue
        m = _RE_WS_CONSTANT.match(buf)
        if m:
            out[m.group("name").upper()] = m.group("val").rstrip()
        buf = ""
    return out


def _reconstruct_block(lines: list[str], start: int) -> tuple[str, int]:
    """The EXEC CICS…END-EXEC logical statement from `start`, plus its end line."""
    end = _consume_through_token(lines, start, "END-EXEC", max_lines=30)
    return _logical_statement(lines, start, end), end


def _consume_through_token(lines: list[str], start: int, token: str,
                           max_lines: int = 30) -> int:
    end_max = min(start + max_lines, len(lines))
    for j in range(start, end_max + 1):
        code = cobol_code_text(lines[j - 1] if j <= len(lines) else "")
        if token.upper() in code.upper():
            return j
    return start


def _read_lines(path: str) -> list[str]:
    try:
        return Path(path).read_text(encoding="latin-1").split("\n")
    except OSError:
        return []


# --- RUL-COBOL-002/003/004: COPY / INCLUDES (lexical, source-direct) ---

def _emit_copy_includes(ctx: _Ctx) -> None:
    """The program's DIRECT COPY statements -> INCLUDES edges (+ DEFINES_LAYOUT_FOR for
    FD-context copies). Source-direct: a COPY directive's line numbers ARE source lines
    (no preprocessing fold), so this needs no resolver. The stateful section/FD/record
    walk mirrors the regex baseline exactly; byte-parity is proven across the full corpus
    by the emission harness. `emit_program` only runs on programs, so source_role is
    always 'program' (RUL-COBOL-020 is the copybook-role variant, handled in the data
    layer's domain, not here).
    """
    lines = ctx.program_lines
    markers = _section_markers(lines)
    current_fd: str | None = None
    current_record: str | None = None
    i, n = 1, len(lines)
    while i <= n:
        code = cobol_code_text(lines[i - 1])
        in_file_section = _in_section(
            i, markers, ("FILE SECTION",),
            exit_on=("WORKING-STORAGE", "LINKAGE", "PROCEDURE DIVISION"))
        mfd = _RE_FD.match(code)
        if mfd and in_file_section:
            current_fd, current_record = mfd.group("fd").upper(), None
            i += 1
            continue
        if _RE_SD.match(code) and in_file_section:
            current_fd, current_record = None, None
            i += 1
            continue
        m01 = _RE_01.match(code)
        if m01 and in_file_section and current_fd:
            current_record = m01.group("rec").upper()
            i += 1
            continue
        if _RE_COPY_BEGIN.search(code):
            end_idx = _consume_through_period(lines, i, max_lines=10)
            stmt = _logical_statement(lines, i, end_idx)
            fd_area = current_fd is not None and current_record is not None
            if _emit_one_copy(ctx, stmt, i, end_idx, fd_area, current_fd):
                i = end_idx + 1
                continue
        i += 1


def _emit_one_copy(ctx: _Ctx, stmt: str, start: int, end: int,
                   fd_area: bool, current_fd: str | None) -> bool:
    m_full = _RE_COPY_HEAD.match(stmt)
    if m_full:
        target = (m_full.group(1) or m_full.group(2) or m_full.group(3)).upper()
        rest = m_full.group("rest") or ""
        replacing = _parse_replacing(rest) if "REPLACING" in rest.upper() else None
    else:
        m_beg = _RE_COPY_BEGIN.match(stmt)
        if not m_beg:
            return False
        target = (m_beg.group(1) or m_beg.group(2) or m_beg.group(3)).upper()
        replacing = None

    rule_id = ("RUL-COBOL-003" if replacing
               else "RUL-COBOL-004" if fd_area
               else "RUL-COBOL-002")
    origin = ConstructOrigin(ctx.src.record.path, start, "program")
    _emit(ctx.sink, kind="edge_candidate", rule_id=rule_id,
          data={
              "edge_type": "INCLUDES",
              "from": ctx.from_id,
              "to_candidate": f"copybook:{target}",
              "fd_context": fd_area,
              "replacing_terms": replacing,
          },
          origin=origin, src=ctx.src, program_lines=ctx.program_lines,
          end_line=end, role="use-site")
    if fd_area and current_fd:
        lf_id = f"logical-file:{ctx.program_name}/{current_fd}"
        _emit(ctx.sink, kind="edge_candidate", rule_id="RUL-COBOL-004",
              data={
                  "edge_type": "DEFINES_LAYOUT_FOR",
                  "from": f"copybook:{target}",
                  "to_candidate": lf_id,
              },
              origin=origin, src=ctx.src, program_lines=ctx.program_lines,
              end_line=end, role="fd-context")
    return True


def _parse_replacing(rest: str) -> list[dict]:
    """Mirror of the regex extractor's REPLACING ... BY ... parse (kept byte-identical)."""
    import re
    terms = []
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


# --- stateful-walk helpers (independent re-derivation of the regex section logic) ---

def _section_markers(lines: list[str]) -> list[tuple[int, str]]:
    markers: list[tuple[int, str]] = []
    for i, raw in enumerate(lines, 1):
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


def _in_section(line_no: int, markers: list[tuple[int, str]],
                names: tuple[str, ...], *, exit_on: tuple[str, ...] = ()) -> bool:
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


def _consume_through_period(lines: list[str], start: int, max_lines: int = 10) -> int:
    for j in range(start, min(start + max_lines, len(lines)) + 1):
        code = cobol_code_text(lines[j - 1] if j <= len(lines) else "")
        if code.rstrip().endswith("."):
            return j
    return start


def _logical_statement(lines: list[str], start: int, end: int) -> str:
    return " ".join(cobol_code_text(lines[j - 1]).strip()
                    for j in range(start, end + 1) if 1 <= j <= len(lines))


def _clause_keyword(node: dict | None, choices: tuple[str, ...]) -> str | None:
    """Pull the value keyword out of a structured clause (e.g. ORGANIZATION IS INDEXED
    → "INDEXED"; LINE SEQUENTIAL → "LINE_SEQUENTIAL"). Matches the regex extractor's
    normalization (`.replace(" ", "_")`)."""
    if node is None:
        return None
    toks = [t.upper() for t in _flat(node) if t.strip()]
    text = " ".join(toks)
    # longest choice first so "LINE SEQUENTIAL" wins over "SEQUENTIAL"
    for choice in sorted(choices, key=len, reverse=True):
        if choice in text:
            return choice.replace(" ", "_")
    return None


# --- source-tree layout (filesystem convention, flagged — not language semantics) ---

def _sibling_copy_dirs(program_path: Path) -> list[Path]:
    app = program_path.parent.parent  # …/app/cbl/PROG.cbl -> …/app
    dirs = [app / "cpy", app / "cpy-bms"]
    return [d for d in dirs if d.is_dir()]


def _build_harness(copy_dirs: list[Path], dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    for d in copy_dirs:
        parse.build_copybook_harness(d, dest)
    return dest
