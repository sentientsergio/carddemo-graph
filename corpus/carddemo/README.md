# corpus/carddemo

## Provenance
- **Source:** [aws-samples/aws-mainframe-modernization-carddemo](https://github.com/aws-samples/aws-mainframe-modernization-carddemo)
- **Retrieval:** 2026-04-27, as a git submodule under `source/`.
- **License:** see `source/LICENSE`. Our derivative (the stripped corpus) is distributed under the same terms.

## Layout
- `source/` — original CardDemo, unmodified. Git submodule.
- `stripped/` — derivative with comments and natural-language documentation removed. Produced by `scripts/strip_corpus.py`.

## Reproduce the stripped corpus
```sh
python3 scripts/strip_corpus.py
```

## What gets stripped

Comment removal covers every comment-bearing source type in the corpus, with the exact rule per syntax documented in [`docs/strip-syntax/`](../../docs/strip-syntax/README.md).

- **COBOL family** (`.cbl`, `.cob`, `.cpy`, `.dcl` DCLGEN output): comment lines where column 7 is `*`. Code lines (and their columns 1–6 sequence area, columns 73–80 trailing identification) are preserved byte-for-byte.
- **JCL family** (`.jcl`, `.prc`, `.proc`, `.jcl.template`): comment lines starting `//*`.
- **HLASM-format family** (`.bms`, `.asm`, `.mac`, `.psb`, `.dbd`, `.csd`): comment lines where column 1 is `*`, with carve-out for the `*PROCESS` listing-control directive.
- **SQL family** (`.ddl`, `.ctl`): `--` line comments and `/* ... */` block comments removed with string-literal awareness.
- **Shell family** (`.sh`, `.awk`): leading-`#` line comments removed; `#!` shebang preserved on line 1.
- **Documentation files anywhere in the tree**: `*.md`, `README*`, `CONTRIBUTING*`, `CODE_OF_CONDUCT*`, `*.png`, `*.drawio`.
- `LICENSE` and `NOTICE` are preserved per Apache 2.0.

Other files (sample data, EBCDIC binaries, build artifacts) pass through byte-identical to source.

**One acknowledged exception:** HLASM operand-tail comments — short remarks attached after instruction operands on the same line — are not removed. Identifying them reliably requires parsing each HLASM macro's operand syntax, and that work is deferred (see `docs/strip-syntax/assembler-col1.md`). The residual is small: 7 lines across 5,477 lines of stripped HLASM, concentrated in two assembler files (`app/asm/COBDATFT.asm`, `app/asm/MVSWAIT.asm`); zero residual in `.bms`/`.mac`/`.psb`/`.dbd`. See `proposition.md` §3 for detail.

## Verification

| Action | Files | Source lines | Output lines | Δ |
|---|---:|---:|---:|---:|
| stripped-cobol | 112 | 41,089 | 36,089 | −5,000 |
| stripped-jcl | 62 | 4,052 | 2,230 | −1,822 |
| stripped-assembler | 37 | 6,821 | 6,162 | −659 |
| stripped-sql | 14 | 306 | 194 | −112 |
| stripped-shell | 10 | 413 | 383 | −30 |
| passthrough | 79 | 12,409 | 12,409 | 0 |
| removed-doc | 18 | 21,506 | 0 | −21,506 |
| **stripped tree total** | **314 files** | | | |

The strip script halts loudly on documented edge cases (unrecognized COBOL indicator-area byte, `*>` floating-comment marker, ambiguous `*<token>` in HLASM, unclosed `/*` block or unclosed string in SQL). None fired against the CardDemo source.

After the strip, an invariant-verification pass asserts per-syntax structural correctness — no residual `*` at column 7 in stripped COBOL, no `//*` in stripped JCL, no column-1 `*` outside the `*PROCESS` carve-out in stripped HLASM, no `/*` / `*/` / `--` in stripped SQL, no leading-`#` outside the line-1 shebang in stripped shell, every passthrough file byte-identical to source. Halts loudly on the first violation.

The strip is idempotent: running twice produces the same output as running once (verified via `diff -r`).

An automated test suite at [`tests/test_strip.py`](../../tests/test_strip.py) (37 tests) exercises the rules against synthetic fixtures including the regression for the sprint-1 `.jcl.template` double-extension classifier bug. Run via:

```sh
python3 -m unittest tests.test_strip
```
