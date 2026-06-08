"""Validation: structural invariants + (later) semantic coverage assertions."""

from carddemo_graph.validation.structural import (
    Issue, Report,
    validate_entities, validate_edges, validate_observations,
    validate_enrichments, validate_file,
)

__all__ = [
    "Issue", "Report",
    "validate_entities", "validate_edges", "validate_observations",
    "validate_enrichments", "validate_file",
]
