// kuzu schema for carddemo-graph
//
// Per spec v4.1: kuzu is the executable substrate; the .db file is a build product
// of entities.json + edges.json, not a separate source of truth.
//
// Load-step responsibility: read entities.json/edges.json, INSERT node rows per entity
// type and relationship rows per edge type. Full provenance stays in the JSON; the kuzu
// schema captures enough provenance (rule_id, source_path, start_line, end_line) for
// `evidence_path` rendering in query results.
//
// This file is intended to be executed once per build:
//   kuzu carddemo_graph.db < artifacts/kuzu_schema.cypher
//
// The Python load step (src/carddemo_graph/loader/kuzu_load.py — Gate 2) issues these
// DDLs through the kuzu Python driver, then bulk-loads rows.

// ==============================================================================
// Node tables — one per Entity type in schema.json's EntityType enum
// ==============================================================================

CREATE NODE TABLE Program(
  id STRING,
  name STRING,
  partial BOOLEAN DEFAULT FALSE,
  asm_stub BOOLEAN DEFAULT FALSE,
  size_loc INT64,
  fan_in INT64,
  fan_out INT64,
  straddle_score DOUBLE,
  source_path STRING,
  rule_id STRING,
  PRIMARY KEY (id)
);
// `inferred_purpose` (LLM-derived) is NOT a Program column. It is enrichment, not
// skeleton. Pass-2 promotion writes inferred properties to the Enrichment node
// table (see end of this file) keyed by entity_id.

CREATE NODE TABLE Copybook(
  id STRING,
  name STRING,
  partial BOOLEAN DEFAULT FALSE,
  reuse_count INT64,
  source_path STRING,
  rule_id STRING,
  PRIMARY KEY (id)
);

CREATE NODE TABLE JCLJob(
  id STRING,
  name STRING,
  jcllib_search_path STRING,
  source_path STRING,
  rule_id STRING,
  PRIMARY KEY (id)
);

CREATE NODE TABLE JCLStep(
  id STRING,
  name STRING,
  job_id STRING,
  step_order INT64,
  source_path STRING,
  rule_id STRING,
  PRIMARY KEY (id)
);

CREATE NODE TABLE JCLProc(
  id STRING,
  name STRING,
  declared_name STRING,
  filename_mismatch BOOLEAN DEFAULT FALSE,
  default_params STRING,
  source_path STRING,
  rule_id STRING,
  PRIMARY KEY (id)
);

CREATE NODE TABLE JCLProcInvocation(
  id STRING,
  name STRING,
  job_id STRING,
  step_name STRING,
  invoked_proc_id STRING,
  bound_params STRING,
  source_path STRING,
  rule_id STRING,
  PRIMARY KEY (id)
);

CREATE NODE TABLE LogicalFile(
  id STRING,
  name STRING,
  program_id STRING,
  organization STRING,
  access_mode STRING,
  record_key STRING,
  alternate_record_keys STRING,
  assign_dd STRING,
  scope STRING,                       // 'batch' | 'cics'
  source_path STRING,
  rule_id STRING,
  PRIMARY KEY (id)
);

CREATE NODE TABLE Dataset(
  id STRING,
  name STRING,                        // normalized DSN
  partial BOOLEAN DEFAULT FALSE,
  organization STRING,
  centrality DOUBLE,
  gdg_offset STRING,
  unresolved_tokens STRING,
  rule_id STRING,
  PRIMARY KEY (id)
);
// `inferred_purpose` is enrichment, not skeleton — see Enrichment table below.

CREATE NODE TABLE BMSMapset(
  id STRING,
  name STRING,
  partial BOOLEAN DEFAULT FALSE,
  lang STRING,
  mode STRING,
  source_path STRING,
  rule_id STRING,
  PRIMARY KEY (id)
);

CREATE NODE TABLE BMSMap(
  id STRING,
  name STRING,
  partial BOOLEAN DEFAULT FALSE,
  mapset_id STRING,
  line_pos INT64,
  column_pos INT64,
  size_rows INT64,
  size_cols INT64,
  source_path STRING,
  rule_id STRING,
  PRIMARY KEY (id)
);

CREATE NODE TABLE BMSField(
  id STRING,
  name STRING,
  map_id STRING,
  mapset_id STRING,
  pos_row INT64,
  pos_col INT64,
  length INT64,
  attrb STRING,
  color STRING,
  initial_value STRING,
  prompt_value STRING,
  label STRING,
  is_filler BOOLEAN DEFAULT FALSE,
  source_path STRING,
  rule_id STRING,
  PRIMARY KEY (id)
);

CREATE NODE TABLE CICSTransaction(
  id STRING,
  name STRING,                        // 4-char TRANID
  partial BOOLEAN DEFAULT FALSE,
  description STRING,
  fan_out INT64,
  source_path STRING,
  rule_id STRING,
  PRIMARY KEY (id)
);

// Placeholder for unresolved references (per spec §Unresolved: "Never dropped").
// Holds dynamic-CALL identifiers, missing programs referenced only by CSD, etc.
CREATE NODE TABLE Unresolved(
  id STRING,                          // 'unresolved:<surface-form>'
  surface_form STRING,
  target_type_hint STRING,            // 'Program' | 'Dataset' | ...
  reason STRING,                      // 'phantom_csd' | 'dynamic_call' | 'external_le' | ...
  source_path STRING,
  rule_id STRING,
  PRIMARY KEY (id)
);

// DataItem — field-level COBOL record layout (v2.2 KU-9). One per data-description
// entry in a copybook record layout. `suggested_sql_type` is advisory (RUL-DERIV),
// not authoritative DDL. occurs/redefines are facts; interpretation is downstream.
CREATE NODE TABLE DataItem(
  id STRING,
  name STRING,
  level INT64,
  picture STRING,
  usage STRING,
  occurs INT64,
  redefines STRING,
  is_filler BOOLEAN DEFAULT FALSE,
  is_group BOOLEAN DEFAULT FALSE,
  suggested_sql_type STRING,
  parent_item STRING,
  copybook_id STRING,
  source_path STRING,
  rule_id STRING,
  PRIMARY KEY (id)
);

// ==============================================================================
// Relationship tables — one per EdgeType in schema.json, multi-typed where needed
// ==============================================================================

CREATE REL TABLE INCLUDES(
  FROM Program TO Copybook,
  FROM Copybook TO Copybook,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64,
  replacing_terms STRING,
  fd_context BOOLEAN DEFAULT FALSE
);

CREATE REL TABLE EXPANDS_TO(
  FROM JCLProcInvocation TO JCLStep,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64,
  step_order INT64
);

CREATE REL TABLE DEFINES_LAYOUT_FOR(
  FROM Copybook TO LogicalFile,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64
);

CREATE REL TABLE CALLS(
  FROM Program TO Program,
  FROM Program TO Unresolved,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64,
  call_kind STRING,                   // 'static' | 'dynamic'
  breadcrumb STRING
);

CREATE REL TABLE LINKS_TO(
  FROM Program TO Program,
  FROM Program TO Unresolved,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64,
  call_kind STRING,                   // 'static' (literal PROGRAM('NAME')) | 'dynamic' (identifier-form)
  breadcrumb STRING
);

CREATE REL TABLE XCTLS_TO(
  FROM Program TO Program,
  FROM Program TO Unresolved,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64,
  call_kind STRING,                   // 'static' (literal PROGRAM('NAME')) | 'dynamic' (identifier-form)
  breadcrumb STRING
);

CREATE REL TABLE RETURNS_TO_TRANSID(
  FROM Program TO CICSTransaction,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64
);

CREATE REL TABLE SENDS_MAP(
  FROM Program TO BMSMap,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64
);

CREATE REL TABLE RECEIVES_MAP(
  FROM Program TO BMSMap,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64
);

CREATE REL TABLE DECLARES_FILE(
  FROM Program TO LogicalFile,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64
);

CREATE REL TABLE BINDS_TO(
  FROM LogicalFile TO Dataset,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64,
  dd_name STRING,
  binding_source STRING               // 'JCL_DD' | 'CSD'
);

CREATE REL TABLE READS(
  FROM Program TO LogicalFile,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64,
  access_form STRING                  // 'COBOL_READ' | 'CICS_READ' | 'CICS_READNEXT' | 'CICS_READPREV'
);

CREATE REL TABLE WRITES(
  FROM Program TO LogicalFile,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64,
  access_form STRING
);

CREATE REL TABLE UPDATES(
  FROM Program TO LogicalFile,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64,
  access_form STRING
);

CREATE REL TABLE DELETES(
  FROM Program TO LogicalFile,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64,
  access_form STRING
);

CREATE REL TABLE STARTS_BROWSE(
  FROM Program TO LogicalFile,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64,
  access_form STRING
);

CREATE REL TABLE INVOKES(
  FROM JCLStep TO Program,
  FROM JCLStep TO Unresolved,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64
);

CREATE REL TABLE USES_DATASET(
  FROM JCLStep TO Dataset,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64,
  dd_name STRING,
  allocation_disposition STRING,
  inferred_access_mode STRING,
  inference_basis STRING
);

CREATE REL TABLE USES_PROC(
  FROM JCLStep TO JCLProc,
  FROM JCLProcInvocation TO JCLProc,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64
);

CREATE REL TABLE PASSES_SYSIN_TO(
  FROM JCLStep TO Dataset,
  FROM JCLStep TO Program,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64,
  utility STRING                      // 'IDCAMS' | 'SORT' | 'IEBGENER' | ...
);

CREATE REL TABLE IS_TRANSACTION_FOR(
  FROM CICSTransaction TO Program,
  FROM CICSTransaction TO Unresolved,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64
);

// Field-level record layout (v2.2 KU-9). HAS_FIELD: copybook -> its 01-level record
// roots; CONTAINS_ITEM: parent data item -> child (the level-number hierarchy).
CREATE REL TABLE HAS_FIELD(
  FROM Copybook TO DataItem,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64
);

CREATE REL TABLE CONTAINS_ITEM(
  FROM DataItem TO DataItem,
  confidence DOUBLE,
  evidence_kind STRING,
  rule_id STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64
);

// ==============================================================================
// Enrichment node table — LLM-inferred properties.
//
// Empty in v1. Pass-2's promotion step writes enriched property values here.
// `entity_id` is a foreign-key property pointing at the enriched entity's id
// (not a graph edge — graph edges would require N rel tables, one per entity
// type, and the traversal patterns aren't yet clear enough to commit). When
// Pass 2 is implemented and the join pattern stabilizes, this may evolve into
// a `HAS_ENRICHMENT` rel table.
//
// Loaders that want only the skeleton can skip this table entirely.
// ==============================================================================

CREATE NODE TABLE Enrichment(
  id STRING,
  entity_id STRING,
  property STRING,
  value STRING,
  evidence_kind STRING,               // always 'inferred'
  prompt_template_id STRING,
  source_observations STRING,         // JSON-encoded list of obs ids
  confidence DOUBLE,
  promotion_criteria STRING,
  source_path STRING,
  start_line INT64,
  end_line INT64,
  PRIMARY KEY (id)
);
