# SKILL — Evidence-grounded KB extraction over a mainframe codebase

This is the extraction *process* recipe — generalizes the methodology that built `carddemo-graph` to a new legacy codebase (COBOL/JCL/BMS/CICS, optionally extended to DB2/IMS/MQ). Use it as a starting point for a fresh extraction; iterate on rules and gates as the new corpus reveals its idioms.

---

## Purpose

Produce a structured, provenance-rich knowledge graph from a legacy mainframe codebase, such that downstream agents can answer maintenance and modernization questions by traversing the graph instead of re-reading source. The graph is built and validated under a **phase-gate discipline** with explicit acceptance tests.

The key architectural commitments:

1. **Three-pass extraction with strict role separation.** Pass 1 deterministic (regex/parser, no judgment). Pass 2 LLM-as-candidate-not-final (proposes hypotheses, never writes final entities/edges). Pass 3 merge & resolution (the only writer of final artifacts).
2. **Full provenance on every claim.** Every entity and edge carries `rule_id`, `evidence_kind` ∈ {deterministic, resolved, derived, llm_candidate, manual}, `confidence`, and a `provenance` list with source-line ranges.
3. **Skeleton / enrichment split.** Skeleton = provenanced ground truth (deductive composition); enrichment = LLM-inferred properties (separate `enrichments.json` artifact). Skeleton consumers don't see enrichments by accident.
4. **Closed vocabulary with versioned schema.** Adding new entity/edge types requires schema version bumps. Stable types are portable across codebases.
5. **Gold-set frozen before full-tree extraction.** Acceptance Test A compares the resolver output against hand-traced expectations, after canonicalization defined by `gold_match.py`. Post-freeze gold changes require explicit changelog entries.

---

## When to use this skill

- New mainframe codebase needing modernization analysis where the upstream constraints are reasoning quality (provenance, gold-asserted correctness) rather than raw extraction speed.
- A team that wants the audit trail to be inspectable and reproducible — every claim traces to a source line and a named extraction rule.
- A planned LLM-assisted modernization where the LLM benefits from a typed, provenanced intermediate representation rather than working over raw source.

Not the right fit when: you need 80%-confidence sketch-grade extraction over thousands of files quickly, or when no human reviewer can do the gold-set B-pass.

---

## Prerequisites

- Python 3.11+ with `kuzu`, `jsonschema`, `pytest`
- Source corpus accessible on disk (cloned or copied; this skill does not modify it)
- Optional but recommended: a comment-strip pipeline to produce a `stripped/` derivative for deterministic parsing (so regex rules don't have to dodge comments in every language). CardDemo's strip pipeline lives outside this repo; new corpora can either use a similar one or operate on raw source with adjusted column rules
- A named human reviewer for the gold-set B-pass (Reviewer B per spec §Validation §Gold-set construction protocol)

---

## The 5 gates

### Gate 0 — Corpus profiling (no extraction yet)

**Goal:** understand the corpus shape before writing any rules.

**Protocol:**
1. Enumerate files by type/extension. Report counts and per-area structure.
2. Identify naming conventions for each entity-class (program IDs, copybook names, JCL job names, DSN patterns, transaction IDs).
3. Locate authoritative sources: which file(s) hold the authoritative transaction↔program bindings (CSD / DFHCSDUP / CEDA)? Where do JCL PROCs live (cataloged vs inline)? What symbolic parameters are in use?
4. Inventory anomalies: phantom programs (referenced in CSD but no source body), PROC-name collisions, multi-line PROGRAM-ID formats, identifier-form CICS verbs (MOVE-chain navigation patterns), GDG references, etc.
5. Decide v1 scope: which file types are in/out, which features are deferred (DB2/IMS/MQ typically deferred), which subapps are excluded.

**Exit when:** inventory reviewed, unexpected types triaged, schema implications identified, CICS definition source confirmed, go/no-go recorded.

**Output:** `corpus_profile.md` (template: see `artifacts/corpus_profile.md` from carddemo-graph).

### Gate 1 — Schema and deterministic-rule review

**Goal:** lock the entity/edge vocabulary, the rule inventory, and validation infrastructure before any extraction runs.

**Protocol:**
1. Adapt the entity model (default: Program, Copybook, JCLJob, JCLStep, JCLProc, JCLProcInvocation, LogicalFile, Dataset, BMSMapset, BMSMap, BMSField, CICSTransaction). Add per-codebase types if the Gate-0 profile demands.
2. Adapt the edge model — keep the closed vocabulary discipline. Document each edge type's `from`/`to` types and any required attributes (e.g., `BINDS_TO` carries `dd_name` and `binding_source`).
3. Codify canonical-ID rules (e.g., `program:NAME` where NAME is from PROGRAM-ID, not filename).
4. Codify confidence + evidence-kind rules.
5. Write the deterministic-rule inventory: every rule gets a stable `rule_id` (e.g., `RUL-COBOL-001`). Each rule's text says: what construct it detects, what observation it emits (entity_candidate / edge_candidate / property_observation / unresolved_reference / anomaly), and any edge cases.
6. Author 5 sample entities + 5 sample edges with verbatim source citations.
7. Set up the structural validator: required-field enforcement, canonical-id pattern, edge confidence range, `llm_candidate` forbidden in edges.json, provenance shape, etc. Test the validator with paired negative-case unit tests.
8. Define the kuzu schema (node tables per entity type + rel tables per edge type). Smoke-load the schema.

**Exit when:** Gate 0 implications incorporated; rule inventory signed off; samples pass structural invariants.

**Output:** `schema.json`, `deterministic_rules.md`, `kuzu_schema.cypher`, sample_{entities,edges,observations}.json, the structural validator + tests, `gate1_closure.md`.

### Gate 2 — Golden-file pilot

**Goal:** validate the rules against a hand-checkable subset before running on the whole corpus.

**Protocol:**
1. Select a subset: at minimum one online COBOL, one batch COBOL, one JCL with a PROC reference, one BMS mapset, one copybook-heavy program, plus the authoritative CSD. Aim for ~10-15 files.
2. Run the extractor pipeline (Pass 1 deterministic + Pass 3 resolve + load into kuzu).
3. Inspect the output exhaustively against the source.
4. Adjust deterministic rules as needed. **Surface every rule adjustment with a justification** — at the end of Gate 2 you'll have a known set of refinements to land before the full-tree run.
5. Run Q1-Q4 sample queries against the kuzu DB; verify each returns plausible results.
6. Run structural invariants validator + semantic coverage assertions.
7. Produce unresolved report, conflict-ledger entries (if any), constructs-not-modeled list.

**Exit when:** subset contains at least one example of each critical edge type; unresolved report reviewed; gold-set candidates can be drafted; rule adjustments completed.

**Output:** `gate2/entities.json`, `edges.json`, `observations.json`, `resolution_report.md`, `unresolved_report.md`, `constructs_not_modeled.md`, `gate2/carddemo_graph.db`, `gate2_closure.md`.

### Gold-set authoring + B-pass (between Gate 2 and Gate 3)

**Goal:** hand-trace the expected answers for Q1-Q4 across a representative slice of the corpus, source-grepped not extractor-inferred.

**Protocol:**
1. Reviewer A traces each Qx entry from source via `grep` and direct inspection. **Do NOT consult the extractor's output during the trace** — that defeats the test.
2. Every gold-set entry has a grep-verifiable line citation. Inferences from naming convention without source verification are excluded.
3. Reviewer B independently checks the trace. Discrepancies surface as gold-set bugs (Reviewer A error) or extractor bugs (rule miss) and are triaged accordingly.
4. The gold-set is **frozen** before full-tree extraction. Post-freeze changes require entries in `gold_set_changelog.md`.
5. Add negative gold-set entries (`gold_set_negative.md`): "must NOT infer" cases like "dynamic CALL must not appear as static reachable program."

**Output:** `gold/gold_set.md` (frozen), `gold/gold_set_negative_candidates.md`, `gold/gold_set_changelog.md`.

### Gate 3 — Full-tree extraction

**Goal:** run the extractor on the full corpus and pass Acceptance Test A.

**Protocol:**
1. Run the extractor end-to-end on the full v1 scope.
2. Validate: structural invariants pass; semantic coverage assertions pass.
3. Run `gold_match.py` — compares query results against the frozen `gold_set.md` after canonicalization. Expect `[SUBSET] → [MATCH]` transition from Gate 2.
4. For any residual deltas, classify per the failure-mode taxonomy: parser miss, canonicalization error, unresolved symbol, ambiguous symbol, missing source file, unsupported construct, LLM candidate rejected, resolver conflict, query bug, gold-set bug.
5. Fix what's fixable in-pass (parser misses, derivation bugs); surface gold-set bugs for Reviewer-B amendment via `gold_set_changelog.md`.

**Exit when:** all structural invariants pass; semantic coverage assertions pass; Q1-Q4 match `gold_set.md` exactly after canonicalization; failure-mode taxonomy applied to residuals; deltas signed off or remediated.

**Output:** `gate3/entities.json`, `edges.json`, `observations.json`, `enrichments.json` (empty in v1), `gate3/carddemo_graph.db`, `kb_capabilities.md`, `report.md`, `clustering_report.md`, `gate3_closure.md`.

### Gate 4 — Downstream-agent trial

**Goal:** Acceptance Test B — verify the KB is rich enough that a downstream agent can produce useful modernization analysis without re-reading source.

**Protocol:**
1. Assemble `agent_packet/` per spec (README, kb_capabilities, graph_summary, known_unknowns, query_examples, entities/edges/enrichments JSON, kuzu .db, resolution_report).
2. Brief a fresh agent session with: a framing prompt naming the modernization target stack (e.g., Java 21 + Spring Boot + Spring Batch + Aurora + AWS-native orchestration), the `agent_packet/`, and the 7-dimension rubric.
3. Time-box the agent run. The agent produces `operations_manual.md` (runtime topology, failure surfaces, change-safety surfaces) and `modernization_strategy.md` (architecture abstraction, decomposition candidates, sequencing, risk-ranked unknowns).
4. A named reviewer scores each rubric dimension on a 3-point scale (insufficient / adequate / strong).

**Exit when:** rubric scoring shows adequate-or-better across all dimensions, strong on at least three. Failures traced to KB shortfalls vs agent prompting.

---

## Pass-2 LLM question set (placeholder for v1)

For v1, Pass 2 is deferred — the deterministic rules cover enough of the corpus that the residual is small and can be parked as Unresolved / partial entities with breadcrumbs. When Pass 2 is invoked in a future version:

**Each Pass-2 candidate is JSON-schema-validated** and must declare:
- `prompt_template_id` (versioned)
- `category` ∈ {observed, hypothesized, unsupported_construct, needs_deterministic_rule}
- `source_observations` (which Pass-1 observations the LLM read)
- `uncertainty_rationale`
- exact source line range (no candidate without a citation)
- writes only to `observations.json` as `evidence_kind: llm_candidate` — NEVER to `edges.json`

**Promotion step (separate from Pass 2):** explicit, auditable criteria turn validated llm_candidates into `enrichments.json` entries with `evidence_kind: inferred`. Promotion criteria are documented per promotion event.

**Question categories Pass 2 is suited for** (NOT in v1):
- MOVE-chain resolution of identifier-form CALL/LINK/XCTL targets (CardDemo's `unresolved:CDEMO-TO-PROGRAM` pattern)
- Inferred-purpose annotation on Program/Dataset entities
- Bounded-context naming for clusters (Q5 candidates)
- DCB-attribute inference when DSORG= is not directly stated
- Anomaly explanations / human-readable narratives on conflict-ledger entries

**Question categories Pass 2 is NOT suited for** (do these deterministically or not at all):
- Anything that has a closed-form rule (e.g., COPY statement detection, DSN normalization, FD record-area detection)
- Promoting dynamic CALL to typed Program (forbidden by RUL-NEG-001)
- Anything where the LLM can't cite a source line range

---

## Merge / resolution rules (Pass 3)

Pass 3 is the only phase that writes `entities.json` and `edges.json`. Key resolution chains:

- **COBOL LogicalFile → JCL DD → Dataset** (batch). Match `SELECT ... ASSIGN TO <dd>` to the invoking JCLStep's `//<dd> DD DSN=`. `BINDS_TO` edge carries `dd_name` + `binding_source="JCL_DD"`.
- **CICS LogicalFile → CSD DEFINE FILE → Dataset** (online). Match `EXEC CICS verb FILE('NAME')` (or `DATASET('NAME')`) to CSD `DEFINE FILE(NAME) DSNAME(...)`. `BINDS_TO` edge carries `binding_source="CSD"`.
- **PROC expansion.** For each `JCLProcInvocation`, emit `EXPANDS_TO` edges to every `JCLStep` belonging to the invoked `JCLProc`. Bound parameters tracked per invocation.
- **WS-constant propagation** (narrow form). When a CICS `DATASET(WS-FOO)` operand references a WS variable declared as `PIC X(N) VALUE 'literal'`, resolve to the literal. Anything beyond this narrow form falls to Pass 2.

Conflict-handling precedences (from spec §Conflict handling):

| Conflict | Precedence | Alternative |
|---|---|---|
| Transaction → program | CSD authoritative | Source idiom → lower-confidence candidate, flagged |
| Logical file → dataset | JCL DD (batch) or CICS FCT (online) authoritative | Conflicting source → conflict ledger entry, no edge |
| PROC inline vs cataloged | Inline at use-site overrides | Both retained; invocation references resolved form |
| Filename vs PROGRAM-ID | PROGRAM-ID authoritative | Filename mismatch recorded as anomaly |
| Same-named PROCs in different files | Merge with both as provenance | Filename-mismatch flag on the non-matching source |

---

## Re-run instructions

```bash
# Setup (once per environment)
python3.12 -m venv .venv
.venv/bin/pip install -e .
# .venv/bin/pip install kuzu jsonschema pytest  # if not in pyproject

# Full extraction
PYTHONPATH=src .venv/bin/python -m carddemo_graph.gate3

# Pilot (Gate 2 subset) — faster for iteration
PYTHONPATH=src .venv/bin/python -m carddemo_graph.pilot

# Gold-set comparator
PYTHONPATH=src .venv/bin/python -m carddemo_graph.gold_match \
    artifacts/gate3/carddemo_graph.db gold/gold_set.md

# Structural validator
PYTHONPATH=src .venv/bin/python -m carddemo_graph.validation.structural \
    artifacts/gate3/entities.json artifacts/gate3/edges.json

# Semantic coverage
PYTHONPATH=src .venv/bin/python -m carddemo_graph.validation.semantic \
    artifacts/gate3/entities.json artifacts/gate3/edges.json \
    artifacts/gate3/unresolved_report.md

# Tests
PYTHONPATH=src .venv/bin/pytest tests/
```

The `gate3.py` driver:
1. Enumerates v1 corpus files via the `enumerate_v1_corpus` glob set (adapt for a new codebase)
2. Runs the appropriate extractor per file type (cobol / jcl / proc / bms / csd)
3. Runs Pass 3 resolver
4. Validates structural invariants on entities/edges/observations/enrichments
5. Builds the kuzu .db from the JSON artifacts
6. Runs Q1-Q4 sample queries
7. Computes semantic coverage assertions
8. Prints a summary

Reproducibility guarantee: same inputs + same extractor version → byte-identical entities and edges by canonical-id. The corpus_hash in each artifact's header is stable.

---

## Applying this skill to a new codebase

1. **Clone this repo as a starting template.** The src/ tree is your starting Pass-1 + Pass-3 + validation infrastructure.
2. **Run Gate 0 on the new corpus.** Don't write any rules yet — produce `corpus_profile.md` based on what's actually there.
3. **Adapt rules incrementally.** Most COBOL/JCL/BMS/CICS rules transfer directly. New codebases may surface: DB2 (add SQL rules + entities), IMS (add IMSDatabase + ACCESSES_SEGMENT), MQ (add MQQueue + PUTS/GETS), assembler-heavy programs (add assembler-specific rules), unusual naming conventions (adjust canonical-id rules).
4. **Author the gold-set against your corpus.** Cannot re-use CardDemo's. Reviewer A traces, Reviewer B checks. Source-grep discipline (every entry has a verifiable line citation).
5. **Iterate Gates 1-3 until Acceptance Test A passes.** Expect 1-3 rule refinement cycles for a new corpus.
6. **Then Gate 4.** Assemble an agent_packet; brief a fresh agent with the modernization target stack; score the rubric.

---

## Outputs

After a complete Gate 0-3 cycle:

```
artifacts/
  corpus_profile.md           # Gate 0
  schema.json                 # Gate 1
  deterministic_rules.md      # Gate 1
  kuzu_schema.cypher          # Gate 1
  sample_{entities,edges,observations}.json  # Gate 1
  gate1_closure.md            # Gate 1
  gate2/                      # Gate 2 pilot outputs
    entities.json, edges.json, observations.json, enrichments.json
    resolution_report.md, unresolved_report.md, constructs_not_modeled.md
    carddemo_graph.db, gate2_closure.md, query_samples.json
  gate3/                      # Gate 3 full-tree outputs (same shape as gate2/)
  kb_capabilities.md          # downstream agent reads this first
  report.md                   # extraction quality report
  clustering_report.md        # Q5 informational
  agent_packet/               # Gate 4 inputs
    README.md, kb_capabilities.md, graph_summary.md, known_unknowns.md,
    query_examples.md, entities.json, edges.json, enrichments.json,
    carddemo_graph.db, resolution_report.md

gold/
  gold_set.md                 # frozen Reviewer-A/B traces
  gold_set_negative_candidates.md
  gold_set_changelog.md       # initial freeze + any post-freeze amendments
```

Plus source code at `src/carddemo_graph/` and `tests/`.
