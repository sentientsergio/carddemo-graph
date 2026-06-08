# Gold Set — Frozen

> **STATUS: FROZEN 2026-05-13.**
> **Reviewer A:** engineer agent (`engineer - carddemo-graph`, session `cse_01UcHczjfDVZDmgaXMhr5cQL`).
> **Reviewer B:** the project sponsor; an independent source-grep cross-check pass verified the citations.
> **Known Gate-3 incremental (not a blocker, will be folded during Gate-3 review):** Q2.1-Q2.5 `jcl_access` fine-grain (DD-name + DISP + inferred_access_mode per step).
> **Changelog:** see `gold/gold_set_changelog.md`.
>
> **Discipline:** Every entry has a grep-verifiable line citation. Inferences from naming convention without source verification are excluded. Per the project's skeleton-vs-enrichment principle: only *deductive composition with a named rule* qualifies as skeleton answer. Heuristic / control-flow / LLM-judgment goes to the enrichment side or to Unresolved with breadcrumb.

## Revisions in this pass (vs. initial Reviewer-A submission)

1. **Q2.1 USRSEC** — corrections per the source-grep review:
   - REMOVED COADM01C (declares WS-USRSEC-FILE but never uses it in EXEC CICS verbs — verified)
   - COSGN00C line corrected 165 → 166 (DATASET operand line per convention)
   - COUSR00C: added READPREV (582); ENDBR has no edge (per spec); STARTBR/READNEXT/READPREV with correct lines
   - COUSR01C: WRITES only at 190 (corrected — earlier "READS / WRITES" was wrong)
2. **Q2.2-Q2.5** — re-traced from scratch via source grep, not naming-convention inference. Each entry has its verb line + operand line + the WS/LIT constant binding it to the CSD file name.
3. **Q3.2 CAUP** — RE-CORRECTED (2026-06-01): reachable_programs = [program:CSUTLDTC, program:CEEDAYS]; unresolved_reaches retains CDEMO-TO-PROGRAM (identifier-form XCTL). The earlier "CSUTLDTC is NOT called" was based on a program-body-only grep that missed COPY-expanded calls — COACTUPC `COPY CSUTLDPY` (3743) and CSUTLDPY contains `CALL 'CSUTLDTC'` (255); CSUTLDTC.cbl→CEEDAYS (93). Source-traced; see Q3.2 note + changelog.
4. **Q3.3 CT01** — unchanged: COTRN01C does NOT COPY CSUTLDPY (no copybook-expanded call), so reachable_programs = [] remains correct.
5. **Q4.2 CAUP** — enumerated all 52 INITIAL= clauses from `app/bms/COACTUP.bms`.
6. **Q1** — entries retained from prior pass; no source-grep-review findings against Q1.

## Format

Each Qx entry: `input`, `expected` (the resolver query result), `freeze_status` = PENDING-B-REVIEW.

For Q1/Q2 entries, every `expected` row has a `rule_id` and a verbatim line citation. Citations follow the convention **operand-line** (the line bearing the dataset/copybook/map name), since that's what the source-grep review used and what `gold_match.py`'s canonicalization can compare structurally.

---

# Q1 — Direct copybook inclusion impact

(Q1.1-Q1.5 entries from prior submission retained — the source-grep review surfaced no findings against them. Reproduced for completeness.)

## Q1.1 — `copybook:CVACT01Y` (Account record layout)

**freeze_status:** PENDING-B-REVIEW

### Input
```json
{ "copybook_id": "copybook:CVACT01Y" }
```

### Expected — `direct_includers` (11 programs)
| program_id | source_path | line | rule_id |
|---|---|---:|---|
| program:CBACT01C | app/cbl/CBACT01C.cbl | 61 | RUL-COBOL-002 |
| program:CBACT04C | app/cbl/CBACT04C.cbl | 89 | RUL-COBOL-002 |
| program:CBEXPORT | app/cbl/CBEXPORT.cbl | 50 | RUL-COBOL-004 (FD-context: FD ACCOUNT-INPUT) |
| program:CBIMPORT | app/cbl/CBIMPORT.cbl | 59 | RUL-COBOL-004 (FD-context: FD ACCOUNT-OUTPUT) |
| program:CBSTM03A | app/cbl/CBSTM03A.CBL | 24 | RUL-COBOL-002 |
| program:CBTRN01C | app/cbl/CBTRN01C.cbl | 96 | RUL-COBOL-002 |
| program:CBTRN02C | app/cbl/CBTRN02C.cbl | 98 | RUL-COBOL-002 |
| program:COACTUPC | app/cbl/COACTUPC.cbl | 559 | RUL-COBOL-002 |
| program:COACTVWC | app/cbl/COACTVWC.cbl | 191 | RUL-COBOL-002 |
| program:COBIL00C | app/cbl/COBIL00C.cbl | 55 | RUL-COBOL-002 |
| program:COTRN02C | app/cbl/COTRN02C.cbl | 65 | RUL-COBOL-002 |

### Expected — `transactions` (4 — only online programs that are direct includers)
| transaction_id | program_id |
|---|---|
| transaction:CAUP | program:COACTUPC |
| transaction:CAVW | program:COACTVWC |
| transaction:CB00 | program:COBIL00C |
| transaction:CT02 | program:COTRN02C |

### Expected — `maps` (literal-form SEND/RECEIVE from direct-includer online programs)
| program_id | map_id | direction | line |
|---|---|---|---:|
| program:COBIL00C | bms-map:COBIL00/COBIL0A | SEND | 252 |
| program:COBIL00C | bms-map:COBIL00/COBIL0A | RECEIVE | 262 |
| program:COTRN02C | bms-map:COTRN02/COTRN2A | SEND | 471 |
| program:COTRN02C | bms-map:COTRN02/COTRN2A | RECEIVE | 486 |

(COACTUPC/COACTVWC use identifier-form `MAP(LIT-THISMAP) MAPSET(LIT-THISMAPSET)` — MOVE-chain resolution required, classified enrichment per the skeleton/enrichment principle. Not in the skeleton answer.)

### Expected — `jobs` / `jcl_steps` (JCL EXEC PGM= invoking batch includers)
| program | invoking_jcl_job |
|---|---|
| CBACT01C | jcl-job:READACCT |
| CBACT04C | jcl-job:INTCALC |
| CBEXPORT | jcl-job:CBEXPORT |
| CBIMPORT | jcl-job:CBIMPORT |
| CBSTM03A | jcl-job:CREASTMT |
| CBTRN01C | jcl-job:DALYREJS |
| CBTRN02C | jcl-job:POSTTRAN (STEP15) |

### Expected — `related_files` (DEFINES_LAYOUT_FOR — FD-context only)
| logical_file_id | rule_id |
|---|---|
| logical-file:CBEXPORT/ACCOUNT-INPUT | RUL-COBOL-004 (line 50) |
| logical-file:CBIMPORT/ACCOUNT-OUTPUT | RUL-COBOL-004 (line 59) |

---

## Q1.2 — `copybook:CSUSR01Y` (User session layout)

(Unchanged from prior submission — direct grep verified.)

### Input
```json
{ "copybook_id": "copybook:CSUSR01Y" }
```

### Expected — `direct_includers` (12 online programs)
| program_id | line |
|---|---:|
| program:COACTUPC | 556 |
| program:COACTVWC | 189 |
| program:COADM01C | 34 |
| program:COCRDLIC | 223 |
| program:COCRDSLC | 176 |
| program:COCRDUPC | 295 |
| program:COMEN01C | 34 |
| program:COSGN00C | 31 |
| program:COUSR00C | 57 |
| program:COUSR01C | 29 |
| program:COUSR02C | 41 |
| program:COUSR03C | 41 |

### Expected — `transactions` (12 — one per direct-includer; all bind via CSD)
| transaction_id | program_id |
|---|---|
| transaction:CA00 | program:COADM01C |
| transaction:CAUP | program:COACTUPC |
| transaction:CAVW | program:COACTVWC |
| transaction:CC00 | program:COSGN00C |
| transaction:CCDL | program:COCRDSLC |
| transaction:CCLI | program:COCRDLIC |
| transaction:CCUP | program:COCRDUPC |
| transaction:CM00 | program:COMEN01C |
| transaction:CU00 | program:COUSR00C |
| transaction:CU01 | program:COUSR01C |
| transaction:CU02 | program:COUSR02C |
| transaction:CU03 | program:COUSR03C |

### Expected — `maps` (literal-form only)
| program_id | map_id | direction (lines) |
|---|---|---|
| program:COADM01C | bms-map:COADM01/COADM1A | SEND 141, RECEIVE 150 |
| program:COMEN01C | bms-map:COMEN01/COMEN1A | SEND 175, RECEIVE 184 |
| program:COSGN00C | bms-map:COSGN00/COSGN0A | SEND 114, RECEIVE 76 |
| program:COUSR00C | bms-map:COUSR00/COUSR0A | SEND 472,480 / RECEIVE 490 |
| program:COUSR01C | bms-map:COUSR01/COUSR1A | SEND 148, RECEIVE 158 |
| program:COUSR02C | bms-map:COUSR02/COUSR2A | SEND 230, RECEIVE 240 |
| program:COUSR03C | bms-map:COUSR03/COUSR3A | SEND 177, RECEIVE 187 |

### Expected — `jobs`/`jcl_steps`/`related_files`: empty (all 12 includers are online; CSUSR01Y is never FD-context)

---

## Q1.3 — `copybook:CVCRD01Y` (Card record layout)

### Input
```json
{ "copybook_id": "copybook:CVCRD01Y" }
```

### Expected — `direct_includers` (5 online programs)
| program_id | line |
|---|---:|
| program:COACTUPC | 533 |
| program:COACTVWC | 165 |
| program:COCRDLIC | 177 |
| program:COCRDSLC | 153 |
| program:COCRDUPC | 227 |

### Expected — `transactions`
| transaction_id | program_id |
|---|---|
| transaction:CAUP | program:COACTUPC |
| transaction:CAVW | program:COACTVWC |
| transaction:CCDL | program:COCRDSLC |
| transaction:CCLI | program:COCRDLIC |
| transaction:CCUP | program:COCRDUPC |

### Expected — `maps`: empty (all card-screen SEND/RECEIVE use identifier-form operands — enrichment, not skeleton)
### Expected — `jobs`/`jcl_steps`/`related_files`: empty

---

## Q1.4 — `copybook:COCOM01Y` (Common online layout)

### Input
```json
{ "copybook_id": "copybook:COCOM01Y" }
```

### Expected — `direct_includers` (17 programs)
| program_id | line |
|---|---:|
| program:COACTUPC | 565 |
| program:COACTVWC | 167 |
| program:COADM01C | 26 |
| program:COBIL00C | 38 |
| program:COCRDLIC | 179 |
| program:COCRDSLC | 155 |
| program:COCRDUPC | 229 |
| program:COMEN01C | 26 |
| program:CORPT00C | 113 |
| program:COSGN00C | 24 |
| program:COTRN00C | 37 |
| program:COTRN01C | 28 |
| program:COTRN02C | 47 |
| program:COUSR00C | 42 |
| program:COUSR01C | 22 |
| program:COUSR02C | 25 |
| program:COUSR03C | 25 |

### Expected — `transactions` (17 + 1 phantom = 18)

All 18 CARDDEMO.CSD transactions bind to one of the 17 online programs above OR to the phantom `program:COCRDSEC` (CDV1 transaction). Phantoms count — `program:COCRDSEC` is `partial: true` per RUL-CSD-002.

| transaction_id | program_id |
|---|---|
| transaction:CA00 | program:COADM01C |
| transaction:CAUP | program:COACTUPC |
| transaction:CAVW | program:COACTVWC |
| transaction:CB00 | program:COBIL00C |
| transaction:CC00 | program:COSGN00C |
| transaction:CCDL | program:COCRDSLC |
| transaction:CCLI | program:COCRDLIC |
| transaction:CCUP | program:COCRDUPC |
| transaction:CDV1 | program:COCRDSEC (partial — phantom) |
| transaction:CM00 | program:COMEN01C |
| transaction:CR00 | program:CORPT00C |
| transaction:CT00 | program:COTRN00C |
| transaction:CT01 | program:COTRN01C |
| transaction:CT02 | program:COTRN02C |
| transaction:CU00 | program:COUSR00C |
| transaction:CU01 | program:COUSR01C |
| transaction:CU02 | program:COUSR02C |
| transaction:CU03 | program:COUSR03C |

(Wait: COCRDSEC doesn't COPY COCOM01Y — no source body exists. So the Q1.4 transactions list should EXCLUDE CDV1 since its program doesn't include COCOM01Y. **Excluded.** Final count: 17 transactions, one per online includer.)

### Expected — `maps`: per-includer literal-form maps (see Q1.2 for the subset; COBIL00C/COTRN0xC/CORPT00C/COSGN00C add their own — full enumeration deferred to AT review)

### Expected — `related_files`: empty

---

## Q1.5 — `copybook:CVTRA05Y` (Transaction record layout)

### Input
```json
{ "copybook_id": "copybook:CVTRA05Y" }
```

### Expected — `direct_includers` (11 programs)
| program_id | line | rule_id |
|---|---:|---|
| program:CBACT04C | 94 | RUL-COBOL-002 |
| program:CBEXPORT | 56 | RUL-COBOL-004 (FD-context: FD-TRANSACTION-INPUT) |
| program:CBIMPORT | 69 | RUL-COBOL-004 (FD-context: FD-TRANSACTION-OUTPUT) |
| program:CBTRN01C | 101 | RUL-COBOL-002 |
| program:CBTRN02C | 84 | RUL-COBOL-002 |
| program:CBTRN03C | 70 | RUL-COBOL-002 |
| program:COBIL00C | 57 | RUL-COBOL-002 |
| program:CORPT00C | 121 | RUL-COBOL-002 |
| program:COTRN00C | 54 | RUL-COBOL-002 |
| program:COTRN01C | 45 | RUL-COBOL-002 |
| program:COTRN02C | 64 | RUL-COBOL-002 |

### Expected — `transactions` (5)
| transaction_id | program_id |
|---|---|
| transaction:CB00 | program:COBIL00C |
| transaction:CR00 | program:CORPT00C |
| transaction:CT00 | program:COTRN00C |
| transaction:CT01 | program:COTRN01C |
| transaction:CT02 | program:COTRN02C |

### Expected — `related_files`
| logical_file_id |
|---|
| logical-file:CBEXPORT/TRANSACTION-INPUT |
| logical-file:CBIMPORT/TRANSACTION-OUTPUT |

---

# Q2 — Dataset access (revised, source-verified)

**Methodology:** For each dataset, I grepped (a) `VALUE '<csd_file_name>'` to find WS/LIT constants in each program that resolve to the CSD file name; (b) `(DATASET|FILE) *\(<ws-name>` paired with the preceding `EXEC CICS <verb>` line to find actual access sites; (c) `DSN=<dsn>` across JCL to find batch DD bindings. Citations are operand-line of the EXEC CICS verb (the line bearing DATASET/FILE operand).

## Q2.1 — `dataset:AWS.M2.CARDDEMO.USRSEC.VSAM.KSDS` (CSD FILE USRSEC)

### Input
```json
{ "dataset_id": "dataset:AWS.M2.CARDDEMO.USRSEC.VSAM.KSDS" }
```

### Expected — `program_access` (online, via CSD `DEFINE FILE(USRSEC) DSNAME(...)` chain)

| program_id | logical_file_id | mode | edge_type | verb_line | operand_line |
|---|---|---|---|---:|---:|
| program:COSGN00C | logical-file:COSGN00C/USRSEC | READ | READS | 165 | 166 |
| program:COUSR00C | logical-file:COUSR00C/USRSEC | STARTBR | STARTS_BROWSE | 521 | 522 |
| program:COUSR00C | logical-file:COUSR00C/USRSEC | READNEXT | READS | 550 | 551 |
| program:COUSR00C | logical-file:COUSR00C/USRSEC | READPREV | READS | 581 | 582 |
| program:COUSR01C | logical-file:COUSR01C/USRSEC | WRITE | WRITES | 189 | 190 |
| program:COUSR02C | logical-file:COUSR02C/USRSEC | READ | READS | 271 | 272 |
| program:COUSR02C | logical-file:COUSR02C/USRSEC | REWRITE | UPDATES | 306 | 307 |
| program:COUSR03C | logical-file:COUSR03C/USRSEC | READ | READS | 218 | 219 |
| program:COUSR03C | logical-file:COUSR03C/USRSEC | DELETE | DELETES | 253 | 254 |

(COADM01C declares `WS-USRSEC-FILE` but never uses it in any EXEC CICS verb. NOT a USRSEC accessor. Source-verified.)
(ENDBR statements in COUSR00C at line 612-613 are operational; no edge per spec closed vocab.)

### Expected — `jcl_access`
| jcl_job_id | role | source_path |
|---|---|---|
| jcl-job:DUSRSECJ | define/load | app/jcl/DUSRSECJ.jcl |

**Note (post-freeze amendment 2026-05-13, F5):** Only DUSRSECJ.jcl references `DSN=AWS.M2.CARDDEMO.USRSEC.VSAM.KSDS` (the Q2.1 target). ESDSRRDS.jcl references `USRSEC.VSAM.ESDS` and `USRSEC.VSAM.RRDS` — separate `Dataset` entities, not in scope for this Q2.1 jcl_access. See `gold_set_changelog.md` for the amendment record + scoping clarification (Q2 `jcl_access` = JCL DD allocations to the exact-DSN dataset; family-name variants are distinct entities).

(Specific DD names + inferred_access_mode is a Known Gate-3 Incremental per freeze banner.)

---

## Q2.2 — `dataset:AWS.M2.CARDDEMO.ACCTDATA.VSAM.KSDS` (CSD FILE ACCTDAT)

### Expected — `program_access`

| program_id | constant_used | mode | edge_type | verb_line | operand_line |
|---|---|---|---|---:|---:|
| program:COACTUPC | LIT-ACCTFILENAME = 'ACCTDAT ' | READ | READS | 3320 | 3321 |
| program:COACTUPC | LIT-ACCTFILENAME = 'ACCTDAT ' | READ | READS | 3470 | 3471 |
| program:COACTUPC | LIT-ACCTFILENAME = 'ACCTDAT ' | REWRITE | UPDATES | 3609 | 3610 |
| program:COACTVWC | LIT-ACCTFILENAME = 'ACCTDAT ' | READ | READS | 667 | 668 |
| program:COBIL00C | WS-ACCTDAT-FILE = 'ACCTDAT ' | READ | READS | 293 | 294 |
| program:COBIL00C | WS-ACCTDAT-FILE = 'ACCTDAT ' | REWRITE | UPDATES | 324 | 325 |

(Constants verified: COACTUPC line 516, COACTVWC line 146, COBIL00C line 16, COTRN02C line 16 — COTRN02C declares the constant but does NOT use it in any EXEC CICS verb against ACCTDAT — verified, not in access list.)

**Note (post-freeze amendment 2026-05-28, Finding D):** COACTUPC accesses ACCTDAT at THREE sites (READ@3320, READ@3470, REWRITE@3609 — all via `LIT-ACCTFILENAME`), not one. The initial freeze listed only the 3320 READ; the 3470 READ and 3609 REWRITE were a Reviewer-A omission, surfaced when the corrected two-line WS-constant resolver (Finding A fix) made the extractor more complete than the gold. Added 2026-05-28 with the sponsor's sign-off. See `gold_set_changelog.md`.

### Expected — `jcl_access`
| jcl_job_id | source_path |
|---|---|
| jcl-job:ACCTFILE | app/jcl/ACCTFILE.jcl (load) |
| jcl-job:CBEXPORT | app/jcl/CBEXPORT.jcl |
| jcl-job:CBIMPORT | app/jcl/CBIMPORT.jcl |
| jcl-job:CREASTMT | app/jcl/CREASTMT.JCL |
| jcl-job:INTCALC | app/jcl/INTCALC.jcl |
| jcl-job:POSTTRAN | app/jcl/POSTTRAN.jcl |
| jcl-job:READACCT | app/jcl/READACCT.jcl |

(7 batch jobs reference the ACCTDATA dataset via DSN; specific DD names + inferred_access_mode TBD.)

---

## Q2.3 — `dataset:AWS.M2.CARDDEMO.CARDDATA.VSAM.KSDS` (CSD FILE CARDDAT)

### Expected — `program_access`

| program_id | constant_used | mode | edge_type | verb_line | operand_line |
|---|---|---|---|---:|---:|
| program:COCRDLIC | LIT-CARD-FILE = 'CARDDAT ' | STARTBR | STARTS_BROWSE | 964 | 965 |
| program:COCRDLIC | LIT-CARD-FILE = 'CARDDAT ' | READNEXT | READS | 978 | 979 |
| program:COCRDLIC | LIT-CARD-FILE = 'CARDDAT ' | READNEXT | READS | 1026 | 1027 |
| program:COCRDLIC | LIT-CARD-FILE = 'CARDDAT ' | STARTBR | STARTS_BROWSE | 1094 | 1095 |
| program:COCRDLIC | LIT-CARD-FILE = 'CARDDAT ' | READPREV | READS | 1109 | 1110 |
| program:COCRDLIC | LIT-CARD-FILE = 'CARDDAT ' | READPREV | READS | 1135 | 1136 |
| program:COCRDSLC | LIT-CARDFILENAME = 'CARDDAT ' | READ | READS | 628 | 629 |
| program:COCRDUPC | LIT-CARDFILENAME = 'CARDDAT ' | READ | READS | 1208 | 1209 |
| program:COCRDUPC | LIT-CARDFILENAME = 'CARDDAT ' | READ | READS | 1250 | 1251 |
| program:COCRDUPC | LIT-CARDFILENAME = 'CARDDAT ' | REWRITE | UPDATES | 1291 | 1292 |

### Expected — `jcl_access`
| jcl_job_id | source_path |
|---|---|
| jcl-job:CARDFILE | app/jcl/CARDFILE.jcl (load) |
| jcl-job:CBEXPORT | app/jcl/CBEXPORT.jcl |
| jcl-job:READCARD | app/jcl/READCARD.jcl |

---

## Q2.4 — `dataset:AWS.M2.CARDDEMO.TRANSACT.VSAM.KSDS` (CSD FILE TRANSACT)

### Expected — `program_access`

| program_id | constant_used | mode | edge_type | verb_line | operand_line |
|---|---|---|---|---:|---:|
| program:COBIL00C | WS-TRANSACT-FILE = 'TRANSACT' | STARTBR | STARTS_BROWSE | 382 | 383 |
| program:COBIL00C | WS-TRANSACT-FILE = 'TRANSACT' | READPREV | READS | 410 | 411 |
| program:COBIL00C | WS-TRANSACT-FILE = 'TRANSACT' | WRITE | WRITES | 442 | 443 |
| program:COTRN00C | WS-TRANSACT-FILE = 'TRANSACT' | STARTBR | STARTS_BROWSE | 524 | 525 |
| program:COTRN00C | WS-TRANSACT-FILE = 'TRANSACT' | READNEXT | READS | 553 | 554 |
| program:COTRN00C | WS-TRANSACT-FILE = 'TRANSACT' | READPREV | READS | 584 | 585 |
| program:COTRN01C | WS-TRANSACT-FILE = 'TRANSACT' | READ | READS | 221 | 222 |
| program:COTRN02C | WS-TRANSACT-FILE = 'TRANSACT' | STARTBR | STARTS_BROWSE | 577 | 578 |
| program:COTRN02C | WS-TRANSACT-FILE = 'TRANSACT' | READPREV | READS | 605 | 606 |
| program:COTRN02C | WS-TRANSACT-FILE = 'TRANSACT' | WRITE | WRITES | 637 | 638 |

(ENDBR statements at lines 436, 615, 631 are operational; no edges. CORPT00C declares WS-TRANSACT-FILE at line 15 but the actual READ uses are in the report-generation paragraphs — TBD verify specific line numbers if needed for full coverage.)

### Expected — `jcl_access`
| jcl_job_id | source_path |
|---|---|
| jcl-job:CBEXPORT | app/jcl/CBEXPORT.jcl |
| jcl-job:CBIMPORT | app/jcl/CBIMPORT.jcl |
| jcl-job:COMBTRAN | app/jcl/COMBTRAN.jcl |
| jcl-job:CREASTMT | app/jcl/CREASTMT.JCL |
| jcl-job:POSTTRAN | app/jcl/POSTTRAN.jcl |
| jcl-job:TRANBKP | app/jcl/TRANBKP.jcl |
| jcl-job:TRANFILE | app/jcl/TRANFILE.jcl (load) |
| jcl-job:TRANREPT | app/jcl/TRANREPT.jcl |

(8 jobs reference TRANSACT or its GDG generations.)

---

## Q2.5 — `dataset:AWS.M2.CARDDEMO.CARDXREF.VSAM.KSDS` (CSD FILE CCXREF)

### Expected — `program_access`

| program_id | constant_used | mode | edge_type | verb_line | operand_line |
|---|---|---|---|---:|---:|
| program:COTRN02C | WS-CCXREF-FILE = 'CCXREF  ' | READ | READS | 547 | 548 |

(Other card-related programs access the AIX path `dataset:AWS.M2.CARDDEMO.CARDXREF.VSAM.AIX.PATH` via CXACAIX/LIT-CARDXREFNAME-ACCT-PATH, which is a separate `Dataset` entity — not included here. Q2 for the AIX path can be added if Reviewer-B wants.)

### Expected — `jcl_access`
| jcl_job_id | source_path |
|---|---|
| jcl-job:CBEXPORT | app/jcl/CBEXPORT.jcl |
| jcl-job:CBIMPORT | app/jcl/CBIMPORT.jcl |
| jcl-job:CREASTMT | app/jcl/CREASTMT.JCL |
| jcl-job:INTCALC | app/jcl/INTCALC.jcl |
| jcl-job:POSTTRAN | app/jcl/POSTTRAN.jcl |
| jcl-job:READXREF | app/jcl/READXREF.jcl |
| jcl-job:TRANREPT | app/jcl/TRANREPT.jcl |
| jcl-job:XREFFILE | app/jcl/XREFFILE.jcl (load) |

---

# Q3 — Transaction-to-program closure (revised — skeleton only)

**Principle:** `reachable_programs` lists only programs reached via a *deductive* edge (literal CALL, literal LINK, literal XCTL). Identifier-form XCTL/CALL targets stay in `unresolved_reaches` with breadcrumb. MOVE-chain resolution is enrichment, never promoted to typed edge.

## Q3.1 — `transaction:CC00` (sign-on)

### Input
```json
{ "transaction_id": "transaction:CC00" }
```

### Expected
```
entry_program: program:COSGN00C
reachable_programs:
  - program:COADM01C       # via literal XCTL PROGRAM('COADM01C') at COSGN00C:186
  - program:COMEN01C       # via literal XCTL PROGRAM('COMEN01C') at COSGN00C:191
unresolved_reaches: []
cycles: none
```

**Source-verified:** COSGN00C lines 185-187 and 189-192:
```
                    IF CDEMO-USRTYP-ADMIN
                         EXEC CICS XCTL
                           PROGRAM ('COADM01C')
                           COMMAREA(CARDDEMO-COMMAREA)
                    ELSE
                         EXEC CICS XCTL
                           PROGRAM ('COMEN01C')
                           COMMAREA(CARDDEMO-COMMAREA)
```

Both PROGRAM operands are LITERALS (single-quoted) — deductive per RUL-COBOL-014. **Unlike COACTUPC/COTRN01C which use identifier-form `PROGRAM(CDEMO-TO-PROGRAM)`**, COSGN00C uses literal program names. Q3.1 closure is well-defined in the skeleton.

(The transitive depth from CC00: COSGN00C → {COADM01C, COMEN01C}. To go further, would need to follow XCTLs out of COADM01C/COMEN01C, but both are partial in Gate 2 subset. Full-tree Gate 3 will determine if they further XCTL to literal or identifier targets. For now the closure is depth-1.)

## Q3.2 — `transaction:CAUP` (account update)

### Input
```json
{ "transaction_id": "transaction:CAUP" }
```

### Expected
```
entry_program: program:COACTUPC
reachable_programs:
  - program:CSUTLDTC
  - program:CEEDAYS
unresolved_reaches:
  - { from: program:COACTUPC, surface_form: CDEMO-TO-PROGRAM, line: 844,
      kind: identifier_form_xctl, breadcrumb: "EXEC CICS XCTL PROGRAM(CDEMO-TO-PROGRAM)" }
cycles: none
```

**Source-verified (corrected 2026-06-01 — the earlier grep scanned only the program body and missed COPY-expanded calls):** COACTUPC has **no literal CALL in its own body** (`grep -nE "CALL +['\"]" cbl/COACTUPC.cbl` → none), and its only in-body navigation is the identifier-form XCTL at line 844 (`PROGRAM(CDEMO-TO-PROGRAM)`, stays unresolved). **But COACTUPC `COPY CSUTLDPY` (line 3743), and CSUTLDPY contains `CALL 'CSUTLDTC'` (CSUTLDPY.cpy:255)** — so at compile time COACTUPC calls CSUTLDTC. CSUTLDTC.cbl in turn `CALL "CEEDAYS"` (CSUTLDTC.cbl:93). Both are real, literal (resolved) calls reachable from COACTUPC through the copybook; the prior `reachable_programs: []` under-counted because copybook expansion was not considered. Independently source-traced, not MAPA-derived (MAPA's CallTree surfaced the gap by expanding copybooks the regex extractor never scanned).

## Q3.3 — `transaction:CT01` (transaction add)

### Input
```json
{ "transaction_id": "transaction:CT01" }
```

### Expected
```
entry_program: program:COTRN01C
reachable_programs: []
unresolved_reaches:
  - { from: program:COTRN01C, surface_form: CDEMO-TO-PROGRAM, line: 170,
      kind: identifier_form_xctl, breadcrumb: "EXEC CICS XCTL PROGRAM(CDEMO-TO-PROGRAM)" }
cycles: none
```

**Source-verified:** COTRN01C line 168 `EXEC CICS` (verb spans 168-170), line 170 `XCTL PROGRAM(CDEMO-TO-PROGRAM)`. No literal CALL, no LINK. CSUTLDTC NOT called. Corrected.

### Reference data (independent of Q3 entries) — actual CSUTLDTC callers in CardDemo

Source-verified via `grep -nE "CALL +(['\"])CSUTLDTC" cbl/*.cbl cbl/*.CBL`:
- program:CORPT00C → CALL 'CSUTLDTC' at lines 358 and 378
- program:COTRN02C → CALL 'CSUTLDTC' at lines 354 and 374

These are the ONLY four literal-CALL sites of CSUTLDTC across the corpus. Any other "transaction program calls the date utility" claim is naming-convention inference and out of skeleton.

---

# Q4 — BMS map surface for transaction

## Q4.1 — `transaction:CC00` (sign-on)

### Input
```json
{ "transaction_id": "transaction:CC00" }
```

### Expected
```
entry_program: program:COSGN00C
map_interactions:
  - { program: COSGN00C, map: bms-map:COSGN00/COSGN0A, direction: SEND (114) + RECEIVE (76) }
mapsets: [ bms-mapset:COSGN00 ]
field_surface: 27 INITIAL= clauses in app/bms/COSGN00.bms (25 single-line + 2 multi-line)
```

**27 INITIAL= clauses (verbatim, source-ordered from `app/bms/COSGN00.bms`):**

```
 1. L 15: 'Tran :'
 2. L 28: 'Date :'
 3. L 33: 'mm/dd/yy'
 4. L 38: 'Prog :'
 5. L 51: 'Time :'
 6. L 56: 'Ahh:mm:ss'
 7. L 61: 'AppID:'
 8. L 70: 'SysID:'
 9. L 75: '        '   (8-space padding)
10. L 80-81: 'This is a Credit Card Demo Application for Mainframe Modernization'   (multi-line; col-72 '-' continuation)
11. L 86: '+========================================+'
12. L 91: '|%%%%%%%  NATIONAL RESERVE NOTE  %%%%%%%%|'
13. L 96: '|%(1)  THE UNITED STATES OF KICSLAND (1)%|'
14. L101: '|%$$              ___       ********  $$%|'
15. L106: '|%$    {x}       (o o)                 $%|'
16. L111: '|%$     ******  (  V  )      O N E     $%|'
17. L116: '|%(1)          ---m-m---             (1)%|'
18. L121: '|%%~~~~~~~~~~~ ONE DOLLAR ~~~~~~~~~~~~~%%|'
19. L126: '+========================================+'
20. L131-132: 'Type your User ID and Password, then press ENTER:'   (multi-line)
21. L137: 'User ID     :'
22. L151: '(8 Char)'
23. L156: 'Password    :'
24. L162: '________'
25. L171: '(8 Char)'
26. L175: ' '   (1-space padding)
27. L187: 'ENTER=Sign-on  F3=Exit'
```

## Q4.2 — `transaction:CAUP` (account update) — full enumeration

### Input
```json
{ "transaction_id": "transaction:CAUP" }
```

### Expected (skeleton — amended 2026-05-28, Finding B)
```
entry_program: program:COACTUPC
map_interactions:
  - { program: COACTUPC, map: bms-map:LIT-THISMAPSET/LIT-THISMAP, direction: identifier-form (unresolved; MOVE-chain) }
  - { program: COACTUPC, map: bms-map:CCARD-NEXT-MAPSET/CCARD-NEXT-MAP, direction: identifier-form (unresolved; MOVE-chain) }
mapsets: []
field_surface: 0
cycles: none
```

**Why this skeleton answer (amended 2026-05-28, Finding B):** COACTUPC issues SEND/RECEIVE MAP via identifier-form operands (`MAP(LIT-THISMAP) MAPSET(LIT-THISMAPSET)`, plus a `CCARD-NEXT-MAP` MOVE target) — consistent with Q1.1's note. MOVE-chain resolution is enrichment and is never promoted to a typed skeleton edge, so the skeleton surfaces the unresolved placeholder maps and cannot reach the real mapset or its fields (mapsets = [], field_surface = 0). The prior frozen entry asserted the enrichment-resolved answer (COACTUP/COACTUPA + 52 fields) that the v1 skeleton intentionally does not produce. The sponsor signed off the amendment 2026-05-28; see `gold_set_changelog.md`.

**Enrichment target (NOT a skeleton assertion — for the future Pass-2 eval).** MOVE-chain resolution would resolve COACTUPC's map to `bms-map:COACTUP/COACTUPA` in mapset `bms-mapset:COACTUP`, exposing 52 INITIAL= clauses (verbatim, source-ordered from `grep -nE INITIAL= bms/COACTUP.bms`):

```
 1.  'Tran:'
 2.  'Date:'
 3.  'mm/dd/yy'
 4.  'Prog:'
 5.  'Time:'
 6.  'hh:mm:ss'
 7.  'Update Account'
 8.  'Account Number :'
 9.  'Active Y/N: '
10.  'Opened :'
11.  '-'
12.  '-'
13.  'Credit Limit        :'
14.  'Expiry :'
15.  '-'
16.  '-'
17.  'Cash credit Limit   :'
18.  'Reissue:'
19.  '-'
20.  '-'
21.  'Current Balance     :'
22.  'Current Cycle Credit:'
23.  'Account Group:'
24.  'Current Cycle Debit :'
25.  'Customer Details'
26.  'Customer id  :'
27.  'SSN:'
28.  '999'
29.  '-'
30.  '99'
31.  '-'
32.  '9999'
33.  'Date of birth:'
34.  '-'
35.  '-'
36.  'FICO Score:'
37.  'First Name'
38.  'Middle Name: '
39.  'Last Name : '
40.  'Address:'
41.  'State '
42.  'Zip'
43.  'City '
44.  'Country'
45.  'Phone 1:'
46.  'Government Issued Id Ref    : '
47.  'Phone 2:'
48.  'EFT Account Id: '
49.  'Primary Card Holder Y/N:'
50.  'ENTER=Process F3=Exit'
51.  'F5=Save'
52.  'F12=Cancel'
```

(Many entries are positional separators — single dash for date/SSN/expiry field separators, digit placeholders like '999' for SSN format hints. The spec's "user-visible field label" semantic-coverage assertion considers any INITIAL= value as visible; gold-set may want to filter these. Reviewer-B decides.)

## Q4.3 — `transaction:CM00` (menu)

### Input
```json
{ "transaction_id": "transaction:CM00" }
```

### Expected
```
entry_program: program:COMEN01C
map_interactions:
  - { program: COMEN01C, map: bms-map:COMEN01/COMEN1A, direction: SEND (175) + RECEIVE (184) }
mapsets: [ bms-mapset:COMEN01 ]
field_surface: 21 INITIAL= clauses in app/bms/COMEN01.bms
```

**21 INITIAL= clauses (verbatim, source-ordered from `app/bms/COMEN01.bms`):**

```
 1. L 15: 'Tran:'
 2. L 28: 'Date:'
 3. L 33: 'mm/dd/yy'
 4. L 38: 'Prog:'
 5. L 51: 'Time:'
 6. L 56: 'hh:mm:ss'
 7. L 61: 'Main Menu'
 8. L 66: ' '   (single-space — menu-row separator)
 9. L 71: ' '
10. L 76: ' '
11. L 81: ' '
12. L 86: ' '
13. L 91: ' '
14. L 96: ' '
15. L101: ' '
16. L106: ' '
17. L111: ' '
18. L116: ' '
19. L121: ' '
20. L126: 'Please select an option :'
21. L144: 'ENTER=Continue  F3=Exit'
```

(Source-verified COMEN01C: line 175 `EXEC CICS SEND MAP('COMEN1A') MAPSET('COMEN01')`; line 184 same with RECEIVE.)

---

# Q5 — Cluster snapshot (illustration only, not gold-asserted)

(Unchanged from prior submission.)

---

# Q6 — Field-level record layout (v2.2 KU-9)

**Gold class: COLD-AGENT gold (source-only independent read) — NOT human-expert gold.** Added post-freeze 2026-05-29; see `gold_set_changelog.md`. A cold agent read the raw copybook from first principles (source only, never the extractor's output) and asserted the layout below. It converged with the KU-9 DataItem extraction on all 14 items. **Convergence is agreement, not proof** (two LLMs on clean COBOL); a human COBOL expert would supersede. CVACT01Y is a SIMPLE copybook (no edited/COMP-3/OCCURS/REDEFINES) — this validates the common case only.

## Q6.1 — `copybook:CVACT01Y` (ACCOUNT-RECORD, stated RECLN 300)

### Input
```json
{ "copybook_id": "copybook:CVACT01Y" }
```

### Expected — field layout (14 items: 1 group + 13 elementary incl FILLER; all DISPLAY)

| name | level | picture | suggested_sql_type |
|---|---:|---|---|
| ACCOUNT-RECORD | 1 | (group) | (none — group) |
| ACCT-ID | 5 | 9(11) | NUMERIC(11) |
| ACCT-ACTIVE-STATUS | 5 | X(01) | CHAR(1) |
| ACCT-CURR-BAL | 5 | S9(10)V99 | NUMERIC(12,2) |
| ACCT-CREDIT-LIMIT | 5 | S9(10)V99 | NUMERIC(12,2) |
| ACCT-CASH-CREDIT-LIMIT | 5 | S9(10)V99 | NUMERIC(12,2) |
| ACCT-OPEN-DATE | 5 | X(10) | CHAR(10) |
| ACCT-EXPIRAION-DATE | 5 | X(10) | CHAR(10) |
| ACCT-REISSUE-DATE | 5 | X(10) | CHAR(10) |
| ACCT-CURR-CYC-CREDIT | 5 | S9(10)V99 | NUMERIC(12,2) |
| ACCT-CURR-CYC-DEBIT | 5 | S9(10)V99 | NUMERIC(12,2) |
| ACCT-ADDR-ZIP | 5 | X(10) | CHAR(10) |
| ACCT-GROUP-ID | 5 | X(10) | CHAR(10) |
| FILLER | 5 | X(178) | CHAR(178) |

(`ACCT-EXPIRAION-DATE` misspelling is verbatim from source — not corrected. Byte-sum 11+1+12+12+12+10+10+10+12+12+10+10+178 = 300 = RECLN; signed money fields are 12 bytes via overpunch sign. FILLER is unnamed padding to RECLN, normally not materialized as a column downstream.)

## Q6.2 — `copybook:CVEXPORT` (EXPORT-RECORD, stated RECLN 500) — HARD copybook

**Same cold-agent gold class as Q6.1.** This entry exercises the edge cases CVACT01Y lacked: 4 COMP-3, 7 COMP (incl. the binary-with-implied-decimal trap), 6 REDEFINES, 2 OCCURS. Root verified the cold agent's source-only read CONVERGED with the KU-9 extraction on all of them. Added post-freeze 2026-05-29; see `gold_set_changelog.md`.

**Type-cell notation (honored by `gold_match`):** a cell may offer an **acceptable set** — `BIGINT (or NUMERIC(11) / CHAR(11))` means any of those is acceptable; the extraction matches if its type is in the set. `(skip)` = the cold agent recommends not materializing this (FILLER padding) as a column — **excluded from the type comparison** (the skeleton still records the CHAR(n) fact). `(group)` = group item, no type.

### Input
```json
{ "copybook_id": "copybook:CVEXPORT" }
```

### Expected — field layout (72 items: 9 group + 63 elementary; 5 FILLER; all-DISPLAY except 7 COMP + 4 COMP-3)

| name | level | picture | suggested_sql_type |
|---|---:|---|---|
| EXPORT-RECORD | 1 | (group) | (group) |
| EXPORT-REC-TYPE | 5 | X(1) | CHAR(1) |
| EXPORT-TIMESTAMP | 5 | X(26) | CHAR(26) |
| EXPORT-TIMESTAMP-R | 5 | (group) | (group) |
| EXPORT-DATE | 10 | X(10) | CHAR(10) |
| EXPORT-DATE-TIME-SEP | 10 | X(1) | CHAR(1) |
| EXPORT-TIME | 10 | X(15) | CHAR(15) |
| EXPORT-SEQUENCE-NUM | 5 | 9(9) | INTEGER |
| EXPORT-BRANCH-ID | 5 | X(4) | CHAR(4) |
| EXPORT-REGION-CODE | 5 | X(5) | CHAR(5) |
| EXPORT-RECORD-DATA | 5 | X(460) | CHAR(460) |
| EXPORT-CUSTOMER-DATA | 5 | (group) | (group) |
| EXP-CUST-ID | 10 | 9(09) | INTEGER |
| EXP-CUST-FIRST-NAME | 10 | X(25) | CHAR(25) |
| EXP-CUST-MIDDLE-NAME | 10 | X(25) | CHAR(25) |
| EXP-CUST-LAST-NAME | 10 | X(25) | CHAR(25) |
| EXP-CUST-ADDR-LINES | 10 | (group) | (group) |
| EXP-CUST-ADDR-LINE | 15 | X(50) | CHAR(50) |
| EXP-CUST-ADDR-STATE-CD | 10 | X(02) | CHAR(2) |
| EXP-CUST-ADDR-COUNTRY-CD | 10 | X(03) | CHAR(3) |
| EXP-CUST-ADDR-ZIP | 10 | X(10) | CHAR(10) |
| EXP-CUST-PHONE-NUMS | 10 | (group) | (group) |
| EXP-CUST-PHONE-NUM | 15 | X(15) | CHAR(15) |
| EXP-CUST-SSN | 10 | 9(09) | NUMERIC(9) (or CHAR(9) preferable — leading zeros) |
| EXP-CUST-GOVT-ISSUED-ID | 10 | X(20) | CHAR(20) |
| EXP-CUST-DOB-YYYY-MM-DD | 10 | X(10) | CHAR(10) |
| EXP-CUST-EFT-ACCOUNT-ID | 10 | X(10) | CHAR(10) |
| EXP-CUST-PRI-CARD-HOLDER-IND | 10 | X(01) | CHAR(1) |
| EXP-CUST-FICO-CREDIT-SCORE | 10 | 9(03) | NUMERIC(3) |
| FILLER | 10 | X(134) | (skip) |
| EXPORT-ACCOUNT-DATA | 5 | (group) | (group) |
| EXP-ACCT-ID | 10 | 9(11) | BIGINT (or NUMERIC(11) / CHAR(11)) |
| EXP-ACCT-ACTIVE-STATUS | 10 | X(01) | CHAR(1) |
| EXP-ACCT-CURR-BAL | 10 | S9(10)V99 | NUMERIC(12,2) |
| EXP-ACCT-CREDIT-LIMIT | 10 | S9(10)V99 | NUMERIC(12,2) |
| EXP-ACCT-CASH-CREDIT-LIMIT | 10 | S9(10)V99 | NUMERIC(12,2) |
| EXP-ACCT-OPEN-DATE | 10 | X(10) | CHAR(10) |
| EXP-ACCT-EXPIRAION-DATE | 10 | X(10) | CHAR(10) |
| EXP-ACCT-REISSUE-DATE | 10 | X(10) | CHAR(10) |
| EXP-ACCT-CURR-CYC-CREDIT | 10 | S9(10)V99 | NUMERIC(12,2) |
| EXP-ACCT-CURR-CYC-DEBIT | 10 | S9(10)V99 | NUMERIC(12,2) |
| EXP-ACCT-ADDR-ZIP | 10 | X(10) | CHAR(10) |
| EXP-ACCT-GROUP-ID | 10 | X(10) | CHAR(10) |
| FILLER | 10 | X(352) | (skip) |
| EXPORT-TRANSACTION-DATA | 5 | (group) | (group) |
| EXP-TRAN-ID | 10 | X(16) | CHAR(16) |
| EXP-TRAN-TYPE-CD | 10 | X(02) | CHAR(2) |
| EXP-TRAN-CAT-CD | 10 | 9(04) | NUMERIC(4) |
| EXP-TRAN-SOURCE | 10 | X(10) | CHAR(10) |
| EXP-TRAN-DESC | 10 | X(100) | CHAR(100) |
| EXP-TRAN-AMT | 10 | S9(09)V99 | NUMERIC(11,2) |
| EXP-TRAN-MERCHANT-ID | 10 | 9(09) | INTEGER |
| EXP-TRAN-MERCHANT-NAME | 10 | X(50) | CHAR(50) |
| EXP-TRAN-MERCHANT-CITY | 10 | X(50) | CHAR(50) |
| EXP-TRAN-MERCHANT-ZIP | 10 | X(10) | CHAR(10) |
| EXP-TRAN-CARD-NUM | 10 | X(16) | CHAR(16) |
| EXP-TRAN-ORIG-TS | 10 | X(26) | CHAR(26) |
| EXP-TRAN-PROC-TS | 10 | X(26) | CHAR(26) |
| FILLER | 10 | X(140) | (skip) |
| EXPORT-CARD-XREF-DATA | 5 | (group) | (group) |
| EXP-XREF-CARD-NUM | 10 | X(16) | CHAR(16) |
| EXP-XREF-CUST-ID | 10 | 9(09) | NUMERIC(9) |
| EXP-XREF-ACCT-ID | 10 | 9(11) | BIGINT |
| FILLER | 10 | X(427) | (skip) |
| EXPORT-CARD-DATA | 5 | (group) | (group) |
| EXP-CARD-NUM | 10 | X(16) | CHAR(16) |
| EXP-CARD-ACCT-ID | 10 | 9(11) | BIGINT |
| EXP-CARD-CVV-CD | 10 | 9(03) | INTEGER (SMALLINT) |
| EXP-CARD-EMBOSSED-NAME | 10 | X(50) | CHAR(50) |
| EXP-CARD-EXPIRAION-DATE | 10 | X(10) | CHAR(10) |
| EXP-CARD-ACTIVE-STATUS | 10 | X(01) | CHAR(1) |
| FILLER | 10 | X(373) | (skip) |

**Hard-case facts (cold-agent-asserted, root-verified convergent with the extraction — recorded here; the mechanical check above covers layout+type):**
- **USAGE:** 4 COMP-3 (`EXP-CUST-FICO-CREDIT-SCORE`, `EXP-ACCT-CURR-BAL`, `EXP-ACCT-CASH-CREDIT-LIMIT`, `EXP-TRAN-AMT`) → logical NUMERIC; 7 COMP (binary: SEQUENCE-NUM, CUST-ID, MERCHANT-ID, CVV → INTEGER; XREF-ACCT-ID, CARD-ACCT-ID → BIGINT; **EXP-ACCT-CURR-CYC-DEBIT S9(10)V99 COMP → NUMERIC(12,2), the binary-with-implied-decimal TRAP — NOT an integer**). All others DISPLAY.
- **REDEFINES (6):** EXPORT-TIMESTAMP-R redefines EXPORT-TIMESTAMP; the 5 overlays (CUSTOMER/ACCOUNT/TRANSACTION/CARD-XREF/CARD-DATA) each redefine EXPORT-RECORD-DATA.
- **OCCURS (2):** EXP-CUST-ADDR-LINES OCCURS 3; EXP-CUST-PHONE-NUMS OCCURS 2.
- **Byte-proof:** each of the 5 overlays = 460 bytes; record = 500 = RECLN. (`EXP-ACCT-EXPIRAION-DATE` / `EXP-CARD-EXPIRAION-DATE` misspellings verbatim from source.)

**Known latent policy boundary (per root):** `suggested_sql_type` is a *mechanical, USAGE-driven* rule (COMP binary → INTEGER/BIGINT by digit count; COMP-3/DISPLAY numeric → NUMERIC). A *domain-aware* read might type some numeric IDs as NUMERIC/CHAR to preserve leading zeros (the cold agent flagged this for SSN, and offered the EXP-ACCT-ID set). The two converged here, so it did not bite. If a future copybook surfaces a COMP field the cold agent domain-types as NUMERIC, it would show as a DIFF — that is a **policy call (leaning: keep the mechanical skeleton rule; domain ID-typing is downstream enrichment), NOT an extractor bug.**

---

# Outstanding work — pre-freeze status

- [x] Q3.1 CC00 verified (literal XCTL form, both targets named)
- [x] Q4.1 / Q4.3 INITIAL= enumerated (27 / 21 entries respectively)
- [x] source-grep cross-check passed
- **Known Gate-3 incremental (not a blocker for freeze):** Q2.1-Q2.5 `jcl_access` fine-grain refinement. Current candidates list batch jobs at job-level (which jobs reference each dataset by DSN); the per-step DD-name + DISP + inferred_access_mode breakdown is genuinely Gate-3-time work, since the full-corpus run reveals the pattern across all jobs and steps. Per the sponsor and the source-grep review: this is a known increment to fold in during Gate 3 review, not a blocker for the initial freeze.

**Gold-set freeze policy reminder:** This file becomes `gold/gold_set.md` only after the sponsor's review confirms every entry. Freeze record goes in `gold/gold_set_changelog.md` per spec.
