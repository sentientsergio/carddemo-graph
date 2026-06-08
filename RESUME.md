# RESUME — grammar-parser foundation (v3), branch `feature/grammar-parser-foundation`

Durable resume point for a fresh chair. **Steps 1 & 2 (vendor MAPA + lift into `src/`) are DONE
and committed at tip `581095e`; provenance is SOLVED and committed at `5836cc4`. EMISSION (step 3)
is the next work, then Phase 2 (step 4).** Do NOT redo the foundation/DataItem/provenance — they
are LOCKED. Local only, no push. Plan of record: `~/.claude/plans/polymorphic-leaping-mountain.md`.

## Goal

Replace hand-tuned regex Pass-1 (`src/carddemo_graph/extract/cobol.py`, `CobolExtractor`,
RUL-COBOL-001…021) with a **pluggable grammar-parser foundation** (COBOL first; JCL/assembler
later). Generalizes because it implements the language standard, not the corpus. Downstream
contract (Observation shape, Pass-3 resolver, gold, Q1–Q5) does NOT change.

## Decisions locked

- **Parser = MAPA** (cschneid-the-elder/mapa, MIT, ANTLR4 @ commit `2ad7cd5`). Beat ProLeap in
  the Phase-0 bake-off: full COBOL data layer, file-control + I/O, static/dynamic CALL, and —
  decisively — parses **inside** `EXEC CICS` (ProLeap returns it as opaque text). One toolchain
  spans COBOL+CICS+DB2+DLI+JCL. Note: `artifacts/parser_bakeoff_phase0.md`.
- **Provenance remap = approach (B)**, owned by the **Normalize seam** (our adapter), not the
  parser. MAPA parses a *preprocessed* form (cols>72 stripped, COPY spliced, blanks/continuations
  folded), so ANTLR coords are preprocessed. We recover original coords by aligning the temp
  files MAPA already retains under `-saveTemp`. Upstream MAPA patch stays minimal (one COPY-splice
  origin sidecar); all coordinate logic lives in our adapter.
- **Vendoring = (b)**: vendor MAPA **source + a standalone `.patch` + a documented build step**
  (not a binary jar; not a submodule). Our delta stays a reviewable, upstream-offerable patch;
  MAPA's MIT `LICENSE` + attribution preserved in the vendored tree.

## Proven state (all SHOWN, not asserted)

- **DataItem field layer** at gold parity vs CVACT01Y (Q6.1): 14/14 items + types, reusing
  `_suggested_sql_type()` UNCHANGED. MAPA parse tree → DataItem emission works.
- **Provenance round-trip, BOTH halves:**
  - Expanded field → copybook line, on **CVEXPORT** (non-1:1, 5 blanks; our Q6.2 hard case):
    drift corrected exactly — FILLER folded L95 → source L100 (+5), ACTIVE-STATUS L94→99 (+5),
    REDEFINES L23→24 (+1). 98/98 fold lines aligned, 0 flags.
  - Program statement → program line, on **CBTRN02C**: `CALL 'CEE3ABD'` folded L660 → source
    L711 (+51), end-to-end through the copy-pass sidecar. 678/678 aligned, 0 flags.
  - Mechanism: col-strip is 1:1 with source; only the blank-collapse fold needs alignment;
    content-anchored two-pointer walk that **flags rather than emits** on any mismatch.

## Scope caveat (generalization boundary — load-bearing)

**CORRECTION (Phase-2 finding, 2026-06-01):** the earlier claim that the corpus has *zero*
classic continuation lines was WRONG — it overlooked **CBSTM03A.CBL** (uppercase `.CBL`, and
missed by `*.cbl` globs). CBSTM03A's HTML literals ARE continued across col-7 `-` lines (e.g.
L124-125: `88 HTML-L08 VALUE '<table…styl` then `-  'e="width:70%;…">'.`). So true
continuation-folding IS exercised by exactly one program. `fold_align` **fail-loud-refuses** on
it (FoldAlignmentError — the invariant working as designed, surfacing the gap), and the adapter
**falls back to the regex extractor for that one program** (byte-identical output; guard:
`test_continuation_program_falls_back_to_regex`). All other 30 programs + all copybooks emit via
MAPA. Continuation-folding (consume N source lines → anchor to statement start) remains **Phase-3
work**; until then the regex fallback keeps the pipeline whole. Does NOT block Phase 2. The rest
of the fold exercised elsewhere is blank-collapse + comment-preservation. Full detail:
`artifacts/parser_provenance_proof.md`.

## Next-step sequence (steps 1 & 2 DONE at 581095e — EMISSION is next)

1. **Vendor MAPA (b): DONE (2026-06-01).** `vendor/mapa/` = pristine `upstream/` @2ad7cd5 +
   standalone `mapa_origin_tracker.patch` + reproducible `build.sh` (stage→patch→ANTLR-gen→javac→jar)
   + MIT LICENSE/attribution + `MapaTreeDump.java` (our data-layer tree dumper). Build artifacts
   (CallTree.jar, MapaTreeDump.class, generated ANTLR, build/) gitignored; 15MB vendored.
   Two gaps the old artifact README missed, now fixed in build.sh: the ANTLR generation step, and
   the manifest Class-Path for the relocated jar.
2. **Lift into `src/carddemo_graph/extract/parsers/`: DONE (2026-06-01).** `registry.py`
   (lang→extractor; env flag **`CARDDEMO_COBOL_PARSER=regex|mapa`**, default regex; wired into
   `pilot.py` + `gate3.py`) + `cobol/{parse,normalize,map_dataitem,adapter}.py`. Parse seam shells
   MapaTreeDump (col-strips input to ≤72 first; lenient on syntax errors; scratch cwd). Normalize seam
   = `identity_origin_map` (DataItem 1:1) + `fold_align` (the (B) reusable, fail-loud). Map seam reuses
   `_suggested_sql_type`/`_normalize_usage` UNCHANGED; generic over grammar nodes.
   **DataItem PARITY PROVEN: 517/517 across 31 copybooks, 0 regressions, 3 improvements** (MAPA catches
   `PIC +ZZZ,ZZZ,ZZZ.ZZ` that regex's `_RE_PIC` char class misses → NUMERIC(11,2)). Full gate3 under the
   `mapa` flag (copybooks→MAPA, programs→regex delegation) = 1864 ent / 1445 edges (= regex), gold_match
   **37/0/3** (Q6.1 14/14, Q6.2 67/67). pytest 21/21 (`tests/test_mapa_dataitem.py`, skips if jar unbuilt).
3. **Rest of emission via the same Observation emitter — IN PROGRESS (`map_program.py`).** Building as
   proven increments, each at facts-parity vs regex (`tests/test_mapa_program_emission.py`: per-rule
   `data`+start_line diff, categorizing only_regex=regression vs only_mapa=improvement). **DONE so far,
   full-corpus parity (31/31 programs, 0 unexpected only_regex/only_mapa):**
   - RUL-COBOL-001 PROGRAM-ID, RUL-COBOL-005 file-control (structured `fileControlEntry` clauses).
   - RUL-COBOL-011/012 CALL (tree `callStatement`; literal→static, identifier→dynamic). **Copybook-origin
     CALL improvement proven:** COACTUPC `CALL 'CSUTLDTC'` lives in proc-copybook CSUTLDPY → MAPA emits
     `program:CSUTLDTC` w/ copybook provenance; regex emits 0 (never scans copybook bodies). RUL-012
     corpus-unexercised (0 dynamic calls in all 14 CALL programs — honesty caveat, like continuations).
   - RUL-COBOL-002/003/004 COPY/INCLUDES (+ DEFINES_LAYOUT_FOR). COPY is a preprocessor directive with NO
     expanded-tree grammar node (CSV over-reports transitive; .origin chain is the dead-end), so its scan
     is lexical-on-source (the documented keyword-level boundary) — independent re-derivation of the frozen
     regex section/FD walk, proven byte-parity corpus-wide (RUL-002 ×183, 003 ×39, 004 ×56).
   - **FINDING — latent provenance bug fixed (`program_provenance._src_code`):** `resolve()`'s program-native
     content check compared RAW source (cols 1..80) vs the col-stripped (≤72) top-temp; **COBSWAIT** keeps
     cols-73..80 sequence numbers on its PROGRAM-ID/CALL lines (the corpus didn't strip them; 5 programs
     carry such lines incl 2 proof programs, which passed only because their construct lines were clean),
     so it fail-loud-raised. Fix: compare cols 1..72 like-for-like, as `fold_align` already does. Regression
     guard added (COBSWAIT in both program tests). This is the one touch to the LOCKED provenance component.
   - RUL-COBOL-006..010 batch I/O (tree I/O statement nodes; WRITE/REWRITE record→logical-file via
     source-derived FD/01 map). **IMPROVEMENT:** MAPA drops 2 regex READ-TO false positives in COCRDLIC
     (`SET MORE-RECORDS-TO-READ TO TRUE` → bogus logical-file:.../TO; grammar emits none). 009/010 (batch
     DELETE/START) corpus-unexercised.
   - RUL-COBOL-013/014/018 structured CICS + 015/016/017 CICSOTHER (block LINE from grammar
     execCicsStatement; operands from frozen keyword-paren patterns on the grammar-delimited block — the
     documented boundary; ws-constant propagation for file ops; identifier-XCTL stays unresolved+
     must_not_promote). Exact parity. 013/015 (CICS LINK / RETURN-TRANSID) corpus-unexercised.
   - **ADAPTER FLIPPED (programs regex→map_program) + PHASE-2 DONE — step 4 below.** Commits c2987d2,
     dbad66e, 3b088f2, 49bf915, + flip. Per-mapper full-corpus facts-parity proven before the flip
     (`tests/test_mapa_program_emission.py`).
   CICS / CALL / file-control / INCLUDES,
   replacing the regex delegation for programs in `adapter.py`. Keep identifier-form XCTL as
   `unresolved:*` (must-not-promote; MAPA: `CICSXCTLBYIDENTIFIER`/`UNRESOLVEDCALL`). **Decoded starting
   point (this is the crux — program PROVENANCE composition):**
   - MAPA's `CobolParser` REQUIRES preprocessed input. On a raw program it dumps COPY/EXEC-CICS/procedure
     regions as opaque `freeFormText` (0 call/cics/copy nodes). So programs MUST be walked from the
     **preprocessed tree**, not the raw source.
   - The tree to walk is the **final COPY-expansion pass** (`-saveTemp` temp `…-00005-…-cbl`, fully
     expanded): yields `callStatement` + `fileControlEntry` (+ `execCicsStatement` for CICS programs).
     Earlier numbered passes are intermediate; `withoutcontinuations`/`without73to80` are the program's
     own col-strip/fold (without73to80 line count == stripped source, 1:1).
   - CallTree CSV (`CALL`/`CICSREAD|REWRITE`/`COPY`/`DD`/`PGM`) gives **pre-resolved** operands
     (CICS file operands resolved to filenames — MAPA does the WS-constant propagation the regex path
     needed) and classifications, but **no line numbers** and omits SEND/RECEIVE-MAP/LINK/RETURN — so
     those come from the **tree** (execCicsStatement nodes; CICS innards are parsed). COPY/INCLUDES come
     from the CSV `COPY` rows (COPY is expanded out of the tree).
   - **Provenance = compose the `.origin` PASS/COPY sidecar chain across passes + `fold_align`** to map a
     preprocessed (expanded) line → source line. Proven on CBTRN02C (CALL 'CEE3ABD' → source 711, +51
     drift). The per-pass `<temp>.origin` records are `PASS <inputLine>` / `COPY <copybookPath> <line>`;
     compose pass5→…→pass0→program/copybook. **Feed MAPA the STRIPPED program** (same SourceFile as
     regex) so provenance lands on stripped lines → Q2.verb_line stays comparable to the frozen gold.
   - Don't re-emit the expanded copybook data items as program DataItems (data items come from copybooks
     only; programs emit program-level constructs).
   - **FINDING (2026-06-01, validated empirically — the program-provenance composition is HARDER than the
     proof implied):** the (B) round-trip was proven on CBTRN02C (5 COPYs, 6 passes) and generalizes there
     — CALL + all 6 fileControlEntry compose to exact source lines. But it does NOT generalize as-is to
     many-COPY programs. **COACTUPC has 57 single-COPY passes**, and the naive linear PASS-chain
     (pass K input = pass K-1 output, walk pass56→…→pass0→folded) **silently mismaps**: an `EXEC CICS SEND
     MAP` at top-temp line 4794 composed to source line 3693 (`AND CUST-DOB…`), a different statement.
     Going backward the chain shows impossible line-number INCREASES (pass16:4868 ← pass15:4870), so the
     per-pass `.origin` records don't compose under the simple linear model for many-COPY programs.
     **`fold_align` (Normalize seam) is NOT at fault** — the COACTUPC fold is pure blank-collapse (376
     blanks, 0 comments) and woc→source is exact (woc 3325 = source 3693, content-matched). The bug is
     isolated to the multi-pass `.origin` chain, which is **exploratory only — NOT committed** (refused to
     commit a known-mismapping composer, per the fail-loud / quality-over-speed discipline).
     MAPA's preprocessor model (CobolSource.java ~423-486): iterative, expands ~one COPY per pass, writes a
     numbered temp per iteration, re-reads it, until no COPY remains; OriginTracker.begin() per pass; splice
     records via CopyStatement (pre-fragment recordPass(startLine) / spliced recordCopy / post recordPass(endLine)).
   - **CONVERGED APPROACH (still approach (B); avoids the multi-pass COPY-insertion accounting entirely —
     do NOT keep chasing the 57-pass chain, it was a dead end):** I only need provenance for the CONSTRUCTS
     I emit (CALL/CICS/SELECT/COPY), not every line. Resolve each construct by CONTENT, with content-validation
     as a HARD fail-loud invariant (the project's directive):
     * **Program-native constructs** (the common case): they appear in the folded program `withoutcontinuations`
       (woc) in the SAME ORDER as the tree's nodes of that type. Anchor by (rule-type, ordinal): Nth tree
       `execCicsStatement` ↔ Nth woc line matching the construct predicate → `fold_align` woc→source.
       **VALIDATED EXACT: COACTUPC execCicsStatement 17/17, fileControlEntry 6/6; CBTRN02C callStatement 1/1,
       fileControlEntry 6/6** — every construct → exact stripped-source line.
     * **Copybook-origin constructs** (NEW finding, must handle): a CALL/CICS can live in a PROCEDURE copybook,
       not the program. e.g. COACTUPC `CALL 'CSUTLDTC'` is in copybook CSUTLDPY — it is NOT in woc at all
       (woc has 0 CALL/CSUTLDTC lines). Such a construct's provenance is the COPYBOOK line; resolve by content
       in the spliced copybook. **This is also a MAPA improvement over regex** — the regex extractor only emits
       CALL/CICS when `source_role=="program"`, so it NEVER sees procedure-copybook CALLs/CICS; MAPA (CallTree
       expands copybooks) does. Expect these as three-way-diff *improvements*, with copybook provenance.
     * **Content-validation invariant (hard, structural):** for every emitted construct, assert the mapped
       source/copybook line content contains the construct's own signature (verb + operand from the tree/CSV),
       modulo known transforms — else FAIL LOUD and do not emit. Makes a silently-wrong edge impossible by
       construction; partial progress is safe (verified emit, unverified fail loud, none wrong).
   - **Before committing the composer:** validate exact on CBTRN02C + COACTUPC + one more many-COPY CICS
     program (e.g. COCRDUPC/COACTVWC), covering program-native AND copybook-origin, content-validated.
     Then lift into normalize.py (the construct-anchor + content-check) and wire the program mappers.
   - Exploratory scripts were in /tmp (ephemeral): pass-chain (wrong), content-anchor-walk (desyncs), and the
     working ordinal-content validator. Reproduce the ordinal+content approach as the committed composer.
   - **PROVENANCE SOLVED + COMMITTED (5836cc4):** `program_provenance.py::ProgramConstructResolver` +
     `parse.py::{call_tree, build_copybook_harness, parse_temp_tree}`. Construct-anchor + content-validation,
     fail-loud, proven exact on 3 programs. Use it for every emitted construct's line.
   - **EMISSION-SURFACE FINDINGS (2026-06-01 — these reshape the mapper plan; settle before coding mappers):**
     * **CICS operands are NOT in the MapaTreeDump (CobolParser) tree** — EXEC CICS innards are tokenized
       CHARACTER-BY-CHARACTER (`EXEC CICS X C T L P R O G R A M ( …`). So CICS operands must come from the
       CallTree CSV, NOT the tree. The tree's `execCicsStatement` node is still useful for the LINE (→ composer).
     * **CallTree CSV CICS vocabulary** (ExecCicsStatementType): CICSLINK, CICSXCTL, CICSRUN/STARTTRANSID,
       CICSDELETE/READ/REWRITE/WRITE/STARTBR/READNEXT/READPREV, + **CICSOTHER**. CICS file ops + XCTL/LINK are
       structured with RESOLVED operands (filename / target, BYLITERAL vs BYIDENTIFIER) — covers RUL-COBOL-013/014/018.
       But **SEND/RECEIVE MAP and RETURN TRANSID are CICSOTHER** — NOT structured. For those (RUL-COBOL-015/016/017,
       needed for Q4), reconstruct the EXEC CICS…END-EXEC block from source (composer gives the line) and pull the
       MAP/MAPSET/TRANSID operand with the existing simple keyword-paren regexes (`_RE_MAP_OP` etc. in cobol.py) —
       the block boundary is grammar-given; only the operand extraction is keyword-paren, not COBOL parsing.
     * **CSV has no line numbers** — marry CSV rows to tree nodes by document order for the line, OR (cleaner for
       CICS, since tree has CICSOTHER nodes the CSV lacks) reconstruct-from-source-block for everything CICS and use
       CSV only for the resolved operand. CALL: CSV CALLBYLITERAL→static program:, else dynamic→unresolved:; line via
       tree callStatement + composer. INCLUDES: CSV COPY rows; line = COPY directive (content-anchor "COPY X" in woc);
       **FD-context + REPLACING are NOT in the CSV** → read them from the source COPY statement + section (as the regex
       extractor does). file-control SELECT: tree `fileControlEntry` IS structured (select/assign/org/access) + composer
       line. Batch (non-CICS) I/O: CSV DD flags give read/write/update per file but NO line → get lines from tree I/O
       statements. program-id: CSV PGM row + tree `programIdParagraph` line.
     * **Mapping fidelity:** reproduce the exact RUL-COBOL data payloads (see cobol.py:355-1012) so Pass-3/gold don't
       change. identifier-form XCTL → `unresolved:*` + `must_not_promote: True` (CSV CICSXCTLBYIDENTIFIER).
       This is a SUBSTANTIAL build (~13 rules, two surfaces, order/block matching) — scope a focused session; validate
       facts-parity vs regex per-rule (extract both, diff observation `data`) before the Phase-2 gate.
     * **KNOWN BOUNDARY — document honestly (the project's directive), same class as the continuation-line boundary:**
       SEND/RECEIVE-MAP/RETURN-TRANSID operand extraction is **keyword-level** (keyword-paren `MAP(x)`/`MAPSET(y)`/
       `TRANSID(z)` extraction inside the grammar-DELIMITED EXEC CICS…END-EXEC block), NOT full CICS-grammar parsing.
       This is acceptable because the block boundary is grammar-given and the MAJOR CICS verbs (LINK/XCTL/file-ops/
       transid, incl the must-not-promote CICSXCTLBYIDENTIFIER) ARE structured by CallTree — the MAPA pick is unchanged.
       But it IS a boundary: belongs in the README "what generalizes" section next to continuations. **CICSOTHER must
       not become a silent-brittle corner:** content-validate each extracted operand against the block text and FAIL
       LOUD on ambiguity (no operand found / multiple candidates) rather than emit a guess.
     * **Per-mapper invariant:** content-validation / fail-loud on EVERY mapper, not just provenance —
       validate each rule's `data` payload against the source evidence; an unvalidated mapping fails loud, never emits.
       Then the Phase-2 three-way diff (Task 4) categorizes EVERY delta honestly — parity / improvement / regression —
       including the −31/+31 PROCEDURE-fragment-copybook population and the copybook-origin-CALL improvements; surface
       any real regression rather than smoothing it.
4. **Phase 2 — the real gate: PASS (2026-06-01).** Driver `artifacts/phase2_diff.py` runs full Gate-3
   both variants (`CARDDEMO_COBOL_PARSER=regex|mapa` → `artifacts/gate3_{regex,mapa}/`, gitignored),
   gold_match each, three-way observation diff (parity/improvement/regression).
   **Result:** program-rule regressions **0**; gold regressions **0**; graph at parity (mapa **1863
   ent / 1444 edges** vs regex **1864 / 1445** — the −1/−1 is the net of improvements). gold_match:
   regex 37/40 (0 real), mapa 36/40 (0 regressions; 1 improvement-candidate). All validation green.
   - **Dividends (improvements, categorized):** copybook-origin CALL discovered (COACTUPC→CSUTLDTC,
     copybook provenance — regex never scans copybook bodies); 2 regex READ-TO false positives dropped
     (COCRDLIC); DataItem `PIC +ZZZ,ZZZ,ZZZ.ZZ` correctly typed NUMERIC(11,2) (CVTRA07Y) where regex saw
     a group. Pre-existing copybook-layer obs deltas (RUL-002 copybook-presence entities ×31 → Pass-3
     materializes; RUL-021 PIC fix) are benign, not from the program flip.
   - **RESOLVED — gold Q3.2 updated (the sponsor ruled UPDATE, 2026-06-01, commit b30c8fd):** Q3.2
     `reachable_programs` `[]` → `[program:CSUTLDTC, program:CEEDAYS]` + changelog audit entry.
     Source-traced (COACTUPC.cbl:3743 COPY CSUTLDPY → CSUTLDPY.cpy:255 CALL 'CSUTLDTC' → CSUTLDTC.cbl:93
     CALL "CEEDAYS"); the freeze-time `[]` came from a program-body-only grep that didn't expand copybooks.
     After update: **mapa 37/40, 0 real diffs (fully green)**; notably the **regex baseline now shows a REAL
     Q3.2 diff** (can't see the copybook-origin call) — the corrected gold exposes the exact under-counting
     the migration fixes. MAPA is now demonstrably more correct than regex, not merely at parity. Q3.3
     (COTRN01C) verified unchanged (does not COPY CSUTLDPY).
   - **CBSTM03A.CBL → regex fallback** (col-7 continuation boundary, Phase-3) — see Scope caveat above.
   Original step-4 plan (kept): every regression fixed generically in the parser/bridge, never a
   CardDemo-specific rule; improvements are the dividend.

## Invariants / guardrails

- Observations identical in shape (`extract/observation.py`, `evidence_kind="deterministic"`,
  rule_ids from `deterministic_rules.md`, provenance = path+line range from node spans).
- **CardDemo-specific handling in the bridge is the anti-pattern — flag it, don't bury it.**
- Don't harden the abstract adapter interface before parser #2 (JCL) tests it.
- 100% original-coordinate provenance is a structural invariant.

## Artifact pointers

- `artifacts/parser_bakeoff_phase0.md` — MAPA vs ProLeap bake-off + pick.
- `artifacts/parser_provenance_proof.md` — provenance proof + generalization boundary.
- `artifacts/parser_foundation/mapa_origin_tracker.patch` — our MAPA delta (standalone).
- `artifacts/parser_foundation/fold_align.py` — provenance round-trip proof of record.
- `artifacts/parser_foundation/README.md` — MAPA attribution + apply/build steps.
- `README.md` / `SHOWCASE.md` — reframe drafts, **uncommitted** until the foundation proves out
  (Phase 2 green); then rewrite the generalization claim honestly.
