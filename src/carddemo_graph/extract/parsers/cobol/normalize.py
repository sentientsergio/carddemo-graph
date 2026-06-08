"""Normalize seam — the (B) origin-map contract: a preprocessed parse coordinate
back to its original (source_path, source_line).

MAPA parses a *preprocessed* form (cols>72 stripped, COPY spliced, blank/continuation
folded), so ANTLR line numbers are preprocessed-line numbers. A `ProvenanceItem` must
carry the *original* line. Approach (B) owns that remap here, in our adapter, derived
from the temp files MAPA already retains under `-saveTemp`. (The upstream patch DOES emit
per-pass `.origin` sidecar records — full `PASS`/`COPY` entries, not a single minimal
sidecar — but those are FILTERED OUT in `parse.py` and NOT consumed: the multi-pass
sidecar composition was a dead-end that mismaps on many-COPY programs. The live remap is
`fold_align` here + content-anchored copybook statement-search in the resolver.) All
coordinate logic lives in this module + `program_provenance.py`.

Two origin maps:

- `identity_origin_map` — the trivial 1:1 map, for when the parsed file *is* the
  source (a standalone copybook fed to MapaTreeDump: no splicing, no fold). DataItem
  provenance uses this.

- `fold_align` — the content-anchored, **fail-loud** aligner that recovers
  fold-line → source-line for the blank-collapse/continuation fold. Lifted from the
  proven `artifacts/parser_foundation/fold_align.py` (the round-trip proof of record).
  Consumed by program-statement provenance [step 3], composed with content-anchored
  copybook statement-search (NOT the `.origin` sidecar, which is filtered out). It
  refuses (raises) rather than emit a silently-wrong edge.

Generalization boundary (load-bearing, see artifacts/parser_provenance_proof.md):
the fold transform CardDemo exercises is blank-collapse + comment preservation only —
it has zero classic continuation lines (col-7 `-`). True continuation-folding (N
source lines → 1 anchored line) is unexercised; `fold_align` is fail-loud on it
(a folded line that matches no single strip line raises). Extending the walk to
consume continuations and anchor to the statement start is slotted for Phase 3.
"""

from __future__ import annotations

from dataclasses import dataclass


class FoldAlignmentError(RuntimeError):
    """The fold could not be aligned to source unambiguously — refuse to emit
    silently-wrong provenance (the "refuse rather than lie" posture)."""


@dataclass(frozen=True)
class OriginMap:
    """Maps a parsed (preprocessed) 1-based line to an original 1-based source line.

    `source_path` is the originating file (a copybook path for spliced lines, the
    program path otherwise). For the DataItem case the parsed file *is* the source,
    so this is the identity over the copybook.
    """
    source_path: str
    _line_map: dict[int, int]

    def source_line(self, parsed_line: int) -> int | None:
        return self._line_map.get(parsed_line)


def identity_origin_map(source_path: str, n_lines: int) -> OriginMap:
    """The 1:1 map for when the parsed file is itself the source."""
    return OriginMap(source_path=source_path,
                     _line_map={i: i for i in range(1, n_lines + 1)})


def _norm(s: str) -> str:
    # the fold preserves columns; only trailing whitespace differs
    return s.rstrip()


def _is_blank(s: str) -> bool:
    return s.strip() == ""


def fold_align(source_lines: list[str], strip_lines: list[str],
               fold_lines: list[str]) -> dict[int, int]:
    """Return {fold_line(1-based): source_line(1-based)} for the blank-collapse fold.

    Per-transform isolation: the column-strip stage (`strip_lines`) is asserted 1:1
    with `source_lines` (line N == line N on cols 1-72), so only the fold needs
    aligning. Alignment is a content-anchored two-pointer walk that skips the lines
    the fold drops (blanks) and asserts per-line content match; ANY divergence raises
    (no silently-wrong edge). Handles leading-blank, blank-collapse, and duplicates
    (the monotonic walk preserves order).

    Raises FoldAlignmentError on: strip not 1:1 with source; a fold line matching no
    strip line (e.g. an unhandled continuation); or an unconsumed non-blank strip line.
    """
    if len(strip_lines) != len(source_lines):
        raise FoldAlignmentError(
            f"col-strip not 1:1: strip={len(strip_lines)} src={len(source_lines)}")
    for i, (a, b) in enumerate(zip(source_lines, strip_lines), 1):
        if a[:72].rstrip() != b[:72].rstrip():
            raise FoldAlignmentError(f"strip diverges from source at line {i}")

    fold_to_src: dict[int, int] = {}
    oi = 0  # index into strip (0-based)
    for fi, fline in enumerate(fold_lines, 1):
        # The fold drops most blanks but may keep an occasional one (e.g. a leading
        # blank). A blank fold line carries no construct, so skip it without consuming
        # a strip line — the next non-blank fold line still anchors correctly.
        if _is_blank(fline):
            continue
        while oi < len(strip_lines) and _is_blank(strip_lines[oi]):
            oi += 1
        if oi >= len(strip_lines):
            raise FoldAlignmentError(f"fold line {fi} ran past end of strip")
        if _norm(fline) != _norm(strip_lines[oi]):
            raise FoldAlignmentError(
                f"fold/strip content mismatch at fold line {fi}: "
                f"{fline.strip()!r} != {strip_lines[oi].strip()!r} "
                f"(unhandled continuation?) — refusing to emit")
        fold_to_src[fi] = oi + 1  # strip line == source line (1:1 proven above)
        oi += 1
    while oi < len(strip_lines):
        if not _is_blank(strip_lines[oi]):
            raise FoldAlignmentError(f"unconsumed non-blank strip line {oi + 1}")
        oi += 1
    return fold_to_src
