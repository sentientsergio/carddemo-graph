"""Grammar-parser foundation for Pass-1 extraction.

A pluggable foundation that accepts N>1 grammar parsers over the language roadmap
(COBOL now; JCL/assembler later). Three seams + a registry:

- parse     — vendor parser → parse tree (per-language, swappable)
- normalize — parse coordinate → original (source_path, line) provenance
- map       — tree walk → the existing `Observation` contract (unchanged)
- registry  — language tag → extractor (the single dispatch swap point)

The downstream contract (Observation shape, Pass-3 resolver, gold, Q1-Q5) does NOT
change — that invariance is how the methodology is proven to survive the parser swap.
"""

from carddemo_graph.extract.parsers.registry import get_extractor, get_cobol_extractor

__all__ = ["get_extractor", "get_cobol_extractor"]
