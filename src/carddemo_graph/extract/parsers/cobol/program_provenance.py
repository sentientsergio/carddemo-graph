"""Program-construct provenance — map a preprocessed parse-tree construct back to its
ORIGINAL source line (the program, or a spliced copybook), content-validated.

Why this exists (and why it is NOT the multi-pass origin chain): MAPA's CobolParser
requires preprocessed input, so program constructs (CALL / EXEC CICS / SELECT) are read
from the fully COPY-expanded temp, whose line numbers are preprocessed coordinates. The
naive multi-pass `.origin` chain does NOT compose correctly for many-COPY programs
(validated: it silently mismaps on COACTUPC's 57 passes). But we don't need a general
line map — only the lines of the *constructs we emit*, and those are anchorable by
content:

- **Program-native constructs** appear in the folded program (`withoutcontinuations`,
  "woc") in the SAME ORDER as the tree's nodes of that type. We consume woc occurrences
  of each construct's exact line content in order, then map woc->source via the proven
  `fold_align`. (Order-preserving because the constructs are program-native.)
- **Copybook-origin constructs** (e.g. a `CALL` inside a PROCEDURE copybook) are NOT in
  woc; we resolve them by their statement text in the spliced copybooks. (The regex
  extractor never sees these — it only scans program bodies — so they surface as
  three-way-diff *improvements*, carrying copybook provenance.)

**Content-validation is a hard, structural invariant:** every resolution asserts the
mapped line's content matches the construct's own line (operand-strict — the full
verb+operands, so two adjacent same-type constructs can't silently swap). On any
divergence we RAISE (`ProvenanceError`) rather than emit a silently-wrong edge. That
makes a wrong provenance edge impossible by construction; an ordinal desync fails the
check instead of shipping.

Validated exact on CBTRN02C (7 constructs), COACTUPC (17 program-native + 1 copybook),
COCRDUPC (12) — see tests/test_mapa_program_provenance.py.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

from .normalize import fold_align


class ProvenanceError(RuntimeError):
    """A construct could not be resolved to a content-matching source line — refuse to
    emit a silently-wrong provenance edge."""


@dataclass(frozen=True)
class ConstructOrigin:
    source_path: str          # the program path, or a copybook path
    line: int                 # 1-based line in that file
    kind: str                 # "program" | "copybook"


def _read(path: Path) -> list[str]:
    lines = path.read_text(encoding="latin-1").split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def _norm(s: str) -> str:
    return s.rstrip()


def _src_code(line: str) -> str:
    """Source line reduced to its cols-1..72 code area (trailing-stripped). The original
    source may legitimately carry cols-73..80 sequence numbers (not every corpus strips
    them); the preprocessed temps are already cols<=72, so the program-native content
    check must compare like-for-like — cols 1..72 both sides — exactly as `fold_align`
    does. Without this, a construct on a sequence-numbered line fails content-validation
    spuriously (surfaced by COBSWAIT's seq-numbered PROGRAM-ID line)."""
    return line[:72].rstrip()


def _code_text(line: str) -> str:
    """COBOL code area (cols 8-72), stripped — drops the cols-1-6 sequence area and the
    col-7 indicator so a copybook's own sequence numbers don't defeat the match."""
    return line[7:72].strip() if len(line) >= 7 else line.strip()


class ProgramConstructResolver:
    """Resolves preprocessed top-temp construct lines to original provenance.

    Built from one CallTree `-saveTemp` run's temps + the program source + the copybook
    harness. `resolve(top_line)` returns a content-validated ConstructOrigin or raises.
    """

    def __init__(self, *, tempdir: Path, program_stem: str,
                 program_source: Path, top_temp: Path, copy_dir: Path):
        self._src_path = str(program_source)
        self._src = _read(program_source)
        self._top = _read(top_temp)
        woc = _read(_one(tempdir, f"CallTree-{program_stem}-withoutcontinuations-*-cbl"))
        w73 = _read(_one(tempdir, f"CallTree-{program_stem}-without73to80-*-cbl"))
        # folded(woc) line -> source line (fail-loud); proven blank-collapse alignment.
        self._fold_to_src = fold_align(self._src, w73, woc)
        # woc content -> queue of its 1-based line numbers, consumed in document order.
        self._woc_occ: dict[str, deque[int]] = defaultdict(deque)
        for i, line in enumerate(woc, 1):
            self._woc_occ[_norm(line)].append(i)
        self._copy_dir = copy_dir
        self._copy_cache: dict[str, list[str]] = {}

    def resolve(self, top_line: int) -> ConstructOrigin:
        """Map a 1-based top-temp line to its content-validated original provenance."""
        content = _norm(self._top[top_line - 1])
        occ = self._woc_occ.get(content)
        if occ:
            woc_line = occ.popleft()
            src_line = self._fold_to_src.get(woc_line)
            if src_line is None or _src_code(self._src[src_line - 1]) != content:
                raise ProvenanceError(
                    f"program-native construct at top line {top_line} did not "
                    f"content-validate against source: {content!r}")
            return ConstructOrigin(self._src_path, src_line, "program")
        # Not program-native -> copybook-origin. Match the statement text in a copybook.
        stmt = content.strip()
        hit = self._find_in_copybooks(stmt)
        if hit is None:
            raise ProvenanceError(
                f"construct at top line {top_line} is neither program-native nor "
                f"resolvable in any copybook: {content!r}")
        path, line = hit
        return ConstructOrigin(path, line, "copybook")

    def _find_in_copybooks(self, stmt: str) -> tuple[str, int] | None:
        for cf in sorted(self._copy_dir.iterdir()):
            if not cf.is_file():
                continue
            key = str(cf)
            if key not in self._copy_cache:
                try:
                    self._copy_cache[key] = _read(cf)
                except OSError:
                    self._copy_cache[key] = []
            for i, line in enumerate(self._copy_cache[key], 1):
                if _code_text(line) == stmt:
                    # resolve the symlink back to the real copybook path
                    return str(cf.resolve()), i
        return None


def _one(tempdir: Path, pattern: str) -> Path:
    import glob
    hits = sorted(glob.glob(str(tempdir / pattern)))
    if not hits:
        raise ProvenanceError(f"missing temp {pattern} in {tempdir}")
    return Path(hits[0])
