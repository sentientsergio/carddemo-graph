# Provenance Round-Trip — Proof and Generalization Boundary

Status: PROVEN for the transforms this corpus contains. Companion to `parser_bakeoff_phase0.md`.
Date: 2026-05-31. Branch: `feature/grammar-parser-foundation`. Uncommitted pending review.

## Why this matters

The grammar-parser foundation (MAPA, see the bake-off note) parses a *preprocessed*
form of each source: columns >72 stripped, `COPY` members spliced in, continuation
lines folded. ANTLR node coordinates therefore point at **preprocessed** lines, not the
original source. But a `ProvenanceItem` must carry the **original** `source_path` + line
(a copybook field resolves to its copybook file+line; a program statement to its program
line). 100% original-coordinate provenance is a structural invariant of the engine.

So a remap is required: preprocessed coordinate → original file + line. The design
decision (approach **B**) is that this remap is a **Normalize-seam contract owned by our
adapter**, not piggybacked on the parser. The upstream MAPA patch stays minimal (a single
COPY-splice origin sidecar); all coordinate logic lives in our adapter, derived by
aligning the intermediate temp files MAPA already retains under `-saveTemp`.

## What was proven

Two halves, both **shown** (not asserted), each on the case that actually stresses it.

### 1. Expanded field → copybook line (non-1:1 copybook)

Gate copybook: **CVEXPORT** — 5 blank lines (orig 20/43/61/80/89), also our Q6.2 hard case.

- Per-transform isolation: the column-strip stage (`copyWithout73to80`) writes every
  input line, proven **1:1** with source (cols 1–72 identical, line N == line N). So only
  the continuation-fold stage needs alignment: `without73to80` (103 lines) → folded (98),
  dropping exactly the 5 blanks; comments survive.
- Content-anchored alignment (not a naive line-diff): a two-pointer walk that skips the
  lines the fold drops and **asserts per-line content match**. All 98 folded lines matched
  their mapped source line, 0 flags.
- Drift corrected exactly: `FILLER` folds to line 95 → resolves to true source **100**
  (+5); `EXP-CARD-ACTIVE-STATUS` folded 94 → source 99 (+5); the REDEFINES folded 23 →
  source 24 (+1). The naive "folded line == source line" read mislabels every post-blank
  field. The full chain `final-copy-line → folded-line → SOURCE-line` composes with the
  COPY-splice sidecar (all 98 spliced entries chained).

### 2. Program statement → program line (program-native)

Gate program: **CBTRN02C** — 731 lines, 53 blank, 59 comment.

- strip = 731 (1:1 with source); folded = 678 (drops the 53 blanks; comments survive).
- `CALL 'CEE3ABD'` (program-native, near end of file, past all blank-collapse) folds to
  line 660 → resolves to **exact source line 711** (drift +51). End-to-end through the
  copy-pass PASS records: `final copy-temp line → fold line 660 → align → source 711`.
  All 678 fold lines aligned, 0 flags. Same mechanism as the copybook half.

## Generalization boundary (load-bearing, not a footnote)

The fold transform **actually exercised by this corpus** is blank-line collapse +
comment preservation. The CardDemo corpus has **zero classic continuation lines**
(column-7 `-`) — in any program or copybook (CBTRN02C, COACTUPC, every member: 0).

Classic continuation lines are **common in production COBOL**. CardDemo having none is a
quirk of *this* corpus, so this is a genuine **per-corpus generalization boundary**, not
an incidental detail. Two consequences:

- **Not yet exercised:** true continuation-folding (N source lines folded onto one
  anchored output line). The current content-anchored alignment does not yet resolve it.
- **Fail-loud, not fail-silent:** if a continuation is encountered, a folded line's
  content will not match any single strip line, so the alignment **flags and refuses to
  emit** rather than producing a silently-wrong provenance edge. The posture is "refuse
  rather than lie."

**Bounded extension (scheduled for Phase 3, the N>1 across-corpus check):** extend the
walk to consume continuation lines and anchor the folded line to the statement *start*
line (range maps naturally onto `ProvenanceItem` start/end). Phase 3 should use a
continuation-bearing snippet (synthetic is acceptable) — it both proves the guard fires
and exercises the extension. This does **not** block Phase 2, since CardDemo has no
continuations.

## Proof artifacts

`/tmp/parser-bakeoff/fold_align.py` (copybook proof + inline program proof), the patched
MAPA build, and the source-based copybook harness `cpy-src/`. These are ephemeral; the
adapter-side alignment and the minimal MAPA patch are to be lifted into
`src/carddemo_graph/extract/parsers/` as the committed foundation.
