# Clustering Report (Q5 — informational)

Per spec §Q5: cluster CardDemo programs by shared data access; surface bounded-context candidates, straddle programs, and cross-cluster edges. **Informational only — not gold-asserted.**

Source: Gate 3 full-tree extraction (`gate3-fulltree-2026-05-13`).

## 1. Methodology

The clustering uses the bipartite Program ↔ Dataset projection derived from the skeleton graph:

- For each Program, compute its accessed-Dataset set by chaining:
  - **Online side:** Program → `READS`/`WRITES`/`UPDATES`/`DELETES`/`STARTS_BROWSE` → LogicalFile → `BINDS_TO` → Dataset
  - **Batch side:** Program ← `INVOKES` ← JCLStep → `USES_DATASET` → Dataset
- Group programs by naming-convention domain prefix (CB* / CO* with inner 3-letter token: ACT/CRD/TRN/USR/BIL/RPT/MEN/ADM/SGN/CUS/EXP/IMP/STM)
- For each cluster, compute its "canonical dataset set" = datasets touched by ≥2 programs in the cluster
- Straddle programs: those whose accessed datasets intersect canonical sets of clusters other than their own

This is a deliberately simple heuristic for v1 — it surfaces candidate boundaries from observed access patterns without requiring richer domain knowledge. Spectral / community-detection algorithms would be a v1.1 refinement.

**Plumbing-dataset filter applied:** `LOADLIB` (the load-module library, attached as STEPLIB DD by virtually every batch job) and other near-universal datasets create spurious straddles. The first-pass output without filtering shows 15 straddle programs; after excluding LOADLIB-only ties, 5 genuine straddles remain. Both views are reported below.

## 2. Candidate clusters

21 programs with non-empty dataset access fall into 9 naming-convention clusters:

| Cluster | Programs (count) | Canonical datasets (touched by ≥2 programs in cluster) |
|---|---|---|
| **account** | CBACT01C, CBACT02C, CBACT03C, CBACT04C (4) | ACCTDATA.VSAM.KSDS, CARDXREF.VSAM.KSDS, CARDDATA.VSAM.KSDS, LOADLIB |
| **transaction** | CBTRN02C, CBTRN03C, COTRN00C, COTRN01C, COTRN02C (5) | TRANSACT.VSAM.KSDS, ACCTDATA.VSAM.KSDS, CARDXREF.VSAM.KSDS, CARDXREF.AIX.PATH, TCATBALF.VSAM.KSDS, TRANCATG.VSAM.KSDS, TRANTYPE.VSAM.KSDS, LOADLIB |
| **user** | COUSR00C, COUSR01C, COUSR02C, COUSR03C (4) | USRSEC.VSAM.KSDS |
| **export-import** | CBEXPORT, CBIMPORT (2) | ACCTDATA.VSAM.KSDS, CARDDATA.VSAM.KSDS, CARDXREF.VSAM.KSDS, CUSTDATA.VSAM.KSDS, TRANSACT.VSAM.KSDS, LOADLIB, ACCTDATA.IMPORT, CARDXREF.IMPORT, CUSTDATA.IMPORT, TRANSACT.IMPORT, EXPORT.DATA, IMPORT.ERRORS |
| **billing** | COBIL00C (1) | — (single-program cluster) |
| **customer** | CBCUS01C (1) | — |
| **signon** | COSGN00C (1) | — |
| **statement** | CBSTM03A (1) | — |
| **other** | COBSWAIT, COCALL01 (2) | LOADLIB only |

**Reading:** the account / transaction / user clusters are the clear bounded-context candidates — each has multiple programs operating on a shared dataset core. export-import is a true "bulk plumbing" cluster that touches everything by design. The single-program clusters (billing, customer, signon, statement) are interesting precisely BECAUSE they're singletons — each is a likely seam where one program bridges multiple domains.

## 3. Straddle programs

A straddle program accesses datasets belonging to clusters other than its own. Two filtering modes:

### 3.1 Unfiltered (includes LOADLIB plumbing)

15 of 21 programs would qualify, most via LOADLIB STEPLIB ties only. The signal-to-noise is poor:

```
account:        CBACT01C, CBACT02C, CBACT03C, CBACT04C — all touch LOADLIB (which exists in every other cluster too)
transaction:    CBTRN02C, CBTRN03C — same LOADLIB story + real ACCTDATA/CARDXREF
billing:        COBIL00C → account, transaction (real)
customer:       CBCUS01C → all (only via LOADLIB)
signon:         COSGN00C → user (real)
export-import:  CBEXPORT, CBIMPORT → many (largely real, bulk crosses all domains)
statement:      CBSTM03A → all (mixed: real ACCTDATA + plumbing LOADLIB)
other:          COBSWAIT, COCALL01 → all (only via LOADLIB)
```

### 3.2 Filtered (excluding LOADLIB-only ties)

**5 genuine straddle programs:**

| Program | Own cluster | Touches | Datasets shared (excluding LOADLIB) |
|---|---|---|---|
| **COBIL00C** | billing | account, transaction | `ACCTDATA.VSAM.KSDS` (from account); `TRANSACT.VSAM.KSDS` (from transaction) — billing reads account balance and writes transaction events |
| **COSGN00C** | signon | user | `USRSEC.VSAM.KSDS` (from user) — sign-on validates against the user-security store that the user CRUD screens own |
| **COTRN02C** | transaction | account | `CARDXREF.VSAM.KSDS` (from account) — transaction display joins the card-to-account cross-reference |
| **CBEXPORT** | export-import | account, transaction | `ACCTDATA.VSAM.KSDS`, `CARDXREF.VSAM.KSDS`, `TRANSACT.VSAM.KSDS` — bulk export by definition crosses |
| **CBSTM03A** | statement | account, transaction | `ACCTDATA.VSAM.KSDS`, `CARDXREF.VSAM.KSDS` — statements join account + card-xref data |

**Reading:** all 5 are genuine bounded-context seams. COBIL00C and CBSTM03A are particularly interesting — both are operationally important programs (billing, statement generation) that compose multiple bounded contexts. In a modernization target like Spring Boot, each would naturally become an *orchestration* service that depends on the bounded-context services (Account, Transaction, Customer) rather than living *inside* any one of them.

## 4. Cross-cluster edges (data-only)

Datasets that span ≥2 clusters' canonical sets:

| Dataset | Clusters | Interpretation |
|---|---|---|
| ACCTDATA.VSAM.KSDS | account, transaction, billing*, statement*, export-import | The account record is the most-shared resource. account owns it; everyone else reads it. |
| CARDXREF.VSAM.KSDS | account, transaction, statement*, export-import | Card-to-account cross-reference; account owns conceptually but transaction-domain programs read it heavily for card-based queries. |
| TRANSACT.VSAM.KSDS | transaction, billing*, statement*, export-import | Transaction is the source-of-truth for transactional events; billing/statement read for derived views. |
| CARDDATA.VSAM.KSDS | account, export-import | Card master data; account-domain owns. |
| CUSTDATA.VSAM.KSDS | customer*, statement*, export-import | Customer master data; customer-domain owns. |

(\*) = touched by a single-program cluster; the share is more about the single program straddling than a multi-program ownership claim.

**Hypothesized seams** for a Java/Spring Boot modernization:
- An `AccountService` owns ACCTDATA + CARDDATA + CARDXREF; exposes read API for transaction, billing, statement contexts.
- A `TransactionService` owns TRANSACT + TCATBALF + TRANCATG + TRANTYPE; exposes write API for billing and read API for statement.
- A `UserService` owns USRSEC; exposes auth API for SignOnService.
- A `CustomerService` owns CUSTDATA.
- Orchestration services (Billing, Statement, Sign-on, Bulk-Export) call into the above.

This is observed-pattern reasoning, not a commitment — modernization decisions involve operational constraints not visible in the data graph alone.

## 5. Limitations

- **Heuristic clustering.** The naming-convention grouping happens to work well for CardDemo because the program naming is principled. A real codebase with messier naming would need genuine community detection (e.g., Louvain modularity on the bipartite projection).
- **Plumbing-dataset filter is corpus-specific.** `LOADLIB` is the obvious one to exclude here. A general approach would compute datasets that appear in ≥N clusters and treat them as plumbing; this report applies that judgment manually.
- **MOVE-chain XCTL targets are not modeled.** Online programs' inter-screen navigation flows through `unresolved:CDEMO-TO-PROGRAM` (per the skeleton/enrichment principle). The functional call graph of online flows is therefore deferred to Pass-2 enrichment. The data-access view here is unaffected (datasets are accessed within each program's body deterministically).
- **No temporal clustering.** Two programs that read the same dataset at different lifecycle phases (e.g., batch load vs. real-time query) appear in the same cluster. Real bounded-context analysis would distinguish.
- **Single-program clusters are noise-amplifiers.** With only one program in a cluster, "canonical dataset set" is undefined and the cluster's identity is fragile. v1 reports them as separate clusters for completeness; modernization analysis would likely merge them with their primary collaborator.
