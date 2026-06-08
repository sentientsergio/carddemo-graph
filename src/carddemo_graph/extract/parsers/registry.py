"""Parser registry — language tag → Pass-1 extractor.

Adding a grammar parser is registering an adapter here, not re-architecting the
orchestration. Today only COBOL has an alternate (MAPA) adapter; JCL/BMS/CSD/PROC
keep their existing extractors. The registry is the single swap point that
`pilot.py` / `gate3.py` dispatch through.

COBOL parser selection is controlled by the env flag **`CARDDEMO_COBOL_PARSER`**:
- `mapa` (**default**) — the grammar-parser foundation adapter
  (`parsers.cobol.adapter.extract_cobol_mapa`). Blessed as default after Phase-2 proved
  it at full-corpus facts-parity AND demonstrably more correct than regex (it resolves
  copybook-origin reachability the regex path structurally cannot — e.g. Q3.2
  COACTUPC→CSUTLDTC→CEEDAYS via `COPY CSUTLDPY`).
- `regex`            — the hand-tuned regex extractor (`extract.cobol.extract_cobol`).
  Unchanged; remains importable and selectable for the Phase-2 three-way comparison.

The flag (not a code change) is what lets the Phase-2 three-way diff run both paths
over the same corpus.
"""

from __future__ import annotations

import os
from typing import Callable

from carddemo_graph.extract.observation import ObservationSink
from carddemo_graph.extract.sources import SourceFile

Extractor = Callable[[SourceFile, ObservationSink], None]

_COBOL_PARSER_ENV = "CARDDEMO_COBOL_PARSER"
_DEFAULT_COBOL_PARSER = "mapa"


def cobol_parser_choice() -> str:
    return os.environ.get(_COBOL_PARSER_ENV, _DEFAULT_COBOL_PARSER).strip().lower()


def get_cobol_extractor() -> Extractor:
    """Return the COBOL extractor selected by `CARDDEMO_COBOL_PARSER`."""
    choice = cobol_parser_choice()
    if choice == "regex":
        from carddemo_graph.extract.cobol import extract_cobol
        return extract_cobol
    if choice == "mapa":
        from carddemo_graph.extract.parsers.cobol.adapter import extract_cobol_mapa
        return extract_cobol_mapa
    raise ValueError(
        f"unknown {_COBOL_PARSER_ENV}={choice!r} (expected 'regex' or 'mapa')")


def get_extractor(lang: str) -> Extractor:
    """Return the Pass-1 extractor for a pilot/gate3 language tag.

    COBOL routes through the flag; the other languages keep their existing
    extractors (registering a new adapter here is how a parser joins the foundation).
    """
    if lang == "cobol":
        return get_cobol_extractor()
    if lang == "jcl":
        from carddemo_graph.extract.jcl import extract_jcl
        return extract_jcl
    if lang == "proc":
        from carddemo_graph.extract.jcl import extract_proc
        return extract_proc
    if lang == "bms":
        from carddemo_graph.extract.bms import extract_bms
        return extract_bms
    if lang == "csd":
        from carddemo_graph.extract.csd import extract_csd
        return extract_csd
    raise ValueError(f"unknown lang: {lang}")
