"""COBOL adapter on the grammar-parser foundation — orchestrates parse → normalize
→ map for one source file, emitting the existing Observation contract.

Routing (all three COBOL surfaces now on the grammar-parser foundation):
- **Copybook record layouts → DataItems via MAPA** (`map_dataitem`; parse-tree walk +
  reused `_suggested_sql_type`). Q6 gold parity.
- **Programs → program constructs via MAPA** (`map_program`; CallTree + the
  content-validated `ProgramConstructResolver`). PROGRAM-ID / file-control / CALL /
  COPY-INCLUDES / batch-I/O / EXEC-CICS, all at full-corpus facts-parity with the regex
  baseline (see `tests/test_mapa_program_emission.py`). No double-emit: copybooks are
  data-only (program scans emit nothing for them) and programs carry no DataItems.
- **BMS symbolic-map copybooks → the regex path.** A `cpy-bms` file is a generated
  symbolic-map structure, not a compilation unit and not a record layout; it stays on
  the existing extractor (which emits its Copybook-presence/COPY observations), exactly
  as before the program flip — unchanged behaviour.

The mapping layer is generic over the COBOL grammar; there is no CardDemo-specific
handling in this bridge (the anti-pattern). The only corpus-shaped assumption is the
source-tree layout (`map_program` derives a program's copybook dirs from sibling
`cpy`/`cpy-bms`), flagged there as filesystem convention. `pilot.py` / `gate3.py`
dispatch COBOL through the registry, which returns this adapter under the `mapa` flag.
"""

from __future__ import annotations

from carddemo_graph.extract.observation import ObservationSink
from carddemo_graph.extract.sources import SourceFile

from . import parse
from .normalize import identity_origin_map, FoldAlignmentError
from .map_dataitem import emit_data_items
from .map_program import emit_program
from .program_provenance import ProvenanceError

# Documented boundaries on which the program emitter fail-loud-refuses rather than emit a
# wrong edge (see RESUME §3 "generalization boundary"): classic col-7 continuation lines
# (`fold_align` cannot align an N-line→1 fold yet — Phase-3 work) and any construct that
# fails content-validation. CardDemo has exactly one such program (CBSTM03A.CBL: HTML
# literals continued across col-7). On these we fall back to the frozen regex extractor
# for that ONE program — the pipeline stays whole and correct, the boundary stays honest,
# and continuation-folding is picked up in Phase 3. `emit_program` raises during resolver
# construction, before any observation is emitted, so the fallback never double-emits.
_PROGRAM_BOUNDARY = (FoldAlignmentError, ProvenanceError, parse.MapaParseError)


def _is_copybook(src: SourceFile) -> bool:
    return (src.path.suffix in (".cpy", ".CPY")
            or "/cpy" in str(src.path).replace("\\", "/"))


def _is_bms_copybook(src: SourceFile) -> bool:
    # BMS-generated symbolic maps are modeled as BMSField entities, not DataItems
    # (mirrors cobol.py::_scan_data_items scope).
    return "cpy-bms" in str(src.path).lower()


def extract_cobol_mapa(src: SourceFile, sink: ObservationSink) -> None:
    """Registry entry point (mirrors `extract.cobol.extract_cobol`'s signature)."""
    if _is_copybook(src):
        if _is_bms_copybook(src):
            # BMS symbolic-map copybook — keep on the regex path (unchanged).
            from carddemo_graph.extract.cobol import extract_cobol as _regex_extract
            _regex_extract(src, sink)
            return
        _extract_copybook_dataitems(src, sink)
        return
    # Programs — grammar-parser construct emission (CallTree + resolver).
    try:
        emit_program(src, sink)
    except _PROGRAM_BOUNDARY as e:
        # Documented fail-loud boundary (e.g. col-7 continuations) — fall back to the
        # frozen regex extractor for this one program. Surfaced, not swallowed.
        import sys
        print(f"[mapa] {src.path.name}: program emitter hit a documented boundary "
              f"({type(e).__name__}); falling back to regex for this file. {e}",
              file=sys.stderr)
        from carddemo_graph.extract.cobol import extract_cobol as _regex_extract
        _regex_extract(src, sink)


def _extract_copybook_dataitems(src: SourceFile, sink: ObservationSink) -> None:
    # Lenient: a copybook may be a PROCEDURE-division code fragment (not a standalone
    # compilation unit) — that yields syntax errors but zero data-description entries,
    # so the data-layer walk emits nothing, matching the regex extractor's behavior on
    # the same file. ANTLR error-recovery still builds a tree for any data entries that
    # do parse. (Surveyed: only the two code-fragment copybooks error; both yield 0
    # DataItems in both the regex and MAPA paths.)
    tree, _errs = parse.dump_tree_lenient(src.path)
    # A standalone copybook is parsed as-is: tree line numbers are the copybook's own
    # source lines, so the origin map is the identity (no splice/fold to undo).
    origin = identity_origin_map(str(src.path), len(src.lines))
    emit_data_items(
        tree=tree,
        copybook_stem=src.path.stem,
        lines=src.lines,
        origin=origin,
        source_file_id=src.record.id,
        source_hash=src.record.source_hash,
        sink=sink,
    )
