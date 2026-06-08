# Query Examples (Cypher against `carddemo_graph.db`)

Ready-to-use Cypher patterns. Load `carddemo_graph.db` into kuzu:

```python
import kuzu
db = kuzu.Database("carddemo_graph.db")
conn = kuzu.Connection(db)
```

---

## Acceptance queries (Q1-Q4)

### Q1 — Direct copybook impact

```cypher
// Programs that COPY copybook:CSUSR01Y
MATCH (p:Program)-[r:INCLUDES]->(c:Copybook {id: 'copybook:CSUSR01Y'})
RETURN p.id AS program_id, r.source_path AS source_path, r.start_line AS line
ORDER BY program_id;

// Transactions bound to those programs
MATCH (t:CICSTransaction)-[:IS_TRANSACTION_FOR]->(p:Program)
      <-[:INCLUDES]-(c:Copybook {id: 'copybook:CSUSR01Y'})
RETURN DISTINCT t.id AS transaction_id, p.id AS program_id
ORDER BY transaction_id;

// Maps sent/received by those programs (literal-form only)
MATCH (c:Copybook {id: 'copybook:CSUSR01Y'})<-[:INCLUDES]-(p:Program)
      -[:SENDS_MAP|RECEIVES_MAP]->(m:BMSMap)
WHERE m.partial IS NULL OR m.partial = FALSE
RETURN DISTINCT p.id AS program_id, m.id AS map_id
ORDER BY program_id, map_id;

// Related logical files (DEFINES_LAYOUT_FOR — FD-context only)
MATCH (c:Copybook {id: 'copybook:CSUSR01Y'})-[:DEFINES_LAYOUT_FOR]->(lf:LogicalFile)
RETURN lf.id AS logical_file_id, lf.name AS name;
```

### Q2 — Dataset access

```cypher
// Program access (online + batch via BINDS_TO chain)
MATCH (p:Program)-[r:READS|WRITES|UPDATES|DELETES|STARTS_BROWSE]->(lf:LogicalFile)
      -[b:BINDS_TO]->(d:Dataset {id: 'dataset:AWS.M2.CARDDEMO.USRSEC.VSAM.KSDS'})
RETURN p.id AS program_id, lf.id AS logical_file, b.dd_name AS dd,
       label(r) AS mode, r.source_path AS path, r.start_line AS line
ORDER BY program_id, line;

// JCL access via USES_DATASET
MATCH (s:JCLStep)-[u:USES_DATASET]->(d:Dataset {id: 'dataset:AWS.M2.CARDDEMO.USRSEC.VSAM.KSDS'})
RETURN s.id AS step, u.dd_name AS dd,
       u.allocation_disposition AS disp,
       u.inferred_access_mode AS mode;
```

### Q3 — Transaction-to-program closure

```cypher
// Entry program
MATCH (t:CICSTransaction {id: 'transaction:CC00'})-[:IS_TRANSACTION_FOR]->(p:Program)
RETURN p.id AS entry_program;

// Transitively reachable via literal-form static edges (typed programs only)
MATCH (t:CICSTransaction {id: 'transaction:CC00'})-[:IS_TRANSACTION_FOR]->(p0:Program)
      -[:CALLS|LINKS_TO|XCTLS_TO*1..6]->(p:Program)
WHERE p.id <> p0.id AND NOT p.id STARTS WITH 'unresolved:'
RETURN DISTINCT p.id AS reachable_program
ORDER BY reachable_program;

// Unresolved reaches (identifier-form XCTL/LINK/CALL — MOVE-chain target)
MATCH (t:CICSTransaction {id: 'transaction:CC00'})-[:IS_TRANSACTION_FOR]->(p0:Program)
      -[c:CALLS|LINKS_TO|XCTLS_TO]->(u:Program)
WHERE u.id STARTS WITH 'unresolved:'
RETURN p0.id AS source, u.id AS target,
       c.breadcrumb AS breadcrumb, c.call_kind AS kind;
```

### Q4 — BMS map surface for transaction

```cypher
// Entry program
MATCH (t:CICSTransaction {id: 'transaction:CAUP'})-[:IS_TRANSACTION_FOR]->(p:Program)
RETURN p.id AS entry_program;

// Map interactions
MATCH (t:CICSTransaction {id: 'transaction:CAUP'})-[:IS_TRANSACTION_FOR]->(p:Program),
      (p)-[r:SENDS_MAP|RECEIVES_MAP]->(m:BMSMap)
WHERE m.partial IS NULL OR m.partial = FALSE
RETURN DISTINCT p.id, m.id, label(r) AS direction;

// Field surface (visible labels only)
MATCH (t:CICSTransaction {id: 'transaction:CAUP'})-[:IS_TRANSACTION_FOR]->(p:Program),
      (p)-[:SENDS_MAP|RECEIVES_MAP]->(m:BMSMap)
MATCH (f:BMSField) WHERE f.map_id = m.id AND f.label <> ''
RETURN DISTINCT m.id AS map, f.name AS field, f.label AS label
ORDER BY map, field;
```

---

## Modernization-flavored traversals

### Find programs that straddle bounded-context candidates

Programs that READ/WRITE datasets in more than one cluster signal cross-context coupling.

```cypher
// All datasets each program touches
MATCH (p:Program)-[:READS|WRITES|UPDATES|DELETES|STARTS_BROWSE]->(lf:LogicalFile)
      -[:BINDS_TO]->(d:Dataset)
RETURN p.id AS program, collect(DISTINCT d.id) AS datasets
ORDER BY program;
```

(Then group by dataset family in your analysis — this is the Q5 shared-data-access clustering, informational and not gold-asserted. The skeleton gives you the Program↔Dataset access facts; the bounded-context grouping is yours to derive.)

### Find programs invoked by JCL (batch surface)

```cypher
MATCH (s:JCLStep)-[:INVOKES]->(p:Program)
WHERE NOT p.id STARTS WITH 'program:I' AND NOT p.id STARTS WITH 'program:S'
  AND p.partial = FALSE
RETURN p.id AS program, collect(s.id) AS invoking_steps
ORDER BY program;
```

(Excludes system utilities like IDCAMS, SORT etc. — adjust the prefix filter as needed.)

### Find unresolved JCL→program references

```cypher
MATCH (s:JCLStep)-[:INVOKES]->(p:Program)
WHERE p.partial = TRUE
RETURN p.id AS unresolved_target, count(*) AS invoking_step_count
ORDER BY invoking_step_count DESC;
```

### Find which datasets a program transitively depends on (with dd-name evidence)

```cypher
MATCH (p:Program {id: 'program:CBTRN02C'})
      <-[:INVOKES]-(s:JCLStep)
      -[u:USES_DATASET]->(d:Dataset)
RETURN d.id AS dataset, u.dd_name AS dd_name,
       u.allocation_disposition AS disp,
       d.organization AS org;
```

### Find what programs in the corpus use VSAM (vs PS / GDG / PDS)

```cypher
MATCH (p:Program)-[:READS|WRITES|UPDATES|DELETES|STARTS_BROWSE]->(lf:LogicalFile)
      -[:BINDS_TO]->(d:Dataset)
RETURN d.organization AS org, count(DISTINCT p.id) AS distinct_programs
ORDER BY distinct_programs DESC;
```

### Trace a copybook's transitive impact (programs + jobs that include it directly or via nested copy)

```cypher
MATCH p = (c:Copybook {id: 'copybook:CVACT01Y'})<-[:INCLUDES*1..3]-(consumer)
RETURN DISTINCT consumer.id AS consumer_id, length(p) AS hops
ORDER BY hops, consumer_id;
```

### Find the conflict ledger

```cypher
// Distinct PROC names with multiple source files (collision detection)
MATCH (proc:JCLProc)
RETURN proc.id, proc.declared_name, proc.source_path;
```

(See `resolution_report.md` for the human-readable conflict ledger; the REPROC collision is the one v1 entry.)

---

## Reading provenance back to source

Every entity and edge carries `source_path` + `start_line` + `end_line` + `rule_id`. To trace a claim:

```cypher
MATCH (p:Program {id: 'program:COSGN00C'})-[r:XCTLS_TO]->(target:Program)
RETURN target.id, r.call_kind, r.breadcrumb,
       r.source_path AS file, r.start_line AS from_line, r.end_line AS to_line,
       r.rule_id AS rule;
```

For full-detail provenance with snippets, consult `entities.json` / `edges.json` directly (kuzu carries first-citation provenance for efficiency; the JSON carries the full list).

---

## What kuzu doesn't (yet) cover

- `enrichments.json` content (empty in v1; if Pass-2 lands, may add `HAS_ENRICHMENT` rels or query enrichments by entity_id property)
- Pre-resolution Pass-1 observations (those live in `observations.json`; useful for tracing a specific extractor decision back to its rule)
- Multi-provenance per entity/edge — kuzu stores the first provenance only as columns; the JSON has the full list

When you need the full audit trail, drop into the JSON; when you need traversal, stay in Cypher.
