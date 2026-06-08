"""Facts-parity harness: regex vs MAPA program-construct emission.

For each program, run the regex extractor and the MAPA `emit_program` into separate
sinks, then diff the emitted Observation `data` payloads **per rule_id**. The MAPA path
must reach parity with the regex baseline on every implemented rule before the Phase-2
gate (the per-mapper invariant). As mappers are added, extend `IMPLEMENTED_RULES`.

Deltas are categorized, not smoothed:
- `only_regex` — a payload the regex emitted that MAPA did not (a candidate regression).
- `only_mapa`  — a payload MAPA emitted that the regex did not (a candidate improvement,
  e.g. a copybook-origin CALL the regex never scans).
Parity for an implemented rule = empty `only_regex` AND empty `only_mapa`, unless the
delta is in the documented allowed-improvement set.

Skips cleanly if the vendored MAPA build is absent (vendor/mapa/build.sh).
"""

import json
import tempfile
from pathlib import Path

import pytest

from carddemo_graph.extract.cobol import extract_cobol
from carddemo_graph.extract.observation import ObservationSink
from carddemo_graph.extract.parsers.cobol import parse
from carddemo_graph.extract.parsers.cobol.adapter import extract_cobol_mapa
from carddemo_graph.extract.parsers.cobol.map_program import emit_program
from carddemo_graph.extract.sources import read_source_file

_REPO = Path(__file__).resolve().parents[1]
_CBL = _REPO / "corpus" / "carddemo" / "stripped" / "app" / "cbl"

# Rules whose MAPA mapper is implemented and expected at parity. Grow this as mappers
# land; rules not listed are not yet diffed (the adapter still delegates them to regex).
IMPLEMENTED_RULES = {
    "RUL-COBOL-001",   # PROGRAM-ID
    "RUL-COBOL-005",   # file-control SELECT (LogicalFile + DECLARES_FILE)
    "RUL-COBOL-011",   # CALL literal (static)
    "RUL-COBOL-012",   # CALL identifier (dynamic) — corpus-unexercised
    "RUL-COBOL-002",   # COPY / INCLUDES (plain)
    "RUL-COBOL-003",   # COPY / INCLUDES (REPLACING)
    "RUL-COBOL-004",   # COPY / INCLUDES (FD-context) + DEFINES_LAYOUT_FOR
    "RUL-COBOL-006",   # READS
    "RUL-COBOL-007",   # WRITES
    "RUL-COBOL-008",   # UPDATES (REWRITE)
    "RUL-COBOL-009",   # DELETES — corpus-unexercised
    "RUL-COBOL-010",   # STARTS_BROWSE — corpus-unexercised
    "RUL-COBOL-013",   # CICS LINK — corpus-unexercised
    "RUL-COBOL-014",   # CICS XCTL (incl identifier-form must_not_promote)
    "RUL-COBOL-015",   # CICS RETURN TRANSID — corpus-unexercised
    "RUL-COBOL-016",   # CICS SEND MAP
    "RUL-COBOL-017",   # CICS RECEIVE MAP
    "RUL-COBOL-018",   # CICS file ops (ws-constant propagation)
}

# A delta between the two extractors is categorized, not blindly failed. Two kinds of
# delta are correctness *improvements*, not regressions:
#
# 1. only_mapa improvement — MAPA emits a construct the regex structurally cannot see.
#    CALL/CICS in a PROCEDURE copybook: the regex only scans program bodies, so a
#    construct whose provenance is a copybook (not the program) is a documented dividend.
#    (CALL exercises this on COACTUPC; copybook-origin CICS is generalization-only — no
#    instance in the CardDemo corpus — but the predicate covers it for correctness.)
_IMPROVEMENT_RULES = ("RUL-COBOL-011", "RUL-COBOL-012",
                      "RUL-COBOL-013", "RUL-COBOL-014", "RUL-COBOL-015",
                      "RUL-COBOL-016", "RUL-COBOL-017", "RUL-COBOL-018")


def _is_allowed_improvement(rule: str, obs, program_path: Path) -> bool:
    if rule in _IMPROVEMENT_RULES:
        sp = obs.provenance[0].source_path if obs.provenance else ""
        return Path(sp).resolve() != program_path.resolve()
    return False


# 2. only_regex false-positive — the regex emits an edge MAPA's grammar says is not real.
#    The batch-I/O regexes (`\bREAD\s+<id>` etc.) fire on non-statements like
#    `SET MORE-RECORDS-TO-READ TO TRUE` (the `READ` ending a data-name, then `TO`),
#    inventing a bogus logical file. MAPA, parsing the actual grammar, emits no I/O
#    statement there. Ground truth = the grammar: an only_regex I/O edge whose start line
#    has NO MAPA I/O statement is a regex false positive MAPA correctly drops.
_BATCH_IO_RULES = ("RUL-COBOL-006", "RUL-COBOL-007", "RUL-COBOL-008",
                   "RUL-COBOL-009", "RUL-COBOL-010")


def _is_regex_false_positive(rule: str, obs, mapa_io_lines: set[int]) -> bool:
    if rule in _BATCH_IO_RULES:
        start = obs.provenance[0].start_line if obs.provenance else None
        return start not in mapa_io_lines
    return False

# Programs spanning batch (SELECT-heavy) and CICS (online) styles. COBSWAIT carries
# cols-73..80 sequence numbers on its PROGRAM-ID/CALL lines — the seq-number provenance
# regression guard (see program_provenance._src_code).
PROGRAMS = ["CBTRN02C", "CBACT01C", "CBACT04C", "COACTUPC", "COCRDUPC", "COMEN01C",
            "COBSWAIT",
            # COCRDLIC has `SET MORE-RECORDS-TO-READ TO TRUE` — the regex `READ TO`
            # false positive MAPA correctly drops (regex-false-positive guard).
            "COCRDLIC"]

try:
    parse.ensure_built()
    _BUILT = True
except parse.MapaUnavailable:
    _BUILT = False

needs_mapa = pytest.mark.skipif(
    not _BUILT, reason="vendor/mapa build artifacts absent (run vendor/mapa/build.sh)")


def _key(obs) -> str:
    """Canonical comparison key for one observation: (rule, kind, data, start_line)."""
    d = json.dumps(obs.data, sort_keys=True, default=str)
    start = obs.provenance[0].start_line if obs.provenance else None
    return json.dumps([obs.rule_id, obs.kind, d, start], sort_keys=True)


def _by_rule(sink: ObservationSink) -> dict[str, list]:
    out: dict[str, list] = {}
    for o in sink.observations:
        out.setdefault(o.rule_id, []).append(o)
    return out


def _extract_both(prog: str):
    path = _CBL / f"{prog}.cbl"
    src = read_source_file(path, sfid=f"sf-{prog}")

    regex_sink = ObservationSink()
    extract_cobol(src, regex_sink)

    mapa_sink = ObservationSink()
    src2 = read_source_file(path, sfid=f"sf-{prog}")
    emit_program(src2, mapa_sink, workdir=Path(tempfile.mkdtemp(prefix=f"emit-{prog}-")))
    return regex_sink, mapa_sink


@needs_mapa
def test_continuation_program_falls_back_to_regex():
    """CBSTM03A.CBL uses classic col-7 continuation lines (HTML literals continued across
    lines) — the documented Phase-3 fold boundary. `emit_program` fail-loud-refuses
    (FoldAlignmentError); the adapter falls back to the regex extractor for this one
    program, so its observations are byte-identical to the regex baseline (no loss)."""
    from carddemo_graph.extract.parsers.cobol.normalize import FoldAlignmentError
    path = _CBL / "CBSTM03A.CBL"
    # emit_program itself must refuse (fail-loud, not silently emit a wrong fold).
    with pytest.raises(FoldAlignmentError):
        emit_program(read_source_file(path, "x"), ObservationSink(),
                     workdir=Path(tempfile.mkdtemp(prefix="cbstm03a-")))
    # The adapter falls back -> parity with regex.
    rx = ObservationSink(); extract_cobol(read_source_file(path, "r"), rx)
    mp = ObservationSink(); extract_cobol_mapa(read_source_file(path, "m"), mp)
    assert {_key(o) for o in rx.observations} == {_key(o) for o in mp.observations}


@needs_mapa
@pytest.mark.parametrize("prog", PROGRAMS)
def test_program_construct_parity(prog):
    program_path = _CBL / f"{prog}.cbl"
    regex_sink, mapa_sink = _extract_both(prog)
    rx = _by_rule(regex_sink)
    mp = _by_rule(mapa_sink)

    # Source lines where MAPA emitted a batch-I/O statement — the grammar's ground truth
    # for distinguishing a regex false positive from a real miss.
    mapa_io_lines = {o.provenance[0].start_line for r in _BATCH_IO_RULES
                     for o in mp.get(r, []) if o.provenance}

    problems = []
    for rule in sorted(IMPLEMENTED_RULES):
        rx_by_key = {_key(o): o for o in rx.get(rule, [])}
        mp_by_key = {_key(o): o for o in mp.get(rule, [])}
        # An only_regex payload is a regression UNLESS it is a regex false positive
        # MAPA's grammar correctly drops.
        only_regex = [rx_by_key[k] for k in set(rx_by_key) - set(mp_by_key)
                      if not _is_regex_false_positive(rule, rx_by_key[k], mapa_io_lines)]
        # An only_mapa payload is a regression UNLESS it is a documented improvement.
        only_mapa = [mp_by_key[k] for k in set(mp_by_key) - set(rx_by_key)
                     if not _is_allowed_improvement(rule, mp_by_key[k], program_path)]
        if only_regex or only_mapa:
            problems.append(
                f"\n  [{rule}] only_regex(unexpected)={len(only_regex)} "
                f"only_mapa(unexpected)={len(only_mapa)}"
                + "".join(f"\n    -REGEX {_key(o)}" for o in only_regex)
                + "".join(f"\n    +MAPA  {_key(o)}" for o in only_mapa))
    assert not problems, f"{prog} parity diffs:" + "".join(problems)
