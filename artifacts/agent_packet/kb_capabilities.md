# carddemo-graph — Knowledge-Base Capabilities

**The artifact a downstream agent reads first.** Tells you what this KB knows about AWS CardDemo, what queries it can answer with high confidence, and what's deliberately deferred.

Run: `gate3-fulltree-2026-05-13`. Schema version: `1.0.0`. Corpus hash: `f89baa793cdaff4809b17c2b381cc295a8ec3638cd7333748c8aecdd6564265a` (stable across reruns).

---

## At a glance

| Layer | Counts |
|---|---|
| Source files extracted | 139 (COBOL 81, JCL 38, BMS 17, JCL PROC 2, CSD 1) |
| Entities | **1864** total — 1832 full + 32 partial (incl. 517 DataItem, v2.2 KU-9) |
| Edges | **1445** total — every edge has full provenance + rule_id + confidence + evidence_kind |
| Pass-1 observations | 3562 (1932 entity_candidate + 1406 edge_candidate + 224 property_observation) |
| Conflict-ledger entries | 1 (REPROC PROC-name collision: REPROC.prc + TRANREPT.prc declare same canonical id) |
| LLM (Pass-2) candidates produced in v1 | **0** (Pass 2 deferred; rails in place for forward compatibility) |

All edges have `confidence == 1.0` in v1 (since all edges come from `deterministic` or `resolved`/`derived` rules with deductive composition — no probabilistic candidates surfaced into the final graph).

---

## Entity coverage

| Type | Total | Full | Partial | Partial reason (when present) |
|---|---:|---:|---:|---|
| Program | 50 | 33 | 17 | 15 dynamic-XCTL targets (`unresolved:CDEMO-TO-PROGRAM` etc.); 1 phantom (COCRDSEC: CSD-defined, no source body); 1 external (NONEXEG: deliberate "missing program" in test path) |
| Copybook | 50 | 48 | 2 | DFHAID, DFHBMSCA (IBM-supplied CICS copybooks, not in corpus) |
| BMSMapset | 17 | 17 | 0 | — |
| BMSMap | 19 | 17 | 2 | identifier-form `MAP(LIT-THISMAP)` operands that didn't resolve to literal map names (MOVE-chain → enrichment territory) |
| BMSField | 902 | 902 | 0 | every DFHMDF in every mapset |
| DataItem | 517 | 517 | 0 | field-level copybook record layout (v2.2 KU-9); `app/cpy/` only |
| CICSTransaction | 18 | 18 | 0 | all CSD-defined |
| Dataset | 62 | 61 | 1 | `dataset:&CNTLLIB` — unresolved JCL symbolic parameter |
| LogicalFile | 79 | 72 | 7 | CICS file references in online COBOL that couldn't deductively chain to a CSD `DEFINE FILE` |
| JCLJob | 38 | 38 | 0 | — |
| JCLStep | 107 | 104 | 3 | step-prefix DD overrides referencing steps not declared in the same scope |
| JCLProc | 1 | 1 | 0 | REPROC (single canonical PROC after the collision merge) |
| JCLProcInvocation | 4 | 4 | 0 | — |
| **TOTAL** | **1864** | **1832** | **32** | — |

**Partial = NOT a confidence problem.** A partial entity is one whose canonical id is known but whose source body or full property set isn't directly observable in the corpus. Examples: a Program referenced by CSD but with no `.cbl` file; an identifier-form XCTL target whose value depends on MOVE-chain analysis. The graph is full-citizen for these — they're queryable, traversable, and counted in fan-in/fan-out — but they carry `partial: true` so downstream agents can filter or weight differently.

---

## Edge coverage

| Type | Count | Spec category |
|---|---:|---|
| CONTAINS_ITEM | 477 | Field-level layout (v2.2 KU-9; parent item → child) |
| INCLUDES | 254 | Source structure |
| USES_DATASET | 136 | JCL |
| WRITES | 118 | File/dataset access |
| INVOKES | 102 | JCL |
| READS | 66 | File/dataset access |
| DECLARES_FILE | 49 | File/dataset access |
| DEFINES_LAYOUT_FOR | 32 | Source structure |
| CALLS | 32 | Program control flow |
| XCTLS_TO | 23 | Program control flow |
| SENDS_MAP | 20 | CICS UI |
| IS_TRANSACTION_FOR | 18 | CICS binding |
| RECEIVES_MAP | 17 | CICS UI |
| EXPANDS_TO | 16 | Source structure (derived RUL-JCL-PROC-004) |
| BINDS_TO | 23 | File/dataset access |
| UPDATES | 8 | File/dataset access |
| STARTS_BROWSE | 6 | File/dataset access |
| USES_PROC | 4 | JCL |
| DELETES | 1 | File/dataset access |
| PASSES_SYSIN_TO | 1 | JCL |
| HAS_FIELD | 42 | Field-level layout (v2.2 KU-9; copybook → 01-record root) |
| LINKS_TO | **0** | Program control flow (corpus-level absence; Gate 0 anomaly #6) |
| RETURNS_TO_TRANSID | **0** | Program control flow (corpus-level absence — CardDemo programs RETURN without TRANSID) |
| **TOTAL** | **1445** | — |

**18 / 21 edge types observed.** The 3 corpus-level absences are confirmed by grep across the full v1 corpus — they are NOT extractor gaps. The schema retains them for portability to other mainframe codebases.

---

## Coverage denominators (for honest answering)

These are the "observed N; resolved M; unresolved K" figures the downstream agent should cite when answering "how complete is this answer?"

| Construct | Observed | Resolved | Notes |
|---|---:|---:|---|
| COPY statements (all forms) | 254 | 220 in-corpus + 34 external | externals = DFHAID/DFHBMSCA (IBM-supplied); 32 of in-corpus are FD-context (DEFINES_LAYOUT_FOR) |
| `EXEC CICS` blocks | 887 edge candidates total | varies by verb | LINK 0 / XCTL 23 (2 literal + 21 dynamic) / RETURN 0-TRANSID / SEND 20 / RECEIVE 17 / file verbs 80 |
| JCL `DD DSN=` allocations | 136 USES_DATASET edges | 135 resolved + 1 partial | 1 partial = `dataset:&CNTLLIB` (unresolved symbolic param in REPROC.prc) |
| Dynamic identifier-form CALL/LINK/XCTL | 21 | 21 (all routed to `unresolved:*`) | by design — MOVE-chain resolution is enrichment, not skeleton |
| FD-context COPY (DEFINES_LAYOUT_FOR) | 32 distinct (copybook, logical_file) pairs | 32 | all in-corpus copybooks defining record layouts for batch I/O |
| BMS field labels (INITIAL or PROMPT non-empty) | 902 BMSField entities | full count in source, reported with content | per-mapset enumeration via `bms-field:<MAPSET>/<MAP>/<NAME>` |
| LLM-candidate observations (Pass 2) | 0 | — | Pass 2 deferred for v1; rails in place (prompt_template_id, category, source_observations) |

---

## What this KB can answer with high confidence (skeleton-grounded)

The five v1 acceptance queries, with their semantic contracts:

- **Q1 — Direct copybook inclusion impact.** Given a `Copybook` id, returns the programs that directly COPY it, the transactions bound to those programs, the BMS maps sent/received by them, the JCL jobs and steps invoking them, and the related logical files for which the copybook defines a record layout. *Gold-matched 5/5 in Gate 3.*
- **Q2 — Dataset access.** Given a `Dataset` id, returns per-program access (with batch DD or CICS file binding and READ/WRITE/UPDATE/DELETE/BROWSE per call site) and per-JCL-step access (with allocation disposition and inferred access mode). *Per-step DD-name + DISP fine-grain is a Known Gate-3 Incremental in the gold-set freeze; spot-checks at job level match.*
- **Q3 — Transaction-to-program closure.** Given a `CICSTransaction` id, returns the entry program plus transitive reachable programs via static `CALLS`/`LINKS_TO`/`XCTLS_TO`, with cycle detection. **Identifier-form (MOVE-chain) XCTL/LINK/CALL targets stay as `unresolved:*` with breadcrumb, never promoted to typed Program edges** — per the skeleton/enrichment principle. *Gold-matched on CC00 / CAUP / CT01: literal XCTL paths populate `reachable_programs`; identifier-form populates `unresolved_reaches`.*
- **Q4 — BMS map surface for transaction.** Given a `CICSTransaction` id, returns entry program, distinct map interactions (program × map × SEND|RECEIVE), enclosing mapsets, and per-map field surface (INITIAL/PROMPT labels). *Verbatim INITIAL enumerations in `gold/gold_set.md`.*
- **Q5 — Cluster by shared data access** (informational, not gold-asserted). Returns candidate bounded-context clusters with straddle programs flagged. Derivable from the graph via the Program↔Dataset shared-access projection in `query_examples.md` (group programs by the datasets they READ/WRITE/UPDATE/DELETE/BROWSE and by JCL USES_DATASET).

Ready-to-run Cypher for Q1–Q4 is in `query_examples.md` in this packet. (In the repo, standalone `q1.cypher`–`q5.cypher` live under `queries/`, and the same logic runs in `src/carddemo_graph/pilot.py` / `gate3.py`; those are outside this self-contained packet.)

## What this KB cannot answer (deferred features, per spec §Deferred extensions)

- **DB2 / SQL**: `SQLTable` entities, `SELECTS_FROM`/`INSERTS_INTO`/`UPDATES_TABLE`/`DELETES_FROM_TABLE` edges, `EXEC SQL` patterns. The deferred subapps `app/app-authorization-ims-db2-mq` and `app/app-transaction-type-db2` are in the corpus but **not extracted** in v1.
- **IMS DB**: `IMSDatabase`, `ACCESSES_SEGMENT`.
- **MQ**: `MQQueue`, `PUTS_MESSAGE`/`GETS_MESSAGE`. Deferred subapp `app/app-vsam-mq` is in the corpus but not extracted.
- **`DataItem` granularity**: level/picture/usage/occurs/redefines/parent. Out of v1 design decision per spec.
- **BMS field ↔ symbolic-map data item linking (`MAPS_TO_ITEM`)**: depends on `DataItem`.
- **Intra-program control flow**: paragraph/section entities, `PERFORMS`/`GO_TO`. Out of v1.
- **Transitive (wide) Q1**: automatic inclusion of programs touching files whose record-layout copybook is the target. `related_files` field is the informational seed.
- **MOVE-chain resolution of identifier-form CALL/LINK/XCTL targets**: parked as `unresolved:*` with breadcrumb. Pass-2 LLM-assisted promotion may produce `enrichments` records when wired (none in v1).

---

## Confidence and evidence-kind distribution

```
Edge confidence:
  ==1.0:      1445 (100%)
  >=0.7,<1.0: 0
  <0.7:       0

Edge evidence_kind:
  deterministic: 1406 (97.3%) — direct rule match in source (incl. HAS_FIELD/CONTAINS_ITEM)
  derived:         16 (1.1%) — RUL-JCL-PROC-004 EXPANDS_TO from JCLProcInvocation
  resolved:        23 (1.6%) — RUL-RES-002 BINDS_TO via CSD chain
  llm_candidate:   0          — never in edges.json by design
  manual:          0          — none in v1
```

The 13 `resolved` edges are the online `LogicalFile → BINDS_TO → Dataset` chain via CSD `DEFINE FILE`. The 16 `derived` edges are PROC-invocation expansion (JCLProcInvocation → JCLStep).

---

## Unresolved summary

| Category | Count | Notes |
|---|---:|---|
| External-reference partial copybooks | 2 | DFHAID, DFHBMSCA — IBM-supplied; treated as `partial: true` with surface form preserved |
| Identifier-form CALL/LINK/XCTL targets | 21 | All routed to `unresolved:CDEMO-TO-PROGRAM` (the universal CardDemo MOVE-target convention); breadcrumb preserved |
| Identifier-form BMS map operands | 2 | `MAP(LIT-THISMAP) MAPSET(LIT-THISMAPSET)` patterns |
| Phantom programs (CSD-only) | 1 | COCRDSEC (CSD `DEFINE PROGRAM` only; no source body) |
| External program references | 1 | NONEXEG (literal CALL to a deliberately-missing program; CardDemo test pattern) |
| Unresolved symbolic JCL parameter | 1 | `&CNTLLIB` in REPROC.prc DSN — substituted at use-site, not extractable from PROC body alone |
| Step-prefix DD overrides without declaration | 3 | JCLProc DD-override sites referencing steps not declared in the same JCL scope |
| LogicalFile without CSD binding | 7 | CICS file references where the CSD `DEFINE FILE(<name>)` was not found |
| **TOTAL** | **32 partial entities** | all listed in `unresolved_report.md` |

---

## Constructs observed but NOT modeled in v1

(Verbatim from `constructs_not_modeled.md`. These are operational CICS verbs and out-of-scope SQL/IMS/MQ patterns the closed-vocabulary edge schema deliberately excludes.)

```
EXEC CICS HANDLE / ABEND / ASSIGN / INQUIRE — operational; no closed-vocab edge
EXEC CICS ASKTIME / FORMATTIME              — operational; no closed-vocab edge
EXEC CICS WRITEQ / READQ TS|TD             — TS/TD queues not in v1 closed vocab
COBOL paragraphs/sections                   — out of v1 design (intra-program control flow)
DataItem (field-level)                      — out of v1 design
DCLGEN copybooks (.dcl) / EXEC SQL          — needs-ext (DB2)
IMS DBD/PSB                                 — needs-ext
MQ EXEC MQ                                  — needs-ext
```

---

## How to consume this KB

Two surfaces:

**1. Native JSON.** `entities.json` + `edges.json` + `observations.json` + `enrichments.json` (empty in v1, see skeleton/enrichment split below). Every entity and edge carries full provenance: source path + line range + rule_id + evidence_kind + confidence. Read these directly for type-strict consumers.

**2. Embedded graph DB.** `carddemo_graph.db` is a kuzu database built deterministically from the JSON. Query it natively in Cypher:

```python
import kuzu
db = kuzu.Database("carddemo_graph.db")
conn = kuzu.Connection(db)
# Example: programs that COPY copybook:CSUSR01Y
result = conn.execute(
    "MATCH (p:Program)-[:INCLUDES]->(c:Copybook {id: 'copybook:CSUSR01Y'}) RETURN p.id"
)
```

See `query_examples.md` in this packet for ready-to-run Cypher (Q1–Q4 plus modernization-style traversals).

---

## Skeleton / enrichment split

**Critical for honest answering.** This KB strictly separates:

- **Skeleton** (`entities.json`, `edges.json`, `carddemo_graph.db`): provenanced ground truth. Every claim derives from a deductive rule with explicit `rule_id` and source-line citations. Pass-1 deterministic and Pass-3 resolved/derived live here. Nothing LLM-judgment-derived is in the skeleton.
- **Enrichment** (`enrichments.json`): LLM-inferred properties. **Empty in v1.** Pass-2 promotion populates it later with explicit promotion criteria; downstream consumers who want enrichment-layer hints load it separately. Skeleton consumers don't see enrichments.

A downstream agent answering questions can quote skeleton facts with full confidence (rule-grounded, source-cited) and explicitly mark anything beyond as inferential. Pass 2 work, when it lands, will write to `enrichments.json` with `evidence_kind: inferred` and structured `prompt_template_id` + `source_observations`.

---

## Audit trail

Every entity and every edge can be traced to the source line that produced it. `observations.json` carries the pre-resolution Pass-1 audit trail; `resolution_report.md` documents merge decisions and the conflict ledger; `unresolved_report.md` lists partial entities and why; `gold/gold_set.md` + `gold/gold_set_changelog.md` document the hand-traced acceptance set and any post-freeze amendments.

Reproducibility: same inputs + extractor version → byte-identical entities/edges (verified — corpus_hash is stable). `python -m carddemo_graph.gate3` rebuilds everything from source.
