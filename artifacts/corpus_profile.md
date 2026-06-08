# Corpus Profile — AWS CardDemo (stripped)

**Gate 0 output.** Per spec v4.1 §Gate 0.

**Inputs:**
- Stripped corpus: `corpus/carddemo/stripped/` (314 files)
- Original-with-comments: `corpus/carddemo/source/` (for spot-checks only)
- Strip provenance: `corpus/carddemo/README.md` (per-syntax strip rules, verification table, idempotence guarantee)

**Author:** engineer agent (`engineer - carddemo-graph`, session `cse_01UcHczjfDVZDmgaXMhr5cQL`)
**Date:** 2026-05-12 (evening)

---

## 1. Inventory by area

```
stripped/
├── app/        240 files  ← extraction target (v1 base mode subset)
├── samples/     15 files  ← sample build/deploy JCL + runtime zips — OUT OF V1 SCOPE
└── scripts/     56 files  ← strip-pipeline artifacts — OUT OF V1 SCOPE
```

### 1.1 `app/` (extraction target)

| Subdir | Files | v1 type | Notes |
|---|---:|---|---|
| `app/cbl/` | 33 | `Program` (COBOL) | Mixed `.cbl`/`.CBL` |
| `app/cpy/` | 31 | `Copybook` | Mixed `.cpy`/`.CPY`; record layouts, working-storage shared structures |
| `app/cpy-bms/` | 18 | `Copybook` (BMS-generated) | Symbolic-map copybooks generated from BMS DSECTs; all `.CPY` |
| `app/jcl/` | 38 | `JCLJob`/`JCLStep` | Mixed `.jcl`/`.JCL`; one `.template` (passthrough) |
| `app/bms/` | 17 | `BMSMapset` → `BMSMap` → `BMSField` | `.bms` source for each online screen |
| `app/proc/` | 2 | `JCLProc` | `REPROC.prc`, `TRANREPT.prc` — cataloged |
| `app/csd/` | 2 | CICS resource defs | `CARDDEMO.CSD` (real) + `.gitkeep` |
| `app/asm/` | 2 | `Program` (assembler stub) | `COBDATFT.asm`, `MVSWAIT.asm` |
| `app/maclib/` | 2 | (informational) | `ASMWAIT.mac`, `COCDATFT.mac` — assembler macros |
| `app/ctl/` | 1 | (informational) | `REPROCT.ctl` — IDCAMS REPRO control card |
| `app/catlg/` | 1 | (informational) | `LISTCAT.txt` — IDCAMS LISTCAT output sample, not source |
| `app/data/` | 23 | (out of entity model) | ASCII + EBCDIC `.PS` datasets — referenced by DSN, not modeled directly |
| `app/scheduler/` | 2 | (out of v1 scope) | CA-7 and Control-M scheduler scripts — scheduling not in entity model |
| `app/app-authorization-ims-db2-mq/` | 39 | DEFERRED EXTENSION | DB2/IMS/MQ subapp — out of v1 base mode |
| `app/app-transaction-type-db2/` | 26 | DEFERRED EXTENSION | DB2 subapp — out of v1 base mode |
| `app/app-vsam-mq/` | 3 | DEFERRED EXTENSION | MQ subapp — out of v1 base mode |

**v1 extraction-target file count: ~145** (app/cbl + app/cpy + app/cpy-bms + app/jcl + app/bms + app/proc + app/csd/CARDDEMO.CSD + app/asm + app/ctl + app/maclib + selective app/catlg).

### 1.2 Excluded from extraction

- **`samples/m2/*.zip`** — runtime binaries (Micro Focus, UniKix). Not source.
- **`samples/jcl/`, `samples/proc/`** — build/deploy JCL (BATCMP, BMSCMP, CICCMP, etc.). Could be modeled later but not in v1 acceptance set.
- **`scripts/markers/`** (52 files) — zero-byte sentinel files left by the strip pipeline. Not corpus content. (Verified empty.)
- **`app/data/`** — actual data files (ASCII text + EBCDIC binaries). Datasets are modeled as `Dataset` entities derived from JCL DSN= bindings, NOT from these files.
- **Deferred subapps** (`app-authorization-ims-db2-mq`, `app-transaction-type-db2`, `app-vsam-mq`) — these use DB2 / IMS / MQ which are explicitly **needs-ext** per spec §Deferred extensions. Out of v1 base mode.
- **`.gitkeep`** files (3) — VCS placeholders.

---

## 2. Naming conventions

### 2.1 COBOL programs
- 8-character names, alphanumeric, uppercase.
- **Batch programs** prefix `CB*`: `CBACT01C`, `CBACT02C`, `CBACT03C`, `CBACT04C`, `CBCUS01C`, `CBEXPORT`, `CBIMPORT`, `CBSTM03A`, `CBSTM03B`, `CBTRN01C`, `CBTRN02C`, `CBTRN03C`. (12 batch programs)
- **Online programs** prefix `CO*`: `COACTUPC`, `COACTVWC`, `COADM01C`, `COBIL00C`, `COBSWAIT`, `COCALL01`, `COCRDLIC`, `COCRDSLC`, `COCRDUPC`, `COEGG01`, `COMEN01C`, `CORPT00C`, `COSGN00C`, `COTRN00C`, `COTRN01C`, `COTRN02C`, `COUSR00C`, `COUSR01C`, `COUSR02C`, `COUSR03C`. (20 online programs)
- **Utility** prefix `CS*`: `CSUTLDTC` (date conversion utility). (1)
- Filename matches `PROGRAM-ID` exactly in the observed sample.

### 2.2 Copybooks
- 8-character names, conventional suffixes:
  - `*Y` suffix: 21 copybooks — typical CardDemo convention (e.g., `CVACT01Y`, `CVCRD01Y`, `CSMSG01Y`).
  - `*01`/`*02`/`*03` numeric suffix: variants of a structure.
- Some names embed domain area: `CV*` for "card view"-ish layouts, `CS*` for shared/system, `CO*` for online-related shared layouts.

### 2.3 BMS-generated copybooks (`cpy-bms/`)
- Filename matches the BMS mapset name: `COSGN00.bms` → `COSGN00.CPY`.
- Naming is 1:1 between `bms/<mapset>.bms` and `cpy-bms/<mapset>.CPY`.

### 2.4 JCL jobs
- Uppercase descriptive names. Driver jobs (e.g., `POSTTRAN`, `INTCALC`), file-load jobs (e.g., `ACCTFILE`, `CARDFILE`, `CUSTFILE`), reporting jobs (e.g., `PRTCATBL`, `TRANREPT`).
- One inline IDCAMS reference convention: jobs named after the dataset they load (`ACCTFILE.jcl` loads `AWS.M2.CARDDEMO.ACCTDATA.VSAM.KSDS`, etc.).

### 2.5 Dataset DSNs
- Uniform high-level qualifier: `AWS.M2.CARDDEMO.*`
- VSAM KSDS: `AWS.M2.CARDDEMO.<NAME>.VSAM.KSDS`
- VSAM AIX paths: `AWS.M2.CARDDEMO.<NAME>.VSAM.AIX.PATH`
- PS datasets: `AWS.M2.CARDDEMO.<NAME>.PS`
- Backup GDGs: `AWS.M2.CARDDEMO.<NAME>.BKUP(+1)`, `AWS.M2.CARDDEMO.<NAME>.DALY(+1)`

### 2.6 CICS transaction IDs
- 4-character codes, grouped by domain area:
  - `CAxx`: Account screens (`CAUP`, `CAVW`)
  - `CBxx`: Bill (`CB00`)
  - `CCxx`: Card screens (`CCDL`, `CCLI`, `CCUP`, `CC00`)
  - `CDxx`: Developer (`CDV1`)
  - `CMxx`: Menu (`CM00`)
  - `CRxx`: Report (`CR00`)
  - `CTxx`: Transactions (`CT00`, `CT01`, `CT02`)
  - `CUxx`: Users (`CU00`–`CU03`)
  - **18 TRANSACTIONs in CSD.**

---

## 3. CICS resource definitions — authoritative source

**Sole v1 CSD:** `app/csd/CARDDEMO.CSD` — 64 `DEFINE` statements, format = DFHCSDUP free-form (multi-line with continuation operands).

### 3.1 Counts (CARDDEMO.CSD)

| DEFINE type | Count | Purpose |
|---|---:|---|
| FILE | 8 | VSAM dataset bindings: `ACCTDAT`, `CARDAIX`, `CARDDAT`, `CCXREF`, `CUSTDAT`, `CXACAIX`, `TRANSACT`, `USRSEC` |
| MAPSET | 17 | All online mapsets (matches `bms/` count) |
| PROGRAM | 18 | Online programs (matches `cbl/CO*` count + 1 phantom — see anomaly #3) |
| TRANSACTION | 18 | All online transactions; each binds to exactly one PROGRAM |
| Other (header/group) | 3 | Group/list machinery |

### 3.2 Transaction → Program map (CSD-authoritative)

| TRANID | PROGRAM | Description (from CSD) |
|---|---|---|
| CAUP | COACTUPC | Credit Card Demo Account Update |
| CAVW | COACTVWC | (no description) |
| CA00 | COADM01C | (no description) |
| CB00 | COBIL00C | (no description) |
| CCDL | COCRDSLC | (no description) |
| CCLI | COCRDLIC | (no description) |
| CCUP | COCRDUPC | Credit Card Update Transaction |
| CC00 | COSGN00C | (no description) |
| **CDV1** | **COCRDSEC** | Developer Transaction - 1 — **target program missing from `cbl/`, see anomaly #3** |
| CM00 | COMEN01C | (no description) |
| CR00 | CORPT00C | (no description) |
| CT00 | COTRN00C | (no description) |
| CT01 | COTRN01C | (no description) |
| CT02 | COTRN02C | (no description) |
| CU00 | COUSR00C | (no description) |
| CU01 | COUSR01C | (no description) |
| CU02 | COUSR02C | (no description) |
| CU03 | COUSR03C | (no description) |

### 3.3 File definitions

8 FILE entries. Each declares a `DSNAME(...)` linking the CICS logical file name to a VSAM dataset.

| CICS FILE | DSNAME | Type |
|---|---|---|
| ACCTDAT | `AWS.M2.CARDDEMO.ACCTDATA.VSAM.KSDS` | KSDS |
| CARDAIX | `AWS.M2.CARDDEMO.CARDDATA.VSAM.AIX.PATH` | AIX path |
| CARDDAT | `AWS.M2.CARDDEMO.CARDDATA.VSAM.KSDS` | KSDS |
| CCXREF | `AWS.M2.CARDDEMO.CARDXREF.VSAM.KSDS` | KSDS |
| CUSTDAT | `AWS.M2.CARDDEMO.CUSTDATA.VSAM.KSDS` | KSDS |
| CXACAIX | `AWS.M2.CARDDEMO.CARDXREF.VSAM.AIX.PATH` | AIX path |
| TRANSACT | `AWS.M2.CARDDEMO.TRANSACT.VSAM.KSDS` | KSDS |
| USRSEC | `AWS.M2.CARDDEMO.USRSEC.VSAM.KSDS` | KSDS |

These are the **authoritative** logical-file → dataset bindings for the online runtime. Per spec conflict-handling table: "Logical file → dataset | JCL DD (batch) or CICS FCT (online) authoritative."

### 3.4 Additional CSDs (out of v1 scope)
- `app/app-vsam-mq/csd/CRDDEMOM.csd`
- `app/app-transaction-type-db2/csd/CRDDEMOD.csd`
- `app/app-authorization-ims-db2-mq/csd/CRDDEMO2.csd`

These belong to the deferred-extension subapps and are not loaded into v1 extraction.

---

## 4. JCL surface

### 4.1 PROC location and form

- **Cataloged PROCs:** 2, both in `app/proc/`
  - `REPROC.prc` — declares `//REPROC PROC`; one step (PRC001, EXEC PGM=IDCAMS) for generic REPRO operations.
  - `TRANREPT.prc` — declares `//REPROC PROC` ← **PROC-name collision anomaly, see anomaly #1**.
- **Inline PROCs (defined inside a JCL job):** 0 in the v1 scope. Confirmed by `grep '^//[A-Z0-9]+ +PROC( |$)'` across `app/jcl/`.

### 4.2 PROC invocation sites (`EXEC PROC=`)

Only 3 invocation sites in the entire corpus, all → `REPROC`:

| Job | Step | Called PROC |
|---|---|---|
| `app/jcl/PRTCATBL.jcl` | STEP05R | REPROC |
| `app/jcl/TRANBKP.jcl` | STEP05R | REPROC |
| `app/jcl/TRANREPT.jcl` | STEP05R | REPROC |

Every other JCL file uses `EXEC PGM=...` directly. **`TRANREPT.prc` is never invoked** anywhere in the corpus — see anomaly #2 (dead PROC).

### 4.3 Symbolic parameters in use

Very small set:
- `&CNTLLIB` — control-card library path (override at use-site)
- `&HLQ` — high-level qualifier override
- `&SYSUID` — z/OS standard user-id var
- `&SYUID` — **almost certainly a typo of `&SYSUID`**, observed in JCL header (one occurrence) — anomaly #4

### 4.4 EXEC patterns

JCL is overwhelmingly straight `EXEC PGM=<name>` against COBOL/SORT/IDCAMS/IEFBR14. Common utilities observed:
- `IDCAMS` — VSAM define/delete/repro
- `SORT` — DFSORT
- `IEBGENER` — sequential copy
- `IEBCOPY` — partitioned dataset copy (less common here)
- `IEFBR14` — null op for dataset disposition
- `LISTCAT` — catalog listing utility

---

## 5. COBOL surface

### 5.1 Batch vs online programs

- **Batch programs** (`CB*`, 12 in `cbl/`): use `SELECT` / `ASSIGN` / `ORGANIZATION` / `ACCESS MODE` / `FD` declarations in `FILE-CONTROL`. Standard COBOL file I/O.
- **Online programs** (`CO*`, 20 in `cbl/`): **no `FILE-CONTROL` section.** File access is entirely via `EXEC CICS READ/WRITE/REWRITE/DELETE/STARTBR/READNEXT/READPREV/ENDBR` against CICS logical files (which the CSD binds to VSAM datasets).

This is a clean and important split for resolver-chain logic:
- For batch: `Program` → `LogicalFile` (via SELECT/ASSIGN) → `BINDS_TO` → `Dataset` (via JCL DD).
- For online: `Program` → uses CICS logical file (via `EXEC CICS verb FILE(...)`) — the file is the CSD-defined logical file name, which `BINDS_TO` its `Dataset` per CSD `DSNAME(...)`.

### 5.2 `PROGRAM-ID` format

**Multi-line `PROGRAM-ID` is present.** All `COA*C`, `COCRD*C` programs (5 confirmed) use:
```
       PROGRAM-ID.
           COACTUPC.
```

Other programs (e.g., `CBACT01C`, `COSGN00C`) put the name on the same line:
```
       PROGRAM-ID. CBACT01C.
```

**Deterministic rule must handle both** — Gate 1 rule `RUL-COBOL-001` (PROGRAM-ID extraction).

Trailing identification area (columns 73–80) is preserved per strip rules and shows up as e.g. `0002000` on `COBSWAIT`'s PROGRAM-ID line. Parser should ignore col 73+.

### 5.3 COPY statement inventory

- Plain `COPY <name>.` — most common.
- `COPY '<name>'.` (quoted form) — observed (e.g., `COPY 'CSUTLDWY'.` in COACTUPC line 130).
- `COPY <name> REPLACING ...` — used heavily. `CSSETATY` is COPYed with REPLACING ≥10 times per COACTUPC alone (different attribute substitutions).
- `COPY DFHBMSCA`, `COPY DFHAID` — IBM-supplied CICS copybooks (not in corpus); will resolve to `Unresolved` with surface form.

### 5.4 `CALL` inventory

Static (literal) CALLs found:
- In-corpus targets: `CBSTM03B`, `COBDATFT`, `CSUTLDTC`, `MVSWAIT`
- LE runtime (external, unresolved): `CEE3ABD`, `CEEDAYS`
- **`NONEXEG`** — appears in one program; likely a deliberate "missing program" used to test error paths. Will become `Unresolved`. (Could also be a typo — to verify in Gate 2.)

**Dynamic CALLs (identifier-based, e.g., `CALL WS-PROGRAM-NAME`)** — **zero observed** in v1 scope. The deterministic rule for dynamic CALL detection should still exist (Q3's `unresolved_reaches` contract relies on it), but produces no matches on this corpus.

### 5.5 EXEC CICS verb coverage

Observed counts across all online COBOL:

| Verb | Count | Spec edge type |
|---|---:|---|
| SEND | 31 | `SENDS_MAP` (when MAP operand present) |
| RETURN | 27 | `RETURNS_TO_TRANSID` (when TRANSID operand present) |
| READ | 20 | `READS` (file) |
| RECEIVE | 17 | `RECEIVES_MAP` (when MAP operand present) |
| XCTL | 10 | `XCTLS_TO` |
| HANDLE | 8 | (operational, no edge) |
| STARTBR | 6 | `STARTS_BROWSE` |
| READPREV | 6 | `READS` (browse direction) |
| ENDBR | 5 | (browse close; no new edge type per spec) |
| READNEXT | 4 | `READS` (browse direction) |
| ABEND | 4 | (operational, no edge) |
| WRITE | 3 | `WRITES` |
| REWRITE | 2 | `UPDATES` |
| ASSIGN | 2 | (operational, no edge) |
| WRITEQ | 1 | (TS/TD queue, no edge in v1 vocab) |
| INQUIRE | 1 | (operational, no edge) |
| FORMATTIME | 1 | (operational, no edge) |
| DELETE | 1 | `DELETES` |
| ASKTIME | 1 | (operational, no edge) |

**Not observed: `EXEC CICS LINK`.** No `LINKS_TO` edges will be populated by this corpus. The schema retains the edge type but its instance count for CardDemo is zero. Worth noting in `report.md`.

---

## 6. BMS surface

- 17 mapsets in `app/bms/`; each is also represented as a symbolic-map copybook in `cpy-bms/`.
- Standard BMS-macro form: `DFHMSD` (mapset header) → `DFHMDI` (map definition) → `DFHMDF` (field definitions).
- Continuation: `-` in column 72 (HLASM-style). Visible in stripped output.
- Fields typically have positional attributes (`POS=(row,col)`, `LENGTH=`), display attributes (`ATTRB=(...)`), color (`COLOR=`), and many have `INITIAL='...'` literal text — that literal is the `BMSField.label` per spec.
- Generated symbolic-map copybooks follow standard IBM convention: each field becomes `<NAME>L` (length), `<NAME>F` (flag), `<NAME>I` (input value), with REDEFINES for output (`<NAME>A`).
- The `bms/<X>.bms` source is authoritative for the user-visible field labels (per Q4 contract); the `cpy-bms/<X>.CPY` is what online programs `COPY` to address those fields.

---

## 7. Anomalies

Numbered, with the deterministic rule or conflict-handling path each will go through.

### Anomaly 1 — PROC-name collision: `REPROC.prc` and `TRANREPT.prc` both declare `//REPROC PROC`

**Observed.** Both files declare themselves as PROC `REPROC` on line 1. By the spec analog of "PROGRAM-ID authoritative over filename" (canonical-name conflict-handling table), both files claim canonical ID `jcl-proc:REPROC`. Filenames disagree: `REPROC.prc` (matches) and `TRANREPT.prc` (mismatch — filename says TRANREPT, contents say REPROC).

**Diagnosis (informational, not extractor concern):** `TRANREPT.prc` appears to be a copy-paste artifact — its body is *almost identical* to the body of the inlined steps of `TRANREPT.jcl` (the actual job driver), suggesting it was generated from the same template and the header line was copied from REPROC.prc without correction. The PROC is dead: never invoked.

**Resolution path:**
- Gate 1 rule `RUL-JCL-PROC-001` (PROC-name extraction) reads the `//name PROC` declaration.
- Conflict-ledger entry in `resolution_report.md` of type `proc_name_collision`: two source files, same canonical name. Both retained as candidates; neither edge produced until conflict is human-reviewed.
- Filename mismatch anomaly recorded for `TRANREPT.prc` (filename ≠ declared PROC name).

### Anomaly 2 — Cataloged PROC with no callers: `TRANREPT.prc`

**Observed.** No `EXEC PROC=TRANREPT` anywhere in the corpus. Combined with anomaly #1 (it declares itself as REPROC anyway), it's effectively dead.

**Resolution path:** Reported in `report.md` as dead PROC. Does not block Q1–Q4.

### Anomaly 3 — Phantom program in CSD: `COCRDSEC`

**Observed.** `DEFINE PROGRAM(COCRDSEC)` and `DEFINE TRANSACTION(CDV1) PROGRAM(COCRDSEC)` exist in `CARDDEMO.CSD`, but no `COCRDSEC.cbl` (or `COCRDSEC.CBL`) is present in `app/cbl/`. CDV1 is described in CSD as "Developer Transaction - 1" — likely a developer tool deliberately excluded from the open-source corpus.

**Resolution path:**
- CSD-derived `Program` entity for `COCRDSEC` created with `partial: true` (or `Unresolved` flavor) and surface form preserved.
- `IS_TRANSACTION_FOR(transaction:CDV1, program:COCRDSEC)` edge created with `evidence_kind: deterministic`, source = CSD; the `program:COCRDSEC` entity itself carries `provenance.from = CSD only` and `partial: true`.
- Reported in `unresolved` summary.

### Anomaly 4 — Typo symbolic param: `&SYUID` (vs. `&SYSUID`)

**Observed.** One JCL header uses `&SYUID` where every other instance uses `&SYSUID`. Almost certainly a typo, not an intentional separate variable.

**Resolution path:** Symbolic-parameter inventory rule records both surface forms verbatim; reporter flags `&SYUID` as singleton with low resolution probability. No entity/edge impact for v1 acceptance.

### Anomaly 5 — Multi-line `PROGRAM-ID` (5 programs)

**Observed.** `COACTUPC`, `COACTVWC`, `COCRDLIC`, `COCRDSLC`, `COCRDUPC` use multi-line PROGRAM-ID:
```
       PROGRAM-ID.
           NAME.
```

**Resolution path:** `RUL-COBOL-001` must support multi-line PROGRAM-ID (period terminator can be on same line as name, or name itself terminates with period after a following line). Not actually anomalous, just a parser correctness requirement.

### Anomaly 6 — `EXEC CICS LINK` absent entirely

**Observed.** Zero LINK statements in v1 scope. Closed-vocabulary edge `LINKS_TO` exists in schema but no instances. Worth flagging because Gate 2 subset will not validate this edge type.

**Implication:** Either choose a Gate 2 subset that exercises an alternative edge (XCTL is plentiful, will substitute), or accept that `LINKS_TO` is schema-only for CardDemo. Spec Gate 2 says: "subset contains at least one example of each critical edge type." `LINKS_TO` is critical-vocabulary; absence in corpus means we cannot satisfy this clause for `LINKS_TO`. Document as a known coverage limit.

### Anomaly 7 — `NONEXEG` referenced as CALL target

**Observed.** `CALL 'NONEXEG' USING WS-DATE-IN` in one program. No `NONEXEG.cbl` in corpus. Pattern (and the deliberately-unpronounceable name) suggests intentional "missing program" used for error-handling testing.

**Resolution path:** Treated as `Unresolved` per the standard chain.

### Anomaly 8 — `LISTCAT.txt` is IDCAMS output, not source

**Observed.** `app/catlg/LISTCAT.txt` is a captured LISTCAT *result*, not a script that produces it. Useful as informational reference (dataset attributes) but not extractable as source.

**Resolution path:** Excluded from extractor input; available to Pass 2 (LLM) on request as context when a dataset attribute is ambiguous.

### Anomaly 9 — Strip pipeline marker files in `scripts/markers/`

**Observed.** 52 zero-byte sentinel files named after COBOL programs / dataset names, e.g., `scripts/markers/CBACT01C`, `scripts/markers/CUSTFILE`. Strip-pipeline metadata, not corpus.

**Resolution path:** Extractor input list excludes everything under `scripts/`.

---

## 8. Schema implications for Gate 1

Folded from Gate 0 findings into the Gate 1 schema design:

1. **`partial: true` flag on `Program` entities** (per spec) for CSD-only programs (e.g., `COCRDSEC`). Confirm flag semantics in `schema.json`.
2. **PROC canonical-id rule** — use the `//name PROC` declared name, not filename. Add `filename_mismatch_anomaly` provenance flag when they disagree (`TRANREPT.prc` → declared `REPROC` collision case).
3. **Multi-line `PROGRAM-ID` parsing** — `RUL-COBOL-001` requires lookahead until period terminator.
4. **`COPY REPLACING`** — record `replacing_terms` on the `INCLUDES` edge; copybook canonical-id is still the base name, but the include-site provenance must capture that REPLACING applied (for downstream agent reasoning about effective vs. nominal copybook contents).
5. **`LINKS_TO` vocabulary slot** — keep in schema for portability; v1 instance count for CardDemo is zero. Note in `kb_capabilities.md` denominators.
6. **Logical file → dataset for online programs:** must consult CSD `DEFINE FILE` for online-side `BINDS_TO`. For batch-side, JCL DD. The spec's precedence "JCL DD (batch) or CICS FCT (online)" applies — and `CICS FCT` here means the `DEFINE FILE` resource defs in CARDDEMO.CSD.
7. **DD name shared across multiple JCL jobs** — by spec, treat each job's DD as distinct binding (no merging). Will be true in CardDemo — there are repeated DD names like `TRANFILE` across jobs.
8. **`samples/`, `scripts/`, `app/data/`, deferred subapps, `.gitkeep`** — all excluded from corpus by extractor's input-list rule.

---

## 9. Go / no-go on Gate 0

| Spec Gate-0 exit criterion | Status |
|---|---|
| Inventory reviewed | ✅ — sections 1, 2 |
| Unexpected types triaged | ✅ — anomalies §7, scope decisions §1.2 |
| Schema implications identified | ✅ — §8 |
| CICS definition source confirmed | ✅ — `app/csd/CARDDEMO.CSD` (sole v1 CSD; 3 others belong to deferred subapps) |
| Go / no-go recorded | ✅ — **GO** |

**Go.** Proceed to Gate 1 (schema and deterministic rule inventory). Pre-frozen positions:

- v1 extraction scope = ~145 files (`app/{cbl,cpy,cpy-bms,jcl,bms,proc,asm,ctl,maclib}/` + `app/csd/CARDDEMO.CSD` + selective `app/catlg/LISTCAT.txt` as Pass-2 reference only).
- v1 base mode confirmed: COBOL, JCL, BMS, CICS, VSAM, copybooks, CSD, assembler. No DB2/IMS/MQ.
- `LINKS_TO` edge type retained in schema but corpus instance count will be zero; Gate 2 subset substitutes `XCTLS_TO` as the inter-program control-flow exemplar.
- Phantom program (`COCRDSEC`) and PROC-name collision (`REPROC.prc` / `TRANREPT.prc`) will exercise the unresolved + conflict-ledger paths in Gate 2.
- Strip-pipeline marker files and runtime zip samples explicitly excluded from extractor input.

---

**Reviewer-B (AT) review owed:** the project sponsor, AT pass. This profile is **engineer-authored, Reviewer-A only** until your review.
