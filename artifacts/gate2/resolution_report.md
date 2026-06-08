# Resolution Report

- run_id: `gate2-pilot-20260513T160445Z`
- schema_version: `1.0.0`
- extractor_version: `0.1.0`
- entities: **182**
- edges: **222**
- conflict-ledger entries: **1**
- unresolved/partial records: **55**

## Merge decisions

- `bms-mapset:COSGN00` — merged from 2 observations, rules: RUL-BMS-001, RUL-CSD-003, sources: corpus/carddemo/stripped/app/bms/COSGN00.bms, corpus/carddemo/stripped/app/csd/CARDDEMO.CSD
- `dataset:AWS.M2.CARDDEMO.ACCTDATA.VSAM.KSDS` — merged from 2 observations, rules: RUL-CSD-004, RUL-JCL-004, sources: corpus/carddemo/stripped/app/csd/CARDDEMO.CSD, corpus/carddemo/stripped/app/jcl/POSTTRAN.jcl
- `dataset:AWS.M2.CARDDEMO.CARDXREF.VSAM.KSDS` — merged from 4 observations, rules: RUL-CSD-004, RUL-JCL-004, sources: corpus/carddemo/stripped/app/csd/CARDDEMO.CSD, corpus/carddemo/stripped/app/jcl/POSTTRAN.jcl, corpus/carddemo/stripped/app/jcl/TRANREPT.jcl, corpus/carddemo/stripped/app/proc/TRANREPT.prc
- `dataset:AWS.M2.CARDDEMO.DATEPARM` — merged from 2 observations, rules: RUL-JCL-004, sources: corpus/carddemo/stripped/app/jcl/TRANREPT.jcl, corpus/carddemo/stripped/app/proc/TRANREPT.prc
- `dataset:AWS.M2.CARDDEMO.LOADLIB` — merged from 3 observations, rules: RUL-JCL-004, sources: corpus/carddemo/stripped/app/jcl/POSTTRAN.jcl, corpus/carddemo/stripped/app/jcl/TRANREPT.jcl, corpus/carddemo/stripped/app/proc/TRANREPT.prc
- `dataset:AWS.M2.CARDDEMO.TRANCATG.VSAM.KSDS` — merged from 2 observations, rules: RUL-JCL-004, sources: corpus/carddemo/stripped/app/jcl/TRANREPT.jcl, corpus/carddemo/stripped/app/proc/TRANREPT.prc
- `dataset:AWS.M2.CARDDEMO.TRANREPT` — merged from 2 observations, rules: RUL-JCL-004, sources: corpus/carddemo/stripped/app/jcl/TRANREPT.jcl, corpus/carddemo/stripped/app/proc/TRANREPT.prc
- `dataset:AWS.M2.CARDDEMO.TRANSACT.BKUP` — merged from 4 observations, rules: RUL-JCL-004, sources: corpus/carddemo/stripped/app/jcl/TRANREPT.jcl, corpus/carddemo/stripped/app/proc/TRANREPT.prc
- `dataset:AWS.M2.CARDDEMO.TRANSACT.DALY` — merged from 4 observations, rules: RUL-JCL-004, sources: corpus/carddemo/stripped/app/jcl/TRANREPT.jcl, corpus/carddemo/stripped/app/proc/TRANREPT.prc
- `dataset:AWS.M2.CARDDEMO.TRANSACT.VSAM.KSDS` — merged from 4 observations, rules: RUL-CSD-004, RUL-JCL-004, sources: corpus/carddemo/stripped/app/csd/CARDDEMO.CSD, corpus/carddemo/stripped/app/jcl/POSTTRAN.jcl, corpus/carddemo/stripped/app/jcl/TRANREPT.jcl, corpus/carddemo/stripped/app/proc/TRANREPT.prc
- `dataset:AWS.M2.CARDDEMO.TRANTYPE.VSAM.KSDS` — merged from 2 observations, rules: RUL-JCL-004, sources: corpus/carddemo/stripped/app/jcl/TRANREPT.jcl, corpus/carddemo/stripped/app/proc/TRANREPT.prc
- `dataset:NULLFILE` — merged from 2 observations, rules: RUL-JCL-004, sources: corpus/carddemo/stripped/app/proc/REPROC.prc
- `jcl-proc:REPROC` — merged from 2 observations, rules: RUL-JCL-PROC-001, sources: corpus/carddemo/stripped/app/proc/REPROC.prc, corpus/carddemo/stripped/app/proc/TRANREPT.prc
- `jcl-step:TRANREPT/STEP05R` — merged from 2 observations, rules: RUL-JCL-002, sources: corpus/carddemo/stripped/app/jcl/TRANREPT.jcl
- `program:COACTUPC` — merged from 2 observations, rules: RUL-COBOL-001, RUL-CSD-002, sources: corpus/carddemo/stripped/app/cbl/COACTUPC.cbl, corpus/carddemo/stripped/app/csd/CARDDEMO.CSD
- `program:COCRDLIC` — merged from 2 observations, rules: RUL-COBOL-001, RUL-CSD-002, sources: corpus/carddemo/stripped/app/cbl/COCRDLIC.cbl, corpus/carddemo/stripped/app/csd/CARDDEMO.CSD
- `program:COSGN00C` — merged from 2 observations, rules: RUL-COBOL-001, RUL-CSD-002, sources: corpus/carddemo/stripped/app/cbl/COSGN00C.cbl, corpus/carddemo/stripped/app/csd/CARDDEMO.CSD

## Conflict ledger

### Conflict — `jcl-proc:REPROC` (proc_name_collision)

- **rule:** `RUL-RES-006`
- **description:** Multiple source files declare the same PROC canonical id `jcl-proc:REPROC`. Per RUL-RES-006, the declared name on the `//<name> PROC` line is authoritative over filename. All sources retained as provenance; an entity is materialized with merged provenance; downstream `USES_PROC` edges point to this canonical id. Filename-mismatch source flagged.
- **competing sources:**
  - `corpus/carddemo/stripped/app/proc/REPROC.prc` (filename_mismatch=False)
  - `corpus/carddemo/stripped/app/proc/TRANREPT.prc` (filename_mismatch=True)
- **resolution:** Primary: corpus/carddemo/stripped/app/proc/REPROC.prc; alternates: ['corpus/carddemo/stripped/app/proc/TRANREPT.prc']. Conflict retained for human review; entity created with merged provenance.
