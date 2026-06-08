// Q5 — Cluster by shared data access (INFORMATIONAL; not gold-asserted, per spec §Q5).
// Contract: surface bounded-context candidates and straddle programs from shared
// dataset access. The v1 heuristic (see artifacts/clustering_report.md §1) builds a
// Program<->Dataset bipartite projection from the two access paths below, groups
// programs by naming-convention domain, computes each cluster's canonical dataset
// set (datasets touched by >=2 programs in the cluster), and flags straddle programs
// whose datasets cross cluster boundaries (excluding plumbing datasets like LOADLIB).
// Substrate: kuzu (spec v4.1). The projection halves mirror clustering_report.md §1.

// (a) online side — Program -> LogicalFile -> Dataset, per-program dataset set
MATCH (p:Program)-[:READS|WRITES|UPDATES|DELETES|STARTS_BROWSE]->(lf:LogicalFile)
      -[:BINDS_TO]->(d:Dataset)
RETURN p.id AS program, collect(DISTINCT d.id) AS datasets
ORDER BY program;

// (b) batch side — Program <- JCLStep -> Dataset, per-program dataset set
MATCH (p:Program)<-[:INVOKES]-(s:JCLStep)-[:USES_DATASET]->(d:Dataset)
RETURN p.id AS program, collect(DISTINCT d.id) AS datasets
ORDER BY program;
