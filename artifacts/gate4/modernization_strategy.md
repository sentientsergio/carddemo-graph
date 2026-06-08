# CardDemo — Modernization Strategy

**Target stack:** Java 21 + Spring Boot + Spring Batch + PostgreSQL (Aurora) + AWS-native orchestration — **Step Functions** for inter-job sequencing, **ECS Fargate** for services, **S3** for staging / GDG replacement.

**Source of truth and method:** derived solely from the carddemo-graph v1 KB packet (`carddemo_graph.db` queried in Cypher via kuzu 0.11.3, cross-checked against `entities.json`/`edges.json`). Every structural claim cites a KB entity/edge type. Gaps are tagged `[KU-n]` against `known_unknowns.md` and carried into the risk register (§5). This strategy maps the **extracted v1 corpus**; DB2/IMS/MQ subapps are out of scope and are themselves the largest carried-forward risk `[KU-1]`.

See `operations_manual.md` for the as-built topology this plan transforms.

---

## 1. Architecture abstraction (mainframe → target)

### 1.1 CICS online → Spring Boot services on ECS Fargate

The online surface is **18 CICS transactions → 18 entry programs → BMS screens** (`IS_TRANSACTION_FOR`, `SENDS_MAP`/`RECEIVES_MAP`). Map each transaction to a REST/RPC endpoint on a Spring Boot service:

- **Transaction id → route.** The 18 `CICSTransaction` ids (CC00, CM00, CAUP, …) become API operations; the CSD binding table is the authoritative route map. CC00/COSGN00C is the sign-on/auth entry point.
- **BMS maps → DTOs / view models.** 19 `BMSMap` with 902 `BMSField` (INITIAL/PROMPT labels preserved) give the screen field inventory — the raw material for request/response DTOs and form validation. Field-level *type/length* is **not in the KB** (`DataItem` not modeled `[KU-9]`); DTO typing must be recovered from the COBOL copybooks at build time, not from this packet.
- **Pseudo-conversational state → stateless sessions.** CardDemo carries state in the COMMAREA and uses TRANSID-less `RETURN` (0 `RETURNS_TO_TRANSID` edges `[KU-7]`). In the target this becomes an explicit session/state object (token + server-side or Redis-backed session). The COMMAREA structure (`COCOM01Y`, 17 includers) is the migration contract for that state object.
- **XCTL navigation → service-orchestrated routing.** CICS `XCTL` (no return) becomes either client-driven navigation or a front-controller. **Critical:** 21 of 23 `XCTLS_TO` edges are dynamic MOVE-chain targets `[KU-2]` — the actual screen-to-screen graph is not in the KB. The two static edges (`COSGN00C → COMEN01C`, `COSGN00C → COADM01C`) are the only deductively-known transitions. The full navigation map must be recovered (COBOL `MOVE`-chain analysis / Pass-2 enrichment) before the routing layer can be specified.

### 1.2 JCL → Step Functions + Spring Batch on Fargate

The batch surface is **38 `JCLJob` / 107 `JCLStep`**, invoking 12 in-corpus COBOL batch programs plus MVS utilities (`INVOKES`).

- **Each application COBOL batch program → one Spring Batch job** (reader → processor → writer). The 12 targets (CBACT01C–04C, CBCUS01C, CBTRN02C/03C, CBSTM03A, CBEXPORT, CBIMPORT, COCALL01, COBSWAIT) are the unit of port.
- **JCL job/step sequencing → Step Functions state machines.** A JCL job is a state machine; each step is a state. DISP semantics on `USES_DATASET` (`SHR`/`OLD`/`NEW,CATLG,DELETE`/`MOD,DELETE,DELETE`) encode the read-vs-create-vs-append intent that becomes the state's input/output contract.
- **MVS utilities → native equivalents.** `IDCAMS` REPRO (PS→KSDS load) → Spring Batch flat-file→Aurora loader or `COPY`/bulk insert; `SORT`/`DFSORT` → in-job sort or `ORDER BY`; `IEBGENER` → S3 copy; `IEFBR14` → no-op/allocation state; `IKJEFT1B`/`SDSF`/`FTP`/`DFHCSDUP` → operational tooling, mostly dropped or replaced by AWS-native equivalents. These are all `partial`/external in the KB `[KU-3]` — behavior is inferred from the utility name and DD wiring, not source.
- **PROCs → reusable state-machine fragments / shared Spring Batch steps.** The single `REPROC` PROC (4 `USES_PROC` invocations, 16 `EXPANDS_TO`) becomes a parameterized sub-workflow; its `&CNTLLIB` symbolic `[KU-6]` becomes a Step Functions input parameter resolved per caller (mirroring the existing use-site binding).

### 1.3 VSAM → PostgreSQL (Aurora)

The 11 VSAM KSDS masters become Aurora tables; the 23 CSD `BINDS_TO` bindings + 32 `DEFINES_LAYOUT_FOR` edges give the table inventory and their owning record-layout copybooks:

| VSAM KSDS | Aurora table | Record-layout copybook (key) |
|---|---|---|
| ACCTDATA | account | CVACT01Y |
| CUSTDATA | customer | CVCUS01Y |
| CARDDATA | card | CVACT02Y |
| CARDXREF | card_xref | CVACT03Y |
| TRANSACT | transaction | CVTRA05Y |
| USRSEC | user_security | CSUSR01Y |
| TCATBALF / TRANCATG / TRANTYPE / DISCGRP | reference tables | CVTRA0x family |

- **KSDS primary key → table PK.** `LogicalFile` carries `record_key`/`alternate_record_keys` properties; the KSDS key becomes the PK.
- **VSAM AIX paths → indexes.** The 2 `VSAM_AIX_PATH` datasets (`CARDDATA.AIX`, `CARDXREF.AIX`) become secondary indexes on the Aurora tables (e.g., `CARDXREF` alternate access by account id).
- **Access verbs → DAO operations.** `READS`/`STARTS_BROWSE` → `SELECT`/cursor; `WRITES` → `INSERT`; `UPDATES` (`REWRITE`) → `UPDATE`; `DELETES` → `DELETE`. The 45 online access edges + batch access give the per-table CRUD profile (e.g., USRSEC has the full CRUD set across COUSR00–03C; CARDDATA is read-heavy with one update path in COCRDUPC).
- **Field-level schema gap `[KU-9]`:** the KB has record-level layouts only — no PIC/COMP/OCCURS/REDEFINES. Column types, packed-decimal handling, and array/REDEFINES decomposition must be recovered from the copybooks during table-DDL generation. This is a known, bounded recovery task, not a KB fact.

### 1.4 GDG → S3 versioning; PS staging → S3

- **GDG → S3 with object versioning / date-partitioned prefixes.** 7 `GDG_BASE` datasets + 10 `gdg_offset` references (`+1`/`0`) — e.g., `TRANSACT.BKUP`, `TRANSACT.DALY`, `DALYREJS`, `TCATBALF.BKUP`, `DISCGRP.BKUP`, `TRANTYPE.BKUP`, `TRANCATG.PS.BKUP`, `SYSTRAN`. Generation-relative reads (`(+1)`/`(0)`) map to S3 object versions or `s3://…/yyyy/mm/dd/` prefixes; the generation rollover that GDG does automatically becomes a lifecycle/prefix convention.
- **PS staging files → S3 objects.** 37 PS datasets (import/export `.PS`, `.PSCOMP`/`.ARRYPS`/`.VBPS` renderings, `STATEMNT.PS`/`.HTML`, `EXPORT.DATA`, `*.IMPORT`) are inter-step staging — they become S3 objects passed between Step Functions states. The `STATEMNT.PS → TXT2PDF1 → PDF` chain becomes an S3-triggered render step.
- **LOADLIB (PDS) → container images.** `AWS.M2.CARDDEMO.LOADLIB` (the STEPLIB on 13 jobs) has no analog — compiled artifacts become the Fargate task images.

---

## 2. Decomposition candidates (bounded-context seams)

Seams are read directly off shared-data clustering (§3 of the operations manual; KB Q5 informational). The online clusters are unusually clean because most online programs touch exactly one master.

**Strong single-context services (migrate as-is):**
- **User/Identity service** — USRSEC only: COSGN00C (auth), COUSR00–03C (CRUD). The cleanest context; also the natural first cut because sign-on is the entry point and the table has no cross-context joins.
- **Card service** — CARDDATA(+AIX) only: COCRDLIC (list/browse), COCRDSLC (detail), COCRDUPC (update). Self-contained.

**Cohesive multi-table contexts (one service, multiple tables):**
- **Account/Customer service** — ACCTDATA + CUSTDATA + CARDXREF.AIX move together (COACTUPC/COACTVWC always touch all three). Account, customer, and the card cross-reference are one bounded context at the screen level; splitting them would create chatty cross-service calls. CARDXREF is the join hub.
- **Transaction service** — TRANSACT (+CARDXREF for COTRN02C): COTRN00C/01C/02C. Owns transaction read/write/browse.

**Straddle programs → orchestration services (NOT entities, processes).** Programs touching ≥3 dataset families are the cross-context coordinators — they become Step Functions workflows or saga orchestrators that *call* the bounded-context services rather than owning data:

| Straddle program | Families (count) | Target shape |
|---|---|---|
| CBEXPORT / CBIMPORT | 5–6 | Bulk export/import workflow — orchestrator over all services + S3 |
| CBSTM03A (statement engine) | 5 | Statement-generation workflow: reads transaction/account/customer/xref, emits S3 statement object |
| CBTRN02C (daily posting) | 4 | Posting saga: validates against xref/account/reference, writes transaction, emits rejects |
| CBACT04C (interest calc) | 4 | Interest/fee batch over account + reference + xref |
| CBTRN03C (reporting) | 3 | Reporting workflow over transaction + reference + xref |
| COBIL00C (bill pay, online) | 3 | Bill-payment use case spanning Account + Transaction services |

This split keeps the data-owning services thin and pushes cross-master coordination into explicit orchestration — the natural Step Functions / Spring Batch boundary.

---

## 3. Sequencing (dependency-aware migration order)

Ordering principle: migrate low-coupling, low-fan-in leaves first; defer high-straddle orchestrators until the services they coordinate exist; keep online and batch for the *same* master in sync because they share the KSDS schema (now Aurora table).

**Phase 0 — Foundation (no business logic).**
- Stand up Aurora and generate table DDL from the record-layout copybooks (CVACT01Y/02Y/03Y, CVCUS01Y, CVTRA05Y, CSUSR01Y). This is the gating task and carries the field-level recovery work `[KU-9]`.
- Replace file-load jobs (ACCTFILE/CARDFILE/CUSTFILE/XREFFILE/TRANFILE/DUSRSECJ/TRANCATG/TRANTYPE/TCATBALF/DISCGRP — all IDCAMS PS→KSDS) with Spring Batch S3→Aurora loaders. These are pure load utilities with no application logic — lowest risk, and they validate the table schemas end-to-end.
- Recover the dynamic navigation map `[KU-2]` and COMMAREA state contract — prerequisite for any online routing.

**Phase 1 — User/Identity (vertical slice, proves the pattern).**
- Migrate the USRSEC cluster: COSGN00C + COUSR00–03C online service, plus DUSRSECJ load. Single table, full CRUD already mapped, zero cross-context joins, and it's the auth entry point (CC00). Smallest blast radius, highest learning value.

**Phase 2 — Card and reference data.**
- Card service (COCRDLIC/SLC/UPC on CARDDATA+AIX) — self-contained.
- Reference/lookup tables (TRANTYPE, TRANCATG, DISCGRP, TCATBALF) and their loaders — read-mostly, needed by later transaction/interest flows.

**Phase 3 — Account/Customer/XREF context.**
- Account/Customer service (COACTUPC/VWC) over ACCTDATA+CUSTDATA+CARDXREF, plus the single-master read drivers (CBACT01C/02C/03C, CBCUS01C → READACCT/READCARD/READXREF/READCUST). CARDXREF is the join hub everything downstream needs, so it must land here.

**Phase 4 — Transaction core.**
- Transaction service (COTRN00C/01C/02C) over TRANSACT.
- Then the batch transaction cycle once its dependency tables exist: POSTTRAN (CBTRN02C, daily posting), INTCALC (CBACT04C), TRANREPT/REPROC (CBTRN03C), TRANBKP/COMBTRAN (GDG→S3 backup cycle).

**Phase 5 — Cross-cutting orchestrators (last, because they depend on everything).**
- Statement generation (CREASTMT/CBSTM03A + TXT2PDF1 PDF render) — needs account, customer, transaction, xref all live.
- Export/import bridge (CBEXPORT/CBIMPORT) — the 5–6-family straddlers; only meaningful once all services exist.
- Bill payment (COBIL00C) — spans Account + Transaction.

**Wiring throughout:** each migrated JCL job → a Step Functions state machine; inter-job dependencies (e.g., load → posting → reporting → backup) → Step Functions sequencing; GDG generation chains → S3 versioned prefixes (Phase 4+).

---

## 4. Non-translatable / requires-rework constructs

Constructs with no clean 1:1 target mapping, surfaced so they aren't silently dropped:

- **Pseudo-conversational COMMAREA model** — there is no CICS COMMAREA in the target. Requires an explicit session/state design (§1.1). The COMMAREA layout copybook (`COCOM01Y`) is the contract; the behavioral protocol is partly invisible (`HANDLE`/state verbs not modeled `[KU-8]`).
- **Dynamic XCTL navigation `[KU-2]`** — must be resolved before routing can be built; not derivable from this KB.
- **CICS operational verbs `[KU-8]`** — `HANDLE/ABEND/ASSIGN/INQUIRE`, `ASKTIME/FORMATTIME`, and especially **TS/TD queues** (`WRITEQ/READQ/DELETEQ`) emit no edges. If CardDemo uses TS/TD queues for screen scratchpad or inter-transaction comms, that mechanism is invisible and needs separate discovery before the session/messaging design is fixed.
- **LE runtime services** — `CEE3ABD` (abend handler, fan-in 11), `CEEDAYS` (date) are external `[KU-3]`. The pervasive `CALL CEE3ABD` means error/abend handling is everywhere; its logic must be re-implemented as Java exception handling / Spring `@ControlAdvice` + batch skip/retry policies, designed fresh (not ported).
- **Assembler stubs** — `COBDATFT`, `MVSWAIT` (`asm_stub`, no body `[KU-3]`). `MVSWAIT`/COBSWAIT/WAITSTEP is a timing/sequencing wait → Step Functions `Wait` state. `COBDATFT` (date) → a Java date utility. Both require behavioral re-spec, not translation.
- **Phantom program COCRDSEC (CDV1) `[KU-3]`** — no source body; cannot be migrated from this KB. Must be sourced separately or its transaction retired.
- **GDG generation semantics** — relative-generation addressing (`(+1)`/`(0)`/`(-1)`) has no native S3 analog; needs a versioning/prefix convention plus a generation-rollover process (§1.4).
- **`NULLFILE` / DD-DUMMY** — REPROC's no-op DD references map to skipped/empty inputs in the workflow.

---

## 5. Risk-ranked unknowns (carried forward from `known_unknowns.md`)

Ranked by impact on the migration's correctness and schedule.

| Rank | Unknown | KU ref | Impact | Mitigation |
|---|---|---|---|---|
| 1 | **DB2/IMS/MQ subapps not extracted** — authorization (IMS+DB2+MQ), transaction-type (DB2), VSAM+MQ flows entirely absent | KU-1 | If production CardDemo routes auth/messaging through these, the migration scope is materially larger than this KB shows. Highest schedule risk. | Run extraction over the deferred subapps (Pass-2/separate gate) before committing scope. Do not infer from file names. |
| 2 | **Dynamic XCTL navigation graph** — 21/23 transitions unresolved MOVE-chain targets | KU-2 | Online routing layer cannot be specified; screen-flow tests cannot be derived. Blocks Phases 1–5 online work. | MOVE-chain / control-flow recovery (Pass-2 enrichment) on the 18 `CDEMO-TO-PROGRAM` + `CCARD-NEXT-PROG`/`LIT-MENUPGM` sites. Prerequisite for Phase 0 routing. |
| 3 | **Field-level record layout** — no PIC/COMP/OCCURS/REDEFINES; record-level COPY only | KU-9 | Aurora DDL, packed-decimal/COMP-3 column typing, array/REDEFINES decomposition all unknown. Gates Phase 0 schema. | Parse the layout copybooks at build time for column types; bounded, mechanical, but must precede table creation. |
| 4 | **CICS operational verbs incl. TS/TD queues** not modeled | KU-8 | Hidden inter-transaction comms / scratchpad and error-handling logic; could change the session/messaging design. | Targeted source scan for `WRITEQ/READQ/HANDLE` before fixing the state/session architecture. |
| 5 | **Phantom/external/stub programs** — COCRDSEC (no body), CEE3ABD/CEEDAYS (LE), COBDATFT/MVSWAIT (asm), NONEXEG (test) | KU-3 | Behavior unknowable from KB; abend-handling logic must be re-specified. COCRDSEC (CDV1) cannot be migrated as-is. | Re-spec error handling natively; source or retire COCRDSEC; treat NONEXEG path as test-only. |
| 6 | **Partial logical-file bindings** — 7 CICS file refs (5 in CBIMPORT) with no CSD `DEFINE FILE` | KU (cap. tbl) | Dataset binding for those I/O sites not deductively known; affects CBIMPORT import-target mapping. | Resolve via copybook + JCL DD inspection during the import-bridge phase (Phase 5). |
| 7 | **`&CNTLLIB` symbolic + JCLStep PROC-override partials** — REPROC SYSIN DSN bound at call site, not PROC | KU-6 | REPROC sub-workflow input parameter must be resolved per caller; 3 PROC-override steps reference out-of-scope steps. | Parameterize the Step Functions sub-workflow; bind from each invoking job (TRANREPT/PRTCATBL/TRANBKP) as the JCL does today. |
| 8 | **Per-step DD access-mode inference is narrow** (Q2 incremental) — DISP reliable, semantic READ/WRITE/UPDATE inference partial | KU-10 | Some batch step read/write classifications rely on DISP heuristic, not confirmed access verbs. | Confirm against COBOL file access verbs when porting each batch program (already done per-program for the 12 app programs). |
| 9 | **Identifier-form BMS map operands** — 2 partial maps (runtime-selected screen) | KU-5 | The actual screen sent at those sites (COACTUPC/COCRDLIC family) is runtime-determined. | Resolve alongside the navigation-graph recovery (rank 2). |
| 10 | **Enrichment layer empty** — no inferred purpose/cluster names/MOVE resolutions in v1 | KU-11 | All semantic naming (bounded-context names, program purposes) in this doc is analyst inference over skeleton facts, not KB-asserted. | Treat §2 context names as proposals; confirm with domain owners / Pass-2 enrichment. |

**Closing note on grounding:** every structural fact above is skeleton-grounded (rule-derived, source-cited edges/entities at confidence 1.0). The bounded-context *names*, the straddle-vs-owner *role assignments*, and the phase *ordering* are analyst inferences over those facts — flagged as such — because the KB's enrichment layer is empty in v1 `[KU-11]`. No program, dataset, transaction, map, or job name in this document was invented; each appears in the KB or is an explicit `unresolved:*`/`partial` placeholder.
