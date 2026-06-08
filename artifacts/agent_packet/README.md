# carddemo-graph — Agent Packet

**You are receiving this packet as the sole input to a Gate-4 downstream-agent trial against the AWS CardDemo codebase.** Per spec v4.1, the packet is the complete material handed to you. You may not access source code, the strip pipeline, or any other artifact outside this packet.

## What this packet contains

| File | Purpose |
|---|---|
| `README.md` | this file |
| `kb_capabilities.md` | **READ FIRST.** What this KB knows; coverage denominators; what's skeleton vs enrichment; queries supported; deferred features. |
| `graph_summary.md` | Top-level entity/edge counts; key statistics. |
| `known_unknowns.md` | Explicit list of what's NOT in this KB. Use this to flag gaps in your analysis rather than guessing. |
| `query_examples.md` | Ready-to-use Cypher queries for common modernization questions. |
| `entities.json` | Skeleton entities — all 1864 (incl. 517 field-level DataItem), with provenance, partial flags, evidence_kind. |
| `edges.json` | Skeleton edges — all 1445 (incl. HAS_FIELD/CONTAINS_ITEM field-layout edges). |
| `enrichments.json` | LLM-inferred properties. **Empty in v1.** Pass-2 promotion populates this artifact; for now it carries zero entries. The architectural commitment to skeleton/enrichment separation is visible from v1. |
| `carddemo_graph.db` | kuzu graph database — the executable substrate. Load via `kuzu.Database(...)` and query in Cypher. |
| `resolution_report.md` | Pass-3 merge decisions + the conflict ledger (1 entry: REPROC PROC-name collision). |

## How to use this packet

1. Read `kb_capabilities.md` first to learn the surface and limits of what's been extracted.
2. Skim `graph_summary.md` for headline counts.
3. Read `known_unknowns.md` to internalize what to flag rather than guess.
4. When answering specific questions, load `carddemo_graph.db` into kuzu and run Cypher. `query_examples.md` shows the patterns for the v1 acceptance queries Q1-Q4 plus modernization-style traversals.
5. For provenance back to source line: every entity and edge has a `provenance` list with `source_path` + `start_line` + `end_line` + `rule_id`. Cite these when claiming facts.

## Scope reminder

- This KB covers **v1 base mode only**: COBOL, JCL, BMS, CICS resource definitions, VSAM, copybooks, assembler stubs. DB2/IMS/MQ are explicitly deferred per spec §Deferred extensions. The `app/app-*` subapps in the upstream CardDemo source were **not extracted**.
- Some constructs are observed but not modeled by design: COBOL paragraphs/sections, DataItem field-level layouts, EXEC CICS HANDLE/ABEND/ASSIGN/INQUIRE, TS/TD queues. See `known_unknowns.md`.
- Identifier-form CALL/LINK/XCTL targets (MOVE-chain navigation) stay as `unresolved:*` placeholders — Pass-2 enrichment territory. You can ask Q3 transaction-closure questions and get an honest answer of what's deductively reachable vs. what's unresolved with breadcrumb.

## Modernization target stack (for the Gate-4 framing prompt)

Per spec v4.1 §Gate 4: **Java 21 + Spring Boot + Spring Batch + PostgreSQL Aurora + AWS-native orchestration** (Step Functions for inter-job sequencing, ECS Fargate for services, S3 for staging and GDG replacement).

Your task in the trial: produce `operations_manual.md` and `modernization_strategy.md` grounded in this packet, against the named target stack.

## Scoring rubric (for your awareness — applied by the named reviewer)

Each dimension scored insufficient / adequate / strong. Pass threshold: adequate-or-better across all dimensions, strong on at least three.

- **Grounding** — claims cite KB entities/edges/provenance, not unsupported intuition
- **Coverage** — addresses online, batch, data, CICS, JCL, BMS surfaces where applicable
- **Unknown handling** — explicitly lists unresolved, dynamic, unsupported surfaces (use `known_unknowns.md`)
- **Modernization usefulness** — concrete seams, risks, sequencing, non-translatable constructs against the named target
- **Operational usefulness** — explains runtime topology, failure surfaces, change-safety surfaces
- **Hallucination control** — no invented programs, datasets, transactions, maps, jobs
- **Reviewer judgment** — each section "useful enough to guide next analysis"

Quoting a partial entity or an `unresolved:*` placeholder is fine — that's what they're for. Inventing names is not.
