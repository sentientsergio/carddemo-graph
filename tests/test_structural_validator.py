"""Negative-case tests for the structural validator.

Each test feeds intentionally-broken input and asserts the validator reports the
expected error. This protects against silent validator regressions.
"""

import json
import pytest

from carddemo_graph.validation.structural import (
    validate_entities, validate_edges, validate_observations,
    validate_enrichments,
)


def _envelope(payload_extra):
    base = {
        "schema_version": "1.0.0",
        "extractor_version": "test",
        "run_id": "test-run",
        "corpus_hash": "test:corpus",
        "source_files": [
            {
                "id": "sf-1",
                "path": "test.cbl",
                "source_hash": "h",
                "normalized_source_hash": "h-n",
                "encoding": "utf-8",
                "language": "COBOL",
                "parse_status": "ok",
            }
        ],
    }
    base.update(payload_extra)
    return base


_GOOD_PROV = [
    {
        "source_path": "test.cbl",
        "start_line": 1,
        "end_line": 1,
        "source_file_id": "sf-1",
        "source_hash": "h",
    }
]


def test_entity_duplicate_id_is_error():
    payload = _envelope({"entities": [
        {"id": "program:A", "type": "Program", "name": "A", "provenance": _GOOD_PROV},
        {"id": "program:A", "type": "Program", "name": "A", "provenance": _GOOD_PROV},
    ]})
    r = validate_entities(payload, "test")
    assert not r.ok()
    assert any("duplicate entity id" in i.message for i in r.errors)


def test_entity_bad_id_pattern_is_error():
    payload = _envelope({"entities": [
        {"id": "NotAValidId", "type": "Program", "name": "A", "provenance": _GOOD_PROV},
    ]})
    r = validate_entities(payload, "test")
    assert not r.ok()
    assert any("does not match pattern" in i.message for i in r.errors)


def test_entity_unknown_type_is_error():
    payload = _envelope({"entities": [
        {"id": "program:A", "type": "Wonderprogram", "name": "A", "provenance": _GOOD_PROV},
    ]})
    r = validate_entities(payload, "test")
    assert not r.ok()
    assert any("unknown entity type" in i.message for i in r.errors)


def test_edge_missing_confidence_is_error():
    payload = _envelope({"edges": [
        {
            "id": "e1", "type": "INCLUDES", "from": "program:A", "to": "copybook:B",
            # confidence missing
            "evidence_kind": "deterministic", "rule_id": "RUL-COBOL-002",
            "provenance": _GOOD_PROV,
        },
    ]})
    r = validate_edges(payload, "test")
    assert not r.ok()
    assert any("missing required edge field: confidence" in i.message for i in r.errors)


def test_edge_confidence_out_of_range_is_error():
    payload = _envelope({"edges": [
        {
            "id": "e1", "type": "INCLUDES", "from": "program:A", "to": "copybook:B",
            "confidence": 1.5,
            "evidence_kind": "deterministic", "rule_id": "RUL-COBOL-002",
            "provenance": _GOOD_PROV,
        },
    ]})
    r = validate_edges(payload, "test")
    assert not r.ok()
    assert any("confidence must be number in [0,1]" in i.message for i in r.errors)


def test_edge_llm_candidate_is_forbidden():
    payload = _envelope({"edges": [
        {
            "id": "e1", "type": "INCLUDES", "from": "program:A", "to": "copybook:B",
            "confidence": 0.8,
            "evidence_kind": "llm_candidate",
            "rule_id": "RUL-COBOL-002",
            "provenance": _GOOD_PROV,
        },
    ]})
    r = validate_edges(payload, "test")
    assert not r.ok()
    assert any("llm_candidate must never appear in edges.json" in i.message for i in r.errors)


def test_edge_bad_rule_id_is_error():
    payload = _envelope({"edges": [
        {
            "id": "e1", "type": "INCLUDES", "from": "program:A", "to": "copybook:B",
            "confidence": 1.0,
            "evidence_kind": "deterministic",
            "rule_id": "rule-cobol-2",  # wrong shape
            "provenance": _GOOD_PROV,
        },
    ]})
    r = validate_edges(payload, "test")
    assert not r.ok()
    assert any("does not match RUL-" in i.message for i in r.errors)


def test_edge_empty_provenance_is_error():
    payload = _envelope({"edges": [
        {
            "id": "e1", "type": "INCLUDES", "from": "program:A", "to": "copybook:B",
            "confidence": 1.0,
            "evidence_kind": "deterministic",
            "rule_id": "RUL-COBOL-002",
            "provenance": [],
        },
    ]})
    r = validate_edges(payload, "test")
    assert not r.ok()
    assert any("non-empty array" in i.message for i in r.errors)


def test_observation_llm_candidate_requires_prompt_template_id():
    payload = _envelope({"observations": [
        {
            "id": "o1", "kind": "edge_candidate",
            "evidence_kind": "llm_candidate",
            "rule_id": "RUL-COBOL-012",
            "provenance": _GOOD_PROV,
            # prompt_template_id and category missing
        },
    ]})
    r = validate_observations(payload, "test")
    assert not r.ok()
    msgs = [i.message for i in r.errors]
    assert any("prompt_template_id" in m for m in msgs)
    assert any("category" in m for m in msgs)


def test_enrichment_evidence_kind_must_be_inferred():
    payload = _envelope({"enrichments": [
        {
            "id": "enrich-001", "entity_id": "program:A",
            "property": "inferred_purpose", "value": "some inferred summary",
            "evidence_kind": "deterministic",   # wrong — must be 'inferred'
            "prompt_template_id": "PT-1",
            "source_observations": ["obs-001"],
            "confidence": 0.8,
            "provenance": _GOOD_PROV,
        }
    ]})
    r = validate_enrichments(payload, "test")
    assert not r.ok()
    assert any("must be 'inferred'" in i.message for i in r.errors)


def test_enrichment_missing_prompt_template_id_is_error():
    payload = _envelope({"enrichments": [
        {
            "id": "enrich-001", "entity_id": "program:A",
            "property": "inferred_purpose", "value": "x",
            "evidence_kind": "inferred",
            # prompt_template_id missing
            "source_observations": ["obs-001"],
            "confidence": 0.8,
            "provenance": _GOOD_PROV,
        }
    ]})
    r = validate_enrichments(payload, "test")
    assert not r.ok()
    assert any("prompt_template_id" in i.message for i in r.errors)


def test_enrichment_bad_entity_id_pattern_is_error():
    payload = _envelope({"enrichments": [
        {
            "id": "enrich-001", "entity_id": "NotAValidId",
            "property": "inferred_purpose", "value": "x",
            "evidence_kind": "inferred", "prompt_template_id": "PT-1",
            "source_observations": ["obs-001"], "confidence": 0.8,
            "provenance": _GOOD_PROV,
        }
    ]})
    r = validate_enrichments(payload, "test")
    assert not r.ok()
    assert any("does not match pattern" in i.message for i in r.errors)


def test_enrichment_empty_array_is_valid():
    """v1 ships enrichments.json with empty enrichments array — must validate clean."""
    payload = _envelope({"enrichments": []})
    r = validate_enrichments(payload, "test")
    assert r.ok(), f"empty enrichments should validate; errors: {r.errors}"


def test_provenance_inverted_lines_is_error():
    payload = _envelope({"entities": [
        {
            "id": "program:A", "type": "Program", "name": "A",
            "provenance": [
                {
                    "source_path": "test.cbl",
                    "start_line": 10, "end_line": 5,  # inverted
                    "source_file_id": "sf-1", "source_hash": "h",
                }
            ],
        }
    ]})
    r = validate_entities(payload, "test")
    assert not r.ok()
    assert any("start_line" in i.message and "> end_line" in i.message for i in r.errors)
