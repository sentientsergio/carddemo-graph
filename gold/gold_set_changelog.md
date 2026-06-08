# Gold-Set Changelog

Per spec §Validation §Gold-set construction protocol: "Gold set is frozen before full-tree extraction. Changes after freeze require a written reason."

---

## Initial freeze — 2026-05-13

**Status:** FROZEN

**Reviewer A:** engineer agent (`engineer - carddemo-graph`, session `cse_01UcHczjfDVZDmgaXMhr5cQL`).

**Reviewer B:** the project sponsor; an independent source-grep cross-check pass verified the citations.

**Sources of truth for each Qx entry:**
- Line citations derived directly via `grep` against `corpus/carddemo/stripped/app/`. The Gate-2 extractor's `entities.json`/`edges.json` were NOT consulted during the Reviewer-A trace, preserving independence per spec.
- An independent source-grep review pass corrected naming-convention-inferred entries from the initial submission. Corrections folded in the 2026-05-13 morning revision. Notable corrections:
  - Q2.1 USRSEC: COADM01C removed (declares the WS-USRSEC-FILE constant but never references it in any EXEC CICS verb).
  - Q3.2 CAUP and Q3.3 CT01: `reachable_programs` set to `[]`; sole successor is `unresolved:CDEMO-TO-PROGRAM` (identifier-form XCTL — MOVE-chain resolution is enrichment, not skeleton).
  - Q3.1 CC00: verified literal-form (PROGRAM('COADM01C') / PROGRAM('COMEN01C')), so closure populates as `[COADM01C, COMEN01C]`.

**What's frozen:**
- Q1 (copybook impact) — 5 entries, all `direct_includers` source-verified
- Q2 (dataset access) — 5 entries, online program_access source-verified site-by-site; jcl_access at job-level granularity
- Q3 (transaction closure) — 3 entries, all CALLs/LINKs/XCTLs source-checked, identifier-form correctly preserved as Unresolved
- Q4 (BMS map surface) — 3 entries, all INITIAL= clauses enumerated:
  - Q4.1 COSGN00.bms: 27 clauses
  - Q4.2 COACTUP.bms: 52 clauses
  - Q4.3 COMEN01.bms: 21 clauses
- Q5 (clustering) — illustrative snapshot only; not gold-asserted per spec

**Known Gate-3 incremental (not a blocker, will be folded during Gate-3 review):**
- Q2.1-Q2.5 `jcl_access` fine-grain: per-step DD names + DISP + inferred_access_mode. Current granularity is job-level (which JCL jobs reference each dataset by DSN). The per-step refinement is reasonable Gate-3-time work since the full-corpus run reveals the access pattern across all jobs and steps. Folded into a post-Gate-3 amendment to the gold set if Q2 acceptance test surfaces deltas that the refinement would close.

**Discipline enforced at freeze:** every gold-set entry has a grep-verifiable line citation. Inferences from naming convention without source verification are excluded. Per the project's skeleton-vs-enrichment principle: only deductive composition qualifies as skeleton answer.

---

## Append-only post-freeze changes

> **Approval-status note (honesty caveat).** There are **6** post-freeze amendments below: F5 (Q2.1), Finding B (Q4.2), Finding D (Q2.2), Q6.1, Q6.2, and Q3.2. The **four structural amendments** (F5, Finding B, Finding D, Q3.2) carry an explicit Reviewer-B sign-off line. The **two Q6 cold-agent entries** (Q6.1, Q6.2) are recorded WITHOUT a separate Reviewer-B approval line — consistent with their cold-agent-gold status (convergence is agreement, not proof; a human COBOL expert would supersede). So: "6 amendments, 4 with Reviewer-B sign-off", not "all Reviewer-B approved".

### 2026-05-13 — Q2.1 USRSEC jcl_access correction (F5 amendment)

**Author:** engineer agent (`engineer - carddemo-graph`)
**Approver:** the project sponsor
**Failure-mode classification:** `gold-set bug`

**Diff summary:**
- `gold/gold_set.md` Q2.1 USRSEC `jcl_access` table: REMOVE the `jcl-job:ESDSRRDS` row.
- Final expected: 1 job (DUSRSECJ.jcl) — the only JCL referencing `DSN=AWS.M2.CARDDEMO.USRSEC.VSAM.KSDS`.

**Rationale:**
Source-grep against `corpus/carddemo/stripped/app/jcl/*.{jcl,JCL}` confirms `ESDSRRDS.jcl` references `AWS.M2.CARDDEMO.USRSEC.VSAM.ESDS` and `AWS.M2.CARDDEMO.USRSEC.VSAM.RRDS` only — both are separate `Dataset` entities (entry-sequenced and relative-record VSAM organization variants), distinct from the KSDS that the CSD binds CICS file USRSEC to. The Reviewer-A inclusion of ESDSRRDS.jcl was naming-convention inference (the "USRSEC" token in the variant DSNs was misread as referring to the KSDS).

Gate-3 extractor produced 4 distinct `Dataset` entities for USRSEC variants:
- `dataset:AWS.M2.CARDDEMO.USRSEC.VSAM.KSDS` (the Q2.1 target)
- `dataset:AWS.M2.CARDDEMO.USRSEC.VSAM.ESDS`
- `dataset:AWS.M2.CARDDEMO.USRSEC.VSAM.RRDS`
- `dataset:AWS.M2.CARDDEMO.USRSEC.PS`

ESDSRRDS.jcl's USES_DATASET edges land on the ESDS and RRDS entities, not the KSDS.

**Scoping clarification (definitional addition from the source-grep review):**
Q2 `jcl_access` is defined as JCL `DD` allocations to the **exact-DSN** `Dataset` entity. Same-family-name-different-organization datasets (e.g., the ESDS/RRDS variants of USRSEC above) are SEPARATE Dataset entities and are NOT in scope for the gold answer of the KSDS-target query. CEMT and other dynamic CICS resource-management commands are also out of scope (operational, not allocation).

This clarification helps future review passes avoid the inference the initial source-grep pass missed: the USRSEC.* DSN family looks like a single thing to a human reader, but the schema distinguishes them by canonical DSN — and so must the gold-set entries.

**Sign-off:** authorized by the project sponsor, 2026-05-13.

### 2026-05-28 — Q4.2 CAUP map surface re-scoped to skeleton (Finding B)

**Author:** engineer agent (`engineer - carddemo-graph`)
**Approver:** the project sponsor (2026-05-28)
**Failure-mode classification:** `gold-set bug` (skeleton/enrichment boundary mis-scoping)

**Diff summary:**
- `gold/gold_set.md` Q4.2 Expected: `map_interactions` now lists the unresolved identifier-form placeholder maps (`bms-map:LIT-THISMAPSET/LIT-THISMAP`, `bms-map:CCARD-NEXT-MAPSET/CCARD-NEXT-MAP`); `mapsets` = `[]`; `field_surface` = 0.
- The prior resolved-map answer (`bms-mapset:COACTUP`, `bms-map:COACTUP/COACTUPA`, 52 INITIAL= clauses) is retained, relabeled as a **enrichment target** — not a skeleton assertion.

**Rationale:**
COACTUPC issues SEND/RECEIVE MAP via identifier-form operands (`MAP(LIT-THISMAP) MAPSET(LIT-THISMAPSET)`, plus a `CCARD-NEXT-MAP` MOVE target). Per the skeleton/enrichment principle (and Q1.1's own note), MOVE-chain resolution is enrichment and is never promoted to a typed skeleton edge. The mechanical comparator (gold_match Q2-Q4 wiring, 2026-05-28) showed the skeleton correctly returns the unresolved placeholders + field_surface=0, while the frozen gold asserted the enrichment-resolved answer — an over-assertion across the skeleton/enrichment boundary. The amendment makes the gold assert the skeleton answer and records the resolved answer as the enrichment target for the future Pass-2 eval.

### 2026-05-28 — Q2.2 ACCTDATA program_access completeness (Finding D)

**Author:** engineer agent (`engineer - carddemo-graph`)
**Approver:** the project sponsor (2026-05-28)
**Failure-mode classification:** `gold-set bug` (Reviewer-A omission)

**Diff summary:**
- `gold/gold_set.md` Q2.2 `program_access`: ADD two COACTUPC sites — `READ`/READS at verb_line 3470 (operand 3471) and `REWRITE`/UPDATES at verb_line 3609 (operand 3610). Final COACTUPC sites against ACCTDAT: 3 (3320 READ, 3470 READ, 3609 REWRITE).

**Rationale:**
COACTUPC references `LIT-ACCTFILENAME` (= 'ACCTDAT ') in three EXEC CICS file verbs — 3320 (DATASET, READ), 3470 (FILE, READ), 3609 (REWRITE) — source-confirmed. The initial freeze listed only the 3320 READ (Reviewer-A omission). It surfaced when the Finding A fix (two-line WS-constant resolver) made the extractor resolve COACTUPC's ACCTDAT binding and the comparator flagged 3470/3609 as present-in-extract / absent-in-gold. The corrected extractor is more complete than the gold here; the gold is brought up to the source.

### 2026-05-29 — Q6.1 CVACT01Y field-level layout (cold-agent gold, KU-9)

**Author:** cold agent (source-only independent read of the raw copybook — never the extractor's output)
**Orchestrated by:** the build orchestrator (a role; not human-expert review)
**Gold class:** COLD-AGENT gold — explicitly NOT human-expert gold.

**Diff summary:**
- Add `gold/gold_set.md` Q6.1: the 14-item field layout for `copybook:CVACT01Y` (ACCOUNT-RECORD), with per-elementary `suggested_sql_type`.
- Wire into Acceptance Test A: `gold_match.py` compares the KU-9 DataItem extraction for CVACT01Y against this gold (result: 0 DIFF — convergent).

**Rationale / provenance:**
A cold agent read CVACT01Y from first principles (source only) and asserted the layout independently of the extraction. It converged with the KU-9 DataItem extraction on all 14 items — every field/level and all **14** `suggested_sql_type`s identical (NUMERIC(12,2) money, NUMERIC(11) ACCT-ID, CHAR(10) dates, CHAR(178) FILLER — the FILLER IS typed and counted), byte-sum cross-checked to RECLN 300. (The harness reports Q6.1 `field_set` 14/14 and `sql_types(accepted)` 14/14 — use 14/14, not 13/13.)

**Honesty notes (verbatim, per root):**
- Convergence with the extraction = **agreement, not proof** (two LLMs on clean COBOL).
- CVACT01Y is a **SIMPLE** copybook (no edited / COMP-3 / OCCURS / REDEFINES) — this validates the **common case only**.
- A **human COBOL expert would supersede** this cold-agent gold.

### 2026-05-29 — Q6.2 CVEXPORT field-level layout (cold-agent gold, KU-9 hard copybook)

**Author:** cold agent (source-only independent read of the raw copybook)
**Orchestrated by:** the build orchestrator (a role; not human-expert review)
**Gold class:** COLD-AGENT gold — NOT human-expert gold.

**Diff summary:**
- Add `gold/gold_set.md` Q6.2: 72-item field layout for `copybook:CVEXPORT` (EXPORT-RECORD, RECLN 500), the HARD copybook (4 COMP-3, 7 COMP, 6 REDEFINES, 2 OCCURS).
- `gold_match.py`: parse_q6 + compare_q6 extended to honor the cold agent's type-cell notation — acceptable **sets** (`X (or Y/Z)`), `(skip)` (FILLER, excluded from the type compare), `(group)`. Result: Q6.2 field_set 67/67 + sql_types(accepted) 67/67, 0 DIFF (5 skip-FILLER excluded). Test A now 37 matched / 0 diff / 3 known-incremental.

**Rationale / provenance:**
A cold agent read CVEXPORT from first principles (source only) and asserted the layout independently. Root verified it converged with the KU-9 DataItem extraction on every hard case: all 4 COMP-3 → logical NUMERIC, all 7 COMP → INTEGER/BIGINT by digit count INCLUDING the binary-with-implied-decimal trap (EXP-ACCT-CURR-CYC-DEBIT S9(10)V99 COMP → NUMERIC(12,2), not integer), 6 REDEFINES, 2 OCCURS. Where the cold agent offered an acceptable set (e.g. EXP-ACCT-ID `BIGINT (or NUMERIC(11)/CHAR(11))`), the extraction's value (NUMERIC(11)) is within it — match is faithful to the gold's own offering, not cherry-picked.

**Honesty notes (verbatim, per root):**
- Cold-agent gold, orchestrator-recorded 2026-05-29; convergent-with-extraction on all hard cases (COMP-3 / COMP-implied-decimal / REDEFINES / OCCURS).
- Convergence = **agreement, not proof**.
- A **human COBOL expert would supersede**.
- This gold exercises the edge cases CVACT01Y (Q6.1) did not.

**Known latent policy boundary:** `suggested_sql_type` is a mechanical USAGE-driven rule; a domain-aware read might type some numeric IDs as NUMERIC/CHAR (leading zeros). Converged here. If a future copybook diverges on this, it is a **policy call (leaning: keep the mechanical skeleton rule; domain ID-typing is downstream enrichment), NOT an extractor bug.**

Format for future entries:
```
## YYYY-MM-DD — <reason>
**Author:** <name>
**Approver:** <name>
**Diff summary:** <bullet list of changes>
**Rationale:** <why the change is required>
```

---

## 2026-06-01 — Q3.2 reachable_programs: add CSUTLDTC + CEEDAYS (copybook-expanded reachability the freeze-time grep under-counted)

**Author:** engineer agent (`engineer - carddemo-graph`)
**Approver:** the project sponsor (ruling); surfaced from the grammar-parser Phase-2 three-way diff.

**Diff summary:**
- `gold/gold_set.md` Q3.2 (`transaction:CAUP`, entry `program:COACTUPC`): `reachable_programs: []` → `[program:CSUTLDTC, program:CEEDAYS]`. `unresolved_reaches` unchanged (CDEMO-TO-PROGRAM identifier-form XCTL retained). The top-of-file source-grep summary item 3 updated to match; item 4 (Q3.3) annotated as deliberately unchanged.

**Rationale:**
The 2026-05-13 freeze set Q3.2 `reachable_programs = []` on the basis of `grep "CALL +['\"]|EXEC CICS (LINK|XCTL)"` against **`cbl/COACTUPC.cbl` (the program body only)**, which correctly found no in-body literal CALL. But COBOL `COPY` splices copybook code into the program at compile time, and the grep did not expand copybooks. Independently source-traced (NOT MAPA-derived; the grammar parser merely surfaced the gap by expanding copybooks the regex extractor never scanned):
- `COACTUPC.cbl:3743` → `COPY CSUTLDPY`
- `CSUTLDPY.cpy:255` → `CALL 'CSUTLDTC'` (literal, resolved)
- `CSUTLDTC.cbl:93` → `CALL "CEEDAYS"` (literal, resolved)
So COACTUPC really does reach CSUTLDTC (via the copybook) and, transitively, CEEDAYS. This corrects an **incomplete gold to ground truth** — it is not gold rigged to the extractor; the citations stand on their own. **Q3.3 (COTRN01C) deliberately left unchanged** — verified COTRN01C does NOT `COPY CSUTLDPY`, so its `reachable_programs = []` remains correct. After this update, `gold_match` Q3.2 shows 0 diff / 0 extra.

**Honesty note:** this reverses a prior freeze-time "correction"; the reversal is itself source-verified and was ruled by the gold's Reviewer B (the project sponsor, accountable). The general lesson — gold reachability must be traced through COPY expansion, not program-body grep alone — applies to any future Q3 entry whose entry program copies a procedure copybook.
