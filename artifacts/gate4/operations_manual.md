# CardDemo — Operations Manual (as-built, KB-derived)

> **⚠️ SUPERSEDED SNAPSHOT (schema 1.0.0).** This is the frozen Gate-4 deliverable, produced from the `gate3-fulltree-2026-05-13` run (schema 1.0.0, **1347 entities / 926 edges**). The knowledge base has since grown: the v2.2 KU-9 DataItem field layer brought the live graph to **1864 entities / 1445 edges** (see the current `graph_summary.md` / `kb_capabilities.md`), and the grammar-parser (MAPA) is now the default extractor (**1863 / 1444**, with copybook-origin reachability the regex path could not resolve). The figures below describe the 1.0.0 snapshot as-built; they are retained verbatim as the Gate-4 record, not as current totals.

**Source of truth:** the carddemo-graph v1 knowledge-base packet (`carddemo_graph.db`, `entities.json`, `edges.json`). Run `gate3-fulltree-2026-05-13`, schema `1.0.0`, corpus hash `f89baa79…`. Every claim below cites a KB entity/edge type. Where the KB does not know something, it is flagged with a `[KU-n]` tag pointing at the numbered section of `known_unknowns.md`.

**Query path:** queried the kuzu graph (`carddemo_graph.db`) in Cypher via `kuzu` 0.11.3 (anaconda Python 3.10), cross-checked against `entities.json`/`edges.json` for full provenance lists. Counts as-built for this 1.0.0 run: **1347 entities / 926 edges**, all confidence 1.0. *(Correction: the prior wording "counts reconcile with `graph_summary.md` / `kb_capabilities.md` (1347/926)" is stale — those packet summaries were since regenerated to the v2.2 live totals 1864/1445 and no longer carry 1347/926; see the superseded-snapshot banner above.)*

**Scope:** v1 base mode only — COBOL, JCL, BMS, CICS resource definitions (CSD), VSAM, copybooks, assembler stubs. DB2/IMS/MQ subapps are **not extracted** `[KU-1]`. The figures here describe the extracted corpus, not the full upstream CardDemo distribution.

---

## 1. Runtime topology

CardDemo runs as two cooperating surfaces over one shared VSAM data layer: an **online CICS** surface (18 transactions → screen programs → BMS maps) and a **batch JCL** surface (38 jobs → COBOL batch programs + MVS utilities → sequential/VSAM/GDG datasets). The two surfaces meet on the same KSDS clusters.

### 1.1 Online CICS surface

The CSD (`CARDDEMO.CSD`) is the authoritative binding source. It defines **18 `CICSTransaction` entities**, each bound to one entry program via an `IS_TRANSACTION_FOR` edge (18 edges, all `evidence_kind: resolved`/CSD). The complete transaction→program table:

| TRANID | Entry program | Functional area (from data coupling, §3) |
|---|---|---|
| CC00 | COSGN00C | Sign-on (the entry transaction) |
| CM00 | COMEN01C | Main menu |
| CA00 | COADM01C | Admin menu |
| CAUP | COACTUPC | Account update |
| CAVW | COACTVWC | Account view |
| CB00 | COBIL00C | Bill payment |
| CCLI | COCRDLIC | Card list |
| CCDL | COCRDSLC | Card detail |
| CCUP | COCRDUPC | Card update |
| CDV1 | COCRDSEC | Developer/security tool — **phantom** `[KU-3]` |
| CT00 | COTRN00C | Transaction list |
| CT01 | COTRN01C | Transaction view |
| CT02 | COTRN02C | Transaction add |
| CR00 | CORPT00C | Reporting |
| CU00 | COUSR00C | User list |
| CU01 | COUSR01C | User add |
| CU02 | COUSR02C | User update |
| CU03 | COUSR03C | User delete |

(Cited: `IS_TRANSACTION_FOR` edges; `graph_summary.md` CSD binding table.)

**Screen surface (BMS).** 17 `BMSMapset` entities, 19 `BMSMap`, **902 `BMSField`** entities (every `DFHMDF` in every mapset, with INITIAL/PROMPT labels preserved). Programs drive screens through **20 `SENDS_MAP` + 17 `RECEIVES_MAP` edges (37 total map interactions)**. Each online program owns one literal mapset (e.g., `COSGN00C`→`COSGN00/COSGN0A`, 37 fields; `COACTUPC`→`COACTUP/CACTUPA`, 128 fields — the largest screen). Field counts per map are queryable (`BMSField` grouped by `map_id`).

**Navigation between screens** is the operationally important pattern: programs transfer control with `EXEC CICS XCTL` (control transfer, no return). There are **23 `XCTLS_TO` edges**, of which only **2 are statically resolvable** — both from the sign-on program: `COSGN00C → COMEN01C` and `COSGN00C → COADM01C`. The other **21 are dynamic** (`call_kind: dynamic`), routed to `unresolved:*` placeholders because the target is a runtime `MOVE`-chain value `[KU-2]`:
- `unresolved:CDEMO-TO-PROGRAM` — 18 sites (the universal menu-navigation target across almost every online program)
- `unresolved:CCARD-NEXT-PROG` — 2 sites (`COCRDLIC` card-detail navigation)
- `unresolved:LIT-MENUPGM` — 1 site (`COCRDLIC`)

**Two CICS control-flow patterns are confirmed absent at the corpus level** (grep-verified, not extractor gaps) `[KU-7]`:
- **`LINKS_TO` = 0** — CardDemo never uses `EXEC CICS LINK` (call-with-return). All inter-program control is XCTL.
- **`RETURNS_TO_TRANSID` = 0** — every `EXEC CICS RETURN` is TRANSID-less; the pseudo-conversational next-transaction is carried in the COMMAREA, not on the RETURN.

### 1.2 Batch JCL surface

**38 `JCLJob` entities, 107 `JCLStep` entities** (job→step linkage is by id namespace `jcl-step:JOB/STEP`, not an edge). Steps invoke programs via **102 `INVOKES` edges**. Twelve of those targets are in-corpus application batch programs (the rest are MVS utilities — IDCAMS fan-in 62, SORT, IEBGENER, IEFBR14, SDSF, all `partial`/external `[KU-3]`):

| Batch program | Invoking step(s) | Role (from dataflow §1.3) |
|---|---|---|
| CBACT01C | READACCT/STEP05 | Account master read/extract |
| CBACT02C | READCARD/STEP05 | Card master read |
| CBACT03C | READXREF/STEP05 | Card-xref read |
| CBACT04C | INTCALC/STEP15 | Interest calculation (account update) |
| CBCUS01C | READCUST/STEP05 | Customer master read |
| CBEXPORT | CBEXPORT/STEP02 | Full-corpus VSAM→sequential export |
| CBIMPORT | CBIMPORT/STEP01 | Sequential→VSAM import |
| CBSTM03A | CREASTMT/STEP040 | Statement generation (calls CBSTM03B 13×) |
| CBTRN02C | POSTTRAN/STEP15 | Daily transaction posting |
| CBTRN03C | TRANREPT/STEP10R, REPROC/STEP10R | Transaction reporting |
| COBSWAIT | WAITSTEP/WAIT | Wait/sequencing stub (calls MVSWAIT asm) |
| COCALL01 | DISCGRP/STEP20 | Disclosure-group loader (calls NONEXEG — test path) |

(Cited: `INVOKES` edges; partial flags from `Program.partial`.)

**Static batch sub-program calls** (`CALLS`, 32 edges, all `call_kind: static`): the dominant fan-out is `CBSTM03A → CBSTM03B` (13 call sites — the statement engine's worker), plus a date-utility chain `CORPT00C`/`COTRN02C → CSUTLDTC → CEEDAYS`, and a pervasive `→ CEE3ABD` (LE abend handler, 11 fan-in) wired into nearly every batch program for error capture. `CBACT01C → COBDATFT` (assembler date stub).

**PROC usage.** 1 `JCLProc` (`REPROC`), invoked 4× via `USES_PROC` from `PRTCATBL`, `TRANBKP`, `TRANREPT`, and `REPROC` itself; PROC bodies expand to inline steps through **16 `EXPANDS_TO` edges**. The single conflict-ledger entry is the REPROC PROC-name collision (`REPROC.prc` and `TRANREPT.prc` both declare canonical id `jcl-proc:REPROC`; resolved by the `//<name> PROC` line per RUL-RES-006 — see `resolution_report.md`).

### 1.3 Data layer

**62 `Dataset` entities** by organization (`Dataset.organization`):

| Organization | Count | Notes |
|---|---:|---|
| PS (physical sequential) | 37 | flat files, import/export staging, report output |
| VSAM_KSDS | 11 | the master files (keyed) |
| GDG_BASE | 7 | generation data groups (backups, daily cycles) |
| VSAM_AIX_PATH | 2 | alternate-index paths (CARDXREF, CARDDATA) |
| VSAM | 2 | ESDS/RRDS variants of USRSEC |
| PDS | 1 | `AWS.M2.CARDDEMO.LOADLIB` (load library, STEPLIB) |
| UNKNOWN_SENTINEL | 2 | `NULLFILE` and `&CNTLLIB` symbolic `[KU-6]` |

**The 11 KSDS master files are the system's spine.** The 8 CSD-bound CICS files (authoritative `BINDS_TO` chain) and their DSNs:

| CICS FILE | Dataset (KSDS unless noted) |
|---|---|
| ACCTDAT | AWS.M2.CARDDEMO.ACCTDATA.VSAM.KSDS |
| CUSTDAT | AWS.M2.CARDDEMO.CUSTDATA.VSAM.KSDS |
| CARDDAT | AWS.M2.CARDDEMO.CARDDATA.VSAM.KSDS |
| CARDAIX | AWS.M2.CARDDEMO.CARDDATA.VSAM.AIX.PATH |
| CCXREF | AWS.M2.CARDDEMO.CARDXREF.VSAM.KSDS |
| CXACAIX | AWS.M2.CARDDEMO.CARDXREF.VSAM.AIX.PATH |
| TRANSACT | AWS.M2.CARDDEMO.TRANSACT.VSAM.KSDS |
| USRSEC | AWS.M2.CARDDEMO.USRSEC.VSAM.KSDS |

(Cited: CSD bindings in `graph_summary.md`; 23 `BINDS_TO` edges, `evidence_kind: resolved`, `binding_source: CSD`.)

**Online↔batch contact points.** The CICS files above are the *same* KSDS clusters that batch jobs allocate via `USES_DATASET` (136 edges across 31 jobs). For example `AWS.M2.CARDDEMO.TRANSACT.VSAM.KSDS` is read/written online by COBIL00C/COTRN00C/COTRN01C/COTRN02C **and** batch-touched by CBEXPORT, COMBTRAN, CREASTMT, POSTTRAN, TRANBKP, TRANREPT, TRANFILE, REPROC. This shared-cluster contact is the dominant change-safety surface (§5).

**Access semantics** come from edge types: online COBOL `READS`(66)/`WRITES`(118)/`UPDATES`(8, `REWRITE`)/`DELETES`(1)/`STARTS_BROWSE`(6); batch `USES_DATASET` carries `dd_name` + `allocation_disposition` (raw DISP: `SHR`, `OLD`, `(NEW,CATLG,DELETE)`, `(MOD,DELETE,DELETE)`). Note: per-step inferred READ/WRITE/UPDATE mode is a known Gate-3 incremental — DISP is reliable, the semantic mode inference is narrow `[KU-10]`.

**Record layouts.** 50 `Copybook` entities. 32 `DEFINES_LAYOUT_FOR` edges bind record-layout copybooks to logical files: `CVACT03Y` (card-xref, 6 files), `CVACT01Y` (account, 5), `CVTRA05Y` (transaction, 4), `CVCUS01Y` (customer), `CVACT02Y` (card). Field-level layout (PIC/level/OCCURS/REDEFINES) is **not modeled** `[KU-9]` — only record-level COPY relationships.

---

## 2. Batch pipeline (job-level dataflow)

The batch surface, reconstructed from `INVOKES` + `USES_DATASET` (with DISP) edges. This is the operational picture of how data moves day-to-day.

**File-load / setup jobs (PS → VSAM KSDS via IDCAMS REPRO):** `ACCTFILE`, `CARDFILE`, `CUSTFILE`, `XREFFILE`, `TRANFILE`, `TRANCATG`, `TRANTYPE`, `TCATBALF`, `DISCGRP` each take a `*.PS` flat file (`SHR`) and load the corresponding `*.VSAM.KSDS` (`OLD`/`SHR`). `DUSRSECJ` loads `USRSEC.PS` → `USRSEC.VSAM.KSDS`. `DEFGDGD`/`DEFGDGB` define GDG bases; `OPENFIL`/`CLOSEFIL` are CICS file-state jobs.

**Read/extract jobs:** `READACCT` (CBACT01C) reads `ACCTDATA.VSAM.KSDS` and emits three sequential renderings (`.PSCOMP`, `.ARRYPS`, `.VBPS`, all `NEW,CATLG`). `READCARD`/`READXREF`/`READCUST` are the equivalent single-master read drivers (CBACT02C/03C, CBCUS01C).

**Core business cycle:**
- **POSTTRAN** (CBTRN02C): reads `DALYTRAN.PS` (daily input) + `TRANSACT.VSAM.KSDS` + `CARDXREF.VSAM.KSDS` + `ACCTDATA.VSAM.KSDS` + `TCATBALF.VSAM.KSDS`, writes `DALYREJS` (rejects, `NEW,CATLG`). This is the daily posting straddle program (§4).
- **INTCALC** (CBACT04C): reads `TCATBALF` + `CARDXREF` (KSDS+AIX) + `ACCTDATA` + `DISCGRP.VSAM.KSDS`, writes `SYSTRAN` (`NEW,CATLG`). Interest/fee computation.
- **CREASTMT** (CBSTM03A): the statement run — SORT `TRANSACT.VSAM.KSDS` → `TRXFL.SEQ` → `TRXFL.VSAM.KSDS`, joins `CARDXREF`+`ACCTDATA`+`CUSTDATA`, emits `STATEMNT.PS` and `STATEMNT.HTML`. `TXT2PDF1` then renders `STATEMNT.PS` to PDF.
- **TRANREPT** (CBTRN03C, via REPROC PROC): backs up `TRANSACT.VSAM.KSDS` → `TRANSACT.BKUP` (GDG), SORTs to `TRANSACT.DALY` (GDG), joins `CARDXREF`+`TRANTYPE`+`TRANCATG`+`DATEPARM`, emits `TRANREPT` report. `REPROC`, `PRTCATBL`, `TRANBKP` reuse the same PROC.

**Backup / GDG-cycle jobs:** `TRANBKP`, `COMBTRAN` (combines `TRANSACT.BKUP` GDG generations → `TRANSACT.COMBINED` → reload KSDS), `PRTCATBL` (TCATBALF report + GDG backup). 10 datasets carry `gdg_offset` markers (`+1`/`0`) — these are the generation-relative references that S3-versioning replaces (§modernization).

**Import/export bridge:** `CBEXPORT` (CBEXPORT) reads all five master KSDS + writes one consolidated `EXPORT.DATA` (PS); `CBIMPORT` (CBIMPORT) reverses it, writing five `*.IMPORT` PS files + `IMPORT.ERRORS`. These two are the widest data-straddlers in the system (§4).

**Utility/test jobs:** `ESDSRRDS` (USRSEC ESDS/RRDS variants), `INTRDRJ1`/`INTRDRJ2` (FTP/internal-reader test paths with GDG), `WAITSTEP` (COBSWAIT→MVSWAIT sequencing stub).

---

## 3. Functional clustering (online, from shared-data access)

Grouping online programs by the KSDS families they touch (`READS`/`WRITES`/`UPDATES`/`DELETES`/`STARTS_BROWSE` → `BINDS_TO` → Dataset) yields clean seams:

- **USER-SEC cluster:** COSGN00C (read), COUSR00C (read+browse), COUSR01C (write), COUSR02C (read+update), COUSR03C (read+delete) — all and only on `USRSEC.VSAM.KSDS`. Cleanest bounded context.
- **CARD cluster:** COCRDLIC (read+browse `CARDDATA`), COCRDSLC (read `CARDDATA`+AIX), COCRDUPC (read+update `CARDDATA`) — all and only on `CARDDATA.VSAM.KSDS`/AIX.
- **TRANSACTION cluster:** COTRN00C (read+browse), COTRN01C (read), COTRN02C (read+write+browse `TRANSACT`, also reads `CARDXREF`).
- **ACCOUNT/CUSTOMER/XREF cluster:** COACTUPC and COACTVWC each touch `ACCTDATA` + `CUSTDATA` + `CARDXREF.AIX` together — account, customer, and the card-cross-reference are coupled at the screen level (the natural straddle).
- **BILL cluster:** COBIL00C touches `ACCTDATA` + `CARDXREF.AIX` + `TRANSACT` (read/write/browse) — bill payment writes transactions.

(Cited: 45 online program→dataset access rows via `BINDS_TO`.)

---

## 4. Failure surfaces (where things break / where the KB goes dark)

These are the operational fragility points the graph makes explicit.

1. **Dynamic screen navigation is a black box `[KU-2]`.** 21 of 23 `XCTLS_TO` edges are unresolved MOVE-chain targets. Operationally: you cannot statically determine, from this KB, which screen a given online program transfers to at runtime — the next-program is a COMMAREA value set by a `MOVE`. **The "functional next-program graph" of the online app is incomplete.** A Q3 transaction-closure from `CC00` (COSGN00C) yields only `COMEN01C` and `COADM01C` statically; everything past the menu is `unresolved:CDEMO-TO-PROGRAM`. Any runbook for "what happens after screen X" must be reconstructed from runtime behavior, not this KB.

2. **Phantom and external programs `[KU-3]`.** `COCRDSEC` (transaction CDV1) is CSD-defined but **has no source body** — a developer/security tool excluded from the distribution; its behavior is unknowable here. `NONEXEG` is a deliberate "missing program" reached by `COCALL01` on a test path (a `CALL` that intentionally abends). `MVSWAIT`/`COBDATFT` are assembler stubs (no body analysis). LE-runtime programs `CEE3ABD` (abend handler), `CEEDAYS` (date) are external. These are valid graph citizens for closure but carry zero internal-behavior detail.

3. **Error-handling and timing are not modeled `[KU-8]`.** `EXEC CICS HANDLE/ABEND/ASSIGN/INQUIRE`, `ASKTIME/FORMATTIME`, and TS/TD queue verbs (`WRITEQ/READQ/DELETEQ`) emit no edges. CardDemo's actual error-recovery and any queue-based communication are invisible. The pervasive batch `CALL CEE3ABD` shows abend handling *exists* but not its logic.

4. **Unresolved file/symbolic references.**
   - 7 `LogicalFile` partials are CICS file references that didn't chain to a CSD `DEFINE FILE` — 5 in `CBIMPORT` (CUSTOMER/ACCOUNT/CARD-XREF/TRAN/CARD records, `referenced_but_not_directly_observed`) plus `COCRDLIC/TO` and `CBSTM03A/TO`. Their dataset binding is not deductively known.
   - `dataset:&CNTLLIB` is an unresolved JCL symbolic parameter in `REPROC.prc` `[KU-6]` — the real DSN is bound at the *calling* job (`CNTLLIB=…` on `TRANREPT.jcl` etc.), not in the PROC body. The `PASSES_SYSIN_TO` edge (the only one in the corpus) lands on this partial.
   - `dataset:NULLFILE` (REPROC FILEIN/FILEOUT) is the DD-DUMMY sentinel.
   - 3 `JCLStep` partials (`PRTCATBL/PRC001`, `TRANBKP/PRC001`, `TRANREPT/PRC001`) are PROC-expansion DD-override sites referencing steps outside the local scope.
   - 2 `BMSMap` partials (`LIT-THISMAPSET/LIT-THISMAP`, `CCARD-NEXT-MAPSET/CCARD-NEXT-MAP`) are identifier-form map operands — the actual screen sent is a runtime value `[KU-5]`.

5. **Out-of-scope integration paths `[KU-1]`.** Any DB2/IMS/MQ behavior in the deferred subapps (`app-authorization-ims-db2-mq`, `app-transaction-type-db2`, `app-vsam-mq`) is entirely absent. If production CardDemo authorization/MQ flows route through those, this KB cannot see the failure surface there.

---

## 5. Change-safety surfaces (blast radius)

The graph is fan-in/fan-out-complete (partials counted), so blast radius is directly queryable.

**Copybook blast radius (touch-one, rebuild-many).** Direct `INCLUDES` fan-in:

| Copybook | Direct includers | Blast meaning |
|---|---:|---|
| CSSETATY | 39 | screen-attribute REPLACING template — touches almost every online program |
| CSDAT01Y, CSMSG01Y, COTTL01Y, COCOM01Y | 17 each | universal online preamble (date, message, title, COMMAREA) |
| DFHBMSCA, DFHAID | 17 each | IBM-supplied, **content not in corpus** `[KU-4]` |
| CSUSR01Y | 12 | user/session/security record layout |
| CVACT03Y | 12 | card-xref record layout (also 6 `DEFINES_LAYOUT_FOR`) |
| CVTRA05Y | 11 | transaction record layout (4 `DEFINES_LAYOUT_FOR`) |
| CVACT01Y | 11 | account record layout (5 `DEFINES_LAYOUT_FOR`) |
| CVCUS01Y, CVACT02Y | 8 each | customer / card record layouts |

A change to `CVACT01Y` (account layout) forces recompilation/retest of 11 direct includers and revalidation of the 5 logical files it defines — and because the account KSDS is shared online↔batch (§1.3), online (COACTUPC/COACTVWC/COBIL00C) and batch (CBACT01C/04C, CBTRN02C, CBEXPORT, CBSTM03A) move together. Record-layout copybooks are the highest-leverage change-risk because they propagate across both surfaces *and* into on-disk data format.

**Program fan-in (call/invoke dependents).** Among in-corpus app programs, `CBSTM03B` has fan-in 13 (all from CBSTM03A) and `CSUTLDTC` fan-in 4 — both shared utilities whose behavior change ripples to callers. (Top raw fan-in is `IDCAMS` at 62, but that's the MVS utility, not application code.)

**Dataset coupling (the real cross-cutting risk).** The KSDS clusters touched by the most distinct programs are the change-amplifiers:
- `TRANSACT.VSAM.KSDS` — 4 online + ~8 batch programs.
- `CARDXREF.VSAM.KSDS` (+AIX) — the cross-reference everyone joins through: COACTUPC/COACTVWC/COBIL00C/COTRN02C online; CBTRN02C/03C, CBACT04C, CBEXPORT, CBSTM03A, INTCALC, TRANREPT batch.
- `ACCTDATA.VSAM.KSDS` — account master, online update path (COACTUPC `UPDATES`) plus 6 batch readers.

**Straddle programs (multi-context, orchestration candidates).** Programs touching ≥3 dataset families (online+batch union):

| Program | Families touched | Role |
|---|---|---|
| CBEXPORT | ACCOUNT, CARD, CARDXREF, CUSTOMER, STATEMENT, TRANSACTION (6) | widest — full export |
| CBIMPORT | ACCOUNT, CARDXREF, CUSTOMER, STATEMENT, TRANSACTION (5) | full import |
| CBSTM03A | ACCOUNT, CARDXREF, CUSTOMER, STATEMENT, TRANSACTION (5) | statement engine |
| CBTRN02C | ACCOUNT, CARDXREF, REFERENCE, TRANSACTION (4) | daily posting |
| CBACT04C | ACCOUNT, CARDXREF, REFERENCE, TRANSACTION (4) | interest calc |
| CBTRN03C | CARDXREF, REFERENCE, TRANSACTION (3) | transaction reporting |
| COACTUPC, COACTVWC | ACCOUNT, CARDXREF, CUSTOMER (3) | account screens |
| COBIL00C | ACCOUNT, CARDXREF, TRANSACTION (3) | bill payment |

(Cited: program→dataset-family projection over `BINDS_TO` + `INVOKES`/`USES_DATASET`. Note: `Program.straddle_score` and `Dataset.centrality` columns exist in the schema but are **null in v1** — this projection is computed by the analyst from the access edges, not read from a precomputed property `[KU-11]`.)

**Bottom line for change planning:** the safe-to-touch units are the single-context online clusters (USER-SEC, CARD) and single-master batch readers. The dangerous edits are (a) the shared record-layout copybooks (CVACT01Y/CVACT03Y/CVTRA05Y/CVCUS01Y), (b) the `CARDXREF`/`TRANSACT`/`ACCTDATA` KSDS schemas, and (c) the straddle batch programs that read four+ masters at once.
