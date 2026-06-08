"""Tests for the MAPA grammar-parser foundation — DataItem layer + Normalize seam.

The DataItem tests require the vendored MAPA build artifacts (vendor/mapa/CallTree.jar
+ MapaTreeDump.class, produced by vendor/mapa/build.sh). They skip cleanly if the
build hasn't been run, so a fresh checkout without a JDK still gets a green suite for
the rest. The fold-alignment tests are pure-Python and always run.
"""

from pathlib import Path

import pytest

from carddemo_graph.extract.observation import ObservationSink
from carddemo_graph.extract.sources import read_source_file
from carddemo_graph.extract.cobol import extract_cobol as regex_extract
from carddemo_graph.extract.parsers.cobol import parse
from carddemo_graph.extract.parsers.cobol.adapter import extract_cobol_mapa
from carddemo_graph.extract.parsers.cobol.normalize import (
    fold_align, identity_origin_map, FoldAlignmentError,
)

_REPO = Path(__file__).resolve().parents[1]
_CPY = _REPO / "corpus" / "carddemo" / "stripped" / "app" / "cpy"

try:
    parse.ensure_built()
    _MAPA_BUILT = True
except parse.MapaUnavailable:
    _MAPA_BUILT = False

needs_mapa = pytest.mark.skipif(
    not _MAPA_BUILT, reason="vendor/mapa build artifacts absent (run vendor/mapa/build.sh)")


def _data_items(extractor, path):
    sink = ObservationSink()
    extractor(read_source_file(path, "sf-1"), sink)
    return {
        o.data["id_candidate"]: o.data
        for o in sink.observations
        if o.kind == "entity_candidate" and o.data.get("entity_type") == "DataItem"
    }


@needs_mapa
def test_dataitem_parity_on_gold_copybook():
    """CVACT01Y (Q6.1 gold) — MAPA DataItems byte-match the regex extractor."""
    path = _CPY / "CVACT01Y.cpy"
    r = _data_items(regex_extract, path)
    m = _data_items(extract_cobol_mapa, path)
    assert set(r) == set(m)
    fields = ("name", "level", "picture", "usage", "occurs", "redefines",
              "is_group", "is_filler", "suggested_sql_type", "parent_item")
    for k in r:
        assert {f: r[k][f] for f in fields} == {f: m[k][f] for f in fields}, k


@needs_mapa
def test_picture_preserves_edited_decimal_point():
    """An edited numeric PIC keeps its decimal point (regression guard for the
    '.'-filter bug): -ZZZ,ZZZ,ZZZ.ZZ -> NUMERIC(11,2), not NUMERIC(11)."""
    m = _data_items(extract_cobol_mapa, _CPY / "CVTRA07Y.cpy")
    amt = m["dataitem:CVTRA07Y/TRAN-REPORT-AMT"]
    assert amt["picture"] == "-ZZZ,ZZZ,ZZZ.ZZ"
    assert amt["suggested_sql_type"] == "NUMERIC(11,2)"


@needs_mapa
def test_mapa_catches_plus_sign_edited_pic_regex_misses():
    """Dividend: the '+'-prefixed numeric-edited PIC the regex char class misses is
    caught by MAPA as a typed elementary item (not a group)."""
    r = _data_items(regex_extract, _CPY / "CVTRA07Y.cpy")
    m = _data_items(extract_cobol_mapa, _CPY / "CVTRA07Y.cpy")
    key = "dataitem:CVTRA07Y/REPT-PAGE-TOTAL"
    assert r[key]["is_group"] is True and r[key]["suggested_sql_type"] is None
    assert m[key]["is_group"] is False
    assert m[key]["picture"] == "+ZZZ,ZZZ,ZZZ.ZZ"
    assert m[key]["suggested_sql_type"] == "NUMERIC(11,2)"


# --- Normalize seam (pure Python, always runs) ---

def test_identity_origin_map():
    om = identity_origin_map("x.cpy", 3)
    assert [om.source_line(i) for i in (1, 2, 3)] == [1, 2, 3]
    assert om.source_line(4) is None


def test_fold_align_blank_collapse_and_drift():
    """Blank-collapse fold: post-blank lines drift; alignment recovers true source."""
    source = ["01 A.", "", "05 B PIC X.", "", "", "05 C PIC 9."]
    strip = list(source)                       # col-strip is 1:1
    fold = ["01 A.", "05 B PIC X.", "05 C PIC 9."]   # blanks dropped
    m = fold_align(source, strip, fold)
    assert m == {1: 1, 2: 3, 3: 6}             # fold line 3 -> source line 6 (drift +3)


def test_fold_align_keeps_leading_blank():
    """The fold may keep an occasional blank (e.g. a leading one); a blank fold line
    carries no construct and must not desync the alignment."""
    source = ["", "01 A.", "05 B PIC X."]
    strip = list(source)
    fold = ["", "01 A.", "05 B PIC X."]   # leading blank survives the fold
    m = fold_align(source, strip, fold)
    assert m == {2: 2, 3: 3}              # blank fold line 1 maps nothing; rest exact


def test_fold_align_is_fail_loud_on_mismatch():
    """A folded line matching no strip line raises rather than emitting a wrong edge
    (the 'refuse rather than lie' posture; stands in for an unhandled continuation)."""
    source = ["01 A.", "05 B PIC X."]
    strip = list(source)
    fold = ["01 A.", "05 ZZZ DIFFERENT."]
    with pytest.raises(FoldAlignmentError):
        fold_align(source, strip, fold)


def test_fold_align_rejects_non_1to1_strip():
    with pytest.raises(FoldAlignmentError):
        fold_align(["01 A.", "05 B PIC X."], ["01 A."], ["01 A."])
