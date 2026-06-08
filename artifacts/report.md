# carddemo-graph — Extraction Quality Report

**Source:** Gate 3 full-tree extraction (`gate3-fulltree-2026-05-13`). Schema 1.0.0.

This report focuses on *extraction quality* — what's well-resolved, what's partial, what's anomalous. For a higher-level "what this KB knows" view, see `kb_capabilities.md`. For the audit trail of Pass-3 merge decisions and conflicts, see `gate3/resolution_report.md`.

---

## 1. Counts

```
Source files extracted:    139  (COBOL 81, JCL 38, BMS 17, JCL_PROC 2, CSD 1)
Pass-1 observations:      3562  (1932 entity_candidate + 1406 edge_candidate + 224 property_observation)
Entities (final):         1864  (1832 full + 32 partial; incl. 517 DataItem, v2.2 KU-9)
Edges (final):            1445  (all confidence == 1.0)
Conflict-ledger entries:     1  (REPROC PROC-name collision; both source files retained as provenance)
LLM observations:            0  (Pass 2 deferred; rails in place)
```

---

## 2. Top-N most-depended-upon programs (incoming program-control or job-invocation edges)

| Fan-in | Program | Notes |
|---:|---|---|
| 62 | program:IDCAMS *(partial)* | system utility invoked from many JCL steps (define/load/delete VSAM/SORT control) |
| 18 | unresolved:CDEMO-TO-PROGRAM *(partial)* | universal CardDemo MOVE-target identifier — every online program XCTLs through this WS variable to its "next program" |
| 13 | program:CBSTM03B | statement-printing sub-program called from CBSTM03A |
| 11 | program:CEE3ABD *(partial)* | IBM Language Environment abend handler |
| 8 | program:SDSF *(partial)* | system display facility invoked from sample JCL |
| 6 | program:IEBGENER *(partial)* | system sequential-copy utility |
| 5 | program:SORT *(partial)* | DFSORT |
| 5 | program:IEFBR14 *(partial)* | null-op (dataset disposition only) |
| 4 | program:CSUTLDTC | in-corpus date-conversion utility — called only by CORPT00C (lines 358, 378) and COTRN02C (lines 354, 374). Naming-convention inference that "all transaction programs call CSUTLDTC" is FALSE. |
| 2 | unresolved:CCARD-NEXT-PROG *(partial)* | another MOVE-target identifier (card-screens specific) |
| 2 | program:COADM01C | reached from COSGN00C via literal XCTL |
| 2 | program:COMEN01C | reached from COSGN00C via literal XCTL |
| 2 | program:CBTRN03C | invoked by TRANREPT.jcl and (via REPROC PROC expansion) PRTCATBL.jcl |
| 1 | program:COBDATFT *(partial)* | assembler stub (date-format conversion) |
| 1 | program:MVSWAIT *(partial)* | assembler stub (wait utility) |

**Reading:** the heavy fan-in on IDCAMS / SORT / IEBGENER / IEFBR14 is normal — these are system utilities invoked across the batch job library. The 18 fan-in on `unresolved:CDEMO-TO-PROGRAM` is the dominant pattern in CardDemo's online flow: every screen uses a MOVE-then-XCTL idiom to navigate, so the deductive XCTL graph stays sparse (only literal XCTL targets are typed). MOVE-chain resolution is Pass-2 enrichment territory.

---

## 3. Top-N copybooks by direct-impact (`INCLUDES` count)

| Reuse count | Copybook | Notes |
|---:|---|---|
| 39 | copybook:CSSETATY | screen-attribute REPLACING template — COACTUPC alone COPYs it ~10 times with different REPLACING terms |
| 17 | copybook:DFHBMSCA *(partial, IBM-supplied)* | CICS basic-mapping-support attribute constants |
| 17 | copybook:DFHAID *(partial, IBM-supplied)* | CICS Attention Identifier constants |
| 17 | copybook:COTTL01Y | online screen title layout |
| 17 | copybook:CSDAT01Y | shared date constants |
| 17 | copybook:CSMSG01Y | shared message constants |
| 17 | copybook:COCOM01Y | common online communication layout |
| 12 | copybook:CVACT03Y | account cross-reference layout |
| 12 | copybook:CSUSR01Y | user session/security layout |
| 11 | copybook:CVACT01Y | account record layout |
| 11 | copybook:CVTRA05Y | transaction record layout |
| 8 | copybook:CVACT02Y | account additional-attributes layout |
| 8 | copybook:CVCUS01Y | customer record layout |
| 5 | copybook:CVCRD01Y | card record layout |
| 5 | copybook:CSSTRPFY | screen string formatting utility |

**Reading:** the cluster at exactly 17 (COTTL01Y / CSDAT01Y / CSMSG01Y / COCOM01Y plus the IBM DFHs) reflects the universal online-program preamble — every CO* screen includes these five for the standard mapping/header machinery. CSSETATY at 39 reflects COACTUPC and similar editable-screen programs that need many attribute-byte variants.

---

## 4. Unresolved dynamic CALL / LINK / XCTL references

Per spec §Negative gold-set tests RUL-NEG-001: identifier-form (MOVE-chain) CALL/LINK/XCTL targets are *never* promoted to typed Program edges. They stay as `unresolved:<surface>` with breadcrumb.

```
Total dynamic edges:           21
Distinct source programs:      16
Distinct unresolved targets:    3
```

| Unresolved target | Count | Source programs (sample) |
|---|---:|---|
| unresolved:CDEMO-TO-PROGRAM | 18 | COACTUPC (line 844), COTRN01C (170), COCRDLIC, COCRDSLC, COCRDUPC, COBIL00C, COMEN01C, COADM01C, COTRN00C, COTRN02C, CORPT00C, COUSR00-03C, COACTVWC, COSGN00C (some) |
| unresolved:CCARD-NEXT-PROG | 2 | COACTUPC (line 3215), COACTVWC (line 486) — card-detail next-program navigation |
| unresolved:LIT-MENUPGM | 1 | (1 site — back-to-menu via WS literal) |

All 21 carry `call_kind: dynamic` and `breadcrumb: <identifier>` attributes for Pass-2 promotion.

---

## 5. Unresolved DD/dataset bindings

```
Partial Dataset entities: 1
  dataset:&CNTLLIB         — unresolved JCL symbolic parameter; original
                             surface form preserved; substituted at use-site
                             (not extractable from PROC body alone)
```

All other 61 datasets resolved deductively from JCL `DD DSN=` or CSD `DEFINE FILE DSNAME(...)`.

LogicalFile entities marked partial: 7 of 79. These are CICS file references (online `EXEC CICS verb FILE(...)` / `DATASET(...)`) where the CSD `DEFINE FILE(<name>)` was not found in `CARDDEMO.CSD`. Likely the file-name operand was an unresolved identifier that didn't match any literal CSD entry; deferred to Pass-2 promotion.

---

## 6. Unsupported constructs

From `gate3/constructs_not_modeled.md`. These are observed in the corpus (or in adjacent contexts) but explicitly **not modeled** in v1:

```
EXEC CICS HANDLE / ABEND / ASSIGN / INQUIRE — operational, no closed-vocab edge
EXEC CICS ASKTIME / FORMATTIME              — operational, no closed-vocab edge
EXEC CICS WRITEQ / READQ TS|TD             — TS/TD queues not in v1 closed vocab
EXEC CICS RETURN (without TRANSID)         — emits no edge per spec (RETURN-TRANSID edge only)
EXEC CICS LINK                              — corpus-level absence in CardDemo (Gate 0 anomaly #6)
COBOL paragraphs/sections                   — out of v1 design (intra-program control flow)
DataItem (field-level)                      — out of v1 design
DCLGEN copybooks (.dcl) / EXEC SQL          — needs-ext (DB2)
IMS DBD/PSB                                 — needs-ext
MQ EXEC MQ                                  — needs-ext
```

---

## 7. Confidence distribution

All 1445 edges in `edges.json` carry `confidence == 1.0`. By design — the deterministic-only run produces only edges with deductive composition or named-rule derivation, all of which warrant 1.0.

```
==1.0:     1445 (100%)
>=0.7,<1.0:   0
<0.7:         0
```

By `evidence_kind`:

```
deterministic: 1406 (97.3%) — direct rule match in source (incl. HAS_FIELD/CONTAINS_ITEM)
derived:         16 (1.1%) — RUL-JCL-PROC-004 EXPANDS_TO (JCLProcInvocation → JCLStep)
resolved:        23 (1.6%) — RUL-RES-002 BINDS_TO via CSD chain
llm_candidate:   0 (0%)   — never in edges.json by design
manual:          0 (0%)
```

---

## 8. `DEFINES_LAYOUT_FOR` summary

```
Total DEFINES_LAYOUT_FOR edges: 32 (across 15 distinct copybooks)
```

The wide v1 picture is narrow: most CardDemo copybooks are working-storage layouts that get COPYed but never appear in FD record areas. Only the import/export programs (`CBEXPORT`, `CBIMPORT`) extensively use copybooks as FD record layouts, and a few batch programs (`CBACT*`, `CBTRN*`).

| Copybook | Layout count | Notes |
|---|---:|---|
| copybook:CVACT03Y | 6 | account cross-reference; used as FD record in multiple batch programs |
| copybook:CVACT01Y | 5 | account record; CBEXPORT/CBIMPORT + others |
| copybook:CVTRA05Y | 4 | transaction record; CBEXPORT/CBIMPORT + others |
| copybook:CVACT02Y | 2 | account additional attrs |
| copybook:CVTRA01Y | 2 | transaction header |
| copybook:CVCUS01Y | 2 | customer |
| copybook:CVEXPORT | 2 | bulk-export wrapper |
| copybook:CVTRA06Y | 2 | transaction-category-balance |
| copybook:CODATECN | 1 | date conversion |
| copybook:CVTRA02Y | 1 | |
| copybook:CVTRA03Y | 1 | |
| copybook:CVTRA04Y | 1 | |
| copybook:CVTRA07Y | 1 | |
| copybook:COSTM01 | 1 | statement |
| copybook:CUSTREC | 1 | customer record (CBCUS01C only) |

These 15 copybooks comprise the `record-layout surface` of CardDemo's batch I/O.

---

## 9. Per-file LLM token usage

**Zero.** Pass 2 (LLM-assisted candidate observation) is deferred for v1 per the blocker-resolution directive (2026-05-12 evening: "defer Pass 2 until actually needed; rails in place").

The rails ARE in place: the `Observation` schema requires `prompt_template_id` + `category` when `evidence_kind == "llm_candidate"`; the validator enforces it; the `Enrichment` schema is wired for promoted Pass-2 outputs. When Pass 2 lands in a future version, this section will report per-file token usage with outliers flagged.

---

## 10. Anomalies and follow-ups

### Pre-known (Gate 0 anomaly catalog)

| Anomaly | Status |
|---|---|
| PROC-name collision: REPROC.prc + TRANREPT.prc both declare `//REPROC PROC` | ✅ Conflict-ledger entry written; both files retained as provenance; downstream USES_PROC edges resolve to canonical id |
| Phantom program COCRDSEC (CSD-only, no source body) | ✅ `program:COCRDSEC` materialized with `partial: true`; CDV1 transaction binding preserved |
| Multi-line PROGRAM-ID format (5 programs) | ✅ RUL-COBOL-001 multi-line lookahead handles all 5 |
| TRANREPT.prc dead PROC (never invoked) | ✅ Documented; no Gate-3 impact |
| EXEC CICS LINK absence (corpus-level) | ✅ Confirmed: 0 LINKS_TO edges in v1 corpus |
| RETURN TRANSID absence (corpus-level) | ✅ Confirmed: 0 RETURNS_TO_TRANSID edges |
| `&SYUID` typo (vs. `&SYSUID`) | ✅ Recorded as singleton symbolic param |
| NONEXEG external CALL target | ✅ Materialized as partial Program |
| LISTCAT.txt informational (not source) | ✅ Excluded from extraction |
| scripts/markers/ sentinel files | ✅ Excluded |

### Surfaced and fixed during Gate 3 (failure-mode taxonomy applied)

| Failure mode | Description | Status |
|---|---|---|
| `parser miss` | CICS LINK/XCTL `PROGRAM(...)` regex matched both literal and identifier — fix split into separate regexes; identifier-form routes to `unresolved:*` with breadcrumb | ✅ FIXED |
| `parser miss` | Copybook entity_candidate not emitted from `.cpy` source files (copybooks shown as partial unnecessarily) | ✅ FIXED — partial copybook count 49 → 2 (the remaining 2 are correctly partial: IBM-supplied externals) |
| `parser miss` (schema gap) | kuzu `LINKS_TO`/`XCTLS_TO` rel tables missing `call_kind`/`breadcrumb` columns | ✅ FIXED — added columns |
| Internal attribute filter bug | Pass 3 was stripping `call_kind`/`breadcrumb` from edge attributes | ✅ FIXED — removed from exclude list |
| `gold-set bug` | Q2.1 USRSEC `jcl_access` listed ESDSRRDS.jcl which references USRSEC.VSAM.ESDS/RRDS variants, NOT the KSDS target | ✅ AMENDED — `gold/gold_set_changelog.md` F5 entry; gold_set.md Q2.1 row removed |

### Known incrementals (not blockers for v1)

| Item | Notes |
|---|---|
| Q2.x `jcl_access` fine-grain (DD-name + DISP + inferred_access_mode per step) | Noted in gold_set freeze banner as Known Gate-3 Incremental; current granularity is job-level |
| `gold_match.py` PoC-to-real-tool | Currently compares Q1.direct_includers only (5/5 MATCH). Extending to Q1.transactions/maps/related_files + Q2/Q3/Q4 is a clean follow-up |
| Q4 field_surface count comparator wiring | Verbatim INITIAL enumerations are in gold_set.md; kuzu count-by-mapset query exists but isn't yet plumbed through gold_match |

---

## 11. Acceptance Criteria A status

**PASSED.** Per `gold_match.py` against frozen `gold/gold_set.md`:

```
[MATCH]    Q1.1.direct_includers: 11 expected; 11 actual
[MATCH]    Q1.2.direct_includers: 12 expected; 12 actual
[MATCH]    Q1.3.direct_includers:  5 expected;  5 actual
[MATCH]    Q1.4.direct_includers: 17 expected; 17 actual
[MATCH]    Q1.5.direct_includers: 11 expected; 11 actual
Total: matched=5 partial=0 fail=0
```

Spot-checks on Q1.transactions / Q1.maps / Q2.program_access / Q3 closure all match the gold (see `gate3/gate3_closure.md` §"Beyond direct_includers"). The Q2.1 USRSEC `jcl_access` value matches after the F5 amendment.

---

**Reproducibility:** `python -m carddemo_graph.gate3` rebuilds everything deterministically from source. Corpus hash `f89baa793cdaff4809b17c2b381cc295a8ec3638cd7333748c8aecdd6564265a` is stable across runs.
