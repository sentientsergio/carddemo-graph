"""Proof test for the program-construct provenance composer.

Runs the real Parse seam (MAPA CallTree `-saveTemp` + MapaTreeDump) over three
many-COPY programs — two CICS-heavy — and asserts EVERY emitted-construct line
(CALL / EXEC CICS / SELECT) resolves to a content-validated original source or
copybook line. resolve() is fail-loud, so a wrong map raises rather than passing.

Skips cleanly if the vendored MAPA build is absent (vendor/mapa/build.sh).
"""

import tempfile
from pathlib import Path

import pytest

from carddemo_graph.extract.parsers.cobol import parse
from carddemo_graph.extract.parsers.cobol.program_provenance import (
    ProgramConstructResolver, ConstructOrigin,
)

_REPO = Path(__file__).resolve().parents[1]
_CBL = _REPO / "corpus" / "carddemo" / "stripped" / "app" / "cbl"
_CPY = _REPO / "corpus" / "carddemo" / "stripped" / "app" / "cpy"

try:
    parse.ensure_built()
    _BUILT = True
except parse.MapaUnavailable:
    _BUILT = False

needs_mapa = pytest.mark.skipif(
    not _BUILT, reason="vendor/mapa build artifacts absent (run vendor/mapa/build.sh)")

# (rule name, verb keyword expected on the resolved line)
_RULES = [("callStatement", "CALL"),
          ("execCicsStatement", "EXEC"),
          ("fileControlEntry", "SELECT")]


def _find(node, rule, out):
    if isinstance(node, dict):
        if node.get("r") == rule:
            out.append(node)
        for c in node.get("k", []):
            _find(c, rule, out)


_RESOLVE_CACHE: dict[str, tuple] = {}


def _resolve_all(program: Path):
    if str(program) in _RESOLVE_CACHE:
        return _RESOLVE_CACHE[str(program)]
    work = Path(tempfile.mkdtemp(prefix="prov-"))
    harness = parse.build_copybook_harness(_CPY, work / "cpy")
    ct = parse.call_tree(program, harness, work)
    tree = parse.parse_temp_tree(ct.top_temp)
    resolver = ProgramConstructResolver(
        tempdir=ct.tempdir, program_stem=ct.program_stem,
        program_source=program, top_temp=ct.top_temp, copy_dir=harness)

    program_src = program.read_text(encoding="latin-1").split("\n")
    results = []
    for rule, kw in _RULES:
        nodes = []
        _find(tree, rule, nodes)
        nodes.sort(key=lambda n: n["ln"])
        for n in nodes:
            origin = resolver.resolve(n["ln"])   # raises on content-validation failure
            results.append((rule, kw, origin))
    _RESOLVE_CACHE[str(program)] = (results, program_src)
    return results, program_src


@needs_mapa
@pytest.mark.parametrize("prog,min_constructs", [
    ("CBTRN02C.cbl", 7),
    ("COACTUPC.cbl", 18),
    ("COCRDUPC.cbl", 12),
    # COBSWAIT keeps cols-73..80 sequence numbers (the corpus did not strip them); its
    # single CALL resolves through the cols 1..72 like-for-like content check. The
    # PROGRAM-ID seq-number case (the one that surfaced the bug) is guarded by the
    # emission harness, which resolves programIdParagraph.
    ("COBSWAIT.cbl", 1),
])
def test_program_provenance_exact(prog, min_constructs):
    results, program_src = _resolve_all(_CBL / prog)
    assert len(results) >= min_constructs, (prog, len(results))
    for rule, kw, origin in results:
        assert isinstance(origin, ConstructOrigin)
        assert origin.kind in ("program", "copybook")
        # operand-strict: the resolved line carries the construct's verb
        line = Path(origin.source_path).read_text(encoding="latin-1").split("\n")[origin.line - 1]
        assert kw.upper() in line.upper(), (prog, rule, origin, line)


@needs_mapa
def test_copybook_origin_call_is_attributed_to_copybook():
    """COACTUPC's `CALL 'CSUTLDTC'` lives in the CSUTLDPY procedure copybook, not the
    program — its provenance must point at the copybook (and regex never sees it)."""
    results, _ = _resolve_all(_CBL / "COACTUPC.cbl")
    calls = [o for r, kw, o in results if r == "callStatement"]
    assert any(o.kind == "copybook" and "CSUTLDPY" in o.source_path for o in calls), calls
