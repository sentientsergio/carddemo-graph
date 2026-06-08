// Q3 — Transaction-to-program closure.
// Contract: from a CICS transaction, the entry program and the set of programs
// transitively reachable via static CALLS/LINKS_TO/XCTLS_TO (literal-form, typed-
// Program targets only). Identifier-form (dynamic) targets are NOT promoted to
// reachable; they surface separately as unresolved breadcrumbs (spec §Q3, RUL-NEG-001).
// Sample input: transaction:CC00. Substrate: kuzu (spec v4.1).
// Mirrors carddemo_graph.pilot.run_q3_sample (the validated Gate-3 runner).

// entry_program — the program the transaction dispatches to (CSD-authoritative)
MATCH (t:CICSTransaction {id: 'transaction:CC00'})-[:IS_TRANSACTION_FOR]->(p:Program)
RETURN p.id AS entry_program;

// reachable_programs — transitive closure over static edges, typed programs only.
// Bounded depth 1..6 gives cycle-safe traversal over this corpus's call graph.
MATCH (t:CICSTransaction {id: 'transaction:CC00'})-[:IS_TRANSACTION_FOR]->(p0:Program)
      -[:CALLS|LINKS_TO|XCTLS_TO*1..6]->(p:Program)
WHERE p.id <> p0.id AND NOT p.id STARTS WITH 'unresolved:'
RETURN DISTINCT p.id AS reachable_program
ORDER BY reachable_program;

// unresolved_reaches — identifier-form (dynamic) CALL/LINK/XCTL targets, with the
// breadcrumb identifier captured at extract time (e.g. CDEMO-TO-PROGRAM MOVE-chain)
MATCH (t:CICSTransaction {id: 'transaction:CC00'})-[:IS_TRANSACTION_FOR]->(p0:Program)
      -[c:CALLS|LINKS_TO|XCTLS_TO]->(u:Program)
WHERE u.id STARTS WITH 'unresolved:'
RETURN DISTINCT p0.id AS source_program, u.id AS target,
       c.breadcrumb AS breadcrumb, c.call_kind AS call_kind
ORDER BY source_program, target;
