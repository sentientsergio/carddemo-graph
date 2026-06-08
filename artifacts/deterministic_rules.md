# Deterministic Rule Inventory

**Gate 1 output.** Per spec v4 §Pass 1 — deterministic observation.

Each rule has a stable `rule_id`. Every observation in `observations.json` references its producing rule_id. Every edge in `edges.json` traces to rule_id(s) (via its provenance chain).

**Naming:** `RUL-<LANG>(-<SUBCAT>)?-<NNN>` where `<LANG>` ∈ `{COBOL, JCL, JCL-PROC, BMS, CSD, ASM, DERIV, RES}`. Numbers are stable once assigned; deletions create reserved gaps.

**Confidence:** All Pass 1 deterministic rules emit `confidence = 1.0` unless the rule itself produces ambiguous matches (noted per rule).

---

## COBOL rules — `app/cbl/*.{cbl,CBL}` and `app/cpy/*.{cpy,CPY}`, `app/cpy-bms/*.CPY`

Working area is COBOL fixed-format columns 8–72; columns 1–6 (sequence) and 73–80 (identification) are ignored. Column 7 indicator was stripped by the strip pipeline (no comment lines remain).

| rule_id | Detects | Emits |
|---|---|---|
| `RUL-COBOL-001` | `PROGRAM-ID. <name>.` — same-line OR multi-line form (name on a following line, period terminator). Filename mismatch flagged but PROGRAM-ID authoritative. | `entity_candidate(Program, name=<PROGRAM-ID>, id=program:<NAME>)` |
| `RUL-COBOL-002` | `COPY <name>.` and `COPY '<name>'.` (quoted form) outside FD/SD context | `edge_candidate(INCLUDES, from=current-source, to=copybook:<NAME>)` |
| `RUL-COBOL-003` | `COPY <name> REPLACING ... BY ...` (multi-line REPLACING permitted) | `edge_candidate(INCLUDES)` plus `attributes.replacing_terms=[{leading,trailing,by}]` |
| `RUL-COBOL-004` | `COPY <name>.` at FD record-area (within `FD <fdname>` and before `PROCEDURE DIVISION`) | `edge_candidate(DEFINES_LAYOUT_FOR, from=copybook:<NAME>, to=logical-file:<PROGRAM>/<FDNAME>)` |
| `RUL-COBOL-005` | `SELECT <name> ASSIGN TO <dd>` in FILE-CONTROL; pulls in adjacent `ORGANIZATION`, `ACCESS MODE`, `RECORD KEY`, `ALTERNATE RECORD KEY` clauses | `entity_candidate(LogicalFile, id=logical-file:<PROGRAM>/<NAME>)` + `property_observation` (organization, access_mode, record_key, alternate_record_keys, assign_dd) |
| `RUL-COBOL-006` | `READ <logical-file>` (and `READ NEXT/PREVIOUS` browse forms) | `edge_candidate(READS)` |
| `RUL-COBOL-007` | `WRITE <record-of-logical-file>` (record name resolved via FD-record table built in pass) | `edge_candidate(WRITES)` |
| `RUL-COBOL-008` | `REWRITE <record-of-logical-file>` | `edge_candidate(UPDATES)` |
| `RUL-COBOL-009` | `DELETE <logical-file>` | `edge_candidate(DELETES)` |
| `RUL-COBOL-010` | `START <logical-file>` | `edge_candidate(STARTS_BROWSE)` |
| `RUL-COBOL-011` | `CALL '<literal>' [USING ...]` | `edge_candidate(CALLS, kind=static, to=program:<LITERAL>)` |
| `RUL-COBOL-012` | `CALL <identifier> [USING ...]` (no quotes — identifier-based) | `edge_candidate(CALLS, kind=dynamic, to=unresolved:<IDENTIFIER>, breadcrumb=identifier name + surrounding MOVE statements within window)` |
| `RUL-COBOL-013` | `EXEC CICS LINK PROGRAM('<name>')` | `edge_candidate(LINKS_TO, to=program:<NAME>)` |
| `RUL-COBOL-014` | `EXEC CICS XCTL PROGRAM('<name>')` | `edge_candidate(XCTLS_TO, to=program:<NAME>)` |
| `RUL-COBOL-015` | `EXEC CICS RETURN TRANSID('<id>')` | `edge_candidate(RETURNS_TO_TRANSID, to=transaction:<ID>)` |
| `RUL-COBOL-016` | `EXEC CICS SEND MAP('<map>') MAPSET('<mapset>')` (MAPSET optional, default = current mapset) | `edge_candidate(SENDS_MAP, to=bms-map:<MAPSET>/<MAP>)` |
| `RUL-COBOL-017` | `EXEC CICS RECEIVE MAP('<map>') MAPSET('<mapset>')` | `edge_candidate(RECEIVES_MAP, to=bms-map:<MAPSET>/<MAP>)` |
| `RUL-COBOL-018` | `EXEC CICS READ/WRITE/REWRITE/DELETE/STARTBR/READNEXT/READPREV/ENDBR FILE('<file>')` | `edge_candidate(READS/WRITES/UPDATES/DELETES/STARTS_BROWSE)` against `logical-file:<PROGRAM>/<FILE>` (CICS file name; resolved via CSD to Dataset in Pass 3) |
| `RUL-COBOL-019` | `FD <fdname>` declaration | `property_observation` registering FDNAME → LogicalFile mapping for subsequent COBOL-004/006/007/008 rules |
| `RUL-COBOL-020` | Nested COPY (copybooks containing COPY) | `edge_candidate(INCLUDES, from=copybook:<PARENT>, to=copybook:<CHILD>)` |
| `RUL-COBOL-021` | Data-description entry in a copybook record layout (`<level> <name> [REDEFINES x] [PIC p] [USAGE] [OCCURS n].`, multi-line period-terminated) — **v2.2 KU-9**, `app/cpy/` only (BMS symbolic maps in `app/cpy-bms/` excluded; already modeled as BMSField) | `entity_candidate(DataItem, id=dataitem:<COPYBOOK>/<NAME>)` with `level/picture/usage/occurs/redefines/is_filler/is_group/suggested_sql_type/parent_item` + `edge_candidate(HAS_FIELD, copybook→01-root)` or `edge_candidate(CONTAINS_ITEM, parent→child)` via the level-number stack |
| `RUL-COBOL-022` | (reserved) 88-level condition names attached to parent item, non-storage | KU9 stretch seam — not emitted in core |

**RUL-COBOL-001 multi-line behavior.** When `PROGRAM-ID.` appears followed by no name on the same line, the rule advances to the next non-blank line and captures the next identifier as the name (terminated by period). Verified against CardDemo's COACTUPC/COACTVWC/COCRDLIC/COCRDSLC/COCRDUPC.

**RUL-COBOL-018 logical file ID for CICS.** CICS file references use the FILE('NAME') operand. In v1 the logical-file canonical-id for online programs uses the program-scoped form `logical-file:<PROGRAM>/<NAME>`. Pass 3 resolution (RUL-RES-002) chains this to the Dataset via the CSD `DEFINE FILE(<NAME>) DSNAME(...)`.

**RUL-COBOL-021 `suggested_sql_type` mapping (advisory, not authoritative DDL).** Per elementary item from PIC+USAGE: `X(n)/A(n)` → `CHAR(n)`; `9(n)` (display/COMP-3) → `NUMERIC(n)`; `S9(n)V9(m)` → `NUMERIC(n+m,m)`; `9(n)` with `COMP/COMP-4/COMP-5/BINARY` → `INTEGER` (≤9 digits) / `BIGINT` (≤18) / `NUMERIC(n)` (>18); numeric-edited pics (`Z` zero-suppress, `*` check-protect, edited `.` decimal, insertion `, / B` and sign `- + CR DB` ignored) map by digit-position count (e.g. `-ZZZ,ZZZ,ZZZ.ZZ` → `NUMERIC(11,2)`). Group items, FILLER, and OCCURS/REDEFINES *interpretation* (array-vs-child-table, canonical overlay) carry no type — those are downstream decisions; the skeleton records only the facts (`occurs`, `redefines`).

---

## JCL rules — `app/jcl/*.{jcl,JCL}`

| rule_id | Detects | Emits |
|---|---|---|
| `RUL-JCL-001` | `//<name> JOB ...` | `entity_candidate(JCLJob, id=jcl-job:<NAME>)` |
| `RUL-JCL-002` | `//<step> EXEC PGM=<pgm>` | `entity_candidate(JCLStep, id=jcl-step:<JOB>/<STEP>)` + `edge_candidate(INVOKES, from=jcl-step, to=program:<PGM>)` |
| `RUL-JCL-003` | `//<step> EXEC PROC=<proc>` (or implicit `EXEC <proc>` with positional) | `entity_candidate(JCLProcInvocation, id=jcl-proc-inv:<JOB>/<STEP>)` + `edge_candidate(USES_PROC, to=jcl-proc:<PROC>)` |
| `RUL-JCL-004` | `//<dd> DD DSN=<dsn>...` with `DISP=` clause | `entity_candidate(Dataset, id=dataset:<NORMALIZED-DSN>)` + `edge_candidate(USES_DATASET, from=jcl-step, to=dataset:..., attributes={dd_name, allocation_disposition, raw_disp})` |
| `RUL-JCL-005` | `//<dd> DD DUMMY` | `property_observation(jcl-step:..., dd_dummy=<dd>)` |
| `RUL-JCL-006` | `//<dd> DD *` (inline data) | `property_observation(jcl-step:..., dd_inline=<dd>, inline_size_lines=N)` |
| `RUL-JCL-007` | DD concatenation (multiple DSNs under one DD, continuation lines) | `property_observation` linking the secondary DSNs and a `USES_DATASET` edge per |
| `RUL-JCL-008` | Symbolic parameter — usage (`&NAME` in operand) AND declaration (`SYMBOL=value` after PROC) | `property_observation(symbolic_param, name, scope)`; resolution attempted at PROC-invocation expansion |
| `RUL-JCL-009` | DSN containing `&` after parameter substitution attempted: if unresolved tokens remain, Dataset gets `partial: true` and original surface form preserved | property update on the Dataset entity |
| `RUL-JCL-010` | `SYSIN DD DSN=...` or `SYSIN DD *` followed by content naming a dataset/file/program (utility-specific: IDCAMS REPRO, SORT) | `edge_candidate(PASSES_SYSIN_TO, from=jcl-step, to=dataset:.../program:...)` |
| `RUL-JCL-011` | `//JOBLIB JCLLIB ORDER=(...)` | `property_observation(jcl-job:..., jcllib_search_path=[...])` — used by PROC resolution |
| `RUL-JCL-012` | Step-level DD prefix in PROC-invocation (e.g., `//PRC001.FILEIN DD DSN=...`) | `property_observation` linking override to the invoked PROC step |

**RUL-JCL-004 DSN normalization.** GDG references like `AWS.M2.CARDDEMO.TRANSACT.BKUP(+1)` normalize to the base DSN `AWS.M2.CARDDEMO.TRANSACT.BKUP` plus a property `gdg_offset: "+1"`. Reasoning: a Dataset's identity is the base GDG, not the generation.

---

## JCL PROC rules — `app/proc/*.prc` (cataloged) AND inline PROCs anywhere

| rule_id | Detects | Emits |
|---|---|---|
| `RUL-JCL-PROC-001` | `//<name> PROC [params...]` declaration line | `entity_candidate(JCLProc, id=jcl-proc:<DECLARED-NAME>)`. Filename mismatch flagged (RUL-RES-006 applies). |
| `RUL-JCL-PROC-002` | `// PEND` or end-of-file (for cataloged) | property: PROC body delimiter recorded |
| `RUL-JCL-PROC-003` | PROC default parameters on declaration line (`//X PROC PARM1=,PARM2=DEFAULT`) | `property_observation(jcl-proc:..., default_params={...})` |
| `RUL-JCL-PROC-004` | PROC invocation expansion: bind use-site parameters (positional + keyword + overrides) to PROC body | Builds expanded view via `edge_candidate(EXPANDS_TO, from=jcl-proc-inv, to=jcl-step)` for each step in the expanded PROC body |

**Anomaly handled here:** `TRANREPT.prc` declares `//REPROC PROC` on line 1 → RUL-JCL-PROC-001 emits `entity_candidate(JCLProc, id=jcl-proc:REPROC, declared_name=REPROC, source_path=app/proc/TRANREPT.prc)`. Combined with the `entity_candidate` from `REPROC.prc`, Pass 3 conflict resolution (RUL-RES-006) detects the canonical-ID collision and writes a conflict-ledger entry. Filename mismatch flagged separately on the TRANREPT.prc-sourced candidate.

---

## BMS rules — `app/bms/*.bms`

HLASM-format, column 1 = `*` was a comment (stripped). Continuation = `-` in column 72.

| rule_id | Detects | Emits |
|---|---|---|
| `RUL-BMS-001` | `<name> DFHMSD ...` (mapset declaration) | `entity_candidate(BMSMapset, id=bms-mapset:<NAME>)` + `property_observation(lang, mode, ctrl, etc.)` |
| `RUL-BMS-002` | `<name> DFHMDI ...` (map declaration within mapset) | `entity_candidate(BMSMap, id=bms-map:<MAPSET>/<NAME>)` + `property_observation(line, column, size)` |
| `RUL-BMS-003` | `<name> DFHMDF ...` (field declaration) OR positional unnamed `DFHMDF` (no name = filler) | `entity_candidate(BMSField, id=bms-field:<MAPSET>/<MAP>/<NAME>)` + `property_observation(pos, length, attrb, color, initial, prompt)`. For unnamed filler fields, synthesize `bms-field:<MAPSET>/<MAP>/FILLER_<idx>`. |
| `RUL-BMS-004` | HLASM continuation handling (col-72 `-`) — merges continued operand-lines before parsing | parser correctness; no observation directly |

**`BMSField.label` derivation:** When `INITIAL='...'` is present, the literal is `label`. When `PROMPT='...'` is present, that is the label. When neither, label is the empty string (and Q4 contract says "list of `BMSField.label` values" — empty fields included unless we choose to filter).

---

## CSD rules — `app/csd/CARDDEMO.CSD`

Free-form DFHCSDUP syntax. Each `DEFINE` continues across lines until the next top-level keyword.

| rule_id | Detects | Emits |
|---|---|---|
| `RUL-CSD-001` | `DEFINE TRANSACTION(<id>) ... PROGRAM(<pgm>) ...` | `entity_candidate(CICSTransaction, id=transaction:<ID>)` + `edge_candidate(IS_TRANSACTION_FOR, from=transaction:<ID>, to=program:<PGM>)` |
| `RUL-CSD-002` | `DEFINE PROGRAM(<name>) GROUP(...)` | `entity_candidate(Program, id=program:<NAME>, evidence_kind=deterministic)`. Pass 3 sets `partial: true` if no `.cbl`/`.CBL`/`.asm` source exists. |
| `RUL-CSD-003` | `DEFINE MAPSET(<name>) GROUP(...)` | `entity_candidate(BMSMapset, id=bms-mapset:<NAME>)`. Pass 3 reconciles with `.bms` source. |
| `RUL-CSD-004` | `DEFINE FILE(<name>) DSNAME(<dsn>) ...` | `entity_candidate(Dataset, id=dataset:<DSN>)` + `edge_candidate(BINDS_TO, from=logical-file:<online-context>/<NAME>, to=dataset:<DSN>, attributes={binding_source: "CSD"})`. The LogicalFile entity is created in Pass 3 from the union of CSD FILE definitions and online-COBOL `EXEC CICS ... FILE(...)` usages. |

---

## Assembler rules — `app/asm/*.asm`

| rule_id | Detects | Emits |
|---|---|---|
| `RUL-ASM-001` | `<name> CSECT` declaration (control section, the assembler's program-name equivalent) | `entity_candidate(Program, id=program:<NAME>, asm_stub=true)`. No further extraction (assembler-internal control flow out of scope). |

---

## Derived properties (Pass 3 derivations) — `RUL-DERIV-*`

| rule_id | Computes | From |
|---|---|---|
| `RUL-DERIV-001` | `Program.size_loc` | line count of stripped source |
| `RUL-DERIV-002` | `Program.fan_in` | count of `CALLS+LINKS_TO+XCTLS_TO+IS_TRANSACTION_FOR+INVOKES` edges where to=this |
| `RUL-DERIV-003` | `Program.fan_out` | count of `CALLS+LINKS_TO+XCTLS_TO+SENDS_MAP+RECEIVES_MAP+READS+WRITES+UPDATES+DELETES+STARTS_BROWSE+DECLARES_FILE` from this |
| ~~`RUL-DERIV-004`~~ | ~~`Program.inferred_purpose`~~ | **RECLASSIFIED AS ENRICHMENT.** Per the project's skeleton/enrichment principle: LLM-derived properties are not skeleton; they live in `enrichments.json`, not on the entity. Pass 2's promotion step writes inferred_purpose with `evidence_kind: inferred` to that artifact. This rule_id is RETIRED for the skeleton; the corresponding Pass-2 promotion path is documented in `artifacts/schema.json` §EnrichmentsArtifact. |
| `RUL-DERIV-005` | `Program.straddle_score` ∈ [0,1] | Data-coupling breadth, deterministic over the data-access graph (skeleton-class; supersedes the original "cross-cluster edge ratio" sketch, which depended on the informational Q5 naming-convention clustering and was therefore not skeleton-pure). For each in-corpus application program (non-partial Program), the accessed-dataset set combines online accesses (Program -[READS/WRITES/UPDATES/DELETES/STARTS_BROWSE]-> LogicalFile -[BINDS_TO]-> Dataset) and batch accesses (Program <-[INVOKES]- JCLStep -[USES_DATASET]-> Dataset), excluding STEPLIB/JOBLIB DD allocations (load-library plumbing, not data access — the deterministic form of clustering_report.md §1's LOADLIB filter). Over P = in-corpus app programs with ≥1 such access: `straddle_score = |other app programs sharing ≥1 accessed dataset| / (|P|−1)`. Programs with no data access → 0.0; system utilities / phantoms / asm-stubs (partial Programs) are out of scope, not scored. |
| `RUL-DERIV-006` | `Dataset.organization` | Cascade of suffix/name heuristics applied to the normalized DSN base. In order: (1) `.VSAM.KSDS` → `VSAM_KSDS`; (2) `.VSAM.AIX.PATH` → `VSAM_AIX_PATH`; (3) `.PS` → `PS`; (4) `VSAM` token (uncommon) → `VSAM`; (5) `.BKUP`/`.DALY` suffix → `GDG_BASE` (Generation Data Group base; per-generation refs like `BKUP(+1)` are normalized to base by RUL-JCL-004 with a `gdg_offset` property — the base then matches this rule); (6) `LOADLIB` qualifier or `.LOADLIB` suffix → `PDS` (partitioned dataset, typical load-module library naming); (7) sentinels (`NULLFILE`, DSNs starting with `&`) → `UNKNOWN_SENTINEL`; (8) fallback: multi-qualifier DSN with no recognized suffix → `PS` (sequential is the mainframe default for plain-named flat datasets); (9) when JCL DD `DSORG=` is present, it takes precedence over all of the above; (10) when batch COBOL program declaring the file has `ORGANIZATION IS ...`, it takes precedence over (1)-(8) for that program's logical file but not for the underlying Dataset entity. Precedence ordering follows the data-source hierarchy in spec §Conflict handling. |
| ~~`RUL-DERIV-007`~~ | ~~`Dataset.inferred_purpose`~~ | **RECLASSIFIED AS ENRICHMENT** (same path as the retired RUL-DERIV-004 entry above). |
| `RUL-DERIV-008` | `Dataset.centrality` ∈ [0,1] | Application-access degree centrality over the bipartite Program↔Dataset projection (deterministic; supersedes the original "edge-betweenness" sketch — degree is simpler, interpretable, and skeleton-pure). `centrality = |in-corpus app programs accessing the dataset| / |P|`, where the accessed-dataset relation and P are exactly as in RUL-DERIV-005 (online BINDS_TO chain ∪ batch USES_DATASET, STEPLIB/JOBLIB excluded). Datasets with no in-corpus app accessor → 0.0. Ranks the most-shared application resources highest (e.g. ACCTDATA). |
| `RUL-DERIV-009` | `Copybook.reuse_count` | count of `INCLUDES` edges where to=this |
| `RUL-DERIV-010` | `CICSTransaction.fan_out` | count of `RETURNS_TO_TRANSID` to other transactions + downstream programs reachable via `IS_TRANSACTION_FOR` |
| `RUL-DERIV-011` | `USES_DATASET.inferred_access_mode` ∈ {READ, WRITE, UPDATE, DELETE, BROWSE} | DISP value + DD role (utility SYSIN distinguishes IDCAMS REPRO, SORT) + COBOL access verbs against the bound logical file. `inference_basis: ["DISP=SHR + DSORG=KS + READ-only verbs in program X", ...]` |

---

## Resolution rules (Pass 3) — `RUL-RES-*`

| rule_id | Resolves | Precedence / behavior |
|---|---|---|
| `RUL-RES-001` | COBOL `LogicalFile` → JCL DD → `Dataset` chain (batch) | Match LogicalFile.assign_dd to JCL `//<dd>` in the program's invoking step; `BINDS_TO` carries dd_name + binding_source="JCL_DD" |
| `RUL-RES-002` | CICS logical file → CSD `DEFINE FILE` → `Dataset` chain (online) | Match `EXEC CICS ... FILE('<name>')` usage to CSD `DEFINE FILE(<name>) DSNAME(...)`; `BINDS_TO` binding_source="CSD" |
| `RUL-RES-003` | Transaction → Program | CSD authoritative; conflicting source idiom (e.g., a literal in WORKING-STORAGE) recorded as lower-confidence candidate, flagged |
| `RUL-RES-004` | Copybook `DEFINES_LAYOUT_FOR` LogicalFile | When COBOL `COPY` appears inside an FD record area (per RUL-COBOL-004) |
| `RUL-RES-005` | Filename vs. `PROGRAM-ID` | `PROGRAM-ID` authoritative; filename mismatch recorded as anomaly |
| `RUL-RES-006` | Filename vs. declared PROC name | Declared name (`//<name> PROC`) authoritative; filename mismatch recorded as anomaly; multiple files declaring the same name → conflict ledger entry |
| `RUL-RES-007` | PROC inline vs. cataloged | Inline at use-site overrides; both retained; invocation references resolved form |
| `RUL-RES-008` | Map name → mapset | Explicit `MAPSET=` in `EXEC CICS SEND/RECEIVE MAP` overrides default-current; default → secondary candidate |
| `RUL-RES-009` | Copybook path conflict | Closest by path proximity, then alphabetic; all candidates listed in conflict entry |
| `RUL-RES-010` | Logical file → dataset (conflict) | JCL DD (batch) or CICS FCT (online) authoritative; conflicting source → conflict entry, no edge |

---

## Negative rules — must NOT emit

Per spec §Validation, `gold_set_negative.md`. Encoded here as deterministic guards:

| rule_id | Guard |
|---|---|
| `RUL-NEG-001` | Dynamic CALL (RUL-COBOL-012) MUST NOT be promoted to a static `CALLS` edge to a resolved Program. It stays at `to=unresolved:<IDENTIFIER>` unless human-promoted via `manual` evidence_kind. |
| `RUL-NEG-002` | No direct `Program → Dataset` edge. Always via `BINDS_TO`. The schema's edge vocabulary doesn't even contain such an edge type; this rule enforces that Pass 3 never bypasses the chain. |
| `RUL-NEG-003` | Strip-pipeline marker files (`scripts/markers/*`) MUST NOT produce entities. Excluded from input list. |
| `RUL-NEG-004` | Same DD name in different jobs MUST NOT be merged. DD-name is a property of the `USES_DATASET` edge / per-job, not a global identifier. |
| `RUL-NEG-005` | Filename MUST NOT override `PROGRAM-ID` (RUL-RES-005 negated form). |
| `RUL-NEG-006` | A copybook included outside an FD record MUST NOT produce `DEFINES_LAYOUT_FOR`. Only FD-context COPY (RUL-COBOL-004) emits this edge. |
| `RUL-NEG-007` | Comment-only references in original source MUST NOT create entities in stripped extraction. (Implicit: comments are gone from stripped input; rules see only code lines. But the guard is explicit.) |

---

## Rule coverage map: which rules produce which edge types

| Edge type | Producing rule(s) |
|---|---|
| INCLUDES | RUL-COBOL-002, RUL-COBOL-003, RUL-COBOL-020 |
| EXPANDS_TO | RUL-JCL-PROC-004 |
| DEFINES_LAYOUT_FOR | RUL-COBOL-004 |
| CALLS (static) | RUL-COBOL-011 |
| CALLS (dynamic, unresolved) | RUL-COBOL-012 |
| LINKS_TO | RUL-COBOL-013 |
| XCTLS_TO | RUL-COBOL-014 |
| RETURNS_TO_TRANSID | RUL-COBOL-015 |
| SENDS_MAP | RUL-COBOL-016 |
| RECEIVES_MAP | RUL-COBOL-017 |
| DECLARES_FILE | RUL-COBOL-005 |
| BINDS_TO | RUL-RES-001 (batch), RUL-RES-002 (online via RUL-CSD-004) |
| READS | RUL-COBOL-006 (batch), RUL-COBOL-018 (online) |
| WRITES | RUL-COBOL-007, RUL-COBOL-018 |
| UPDATES | RUL-COBOL-008, RUL-COBOL-018 |
| DELETES | RUL-COBOL-009, RUL-COBOL-018 |
| STARTS_BROWSE | RUL-COBOL-010, RUL-COBOL-018 |
| INVOKES | RUL-JCL-002 |
| USES_DATASET | RUL-JCL-004 (+ RUL-DERIV-011 for inferred_access_mode) |
| USES_PROC | RUL-JCL-003 |
| PASSES_SYSIN_TO | RUL-JCL-010 |
| IS_TRANSACTION_FOR | RUL-CSD-001 |

Every edge type in spec §Edge model is covered.

---

## Rule coverage map: which rules produce which entity types

| Entity type | Producing rule(s) |
|---|---|
| Program | RUL-COBOL-001, RUL-CSD-002, RUL-ASM-001 |
| Copybook | (created implicitly by RUL-COBOL-002/003/020 referencing target — Pass 3 materializes from refs and file presence) |
| JCLJob | RUL-JCL-001 |
| JCLStep | RUL-JCL-002, RUL-JCL-003 |
| JCLProc | RUL-JCL-PROC-001 |
| JCLProcInvocation | RUL-JCL-003 |
| LogicalFile | RUL-COBOL-005 (batch), Pass 3 materialization from RUL-COBOL-018 + RUL-CSD-004 (online) |
| Dataset | RUL-JCL-004, RUL-CSD-004 |
| BMSMapset | RUL-BMS-001, RUL-CSD-003 |
| BMSMap | RUL-BMS-002 |
| BMSField | RUL-BMS-003 |
| CICSTransaction | RUL-CSD-001 |

Every entity type in spec §Entity model is covered.

---

## Confidence calibration

- `deterministic` rules emit `confidence = 1.0` unless parsing ambiguity exists (e.g., a CALL operand that looks like both literal and identifier — none observed in CardDemo).
- `resolved` (Pass 3) confidence = product of supporting confidences for independent chain evidence; min for alternative evidence on same claim. Example: a `BINDS_TO` edge resolved through `LogicalFile.assign_dd → JCL DD → DSN` has confidence = 1.0 × 1.0 × 1.0 = 1.0. If a Dataset has `partial: true` due to unresolved symbolic params, downstream edges into it inherit confidence ≤ 0.7.
- `derived` confidence ≤ 0.95 (always below deterministic, to make the kind visible in confidence-class canonicalization). Specific derivation rules can pin tighter values.
- `llm_candidate` is never in `edges.json`. Always promoted (→ `resolved` or `derived`) or rejected before reaching the final graph.
- `manual` requires a reviewer note in `resolution_report.md`.

---

**Reviewer-B (AT) review owed.** Engineer-authored Reviewer-A only.
