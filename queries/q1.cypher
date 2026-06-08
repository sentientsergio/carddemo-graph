// Q1 — Direct copybook inclusion impact.
// Contract: programs that directly COPY a copybook, plus the transactions, maps,
// and related logical-file layouts reachable from those programs. Gold-asserted on
// direct_includers (spec §Acceptance criteria A); DEFINES_LAYOUT_FOR is the
// informational seed for wide impact.
// Sample input: copybook:CSUSR01Y. Substrate: kuzu (Cypher canonical form, spec v4.1).
// Mirrors carddemo_graph.pilot.run_q1_sample (the validated Gate-3 runner).

// direct_includers — programs that directly COPY the copybook
MATCH (p:Program)-[r:INCLUDES]->(c:Copybook {id: 'copybook:CSUSR01Y'})
RETURN p.id AS program_id, p.name AS program_name,
       r.source_path AS source_path, r.start_line AS line
ORDER BY program_id;

// transactions bound (CSD-authoritative) to those programs
MATCH (c:Copybook {id: 'copybook:CSUSR01Y'})<-[:INCLUDES]-(p:Program)
      <-[:IS_TRANSACTION_FOR]-(t:CICSTransaction)
RETURN DISTINCT t.id AS transaction_id, p.id AS program_id
ORDER BY transaction_id;

// maps sent by those programs (literal-form only; partial placeholders excluded)
MATCH (c:Copybook {id: 'copybook:CSUSR01Y'})<-[:INCLUDES]-(p:Program)-[:SENDS_MAP]->(m:BMSMap)
WHERE m.partial IS NULL OR m.partial = FALSE
RETURN DISTINCT p.id AS program_id, m.id AS map_id
ORDER BY program_id, map_id;

// related logical files (this copybook DEFINES_LAYOUT_FOR — FD-context seed for wide impact)
MATCH (c:Copybook {id: 'copybook:CSUSR01Y'})-[:DEFINES_LAYOUT_FOR]->(lf:LogicalFile)
RETURN lf.id AS logical_file_id, lf.name AS name
ORDER BY logical_file_id;
