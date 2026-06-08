# Negative Gold-Set CANDIDATES — Reviewer-A traces

> **STATUS: PENDING B-REVIEW.** Authored by engineer agent as Reviewer A only.
> Per spec §Validation §Negative gold-set tests: enumerated "must not infer" cases.

Per spec, negative tests assert that the resolver does NOT produce certain edges/entities, even though shallow regex matches might suggest otherwise. Each negative case below has a guarding rule_id (RUL-NEG-*) and verifiable corpus evidence.

## NG.1 — Dynamic CALL must not appear as static reachable program

**rule:** `RUL-NEG-001` (negation of RUL-COBOL-012)

**assertion:** For any program X with `CALL <identifier>` where `<identifier>` is not a literal, the resolver MUST NOT produce a `CALLS` edge to a typed `Program` entity. The edge target must be an `unresolved:<identifier>` placeholder (or marked `kind: dynamic` with `to.id` starting with `unresolved:`).

**CardDemo evidence (corpus-level absence):** Direct grep `CALL <identifier>` across `app/cbl/*.cbl` returns no occurrences in the v1 corpus. The negation rule is therefore *vacuously* satisfied in CardDemo. The negation MUST still hold if a future corpus introduces dynamic CALLs.

(Pass-2 work item: COCALL01.cbl is named suggestively; if it ever contains a dynamic call pattern, the resolver must not promote.)

## NG.2 — No direct Program → Dataset edge

**rule:** `RUL-NEG-002`

**assertion:** The edge vocabulary contains no edge type that connects `Program` to `Dataset` directly. Every Program-Dataset relationship is mediated by:
- batch: Program → DECLARES_FILE → LogicalFile → BINDS_TO → Dataset (via JCL DD)
- online: Program → READS/WRITES/etc. → LogicalFile → BINDS_TO → Dataset (via CSD FILE)

**Test:** in `edges.json`, there is no edge with `from.type == 'Program'` and `to.type == 'Dataset'`. Enforced both structurally (no such edge type defined) and as a semantic-coverage invariant (`no_direct_program_dataset_edges`).

**Gate-2 evidence:** Gate-2 semantic coverage check passes — 0 violations across 222 edges.

## NG.3 — Comment-only references must not create entities

**rule:** `RUL-NEG-007`

**assertion:** A reference inside an original-source comment line that was removed by the strip pipeline MUST NOT result in an entity or edge in the extracted graph.

**CardDemo evidence:** The strip pipeline removes COBOL comment lines (column 7 = `*`). The deterministic-extractor operates on the stripped corpus only. Source-level audit: pick any program-name X that appears ONLY in a comment in `corpus/carddemo/source/.../X` and confirm X is absent from `entities.json`.

**Recommended specific case:** Reviewer-B picks a candidate from the comment-bearing source (e.g., a name in a `* CALLED FROM: PROG_X` style comment in `app/cbl/COACTUPC.cbl` that doesn't actually appear in code).

## NG.4 — Similar DD names in different jobs must not be merged

**rule:** `RUL-NEG-004`

**assertion:** `DD <NAME>` allocations in different JCL jobs are distinct `USES_DATASET` edges, never merged into a single edge or shared LogicalFile entity.

**CardDemo evidence:** The DD name `TRANFILE` appears in multiple jobs (POSTTRAN.jcl, TRANREPT.jcl, TRANBKP.jcl). Each must produce its own `USES_DATASET` edge from the owning `jcl-step:<JOB>/<STEP>`.

**Gate-2 evidence:** Gate-2 produced separate `jcl-step:POSTTRAN/STEP15 -[USES_DATASET (dd=TRANFILE)]-> dataset:AWS.M2.CARDDEMO.TRANSACT.VSAM.KSDS` and `jcl-step:TRANREPT/STEP10R -[USES_DATASET (dd=TRANFILE)]-> dataset:AWS.M2.CARDDEMO.TRANSACT.DALY` (different generations of TRANSACT). No merge.

## NG.5 — Filename must not override `PROGRAM-ID`

**rule:** `RUL-NEG-005` (negation of RUL-RES-005)

**assertion:** When a COBOL file's `PROGRAM-ID` differs from its filename stem, the canonical `Program` entity ID uses the PROGRAM-ID, not the filename.

**CardDemo evidence:** All 33 `.cbl/.CBL` files in CardDemo have PROGRAM-ID == filename stem (no mismatches observed at Gate 0). The negation is *vacuously* satisfied; the rule must still hold if a future corpus has a mismatch.

**Tested by extractor's `filename_match` property:** RUL-COBOL-001 records `filename_match: true|false`; Gate-2 shows all 8 COBOL-sourced Program entities with `filename_match: true`.

## NG.6 — COPY outside FD record area must not produce `DEFINES_LAYOUT_FOR`

**rule:** `RUL-NEG-006`

**assertion:** A `COPY <name>` statement in `WORKING-STORAGE SECTION` or `LINKAGE SECTION` (or anywhere outside an FD record area in `FILE SECTION`) MUST NOT emit a `DEFINES_LAYOUT_FOR` edge.

**CardDemo evidence:** Of 86 `INCLUDES` edges in Gate-2 output, only 10 are in FD context (verified by independent FD-context scanner I ran during gold-set tracing). Specifically:
- `COPY CVACT01Y` in `CBACT01C.cbl:61` is in **WORKING-STORAGE** (no DEFINES_LAYOUT_FOR — Gate 2 confirms)
- `COPY CVACT01Y` in `CBEXPORT.cbl:50` is in **FD ACCOUNT-INPUT** (DEFINES_LAYOUT_FOR present — Gate 2 confirms)
- Same copybook, different section context, different edge production — the rule correctly distinguishes.

**Test for Reviewer-B:** Pick `copybook:CVACT01Y` and verify `entities.json` has DEFINES_LAYOUT_FOR only for the 2 FD-context sites (CBEXPORT/ACCOUNT-INPUT, CBIMPORT/ACCOUNT-OUTPUT), not for the 9 working-storage sites.

## NG.7 — Strip-pipeline marker files must not produce entities

**rule:** `RUL-NEG-003`

**assertion:** Files in `corpus/carddemo/stripped/scripts/markers/` (52 zero-byte sentinel files left by the strip pipeline) MUST NOT be inputs to the extractor and MUST NOT produce entities.

**CardDemo evidence:** Files like `scripts/markers/CBACT01C` exist but contain zero bytes. The extractor's input list excludes everything under `scripts/`. Gate-2 confirmed via inspection.

## NG.8 — `COPY ... REPLACING` outside FD context still produces `INCLUDES`, never `DEFINES_LAYOUT_FOR`

**rule:** `RUL-NEG-006` corollary

**assertion:** Even when `COPY <name> REPLACING ... BY ...` adds substitution, the placement-based rule still applies: working-storage REPLACING-COPY produces INCLUDES with `replacing_terms` attribute but NOT DEFINES_LAYOUT_FOR.

**CardDemo evidence:** `COACTUPC.cbl` issues `COPY CSSETATY REPLACING` 10+ times in WORKING-STORAGE SECTION (lines 2881, 2886, 2891, 2896, 2901, ...). Each produces an `INCLUDES` edge with `replacing_terms` populated; none produce `DEFINES_LAYOUT_FOR`.

**Gate-2 evidence:** Gate-2 reports `RUL-COBOL-003 INCLUDES x39` for COACTUPC alone, all with `replacing_terms` arrays and `fd_context: false`.

## NG.9 — PROC-name collision: edge candidates do not silently pick a "winner"

**rule:** `RUL-NEG` corollary to RUL-RES-006

**assertion:** When two source files declare the same PROC canonical id (`//REPROC PROC` in both REPROC.prc and TRANREPT.prc), the resolver MUST NOT silently pick one source and discard the other. Both must appear as provenance on the merged entity, the conflict must be recorded in `resolution_report.md`'s conflict ledger.

**CardDemo evidence (real anomaly):** Verified in Gate-2 output — `jcl-proc:REPROC` has 2 provenance items (one from `app/proc/REPROC.prc`, one from `app/proc/TRANREPT.prc`); 1 conflict ledger entry written; `filename_mismatch: true` flagged on the TRANREPT.prc-sourced candidate.

## NG.10 — Phantom CSD program does not silently become a full Program

**rule:** `RUL-NEG` corollary to RUL-CSD-002

**assertion:** When `DEFINE PROGRAM(X)` exists in CSD but no `.cbl`/`.asm` source body exists, the resulting `Program` entity MUST be marked `partial: true` and listed in `unresolved_report.md`.

**CardDemo evidence:** `COCRDSEC` is in `CARDDEMO.CSD:211` (DEFINE PROGRAM) and `:390` (transaction:CDV1 binds to it) but no `app/cbl/COCRDSEC.cbl` exists.

**Gate-2 evidence:** `program:COCRDSEC` has `partial: true`, `partial_reason: 'csd_only_no_source_body'`, and appears in `unresolved_report.md`. The transaction binding `transaction:CDV1 -[IS_TRANSACTION_FOR]-> program:COCRDSEC` is still present — the phantom isn't dropped, just flagged.

## NG.11 — Unresolved symbolic parameters in DSN do not silently disappear

**rule:** `RUL-NEG` corollary to RUL-JCL-004 / RUL-JCL-009

**assertion:** When a JCL DSN contains an unresolved `&PARM`, the resulting `Dataset` entity MUST be marked `partial: true` with the original surface form preserved in `unresolved_tokens`.

**CardDemo evidence:** REPROC.prc line 8 has `DSN=&CNTLLIB(REPROCT)` (`&CNTLLIB` is a PROC parameter substituted by use-sites).

**Gate-2 evidence:** `dataset:&CNTLLIB` (or normalized form with unresolved tokens) appears in `entities.json` with `partial: true` and is listed in `unresolved_report.md` under `partial_entity` reason.

---

**Reviewer-B should pick at least 3-4 of these and verify against `entities.json` / `edges.json` directly.**
