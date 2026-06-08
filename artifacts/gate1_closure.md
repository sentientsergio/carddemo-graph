# Gate 1 Closure — Schema and Deterministic-Pass Review

**Per spec v4 §Gate 1, with v4.1 kuzu substrate folded in.**

## Deliverables produced

| Spec requirement | Artifact | Status |
|---|---|---|
| Finalized entity and edge schemas | `artifacts/schema.json` (JSON Schema, `schema_version: 1.0.0`) | ✅ |
| Canonical ID rules | `artifacts/schema.json` (`EntityId` pattern), `artifacts/deterministic_rules.md` (per-rule emissions) | ✅ |
| Confidence and evidence-kind rules | `artifacts/schema.json` (`Confidence`/`EvidenceKind` defs), `artifacts/deterministic_rules.md` §Confidence calibration | ✅ |
| Deterministic rule inventory with `rule_id`s | `artifacts/deterministic_rules.md` (38 rules across COBOL/JCL/JCL-PROC/BMS/CSD/ASM/DERIV/RES/NEG) | ✅ |
| 5 sample entities | `artifacts/sample_entities.json` (Program, Copybook, JCLJob, BMSMapset, CICSTransaction — all real CardDemo entities with verified line ranges) | ✅ |
| 5 sample edges | `artifacts/sample_edges.json` (INCLUDES, IS_TRANSACTION_FOR, SENDS_MAP, INVOKES, BINDS_TO) | ✅ |
| Sample `observations.json` fragment | `artifacts/sample_observations.json` (entity_candidate, edge_candidate, anomaly, llm_candidate — exercises every observation kind) | ✅ |
| v4.1 addition: kuzu schema mapping | `artifacts/kuzu_schema.cypher` (13 node tables, 21 rel tables) | ✅ |

## Exit criteria check

Per spec §Gate 1 "exit when":

| Criterion | Evidence |
|---|---|
| Gate 0 implications incorporated | `deterministic_rules.md` covers all 9 anomalies from corpus profile (multi-line PROGRAM-ID → RUL-COBOL-001 explicit clause; PROC-name collision → RUL-JCL-PROC-001 + RUL-RES-006; phantom program → RUL-CSD-002 `partial:true` flow; etc.) |
| Rule inventory signed off | **Pending sponsor AT review.** Engineer-authored, Reviewer-A only. |
| Samples pass structural invariants | `src/carddemo_graph/validation/structural.py` validator runs clean on all three sample files (0 errors, 0 warnings). 10/10 negative-case tests confirm the validator catches each invariant violation. kuzu schema smoke-applies (13 NODE + 21 REL tables created). |

## Engineering proof points

- **Structural validator** at `src/carddemo_graph/validation/structural.py`. Pure stdlib. Enforces: entity ID uniqueness + canonical pattern; edge required fields (id/type/from/to/confidence/evidence_kind/rule_id/provenance); confidence ∈ [0,1]; rule_id shape `RUL-<LANG>(-<SUB>)*-NNN`; `llm_candidate` forbidden in `edges.json`; `llm_candidate` observation requires `prompt_template_id` + `category`; non-empty provenance with required fields; well-ordered line ranges; enum membership for entity/edge types.
- **Negative-case tests** at `tests/test_structural_validator.py` (10 tests, all passing). Each invariant has a paired failing-case assertion so future schema changes can't silently bypass invariants.
- **Kuzu smoke test** (transient, not committed): the full DDL applies cleanly to a fresh kuzu DB and produces exactly 13 NODE tables and 21 REL tables, matching schema.json's EntityType (12 typed + Unresolved) and EdgeType (21 edge types) enums.

## Key decisions encoded in the schema

1. **`Unresolved` is a separate kuzu node table.** Per spec ("Unresolved references emit as `Unresolved` placeholders…Never dropped"), genuinely unresolved references get a distinct node type. Multi-typed rel tables (`CALLS`, `LINKS_TO`, `XCTLS_TO`, `INVOKES`, `IS_TRANSACTION_FOR`) accept either the typed target OR `Unresolved`, so dynamic CALLs and phantom programs still produce traversable edges. The negation rule `RUL-NEG-001` enforces that a dynamic CALL never silently promotes to a typed Program target.
2. **`partial: true` is a property of the typed entity**, not a separate type. Used when the entity *type* is known (e.g., `Program` for COCRDSEC, where CSD `DEFINE PROGRAM` confirms the type, but no source body exists).
3. **`BINDS_TO` is the only path from `Program` to `Dataset`.** There is no direct Program→Dataset edge type in the vocabulary. The schema enforces this both structurally (no such edge type exists in `_EDGE_TYPES`) and via the validator's `RUL-NEG-002` guard.
4. **`USES_DATASET` carries both `allocation_disposition` (raw DISP) and `inferred_access_mode`** (semantic access mode derived via RUL-DERIV-011). Q2's JCL access report reads `inferred_access_mode`; raw DISP is available alongside for spot-checks.
5. **PROC canonical-id authority.** The `//name PROC` declared name is authoritative over filename (analog of PROGRAM-ID rule). The CardDemo-specific case — `TRANREPT.prc` declaring itself as `REPROC` and colliding with `REPROC.prc` — is exercised in `sample_observations.json` as obs-003/obs-004/obs-005 to prove the conflict-ledger path round-trips through the deterministic rules.
6. **LLM-candidate rails are in place from the first observation.** `Observation.evidence_kind = llm_candidate` requires `prompt_template_id` and `category` per spec §Pass 2; the validator enforces this; the sample fragment includes an `llm_candidate` example (obs-006) with all required fields. When Pass 2 actually runs (deferred per blocker-resolution directive), no retrofit is needed.

## What's owed at AT review (Reviewer B (sponsor))

1. **Sign off rule inventory.** Particularly: are 38 rule IDs the right granularity? More fine-grained (per-CICS-verb) or coarser (CICS verbs grouped)? The current split balances: each rule produces exactly one kind of observation; failures in Gate-3 acceptance can be localized to a single rule.
2. **Confirm `Unresolved` node-table treatment** matches spec intent. Alternative reading: keep `partial: true` on typed entities everywhere and don't introduce `Unresolved` as a node type. Current design is more honest about what we know vs. don't.
3. **Confirm derived-properties ownership.** RUL-DERIV-004 (`Program.inferred_purpose`) is the only derived rule that depends on LLM. With the deferred-Pass-2 directive, this property starts as `"unknown"` with `evidence_kind: derived`, confidence ~0.5; Gate 4 agent reads it and may regenerate. Confirm this is acceptable.
4. **Spec §LINKS_TO coverage.** CardDemo contains zero `EXEC CICS LINK` statements (Gate 0 anomaly #6). The edge type stays in the schema; corpus instance count will be zero. Gate-2 subset will use `XCTLS_TO` as the inter-program control-flow exemplar instead.

---

**GO recorded.** Moving to Gate 2 (golden-file pilot extraction).
