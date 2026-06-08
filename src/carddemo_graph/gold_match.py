"""Gold-set canonicalization comparator — Acceptance Test A.

Per spec v4.1 §Validation §Gold-set canonicalization: runs the Q1–Q4 queries
against the kuzu graph (built from entities.json + edges.json) and compares
results to gold/gold_set.md after canonicalization.

Q1–Q4 are auto-compared end-to-end. The queries are the SAME validated runners
used by the Gate-3 driver (`carddemo_graph.pilot.run_q*_sample`) — gold_match does
NOT re-implement query logic; it parses the gold expectations, runs each runner per
gold-entry input, and diffs canonical projections.

Comparison projections (faithful to each gold entry's asserted answer):
  Q1.direct_includers   — set of program ids
  Q2.program_access     — set of (program_id, mode, verb_line) access sites
  Q2.jcl_access         — set of jcl-job ids (query step ids canonicalized to job;
                          gold jcl_access is job-level per the freeze banner's
                          "Known Gate-3 Incremental")
  Q3.entry_program      — scalar program id
  Q3.reachable_programs — set of program ids (typed, static-edge closure only)
  Q3.unresolved_reaches — set of (from_program, breadcrumb)
  Q4.entry_program      — scalar program id
  Q4.mapsets            — set of mapset ids
  Q4.map_interactions   — set of (program_id, map_id). Direction is informational:
                          the skeleton omits identifier-form RECEIVE (enrichment) per
                          the Q4.2 gold note, so comparison is on (program, map) presence.
  Q4.field_surface      — count of visible field labels vs the gold INITIAL= clause count

Enrichments are NOT compared (skeleton/enrichment split): enrichments.json has a
separate hypothesis-friendly eval framework. This comparator targets the skeleton:
entities.json + edges.json via kuzu Cypher.

Usage:
    python -m carddemo_graph.gold_match <kuzu_db> <gold_set_path>
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from carddemo_graph.pilot import (
    run_q1_sample, run_q2_sample, run_q3_sample, run_q4_sample,
)

EDGE_TYPES = {"READS", "WRITES", "UPDATES", "DELETES", "STARTS_BROWSE"}


# ---------------------------------------------------------------------------
# Canonicalization
# ---------------------------------------------------------------------------

def canonical_id(s):
    """Uppercase the value portion of <prefix>:<value> ids (preserve prefix)."""
    if not isinstance(s, str) or ":" not in s:
        return str(s).upper() if isinstance(s, str) else s
    prefix, _, value = s.partition(":")
    return f"{prefix}:{value.upper()}"


def step_to_job(step_id: str) -> str:
    """jcl-step:DUSRSECJ/STEP03 -> jcl-job:DUSRSECJ (gold jcl_access is job-level)."""
    m = re.match(r"jcl-step:([^/]+)/", step_id)
    if m:
        return canonical_id(f"jcl-job:{m.group(1)}")
    return canonical_id(step_id)


# ---------------------------------------------------------------------------
# Gold-set section splitting + sub-extraction
# ---------------------------------------------------------------------------

@dataclass
class Section:
    qname: str          # "Q2.1"
    input_id: str       # "dataset:..." / "copybook:..." / "transaction:..."
    text: str


def split_sections(text: str) -> list[Section]:
    """Split on every '## Qx.y' header; each section runs to the next such header."""
    pat = re.compile(r"^## (Q\d+\.\d+)\b(.*)$", re.MULTILINE)
    matches = list(pat.finditer(text))
    out: list[Section] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        idm = re.search(r"`(copybook|dataset|transaction):[^`]+`", m.group(2))
        input_id = idm.group(0).strip("`") if idm else ""
        out.append(Section(m.group(1), input_id, text[start:end]))
    return out


def _subsection(body: str, label: str) -> str:
    """Text of '### Expected — `label`' up to the next '### ' / '## ' / '---' / EOF."""
    m = re.search(rf"### Expected — `{re.escape(label)}`(.*?)(?=\n### |\n## |\n---|\Z)",
                  body, re.DOTALL)
    return m.group(1) if m else ""


def _first_fenced(body: str) -> str:
    """First ```...``` block after the '### Expected' header (the Q3/Q4 expected block)."""
    em = re.search(r"### Expected\b", body)
    after = body[em.end():] if em else body
    fm = re.search(r"```(.*?)```", after, re.DOTALL)
    return fm.group(1) if fm else ""


def _table_rows(block: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in block.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells if c):   # divider row
            continue
        rows.append(cells)
    return rows


# ---------------------------------------------------------------------------
# Parsers — one per question family
# ---------------------------------------------------------------------------

def parse_q1(text: str) -> dict:
    out = {}
    for sec in split_sections(text):
        if not sec.qname.startswith("Q1."):
            continue
        block = _subsection(sec.text, "direct_includers")
        progs = re.findall(r"program:[A-Z0-9_]+", block)
        out[sec.qname] = {
            "copybook_id": canonical_id(sec.input_id),
            "direct_includers": {canonical_id(p) for p in progs},
        }
    return out


def parse_q2(text: str) -> dict:
    out = {}
    for sec in split_sections(text):
        if not sec.qname.startswith("Q2."):
            continue
        pa = set()
        for cells in _table_rows(_subsection(sec.text, "program_access")):
            prog = next((c for c in cells if re.fullmatch(r"program:[A-Z0-9_]+", c)), None)
            mode = next((c for c in cells if c in EDGE_TYPES), None)
            line = next((c for c in cells if re.fullmatch(r"\d+", c)), None)
            if prog and mode and line:
                pa.add((canonical_id(prog), mode, int(line)))
        jcl = set()
        for cells in _table_rows(_subsection(sec.text, "jcl_access")):
            for c in cells:
                if re.fullmatch(r"jcl-job:[A-Z0-9_]+", c):
                    jcl.add(canonical_id(c))
        out[sec.qname] = {"dataset_id": canonical_id(sec.input_id),
                          "program_access": pa, "jcl_access": jcl}
    return out


def parse_q3(text: str) -> dict:
    out = {}
    for sec in split_sections(text):
        if not sec.qname.startswith("Q3."):
            continue
        block = _first_fenced(sec.text)
        em = re.search(r"entry_program:\s*(program:[A-Z0-9_]+)", block)
        entry = canonical_id(em.group(1)) if em else None
        rm = re.search(r"reachable_programs:(.*?)unresolved_reaches:", block, re.DOTALL)
        reach_blk = rm.group(1) if rm else ""
        reachable = {canonical_id(p) for p in re.findall(r"-\s*(program:[A-Z0-9_]+)", reach_blk)}
        um = re.search(r"unresolved_reaches:(.*)", block, re.DOTALL)
        unres_blk = um.group(1) if um else ""
        unresolved = {(canonical_id(p), bc) for p, bc in re.findall(
            r"from:\s*(program:[A-Z0-9_]+),\s*surface_form:\s*([A-Z0-9\-]+)", unres_blk)}
        out[sec.qname] = {"transaction_id": canonical_id(sec.input_id),
                          "entry_program": entry, "reachable": reachable,
                          "unresolved": unresolved}
    return out


def parse_q4(text: str) -> dict:
    out = {}
    for sec in split_sections(text):
        if not sec.qname.startswith("Q4."):
            continue
        block = _first_fenced(sec.text)
        em = re.search(r"entry_program:\s*(program:[A-Z0-9_]+)", block)
        entry = canonical_id(em.group(1)) if em else None
        msm = re.search(r"mapsets:\s*\[([^\]]+)\]", block)
        mapsets = {canonical_id(x) for x in
                   re.findall(r"bms-mapset:[A-Z0-9_]+", msm.group(1) if msm else "")}
        fcm = re.search(r"field_surface:\s*(\d+)", block)
        field_count = int(fcm.group(1)) if fcm else None
        mim = re.search(r"map_interactions:(.*?)mapsets:", block, re.DOTALL)
        mi_blk = mim.group(1) if mim else ""
        mi = {(canonical_id(f"program:{p}"), canonical_id(mp)) for p, mp in re.findall(
            r"program:\s*([A-Z0-9_]+),\s*map:\s*(bms-map:[A-Z0-9_/-]+)", mi_blk)}
        out[sec.qname] = {"transaction_id": canonical_id(sec.input_id),
                          "entry_program": entry, "mapsets": mapsets,
                          "map_interactions": mi, "field_count": field_count}
    return out


_SQL_TOKEN = re.compile(r"CHAR\(\d+\)|NUMERIC\(\d+(?:,\d+)?\)|BIGINT|INTEGER|SMALLINT",
                        re.IGNORECASE)
_Q6_SKIP = "<<SKIP>>"   # gold cell '(skip)': FILLER padding, excluded from the type check


def parse_q6(text: str) -> dict:
    """Q6 — field-level record layout (v2.2 KU-9). Item row:
    | name | level | picture | suggested_sql_type |.

    The type cell carries the cold agent's notation, parsed faithfully:
      - '(group)' / 'group'      -> group, accepted = {''} (no type)
      - '(skip)'                 -> SKIP sentinel (FILLER padding, excluded from compare)
      - 'X (or Y / Z)' / 'X (W)' -> acceptable SET {X,Y,Z,...} (every type token in the cell)
      - plain 'NUMERIC(12,2)'    -> singleton set
    Match = the extraction's type is IN the gold cell's accepted set (so an explicitly
    offered alternative like EXP-ACCT-ID 'BIGINT (or NUMERIC(11)/CHAR(11))' accepts the
    extraction's NUMERIC(11) — faithful to the gold, not cherry-picked to match).

    Returns {qname: {"copybook_id":..., "items": {(name,level,picture): accepted|SKIP}}}.
    """
    out = {}
    for sec in split_sections(text):
        if not sec.qname.startswith("Q6."):
            continue
        items: dict = {}
        for cells in _table_rows(sec.text):
            if len(cells) < 4 or not re.fullmatch(r"\d+", cells[1].strip()):
                continue  # header/divider/non-item row
            name, level, pic, sqlcell = (cells[0].strip().upper(), int(cells[1].strip()),
                                         cells[2].strip(), cells[-1].strip())
            pic_n = "" if "group" in pic.lower() else pic
            low = sqlcell.lower()
            if "(skip)" in low:
                accepted = _Q6_SKIP
            elif "group" in low:
                accepted = frozenset({""})
            else:
                toks = {t.upper() for t in _SQL_TOKEN.findall(sqlcell)}
                accepted = frozenset(toks) if toks else frozenset({sqlcell.upper()})
            items[(name, level, pic_n)] = accepted
        out[sec.qname] = {"copybook_id": canonical_id(sec.input_id), "items": items}
    return out


def query_data_items(db: Path, copybook_id: str) -> dict:
    """DataItem extraction for a copybook: {(name, level, picture): suggested_sql_type}."""
    import kuzu
    conn = kuzu.Connection(kuzu.Database(str(db), read_only=True))
    r = conn.execute(
        "MATCH (d:DataItem) WHERE d.copybook_id = $c "
        "RETURN d.name, d.level, d.picture, d.suggested_sql_type",
        parameters={"c": copybook_id})
    out = {}
    while r.has_next():
        name, level, pic, sql = r.get_next()
        out[(str(name).upper(), int(level), pic or "")] = (sql or "").upper()
    return out


def compare_q6(db: Path, gold_text: str) -> list:
    """Compare DataItem extraction vs Q6 cold-agent gold: field set (structural) +
    sql-type acceptance (extraction type in the gold cell's accepted set). SKIP items
    (FILLER padding) are excluded from both sides."""
    results = []
    for qn, g in sorted(parse_q6(gold_text).items()):
        gold = g["items"]
        actual = query_data_items(db, g["copybook_id"])
        skip_keys = {k for k, a in gold.items() if a is _Q6_SKIP}
        gold_keys = {k for k, a in gold.items() if a is not _Q6_SKIP}
        actual_keys = {k for k in actual if k not in skip_keys}
        results.append(CompareResult(qn, "field_set", gold_keys, actual_keys))
        checked, ok = set(), set()
        for k in gold_keys & set(actual):
            checked.add(k)
            if actual[k] in {a.upper() for a in gold[k]}:
                ok.add(k)
        results.append(CompareResult(qn, "sql_types(accepted)", checked, ok))
    return results


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------

@dataclass
class CompareResult:
    qname: str
    field: str
    expected: set
    actual: set
    known_incremental: bool = False     # gold flags this as a Gate-3 deferral, not a fail

    @property
    def missing(self):
        return sorted(set(self.expected) - set(self.actual), key=str)

    @property
    def extra(self):
        return sorted(set(self.actual) - set(self.expected), key=str)

    @property
    def matched(self) -> bool:
        return not self.missing and not self.extra


def compare(db: Path, gold_text: str) -> list[CompareResult]:
    results: list[CompareResult] = []

    for qn, g in sorted(parse_q1(gold_text).items()):
        res = run_q1_sample(db, g["copybook_id"])
        actual = {canonical_id(r["program_id"]) for r in res["direct_includers"]}
        results.append(CompareResult(qn, "direct_includers", g["direct_includers"], actual))

    for qn, g in sorted(parse_q2(gold_text).items()):
        res = run_q2_sample(db, g["dataset_id"])
        pa = {(canonical_id(r["program_id"]), r["mode"], int(r["line"]))
              for r in res["program_access"]}
        jcl = {step_to_job(r["jcl_step"]) for r in res["jcl_access"]}
        results.append(CompareResult(qn, "program_access", g["program_access"], pa))
        results.append(CompareResult(qn, "jcl_access", g["jcl_access"], jcl,
                                     known_incremental=True))

    for qn, g in sorted(parse_q3(gold_text).items()):
        res = run_q3_sample(db, g["transaction_id"])
        entry = canonical_id(res["entry_program"]) if res["entry_program"] else None
        reachable = {canonical_id(x) for x in res["reachable_programs"]}
        unresolved = {(canonical_id(r["source_program"]), r["breadcrumb"])
                      for r in res["unresolved_reaches"]}
        results.append(CompareResult(qn, "entry_program", {g["entry_program"]}, {entry}))
        results.append(CompareResult(qn, "reachable_programs", g["reachable"], reachable))
        results.append(CompareResult(qn, "unresolved_reaches", g["unresolved"], unresolved))

    for qn, g in sorted(parse_q4(gold_text).items()):
        res = run_q4_sample(db, g["transaction_id"])
        entry = canonical_id(res["entry_program"]) if res["entry_program"] else None
        mapsets = {canonical_id(m["mapset_id"]) for m in res["mapsets"]}
        mi = {(canonical_id(x["program_id"]), canonical_id(x["map_id"]))
              for x in res["map_interactions"]}
        results.append(CompareResult(qn, "entry_program", {g["entry_program"]}, {entry}))
        results.append(CompareResult(qn, "mapsets", g["mapsets"], mapsets))
        results.append(CompareResult(qn, "map_interactions", g["map_interactions"], mi))
        results.append(CompareResult(qn, "field_surface(count)",
                                     {g["field_count"]}, {len(res["field_surface"])}))

    results.extend(compare_q6(db, gold_text))
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: gold_match.py <kuzu_db> <gold_set_path>")
        return 2
    db = Path(argv[0])
    gold = Path(argv[1])
    if not db.exists():
        print(f"kuzu DB not found: {db}")
        return 2
    if not gold.exists():
        print(f"gold set not found: {gold}")
        return 2

    text = gold.read_text()
    print(f"Loading gold set: {gold}")
    print(f"Gold set status: {'FROZEN' if 'FROZEN' in text[:600] else 'candidate (NOT frozen)'}")
    print()

    results = compare(db, text)
    npass = nfail = nincr = 0
    for r in results:
        if r.matched:
            print(f"[MATCH]  {r.qname}.{r.field}: {len(r.expected)} expected; {len(r.actual)} actual")
            npass += 1
        elif r.known_incremental:
            print(f"[INCR]   {r.qname}.{r.field}: known Gate-3 incremental (job-level gold vs "
                  f"step-level extract) — missing={r.missing[:6]} extra={r.extra[:6]}")
            nincr += 1
        else:
            print(f"[DIFF]   {r.qname}.{r.field}: missing={r.missing[:6]} extra={r.extra[:6]}")
            nfail += 1
    print()
    print(f"Total: matched={npass} diff={nfail} known-incremental={nincr} "
          f"(across {len(results)} field comparisons)")
    print()
    print("Interpretation: [MATCH] = exact after canonicalization. [DIFF] = a real delta "
          "to triage per the failure-mode taxonomy. [INCR] = a delta the frozen gold "
          "explicitly defers to a Gate-3 increment (jcl_access fine-grain).")
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
