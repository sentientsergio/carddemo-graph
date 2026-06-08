# Known Unknowns

What this KB explicitly does NOT know. **Flag these in your analysis rather than guessing.**

---

## 1. Deferred features (entire subapps not extracted)

The upstream CardDemo source contains three "deferred subapp" directories that demonstrate DB2 / IMS / MQ integration patterns. These are **out of v1 scope** per spec §Deferred extensions and were NOT processed by the extractor:

- `app/app-authorization-ims-db2-mq/` — IMS DB + DB2 + MQ
- `app/app-transaction-type-db2/` — DB2
- `app/app-vsam-mq/` — VSAM + MQ

**Implication for modernization analysis:** the v1 KB does not characterize the DB2 schema, the IMS database structure, or any MQ message flow. If your analysis touches these areas, label your claims as "out of scope for v1 KB" rather than inferring from the file names.

---

## 2. Identifier-form CALL/LINK/XCTL targets (MOVE-chain navigation)

Online CardDemo programs navigate via a `MOVE <target> TO WS-NEXT-PROGRAM` → `EXEC CICS XCTL PROGRAM(WS-NEXT-PROGRAM)` idiom. Per the skeleton/enrichment principle (deductive composition only in skeleton), the deterministic extractor does NOT promote identifier-form XCTL/LINK/CALL operands to typed Program edges.

**21 such edges exist in the KB**, all routed to `unresolved:<surface_form>`:

```
unresolved:CDEMO-TO-PROGRAM    — 18 sites (universal — most online programs)
unresolved:CCARD-NEXT-PROG     —  2 sites (card-detail next-program)
unresolved:LIT-MENUPGM         —  1 site
```

Each carries `call_kind: dynamic` and `breadcrumb: <identifier>` attributes. Resolution requires control-flow / MOVE-chain analysis (Pass-2 LLM territory).

**Implication:** Q3 transaction-closure answers will list typed reachable programs separately from `unresolved_reaches`. The "functional next-program graph" of online CardDemo is incomplete in v1 — the skeleton shows where the navigation happens, but not where each MOVE-chain actually goes.

---

## 3. Phantom and external programs (partial entities)

17 Program entities are marked `partial: true`:

- **Phantom:** `program:COCRDSEC` — defined in CSD `DEFINE PROGRAM(COCRDSEC)`, bound to transaction CDV1 (developer transaction), but no source body in the corpus. This is a developer tool deliberately excluded from the public CardDemo distribution.
- **External-program references:** `program:CEE3ABD` (LE runtime abend handler), `program:NONEXEG` (deliberate "missing program" used in test paths), `program:CEEDAYS` (LE runtime date utility), and a handful of system utilities invoked from JCL: `program:IDCAMS`, `program:SORT`, `program:IEBGENER`, `program:IEFBR14`, `program:SDSF`.
- **Dynamic-XCTL targets:** the 3 unresolved CDEMO-TO-PROGRAM / CCARD-NEXT-PROG / LIT-MENUPGM identifiers (see §2).
- **Assembler stubs:** `program:COBDATFT`, `program:MVSWAIT` — CSECT names recognized by extractor as Program (asm_stub=true) but no body analysis.

**Implication:** these are still queryable, traversable graph citizens (so Q3 closure works correctly when control passes through them), but no further internal-behavior analysis is possible from the KB alone.

---

## 4. External copybooks (IBM-supplied, not in corpus)

2 Copybook entities are `partial: true` because they're IBM CICS-supplied copybooks not present in the CardDemo source:

- `copybook:DFHAID` — CICS Attention Identifier constants (PF-key codes etc.)
- `copybook:DFHBMSCA` — CICS basic-mapping-support attribute constants

These are referenced by every online COBOL program (17 INCLUDES edges each). The KB knows they're included; their content is by definition not source-traceable.

---

## 5. Identifier-form BMS map operands

2 BMSMap entities are `partial: true` because some online programs use identifier-form `MAP(LIT-THISMAP) MAPSET(LIT-THISMAPSET)` operands rather than literal map names:

- `bms-map:LIT-THISMAPSET/LIT-THISMAP`
- `bms-map:CCARD-NEXT-MAPSET/CCARD-NEXT-MAP`

The corresponding `SENDS_MAP` / `RECEIVES_MAP` edges land on these partial placeholders. Resolution to the actual map names (e.g., the current screen's `COACTUP/COACTUPA`) requires runtime/MOVE-chain analysis.

**Implication:** Q4 map-surface queries return the literal-form maps cleanly; the identifier-form sites are visible in the graph but their target map names are not knowable from skeleton alone.

---

## 6. Unresolved JCL symbolic parameter

1 Dataset entity is `partial: true`:

- `dataset:&CNTLLIB` — the REPROC.prc PROC body references `DSN=&CNTLLIB(REPROCT)`. `&CNTLLIB` is a PROC parameter substituted at use-site (e.g., `CNTLLIB=AWS.M2.CARDDEMO.CNTL` in TRANREPT.jcl). The PROC body alone can't be fully resolved without per-use-site parameter binding (which the extractor does not yet do for full DSN substitution).

**Implication:** when the agent analyzes REPROC's PRC001 SYSIN dataset reference, it should note that the actual DSN is bound at the calling job, not in the PROC itself.

---

## 7. Corpus-level edge absences

Two edge types in the v1 schema have **zero instances** in the CardDemo extraction:

- `LINKS_TO` — zero in the **extracted v1 scope**. NOTE (corrected): this is NOT because the corpus has no LINK — the deferred subapplication DOES use `EXEC CICS LINK` (e.g. `app/app-authorization-ims-db2-mq/cbl/COPAUS1C.cbl:218` → `EXEC CICS LINK PROGRAM(WS-PGM-AUTH-FRAUD)`), but that subapp is out of v1 extraction scope per the DB2/IMS/MQ deferral. The earlier claim "CardDemo uses XCTL not LINK / no LINK anywhere" was wrong; the honest statement is zero LINKS_TO **in extracted scope**.
- `RETURNS_TO_TRANSID` — zero in the extracted v1 scope: every `EXEC CICS RETURN` in the **in-scope** programs is TRANSID-less.

**Implication:** the v1 graph correctly shows no LINK / no RETURN-TRANSID edges **within its extracted scope**. This is extracted-scope reality, not an extractor gap — but it is NOT a claim that the whole CardDemo distribution lacks LINK (the deferred subapp has one).

---

## 8. Operational CICS verbs not modeled

Per closed-vocabulary discipline, certain CICS verbs are observed in the source but emit no edges in v1 (no closed-vocab edge type covers them):

```
EXEC CICS HANDLE / ABEND / ASSIGN / INQUIRE
EXEC CICS ASKTIME / FORMATTIME
EXEC CICS WRITEQ / READQ TS|TD     — TS/TD queues not modeled in v1
EXEC CICS DELETEQ
```

**Implication:** the KB doesn't carry edges for these operational interactions. If your analysis covers error-handling patterns, timing dependencies, or TS/TD-queue communication, label these as "not modeled in v1."

---

## 9. Constructs explicitly out-of-scope (v1 design decisions)

- COBOL paragraphs and sections — `PERFORMS`/`GO TO` intra-program control flow is not modeled. Each program is treated as a single Program entity with sub-paragraph structure unobservable.
- ~~DataItem (field-level COBOL record layouts) — out of v1.~~ **UPDATED (v2.2, KU-9): the field-level DataItem layer IS now extracted** — 517 `DataItem` entities model copybook record layouts (level / name / picture / usage / occurs / redefines + advisory `suggested_sql_type`), with `HAS_FIELD` / `CONTAINS_ITEM` hierarchy. See `graph_summary.md` / `kb_capabilities.md`. (This line was a v1 design decision; KU-9 superseded it.) Still out: 88-level condition names and `MAPS_TO_ITEM` (the KU-9 stretch seam, deferred).
- BMS field ↔ symbolic-map data item linking — still out (the `MAPS_TO_ITEM` edge between a BMS field and its backing DataItem is the deferred KU-9 stretch, even though the DataItem layer itself now exists).
- Transitive (wide) Q1 — Q1 returns `direct_includers` + `related_files` informational seed, but does not automatically compute "all programs touching files whose record-layout copybook is the target." That's `needs-ext` per spec.
- Performance / hot-path analysis — not in scope.
- Test coverage analysis — not in scope.
- Business-domain boundary proofs — Q5 produces candidates, not commitments.

---

## 10. Q2 jcl_access fine-grain (known Gate-3 incremental)

The frozen gold-set Q2.1-Q2.5 list batch jobs at **job-level granularity** (which JCL jobs reference each dataset by DSN). The per-step DD-name + DISP + inferred_access_mode refinement is a Known Gate-3 Incremental per the gold-set freeze banner — reasonable refinement work, not a blocker for the freeze.

**Implication:** Q2 returns 1 row per job-step that USES_DATASET the target dataset (with DD name and raw DISP available on the edge). The "inferred_access_mode" semantic mode (READ/WRITE/UPDATE) is on the edge `attributes.inferred_access_mode` field but the inference rule (RUL-DERIV-011) is implemented narrowly — extending its inference to combine DISP + DD-role + utility-SYSIN-content + COBOL access verbs is reasonable refinement work.

---

## 11. LLM enrichments (empty in v1)

`enrichments.json` is empty. When Pass 2 is implemented in a future version, it will populate this artifact with `evidence_kind: inferred` properties (e.g., `inferred_purpose` for programs and datasets, bounded-context names for Q5 clusters, MOVE-chain resolutions for identifier-form XCTLs). The architectural commitment is visible from v1 — there's a defined slot for enrichments separate from skeleton.

**Implication:** for Gate 4, you have skeleton-only material. If you would benefit from inferred-purpose hints to write the operations manual or modernization strategy, you can apply your own LLM reasoning to skeleton facts and explicitly label such reasoning as "agent inference" rather than KB fact.
