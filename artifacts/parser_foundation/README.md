# Parser foundation — durable checkpoint (proofs + MAPA patch)

This directory is a **durable checkpoint** of the grammar-parser foundation work (v3),
so the proofs and the MAPA delta survive outside ephemeral `/tmp`. It is NOT the
foundation package itself — that lift (`src/carddemo_graph/extract/parsers/`) starts
fresh. See `../../RESUME.md` for the full resume point.

## Third-party: MAPA (vendored as a patch for now)

- Upstream: **cschneid-the-elder/mapa** — https://github.com/cschneid-the-elder/mapa.git
- Pinned commit: **2ad7cd5e9c5244499cea07925763ff8c36ab2408**
- License: **MIT** (MAPA's `LICENSE` at the repo root). When MAPA source is vendored
  into the tree during the lift, its `LICENSE` and attribution MUST be preserved
  alongside the vendored source. We are not erasing its provenance.

## `mapa_origin_tracker.patch` — our delta (standalone, reviewable, upstream-offerable)

A minimal patch (38 insertions / 4 deletions across 3 files) that makes MAPA's
preprocessor emit a provenance origin sidecar — the integrity-critical piece, kept as a
standalone diff (NOT intermingled into vendored source) so it is reviewable and can be
offered upstream as-is.

- `cobol/src/OriginTracker.java` (new): static, flush-per-write emitter. Per preprocessing
  pass writes `<temp>.origin` with one record per output line — `PASS <inputLine>`
  (passthrough; origin = this pass's input at that line) or
  `COPY <copybookPath> <copyLine>` (a spliced copybook line, a root origin).
- `cobol/src/CopyStatement.java`: record the COPY-splice writes (pre/post source-line
  fragments as PASS; each spliced copybook line as COPY).
- `cobol/src/CobolSource.java`: `begin()` the sidecar at the copy-pass temp; record the
  passthrough write.

The `CallTree.jar` rebuild is a build artifact and is intentionally NOT in the patch.

### Apply + build

```
git clone https://github.com/cschneid-the-elder/mapa.git
cd mapa && git checkout 2ad7cd5
git apply /path/to/mapa_origin_tracker.patch
cd cobol
# JDK 22; MAPA bundles ANTLR 4.13.2. The per-file `make` chokes on mutual class refs;
# build single-shot:
javac -d class -cp "class:antlr-4.13.2-complete.jar:CICSz.jar:DLI.jar:DB2zSQL.jar:commons-cli-1.4.jar" -sourcepath src src/*.java
jar cfm CallTree.jar manifest -C class .
```

## `fold_align.py` — provenance round-trip proof (record of how it was proven)

The (B) adapter-side fold alignment that proves the non-1:1 round-trip (see
`../parser_provenance_proof.md`). This is the **proof of record**, not yet a reusable
module — its input paths are `/tmp`-relative to the original proof run (the MAPA
`-saveTemp` temps). The reusable form lands in the foundation package during the lift.
Re-running requires regenerating the temps (run patched MAPA `-saveTemp` on CBEXPORT /
CBTRN02C against a source-based copybook harness, as documented in the proof note).
