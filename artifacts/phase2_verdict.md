# Phase-2 Gold-Parity Verdict

**Question this answers:** is the default-path `gold_match` result of **37 match / 0 diff /
3 known-incremental** the *full* Phase-2 gold-parity PASS, or is there residual Phase-2
lift still open beyond it?

**Verdict: it is the full Phase-2 gold-parity PASS.** Zero real gold diffs, zero
program-rule regressions, zero gold regressions. The three "diffs" are not open lift — they
are explicit, pre-declared deferrals (see §3). The README's parity claims answer to exactly
this evidence and must not exceed it.

---

## 1. What Phase-2 tests (the gate definition)

The full Gate-3 pipeline is run under **both** COBOL extractors via `CARDDEMO_COBOL_PARSER`
(`mapa` = the grammar parser, now the default; `regex` = the retained baseline), to separate
output directories, then:

1. `gold_match.py` runs every comparator (Q1–Q4 + Q6) against each resulting kuzu graph and
   reports `matched / diff / known-incremental`, exiting non-zero on any **real** diff.
2. A three-way observation diff (`artifacts/phase2_diff.py`) classifies every per-rule delta
   as **parity / improvement / regression** — the gate passes only with **0 program-rule
   regressions** and **0 gold regressions**.

A claim of "parity" is therefore not asserted; it is the output of a runnable gate.

## 2. Evidence (reproduced through the repo-relative generator)

Canonical run: `gate3-fulltree-20260608T150215Z`, schema `1.1.0`. Re-confirmed end-to-end
after the repo-relative-`source_path` generator fix (parity survives the regen).

| | gold_match | graph | gold exit |
|---|---|---|---|
| **MAPA (default)** | **37 match / 0 diff / 3 known-incremental** (of 40) | 1863 entities / 1444 edges | **0** |
| regex (retained baseline) | 36 match / 1 diff / 3 known-incremental | 1864 / 1445 | 1 |

Three-way observation diff (MAPA vs regex): `parity = 3526`, `program-rule regressions = {}`,
`gold regressions = 0`. Categorized deltas:

- **Improvements (MAPA more correct, not at-parity):** copybook-origin CALL discovered ×1
  (`COACTUPC → CSUTLDTC` via `COPY CSUTLDPY`, which the regex never scans); regex `READ`-on-a-
  data-name false positives dropped ×2 (COCRDLIC `SET MORE-RECORDS-TO-READ TO TRUE`).
- **Copybook-layer (pre-existing, benign, not from the program flip):** RUL-COBOL-021 ×3 (the
  `PIC +ZZZ,ZZZ,ZZZ.ZZ` → NUMERIC typing the regex char-class missed); RUL-COBOL-002 ×31
  (Copybook-presence entity emitted as an observation only by regex; under mapa it is
  materialized by Pass-3 from edges — final entity set unaffected).

**The decisive proof:** with the gold corrected to ground truth (Q3.2 copybook-expanded
reachability), the **retained regex baseline now fails Q3.2** (missing `CSUTLDTC`, `CEEDAYS` —
it structurally cannot expand `COPY`), while MAPA passes. So the gate does not merely show
parity — it shows the grammar parser is **demonstrably more correct** than the path it
replaced. (`tests/` 36/36 green.)

## 3. What the 37/0/3 PASS does and does NOT cover (validation strength)

The match count is honest about the strength behind each part — it is not one flat number:

- **Q1–Q4 (33 of the 37): hand-traced ground truth.** The deductive skeleton, checked against
  human hand-traced expected answers.
- **Q6.1 / Q6.2 (4 of the 37): cold-agent gold.** Field-layer convergence with the extraction is
  *agreement, not proof* (two independent reads of clean COBOL); a human COBOL expert would
  supersede. Validated on one simple and one hard copybook.
- **The 3 "diffs" are known-incremental DEFERRALS, not open lift:** Q2 `jcl_access` job-level vs
  step-level fine-grain, explicitly deferred by the gold's freeze banner. Identical in both
  variants — not a MAPA gap.
- **Q5 (clustering) is illustrative and not gold-asserted** — it is not among the 40 comparisons.

## 4. Documented boundaries (out of scope for gold-parity; not residual gate lift)

These are honest scope limits, not unfinished Phase-2 work — the gate passes with them:

- **One program (`CBSTM03A.CBL`) falls back to the regex extractor** — it uses classic col-7
  continuation lines (HTML literals); `fold_align` fail-loud-refuses and the adapter falls back,
  producing output byte-identical to regex. Continuation-folding is Phase-3. 32/33 programs emit
  via MAPA.
- **CICS operand content-validation is not implemented** (SEND/RECEIVE-MAP/RETURN-TRANSID
  operands are keyword-paren extracted from the grammar-delimited block; the construct *line* is
  resolver-validated and fail-loud, the *operand* is not). Phase-3. Does not affect gold-parity.

## 5. Reproduce

```
PYTHONPATH=src python artifacts/phase2_diff.py     # both variants -> gold_match + three-way diff
PYTHONPATH=src python -m carddemo_graph.gold_match artifacts/gate3/carddemo_graph.db gold/gold_set.md
PYTHONPATH=src python -m pytest tests/ -q
```

## 6. What this verdict licenses a README to claim

Exactly: *gold-parity PASS (37 match / 0 diff / 3 known-incremental, exit 0) via the
grammar-parser extractor (now default), 0 regressions, and demonstrably more correct than the
regex baseline it replaced (which scores 36/1/3) — with Q1–Q4 hand-traced, Q6 cold-agent
(agreement-not-proof), Q5 not gold-asserted, and the one continuation-fallback program and the
CICS-operand boundary stated.* No stronger.
