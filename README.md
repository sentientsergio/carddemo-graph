# carddemo-graph

**An evidence-grounded query engine for planning the modernization and maintenance of legacy mainframe applications.**

The system extracts a legacy COBOL/JCL/BMS/CICS/VSAM application into a provenance-rich knowledge graph, then answers questions about it in Cypher. The questions are open-ended — change-impact, control flow, data coupling, decomposition seams, field-level migration hazards — not a fixed menu. A downstream agent traverses the graph to plan maintenance and modernization work, grounded and traceable to source lines — and because the graph carries explicit gaps rather than fabricating, it is built to avoid the path-invention an agent grepping raw source past its context window is prone to. This is the engine on its way to being the core of such a tool, demonstrated end to end — not a finished product.

What sets it apart from a confident summarizer: **it knows what it knows versus what it inferred.** Every entity and edge carries source-line provenance, the rule that extracted it, and a confidence. Where the source is ambiguous — a screen navigation resolved at runtime, a subapp left out of scope — the graph surfaces an explicit gap rather than a plausible fabrication. It says "I didn't extract that."

**See [SHOWCASE.md](SHOWCASE.md) for the engine in action** — real Cypher queries with their real results, and a full operations manual and modernization strategy that a fresh agent produced from the graph alone, with no access to the source.

Demonstrated on [AWS CardDemo](https://github.com/aws-samples/aws-mainframe-modernization-carddemo), a representative public mainframe application. CardDemo is the demonstration vehicle, not the point: the deliverable is the extraction-and-query method, built to carry to other codebases of the same class.

### What it is, and what it is not

- **Planning and analysis are demonstrated; code generation and execution are not.** The engine reasons about the system and supports a migration plan; it does not run the application or emit modernized code.
- **It targets the class of legacy mainframe codebases through a per-corpus adaptation pass — not "any codebase" zero-shot.** A new system gets a fresh corpus profile, schema review, golden-file pilot, and full-tree extraction under the same discipline.
- **One corpus is proven end to end: CardDemo.** Generalization is a claim the project intends to earn corpus by corpus, not one it has banked.
- **The documented query contracts (Q1–Q5) are exemplars, not the limit** — the graph answers arbitrary planning questions. Their validation strength differs and is stated as such, not flattened: **Q1–Q4** are held to **hand-traced ground truth**; **Q5** (clustering) is **illustrative, not gold-asserted**; the field-level record layer (Q6) is validated at the DataItem layer against a **cold-agent gold** (agreement, not proof — a human COBOL expert would supersede). The project holds itself to the honesty discipline it asks of a downstream agent.

## Why

Legacy mainframe modernization is bottlenecked on accurate understanding of the existing system: which programs touch which data, which transactions traverse which programs, where the seams are, what's straddle and what's separable. Agents reasoning over source directly hit context limits and hallucinate paths. An evidence-grounded knowledge graph is a structured intermediate: each entity and edge carries source-line provenance, a rule ID identifying how it was extracted, an evidence kind, and a confidence. Downstream agents traverse the graph instead of grepping source, and every claim traces to an origin.

## How it's built

The grounding the engine depends on comes from **three-pass extraction with strict role separation.**

1. **Deterministic observation** — grammar-parser and rule-level extraction with a rule ID on every observation. **COBOL is now parsed by a vendored grammar parser (MAPA, ANTLR4) — the default extractor** — recovering copybook field layouts (PIC/USAGE/OCCURS/REDEFINES) and program constructs (COPY/SELECT/EXEC CICS/CALL/I-O verbs) from the language grammar rather than corpus-tuned regex; the original regex extractor is retained and selectable for comparison. One program whose literals span col-7 continuation lines fail-loud-falls back to that regex path (a documented boundary, not a silent guess — continuation-folding is roadmap). A second documented boundary: EXEC CICS `SEND`/`RECEIVE MAP` and `RETURN TRANSID` operands are extracted by keyword-paren from the grammar-delimited block — the construct's *source line* is resolver-validated and fail-loud, but operand-level *content*-validation is not yet implemented (Phase-3); it does not affect gold-parity. JCL JOB/EXEC/DD with PROC expansion and parameter binding, BMS DFHMSD/MDI/MDF, and CICS resource definitions (CSD) use their own deterministic extractors — the grammar-parser foundation is COBOL-first, with JCL/assembler as roadmap.
2. **LLM candidate observation** — per-file LLM passes propose candidates for ambiguous cases (dynamic CALLs, unresolved ASSIGNs, etc.) under tight discipline: JSON-schema-validated output, exact source line range required, versioned prompt template ID, candidates never invent entity IDs, dynamic calls never promoted to static. The LLM pass writes only to `observations.json` as `evidence_kind: llm_candidate` — it never authors final entities or edges.
3. **Merge and resolution** — the only phase that writes `entities.json` and `edges.json`. Resolution chains follow precedence rules (CSD authoritative for transaction-to-program, JCL DD authoritative for batch dataset binding, CICS FCT authoritative for online file binding). Conflicts are recorded in a conflict ledger with explicit resolution rationale.

**Every edge carries:** stable ID, type, confidence, evidence kind (`deterministic` / `llm_candidate` / `resolved` / `derived` / `manual`), rule ID, and a provenance list of source-file/line-range entries.

**Unresolved references emit as placeholders.** Never dropped.

## Executable form

The graph loads into [kuzu](https://kuzudb.com) — an embedded, Cypher-compatible graph database. The `.db` file is a deterministic build product of `entities.json` + `edges.json` and ships alongside them.

Queries are open-ended Cypher against the graph (see [SHOWCASE.md](SHOWCASE.md) for arbitrary planning questions answered live). Five query contracts are documented as **executable Cypher** in `queries/` (`q1`–`q5.cypher`) — exemplars, not the boundary of what the graph answers. Their validation strength is labelled, not flattened: **Q1–Q4** are held to **hand-traced ground truth**; **Q5** is **illustrative (not gold-asserted)**. (The field-level record layer is separately gold-checked as Q6 — a cold-agent gold at the DataItem layer, not an executable Cypher contract here.)

- **Q1** — Direct copybook inclusion impact (programs, transactions, maps, jobs, JCL steps; informational seed for wide impact via `DEFINES_LAYOUT_FOR`)
- **Q2** — Dataset access (per-program call-site mode; per-JCL-step access mode derived from DISP + DD role + utility SYSIN)
- **Q3** — Transaction-to-program closure (transitive via static `CALLS` / `LINKS_TO` / `XCTLS_TO`, with cycle detection and unresolved-dynamic-call breadcrumbs)
- **Q4** — BMS map surface for transaction (direction, mapsets, field-label surface)
- **Q5** — Cluster by shared data access (informational; surfaces bounded-context candidates and straddle programs)

The downstream agent receives the kuzu `.db` alongside the JSON artifacts and traverses the graph natively in Cypher — closer to how modernization analyses (transaction closure, shared-data clustering, bounded-context candidates) actually want to be expressed than SQL self-joins.

## Discipline

- **Schema is versioned** with semver. Breaking changes bump major.
- **Gold set is frozen before full-tree extraction.** Changes after freeze require a written reason. This avoids the anti-pattern of adjusting the gold set to match the extractor.
- **Positive and negative gold sets.** Positive: hand-traced expected answers for Q1–Q4. Negative: "must not infer" cases (dynamic CALLs must not appear as static reachable programs; direct program→dataset edges must not exist; comment-only references in original source must not create entities in stripped extraction; etc.).
- **Structural invariants** run on every extraction: 100% provenance coverage on edges, no duplicate canonical IDs, no dynamic calls promoted without source change, unresolved references emitted not dropped.
- **Conflict ledger** records every merge precedence decision with rationale.
- **Failure-mode taxonomy** classifies every gold-set deviation: parser miss, canonicalization error, unresolved symbol, ambiguous symbol, missing source file, unsupported construct, LLM candidate rejected, resolver conflict, query bug, gold-set bug.

## Repository

```
src/carddemo_graph/     # Extraction pipeline
queries/                # Cypher queries (executable against kuzu)
artifacts/              # Generated KB outputs (entities.json, edges.json, kuzu .db)
gold/                   # Hand-traced expectations (positive + negative)
tests/                  # Structural validator + rule tests
```

## Reference corpus

This implementation targets [AWS CardDemo](https://github.com/aws-samples/aws-mainframe-modernization-carddemo) as a known public mainframe corpus. The extraction discipline is intended to generalize: applying it to a new codebase means a fresh corpus profile, schema review, golden-file pilot, then full-tree extraction, all under the same gate discipline.

The CardDemo source itself is not redistributed here. Clone the upstream repository and point the pipeline at it; provenance for the extracted artifacts is preserved via source-file IDs and source-line ranges that resolve into the corresponding upstream files.

## Status

Pre-1.0 POC. The phase-gate discipline:

- **Gate 0 — Corpus profiling.** Inventory, naming conventions, CICS definition source confirmation. ✓
- **Gate 1 — Schema and deterministic-rule review.** Finalized schema, rule inventory with IDs, sample entities and edges. ✓
- **Gate 2 — Golden-file pilot.** Extraction on hand-checkable subset, sample query results, unresolved report, conflict ledger. ✓
- **Gate 3 — Full-tree extraction.** Run against complete corpus; structural invariants, semantic coverage, gold-set match. ✓ Acceptance Test A is mechanically green via `gold_match.py`: **37 match / 0 diff / 3 known-incremental** across 40 field comparisons. The validation strength behind that count, stated honestly rather than flattened into one number: **Q1–Q4 are hand-traced ground truth** (the deductive skeleton); the **3 known-incremental** are the deferred Q2 `jcl_access` fine-grain; the **4 field-layer comparisons (Q6.1/Q6.2) are a cold-agent gold** — convergence with the extraction is *agreement, not proof* (two readings of clean COBOL), validated on one simple and one hard copybook so far, and a human COBOL expert would supersede it; **Q5 is illustrative and not counted**. Produced by the **grammar-parser (MAPA) extractor, now the default** — which is not merely at parity with the earlier regex pass but demonstrably more correct: it resolves copybook-origin reachability the regex path structurally cannot (e.g. Q3.2 `COACTUPC → CSUTLDTC → CEEDAYS` through `COPY CSUTLDPY`), and the gold was corrected to that ground truth (see `gold/gold_set_changelog.md`). The retained regex path scores 36/1/3 on the same gold — failing exactly that copybook-expanded case.
- **Gate 4 — Downstream-agent trial.** Time-boxed agent run consuming only the agent packet, producing operations manual and modernization strategy against a named target stack. ✓ **PASS** — strong on all 7 rubric dimensions. Scored by the build orchestrator and the project sponsor under a packet-only protocol (no source access) — an honest internal review, not third-party-independent verification; a human mainframe SME would supersede. Protocol `artifacts/gate4_protocol.md`; result + deliverables in `artifacts/gate4/` (a frozen schema-1.0.0 snapshot) analyzed in [SHOWCASE.md §5](SHOWCASE.md). The packet alone enabled real downstream modernization reasoning without source access.

This is engineering reference work in active development. Not yet open for external contributions; that will follow stabilization at v1.0.

## Acknowledgments

This work uses [AWS CardDemo](https://github.com/aws-samples/aws-mainframe-modernization-carddemo) as the reference mainframe corpus. CardDemo is a credit-card-application demonstration codebase developed and published by AWS Samples as part of the [AWS Mainframe Modernization](https://aws.amazon.com/mainframe-modernization/) program. We are grateful to the AWS team for publishing a representative legacy COBOL/JCL/BMS/CICS corpus — without a public reference codebase of this completeness, evidence-grounded extraction research against legacy mainframe systems would be substantially harder.

The CardDemo source is referenced as an external dependency, retrieved as a git submodule at the time of corpus construction (2026-04-27 for the work in this repository). Upstream is distributed under its own license (see [the upstream LICENSE file](https://github.com/aws-samples/aws-mainframe-modernization-carddemo/blob/main/LICENSE)); the extraction tooling in this repository neither modifies nor redistributes the upstream source.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
