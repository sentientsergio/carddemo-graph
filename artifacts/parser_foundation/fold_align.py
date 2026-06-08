"""(B) adapter-side fold alignment — proves NON-1:1 copybook provenance round-trip.

Per-transform isolation (review condition 1): we align ONLY the fold step, by
aligning the two temps that differ ONLY by the fold:
    without73to80 (col-strip, proven 1:1 with source)  <->  withoutcontinuations (fold)
Then without73to80-line == source-line (identity, asserted), giving fold-line -> source-line.

Alignment (condition 2): content-anchored two-pointer walk, NOT naive line-diff.
The fold = (strip output) with blank lines removed + continuations folded onto the
statement START line. So the K-th fold line must content-match the K-th NON-foldable
strip line, in order. Every pair is verified on content; any divergence FLAGS loudly
(no silent-wrong provenance edge). Handles leading-blank, blank-collapse, duplicates
(monotonic walk preserves order).
"""
import sys, re

SOURCE = "corpus/carddemo/source/app/cpy/CVEXPORT.cpy"
STRIP  = open("/tmp/parser-bakeoff/_strip_path").read().strip()
FOLD   = open("/tmp/parser-bakeoff/_fold_path").read().strip()

def lines(p):
    return open(p, encoding="iso-8859-1").read().split("\n")

src   = lines(SOURCE)
strip = lines(STRIP)
fold  = lines(FOLD)
# trailing empty element from final newline
for L in (src, strip, fold):
    if L and L[-1] == "": L.pop()

def norm(s):           # fold preserves columns; only trailing ws differs
    return s.rstrip()
def is_blank(s):
    return s.strip() == ""

print(f"src={len(src)}  strip={len(strip)}  fold={len(fold)}")

# --- per-transform isolation: strip must be 1:1 with source on cols 1-72 ---
assert len(strip) == len(src), f"col-strip NOT 1:1: strip={len(strip)} src={len(src)}"
for i,(a,b) in enumerate(zip(src, strip), 1):
    assert a[:72].rstrip() == b[:72].rstrip(), f"strip diverges from source at line {i}"
print("OK  col-strip is 1:1 with source (line N == line N) — fold is isolated")

# --- content-anchored alignment: fold-line -> strip-line(=source line) ---
fold_to_src = {}          # folded line (1-based) -> original source line (1-based)
flags = []
oi = 0                    # index into strip (0-based)
for fi, fline in enumerate(fold, 1):
    # skip strip lines the fold drops (blank lines)
    while oi < len(strip) and is_blank(strip[oi]):
        oi += 1
    if oi >= len(strip):
        flags.append((fi, "ran past end of strip")); break
    if norm(fline) != norm(strip[oi]):
        flags.append((fi, oi+1, f"MISMATCH fold[{fi}]={fline.strip()!r} strip[{oi+1}]={strip[oi].strip()!r}"))
    fold_to_src[fi] = oi + 1     # strip line == source line (1:1 proven above)
    oi += 1
# any remaining strip lines must be only trailing blanks
while oi < len(strip):
    if not is_blank(strip[oi]):
        flags.append((None, oi+1, f"unconsumed non-blank strip line {oi+1}"))
    oi += 1

print(f"aligned {len(fold_to_src)} fold lines; flags={len(flags)}")
for f in flags: print("  FLAG", f)
assert not flags, "ALIGNMENT AMBIGUOUS — refusing to emit silently-wrong provenance"

# --- prove the drift is corrected: pick fields after blanks ---
print("\n=== drift correction (gate cases) ===")
def find_src(substr):
    for n,l in enumerate(src,1):
        if substr in l: return n
def find_fold(substr):
    for n,l in enumerate(fold,1):
        if substr in l: return n
checks = ["EXPORT-RECORD-DATA", "EXPORT-CUSTOMER-DATA REDEFINES", "EXP-CARD-ACTIVE-STATUS",
          "FILLER                          PIC X(373)"]
allok = True
for c in checks:
    fl = find_fold(c); sl_true = find_src(c)
    sl_mapped = fold_to_src.get(fl)
    naive = fl                       # what 1:1 assumption would have claimed
    ok = (sl_mapped == sl_true)
    allok &= ok
    print(f"  {c[:34]:34} fold L{fl:>3} -> src L{sl_mapped:>3} (true {sl_true:>3}, naive-1:1 would say {naive:>3})  {'OK' if ok else 'WRONG'}{'  <-drift '+str(sl_true-naive) if sl_true!=naive else ''}")
print("\nRESULT:", "NON-1:1 ROUND-TRIP PROVEN — fold-line resolves to exact source line" if allok
      else "FAILED — investigate")
