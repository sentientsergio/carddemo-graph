// Q4 — BMS map surface for transaction.
// Contract: from a CICS transaction, the entry program's BMS map interactions
// (direction), the mapsets owning those maps, and the visible field-label surface.
// Sample input: transaction:CC00. Substrate: kuzu (spec v4.1).
// Mirrors carddemo_graph.pilot.run_q4_sample (the validated Gate-3 runner).

// entry_program
MATCH (t:CICSTransaction {id: 'transaction:CC00'})-[:IS_TRANSACTION_FOR]->(p:Program)
RETURN p.id AS entry_program;

// map_interactions — maps sent/received by the entry program, with direction
MATCH (t:CICSTransaction {id: 'transaction:CC00'})-[:IS_TRANSACTION_FOR]->(p:Program),
      (p)-[r:SENDS_MAP|RECEIVES_MAP]->(m:BMSMap)
RETURN DISTINCT p.id AS program_id, m.id AS map_id, label(r) AS direction
ORDER BY program_id, map_id;

// mapsets — the mapsets owning those maps (BMSMap -> BMSMapset is via mapset_id property)
MATCH (t:CICSTransaction {id: 'transaction:CC00'})-[:IS_TRANSACTION_FOR]->(p:Program),
      (p)-[:SENDS_MAP|RECEIVES_MAP]->(m:BMSMap), (ms:BMSMapset)
WHERE ms.id = m.mapset_id
RETURN DISTINCT ms.id AS mapset_id, ms.name AS mapset_name
ORDER BY mapset_id;

// field_surface — visible field labels on those maps
MATCH (t:CICSTransaction {id: 'transaction:CC00'})-[:IS_TRANSACTION_FOR]->(p:Program),
      (p)-[:SENDS_MAP|RECEIVES_MAP]->(m:BMSMap)
MATCH (f:BMSField) WHERE f.map_id = m.id AND f.label <> ''
RETURN DISTINCT m.id AS map_id, f.name AS field_name, f.label AS label
ORDER BY map_id, field_name;
