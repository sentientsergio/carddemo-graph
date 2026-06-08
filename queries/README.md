# Cypher queries

The Q1–Q5 query contracts (see top-level README §"Executable form") in standalone,
executable form. Per spec v4.1: Cypher is the executable canonical form; DuckDB SQL
is optional.

| File | Contract | Sample input | Gold-asserted |
|---|---|---|---|
| `q1.cypher` | Direct copybook inclusion impact | `copybook:CSUSR01Y` | yes (`direct_includers`) |
| `q2.cypher` | Dataset access (program + JCL, with mode) | `dataset:AWS.M2.CARDDEMO.USRSEC.VSAM.KSDS` | yes |
| `q3.cypher` | Transaction-to-program closure | `transaction:CC00` | yes |
| `q4.cypher` | BMS map surface for transaction | `transaction:CC00` | yes |
| `q5.cypher` | Cluster by shared data access | (whole graph) | no — informational |

Each file mirrors the validated Gate-3 runner logic in
`src/carddemo_graph/pilot.py` (`run_q1_sample` … `run_q4_sample`), which is the code
path `gold_match.py` exercises against the frozen `gold/gold_set.md`. The sample
inputs are inlined as literals so each file is directly runnable. Q5 mirrors the
bipartite projection documented in `artifacts/clustering_report.md` §1 and is
informational (not gold-asserted), per spec §Q5.

## Running

The kuzu `.db` is a gitignored build product (see `.gitignore` for rationale);
rebuild it from the committed `entities.json` + `edges.json`, then run a query file:

```
# Rebuild the Gate-3 kuzu DB from the committed JSON artifacts
PYTHONPATH=src .venv/bin/python -m carddemo_graph.gate3

# Run a query file against it (kuzu CLI)
kuzu artifacts/gate3/carddemo_graph.db < queries/q3.cypher
```

To inspect the runner's own validated output without the CLI, read
`artifacts/gate3/query_samples.json` (Q1–Q4 against the full-tree graph).
