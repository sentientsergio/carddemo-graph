# carddemo-graph in action

This page shows the thing the README describes: a working query engine over a legacy mainframe codebase, answering modernization and maintenance-planning questions from an evidence-grounded graph instead of from the source.

Every query below was run against the shipped graph database (`artifacts/agent_packet/carddemo_graph.db`) in Cypher. The results are the actual output, not illustrations. Each answer traces back to source lines through the graph's provenance, and the engine reports what it could not determine rather than guessing.

The reference corpus is [AWS CardDemo](https://github.com/aws-samples/aws-mainframe-modernization-carddemo) — a representative COBOL/JCL/BMS/CICS/VSAM application. CardDemo is the demonstration vehicle, not the point; the point is the extraction-and-query method, which is built to carry to other codebases of the same class through a per-corpus adaptation pass.

---

## 1. Change-impact: what does this record layout touch?

A maintenance planner's first question before touching shared data: who depends on it? The account-record copybook `CVACT01Y` defines the layout of the account master. Which programs would a change to it ripple into?

```cypher
MATCH (p:Program)-[:INCLUDES]->(c:Copybook {id: 'copybook:CVACT01Y'})
RETURN p.id AS program ORDER BY program;
```

```
program:CBACT01C   program:CBACT04C   program:CBEXPORT   program:CBIMPORT
program:CBSTM03A   program:CBTRN01C   program:CBTRN02C   program:COACTUPC
program:COACTVWC   program:COBIL00C   program:COTRN02C
```

Eleven programs — and the engine knows which of them are reachable from a user-facing transaction, in the same traversal:

```cypher
MATCH (t:CICSTransaction)-[:IS_TRANSACTION_FOR]->(p:Program)-[:INCLUDES]->(:Copybook {id: 'copybook:CVACT01Y'})
RETURN t.id AS transaction, p.id AS program ORDER BY transaction;
```

```
transaction:CAUP → program:COACTUPC      transaction:CAVW → program:COACTVWC
transaction:CB00 → program:COBIL00C      transaction:CT02 → program:COTRN02C
```

Each `INCLUDES` and `IS_TRANSACTION_FOR` edge carries the source file and line it was extracted from, so the planner can jump straight to the `COPY CVACT01Y` statement in any of these programs.

## 2. A question the engine was never specifically built to answer

The documented query contracts (Q1–Q5) are exemplars, not the limit of what the graph can answer — Q1–Q4 held to hand-traced ground truth, Q5 illustrative. Because the graph carries field-level record layouts with suggested target column types, you can ask a question no fixed query menu anticipated — for example, *which fields will need careful handling in a move to a relational store because they're stored as packed decimal?*

```cypher
MATCH (d:DataItem) WHERE d.usage = 'COMP-3'
RETURN d.copybook_id AS copybook, d.name AS field, d.picture AS pic,
       d.suggested_sql_type AS target_type
ORDER BY copybook, field;
```

```
copybook            field                        pic          target_type
CVEGG01Y            EGG-AMOUNT                   S9(10)V99    NUMERIC(12,2)
CVEXPORT            EXP-ACCT-CASH-CREDIT-LIMIT   S9(10)V99    NUMERIC(12,2)
CVEXPORT            EXP-ACCT-CURR-BAL            S9(10)V99    NUMERIC(12,2)
CVEXPORT            EXP-CUST-FICO-CREDIT-SCORE   9(03)        NUMERIC(3)
CVEXPORT            EXP-TRAN-AMT                 S9(09)V99    NUMERIC(11,2)
```

`COMP-3` is IBM packed decimal — a storage format that does not survive a naive byte copy into a SQL column. The engine locates every such field across the corpus and proposes the logical target type, turning a class of silent data-corruption bug into a checklist. The suggested type is advisory; the fact that the field is packed decimal is grounded.

## 3. Combining layers: decomposition planning

Two more questions, answered against different layers of the same graph in one traversal each.

Which datasets sit at the center of the application — the shared resources a decomposition has to plan around — and who writes them?

```cypher
MATCH (d:Dataset) WHERE d.centrality > 0
WITH d ORDER BY d.centrality DESC LIMIT 4
OPTIONAL MATCH (p:Program)-[:WRITES|UPDATES]->(:LogicalFile)-[:BINDS_TO]->(d)
WITH d, collect(DISTINCT p.id) AS writers
RETURN d.id AS dataset, d.centrality AS centrality, writers ORDER BY centrality DESC;
```

```
dataset                          centrality   writers
…ACCTDATA.VSAM.KSDS              0.33         [COBIL00C, COACTUPC]
…CARDXREF.VSAM.KSDS              0.29         []   (no direct program writer in this projection)
…TRANSACT.VSAM.KSDS              0.25         [COTRN02C, COBIL00C]
…CARDDATA.VSAM.KSDS              0.21         [COCRDUPC]
```

And which programs are the cross-context coupling risks — the ones whose data reach spans many others, so they resist being cleanly carved into a single service?

```cypher
MATCH (p:Program) WHERE p.straddle_score >= 0.4
RETURN p.id AS program, p.straddle_score AS coupling ORDER BY coupling DESC;
```

```
program:CBEXPORT   0.78      program:CBTRN02C   0.52
program:COTRN02C   0.48      program:CBSTM03A   0.48
program:CBACT04C   0.43      program:COBIL00C   0.43
```

`centrality` and `straddle_score` are derived deterministically from the access edges and recorded on the nodes — the planner reads them, rather than recomputing coupling by hand each time.

## 4. The engine knows what it does not know

This is the part that separates a grounded graph from a confident guesser. CardDemo's online screens navigate by moving a target program name into a variable and transferring control to it — a pattern the deterministic extractor cannot resolve to a destination without executing the program. Ask for the control-flow successors of the account-update transaction and the engine answers honestly:

```cypher
MATCH (t:CICSTransaction {id: 'transaction:CAUP'})-[:IS_TRANSACTION_FOR]->(p:Program)
      -[c:XCTLS_TO|CALLS|LINKS_TO]->(u:Program)
WHERE u.id STARTS WITH 'unresolved:'
RETURN p.id AS from_program, u.id AS unresolved_target,
       c.call_kind AS kind, c.breadcrumb AS breadcrumb;
```

```
from_program       unresolved_target              kind       breadcrumb
program:COACTUPC   unresolved:CDEMO-TO-PROGRAM     dynamic    CDEMO-TO-PROGRAM
```

The destination is an `unresolved:` placeholder, tagged `dynamic`, with the variable name preserved as a breadcrumb. A planner reading this knows exactly what's missing and why — the navigation target is runtime-determined — instead of being handed a fabricated edge. Unresolved references are emitted as first-class graph citizens, never dropped and never invented. The full inventory of what the extraction does not cover lives in [`artifacts/agent_packet/known_unknowns.md`](artifacts/agent_packet/known_unknowns.md).

## 5. The headline proof: planning from the graph alone

The queries above are hand-written. The real test is whether an agent can drive the graph to a useful planning deliverable on its own, without the source.

A fresh agent was given **only** the packet — the graph database, the JSON artifacts, and the capability and known-unknowns documents — with no access to the CardDemo source code. Working entirely in Cypher against the graph, it produced two documents:

- [`artifacts/gate4/operations_manual.md`](artifacts/gate4/operations_manual.md) — the as-built runtime topology: the online CICS surface, the batch JCL surface, the shared VSAM data layer they meet on, the failure surfaces, and the change-safety blast radius.
- [`artifacts/gate4/modernization_strategy.md`](artifacts/gate4/modernization_strategy.md) — a migration plan to a Java/Spring-on-AWS target stack: architecture mapping, decomposition candidates, sequencing, and a risk register.

Both documents hold to the same discipline the graph enforces. From the strategy's closing note:

> every structural fact above is skeleton-grounded (rule-derived, source-cited edges/entities at confidence 1.0) … No program, dataset, transaction, map, or job name in this document was invented; each appears in the KB or is an explicit `unresolved:*`/`partial` placeholder.

The trial ran against an earlier build of the graph and flagged the gaps it hit — among them, that program coupling had to be computed by hand because it wasn't yet a stored property. That gap is now closed: `straddle_score` and `centrality` (query 3) are computed and recorded, and the field-level layouts (query 2) were added in the same line of work. The engine grew toward the questions a planner actually asks.

---

## What this is, and what it is not

Stated plainly, so the demonstration isn't mistaken for more than it is:

- **Planning and analysis are demonstrated; code generation and execution are not.** The graph answers questions about the system and supports a migration plan. It does not run the application or emit modernized code.
- **It targets the class of legacy mainframe codebases, through a per-corpus adaptation pass — not "any codebase" zero-shot.** Applying it to a new system means a fresh corpus profile, schema review, golden-file pilot, then full-tree extraction, under the same discipline.
- **One corpus is proven end to end: CardDemo.** The method is built to generalize; that generalization is a claim the project intends to earn corpus by corpus, not one it has banked.
- **This is an engine on its way to being the core of a modernization-planning tool — not a finished tool.** What's demonstrated is the substrate and the query path, validated against hand-traced ground truth (Q1–Q4, traced independently of the extractor) and — for the field-level layer — a first-principles cold-agent read whose convergence with the extraction is *agreement, not proof*; a human COBOL expert would supersede it.

For how the graph is built — the three-pass extraction, the provenance model, the gate discipline — see the [README](README.md).
