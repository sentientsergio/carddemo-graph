"""Parse seam — invoke the vendored MAPA parser and return raw parse artifacts.

This isolates *how* we get a parse tree (subprocess to a Java jar) from the
mapping that turns it into Observations. Two surfaces, both from the one vendored
MAPA toolchain (see `vendor/mapa/`):

- `dump_tree(path)`  — MapaTreeDump → the full ANTLR parse tree as nested dicts
                       `{"r": rule, "ln": startLine, "le": endLine, "k": [...]}`,
                       terminals as bare strings. Feeds the COBOL data layer.
- `call_tree(...)`   — MAPA's CallTree CSV (CALL/DD/CICS/COPY) + `-saveTemp`
                       origin sidecars. [Wired in step 3 for program emission.]

Nothing here is CardDemo-specific: it shells out to MAPA over an arbitrary COBOL
file. The vendored jar + MapaTreeDump.class are build artifacts produced by
`vendor/mapa/build.sh`; if absent we raise a clear instruction rather than a
cryptic subprocess error.
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

# parsers/cobol/parse.py -> .../carddemo_graph/extract/parsers/cobol
_REPO_ROOT = Path(__file__).resolve().parents[5]
_VENDOR = _REPO_ROOT / "vendor" / "mapa"
_JAR = _VENDOR / "CallTree.jar"
_ANTLR = _VENDOR / "upstream" / "antlr-4.13.2-complete.jar"
_TREEDUMP_DIR = _VENDOR                      # MapaTreeDump.class lives here
_TREEDUMP_MAIN = "MapaTreeDump"

_BUILD_HINT = (
    "MAPA build artifacts not found under vendor/mapa/. Run `vendor/mapa/build.sh` "
    "(requires a JDK on PATH) to produce CallTree.jar + MapaTreeDump.class."
)


class MapaUnavailable(RuntimeError):
    """The vendored MAPA build artifacts are missing — build.sh has not been run."""


class MapaParseError(RuntimeError):
    """MAPA could not parse the file cleanly (syntax errors or process failure)."""


def _classpath() -> str:
    return f"{_TREEDUMP_DIR}:{_JAR}:{_ANTLR}"


def ensure_built() -> None:
    """Raise MapaUnavailable with a build hint if the artifacts are missing."""
    missing = [p for p in (_JAR, _ANTLR, _TREEDUMP_DIR / f"{_TREEDUMP_MAIN}.class")
               if not p.exists()]
    if missing:
        raise MapaUnavailable(f"{_BUILD_HINT}  (missing: {[str(m) for m in missing]})")


def dump_tree(cobol_path: Path) -> dict:
    """Parse a (fixed-format) COBOL file with MAPA's CobolParser; return the ANTLR
    parse tree as nested dicts. Raises MapaParseError on any syntax error so a bad
    parse never silently yields a partial tree (the strict default, for programs).

    Line numbers in the returned tree are 1-based lines *of the file passed in*.
    For a standalone copybook that is the copybook's own line numbering (no COPY
    splicing/folding happens), so DataItem provenance maps 1:1 to source.
    """
    tree, errs = dump_tree_lenient(cobol_path)
    if errs:
        raise MapaParseError(f"MAPA reported {errs} syntax error(s) parsing {cobol_path}")
    return tree


def dump_tree_lenient(cobol_path: Path) -> tuple[dict, int]:
    """Like `dump_tree` but tolerant: return `(tree, syntax_error_count)` and let the
    caller decide. ANTLR error-recovery still builds a tree on a partial parse.

    Used for copybooks: a copybook may be a PROCEDURE-division code fragment (not a
    standalone compilation unit), which yields syntax errors but zero data entries —
    the data-layer walk then correctly emits nothing, matching the regex extractor.
    """
    ensure_built()
    with _col_stripped_temp(cobol_path) as stripped:
        # Run in a scratch cwd: MAPA's logger writes TestIntegration-<ts>.log to the
        # working directory; we don't want that littering the repo tree.
        proc = subprocess.run(
            ["java", "-cp", _classpath(), _TREEDUMP_MAIN, str(stripped)],
            capture_output=True, text=True, cwd=tempfile.gettempdir(),
        )
    if proc.returncode != 0:
        raise MapaParseError(
            f"MapaTreeDump failed on {cobol_path} (rc={proc.returncode}): "
            f"{proc.stderr.strip()[:500]}")
    errs = _syntax_error_count(proc.stderr)
    try:
        return json.loads(proc.stdout), errs
    except json.JSONDecodeError as e:
        raise MapaParseError(f"MapaTreeDump produced invalid JSON for {cobol_path}: {e}")


@dataclass
class CallTreeResult:
    """Artifacts from one CallTree `-saveTemp` run over a program.

    - `csv_text`     — the CallTree CSV (FILE/PGM/COPY/CALL/DD/CICS* rows).
    - `tempdir`      — the `-saveTemp` directory (numbered COPY-expansion passes,
                       per-file without73to80/withoutcontinuations, `.origin` sidecars).
    - `top_temp`     — the final fully-expanded pass temp (what MapaTreeDump parses for
                       program constructs).
    - `program_stem` — e.g. "CBTRN02C.cbl" (the temp-name stem).
    """
    csv_text: str
    tempdir: Path
    top_temp: Path
    program_stem: str


def build_copybook_harness(copy_src_dir: Path, dest_dir: Path) -> Path:
    """Stage copybooks under the bare names MAPA's COPY resolver expects.

    MAPA resolves a `COPY NAME` to `<path>/NAME` (no extension), so we symlink each
    `NAME.cpy` / `NAME.CPY` to a bare `NAME` in `dest_dir`. Generic file-name handling,
    not CardDemo semantics.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted(copy_src_dir.iterdir()):
        if not f.is_file():
            continue
        bare = dest_dir / f.stem
        if not bare.exists():
            bare.symlink_to(f.resolve())
    return dest_dir


def call_tree(program_path: Path, copy_dir: Path, workdir: Path) -> CallTreeResult:
    """Run MAPA's CallTree with `-saveTemp` over a program; return the CSV + temps.

    `copy_dir` is a bare-name copybook harness (see build_copybook_harness). `workdir`
    is where MAPA writes its CSV + log (kept out of the repo tree).
    """
    ensure_built()
    workdir.mkdir(parents=True, exist_ok=True)
    out_csv = workdir / "calltree.csv"
    log = workdir / "calltree.log"
    with open(log, "w") as errf:
        proc = subprocess.run(
            ["java", "-jar", str(_JAR), "-file", str(program_path),
             "-copy", str(copy_dir), "-saveTemp", "-out", str(out_csv)],
            stdout=subprocess.DEVNULL, stderr=errf, cwd=str(workdir),
        )
    if proc.returncode != 0:
        raise MapaParseError(f"CallTree failed on {program_path} (rc={proc.returncode})")
    tempdir = _read_tempdir(log)
    if tempdir is None:
        raise MapaParseError(f"could not locate CallTree -saveTemp dir for {program_path}")
    stem = program_path.name  # e.g. CBTRN02C.cbl
    # Numbered COPY-expansion passes only — exactly 5 digits then a dash, so we don't
    # accidentally match the non-numbered intermediate temp (CallTree-<stem>-<hash>-cbl).
    passes = sorted(glob.glob(str(tempdir / f"CallTree-{stem}-[0-9][0-9][0-9][0-9][0-9]-*-cbl")))
    passes = [p for p in passes if not p.endswith(".origin")]
    if not passes:
        raise MapaParseError(f"no COPY-expansion passes for {program_path} in {tempdir}")
    csv_text = out_csv.read_text(encoding="latin-1") if out_csv.exists() else ""
    return CallTreeResult(csv_text=csv_text, tempdir=tempdir,
                          top_temp=Path(passes[-1]), program_stem=stem)


def parse_temp_tree(temp_path: Path) -> dict:
    """Dump the ANTLR parse tree of an already-preprocessed temp (no col-strip — the
    `-saveTemp` temps are already preprocessed)."""
    ensure_built()
    proc = subprocess.run(
        ["java", "-cp", _classpath(), _TREEDUMP_MAIN, str(temp_path)],
        capture_output=True, text=True, cwd=tempfile.gettempdir(),
    )
    if proc.returncode != 0:
        raise MapaParseError(f"MapaTreeDump failed on {temp_path} (rc={proc.returncode})")
    return json.loads(proc.stdout)


def _read_tempdir(log_path: Path) -> Path | None:
    for line in log_path.read_text(encoding="latin-1", errors="replace").splitlines():
        if "Temporary files are in" in line:
            return Path(line.split("are in ", 1)[1].strip())
    return None


class _col_stripped_temp:
    """Write a cols-1..72 view of `path` to a temp file MapaTreeDump can parse.

    MapaTreeDump feeds the file straight to the lexer (no preprocessor), so columns
    73-80 (the COBOL identification area) would otherwise leak into tokens and corrupt
    e.g. PICTURE strings. The column strip is 1:1 with source (line N == line N), so
    tree line numbers remain valid source line numbers (identity origin map holds).
    Encoding mirrors the proof harness (latin-1 round-trips any byte).
    """

    def __init__(self, path: Path):
        self._src = path
        self._tmp: Path | None = None

    def __enter__(self) -> Path:
        text = self._src.read_text(encoding="latin-1")
        stripped = "\n".join(line[:72] for line in text.split("\n"))
        fd = tempfile.NamedTemporaryFile(
            mode="w", suffix=".cbl", prefix=f"{self._src.stem}-strip-",
            encoding="latin-1", delete=False)
        try:
            fd.write(stripped)
        finally:
            fd.close()
        self._tmp = Path(fd.name)
        return self._tmp

    def __exit__(self, *exc) -> None:
        if self._tmp is not None:
            self._tmp.unlink(missing_ok=True)


def _syntax_error_count(stderr: str) -> int:
    for line in stderr.splitlines():
        line = line.strip()
        if line.startswith("SYNTAX_ERRORS="):
            try:
                return int(line.split("=", 1)[1])
            except ValueError:
                return 0
    return 0
