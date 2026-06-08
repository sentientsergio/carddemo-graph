// Q2 — Dataset access.
// Contract: which programs and JCL steps touch a dataset, with mode. Per-program
// call-site mode comes from the COBOL/CICS access verb (READS/WRITES/UPDATES/
// DELETES/STARTS_BROWSE) over the LogicalFile -> BINDS_TO -> Dataset chain;
// per-JCL-step access comes from USES_DATASET (DISP + DD role).
// Sample input: dataset:AWS.M2.CARDDEMO.USRSEC.VSAM.KSDS. Substrate: kuzu (spec v4.1).
// Mirrors carddemo_graph.pilot.run_q2_sample (the validated Gate-3 runner).

// program_access — programs that access the dataset via the BINDS_TO chain
MATCH (p:Program)-[r:READS|WRITES|UPDATES|DELETES|STARTS_BROWSE]->(lf:LogicalFile)
      -[b:BINDS_TO]->(d:Dataset {id: 'dataset:AWS.M2.CARDDEMO.USRSEC.VSAM.KSDS'})
RETURN p.id AS program_id, lf.id AS logical_file_id, b.dd_name AS dd_name,
       label(r) AS mode, r.source_path AS source_path, r.start_line AS line
ORDER BY program_id, line;

// jcl_access — JCL steps that allocate the dataset via USES_DATASET
MATCH (s:JCLStep)-[u:USES_DATASET]->(d:Dataset {id: 'dataset:AWS.M2.CARDDEMO.USRSEC.VSAM.KSDS'})
RETURN s.id AS jcl_step, u.dd_name AS dd_name,
       u.allocation_disposition AS allocation_disposition,
       u.source_path AS source_path, u.start_line AS line
ORDER BY jcl_step;
