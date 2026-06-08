# Gate 2 Closure — Golden-File Pilot Extraction

**Per spec v4 §Gate 2 + v4.1 (kuzu substrate).**

## What was run

Subset of 12 source files exercising every critical edge type the corpus supports, plus the anomalies catalogued in Gate 0:

| Path | Role |
|---|---|
| `app/cbl/COSGN00C.cbl` | Online sign-on program (XCTL, RETURN, SEND/RECEIVE MAP, CICS READ via WS constant) |
| `app/cbl/COACTUPC.cbl` | Online account-update program — heavy COPY, COPY REPLACING, multi-line PROGRAM-ID |
| `app/cbl/COCRDLIC.cbl` | Online card-list — STARTBR/READNEXT (browse pattern) |
| `app/cbl/CBTRN02C.cbl` | Batch transaction-processing — SELECT/ASSIGN/FD/01-record, batch I/O verbs |
| `app/cbl/CBTRN03C.cbl` | Batch transaction-report — CALL CSUTLDTC (literal CALL) |
| `app/cbl/CSUTLDTC.cbl` | Utility (date conversion) — referenced by CALL from other batch programs |
| `app/jcl/POSTTRAN.jcl` | Driver JCL with 6 DDs binding to multiple datasets |
| `app/jcl/TRANREPT.jcl` | Driver JCL with EXEC PROC=REPROC + step-prefix DD overrides |
| `app/proc/REPROC.prc` | Cataloged PROC — `//REPROC PROC` declaration |
| `app/proc/TRANREPT.prc` | Cataloged PROC — also declares `//REPROC PROC` (collision anomaly) |
| `app/bms/COSGN00.bms` | BMS mapset for sign-on screen — DFHMSD / DFHMDI / DFHMDF with continuations |
| `app/csd/CARDDEMO.CSD` | Authoritative CICS resource definitions — 18 transactions, 18 programs, 17 mapsets, 8 files |

## Counts

| Metric | Value |
|---|---:|
| Pass-1 observations | 399 |
| Entities (final) | 182 |
| - Programs | 28 (8 full from `.cbl` + 20 partial from CSD-only) |
| - Copybooks | 28 (5 full + 23 partial — referenced but body not in subset) |
| - JCLJobs / JCLProcs / JCLProcInvocations / JCLSteps | 2 / 1 / 2 / 8 |
| - LogicalFiles | 18 (12 batch via SELECT, 6 CICS via EXEC CICS file refs) |
| - Datasets | 20 |
| - BMSMapset / BMSMap / BMSField | 17 / 3 / 37 |
| - CICSTransactions | 18 |
| Edges (final) | 222 |
| Partial entities | 55 |
| Conflict-ledger entries | 1 |

## Edge-type coverage

Per spec §Gate 2: "subset contains at least one example of each critical edge type."

| Edge type | Count | Status |
|---|---:|---|
| INCLUDES | 86 | ✅ |
| EXPANDS_TO | 8 | ✅ (derived from JCLProcInvocation → JCLProc → JCLStep) |
| DEFINES_LAYOUT_FOR | 10 | ✅ (FD-record COPY) |
| CALLS | 3 | ✅ (all static literal) |
| LINKS_TO | 0 | **Corpus-level absence** — `EXEC CICS LINK` not used in CardDemo (Gate 0 anomaly #6) |
| XCTLS_TO | 6 | ✅ |
| RETURNS_TO_TRANSID | 0 | **Corpus-level absence** — all `EXEC CICS RETURN` in CardDemo are TRANSID-less |
| SENDS_MAP | 3 | ✅ |
| RECEIVES_MAP | 3 | ✅ |
| DECLARES_FILE | 12 | ✅ (batch SELECT/ASSIGN) |
| BINDS_TO | 1 | ✅ (USRSEC → AWS.M2.CARDDEMO.USRSEC.VSAM.KSDS via CSD) |
| READS | 21 | ✅ (batch + CICS read patterns) |
| WRITES | 4 | ✅ |
| UPDATES | 4 | ✅ (REWRITE + CICS REWRITE) |
| DELETES | 0 | **Corpus-level absence** — no DELETE statements in CardDemo |
| STARTS_BROWSE | 2 | ✅ (COCRDLIC STARTBR) |
| INVOKES | 6 | ✅ |
| USES_DATASET | 32 | ✅ |
| USES_PROC | 2 | ✅ |
| PASSES_SYSIN_TO | 1 | ✅ (REPROC's IDCAMS SYSIN → control-card dataset) |
| IS_TRANSACTION_FOR | 18 | ✅ |

**18 of 21 edge types observed.** The 3 absent edges (LINKS_TO, RETURNS_TO_TRANSID, DELETES) are confirmed corpus-level absences — every CardDemo `.cbl` file was scanned for these patterns and none exist. They are NOT extractor gaps; the schema retains them for portability per v1 design decisions.

## Validation results

### Structural invariants (per `src/carddemo_graph/validation/structural.py`)

```
entities.json:    0 errors, 0 warnings
edges.json:       0 errors, 0 warnings
observations.json: 0 errors, 0 warnings
```

10/10 negative-case tests pass (each invariant has a paired failing-case assertion in `tests/test_structural_validator.py`).

### Semantic coverage assertions (per `src/carddemo_graph/validation/semantic.py`)

```
[OK] transactions_have_entry_program       all 18 transactions have entry programs
[OK] bms_maps_have_visible_label           all 1 resolved maps have at least one visible field label
[WARN] datasets_have_organization           8 datasets without derivable organization
[WARN] datasets_have_binding_evidence       4 datasets without USES_DATASET or BINDS_TO edge in this subset
[OK] no_direct_program_dataset_edges       no direct Program → Dataset edges (RUL-NEG-002 holds)
[OK] no_llm_candidate_in_edges             no llm_candidate evidence in final edges
[OK] dynamic_calls_not_promoted_static     no dynamic CALL silently promoted to a typed Program target (RUL-NEG-001)
[OK] entity_ids_unique                     182 entities, all unique ids
[OK] edges_have_provenance                 all 222 edges have non-empty provenance
[OK] partial_entities_in_unresolved_report all 55 partial entities listed in unresolved report

pass=8 warn=2 fail=0
```

Both warnings are honest descriptions of subset limitations:
- 8 datasets without `organization`: GDG bases (`*.BKUP`, `*.DALY`) + PDS (LOADLIB) + plain PS (DATEPARM, TRANREPT, NULLFILE). The DSN suffix doesn't match VSAM/PS patterns. Could extend the derivation rule (RUL-DERIV-006) to handle GDG/PDS suffixes, but `where derivable` allows the gap.
- 4 datasets without binding evidence: CSD-only files in the subset (defined in CSD but no JCL job in our subset uses them).

### Conflict ledger

**1 entry** — the PROC-name collision anomaly from Gate 0:

```
canonical_id:    jcl-proc:REPROC
conflict_type:   proc_name_collision
rule_id:         RUL-RES-006
primary_source:  REPROC.prc          (filename matches declared name)
alt_source:      TRANREPT.prc        (filename mismatch flagged)
resolution:      Both retained as provenance on the entity; conflict-ledger entry written; downstream USES_PROC edges resolve to the canonical id.
```

This is a real anomaly that round-trips through the deterministic rules, the resolver, and the conflict ledger — not just a sample.

## Q1–Q4 sample results

Executable Cypher against the kuzu DB (`artifacts/gate2/carddemo_graph.db`).

### Q1 — Direct copybook impact for `copybook:CSUSR01Y`

```
direct_includers: 3
  - program:COACTUPC at line 556
  - program:COCRDLIC at line 223
  - program:COSGN00C at line 31
transactions: 3 (CAUP → COACTUPC, CC00 → COSGN00C, CCLI → COCRDLIC)
maps: 1 (bms-map:COSGN00/COSGN0A, sent by COSGN00C — partials filtered)
related_files: 0 (CSUSR01Y is a working-storage layout, not an FD record)
```

### Q2 — Dataset access for `dataset:AWS.M2.CARDDEMO.USRSEC.VSAM.KSDS`

```
program_access: 1
  - program:COSGN00C reads via logical-file:COSGN00C/USRSEC, dd_name=USRSEC, mode=READS, line 165
jcl_access: 0 (USRSEC not referenced in the JCL we extracted)
```

The BINDS_TO chain (CSD DEFINE FILE → DSNAME) round-trips correctly: COSGN00C's `EXEC CICS READ DATASET(WS-USRSEC-FILE)` resolves via WS-constant propagation (WS-USRSEC-FILE has `VALUE 'USRSEC'`), then BINDS_TO finds the CSD-defined USRSEC file's DSNAME.

### Q3 — Transaction closure for `transaction:CC00`

```
entry_program: program:COSGN00C
reachable_programs: 2 (program:COADM01C, program:COMEN01C)
unresolved_reaches: 0 (no dynamic CALLs in subset)
```

Both reachable programs are partial (not in subset). The transitive closure via XCTLS_TO still works — partial entities are full citizens in the graph.

### Q4 — BMS map surface for `transaction:CC00`

```
entry_program: program:COSGN00C
map_interactions: 2 (COSGN00/COSGN0A SENDS_MAP + RECEIVES_MAP)
mapsets: 1 (COSGN00)
field_surface: 27 visible labels (Tran :, Date :, Prog :, User ID :, Password :, etc.)
```

## Exit criteria check

Per spec §Gate 2 "exit when":

| Criterion | Evidence |
|---|---|
| Subset contains at least one example of each critical edge type | 18/21 covered; 3 absent are corpus-level (confirmed via grep) |
| Unresolved report reviewed | 55 partial entities listed in `unresolved_report.md`, grouped by reason |
| Gold-set candidates validated | **Pending** — gold-set trace is Task 4, runs next in tonight's plan |
| Deterministic rules adjusted before full-tree run | Two rule refinements made during Gate 2: (a) added WS-constant propagation for CICS DATASET/FILE operand identifier-form (without this, no online file edges resolve); (b) added string-literal stripping to batch I/O regex (prevents `DISPLAY 'START OF...'` from false-matching the COBOL START verb) |

**Gate 2 exits with caveats:**
- 3 of 4 exit conditions met
- 4th condition (gold-set validation) blocked on Task 4 — proceeding to that now
- Hard stop at Gate 2 completion per the project's directive: **Gate 3 (full-tree extraction) does not start tonight.** Awaits sponsor AT review + gold-set freeze.

## Rule refinements during Gate 2

Pilot interpretation surfaced these adjustments to the deterministic-rule inventory; `deterministic_rules.md` text remains authoritative but the code now also implements:

1. **WS-constant propagation for CICS operands** — `EXEC CICS READ DATASET(WS-FOO)` resolves to the literal `'FOO  '` value via a working-storage `VALUE` clause lookup. Narrow form only: `<level> <name> PIC X(N) VALUE '<literal>'.` inside WORKING-STORAGE SECTION. No MOVE-target tracking, no nested IF. Anything beyond this falls to Pass 2 (with an `operand_kind=ws_unresolved` flag).

2. **String-literal stripping in batch I/O matching** — `_strip_string_literals` replaces COBOL single/double-quoted strings with placeholder space before applying the batch I/O regexes. Prevents `DISPLAY 'START OF EXECUTION ...'` from matching as a `START <name>` browse-positioning statement.

3. **EXPANDS_TO derivation** — added to Pass 3 (RUL-JCL-PROC-004 implementation). At each `JCLProcInvocation`, walk to the invoked `JCLProc` and emit `EXPANDS_TO` for every step in the proc body. CardDemo only has 2 PROC invocations (REPROC called from 3 jobs, only 1 in subset), but the rule is general.

4. **PASSES_SYSIN_TO emission** — when DD name is SYSIN AND the step has a tracked PGM=, emit PASSES_SYSIN_TO in addition to USES_DATASET with `utility=<PGM>`.

5. **Partial entities propagate to unresolved_records uniformly** — Pass 3 now walks all entities at end of resolution and ensures every `partial: true` entity has a matching `unresolved_records` entry. This was needed to make the `partial_entities_in_unresolved_report` semantic-coverage assertion pass.

## What's owed at AT review (Reviewer B (sponsor))

1. **Confirm rule refinements** — particularly WS-constant propagation (RUL-COBOL-018 with operand-kind handling) and string-literal stripping. These are narrow constant-propagation choices that improve recall on CardDemo's online files. Worth sign-off.
2. **Confirm corpus-level absences** — LINKS_TO, RETURNS_TO_TRANSID, DELETES are zero in CardDemo. Do you accept this as the v1 reality, or should I instrument a "looked-for-but-not-found" record per anomaly to make the absence explicit in Q3/Q2 outputs?
3. **Conflict ledger resolution policy** — for the REPROC PROC collision, the current behavior creates ONE entity with merged provenance and lets downstream `USES_PROC` edges all point to it. An alternative is to keep both observed source instances as candidates and refuse to materialize an edge until human review. Which is preferred?
4. **Partial-entity strategy** — currently typed-but-`partial:true` entities are first-class graph citizens (queryable, traversable). Per spec they are "Unresolved placeholders." This works well for Q3 transitive closure (you get a meaningful "reachable but body unknown" answer). Confirm.

## Files produced (under `artifacts/gate2/`)

- `entities.json` — 182 entities, full provenance, structurally validated
- `edges.json` — 222 edges, full provenance, structurally validated
- `observations.json` — 399 Pass-1 observations, the pre-resolution audit trail
- `enrichments.json` — **empty in v1** (architectural commitment to skeleton/enrichment split per the project's principle; Pass-2 promotion populates this artifact later). Validated by the structural validator.
- `carddemo_graph.db` — kuzu graph database (executable substrate per v4.1; includes `Enrichment` node table that's currently empty)
- `resolution_report.md` — merge decisions + conflict ledger
- `unresolved_report.md` — 55 partial entities grouped by reason
- `constructs_not_modeled.md` — closed-vocabulary gaps + needs-ext deferrals
- `query_samples.json` — Q1-Q4 executed against the kuzu DB
- `q1_sample_result.json` — Q1 alone, for quick inspection

## Post-AT-review revisions (2026-05-13 morning)

Following the sponsor's AT review:
- All 5 pilot-rule refinements accepted; corpus-level absence policy accepted; PROC-collision merge policy accepted; partial-entity strategy confirmed.
- **`inferred_purpose` (and any other LLM-inferred properties) reclassified out of skeleton** per the project's principle "skeleton must be provenanced ground truth; LLM-judgment is enrichment." Schema now has a separate `enrichments.json` artifact (empty in v1) plus an `Enrichment` node table in kuzu for forward compatibility. RUL-DERIV-004 and RUL-DERIV-007 are RETIRED from the skeleton rule inventory.
- **RUL-DERIV-006 extended** with GDG_BASE / PDS / UNKNOWN_SENTINEL / fallback-PS classifiers. Gate-2 datasets without organization: 8 → 0.
- **Gold candidates revised** for Q2.1 (USRSEC corrections — COADM01C removed; COUSR0xC verbs corrected), Q2.2-Q2.5 (source-grep verified from scratch), Q3.2/Q3.3 (corrected to `unresolved:CDEMO-TO-PROGRAM`), Q3.1 (verified literal-form: COSGN00C → COADM01C, COMEN01C), Q4.2 (all 52 INITIAL= clauses enumerated).

Validation state after revisions:
- Structural: 0 errors across entities/edges/observations/enrichments
- Semantic coverage: 9 PASS + 1 WARN (Gate-2 subset limit, will close at Gate 3)
- Negative-case tests: 14/14 pass (added 4 for enrichments)
- Q1-Q4 sample queries: all return correct results

## Reproducibility

```
.venv/bin/python -m carddemo_graph.pilot
```

Deterministic: same inputs + extractor version produce identical entities/edges by canonical-id (verified — `corpus_hash: 13564b68efa4e366708b72238477cde2fd2d7c1dfa38aded3aadda92e60a7fb6` stable across runs).

---

**Reviewer-B (AT) review owed.** Engineer-authored Reviewer-A only.
**Gate 3 NOT started** — awaits the sponsor's AT pass on Gate 2 + gold-set freeze per the project's "hard stop at Gate 2" directive.
