# Phase 0 — COBOL parser bake-off against CardDemo

**Status:** Phase-0 deliverable (uncommitted draft for review). Answers the gating question empirically before committing the foundation to a parser.

**Environment:** JDK 22, Maven 3.9.16 (installed for this), network OK. Reps: `COACTUPC.cbl` (CICS-heavy online + two-line `VALUE`), `CBTRN02C.cbl` (batch + literal CALL), `CBEXPORT.cbl` (batch, COPYs `CVEXPORT` → COMP-3 / REDEFINES / OCCURS / edited PIC).

## Candidates and findings

### Python-native — DISQUALIFIED (regex under the hood)
- **python-cobol** (0.1.4): a single module of `re` patterns for data-description rows. Pure regex.
- **legacylens-cobol-parser** (`cobol_parser`, 0.1.20): 16 `re.compile` + 16 `re.search` + 7 `re.split`, no grammar/parser-generator dependency. Regex extractors.

Both are exactly the "trade one regex for another" the plan rules out. Disqualified.

### ProLeap (uwol/proleap-cobol-parser, ANTLR4, MIT) — COBOL-deep; CICS opaque
Built from source (`mvn -DskipTests install`, targets JDK 17, compiles clean on 22). Ran the ASG runner over all three reps and walked the ANTLR tree.

**All three parse.** Construct exposure as native grammar nodes:

| Construct | COACTUPC (online) | CBTRN02C (batch) | CBEXPORT (batch) |
|---|---|---|---|
| DataDescriptionEntry | 1455 | 148 | 175 |
| PictureString | 1062 | 118 | 144 |
| DataRedefinesClause | 112 | 2 | 6 |
| DataOccursClause | 1 | 0 | 2 |
| FileControlEntry / SELECT/ASSIGN/ORG/ACCESS | 0 | 6 each | 6 each |
| READ / WRITE / REWRITE (COBOL) | 0 | 4/3/2 | 5/5/0 |
| CallStatement (static literal / dynamic ident) | 1 / 0 | 1 / 0 | 1 / 0 |
| ExecCicsStatement | 14 | 0 | 0 |

What this establishes:
- **COBOL proper is fully exposed and zero-hand-tuning:** PIC / USAGE / OCCURS / REDEFINES, the FILE-CONTROL block, the COBOL I-O verbs, and — load-bearing — the **static-vs-dynamic CALL distinction** (literal vs identifier operand), all as typed nodes. ProLeap also builds an ASG with data/control flow on top. This is genuine grammar depth; the regex-breakers (two-line `VALUE`, edited PICs, COMP implied-decimal) are non-issues for a real grammar.
- **`EXEC CICS` is a single opaque text token.** The 14 CICS statements in COACTUPC come back as `ExecCicsStatement` nodes whose entire body is one `TERMINAL` blob (`'*>EXECCICS EXEC CICS HANDLE ABEND …'`) — ProLeap does **not** parse inside `EXEC CICS`. So LINK / XCTL / SEND / RECEIVE / CICS-FILE access, and the **identifier-form XCTL that is CardDemo's dynamic-navigation must-not-promote case**, are *not* exposed as nodes. An online program's file access shows zero `FileControlEntry`/`READ` for the same reason — it's all inside the opaque CICS blocks.
- **Copy resolution is brittle and hard-fails.** ProLeap throws (does not degrade) on any unresolved copybook. CardDemo uses `COPY 'literal'` (ProLeap's literal finder does not append extensions) alongside `COPY word`, and pulls IBM-supplied copybooks (`DFHAID`, `DFHBMSCA`) not in the corpus. Getting all three to parse required a harness: extension-less copies of every copybook + empty stubs for the IBM externals. That's parser-config friction, not a mapping concern — but it is real integration cost.

### Koopa (krisds/koopa, island grammar, Java) — assessed by design; empirical run deferred
Ant-based build (no prebuilt jar; `ant` not installed here). Its distinctive value is the *opposite* of ProLeap's brittleness: an island grammar parses files in isolation and **degrades gracefully** on regions it doesn't recognize (→ honest gap, not a thrown exception), and dumps XML parse trees. That directly solves ProLeap's hard-fail-on-missing-copybook problem. But by the same island design it will treat `EXEC CICS` as an unrecognized region too — graceful skip, not CICS-innards parsing. So Koopa buys **robustness**, not CICS depth. Empirical run is a reasonable follow-up (install `ant`, build, run on the same three) but would not change the CICS conclusion below.

### MAPA (cschneid-the-elder/mapa, ANTLR4, MIT) — the family; assessed empirically, head-to-head
ANTLR4 grammars for COBOL (IBM-Z, toward ISO 202x), CICS, DB2z SQL/PL, EXEC DLI, EXEC SQLIMS, and JCL. Built from source (`make`, bundles ANTLR 4.13.2). Ran its `CallTree` tool on the same three reps. The author has himself run MAPA against AWS CardDemo (`cobol/readme.md`), including the `EXEC CICS XCTL PROGRAM(identifier)` dynamic-nav case.

Empirical results (all three parse, exit 0, no errors, no harness):
- **COBOL data layer is full**, not shallow — `dataDescriptionEntryFormat1` carries PIC/USAGE/OCCURS/REDEFINES (and more clauses than ProLeap: dataType, dynamicLength, volatile, …). The flagged "breadth tool goes shallow on data" risk did not materialize at the grammar level. (CallTree's CSV is control-flow/file-oriented; the data layer is reached by walking MAPA's parse tree, which the grammar fully supports.)
- **FILE-CONTROL + I/O**: emitted as `DD` rows with read/write/update flags (e.g. `DALYTRAN-FILE,1,0,0,0`; `ACCOUNT-FILE,0,0,1,0`).
- **COBOL CALL static-vs-dynamic**: native — `CALLBYLITERAL` (e.g. CEE3ABD).
- **CICS parsed INSIDE the block** (the layer ProLeap returns as text): COACTUPC yields `CICSREAD ACCTDAT/CUSTDAT/CXACAIX`, `CICSREWRITE ACCTDAT/CUSTDAT`, and — load-bearing — `UNRESOLVEDCALL … CICSXCTLBYIDENTIFIER, CDEMO-TO-PROGRAM`: MAPA natively classifies the identifier-form CICS XCTL as an unresolved/dynamic call. That is exactly our `unresolved:CDEMO-TO-PROGRAM` must-not-promote case, native.
- **Copybooks: graceful** — `CopyStatement` logs "not found" and continues (DFHAID/DFHBMSCA tolerated with no stub harness). Opposite of ProLeap's hard-throw.
- **JCL**: full grammar + `JCLParser` tool (roadmap, note only).
- License **MIT**.

## Head-to-head: ProLeap vs MAPA (the real contest)

| Axis | ProLeap | MAPA |
|---|---|---|
| Parses CardDemo COBOL | yes (needs copybook harness) | yes (graceful, no harness) |
| COBOL data layer (PIC/USAGE/OCCURS/REDEFINES) | full (ASG) | full (grammar) |
| FILE-CONTROL + COBOL I/O | full | full (DD read/write/update) |
| static-vs-dynamic COBOL CALL | yes | yes |
| **EXEC CICS innards** (LINK/XCTL/SEND/RECEIVE/file) | **opaque text — not parsed** | **native structured extraction** |
| **identifier-form XCTL** (must-not-promote) | invisible (inside opaque block) | **native (`CICSXCTLBYIDENTIFIER`→`UNRESOLVEDCALL`)** |
| Missing-copybook behavior | hard-throws | graceful, logged |
| JCL (roadmap) | none | full grammar + tool |
| License | MIT | MIT |
| Toolchain span | COBOL only (bring-your-own CICS) | COBOL + CICS + DB2 + DLI + JCL, one toolchain |

## The finding that matters: CICS is a second language pattern — and MAPA already covers it

CardDemo's online programs encode their control flow (XCTL/LINK), screen I/O (SEND/RECEIVE MAP), and much of their file access inside `EXEC CICS` blocks. A COBOL grammar alone cannot reach them — both ProLeap and Koopa hand the block back as text, so a large share of the existing edge model (LINKS_TO, XCTLS_TO, SENDS_MAP, RECEIVES_MAP, CICS-file READS/WRITES, and the identifier-form-XCTL must-not-promote case) is unreachable from COBOL alone. CICS is genuinely a second language pattern.

MAPA resolves this: it carries the CICS grammar in the same toolchain and extracts those constructs natively (verified: `CICSXCTLBYIDENTIFIER`, `CICSREAD`, `CICSREWRITE`). The architecture is identical for both candidates — the COBOL parse delimits each `EXEC CICS` block; a CICS grammar parses the delimited text — but MAPA *ships* that CICS grammar (and JCL, DB2, DLI), while ProLeap would require sourcing and integrating a separate one.

## Recommendation: MAPA is the foundation parser

Applying the project's rule (best per-language; a family only if it *also* optimizes per-language): MAPA **ties ProLeap on COBOL depth, wins decisively on CICS** (the layer central to CardDemo's online programs and the dynamic-nav must-not-promote case), handles missing copybooks more gracefully, and brings JCL for the next roadmap step — all one MIT toolchain. The depth-vs-breadth gray that would have gone to the project sponsor did not materialize: MAPA wins or ties on every axis that matters here. ProLeap remains an excellent COBOL-only parser and a viable fallback, but it would force a separate CICS-grammar integration that MAPA already provides.

**Foundation shape (unchanged by the pick):** parse / normalize / map + registry. MAPA's `CallTree` tool gives ready-made control-flow + file-access + CICS extraction (CSV); the DataItem field layout + `suggested_sql_type` inputs come from walking MAPA's COBOL parse tree (grammar confirmed full). CICS remains its own grammar+mapping unit on the foundation — MAPA modularizes it internally. The same `Observation` emitter serves both.

## Honest limitations of this bake-off
- **MAPA's data-layer extraction wasn't exercised end-to-end** — confirmed full at the grammar level (`dataDescriptionEntryFormat1`) and via the CICS/file CallTree output, but Phase 1 must walk MAPA's parse tree to emit the DataItem hierarchy + PIC/USAGE/OCCURS/REDEFINES `Observation`s, which is where the real mapping work (and any surprises) will surface.
- **CallTree CSV ≠ our Observation contract** — it's MAPA's own output shape; Phase 1 maps MAPA's parse tree to our `Observation` schema, not its CSV.
- **Koopa** assessed by design, not run (ant build deferred); irrelevant now that MAPA wins on both COBOL and CICS.
- **ProLeap** parsed only with a copybook-closure harness (extension-less copies + IBM stubs); MAPA needed none.
- **Config vs hand-rule (honesty):** the per-corpus config surface is copybook search paths + standard-library stubs (e.g. DFHAID/DFHBMSCA) — compiler-standard, not CardDemo semantics. MAPA's graceful copybook handling shrinks even that. No CardDemo-specific hand-rule was used or needed.
