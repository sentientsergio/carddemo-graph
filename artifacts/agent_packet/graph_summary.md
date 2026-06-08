# Graph Summary

Top-level statistics for the carddemo-graph v1 knowledge base.

## Top-line counts

```
schema_version:    1.1.0
extractor_version: 0.1.0
files extracted:   139
entities:          1864 (1832 full + 32 partial)  — incl. 517 DataItem (v2.2 KU-9)
edges:             1445 (all confidence == 1.0)     — incl. 519 HAS_FIELD/CONTAINS_ITEM
conflict-ledger:   1    (REPROC PROC-name collision)
```

## Entities by type

| Type | Count | Partial |
|---|---:|---:|
| BMSField | 902 | 0 |
| DataItem | 517 | 0 |
| JCLStep | 107 | 3 |
| LogicalFile | 79 | 7 |
| Dataset | 62 | 1 |
| Program | 50 | 17 |
| Copybook | 50 | 2 |
| JCLJob | 38 | 0 |
| BMSMap | 19 | 2 |
| CICSTransaction | 18 | 0 |
| BMSMapset | 17 | 0 |
| JCLProcInvocation | 4 | 0 |
| JCLProc | 1 | 0 |
| **TOTAL** | **1864** | **32** |

## Coupling metrics (v2.1 — now populated)

Two deterministic, skeleton-class properties (rule-derived over the data-access
graph; see `RUL-DERIV-005` / `RUL-DERIV-008`). Both ∈ [0,1]. Read them directly —
no need to recompute coupling by hand.

- **`Program.straddle_score`** — data-coupling breadth: fraction of other in-corpus
  app programs sharing ≥1 accessed dataset. Top straddlers: CBEXPORT (0.78),
  CBTRN02C (0.52), COTRN02C / CBSTM03A (0.48), COBIL00C / CBACT04C (0.44).
- **`Dataset.centrality`** — fraction of in-corpus app programs that access it. Most
  central: ACCTDATA.VSAM.KSDS (0.33), CARDXREF.VSAM.KSDS (0.29), TRANSACT.VSAM.KSDS (0.25).

(Set on all non-partial Programs / all Datasets; system utilities/phantoms are out
of scope. straddle_score is data-coupling breadth, a skeleton-pure proxy — distinct
from the informational Q5 cluster-relative straddle in `clustering_report.md`.)

## Edges by type

| Type | Count | Spec category |
|---|---:|---|
| CONTAINS_ITEM | 477 | Field-level layout (v2.2 KU-9) |
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
| EXPANDS_TO | 16 | Source structure (derived) |
| BINDS_TO | 23 | File/dataset access |
| UPDATES | 8 | File/dataset access |
| STARTS_BROWSE | 6 | File/dataset access |
| USES_PROC | 4 | JCL |
| DELETES | 1 | File/dataset access |
| PASSES_SYSIN_TO | 1 | JCL |
| HAS_FIELD | 42 | Field-level layout (v2.2 KU-9; copybook → 01-record root) |
| LINKS_TO | **0** | Program control flow (corpus-level absence) |
| RETURNS_TO_TRANSID | **0** | Program control flow (corpus-level absence) |
| **TOTAL** | **1445** | — |

## Top-N most-depended-upon programs

| Fan-in | Program | Kind |
|---:|---|---|
| 62 | program:IDCAMS | system utility (partial, not in corpus) |
| 18 | unresolved:CDEMO-TO-PROGRAM | MOVE-chain identifier (universal CardDemo screen-navigation target) |
| 13 | program:CBSTM03B | in-corpus statement sub-program |
| 11 | program:CEE3ABD | LE runtime abend handler (partial) |
| 8 | program:SDSF | system display facility (partial) |
| 6 | program:IEBGENER | system sequential-copy utility (partial) |
| 5 | program:SORT | DFSORT (partial) |
| 5 | program:IEFBR14 | null-op utility (partial) |
| 4 | program:CSUTLDTC | in-corpus date-conversion utility |

## Top-N copybooks by direct-impact

| Reuse count | Copybook | Notes |
|---:|---|---|
| 39 | copybook:CSSETATY | screen-attribute REPLACING template |
| 17 (×5) | DFHBMSCA, DFHAID (partial — IBM-supplied), COTTL01Y, CSDAT01Y, CSMSG01Y, COCOM01Y | universal online preamble |
| 12 | copybook:CVACT03Y | account cross-reference layout |
| 12 | copybook:CSUSR01Y | user session/security layout |
| 11 | copybook:CVACT01Y | account record layout |
| 11 | copybook:CVTRA05Y | transaction record layout |

## Authoritative bindings (CICS)

`CARDDEMO.CSD` defines 18 TRANSACTION↔PROGRAM pairs, 17 MAPSET, 8 FILE↔DSNAME, 18 PROGRAM:

| TRANID | Program | TRANID | Program |
|---|---|---|---|
| CAUP | COACTUPC | CDV1 | COCRDSEC *(phantom)* |
| CAVW | COACTVWC | CM00 | COMEN01C |
| CA00 | COADM01C | CR00 | CORPT00C |
| CB00 | COBIL00C | CT00 | COTRN00C |
| CCDL | COCRDSLC | CT01 | COTRN01C |
| CCLI | COCRDLIC | CT02 | COTRN02C |
| CCUP | COCRDUPC | CU00 | COUSR00C |
| CC00 | COSGN00C (entry) | CU01 | COUSR01C |
| | | CU02 | COUSR02C |
| | | CU03 | COUSR03C |

CSD CICS FILE → DSN bindings:

| FILE | DSN |
|---|---|
| ACCTDAT | AWS.M2.CARDDEMO.ACCTDATA.VSAM.KSDS |
| CARDAIX | AWS.M2.CARDDEMO.CARDDATA.VSAM.AIX.PATH |
| CARDDAT | AWS.M2.CARDDEMO.CARDDATA.VSAM.KSDS |
| CCXREF | AWS.M2.CARDDEMO.CARDXREF.VSAM.KSDS |
| CUSTDAT | AWS.M2.CARDDEMO.CUSTDATA.VSAM.KSDS |
| CXACAIX | AWS.M2.CARDDEMO.CARDXREF.VSAM.AIX.PATH |
| TRANSACT | AWS.M2.CARDDEMO.TRANSACT.VSAM.KSDS |
| USRSEC | AWS.M2.CARDDEMO.USRSEC.VSAM.KSDS |

## Confidence + evidence distribution

```
Confidence:
  ==1.0:  1445 edges (100%)

Evidence kind:
  deterministic: 1406 (97.3%)
  derived:         16 (1.1%)  — RUL-JCL-PROC-004 EXPANDS_TO derivations
  resolved:        23 (1.6%)  — RUL-RES-002 BINDS_TO chains via CSD
  llm_candidate:    0          — never in edges by design
  manual:           0
```

## Field-level record layout (v2.2 KU-9 — DataItem)

517 `DataItem` entities model copybook record layouts (level / name / picture /
usage / occurs / redefines / parent), wired as `Copybook -[HAS_FIELD]-> 01-record
-[CONTAINS_ITEM]-> children`. Each elementary item carries a deterministic,
**advisory** `suggested_sql_type` (e.g. `PIC S9(10)V99` → `NUMERIC(12,2)`,
`PIC X(10)` → `CHAR(10)`) for downstream Aurora DDL derivation — not authoritative
DDL. `occurs`/`redefines` are recorded as facts; their relational interpretation
(array-vs-child-table, canonical overlay) is a downstream decision. Scope is
`app/cpy/` file/data record layouts; `app/cpy-bms/` screen maps are out (already
modeled as BMSField). Example: `MATCH (c:Copybook {id:'copybook:CVACT01Y'})
-[:HAS_FIELD]->(:DataItem)-[:CONTAINS_ITEM]->(f) RETURN f.name, f.suggested_sql_type`.

## Skeleton / enrichment split

- **Skeleton:** `entities.json` + `edges.json` + `carddemo_graph.db` (provenanced ground truth).
- **Enrichment:** `enrichments.json` (LLM-inferred; empty in v1).

The skeleton answer for every Qx is honest and rule-grounded. Inferences from naming convention or MOVE-chain analysis are NOT in the skeleton — they're either deferred to Pass-2 enrichment or surface as `unresolved:*` placeholders with breadcrumb.
