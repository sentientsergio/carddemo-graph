# Vendored: MAPA (COBOL CallTree parser)

This directory vendors the third-party **MAPA** COBOL parser plus our minimal
provenance patch, as the parse engine behind the grammar-parser foundation
(`src/carddemo_graph/extract/parsers/`). It replaces the hand-tuned regex Pass-1.

## Upstream

- Project: **MAPA** — https://github.com/cschneid-the-elder/mapa
- Pinned commit: **`2ad7cd5e9c5244499cea07925763ff8c36ab2408`**
- License: **MIT** (see `LICENSE`, copied verbatim from the MAPA repo root).
- Author: Craig Schneiderwent (portions © Maarten van Haasteren). Their copyright
  and the MIT terms are preserved. We are not erasing MAPA's provenance.

ANTLR 4.13.2 (`upstream/antlr-4.13.2-complete.jar`, BSD-3-Clause) and MAPA's
prebuilt sibling-language jars (`CICSz.jar`, `DLI.jar`, `DB2zSQL.jar`, all MIT,
part of MAPA) and `commons-cli-1.4.jar` (Apache-2.0) are included as build deps —
the COBOL build links against them; we do not rebuild them from source here.

## Vendoring approach (b): source + standalone patch + documented build

- `upstream/` — **pristine** MAPA COBOL build inputs at `2ad7cd5` (hand-written
  `src/*.java`, the four `*.g4` grammars, `Makefile`, `manifest`, build-dep jars).
  Untouched, so our delta stays reviewable as a diff against it.
- `mapa_origin_tracker.patch` — **our delta** (38+/4-, 3 files). Adds a
  provenance origin sidecar to MAPA's preprocessor: per preprocessing pass it
  writes `<temp>.origin` with one record per output line — `PASS <inputLine>`
  (passthrough; origin = this pass's input) or `COPY <copybookPath> <copyLine>`
  (a spliced copybook line — a root origin). Composing the per-pass sidecars maps
  each preprocessed line back to its original file+line. Kept standalone (not
  intermingled into `upstream/`) so it is reviewable and upstream-offerable as-is.
  Identical to the durable checkpoint copy in
  `artifacts/parser_foundation/mapa_origin_tracker.patch`.
- `build.sh` — applies the patch to a throwaway `build/` copy, generates the
  ANTLR sources, compiles single-shot (the per-file `make` chokes on mutual class
  references), and packages `CallTree.jar`.

## Build

```
./build.sh
```

Produces `./CallTree.jar` (gitignored — it is a build artifact, not vendored
source). Requires a JDK on PATH (tested JDK 22; MAPA targets 17+). The COBOL
adapter's Parse seam invokes this jar; it raises a clear "run vendor/mapa/build.sh"
error if the jar is absent.

## What is intentionally NOT vendored

The `.git` history, `testdata/` (NIST suite), and the `cics/db2z/dli/jcl` source
trees of MAPA — none are needed to build the COBOL `CallTree.jar` (the sibling
languages are consumed as prebuilt jars). Generated ANTLR sources, `build/`,
`*.class`, and the output jar are gitignored.
