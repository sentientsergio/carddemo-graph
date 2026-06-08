# FACTUAL CLAIMS-SPINE BRIEF — carddemo-graph POC

## 1. Scope Note

carddemo-graph is a proof-of-concept that extracts a single legacy mainframe application (AWS CardDemo: COBOL/JCL/BMS/CICS/VSAM) into a provenance-rich, Cypher-queryable (kuzu) knowledge graph for modernization and maintenance planning. Extraction is a three-pass role-separated pipeline (deterministic observation → LLM-candidate, empty in this POC → merge/resolve). COBOL Pass-1 originally used a hand-tuned regex extractor; it was replaced by a vendored ANTLR4 grammar parser (MAPA), now the default behind env flag `CARDDEMO_COBOL_PARSER` (regex|mapa, default mapa). The graph is validated against a frozen gold set (Q1–Q6) via `gold_match.py`, and was exercised by a downstream-agent trial (Gates 0–4). Every quantitative claim below is grounded in a named repo artifact (all paths are repository-relative). **This is an N=1 result: only AWS CardDemo has been proven end-to-end; no generalization to other mainframe systems is claimed.**

---

## 2. Claims by Cluster

### Cluster: Extraction Method

**[EM-001] The extraction pipeline implements a three-pass role-separated architecture: Pass 1 (deterministic observation) emits Observation objects; Pass 2 (LLM-candidate) is empty in this POC; Pass 3 (merge/resolve) is the sole writer of entities.json and edges.json.**
- Grounding: `src/carddemo_graph/extract/observation.py:1-8` defines Observation as the Pass 1 unit; `src/carddemo_graph/resolve/pass3.py:685-722` implements `write_artifacts()` writing entities.json (line 696) and edges.json (line 702) as sole writers.
- Validation strength: mechanical-deterministic
- Caveats: Pass 2 is explicitly deferred; enrichments.json is written empty by design at line 719 to establish the architectural slot for future Pass 2 enrichment promotion.
- Testable form: Parse Pass 3 source and confirm `write_artifacts()` is the only public method writing entities.json/edges.json. Grep the codebase for other write calls to these filenames; confirm none. Load both artifacts and verify schema_version and header are identical.

**[EM-002] Every edge carries provenance with source_path, start_line, end_line, source_file_id, source_hash as required fields; every edge also carries rule_id, evidence_kind, and confidence fields.**
- Grounding: `artifacts/schema.json:24-36` define ProvenanceItem required fields; `:159-176` define Edge required fields rule_id, evidence_kind, confidence, provenance; an actual edge in `artifacts/agent_packet/edges.json` shows all required fields present.
- Validation strength: mechanical-deterministic
- Caveats: snippet and role are optional fields (schema lines 32-33). All required fields are enforced by schema validation and present in all 1445 edges.
- Testable form: Parse edges.json, sample 10 random edges. Verify each has a non-empty provenance array; for each provenance item confirm the 5 required fields. Verify each edge has rule_id, evidence_kind, confidence at top level.

**[EM-003] Unresolved references are emitted as first-class entities (never dropped); they are marked partial=true, carry a surface_form property, and all are listed in unresolved_records in the resolution report.**
- Grounding: `artifacts/agent_packet/entities.json` contains 3 unresolved entities (unresolved:CDEMO-TO-PROGRAM, unresolved:LIT-MENUPGM, unresolved:CCARD-NEXT-PROG), all partial=true with properties.surface_form; `src/carddemo_graph/resolve/pass3.py:472-508` (`_materialize_unresolved`) creates these and adds to unresolved_records (line 500); `artifacts/agent_packet/known_unknowns.md:19-29` document them.
- Validation strength: mechanical-deterministic
- Caveats: Total 32 partial entities; 3 are unresolved (dynamic CALL/XCTL targets), 29 are external/phantom references. `_collect_remaining_partials` (pass3.py:103-122) merges all partials.
- Testable form: Parse entities.json, filter id='unresolved:*'. Verify all 3 have partial=true and properties.surface_form. Cross-reference against known_unknowns.md §2; count == 3. Confirm all 3 appear in the resolution report unresolved section.

**[EM-004] Schema is versioned as schema_version='1.1.0'; entity types and edge types are closed-vocabulary enums (13 entity types, 23 edge types).**
- Grounding: `artifacts/schema.json:6` declares schema_version='1.1.0'; `:51-67` enumerate 13 EntityType values; `:70-96` enumerate 23 EdgeType values; entities.json and edges.json headers both show schema_version='1.1.0'.
- Validation strength: mechanical-deterministic
- Caveats: Strict enum validation; no additional entity/edge types permitted.
- Testable form: Parse schema.json, count EntityType enum (13) and EdgeType enum (23). Verify schema_version='1.1.0' in both artifact headers. Verify all entity/edge type values fall in their enums.

**[EM-005] The merge/resolve phase groups observations by id_candidate, merges provenance across multiple rule observations for the same entity, and records merge decisions (count, rule_ids, sources) in resolution_report.md; in gate3 output, 73 such entities are explicitly logged.**
- Grounding: `src/carddemo_graph/resolve/pass3.py:174-241` (`_merge_entity_candidates`, `_merge_one_id`) group by id_candidate and merge provenance (lines 184-205); lines 236-241 record decisions; `artifacts/agent_packet/resolution_report.md:11-85` document 73 merge decisions.
- Validation strength: mechanical-deterministic
- Caveats: Single-rule entities are not listed; contributing_rule_ids is added only when len(rule_ids) > 1 (lines 228-229). Of 1864 total entities, 41 have contributing_rule_ids.
- Testable form: Count resolution_report.md merge-decision lines matching 'merged from \d+ observations' (== 73). Filter entities.json for contributing_rule_ids (== 41, subset of 73). Spot-check 3 merged entities for multiple rule_ids and sources.

**[EM-006] LLM-candidate pass (Pass 2) is empty in this POC; enrichments.json contains zero enrichment entries by design, establishing the architectural commitment that skeleton (entities/edges) is separate from enrichments.**
- Grounding: `artifacts/agent_packet/enrichments.json` shows schema_version='1.1.0' and `'enrichments': []`; `src/carddemo_graph/resolve/pass3.py:715-722` (line 719) explicitly creates the empty enrichments artifact.
- Validation strength: mechanical-deterministic
- Caveats: By design, not a limitation. The empty file establishes the Pass-2 slot. No llm_candidate evidence_kind appears in observations.
- Testable form: Parse enrichments.json; confirm schema_version='1.1.0' and enrichments length 0. Grep /src for any active code path producing llm_candidate observations; confirm none.

**[EM-007] Evidence_kind captures the provenance chain: deterministic (Pass 1), resolved (merged >1 observation), derived (RUL-DERIV-* rules), or manual (reserved). The deterministic-edge count is run-specific: 1406 in the agent_packet snapshot (gate3 2026-05-29), 1405 in the current MAPA-default run (run_id gate3-fulltree-20260603T142240Z).**
- Grounding: `artifacts/schema.json:11-15` define the EvidenceKind enum; `src/carddemo_graph/resolve/pass3.py:221` sets 'resolved', line 155 sets 'derived' for RUL-JCL-PROC-004 EXPANDS_TO; `artifacts/agent_packet/edges.json` → deterministic=1406, resolved=23, derived=16; `artifacts/gate3_mapa/edges.json` (run_id gate3-fulltree-20260603T142240Z) → deterministic=1405 (the −1 is the net of the MAPA-default improvements).
- Validation strength: mechanical-deterministic
- Caveats: manual is reserved/unused in this POC. llm_candidate would appear in observations from Pass 2 (empty). All edges are one of {deterministic, resolved, derived}. Cite the matching run_id when quoting the count — the two runs differ by 1.
- Testable form: Extract unique evidence_kind values from the chosen run's edges.json; confirm set = {deterministic, resolved, derived}. Count deterministic — 1406 for agent_packet, 1405 for gate3_mapa. Spot-check: derived edges have rule_id RUL-DERIV-*; resolved reference multiple rules.

**[EM-008] Entity merge uses OR-semantics for boolean flags, accumulation for list-valued keys, and setdefault for atomic keys; canonical rule_id is determined by _canonical_rule_id() prioritizing COBOL > BMS > JCL > CSD > RES families; contributing_rule_ids are retained when >1.**
- Grounding: `src/carddemo_graph/resolve/pass3.py:196-205` (OR-flags line 199, list-accumulate line 202, setdefault line 205); `:819-839` define `_rule_rank()` and `_canonical_rule_id()` family precedence; `:228-229` retain contributing_rule_ids.
- Validation strength: mechanical-deterministic
- Caveats: Canonical selection is deterministic, seeded by rule-family rank. All 41 multi-rule entities have contributing_rule_ids.
- Testable form: Find 3 entities with contributing_rule_ids (e.g., program:COACTUPC with ['RUL-COBOL-001','RUL-CSD-002']); verify multiple ids. Verify jcl-proc:REPROC has properties.filename_mismatch=true from the alternate source.

**[EM-009] The resolution pass enforces negative invariants: dynamic CALLs never promote to static (RUL-NEG-001, routed to unresolved); no direct Program → Dataset edges (RUL-NEG-002, enforced by edge vocabulary); COPY outside FD record area never produces DEFINES_LAYOUT_FOR (RUL-NEG-006, in the COBOL extractor).**
- Grounding: `src/carddemo_graph/resolve/pass3.py:18-21` document the guards; `:439-445` route dynamic calls to `_materialize_unresolved`; `src/carddemo_graph/validation/structural.py:45-48` state the no-direct-prog-dataset invariant; edges.json shows zero Program→Dataset edges.
- Validation strength: mechanical-deterministic
- Caveats: RUL-NEG-002 is schema-enforced (no Program→Dataset edge type in the enum). RUL-NEG-006 is handled in COBOL Pass 1, not the resolver.
- Testable form: Search edges.json for from='program:*' AND to='dataset:*' (empty). Verify unresolved:* entities carry properties.reason='dynamic_call'. Grep the COBOL extractor's DEFINES_LAYOUT_FOR rule for FD/WORKING-STORAGE context filtering.

**[EM-010] The sole conflict in gate3 is jcl-proc:REPROC (proc_name_collision, RUL-RES-006): REPROC.prc and TRANREPT.prc both declare PROC name=REPROC. Resolution retains merged provenance with filename_mismatch=true on the alternate source.**
- Grounding: `artifacts/agent_packet/resolution_report.md:87-96` document the collision (competing_sources + filename_mismatch); `src/carddemo_graph/resolve/pass3.py:243-286` implement proc-collision detection; entities.json shows jcl-proc:REPROC with provenance from both sources.
- Validation strength: demonstrated-once
- Caveats: Corpus-specific (N=1). The conflict ledger shows exactly 1 entry. Resolved by retaining merged provenance; the alternate source is flagged, not dropped.
- Testable form: Parse the conflict ledger (== 1 entry); confirm it is jcl-proc:REPROC with competing_sources=[REPROC.prc, TRANREPT.prc]. Verify the entity has 2 provenance entries and filename_mismatch=true on the TRANREPT.prc source.

---

### Cluster: Grammar-Parser Foundation

**[GPF-1] COBOL Pass-1 extraction now uses a vendored ANTLR4 grammar parser (MAPA) as the default extractor, selected by env flag CARDDEMO_COBOL_PARSER with default value 'mapa'.**
- Grounding: `src/carddemo_graph/extract/parsers/registry.py:8-9, 31-32`.
- Validation strength: mechanical-deterministic
- Caveats: MAPA is COBOL-only; JCL/BMS/CSD/assembler use separate extractors. Regex extractor is retained and selectable via CARDDEMO_COBOL_PARSER=regex.
- Testable form: Read registry.py line 32; confirm `_DEFAULT_COBOL_PARSER == 'mapa'`. Set the flag to mapa and call `get_cobol_extractor()`; verify extract_cobol_mapa returned. Set to regex; verify extract_cobol returned.

**[GPF-2] The grammar-parser foundation is pluggable via parse/normalize/map seams and a registry dispatch mechanism, allowing additional language parsers to be added by registering adapters without re-architecting orchestration.**
- Grounding: `src/carddemo_graph/extract/parsers/registry.py:52-72`; `src/carddemo_graph/extract/parsers/cobol/adapter.py:1-22, 29-32`.
- Validation strength: mechanical-deterministic
- Caveats: Only COBOL has an alternate adapter (MAPA); the interface is not finalized against parser #2 (JCL). Pattern is established, not yet hardened for general use.
- Testable form: Inspect `get_extractor()`; verify it routes cobol/jcl/proc/bms/csd to language extractors. Confirm adapter.py imports parse, normalize, and map as distinct modules. Verify adding a parser requires no edits outside registry.py and adapters.

**[GPF-3] The regex extractor (extract.cobol.extract_cobol) is retained, unchanged, and remains selectable for Pass-1 via CARDDEMO_COBOL_PARSER=regex; Phase-2 validation uses it as the baseline for facts-parity comparison.**
- Grounding: `src/carddemo_graph/extract/parsers/registry.py:14-15, 42-44`; `src/carddemo_graph/extract/cobol.py:1-10`.
- Validation strength: mechanical-deterministic
- Caveats: The regex extractor is unmodified; it is a frozen baseline for two-variant comparison.
- Testable form: Confirm extract_cobol exists in cobol.py. Run it on a test program; verify Observations emitted. Set the flag to regex and run gate3; verify regex observations in `artifacts/gate3_regex/`.

**[GPF-4] DataItem extraction (COBOL copybook record layouts) is mapped via MAPA parse-tree walk (map_dataitem), reuses the unchanged _suggested_sql_type() from the regex baseline, and achieves byte-parity with the regex extractor on DataItems across copybooks with 0 regressions plus improvements (PIC +ZZZ,ZZZ,ZZZ.ZZ correctly typed).**
- Grounding: `src/carddemo_graph/extract/parsers/cobol/map_dataitem.py:1-12`; `tests/test_mapa_dataitem.py:45-56, 68-79`; `RESUME.md:72-75`.
- Validation strength: mechanical-deterministic
- Caveats: N=1 corpus. Q6.1 (CVACT01Y) is simple (no edited/COMP-3/OCCURS/REDEFINES); complex layouts tested only on Q6.2 (CVEXPORT). BMS symbolic-map copybooks stay on the regex path. Exact counts (517 DataItems, 31 copybooks, 3 improvements) are from RESUME; the gold-set test verified correct types on CVACT01Y and CVTRA07Y.
- Testable form: Run `pytest tests/test_mapa_dataitem.py::test_dataitem_parity_on_gold_copybook`; verify fields match the regex baseline. Run `test_mapa_catches_plus_sign_edited_pic_regex_misses`; verify MAPA catches PIC +ZZZ,ZZZ,ZZZ.ZZ.

**[GPF-5] Program-construct emission (CALL, EXEC CICS, SELECT, batch I/O) via MAPA reaches facts-parity with the regex baseline on parametrized programs covering all implemented rules with 0 unexpected regressions and documented improvements.**
- Grounding: `tests/test_mapa_program_emission.py:36-55, 139-187`; `RESUME.md:79-105`.
- Validation strength: mechanical-deterministic
- Caveats: CBSTM03A.CBL (col-7 continuation lines) falls back to regex (FoldAlignmentError; Phase-3 boundary). RUL-COBOL-009/010/012/013/015 are corpus-unexercised. Batch-I/O delta filtering excludes known regex false positives (SET MORE-RECORDS-TO-READ TO TRUE).
- Testable form: Run `pytest tests/test_mapa_program_emission.py::test_program_construct_parity` (8 tests); all pass. Run `test_continuation_program_falls_back_to_regex`. Inspect IMPLEMENTED_RULES set; count == 18.

**[GPF-6] Program-construct provenance (line mapping from preprocessed parse tree back to original source/copybook lines) is solved via ProgramConstructResolver with content-validation: every construct's mapped source line is assertion-checked to contain the construct's signature (verb + operands), fail-loud on mismatch, preventing silently-wrong provenance edges.**
- Grounding: `src/carddemo_graph/extract/parsers/cobol/program_provenance.py:1-30, 80-100`; `tests/test_mapa_program_provenance.py:75-104`; `RESUME.md:143-170`.
- Validation strength: mechanical-deterministic
- Caveats: Validated exact on 3 programs only (CBTRN02C, COACTUPC, COCRDUPC); extrapolated to full corpus. Multi-pass COPY-composition naive chaining failed; converged on ordinal-content-anchor per construct. COPY is lexical-on-source using frozen keyword-level patterns from the regex baseline.
- Testable form: Run `pytest tests/test_mapa_program_provenance.py::test_program_provenance_exact` for CBTRN02C (7+), COACTUPC (18+), COCRDUPC (12+), COBSWAIT (1+); all pass. Verify `_src_code` (line 64) compares cols 1..72 only. Verify content-validation asserts verb keyword present.

**[GPF-7] Copybook-origin constructs (CALL/CICS inside PROCEDURE copybooks) are detected and attributed to the copybook source, not the program — a dividend over regex which only scans program bodies. COACTUPC→CSUTLDTC is the documented instance.**
- Grounding: `RESUME.md:82-84, 153-158`; `tests/test_mapa_program_provenance.py:98-103`; `gold/gold_set.md:494-495`.
- Validation strength: demonstrated-once
- Caveats: Observed once (COACTUPC COPY CSUTLDPY containing CALL 'CSUTLDTC'). Copybook-origin CICS is generalization-only — no corpus instance. Improvement delta (regex emits 0).
- Testable form: Run `pytest tests/test_mapa_program_provenance.py::test_copybook_origin_call_is_attributed_to_copybook`. Grep COACTUPC.cbl body for CALL CSUTLDTC (no match); grep CSUTLDPY copybook (match at line 255).

**[GPF-8] The Normalize seam (fold_align) maps preprocessed parse-tree coordinates back to original source via a content-anchored two-pointer walk, handling blank-collapse fold and refusing (FoldAlignmentError) rather than emitting silently-wrong provenance on any mismatch.**
- Grounding: `src/carddemo_graph/extract/parsers/cobol/normalize.py:22-27, 70-114`; `tests/test_mapa_dataitem.py:89-115`.
- Validation strength: mechanical-deterministic
- Caveats: Proven only for blank-collapse fold (0 classic col-7 continuations in CardDemo except CBSTM03A, which fails loud). Continuation-folding is Phase-3 work; unhandled continuations are detected and refused.
- Testable form: Run `pytest tests/test_mapa_dataitem.py::test_fold_align_blank_collapse_and_drift, test_fold_align_keeps_leading_blank, test_fold_align_is_fail_loud_on_mismatch, test_fold_align_rejects_non_1to1_strip`; all 4 pass.

**[GPF-9] MAPA is vendored as source + standalone patch (mapa_origin_tracker.patch) + documented build step (vendor/mapa/build.sh); upstream MAPA remains pristine under vendor/mapa/upstream/ at commit 2ad7cd5. The delta is reviewable and upstream-offerable.**
- Grounding: `vendor/mapa/README.md:1-37`; `vendor/mapa/build.sh`; `vendor/mapa/upstream/` structure; `vendor/mapa/LICENSE`; `vendor/mapa/mapa_origin_tracker.patch` (91 lines).
- Validation strength: mechanical-deterministic
- Caveats: Build artifacts (CallTree.jar, MapaTreeDump.class, generated ANTLR sources, build/) are gitignored. Requires JDK 17+ on PATH.
- Testable form: Confirm vendor/mapa/upstream/ is pristine (Makefile, src/*.java, *.g4). Confirm the patch applies cleanly. Run build.sh; verify CallTree.jar produced. Verify LICENSE/attribution preserved.

**[GPF-10] The Phase-2 gate (artifacts/phase2_diff.py) runs full Gate-3 both variants and validates: program-rule regressions 0, gold regressions 0, graph parity (mapa 1863 ent / 1444 edges vs regex 1864 / 1445), gold_match 37/40 for mapa (0 real diffs after Q3.2 update).**
- Grounding: `RESUME.md:207-228`; `artifacts/gate3_mapa/resolution_report.md` (run_id gate3-fulltree-20260603T142240Z, 1863 entities, 1444 edges); `gold/gold_set.md:19, 494-495`.
- Validation strength: demonstrated-once
- Caveats: N=1. Q3.2 gold was corrected post-freeze (COACTUPC→CSUTLDTC surfaced via MAPA, not pre-existing); mapa now shows 0 real diffs (regex baseline shows the real under-counting).
- Testable form: Read gate3_mapa/resolution_report.md; confirm 1863/1444 and run_id. Inspect and run phase2_diff.py; verify gold_match for both parsers.

**[GPF-11] CICS operand extraction (SEND MAP, RECEIVE MAP, RETURN TRANSID) uses keyword-paren patterns on the grammar-delimited EXEC block text (block boundary from the execCicsStatement tree node), not full CICS-grammar parsing. The construct LINE is resolver-validated and fail-loud; operand-level content-validation / fail-loud-on-ambiguity is NOT implemented (deferred to Phase-3).**
- Grounding: `src/carddemo_graph/extract/parsers/cobol/map_program.py` `_cics_map` / `_dispatch_cics` — the operand is taken from the first `_RE_MAP_OP`/`_RE_TRANSID_OP` match and emitted with no validation or ambiguity check. The construct line goes through the content-validated `ProgramConstructResolver`. Framing per the SB-4 boundary entry. (The module docstring at map_program.py:19-22 OVERSTATES this as "content-validated and fail-loud" — that wording is inaccurate and is being corrected; do NOT cite it.)
- Validation strength: asserted-unverified
- Caveats: Keyword-paren is a documented boundary. Major CICS verbs (LINK/XCTL/file-ops) ARE structured by CallTree CSV. Operand-level content-validation for SEND/RECEIVE-MAP/RETURN-TRANSID is Phase-3 work, NOT a completed property — must not be cited as done.
- Testable form: Read `_cics_map` in map_program.py and confirm the MAP/MAPSET/TRANSID operand is emitted directly from the regex match with no content-validation step and no raise-on-ambiguity. Contrast with the construct-line path through ProgramConstructResolver (which does fail-loud).
- *(FLAGGED — asserted-unverified; operand content-validation NOT built; see §4.)*

**[GPF-12] The generalization thesis — 'MAPA implements the language standard, not the corpus' — is demonstrated-once on CardDemo but is NOT a proven general guarantee. False positives (regex READ-TO in SET MORE-RECORDS-TO-READ), improved accuracy (PIC +ZZZ,ZZZ,ZZZ.ZZ), and copybook-origin discoveries (COACTUPC→CSUTLDTC) are CardDemo-specific evidence.**
- Grounding: `RESUME.md:12-13`; `tests/test_mapa_program_emission.py:77-92`; `RESUME.md:79-105`.
- Validation strength: demonstrated-once
- Caveats: Only one corpus tested (N=1). MAPA's COBOL-standard coverage is upstream-validated by the MAPA community; we validate conformance on this corpus via facts-parity and gold.
- Testable form: Compare regex vs mapa observations on CardDemo programs; document improvements as facts. Run on a second corpus (if available) to validate generalization.

**[GPF-13] Documented boundaries (in adapter.py and RESUME.md, surfaced via fail-loud exceptions) prevent silent correctness defects: col-7 continuation lines (CBSTM03A.CBL falls back to regex; FoldAlignmentError), content-validation mismatches (ProvenanceError), and unexercised corpus constructs (RUL-COBOL-009/010/012/013/015).**
- Grounding: `src/carddemo_graph/extract/parsers/cobol/adapter.py:35-43, 70-78`; `RESUME.md:43-56`; `tests/test_mapa_program_emission.py:140-154`.
- Validation strength: mechanical-deterministic
- Caveats: Boundaries are documented but not comprehensive across all COBOL constructs. The CBSTM03A regex fallback is pragmatic, not a final fix; continuation-folding is Phase-3 work.
- Testable form: Confirm the `_PROGRAM_BOUNDARY` exception tuple in adapter.py includes FoldAlignmentError and ProvenanceError. Run the adapter on CBSTM03A.CBL; verify the stderr FoldAlignmentError-fallback message.

**[GPF-14] JCL, BMS, CSD, PROC, and assembler extraction remain unchanged; assembler is not extracted. Only COBOL has the grammar-parser foundation swap; other languages are out of scope for this work.**
- Grounding: `src/carddemo_graph/extract/parsers/registry.py:4-5, 60-72`; `src/carddemo_graph/extract/parsers/cobol/adapter.py:12-15`.
- Validation strength: mechanical-deterministic
- Caveats: JCL may be a future grammar-parser candidate; assembler may be deferred indefinitely.
- Testable form: Confirm parsers/cobol/ exists with no parallel parsers/jcl/, /bms/, /csd/. Confirm registry.py routes jcl/proc/bms/csd to existing extract modules, not adapters.

---

### Cluster: Parser Parity and Superiority

**[PAR-1] MAPA reaches facts-parity with the retained regex extractor on all 18 implemented program-construct rules (RUL-COBOL-001 through 018) across 8 tested programs (CBTRN02C, CBACT01C, CBACT04C, COACTUPC, COCRDUPC, COMEN01C, COBSWAIT, COCRDLIC), with 1 documented fallback (CBSTM03A.CBL) out of 33 total CardDemo programs.**
- Grounding: `tests/test_mapa_program_emission.py:36-55` (18 rules), `:96-100` (8 programs), `:158-187` (parity tests pass), `:140-154` (CBSTM03A fallback test passes).
- Validation strength: mechanical-deterministic
- Caveats: CBSTM03A.CBL falls back to regex (col-7 continuation; Phase-3 deferred). The 8 programs cover representative patterns; the full 32/33 corpus is covered by the full-tree gate3 extraction. RUL-009/010/012/013/015 are corpus-unexercised (parity on these is a default-pass on empty sets).
- Testable form: Run `pytest tests/test_mapa_program_emission.py::test_program_construct_parity -v` with vendor/mapa built; all 8 pass, payloads identical modulo allowed improvements. Run `test_continuation_program_falls_back_to_regex`.

**[PAR-2] Full-corpus gate3 extraction produces entity/edge parity in the kuzu graph under both COBOL parsers: MAPA 1863 entities / 1444 edges vs regex 1864 / 1445, schema 1.1.0 (the one-entity variance is a documented copybook-layer asymmetry, not a program-construct regression).**
- Grounding: `artifacts/gate3_mapa/entities.json` + `artifacts/gate3_regex/entities.json` (run_ids gate3-fulltree-20260603T142240Z and …142204Z); verified counts MAPA 1863/1444, regex 1864/1445; `artifacts/phase2_diff.py:32-39` (`_COPYBOOK_LAYER` exclusion documents RUL-002/020/021 asymmetries).
- Validation strength: mechanical-deterministic
- Caveats: Copybook-layer DataItem emission (RUL-002 presence entity, RUL-020/021 improvements) pre-exists and is benign. The −1/−1 net is improvements (copybook-origin CALL, false-positive batch I/O drops) partially offset by copybook-layer asymmetries.
- Testable form: Verify JSON counts directly: load both entities.json (1863 vs 1864) and both edges.json (1444 vs 1445).

**[SUP-1] MAPA demonstrably extracts correct call-graph reachability that regex misses: transaction:CAUP (entry program:COACTUPC) reaches [program:CSUTLDTC, program:CEEDAYS] via copybook-spliced CALL statements, where regex under-counted in gold (originally reachable_programs=[]). Gold amended 2026-06-01 based on independent source-verification, not MAPA-derivation.**
- Grounding: `gold/gold_set_changelog.md:144-160` (Q3.2 amendment with source citations); `gold/gold_set.md:476-495` (lines 487-488 show the added programs); corpus lines: COACTUPC.cbl:3743 (COPY CSUTLDPY), CSUTLDPY.cpy:255 (CALL 'CSUTLDTC'), CSUTLDTC.cbl:93 (CALL "CEEDAYS").
- Validation strength: hand-traced-gold *(the Q3.2 amendment was traced by engineer grep + source inspection of the three lines above — not a cold-agent read; cold-agent gold is Q6 only)*
- Caveats: The amendment was source-verified independently via grep + inspection, NOT derived from MAPA output; MAPA's CallTree merely surfaced the gap. Regex limitation: program-body-only scan misses procedure-copybook CALLs (regex never expands COPY). This is a gold CORRECTION, not rigging.
- Testable form: Independently verify the three source lines via grep. Verify the changelog entry exists at gold/gold_set_changelog.md with 2026-06-01 date and approval.

**[SUP-2] MAPA's grammar-based I/O parsing correctly drops 2 regex false-positive READ edges in program:COCRDLIC, where the regex pattern matches a 'READ' token ending a data-name (SET MORE-RECORDS-TO-READ TO TRUE) as a batch I/O statement; MAPA's grammar emits no I/O statement on those lines.**
- Grounding: `tests/test_mapa_program_emission.py:77-91` (`_is_regex_false_positive`, `_BATCH_IO_RULES`), `:96-100` (COCRDLIC in PROGRAMS), `:158-187` (parametrized parity includes COCRDLIC); corpus COCRDLIC.cbl lines 974, 1106.
- Validation strength: mechanical-deterministic
- Caveats: False positives are a known regex limitation (batch-I/O regexes fire on text, not grammar). MAPA's grammar is ground truth for statement classification; these are categorized as improvements, not regressions.
- Testable form: Run `pytest tests/test_mapa_program_emission.py::test_program_construct_parity[COCRDLIC] -v`; passes. Grep COCRDLIC.cbl for 'SET MORE-RECORDS-TO-READ' (lines 974, 1106). Confirm these do not parse as batch I/O.

**[SUP-3] MAPA discovers and emits copybook-origin CALL statements (procedure-copybook CALLs never reachable by regex's program-body-only scan): COACTUPC CALL 'CSUTLDTC' provenance is copybook CSUTLDPY.cpy, categorized as an allowed improvement, not a regression.**
- Grounding: `RESUME.md:81-84`; `tests/test_mapa_program_emission.py:58-74` (`_is_allowed_improvement` checks /cpy/ in source_path), `:96-100` (COACTUPC in PROGRAMS).
- Validation strength: demonstrated-once
- Caveats: Only COACTUPC in the corpus exercises procedure-copybook CALL. The rule generalizes, but empirical proof is N=1.
- Testable form: Run `pytest tests/test_mapa_program_emission.py::test_program_construct_parity[COACTUPC] -v`; passes. Verify `_is_allowed_improvement` returns True for the copybook-origin CALL (source_path contains /cpy/).

**[SUP-4] MAPA enables upstream gold correction: Q3.2 gold was amended from reachable_programs=[] to [CSUTLDTC, CEEDAYS] based on independent source-verification of copybook-spliced CALLs; this yields 0 diffs on Q3.2 for MAPA (vs 1 diff for regex after the gold update), demonstrating MAPA's superior coverage.**
- Grounding: `gold/gold_set_changelog.md:144-160` (signed amendment); `gold/gold_set.md:476-495` (Q3.2 updated reachable_programs); `RESUME.md:210-225` (mapa 37/40, 0 real diffs; regex shows the real Q3.2 diff).
- Validation strength: hand-traced-gold
- Caveats: The amendment was source-traced (manual grep + inspection), not derived from MAPA (not circular). It corrects an incomplete gold (freeze-time grep under-counted by not expanding COPY). After update, the regex baseline now shows why the correction was needed.
- Testable form: Verify the changelog entry and gold/gold_set.md Q3.2 lines 487-488. Source-trace the three calls (as in SUP-1). If gold_match were run on both artifacts, regex shows [DIFF] Q3.2.reachable_programs while MAPA shows [MATCH].

---

### Cluster: Provenance

**[PROV-1] 100% original-source-coordinate provenance is a structural invariant — every emitted Observation carries source_path and line numbers remapped from preprocessed coordinates back to their original files and lines.**
- Grounding: `src/carddemo_graph/extract/parsers/cobol/program_provenance.py:1-30`; `normalize.py:1-28`; `RESUME.md:236`.
- Validation strength: mechanical-deterministic
- Caveats: A design invariant enforced by the adapter contract; the strength for any single edge depends on the content-validation of its specific construct (see PROV-2).
- Testable form: For any observation with provenance, verify the source_path file exists, the line numbers fall within bounds, and reading the line confirms the construct's signature (e.g., a CALL line contains 'CALL').

**[PROV-2] Program-construct provenance (CALL, EXEC CICS, SELECT, COPY) is content-validated and fail-loud: every resolution asserts the mapped source/copybook line's content matches the construct's own statement text (verb + operands, operand-strict); on any divergence, ProvenanceError is raised rather than a silently-wrong edge emitted.**
- Grounding: `src/carddemo_graph/extract/parsers/cobol/program_provenance.py:21-26, 103-124`; `adapter.py:68-78`; `tests/test_mapa_program_provenance.py:86-94`.
- Validation strength: mechanical-deterministic
- Caveats: Enforced by `ProgramConstructResolver.resolve()`; the tested programs (CBTRN02C, COACTUPC, COCRDUPC, COBSWAIT) are a sample, not a universal guarantee.
- Testable form: For any emitted construct observation, read the cited line and confirm (a) it exists, (b) it contains the verb keyword, (c) the operand matches. Verify no exception was swallowed during extraction.

**[PROV-3] Program-native constructs are resolved by ordinal-preserving content-anchor: the Nth occurrence of a construct type in the folded program (without continuations) is matched to the Nth parse-tree node of that type, then mapped to source via proven fold_align, ensuring order-preserving exact match.**
- Grounding: `program_provenance.py:12-19, 96-114`; `RESUME.md:147-152`; `tests/test_mapa_program_provenance.py:76-94`.
- Validation strength: hand-traced-gold
- Caveats: Validated exact on CBTRN02C (≥7), COACTUPC (≥18 native), COCRDUPC (≥12), COBSWAIT (≥1) — a sample, not universal proof. Depends on fold_align correctness (see PROV-5).
- Testable form: Run the resolver on the four test programs; verify all callStatement, execCicsStatement, fileControlEntry nodes resolve without ProvenanceError; confirm line numbers/content match expectations at test lines 77-94.

**[PROV-4] Copybook-origin constructs (a CALL or EXEC CICS living in a PROCEDURE copybook) are resolved by statement-content search in the spliced copybooks and attributed to the copybook file, not the program — an improvement over regex which never scans copybook bodies.**
- Grounding: `program_provenance.py:115-139`; `RESUME.md:153-158`; `tests/test_mapa_program_provenance.py:98-103`.
- Validation strength: hand-traced-gold
- Caveats: Demonstrated on COACTUPC's CALL 'CSUTLDTC' in CSUTLDPY (line 255); no copybook-origin CICS exists in the corpus, so CICS is generalization-only. The regex baseline shows these as 'improvements' in the three-way diff.
- Testable form: Verify COACTUPC's CALL 'CSUTLDTC' is absent from COACTUPC.cbl body but present in CSUTLDPY.cpy:255; confirm the observation's provenance source_path points to CSUTLDPY.cpy line 255.

**[PROV-5] fold_align is a proven, content-anchored, fail-loud aligner that maps folded (blank-collapsed) program lines back to original source lines via a two-pointer walk asserting per-line content match; divergence raises FoldAlignmentError rather than emitting silently-wrong provenance.**
- Grounding: `normalize.py:70-114`; `artifacts/parser_provenance_proof.md:26-50`; `RESUME.md:34-41`.
- Validation strength: hand-traced-gold
- Caveats: Proven on CVEXPORT (98/98 fold lines, 0 flags) and CBTRN02C (678/678, 0 flags). Valid only for blank-collapse fold; true continuation-folding is unexercised Phase-3 work. Unhandled continuation raises FoldAlignmentError (the invariant working as designed).
- Testable form: Run fold_align on CVEXPORT and CBTRN02C; verify all lines align without FoldAlignmentError. For any aligned line, read the source at the mapped line and confirm content matches (via `_norm`/`_is_blank` in normalize.py:61-67).

**[PROV-6] CBSTM03A.CBL is the single CardDemo program with classic col-7 continuation lines (HTML literals continued across `-` lines); fold_align fail-loud-refuses on it (FoldAlignmentError), the adapter catches this and falls back to the regex extractor for that one program, preserving byte-identical output and pipeline integrity.**
- Grounding: `RESUME.md:43-56`; `adapter.py:36-43, 68-78`; `tests/test_mapa_program_emission.py:140-154`; `corpus/carddemo/stripped/app/cbl/CBSTM03A.CBL:124-125`.
- Validation strength: demonstrated-once
- Caveats: The only program in the corpus with this boundary case. The regex fallback is byte-identical (verified by test), so no information is lost. Continuation-folding proper is Phase-3 work.
- Testable form: Read CBSTM03A.CBL:124-125 (HTML STRING literal continued across col-7 `-`). Run emit_program on it; confirm FoldAlignmentError mentioning 'unhandled continuation'. Run extract_cobol_mapa; confirm it falls back and produces the regex-baseline observation set.

**[PROV-7] MAPA requires preprocessed input (cols >72 stripped, COPY spliced, continuations/blanks folded), so ANTLR coordinates point to preprocessed lines. The adapter remaps these to original coordinates, entirely in the Normalize seam (not the parser). The LIVE remap is NOT the upstream patch's per-pass origin sidecar — that sidecar (which the patch DOES emit, as full per-pass PASS+COPY records) is FILTERED OUT and unused; the live path is `fold_align` (content-anchored woc→source) plus content-based copybook statement-search in the resolver.**
- Grounding: the vendored patch `vendor/mapa/mapa_origin_tracker.patch` emits per-pass `.origin` records (PASS <inputLine> / COPY <copybookPath> <line>) — NOT a single minimal sidecar; `src/carddemo_graph/extract/parsers/cobol/parse.py:164` (`passes = [p for p in passes if not p.endswith(".origin")]`) drops those `.origin` files so they are not consumed in the live path; `normalize.py` `fold_align` + `program_provenance.py` `ProgramConstructResolver` (content-anchored woc→source + copybook statement-search) are the actual remap.
- Validation strength: mechanical-deterministic
- Caveats: The multi-pass `.origin` sidecar composition was an exploratory dead-end (mismaps on many-COPY programs) and is deliberately NOT used; the live remap relies on fold_align + content validation instead. The 1:1 col-strip stage is asserted; the fold stage is validated by fold_align (see PROV-5). Do NOT describe the patch as a "minimal COPY-splice sidecar" — it emits full per-pass records that are then filtered out.
- Testable form: `grep -n '\.origin' src/carddemo_graph/extract/parsers/cobol/parse.py` → confirm line ~164 filters `.origin` files out. Read the patch and confirm it emits full per-pass PASS+COPY records. Confirm the live remap path (fold_align + resolver) does not read `.origin`. Spot-check final provenance lines fall within source bounds + match content on 1-2 programs.

**[PROV-8] Sequence-numbered source lines (cols 73-80; present in 5 CardDemo programs including COBSWAIT) are handled by comparing cols 1-72 like-for-like, as fold_align does; this prevents spurious content-validation failures and is a regression guard proven by test_program_provenance_exact on COBSWAIT.**
- Grounding: `program_provenance.py:64-71`; `RESUME.md:89-94`; `tests/test_mapa_program_provenance.py:80-84, 86-94`.
- Validation strength: hand-traced-gold
- Caveats: Surfaced by COBSWAIT.cbl whose PROGRAM-ID and CALL lines carry cols-73..80 sequence numbers. The fix (compare cols 1..72, not 1..80) is integrated into `_src_code` and tested. A known regression guard, not a generalization flaw.
- Testable form: In COBSWAIT.cbl verify the PROGRAM-ID and CALL lines carry non-blank cols 73-80. Run the resolver on COBSWAIT; confirm no ProvenanceError and the CALL resolves to the correct line (min_constructs=1).

**[PROV-9] Gate-3 full-tree extraction under CARDDEMO_COBOL_PARSER=mapa produces 1863 entities / 1444 edges (run_id gate3-fulltree-20260603T142240Z, schema 1.1.0), with zero provenance regressions vs regex baseline (1864/1445); gold_match: mapa 37/40 (0 real diffs after Q3.2 correction).**
- Grounding: `artifacts/gate3_mapa/resolution_report.md:1-8`; `RESUME.md:210-212`; `gold/gold_set_changelog.md:144-160`.
- Validation strength: demonstrated-once
- Caveats: A single full-corpus run (N=1). The −1/−1 delta comprises improvements (copybook-origin CALL, DataItem PIC fix) plus pre-existing benign copybook-layer deltas. No regression means no silently-wrong edges.
- Testable form: Run gate3 with mapa; load the kuzu db; count 1863/1444; run gold_match (37/40, 0 real diffs). Spot-check 5-10 random edges for valid source_path/line + construct signature.

**[PROV-10] The col-7 continuation-line boundary (Phase-3 work) is the only generalization gap: blank-collapse + comment-preservation fold is fully exercised (CardDemo has zero continuation lines except CBSTM03A), and continuation-folding (N source lines → 1 anchored line) is unexercised and deferred.**
- Grounding: `RESUME.md:43-56`; `artifacts/parser_provenance_proof.md:52-74`; `normalize.py:22-27`.
- Validation strength: mechanical-deterministic
- Caveats: A documented, fail-loud boundary: fold_align raises FoldAlignmentError on any folded line matching no single strip line. Phase-3 will extend the walk to consume continuations and anchor to statement start.
- Testable form: Search the corpus for col-7 `-` continuation markers across all *.cbl/*.CBL; confirm zero except CBSTM03A.CBL. Verify no other program hits FoldAlignmentError during gate3. Confirm CBSTM03A falls back to regex without error, byte-identical.

---

### Cluster: Gold Validation

**[GV-Q1-FROZEN] Gold set Q1 entries (copybook direct-includer impact) are FROZEN as of 2026-05-13, signed by Reviewer B, covering 5 copybooks (CVACT01Y, CSUSR01Y, CVCRD01Y, COCOM01Y, CVTRA05Y) with hand-traced line citations.**
- Grounding: `gold/gold_set.md:1-10, 32-94`; `gold/gold_set_changelog.md:7-36`.
- Validation strength: hand-traced-gold
- Caveats: Q1 is subset-scoped to direct_includers; transitive closure and MOVE-chain enrichment are out of scope per the skeleton/enrichment principle.
- Testable form: Read gold/gold_set.md:32-94; verify every Q1.1-Q1.5 direct_includers entry has a source line citation. Independently grep the corpus for each cited COPY statement.

**[GV-Q1-DIRECT-INCLUDERS-MATCH] The kuzu graph (run_id gate3-fulltree-20260603T142240Z) matches the frozen gold on Q1.direct_includers exactly for all 5 copybooks: CVACT01Y (11/11), CSUSR01Y (12/12), CVCRD01Y (5/5), COCOM01Y (17/17), CVTRA05Y (11/11).**
- Grounding: `gold/gold_set_changelog.md:120`; `artifacts/gate3_mapa/entities.json` + `edges.json` (1863/1444).
- Validation strength: mechanical-deterministic
- Caveats: This comparison covers Q1.direct_includers only; Q1's other fields and Q2-Q4 have spot-checks in gate3_closure.md (lines 76-82) but not full comparator wiring as of the May-29 closure snapshot. The Q1 match predates post-freeze amendments.
- Testable form: `python3 -m carddemo_graph.gold_match artifacts/gate3_mapa gold/gold_set.md | grep Q1` — verify 5 [MATCH] lines for Q1.x.direct_includers.

**[GV-Q2-FROZEN-PROGRAM-ACCESS] Gold set Q2 entries (dataset access) are FROZEN covering 5 datasets (USRSEC, ACCTDATA, CARDDATA, TRANSACT, CARDXREF) with source-verified program_access sites and jcl_access job-level binding.**
- Grounding: `gold/gold_set.md:283-437`; `gold/gold_set_changelog.md:41-93` (F5 2026-05-13, Finding D 2026-05-28).
- Validation strength: hand-traced-gold
- Caveats: Q2 jcl_access is job-level (which jobs reference the dataset); per-step DD-name + DISP + inferred_access_mode is a known Gate-3 incremental deferral. Q2.2 ACCTDATA was corrected 2026-05-28 (Finding D) to add two COACTUPC sites (3470 READ, 3609 REWRITE).
- Testable form: Read gold/gold_set.md Q2.1-Q2.5 program_access tables (296-422); each row has verb_line + operand_line. Grep the corpus to verify cited EXEC CICS statements and DATASET operands.

**[GV-Q2-USRSEC-JCL-CORRECTED] Gold Q2.1 USRSEC jcl_access was corrected post-freeze (2026-05-13, F5): ESDSRRDS.jcl removed (it accesses the ESDS/RRDS variants, not the KSDS that CSD USRSEC binds to); final expected = 1 job (DUSRSECJ.jcl).**
- Grounding: `gold/gold_set.md:314`; `gold/gold_set_changelog.md:41-68`.
- Validation strength: hand-traced-gold
- Caveats: Corrects a freeze-time naming-convention inference error (same 'USRSEC' token across DSN variants). Signed off and recorded.
- Testable form: Grep the corpus JCL for 'DSN=AWS.M2.CARDDEMO.USRSEC.VSAM.KSDS' — exactly 1 match (DUSRSECJ.jcl). Grep 'USRSEC' to find ESDSRRDS.jcl; verify it references the distinct ESDS/RRDS variants.

**[GV-Q3-FROZEN-CLOSURE] Gold set Q3 entries (transaction-to-program closure via literal CALL/LINK/XCTL) are FROZEN covering 3 transactions (CC00, CAUP, CT01) with skeleton-scope (typed edges only; identifier-form XCTL stays unresolved per the MOVE-chain principle).**
- Grounding: `gold/gold_set.md:439-524`; `gold/gold_set_changelog.md:144-160` (2026-06-01 Q3.2 correction).
- Validation strength: hand-traced-gold
- Caveats: Q3.2 (CAUP) was corrected 2026-06-01 for copybook-expanded reachability: the freeze set [] on program-body-only grep, but COBOL COPY splices copybook code at compile time. Correction is source-verified independently (not MAPA-derived).
- Testable form: Read gold/gold_set.md Q3.1-Q3.3 (451-522); verify each reachable_programs list is backed by literal CALL/LINK/XCTL. For Q3.2, grep COACTUPC.cbl:3743, CSUTLDPY.cpy:255, CSUTLDTC.cbl:93.

**[GV-Q3-Q2-IMPROVEMENT] The Q3.2 gold correction (2026-06-01) adding CSUTLDTC + CEEDAYS to reachable_programs is independently source-verified and does not depend on the MAPA grammar parser; it reverses a prior incomplete gold entry to ground truth.**
- Grounding: `gold/gold_set.md:483-495`; `gold/gold_set_changelog.md:144-160`.
- Validation strength: hand-traced-gold
- Caveats: Reverses a freeze-time decision; the reversal is source-verified and ruled by Reviewer B. General lesson: gold reachability must be traced through COPY expansion, not program-body grep alone.
- Testable form: Source-trace COACTUPC: COPY CSUTLDPY at 3743; CSUTLDPY.cpy literal CALL at 255; CSUTLDTC.cbl CALL at 93.

**[GV-Q4-FROZEN-BMS] Gold set Q4 entries (BMS map surface for transaction) are FROZEN covering 3 transactions (CC00, CAUP, CM00) with literal-form map interactions; Q4.2 CAUP is skeleton-scoped to unresolved identifier-form maps.**
- Grounding: `gold/gold_set.md:528-698`; `gold/gold_set_changelog.md:69-81` (2026-05-28 Finding B).
- Validation strength: hand-traced-gold
- Caveats: Q4.1 CC00 and Q4.3 CM00 assert 27 and 21 INITIAL= clauses as field_surface; Q4.2 CAUP is amended (2026-05-28) to skeleton-scoped unresolved maps (field_surface=0) with the enrichment target recorded separately.
- Testable form: Read gold/gold_set.md Q4.1 COSGN00.bms (544-574) and Q4.3 COMEN01.bms (671-695); count INITIAL= lines (27 and 21). Grep the corpus BMS for 'INITIAL='. For Q4.2, read the skeleton-vs-enrichment note (583-595).

**[GV-Q4-AMENDMENT] Gold Q4.2 (CAUP BMS surface) was amended 2026-05-28 (Finding B) to assert skeleton scope: map_interactions list unresolved identifier-form placeholder maps; mapsets=[]; field_surface=0. The enrichment-resolved answer (COACTUP mapset, 52 fields) is documented as a Pass-2 enrichment target.**
- Grounding: `gold/gold_set.md:583-595`; `gold/gold_set_changelog.md:69-81`.
- Validation strength: hand-traced-gold
- Caveats: Corrects a skeleton/enrichment boundary mis-scoping. COACTUPC uses identifier-form SEND/RECEIVE MAP operands (MOVE-chain required); the skeleton does not resolve MOVE-chains.
- Testable form: Read gold/gold_set.md Q4.2 expected (583-595); verify mapsets=[] and field_surface=0. Grep COACTUPC.cbl for 'SEND MAP' identifier-form operands (no quotes).

**[GV-Q6-COLD-AGENT-GOLD] Gold set Q6 entries (field-level record layout) are COLD-AGENT gold: Q6.1 (CVACT01Y, 14 items) and Q6.2 (CVEXPORT, 72 items with hard cases: COMP-3, COMP, REDEFINES, OCCURS), both added 2026-05-29. Each was independently read from source by a cold agent and converged with the extraction on all items and types.**
- Grounding: `gold/gold_set.md:707-833`; `gold/gold_set_changelog.md:94-132`.
- Validation strength: cold-agent-gold
- Caveats: Convergence = agreement, not proof (two LLMs on clean COBOL). Q6.1 is the common case; Q6.2 exercises hard cases (4 COMP-3, 7 COMP incl. binary-with-implied-decimal trap, 6 REDEFINES, 2 OCCURS). A human COBOL expert would supersede. Known latent boundary: suggested_sql_type is mechanical (USAGE-driven); domain-aware ID typing is downstream enrichment.
- Testable form: For Q6.1, parse CVACT01Y.cpy: count elementary items at level 5+, list names/levels/PICTURE/SQL types; verify byte-sum=300 (RECLN); compare to gold lines 723-735. For Q6.2, parse CVEXPORT.cpy (500-byte), verify all 72 items, hard-case handling, byte-sum=500.

**[GV-Q6-CONVERGENCE] Q6.1 DataItem extraction (CVACT01Y) shows 14/14 field match + 14/14 sql_types(accepted) match vs cold-agent gold (the FILLER item is typed CHAR(178), included in the count). Q6.2 (CVEXPORT) shows 67/67 field + 67/67 type match (5 FILLER skip items excluded per the gold's own (skip) notation) with type-cell notation accepting equivalent sets (e.g., EXP-ACCT-ID 'BIGINT (or NUMERIC(11)/CHAR(11))').**
- Grounding: live harness output — `gold_match.py` prints `[MATCH] Q6.1.field_set: 14 expected; 14 actual` and `[MATCH] Q6.1.sql_types(accepted): 14 expected; 14 actual` against `artifacts/gate3_mapa/carddemo_graph.db`; `src/carddemo_graph/gold_match.py` `parse_q6`/`compare_q6`. (NOTE: the changelog narrative at `gold/gold_set_changelog.md` says "all 13 suggested_sql_types" for Q6.1 — that 13 is stale; the harness compares 14/14. The changelog narrative is being corrected.)
- Validation strength: demonstrated-once
- Caveats: N=1 corpus, two copybooks (simple + hard). Not a general guarantee for all COBOL copybooks. Q6 is cold-agent gold (convergence = agreement, not proof). Use 14/14 for Q6.1, not the changelog's 13/13.
- Testable form: `PYTHONPATH=src python -m carddemo_graph.gold_match artifacts/gate3_mapa/carddemo_graph.db gold/gold_set.md | grep -E 'Q6\.1|Q6\.2'` → `Q6.1.field_set: 14/14`, `Q6.1.sql_types(accepted): 14/14`, `Q6.2 67/67`.

**[GV-GOLD-MATCH-RESULT] The gold_match.py harness, run against the MAPA-default graph, mechanically compares Q1–Q4 and Q6 against the frozen gold and reports 37 matched / 0 diff / 3 known-incremental (of 40 comparisons), exiting 0.**
- Grounding: `src/carddemo_graph/gold_match.py:312-352` — `compare()` runs Q1 (`run_q1_sample`), Q2 (`program_access` + `jcl_access`), Q3 (`entry_program` + `reachable_programs` + `unresolved_reaches`), Q4 (`entry_program` + `mapsets` + `map_interactions` + `field_surface(count)`), and Q6 (`compare_q6`, line 351) — all wired and executed against the live kuzu db. Live run: `run_id gate3-fulltree-20260603T142240Z` (artifacts/gate3_mapa, 1863/1444), exit 0; the `[MATCH]`/`[DIFF]`/`[INCR]` lines for Q2/Q3/Q4/Q6 are emitted by these comparators.
- Validation strength: mechanical-deterministic *(the harness runs the comparators and the count is reproducible; the **gold it compares against** has mixed strength — Q1–Q4 hand-traced, Q6 cold-agent — captured separately by the GV-Q*-FROZEN and GV-Q6 claims)*
- Caveats: Q5 is not compared (illustration-only, not gold-asserted). The 3 known-incremental are Q2 `jcl_access` (job-level gold vs step-level extract), flagged `known_incremental=True` at gold_match.py:326-327. **NOTE: an in-tree doc (`artifacts/gate3/gate3_closure.md:89`) states "Q2–Q4 comparators are stubbed" — that text is STALE gate-3-era (schema 1.0.0); the comparators were wired since, as compare() shows. The stale line should be corrected (separate from this brief).**
- Testable form: `PYTHONPATH=src python -m carddemo_graph.gold_match artifacts/gate3_mapa/carddemo_graph.db gold/gold_set.md; echo $?` → "matched=37 diff=0 known-incremental=3 (across 40 field comparisons)", exit 0. The output's per-field `[MATCH]`/`[DIFF]`/`[INCR]` lines for Q2/Q3/Q4/Q6 confirm those comparators actually run (not Q1-only).

**[GV-GATE3-ENTITY-COUNT] Full-tree Gate-3 extraction (both variants) produced 1863-1864 entities and 1444-1445 edges on the 139-file CardDemo corpus. MAPA variant (1863/1444) is the default-path result as of 2026-06-03T142240Z; regex variant (1864/1445) differs by 1 entity/edge due to documented MAPA improvements.**
- Grounding: `artifacts/gate3_mapa/entities.json` (1863, schema 1.1.0, run_id …142240Z) + `edges.json` (1444); `artifacts/gate3_regex/{entities,edges}.json` (1864/1445); `RESUME.md:211-212`.
- Validation strength: mechanical-deterministic
- Caveats: Skeleton counts only; enrichments.json is empty in this POC. The −1/−1 delta is improvements net (copybook-origin CALL + regex false-positive drops), not a regression.
- Testable form: Load gate3_mapa entities.json (1863) and edges.json (1444).

**[GV-GATE3-SCHEMA-VERSION] Gate-3 extraction produces schema version 1.1.0.**
- Grounding: `artifacts/gate3_mapa/entities.json` header (schema_version 1.1.0); carddemo-graph-spec-v4.1 §Emission.
- Validation strength: mechanical-deterministic
- Caveats: Structural marker; the gold-set Q1-Q6 entries are written under schema 1.1.0.
- Testable form: Read entities.json header; confirm schema_version == '1.1.0'.

**[GV-MAPA-DEFAULT] COBOL parser selection is controlled by env flag CARDDEMO_COBOL_PARSER (mapa|regex, default mapa). The MAPA adapter is the default-path COBOL extractor as of 2026-06-01, blessed after Phase-2 proved full-corpus facts-parity and demonstrably more correct closure (copybook-origin reachability).**
- Grounding: `src/carddemo_graph/extract/parsers/registry.py:8-18` (_DEFAULT_COBOL_PARSER='mapa'); `RESUME.md:1-7, 58-79`.
- Validation strength: demonstrated-once
- Caveats: Default ≠ mandatory; the flag allows runtime selection. The decision is corpus-proven (N=1); generalization beyond CardDemo is not proven.
- Testable form: grep '_DEFAULT_COBOL_PARSER' registry.py; read 8-18. Set the flag to regex and run a pilot to verify the regex path still works.

**[GV-PARSER-PARITY] Full-corpus facts-parity between MAPA and regex is proven on 31 copybooks and program constructs across 8 test programs. Implemented rules in test_mapa_program_emission.py reach parity with zero unexpected only_regex deltas. Improvements: copybook-origin CALL (COACTUPC→CSUTLDTC via COPY) and regex false-positive drops (batch-I/O on SET MORE-RECORDS-TO-READ in COCRDLIC).**
- Grounding: `RESUME.md:58-105`; `tests/test_mapa_program_emission.py:96-100`; `tests/test_mapa_dataitem.py:45-79` (517/517 DataItems across 31 copybooks, 0 regressions, 3 improvements).
- Validation strength: demonstrated-once
- Caveats: Parity demonstrated on CardDemo (N=1). Corpus-unexercised rules (RUL-COBOL-009/010/012/013/015) are implemented but not exercised by the corpus.
- Testable form: `python3 -m pytest tests/test_mapa_program_emission.py::test_program_construct_parity -v | tail -20` — 8 PASSED, zero only_regex findings.

**[GV-CBSTM03A-CONTINUATION] CBSTM03A.CBL uses classic COBOL col-7 continuation lines (HTML literals continued via '-' in col 7). MAPA fail-loud-refuses on FoldAlignmentError; the adapter falls back to regex for this one program, producing byte-identical output with no information loss.**
- Grounding: `RESUME.md:46-56`; `tests/test_mapa_program_emission.py:140-154`; `corpus/carddemo/stripped/app/cbl/CBSTM03A.CBL` (col-7 continuation at 124-125).
- Validation strength: demonstrated-once
- Caveats: Continuation-folding proper is Phase-3 work. The single-program regex fallback keeps the pipeline whole. A documented boundary, not a deficiency.
- Testable form: Verify CBSTM03A.CBL exists (uppercase .CBL); inspect 124-125. Run test_continuation_program_falls_back_to_regex; verify FoldAlignmentError + byte-identical regex fallback.

**[GV-VENDOR-MAPA] MAPA is vendored at vendor/mapa/ as pristine upstream source (MIT license, commit 2ad7cd5) plus a standalone mapa_origin_tracker.patch and reproducible build.sh. The vendored copy includes MapaTreeDump.java (custom data-layer dumper) and generates CallTree.jar + MapaTreeDump.class on build.**
- Grounding: `RESUME.md:1-7, 58-65`; `vendor/mapa/` (build.sh, LICENSE, mapa_origin_tracker.patch, MapaTreeDump.java, plus built CallTree.jar, MapaTreeDump.class).
- Validation strength: demonstrated-once
- Caveats: Vendoring is a local snapshot; upstream changes are not auto-synced. The patch is minimal and upstream-offerable.
- Testable form: ls vendor/mapa/ for build.sh|LICENSE|mapa_origin_tracker.patch|MapaTreeDump; read build.sh to verify the ANTLR-gen + javac + jar steps.

**[GV-TEST-COUNT] The test suite contains 26 named test functions across 4 files: 8 DataItem-layer tests (test_mapa_dataitem.py), 1+8 program-emission tests (test_mapa_program_emission.py), 1+4 program-provenance tests (test_mapa_program_provenance.py), 14 structural-validator tests (test_structural_validator.py).**
- Grounding: grep count verified: 26 named test functions across the four test files.
- Validation strength: mechanical-deterministic
- Caveats: Source-code function counts (26). Parametrized tests expand at pytest runtime; actual case count is higher and depends on MAPA build availability.
- Testable form: `grep -r '^def test_' tests/ | wc -l` — 26. Run pytest with MAPA built for full parametrized expansion.

**[GV-GOLD-FREEZE-DISCIPLINE] The gold set was FROZEN 2026-05-13 with Reviewer A (engineer agent) and Reviewer B. Post-freeze changes are append-only via gold_set_changelog.md with amendment reason and diff summary. Every entry has a grep-verifiable line citation; naming-convention inferences without source verification are excluded.**
- Grounding: `gold/gold_set.md:1-10, 23-27`; `gold/gold_set_changelog.md` (6 post-freeze amendments: F5, Finding B, Finding D, Q6.1, Q6.2, Q3.2).
- Validation strength: hand-traced-gold
- Caveats: The freeze protocol prevents creep toward the extractor's output (over-fitting). **NOT every amendment carries a Reviewer-B sign-off line: the four structural amendments (F5, Finding B, Finding D, Q3.2) carry explicit Reviewer-B approval, but the two Q6 cold-agent entries (Q6.1, Q6.2) are orchestrator-recorded WITHOUT a separate Reviewer-B line** — consistent with their cold-agent-gold (agreement-not-proof) status. State "6 amendments, 4 with Reviewer-B approval", not a blanket "all Reviewer-B approved".
- Testable form: Read gold/gold_set.md:1-10; verify 'FROZEN 2026-05-13' and 'Reviewer B'. Read the changelog and count post-freeze amendment entries (6); verify the four structural ones name an approver and the two Q6 entries do not.

---

### Cluster: Downstream-Agent Trial (Gate 4)

**[G4-1] An agent given only the v1 packet (KB entities, edges, schema; no source code) produced two substantive deliverables: operations_manual.md (end-to-end mainframe topology) and modernization_strategy.md (mapping the COBOL/JCL/VSAM system to Java Spring Boot + PostgreSQL Aurora + AWS-native architecture).**
- Grounding: `artifacts/gate4/gate4_result.md:8`; `artifacts/gate4/operations_manual.md` (215 lines, §1-5: runtime topology, batch pipeline, functional clustering, failure surfaces, change-safety); `artifacts/gate4/modernization_strategy.md` (149 lines, §1-5: mainframe→target mapping, decomposition candidates, sequencing, non-translatable constructs, risk-ranked unknowns).
- Validation strength: demonstrated-once
- Caveats: N=1. Review was by the KB build orchestrator and the project sponsor, NOT an external independent party (gate4_result.md:6 explicitly flags this as orchestrator+sponsor review under a packet-only protocol, not third-party verification). Substantiveness measured by line count and section breadth; content-quality assertions would benefit from independent SME review.
- Testable form: Verify both files exist, are well-formed markdown, ≥100 lines each, with §-numbered sections as listed. Inspect gate4_result.md:8 for the 'packet alone' claim.

**[G4-2] The review found no fabricated program/dataset/transaction/map/job names in the agent's outputs — every structural name cited (e.g., CBEXPORT, TRANSACT.VSAM.KSDS, CM00) was verified to exist in the schema or appears as an explicit unresolved:* placeholder.**
- Grounding: `artifacts/gate4/gate4_result.md:10`; verification against the schema-1.0.0 snapshot (1347 entities / 926 edges / 18 transactions / 902 BMS fields).
- Validation strength: demonstrated-once
- Caveats: Orchestrator+sponsor review, not independent. Verified against the schema-1.0.0 snapshot, now superseded by the live graph. Applies only to the two outputs checked against the packet the agent received.
- Testable form: Extract all program/dataset/transaction/map/job names from both documents. For each, verify it appears in the schema-1.0.0 snapshot OR the known_unknowns.md unresolved:* list. Report any name in neither.

**[G4-3] The review verified that the manual and strategy correctly cited the known unknowns (gaps in known_unknowns.md §1-11), including DB2/IMS/MQ deferral (KU-1), dynamic XCTL navigation (KU-2), and field-level record layouts (KU-9).**
- Grounding: `artifacts/gate4/gate4_result.md:10`; operations_manual.md KU citations at lines 9/46/113/159/161/165/168/170/184/213; modernization_strategy.md KU citations at lines 5/18/19/20/28/29/48/90/92/121-126/149; each points to a real section in known_unknowns.md.
- Validation strength: demonstrated-once
- Caveats: Internal review. known_unknowns.md has been amended post-gate4 (line 113 marks KU-9 'UPDATED (v2.2): the field-level DataItem layer IS now extracted'). The agent received the v1.0.0 packet and correctly cited KU-9 as a then-gap; the live graph now includes it. The claim applies to what was unknown at gate4 time.
- Testable form: Read gate4_result.md:10. List all [KU-n] citations in both documents (≥ KU-1/2/3/5/6/8/9/11). Cross-check each against known_unknowns.md §1-§11. Report any citation with no corresponding section.

**[G4-4] The Gate-4 downstream-agent output was scored PASS / STRONG on 7 dimensions (grounding, coverage, unknown-handling, modernization usefulness, operational usefulness, hallucination control, reviewer judgment) by the build-orchestrator + sponsor under a packet-only protocol — an internal point-in-time judgment, NOT externally validated (rubric unpublished, review not independent). The 7 STRONG scores are an asserted internal assessment, not a demonstrated outcome.**
- Grounding: `artifacts/gate4/gate4_result.md:5, 9` record the asserted scores.
- Validation strength: asserted-unverified
- Caveats: Rubric definitions, dimension thresholds, and operational criteria are NOT in the repo. No independent review of rubric calibration, inter-rater reliability, or validity. 'Hallucination control' is subjective; no automated hallucination-checking harness exists. Must NOT be presented as a demonstrated/validated outcome.
- Testable form: Read gate4_result.md:5 and 9; confirm the scores are TEXTUALLY present (asserted). Confirm the rubric definitions / thresholds are NOT published anywhere in the repo (grep for them; absence means the scores cannot be independently validated).
- *(FLAGGED — asserted-unverified; internal unvalidated judgment; see §4.)*

**[G4-5] The Gate-4 trial was packet-only — the agent_packet/ it consumed contains no source files (db/json/markdown/schema only), which IS verifiable from the repo. The surrounding execution conditions (headless, no human intervention, isolated copy outside the repo, 2026-05-28) are asserted in the gate record but are NOT reproduced/audited; the target stack (Java 21 / Spring Boot / Spring Batch / PostgreSQL Aurora / AWS Step Functions / ECS Fargate / S3) was a framing assumption given to the agent, not KB-discovered.**
- Grounding: `artifacts/gate4/gate4_result.md:7` (asserted run conditions + stack); `artifacts/agent_packet/` directory listing (only carddemo_graph.db, entities/edges/enrichments.json, markdown/schema — no .cbl/.jcl/.bms) confirms packet-only.
- Validation strength: demonstrated-once *(packet-only is a verified fact; headless/no-human/isolated/date are asserted, not reproduced — no execution or audit log in the repo)*
- Caveats: 'headless', 'no human', 'outside the repo' have no independent audit log; treat as asserted run conditions. Only the packet-has-no-source property is repo-verifiable. The target stack is a given, not a discovery.
- Testable form: List agent_packet/ contents — confirm NO source files present (packet-only = verifiable fact). Confirm gate4_result.md:7 STATES date/mode/isolation/stack (asserted). Check both deliverables for any source line-number citations (absence consistent with packet-only derivation).

**[G4-6] The schema-1.0.0 snapshot against which Gate 4 was measured contained 1347 entities, 926 edges, 18 transactions, 902 BMS fields, now superseded by the live graph (v2.2: 1864/1445; MAPA default: 1863/1444) — a formal gate record frozen for audit.**
- Grounding: `artifacts/gate4/gate4_result.md:3, 10`; `artifacts/agent_packet/graph_summary.md:11-12` (1864/1445), `:29` (18 CICSTransaction), `:20` (902 BMSField).
- Validation strength: mechanical-deterministic
- Caveats: The v1.0.0 counts are historical (gate3-fulltree-2026-05-13, schema 1.0.0). The live graph has evolved; the difference is primarily KU-9 (DataItem layer, 517 new entities) and MAPA-default extraction (1863/1444). Both figure sets are asserted and verifiable.
- Testable form: Parse the live agent_packet entities/edges.json (1864/1445) vs graph_summary.md:11-12. Cross-check gate4_result.md:3, 10 for the v1.0.0 snapshot (1347/926/18/902). Confirm the MAPA-default count (1863/1444) in gate4_result.md:3.

**[G4-7] The Gate 4 review identified three top v1→v2 KB requirements (none gate-blocking): KU-9 field-level record layout (PIC/COMP-3/OCCURS/REDEFINES — top gap for Aurora DDL gen); KU-11 populate Program.straddle_score + Dataset.centrality (declared, null in v1); KU-2 dynamic XCTL navigation via Pass-2 MOVE-chain.**
- Grounding: `artifacts/gate4/gate4_result.md:12`; `known_unknowns.md` §2 (KU-2), §9 (KU-9, with 'UPDATED (v2.2)' note), §11 (KU-11); `graph_summary.md:35-49` (straddle_score + centrality now populated in v2.1).
- Validation strength: demonstrated-once
- Caveats: Reflects the agent's operational needs and the review's gate4-time assessment (2026-05-28, v1.0.0). KU-9 and KU-11 have since been partially/fully addressed in the live graph (DataItem layer = 517 entities; straddle_score + centrality now populated), confirming the gaps were real. The claim is specific to gate4-time unknowns.
- Testable form: Read gate4_result.md:12; extract KU-9/11/2. Cross-check each KU section in known_unknowns.md (§2/§9/§11). For KU-9 confirm the line-113 update note; for KU-11 confirm graph_summary.md:35-49 populated. Confirm none labeled 'gate-blocking'.

---

### Cluster: Honesty Discipline

**[HD-1] The gold set is frozen with every entry source-verifiable via explicit grep citations to the corpus, rejecting naming-convention inferences without direct source trace.**
- Grounding: `gold/gold_set_changelog.md:2-35`; `gold/gold_set.md:28-29` (discipline statement).
- Validation strength: mechanical-deterministic
- Caveats: Frozen 2026-05-13; post-freeze amendments (through 2026-06-01) are documented with written rationale; F5/B/D/Q3.2 are source-traced.
- Testable form: For each gold Qx.y entry: read the cited source line(s); verify it contains the claimed entity/operand; confirm no external inference. Run grep -n for COPY/CALL/dataset/map citations.

**[HD-2] Amended gold after freeze uses audit entries (gold_set_changelog.md) with written reason, never retrospectively rigged to match extractor output; the 2026-06-01 Q3.2 amendment corrected an incomplete freeze-time grep by adding copybook-expanded reachability.**
- Grounding: `gold/gold_set_changelog.md:144-160`; `gold/gold_set.md:485-495`.
- Validation strength: mechanical-deterministic
- Caveats: Reverses a 2026-05-13 freeze decision; explicitly source-verified (COACTUPC.cbl:3743 COPY CSUTLDPY, CSUTLDPY.cpy:255 CALL CSUTLDTC, CSUTLDTC.cbl:93 CALL CEEDAYS). Q3.3 deliberately unchanged (COTRN01C does NOT COPY CSUTLDPY).
- Testable form: grep COACTUPC.cbl for 'COPY CSUTLDPY' (3743); CSUTLDPY.cpy for "CALL 'CSUTLDTC'" (255); CSUTLDTC.cbl for 'CALL "CEEDAYS"' (93). Verify gold Q3.2 lists both CSUTLDTC and CEEDAYS.

**[HD-3] Content-validation is a hard structural invariant in provenance composition: every emitted construct's provenance line must content-match the original source or copybook, or emit fails loudly rather than silently mismapping.**
- Grounding: `program_provenance.py:1-29` (invariant), `:103-123` (resolve() with content-validation at 110-113, raising ProvenanceError); `tests/test_mapa_program_provenance.py:86-95`.
- Validation strength: mechanical-deterministic
- Caveats: Applies only to emitted constructs (CALL/EXEC CICS/SELECT), not every line. Copybook constructs match using _code_text (cols 8-72, stripped). ProvenanceError raised at lines 111-112.
- Testable form: Run `pytest tests/test_mapa_program_provenance.py::test_program_provenance_exact -xvs` (requires build.sh). Resolver runs on 4 programs; each construct's resolved line must include its verb. Any silent mismapping fails at line 94.

**[HD-4] Continuation-line folding (COBOL col-7 '-') is deferred to Phase-3; when a program requires it, the pipeline fail-loud-refuses and falls back to the regex extractor for that program only, keeping the pipeline whole.**
- Grounding: `RESUME.md:47-56`; `tests/test_mapa_program_emission.py:140-154`.
- Validation strength: demonstrated-once
- Caveats: Only CBSTM03A.CBL exercises this boundary. The test confirms fail-loud refusal and byte-identical regex fallback for that one program.
- Testable form: Run `pytest tests/test_mapa_program_emission.py::test_continuation_program_falls_back_to_regex -xvs`. Asserts FoldAlignmentError on CBSTM03A.CBL, then byte-parity between regex and MAPA observations.

**[HD-5] Unresolved identifier-form CALL/LINK/XCTL targets are explicitly placed in unresolved:* placeholders with breadcrumb attributes, never promoted to typed edges; this honors the skeleton/enrichment principle and prevents silent guessing.**
- Grounding: `known_unknowns.md:19-34` (§2, 21 unresolved edges → unresolved:<surface_form>); `gold/gold_set.md:485-491` (Q3.2 unresolved_reaches with CDEMO-TO-PROGRAM breadcrumb); `RESUME.md:191-193` (must_not_promote: True).
- Validation strength: mechanical-deterministic
- Caveats: 21 such edges (18 CDEMO-TO-PROGRAM, 2 CCARD-NEXT-PROG, 1 LIT-MENUPGM). Queryable but targets are not deductively knowable.
- Testable form: Read known_unknowns.md §2. Verify gold Q3.2/Q3.3 show unresolved_reaches with breadcrumb. Run gold_match to verify Q3 queries handle unresolved_reaches without promotion.

**[HD-6] Gold-set comparison is mechanically enforced by gold_match.py, which parses Q1-Q4 + Q6 expectations, runs the same query runners used in production (not re-implemented), diffs canonical projections, and exits nonzero on any real DIFF. It runs end-to-end against the live kuzu db.**
- Grounding: `src/carddemo_graph/gold_match.py:1-34` (docstring + `compare()` at 312-352, running Q1-Q4 + Q6), `:359-398` (main() reporting MATCH/DIFF/INCR, exits nonzero on real DIFF). Verified by live execution: kuzu 0.11.3 is installed and the harness ran end-to-end (37/0/3, exit 0 on the MAPA db; 36/1/3, exit 1 on the regex db).
- Validation strength: mechanical-deterministic
- Caveats: Enrichments are not compared (skeleton/enrichment split). jcl_access comparison is marked known_incremental (gold_match.py:326-327). (No kuzu-availability caveat — kuzu 0.11.3 is present and the harness executes fully.)
- Testable form: `PYTHONPATH=src python -m carddemo_graph.gold_match artifacts/gate3_mapa/carddemo_graph.db gold/gold_set.md; echo $?` → prints per-field MATCH/DIFF/INCR and exits 0. Run against the regex db → exits 1 (real Q3.2 DIFF). Both run live (kuzu installed).

**[HD-7] Cold-agent gold (Q6 field-level layouts for CVACT01Y and CVEXPORT) is explicitly labeled NOT human-expert gold; convergence with extraction is agreement, not proof, and a human COBOL expert would supersede it.**
- Grounding: `gold/gold_set.md:709` (gold-class header); `gold/gold_set_changelog.md:107-110` (Q6.1), `:125-129` (Q6.2: 'Convergence = agreement, not proof. A human COBOL expert would supersede.').
- Validation strength: cold-agent-gold
- Caveats: CVACT01Y is simple; CVEXPORT is hard (4 COMP-3, 7 COMP, 6 REDEFINES, 2 OCCURS). Convergence is not proof. Known latent boundary: suggested_sql_type is mechanical (USAGE-driven); a domain-aware read might type IDs differently.
- Testable form: Read gold/gold_set.md Q6.1/Q6.2 in full (707-750+). Verify honesty tags in headers and changelog. Read the hard-case facts in Q6.2.

**[HD-8] Phantom and partial-entity programs (17 total: COCRDSEC phantom, CEE* external utilities, NONEXEG deliberate missing-program, assembler stubs) are marked partial=true in the graph and remain queryable/traversable, preventing silent gaps in control-flow closure.**
- Grounding: `known_unknowns.md:37-46` (§3); `src/carddemo_graph/extract/observation.py:43-78` (Observation dataclass supports partial data).
- Validation strength: demonstrated-once
- Caveats: These entities have no internal-behavior analysis. The count (17) and list (COCRDSEC phantom, CEE utilities, NONEXEG, IDCAMS, SORT, IEBGENER, IEFBR14, SDSF, assembler stubs COBDATFT/MVSWAIT) are documented.
- Testable form: Read known_unknowns.md §3. Verify the 17 entities: 1 phantom (COCRDSEC), 7 external programs, 2 dynamic-XCTL (from §2), assembler stubs.

**[HD-9] The known-unknowns inventory (known_unknowns.md) explicitly documents 11 categories of deferred features, partial entities, and corpus-level edge absences, preventing false negatives from being misread as extractor correctness.**
- Grounding: `known_unknowns.md:1-135` (11 sections: deferred subapps; identifier-form targets; phantom/external; external copybooks; identifier-form BMS maps; JCL symbols; corpus edge absences; operational CICS verbs; out-of-scope constructs; Q2 jcl_access fine-grain; LLM enrichments).
- Validation strength: demonstrated-once
- Caveats: Each section documents specific implications. The 11-section structure is clearly delineated.
- Testable form: Read known_unknowns.md in full (135 lines). Verify 11 numbered sections (§1-§11); each gives a specific implication, not just 'out of scope'.

**[HD-10] Copybook-origin CALL discovery (COACTUPC→CSUTLDTC via CSUTLDPY procedure copybook) is explicitly documented as a three-way-diff improvement (regex never scans copybook bodies), surfacing the regex baseline's real under-counting when the corrected gold is applied.**
- Grounding: `RESUME.md:213-225`; `tests/test_mapa_program_provenance.py:98-103`.
- Validation strength: demonstrated-once
- Caveats: Specific to the MAPA parser. The CBSTM03A regex fallback means MAPA is not universally applied; this improvement applies only to MAPA-parsed programs.
- Testable form: Run `pytest tests/test_mapa_program_provenance.py::test_copybook_origin_call_is_attributed_to_copybook -xvs`. Verifies the CALL has provenance kind='copybook' and 'CSUTLDPY' in source_path.

**[HD-11] The skeleton/enrichment principle is enforced: Q1-Q4 answers assert only deductive composition (literal CALL/LINK/XCTL, direct COPY inclusion, BMS SEND/RECEIVE with literal operands), never MOVE-chain resolution or control-flow inference; enrichment targets are documented separately (e.g., Q4.2 map enrichment) for future Pass-2 eval.**
- Grounding: `gold/gold_set.md:76` (Q1.1 skeleton/enrichment note); `:583-595` (Q4.2 amended skeleton: field_surface=0 with enrichment target showing 52 INITIAL= clauses); `gold/gold_set_changelog.md:74-81`.
- Validation strength: mechanical-deterministic
- Caveats: The Q4.2 amendment (2026-05-28) changed the gold from enrichment-resolved (52 fields) to skeleton-only — an honest boundary acknowledgment, not a weakening. The enrichment target (52 fields) is retained (gold/gold_set.md:596-651) for future Pass-2.
- Testable form: Read gold/gold_set.md Q1.1:76 and Q4.2:583-595. Verify Q4.2 shows field_surface:0 and mapsets:[]. Read the enrichment-target section (596-651). Run gold_match Q4.2; verify field_surface matches skeleton 0, not enrichment 52.

---

### Cluster: Scope Boundaries

**[SB-1] The POC has been validated end-to-end on a single legacy mainframe application (AWS CardDemo) and cannot claim generalization to other mainframe systems.**
- Grounding: `RESUME.md:43`; `artifacts/gate3_mapa/entities.json` (run_id gate3-fulltree-20260603T142240Z).
- Validation strength: demonstrated-once
- Caveats: One system only; no second-codebase testing. Run_id confirms a single extraction run.
- Testable form: Inspect git log and the gate3_mapa run_id (single AWS CardDemo extraction); grep corpus/ for a single corpus root; confirm no secondary corpus runs.

**[SB-2] COBOL program CBSTM03A.CBL (HTML literals continued across col-7 lines) falls back to the regex extractor rather than MAPA, because continuation-line provenance folding is not yet implemented.**
- Grounding: `RESUME.md:45-56`; `adapter.py:35-43`.
- Validation strength: mechanical-deterministic
- Caveats: Only CBSTM03A.CBL has continuation lines; the boundary is documented but unexercised by any other file. Continuation-folding is Phase-3.
- Testable form: Run with CARDDEMO_COBOL_PARSER=mapa; inspect stderr for the CBSTM03A FoldAlignmentError fallback; verify the mapa-variant processes CBSTM03A via regex fallback.

**[SB-3] COPY-expanded program reachability was under-counted at gold-set freeze time (2026-05-13) because the closure was traced via grep on program bodies only, not copybook-expanded source. Q3.2 (CAUP) has been corrected post-freeze to reflect copybook-origin CALL reachability.**
- Grounding: `gold/gold_set_changelog.md:144-160`; `gold/gold_set.md:476-495`.
- Validation strength: hand-traced-gold
- Caveats: The under-count was a gold-set hand-tracing limitation, not an extractor bug. MAPA's automatic copybook expansion revealed the gap. Q3.3 (COTRN01C) independently verified unchanged (does NOT copy the procedure copybook).
- Testable form: Verify the 2026-06-01 changelog entry is signed off; grep COACTUPC.cbl:3743, CSUTLDPY.cpy:255, CSUTLDTC.cbl:93; verify CSUTLDTC and CEEDAYS appear as CAUP-reachable in gate3_mapa/entities.json.

**[SB-4] CICS SEND-MAP, RECEIVE-MAP, and RETURN-TRANSID operand extraction is performed at the keyword-parenthesis level (MAP(x)/MAPSET(y)/TRANSID(z)) inside grammar-delimited EXEC CICS…END-EXEC blocks, not via full CICS grammar parsing.**
- Grounding: `RESUME.md:172-181`; `adapter.py:35`.
- Validation strength: asserted-unverified
- Caveats: A documented boundary, not a measured gap. The block boundary is provided by MAPA; operand extraction inside relies on regex keyword-paren. Acceptable because major CICS verbs (LINK/XCTL/file-ops/TRANSID-start) ARE structured by CallTree, and MAPA was chosen because it parses inside EXEC CICS blocks.
- Testable form: Inspect map_program.py CICSOTHER handling; verify operands extracted from the grammar-delimited block text match source operand lines; cross-check against gold Q4.

**[SB-5] Identifier-form CALL/LINK/XCTL targets (target name stored in a variable, resolved via MOVE-chain) are NOT promoted to typed Program edges in the skeleton. They remain unresolved:* placeholders with breadcrumb metadata.**
- Grounding: `known_unknowns.md:19-33` (§2, '21 such edges exist'); `gold/gold_set.md:76`.
- Validation strength: mechanical-deterministic
- Caveats: 21 unresolved program-references (18 CDEMO-TO-PROGRAM, 2 CCARD-NEXT-PROG, 1 LIT-MENUPGM). A design decision (skeleton/enrichment), not a limitation. Resolving requires MOVE-chain (Pass-2) analysis.
- Testable form: Query entities.json for 'unresolved:' Program entities (3 distinct: CDEMO-TO-PROGRAM, CCARD-NEXT-PROG, LIT-MENUPGM). Verify they never appear as 'from' of CALLS/XCTLS_TO/LINKS_TO edges.

**[SB-6] The v1 schema includes field-level COBOL record-layout entities (DataItem, v2.2 KU-9) but does NOT include MAPS_TO_ITEM edges linking BMS fields to their backing symbolic-map data items.**
- Grounding: mechanically counted in `artifacts/gate3_mapa/entities.json` (type=='DataItem' → 517) and `artifacts/gate3_mapa/edges.json` (edge_type=='MAPS_TO_ITEM' → 0); `artifacts/agent_packet/known_unknowns.md` documents the deferral.
- Validation strength: mechanical-deterministic *(promoted from asserted-unverified — both counts are directly countable: DataItem=517, MAPS_TO_ITEM=0, verified)*
- Caveats: The DataItem layer is in the extraction (517 entities); only the cross-layer BMS-to-DataItem link (MAPS_TO_ITEM) is deferred (requires additional semantic resolution).
- Testable form: `python -c "import json; e=json.load(open('artifacts/gate3_mapa/entities.json'))['entities']; print(sum(x['type']=='DataItem' for x in e))"` → 517; same over edges.json for MAPS_TO_ITEM → 0.

**[SB-7] Deferred subapplications (app/app-authorization-ims-db2-mq/, app/app-transaction-type-db2/, app/app-vsam-mq/) containing DB2/IMS/MQ patterns are NOT extracted in v1; the KB does not model SQL, IMS segments, or MQ queues.**
- Grounding: `known_unknowns.md:7-15` (§1); `artifacts/kb_capabilities.md:109-112`.
- Validation strength: demonstrated-once
- Caveats: These directories are present in the corpus but deliberately excluded. A v1 analysis mentioning DB2/IMS/MQ cannot be KB-grounded.
- Testable form: Verify the three directories exist in corpus/; search entities.json for SQLTable/IMSDatabase/MQQueue entity types (count == 0 each).

**[SB-8] The MAPA parser is the DEFAULT COBOL extractor (CARDDEMO_COBOL_PARSER=mapa) as of the Phase-2 gate (2026-06-01), replacing the hand-tuned regex extractor. The regex path remains selectable for comparison.**
- Grounding: `registry.py:32`; `RESUME.md:207-211`.
- Validation strength: mechanical-deterministic
- Caveats: Phase-2 three-way diff proved MAPA at full-corpus facts-parity with regex (1863/1444 vs 1864/1445, the −1/−1 net improvements). Not mandatory — regex selectable via env flag.
- Testable form: Run gate3 with no flag set; verify default 'mapa' via registry.py. Run phase2_diff.py; verify regex and mapa differ by the documented improvements.

**[SB-9] No EXEC CICS LINK edges (LINKS_TO) exist in the extracted v1 KB — the LINKS_TO count is zero in scope. This is NOT because the corpus has no LINK: the deferred subapplication uses EXEC CICS LINK (e.g. COPAUS1C.cbl:218 `EXEC CICS LINK PROGRAM(WS-PGM-AUTH-FRAUD)`), but that subapp is out of v1 extraction scope per the DB2/IMS/MQ deferral.**
- Grounding: `artifacts/agent_packet/kb_capabilities.md` (LINKS_TO == 0 in scope); `corpus/carddemo/stripped/app/app-authorization-ims-db2-mq/cbl/COPAUS1C.cbl:218` (`EXEC CICS LINK PROGRAM(WS-PGM-AUTH-FRAUD)`), in the deferred subapp.
- Validation strength: mechanical-deterministic
- Caveats: Do NOT claim "CardDemo uses XCTL not LINK / the corpus has no LINK" — that is false (the deferred subapp has a real LINK). The honest statement is: zero LINKS_TO in the EXTRACTED v1 scope, because the one LINK-bearing program is in the deferred subapp. The schema retains LINKS_TO for portability.
- Testable form: `grep -rn 'EXEC CICS.*LINK' corpus/carddemo/stripped/app/` → finds the LINK in app-authorization-ims-db2-mq (deferred), and none in the in-scope tree. Query the in-scope edges.json for LINKS_TO (count 0).

**[SB-10] No EXEC CICS RETURN TRANSID edges (RETURNS_TO_TRANSID) exist in the KB. Every EXEC CICS RETURN in CardDemo returns without specifying a follow-up transaction id.**
- Grounding: `known_unknowns.md:89`; `artifacts/kb_capabilities.md:73` (RETURNS_TO_TRANSID == 0).
- Validation strength: mechanical-deterministic
- Caveats: A CardDemo design pattern, not an extractor limitation. Schema retains RETURNS_TO_TRANSID for portability.
- Testable form: Grep corpus *.cbl for 'EXEC CICS.*RETURN.*TRANSID' (count 0); query edges.json for RETURNS_TO_TRANSID (count 0).

**[SB-11] CICS operational verbs (HANDLE, ABEND, ASSIGN, INQUIRE, ASKTIME, FORMATTIME, WRITEQ, READQ, DELETEQ) are observed in source but emit no typed edges in v1 because no closed-vocabulary edge types cover them.**
- Grounding: `known_unknowns.md:95-104` (§8).
- Validation strength: asserted-unverified
- Caveats: Present in source but intentionally not modeled. Coverage would require new edge types and rules.
- Testable form: Grep corpus *.cbl for 'EXEC CICS.*HANDLE\|ABEND\|ASSIGN' (matches found); verify these sites produce no edges in edges.json.

**[SB-12] Intra-program control flow (COBOL paragraphs, sections, PERFORM/GO-TO) is NOT modeled in the v1 schema. Each program is treated as a single entity.**
- Grounding: mechanically counted in `artifacts/gate3_mapa/entities.json` — no entity has type 'Paragraph' or 'Section' (both counts 0; the entity-type vocabulary present is BMSField/DataItem/JCLStep/LogicalFile/Dataset/Program/Copybook/JCLJob); `artifacts/agent_packet/known_unknowns.md` documents the deferral.
- Validation strength: mechanical-deterministic *(promoted from asserted-unverified — Paragraph=0, Section=0 are directly countable, verified)*
- Caveats: A v1 design decision; intra-program flow analysis is deferred.
- Testable form: `python -c "import json; e=json.load(open('artifacts/gate3_mapa/entities.json'))['entities']; print(sum(x['type'] in ('Paragraph','Section') for x in e))"` → 0.

**[SB-13] The v1 KB contains exactly 1 JCL symbolic parameter that could not be fully resolved: &CNTLLIB in REPROC.prc, bound at job-use-site but not statically resolvable from the PROC body alone.**
- Grounding: `known_unknowns.md:74-80` (§6); `artifacts/kb_capabilities.md:35`.
- Validation strength: mechanical-deterministic
- Caveats: An honest boundary of static analysis without per-use-site parameter binding.
- Testable form: Search entities.json for an id containing '&CNTLLIB' with partial=true; verify no other dataset entity has a symbolic-parameter name (starting with &).

**[SB-14] Two IBM-supplied CICS copybooks (DFHAID, DFHBMSCA) are referenced by CardDemo but not present in the corpus. They are marked partial=true.**
- Grounding: `known_unknowns.md:50-57` (§4); `artifacts/kb_capabilities.md:29`.
- Validation strength: mechanical-deterministic
- Caveats: The KB knows these are included by 17 online COBOL programs each, but their content cannot be source-traced.
- Testable form: Search entities.json for copybook:DFHAID and copybook:DFHBMSCA (both partial=true); verify each has 17 INCLUDES edges in edges.json.

**[SB-15] The gold Q2.1-Q2.5 dataset-access entries define jcl_access at job-level granularity (which JCL jobs reference each dataset by DSN). Fine-grain per-step DD-name + DISP + inferred_access_mode is a Known Gate-3 Incremental, not included in the freeze.**
- Grounding: `gold/gold_set.md:3-6`; `gold/gold_set_changelog.md:32-33`; `known_unknowns.md:122-127` (§10).
- Validation strength: asserted-unverified
- Caveats: A reasonable, documented refinement, not a blocker. Current implementation returns per-step USES_DATASET with DD name and DISP on the edge.
- Testable form: Inspect gold Q2.1-Q2.5 jcl_access tables; verify job-level (jcl-job:X) not step-level; verify the changelog marks this Known Gate-3 Incremental.

**[SB-16] Q5 (cluster analysis by shared data access) produces candidate bounded-context clusters with straddle programs flagged, but is explicitly NOT gold-asserted. Q1-Q4 and Q6 are the deterministic gold-grounded acceptance queries.**
- Grounding: `gold/gold_set.md:701` ('illustration only, not gold-asserted'); `gold/gold_set_changelog.md:30`.
- Validation strength: asserted-unverified
- Caveats: Q5 is informational only; clustering results are candidate/illustrative, not ground truth.
- Testable form: Verify gold Q5 states 'illustration only, not gold-asserted'; verify gold_match.py does not run a Q5 comparison (only Q1-Q4, Q6).

**[SB-17] The 17 partial Program entities comprise: 3 unresolved identifier-form placeholders (CDEMO-TO-PROGRAM, CCARD-NEXT-PROG, LIT-MENUPGM) + 1 phantom (COCRDSEC, CSD-defined, no source body) + 13 other (external refs / system utilities / assembler stubs).**
- Grounding: `artifacts/kb_capabilities.md:28`; `known_unknowns.md:37-46` (§3).
- Validation strength: mechanical-deterministic
- Caveats: Partial programs remain queryable, traversable graph citizens carrying metadata (asm_stub, partial flags). *(Corrected from the draft's '15 dynamic-XCTL + 1 phantom + 1 external' grouping: the 3 unresolved placeholders account for 21 reference sites total — the per-entity composition is 3 unresolved + 1 phantom + 13 other.)*
- Testable form: Count Program entities with partial=true (== 17). Inspect ids for unresolved:*, program:COCRDSEC, program:NONEXEG, and external names matching known_unknowns.md §3.
- *(FLAGGED — strength_label_ok=false, survives_adversarial=false: draft grouping imprecise; corrected breakdown carried above. See §4.)*

**[SB-18] The v1 KB has zero LLM-candidate observations (Pass-2 enrichments). enrichments.json is empty; Pass-2 is deferred.**
- Grounding: `known_unknowns.md:130-134` (§11); `artifacts/kb_capabilities.md:18` ('LLM (Pass-2) candidates produced in v1 | 0').
- Validation strength: mechanical-deterministic
- Caveats: The architectural rails for Pass-2 are in place; enrichments can be added without schema changes.
- Testable form: Verify enrichments.json exists; inspect its 'enrichments' key (empty array []).

**[SB-19] BMS field identifiers using identifier-form operands (MAP(LIT-THISMAP) MAPSET(LIT-THISMAPSET)) rather than literal map names are represented as partial placeholder entities (bms-map:LIT-THISMAPSET/LIT-THISMAP, bms-map:CCARD-NEXT-MAPSET/CCARD-NEXT-MAP) in the skeleton. Resolution to actual map names requires MOVE-chain enrichment.**
- Grounding: `known_unknowns.md:61-70` (§5); `gold/gold_set.md:587`.
- Validation strength: hand-traced-gold
- Caveats: A skeleton/enrichment boundary decision, not an extractor limitation. The enrichment answer (COACTUP/COACTUPA maps + 52 field labels) is recorded as the enrichment target.
- Testable form: Verify gold Q4.2 lists placeholder bms-map entities and field_surface=0; verify the Finding B amendment documents the re-scoping; query entities.json for these partial bms-map entities.

**[SB-20] Q6 field-level DataItem gold (CVACT01Y, CVEXPORT) is validated against COLD-AGENT independent reads, not human COBOL expert review. Convergence between extraction and cold-agent read is agreement, not proof.**
- Grounding: `gold/gold_set_changelog.md:94-110` (Q6.1 honesty notes), `:112-131` (Q6.2 honesty notes).
- Validation strength: cold-agent-gold
- Caveats: High-confidence for simple (CVACT01Y: 14 items) and hard (CVEXPORT: all edge cases) copybooks. A human expert review would supersede if it contradicts.
- Testable form: Inspect the 2026-05-29 changelog entries for Q6.1 and Q6.2; verify both disclaim human-expert status and state convergence=agreement-not-proof; verify the gold_match comparison shows 0 DIFF on DataItem extraction.

---

## 3. Validation-Strength Ledger

| Validation strength | Count |
|---|---|
| mechanical-deterministic | 43 |
| demonstrated-once | 20 |
| hand-traced-gold | 13 |
| cold-agent-gold | 3 |
| asserted-unverified | 5 |
| **Total claims** | **84** |

This is the CORRECTED distribution after the independent test's 8 relabels, 2 under-claim withdrawals, and 2 optional promotions (applied below).

Relabels/moves applied (independent-test result + verified promotions):
- **G4-4** demonstrated-once → **asserted-unverified** (rubric unpublished, review not independent — internal judgment, not a demonstrated outcome).
- **G4-5** mechanical-deterministic → **demonstrated-once** (packet-only is verified fact; headless/no-human/isolated/date are asserted, not reproduced).
- **SUP-1** cold-agent-gold → **hand-traced-gold** (the Q3.2 amendment was grep + source inspection, not a cold-agent read; cold-agent gold is Q6 only).
- **GV-GOLD-MATCH-RESULT** demonstrated-once → **mechanical-deterministic** (false flag withdrawn: gold_match compare() runs Q1–Q4 + Q6 live; the "stubbed" citation was a stale doc).
- **HD-6** flag withdrawn, kept **mechanical-deterministic** (kuzu 0.11.3 installed; gold_match runs end-to-end live).
- **SB-6** and **SB-12** asserted-unverified → **mechanical-deterministic** (counts directly verified: DataItem=517, MAPS_TO_ITEM=0, Paragraph=Section=0).

Remaining **asserted-unverified (5):** GPF-11 (CICS operand content-validation NOT built), SB-4, SB-11, SB-15, SB-16.

---

## 4. FLAGGED — May Not Survive Adversarial Scrutiny

These are surfaced UP FRONT. A later independent test should treat them as the weak points of the spine.

**[GPF-11] CICS operand content-validation — asserted, NOT built.** The construct LINE is resolver-validated and fail-loud, and the block boundary + keyword-paren operand extraction ARE in place; but operand-level content-validation / fail-loud-on-ambiguity for SEND/RECEIVE-MAP/RETURN-TRANSID is **not implemented** (Phase-3). The `map_program.py` docstring (lines 19-22) OVERSTATES this as "content-validated and fail-loud" — inaccurate; cite the SB-4 boundary framing, never the docstring. Labeled **asserted-unverified**. Do not state operand-level CICS content-validation as a completed property. *(The docstring itself is being corrected in the repo.)*

**[GV-GOLD-MATCH-RESULT]** — *flag WITHDRAWN after ground-truth re-verification.* An earlier draft flagged this on the basis of `artifacts/gate3/gate3_closure.md:89` ("Q2–Q4 comparators stubbed"), but **that doc line is itself STALE (gate-3 era, schema 1.0.0)**. The current `src/carddemo_graph/gold_match.py:312-352` `compare()` runs Q1–Q4 **and** Q6 comparators against the live kuzu db — confirmed by reading the code and by the per-field `[MATCH]`/`[DIFF]`/`[INCR]` output. So the 37/0/3 IS a real automated mechanical comparison (Q1-only was the gate-3 state). Re-labeled **mechanical-deterministic** in §2. The stale gate3_closure.md:89 line is a separate in-tree doc correction.

**[G4-4] Gate 4 PASS / STRONG on 7 dimensions — asserted-unverified (relabeled from demonstrated-once).**
The scores are textually present in gate4_result.md:5,9, but the **rubric definitions, dimension thresholds, and justifications are NOT published in the repo**, and the review was by the build orchestrator + sponsor, NOT third-party-independent. The 7 STRONG are an internal point-in-time judgment, not a demonstrated/externally-validated outcome — do not present them as a demonstrated result.

**[HD-6]** — *flag WITHDRAWN.* The original draft flagged this as not-fully-executable without kuzu, but **kuzu 0.11.3 IS installed and gold_match runs end-to-end live** (verified: 37/0/3 exit-0 on the MAPA db, 36/1/3 exit-1 on the regex db). Re-labeled / kept **mechanical-deterministic** in §2 with the kuzu caveat removed. (One of two under-claims the test corrected; the other was GV-GOLD-MATCH-RESULT.)

**[SB-17] 17 partial Program entities composition** — *strength_label_ok = false; survives_adversarial = false (as originally drafted).*
The draft grouping ('15 dynamic-XCTL targets + 1 phantom + 1 external') is imprecise. The **corrected breakdown** (carried in the SB-17 claim above) is: **3 unresolved identifier-form placeholders + 1 phantom (COCRDSEC) + 13 other (external refs / system utilities / assembler stubs) = 17**, where the 3 unresolved placeholders together account for 21 reference sites. Use the corrected composition, not the '15 dynamic-XCTL' phrasing.

---

## 5. What We Deliberately Do NOT Claim

- **No generalization beyond CardDemo (N=1).** Only one legacy mainframe application has been proven end-to-end (SB-1). No second corpus was run; the generalization thesis (GPF-12) is demonstrated-once, not a guarantee.
- **No full COBOL continuation-line coverage.** CBSTM03A.CBL (col-7 continuation lines) falls back to the regex extractor; continuation-folding is deferred to Phase-3 (SB-2, PROV-6, PROV-10).
- **No full CICS grammar.** SEND/RECEIVE-MAP/RETURN-TRANSID operands are extracted by keyword-paren inside the grammar-delimited EXEC block, not by full CICS grammar parsing (SB-4, GPF-11).
- **No DB2/IMS/MQ.** The deferred subapplications are not extracted; the KB does not model SQL, IMS segments, or MQ queues (SB-7).
- **No assembler.** Assembler is not extracted; assembler stubs are partial entities only (GPF-14, HD-8).
- **No intra-program control flow.** COBOL paragraphs, sections, and PERFORM/GO-TO are not modeled; each program is a single entity (SB-12).
- **No MOVE-chain / dynamic-target resolution in the skeleton.** Identifier-form CALL/LINK/XCTL targets and identifier-form BMS maps remain unresolved:* placeholders; resolution is Pass-2 enrichment territory (SB-5, SB-19, HD-5).
- **No BMS-field → DataItem linking.** The DataItem layer exists, but MAPS_TO_ITEM edges (BMS field ↔ symbolic-map data item) are not emitted (SB-6).
- **No operational-CICS edges.** HANDLE/ABEND/ASSIGN/INQUIRE/queue verbs are observed but not modeled as typed edges (SB-11).
- **No LLM-candidate enrichments.** Pass-2 is empty; enrichments.json is an empty array by design (SB-18, EM-006).
- **Q5 is not gold-asserted.** Cluster analysis is illustrative only; Q1-Q4 and Q6 are the gold-grounded acceptance queries (SB-16).
- **Cold-agent Q6 gold is agreement, not proof.** Two-LLM convergence on field-level layouts is not human-expert validation (SB-20, HD-7, GV-Q6-COLD-AGENT-GOLD).
- **Gate-4 review is not third-party-independent.** It was conducted by the build orchestrator + sponsor under a packet-only protocol (G4-1, G4-4).