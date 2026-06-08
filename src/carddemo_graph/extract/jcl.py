"""JCL and JCL-PROC Pass-1 deterministic extractor.

Implements RUL-JCL-* and RUL-JCL-PROC-* from `artifacts/deterministic_rules.md`.

JCL syntax (here): lines start with `//`. After the strip pipeline, `//*` comments
are gone. A statement is one of:
  //<name> JOB ...
  //<step> EXEC PGM=<pgm>[,...]
  //<step> EXEC PROC=<proc>[,...]
  //<dd>   DD <operands...>
  //<name> PROC ...      (cataloged PROC declaration; in .prc files)
  //       <continuation operands>   (continuation lines)
  // PEND                            (end of inline PROC)

DD statements continue across lines; subsequent lines are continuation lines
beginning with `//` followed by whitespace. The continuation marker is a trailing
comma on the previous operand.
"""

from __future__ import annotations

import re

from carddemo_graph.extract.observation import (
    Observation, ObservationSink, ProvenanceItem,
)
from carddemo_graph.extract.sources import SourceFile


# Line-shape patterns
_RE_JOB = re.compile(r"^//(?P<name>[A-Z][A-Z0-9#@$]{0,7})\s+JOB\b", re.IGNORECASE)
_RE_EXEC = re.compile(
    r"^//(?P<step>[A-Z][A-Z0-9#@$]{0,7})\s+EXEC\s+(?P<rest>.+)$",
    re.IGNORECASE,
)
_RE_DD = re.compile(
    r"^//(?P<dd>[A-Z][A-Z0-9.#@$]{0,15}?)\s+DD\s+(?P<rest>.+)$",
    re.IGNORECASE,
)
_RE_PROC_DECL = re.compile(r"^//(?P<name>[A-Z][A-Z0-9#@$]{0,7})\s+PROC\b\s*(?P<params>.*)$",
                           re.IGNORECASE)
_RE_PEND = re.compile(r"^//\s*PEND\b", re.IGNORECASE)
_RE_JCLLIB = re.compile(
    r"^//(?P<name>[A-Z][A-Z0-9#@$]{0,7})?\s*JCLLIB\s+ORDER=\(?(?P<paths>[^)]+)\)?",
    re.IGNORECASE,
)
_RE_CONTINUATION = re.compile(r"^//\s+(?P<rest>.+)$")

# EXEC operands
_RE_PGM = re.compile(r"\bPGM\s*=\s*(?P<v>[A-Z][A-Z0-9]*)", re.IGNORECASE)
_RE_PROC_OP = re.compile(r"\bPROC\s*=\s*(?P<v>[A-Z][A-Z0-9]*)", re.IGNORECASE)
_RE_EXEC_PROC_POSITIONAL = re.compile(
    r"^\s*(?P<proc>[A-Z][A-Z0-9]*)(?:[,\s]|$)", re.IGNORECASE
)

# DD operands
_RE_DSN = re.compile(r"\bDSN\s*=\s*(?P<v>[A-Z0-9.&+\-()]+)", re.IGNORECASE)
_RE_DISP = re.compile(r"\bDISP\s*=\s*(?P<v>\([^)]*\)|[A-Z]+)", re.IGNORECASE)
_RE_DUMMY = re.compile(r"\bDUMMY\b", re.IGNORECASE)
_RE_SYSOUT = re.compile(r"\bSYSOUT\s*=\s*[*A-Z0-9]+", re.IGNORECASE)
_RE_DCB_DSORG = re.compile(r"\bDSORG\s*=\s*(?P<v>[A-Z]+)", re.IGNORECASE)

# Step-level override prefix in PROC use-sites: //STEPNAME.DDNAME DD ...
_RE_STEP_PREFIX_DD = re.compile(
    r"^//(?P<step>[A-Z][A-Z0-9#@$]{0,7})\.(?P<dd>[A-Z][A-Z0-9#@$]{0,15})\s+DD\s+(?P<rest>.+)$",
    re.IGNORECASE,
)


def _normalize_dsn(dsn: str) -> tuple[str, dict]:
    """Normalize a DSN to a canonical Dataset id.

    Handles:
      - GDG references like 'X.Y.BKUP(+1)' → base 'X.Y.BKUP' with gdg_offset '+1'
      - Quoted DSN remains canonical (quote chars stripped)
      - Trailing /leading whitespace stripped
      - Member references like 'X.Y(MBR)' → base 'X.Y' with member 'MBR' (non-numeric)
      - Unresolved symbolic params kept verbatim; partial flag set
    """
    raw = dsn.strip().strip("'\"")
    attrs: dict = {}
    m = re.match(r"^(?P<base>[A-Z0-9.&+\-]+)(?:\((?P<paren>[^)]+)\))?$", raw, re.IGNORECASE)
    if not m:
        return raw, attrs
    base = m.group("base")
    paren = m.group("paren")
    if paren is not None:
        if re.match(r"^[+\-]?\d+$", paren):
            attrs["gdg_offset"] = paren
        else:
            attrs["member"] = paren
    if "&" in base:
        attrs["partial"] = True
        attrs["unresolved_tokens"] = re.findall(r"&[A-Z][A-Z0-9]*", base, re.IGNORECASE)
    return base, attrs


class JclExtractor:
    """JCL/PROC extractor. One instance per file."""

    def __init__(self, source: SourceFile, sink: ObservationSink, *, kind: str):
        """kind ∈ {'job', 'proc'} — affects how PROC/JOB declarations are interpreted."""
        self.src = source
        self.sink = sink
        self.kind = kind
        self.lines = source.lines
        self.src_id = source.record.id
        self.src_hash = source.record.source_hash
        self.src_path = source.record.path
        self.current_job: str | None = None
        self.current_proc: str | None = None
        self.current_step: str | None = None
        self.current_step_pgm: str | None = None  # PGM= of most recent EXEC, for SYSIN routing
        self.step_counter: int = 0

    def _prov(self, s: int, e: int | None = None, snippet: str | None = None,
              role: str | None = None) -> list[ProvenanceItem]:
        if e is None:
            e = s
        if snippet is None:
            snippet = "\n".join(self.lines[s - 1:e])
        return [ProvenanceItem(
            source_path=self.src_path, start_line=s, end_line=e,
            snippet=snippet, role=role,
            source_file_id=self.src_id, source_hash=self.src_hash,
        )]

    def _emit_obs(self, *, kind: str, rule_id: str, data: dict,
                  start_line: int, end_line: int | None = None,
                  snippet: str | None = None, role: str | None = None) -> None:
        self.sink.add(Observation(
            id=self.sink.next_id(),
            kind=kind, evidence_kind="deterministic", rule_id=rule_id,
            provenance=self._prov(start_line, end_line, snippet, role),
            data=data,
        ))

    def _logical_statement(self, start: int) -> tuple[str, int]:
        """Read JCL statement at line `start` plus its continuation lines.

        Continuation: previous operand ends with comma, next line starts `//   `
        (slashes followed by spaces, not a new statement header).

        Returns (combined_text, end_line).
        """
        parts: list[str] = [self.lines[start - 1]]
        i = start
        while i < len(self.lines):
            cur_stripped = self.lines[i - 1].rstrip()
            if not cur_stripped.endswith(","):
                break
            nxt = self.lines[i] if i < len(self.lines) else ""
            mcont = _RE_CONTINUATION.match(nxt)
            if not mcont:
                break
            parts.append("    " + mcont.group("rest"))
            i += 1
        return ("\n".join(parts), i)

    def extract(self) -> None:
        if self.kind == "proc":
            self._extract_proc()
        else:
            self._extract_job()

    # ----------------------------- JOBs ---------------------------

    def _extract_job(self) -> None:
        i = 1
        n = len(self.lines)
        while i <= n:
            line = self.lines[i - 1]
            if not line.startswith("//"):
                i += 1
                continue

            m = _RE_JOB.match(line)
            if m:
                name = m.group("name").upper()
                self.current_job = name
                stmt, end = self._logical_statement(i)
                self._emit_obs(
                    kind="entity_candidate", rule_id="RUL-JCL-001",
                    data={
                        "entity_type": "JCLJob", "name": name,
                        "id_candidate": f"jcl-job:{name}",
                    },
                    start_line=i, end_line=end, role="declaration",
                )
                i = end + 1
                continue

            m = _RE_JCLLIB.match(line)
            if m:
                stmt, end = self._logical_statement(i)
                # property_observation on job
                self._emit_obs(
                    kind="property_observation", rule_id="RUL-JCL-011",
                    data={
                        "owner_id": f"jcl-job:{self.current_job}" if self.current_job else None,
                        "property": "jcllib_search_path",
                        "value": m.group("paths").strip(),
                    },
                    start_line=i, end_line=end, role="declaration",
                )
                i = end + 1
                continue

            m = _RE_EXEC.match(line)
            if m:
                stmt, end = self._logical_statement(i)
                step = m.group("step").upper()
                self.current_step = step
                self.step_counter += 1
                self._handle_exec(stmt, step, i, end)
                i = end + 1
                continue

            # Step-prefixed DD (PROC use-site override): //STEPNAME.DDNAME DD ...
            m = _RE_STEP_PREFIX_DD.match(line)
            if m:
                stmt, end = self._logical_statement(i)
                self._handle_dd(stmt, m.group("dd").upper(), i, end,
                               proc_step_override=m.group("step").upper())
                i = end + 1
                continue

            m = _RE_DD.match(line)
            if m:
                stmt, end = self._logical_statement(i)
                self._handle_dd(stmt, m.group("dd").upper(), i, end)
                i = end + 1
                continue

            i += 1

    # ----------------------------- PROCs --------------------------

    def _extract_proc(self) -> None:
        i = 1
        n = len(self.lines)
        while i <= n:
            line = self.lines[i - 1]
            if not line.startswith("//"):
                i += 1
                continue

            m = _RE_PROC_DECL.match(line)
            if m and self.current_proc is None:
                name = m.group("name").upper()
                self.current_proc = name
                stmt, end = self._logical_statement(i)
                # Filename mismatch detection
                fname_stem = self.src.path.stem.upper()
                filename_mismatch = (name != fname_stem)
                self._emit_obs(
                    kind="entity_candidate", rule_id="RUL-JCL-PROC-001",
                    data={
                        "entity_type": "JCLProc",
                        "declared_name": name,
                        "id_candidate": f"jcl-proc:{name}",
                        "filename": self.src.path.name,
                        "filename_mismatch": filename_mismatch,
                        "default_params": m.group("params").strip() or None,
                    },
                    start_line=i, end_line=end, role="declaration",
                )
                i = end + 1
                continue

            if _RE_PEND.match(line):
                i += 1
                continue

            m = _RE_EXEC.match(line)
            if m:
                stmt, end = self._logical_statement(i)
                step = m.group("step").upper()
                self.current_step = step
                self.step_counter += 1
                # Within a PROC, EXEC PROC= or EXEC PGM= behave the same; use the proc name
                # as the "job-like" scope for the step id.
                self._handle_exec(stmt, step, i, end, owning_proc=self.current_proc)
                i = end + 1
                continue

            m = _RE_STEP_PREFIX_DD.match(line)
            if m:
                stmt, end = self._logical_statement(i)
                self._handle_dd(stmt, m.group("dd").upper(), i, end,
                               proc_step_override=m.group("step").upper(),
                               owning_proc=self.current_proc)
                i = end + 1
                continue

            m = _RE_DD.match(line)
            if m:
                stmt, end = self._logical_statement(i)
                self._handle_dd(stmt, m.group("dd").upper(), i, end,
                               owning_proc=self.current_proc)
                i = end + 1
                continue

            i += 1

    # ----------------------------- EXEC handler -------------------

    def _handle_exec(self, stmt: str, step: str, start: int, end: int,
                     *, owning_proc: str | None = None) -> None:
        scope_name = owning_proc or self.current_job or "UNKNOWN"
        step_id = f"jcl-step:{scope_name}/{step}"
        self._emit_obs(
            kind="entity_candidate", rule_id="RUL-JCL-002",
            data={
                "entity_type": "JCLStep",
                "name": step,
                "id_candidate": step_id,
                "owner_id": (f"jcl-job:{scope_name}" if owning_proc is None else
                             f"jcl-proc:{scope_name}"),
                "step_order": self.step_counter,
            },
            start_line=start, end_line=end, role="declaration",
        )

        m_pgm = _RE_PGM.search(stmt)
        if m_pgm:
            pgm = m_pgm.group("v").upper()
            self.current_step_pgm = pgm
            self._emit_obs(
                kind="edge_candidate", rule_id="RUL-JCL-002",
                data={
                    "edge_type": "INVOKES",
                    "from": step_id,
                    "to_candidate": f"program:{pgm}",
                },
                start_line=start, end_line=end, role="use-site",
            )
            return
        # Non-PGM EXEC (PROC or positional) — clear PGM tracking
        self.current_step_pgm = None

        m_proc = _RE_PROC_OP.search(stmt)
        if m_proc:
            proc = m_proc.group("v").upper()
            inv_id = f"jcl-proc-inv:{scope_name}/{step}"
            self._emit_obs(
                kind="entity_candidate", rule_id="RUL-JCL-003",
                data={
                    "entity_type": "JCLProcInvocation",
                    "id_candidate": inv_id,
                    "name": step,
                    "owner_id": f"jcl-job:{scope_name}" if owning_proc is None else f"jcl-proc:{scope_name}",
                    "invoked_proc_id": f"jcl-proc:{proc}",
                },
                start_line=start, end_line=end, role="declaration",
            )
            self._emit_obs(
                kind="edge_candidate", rule_id="RUL-JCL-003",
                data={
                    "edge_type": "USES_PROC",
                    "from": inv_id,
                    "to_candidate": f"jcl-proc:{proc}",
                },
                start_line=start, end_line=end, role="use-site",
            )
            return

        # Positional PROC invocation: `EXEC <name>` with no PGM=/PROC= prefix
        # is interpreted as `EXEC PROC=<name>`.
        rest_match = re.search(r"\bEXEC\s+(?P<rest>.+)$", stmt, re.IGNORECASE)
        if rest_match:
            mpos = _RE_EXEC_PROC_POSITIONAL.match(rest_match.group("rest"))
            if mpos:
                proc = mpos.group("proc").upper()
                # Skip "PGM" / "PROC" - already handled
                if proc not in ("PGM", "PROC"):
                    inv_id = f"jcl-proc-inv:{scope_name}/{step}"
                    self._emit_obs(
                        kind="entity_candidate", rule_id="RUL-JCL-003",
                        data={
                            "entity_type": "JCLProcInvocation",
                            "id_candidate": inv_id,
                            "name": step,
                            "owner_id": f"jcl-job:{scope_name}" if owning_proc is None else f"jcl-proc:{scope_name}",
                            "invoked_proc_id": f"jcl-proc:{proc}",
                            "positional": True,
                        },
                        start_line=start, end_line=end, role="declaration",
                    )
                    self._emit_obs(
                        kind="edge_candidate", rule_id="RUL-JCL-003",
                        data={"edge_type": "USES_PROC", "from": inv_id,
                              "to_candidate": f"jcl-proc:{proc}"},
                        start_line=start, end_line=end, role="use-site",
                    )

    # ----------------------------- DD handler ---------------------

    def _handle_dd(self, stmt: str, dd: str, start: int, end: int,
                   *, proc_step_override: str | None = None,
                   owning_proc: str | None = None) -> None:
        scope_name = owning_proc or self.current_job or "UNKNOWN"
        step_name = proc_step_override or self.current_step or "UNKNOWN"
        step_id = (f"jcl-step:{scope_name}/{step_name}" if owning_proc is None else
                   f"jcl-step:{scope_name}/{step_name}")

        if _RE_DUMMY.search(stmt):
            self._emit_obs(
                kind="property_observation", rule_id="RUL-JCL-005",
                data={"owner_id": step_id, "property": "dd_dummy", "value": dd},
                start_line=start, end_line=end, role="property",
            )
            return

        if _RE_SYSOUT.search(stmt):
            self._emit_obs(
                kind="property_observation", rule_id="RUL-JCL-005",
                data={"owner_id": step_id, "property": "dd_sysout", "value": dd},
                start_line=start, end_line=end, role="property",
            )
            return

        m_dsn = _RE_DSN.search(stmt)
        m_disp = _RE_DISP.search(stmt)
        if not m_dsn:
            # Likely an inline-DD (//DDNAME DD *) or a control-card; record as property
            if "*" in stmt.split("DD", 1)[1] if "DD" in stmt else False:
                self._emit_obs(
                    kind="property_observation", rule_id="RUL-JCL-006",
                    data={"owner_id": step_id, "property": "dd_inline", "value": dd},
                    start_line=start, end_line=end, role="property",
                )
            return

        dsn_raw = m_dsn.group("v")
        base, attrs = _normalize_dsn(dsn_raw)
        disp_raw = m_disp.group("v") if m_disp else None
        attributes = {
            "dd_name": dd,
            "raw_disp": disp_raw,
            "allocation_disposition": disp_raw,
        }
        attributes.update(attrs)
        ds_id = f"dataset:{base}"

        # Emit Dataset entity candidate
        self._emit_obs(
            kind="entity_candidate", rule_id="RUL-JCL-004",
            data={
                "entity_type": "Dataset",
                "name": base,
                "id_candidate": ds_id,
                "partial": attrs.get("partial", False),
                "gdg_offset": attrs.get("gdg_offset"),
            },
            start_line=start, end_line=end, role="declaration",
        )

        # Emit USES_DATASET edge candidate
        self._emit_obs(
            kind="edge_candidate", rule_id="RUL-JCL-004",
            data={
                "edge_type": "USES_DATASET",
                "from": step_id,
                "to_candidate": ds_id,
                **attributes,
            },
            start_line=start, end_line=end, role="use-site",
        )

        # PASSES_SYSIN_TO (RUL-JCL-010): when DD name is SYSIN and DSN references a
        # control-card dataset, emit a complementary edge tagged with the utility.
        if dd.upper() == "SYSIN" and self.current_step_pgm:
            self._emit_obs(
                kind="edge_candidate", rule_id="RUL-JCL-010",
                data={
                    "edge_type": "PASSES_SYSIN_TO",
                    "from": step_id,
                    "to_candidate": ds_id,
                    "utility": self.current_step_pgm,
                    "dd_name": dd,
                },
                start_line=start, end_line=end, role="use-site",
            )


def extract_jcl(source: SourceFile, sink: ObservationSink) -> None:
    """Entry: extract JCL (.jcl)."""
    JclExtractor(source, sink, kind="job").extract()


def extract_proc(source: SourceFile, sink: ObservationSink) -> None:
    """Entry: extract JCL PROC (.prc)."""
    JclExtractor(source, sink, kind="proc").extract()
