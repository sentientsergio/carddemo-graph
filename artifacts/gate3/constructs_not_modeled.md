# Constructs Not Modeled

Per spec §Out of scope and §Deferred extensions, the following constructs are observed in CardDemo (or in adjacent contexts) but **not** modeled in v1 base-mode extraction:

- COBOL paragraphs/sections (intra-program control flow) — out-of-scope per v1 design decisions
- DB2 EXEC SQL — needs-ext per spec §Deferred extensions
- DCLGEN copybooks (.dcl) — DB2 schema, not in v1 base mode
- DataItem (field-level) — out-of-scope per v1 design decisions
- EXEC CICS ABEND (operational; no closed-vocab edge)
- EXEC CICS ASKTIME / FORMATTIME (operational; no closed-vocab edge)
- EXEC CICS ASSIGN (operational; no closed-vocab edge)
- EXEC CICS HANDLE (operational; no closed-vocab edge)
- EXEC CICS INQUIRE (operational; no closed-vocab edge)
- EXEC CICS WRITEQ / READQ TS|TD (TS/TD queues; not in v1 closed vocab)
- IMS DBD/PSB — needs-ext per spec §Deferred extensions
- MQ EXEC MQ — needs-ext per spec §Deferred extensions
