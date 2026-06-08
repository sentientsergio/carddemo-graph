# Gate 4 — Downstream-Agent Trial Protocol (Acceptance Test B)

**Status:** harness prepared 2026-05-28. The actual agent RUN is a separate spawn — this document is the brief, the run conditions, and the scoring sheet. It does not itself run the trial.

**Prerequisite:** Gate 3 closed and Acceptance Test A green (33 MATCH / 0 DIFF / 3 known-incremental against `gold/gold_set.md`, on both the Gate-3 db and the packet db, as of commit `a689b9c`).

---

## 1. Purpose (what Gate 4 tests)

Acceptance Test B: **is the knowledge base rich enough that a fresh downstream agent can produce useful modernization analysis from the packet alone — without reading source?** Gate 4 tests the KB's sufficiency, not the extractor's correctness (that's Gate 3 / Test A). A failure here is traced to a *KB shortfall* vs an *agent-prompting* problem (see §6).

---

## 2. Inputs — the packet, and ONLY the packet

The trial agent receives `artifacts/agent_packet/` as its **sole** input:

```
README.md            kb_capabilities.md   graph_summary.md     known_unknowns.md
query_examples.md    entities.json        edges.json           enrichments.json
carddemo_graph.db    resolution_report.md
```

**Packet-only constraint (do NOT relax — it is the whole point of the test):**
- The agent may NOT access the upstream CardDemo source, the stripped corpus, the strip pipeline, `src/`, `queries/`, the gold set, or any repo artifact outside the packet.
- Enforcement for the run spawn: copy `artifacts/agent_packet/` into a fresh standalone working directory and start the trial agent there with no path access to the `carddemo-graph` repo (and/or deny-read rules for anything outside the packet dir). The `source_path` provenance strings inside the JSON/resolution_report are reference metadata for citation only — the agent must treat them as unreachable.
- The agent works in Cypher against `carddemo_graph.db` (rebuildable from the packet's `entities.json` + `edges.json` if needed) plus the packet markdown docs.

---

## 3. Target modernization stack (framing)

Per spec v4.1 §Gate 4, the sponsor's approved default:

**Java 21 + Spring Boot + Spring Batch + PostgreSQL (Aurora) + AWS-native orchestration** — Step Functions for inter-job sequencing, ECS Fargate for services, S3 for staging and GDG replacement.

---

## 4. Deliverables the trial agent must produce

1. **`operations_manual.md`** — how the *current* system runs, derived from the KB:
   - Runtime topology (online CICS transaction surface, batch JCL job/step surface, the data layer and its bindings).
   - Failure surfaces (where things break: unresolved/dynamic navigation, phantom/external programs, partial entities).
   - Change-safety surfaces (blast radius of touching a copybook / dataset / program — fan-in/fan-out, shared-data coupling).
2. **`modernization_strategy.md`** — how to move it to the target stack:
   - Architecture abstraction (CICS→services, JCL→Step Functions/Spring Batch, VSAM→Aurora, GDG→S3).
   - Decomposition candidates (bounded-context seams from Q5 shared-data clustering; straddle programs as orchestration services).
   - Sequencing (what to migrate first; dependency-aware ordering).
   - Risk-ranked unknowns (explicitly carry forward `known_unknowns.md`: DB2/IMS/MQ deferred subapps, MOVE-chain navigation, TS/TD queues, etc.).

---

## 5. Run conditions — the time-box

- **One bounded agent session.** The agent receives the framing prompt (§7) once, then works the packet to completion without human steering or re-prompting for more depth. Producing both deliverables in a single uninterrupted pass IS the test of packet sufficiency.
- **Suggested wall-clock cap: ~90 minutes** (adjustable by the sponsor). The cap exists to keep the trial a *sufficiency* test, not an endurance test; an agent that needs far longer is signalling a KB-richness or packet-orientation problem worth noting.
- No tool access beyond reading the packet + running Cypher against the packet db. No web, no source, no repo.

---

## 6. Scoring rubric (independent named reviewer; 3-point per dimension)

**Reviewer independence (required).** The Gate-4 reviewer must be **named and independent of the KB-builder** — i.e. the project sponsor (AT-issuer) and/or root (reviewer). It must **NOT** be the engineer chair that built this KB. The KB-builder grading whether its own KB is sufficient is a conflict of interest; Test B's entire value is an outside read on sufficiency, so the scoring is done by someone who did not build the extractor or the packet.

Each dimension scored **insufficient / adequate / strong**:

| # | Dimension | What "strong" looks like |
|---|---|---|
| 1 | **Grounding** | Claims cite KB entities/edges/provenance, not unsupported intuition |
| 2 | **Coverage** | Addresses online, batch, data, CICS, JCL, BMS surfaces where applicable |
| 3 | **Unknown handling** | Explicitly lists unresolved/dynamic/unsupported surfaces (uses `known_unknowns.md`) rather than guessing |
| 4 | **Modernization usefulness** | Concrete seams, risks, sequencing, non-translatable constructs against the named target |
| 5 | **Operational usefulness** | Explains runtime topology, failure surfaces, change-safety surfaces |
| 6 | **Hallucination control** | No invented programs, datasets, transactions, maps, jobs (quoting `unresolved:*` / partial entities is correct, not a violation) |
| 7 | **Reviewer judgment** | Each section "useful enough to guide the next analysis" |

---

## 7. Framing prompt (hand this to the trial agent verbatim)

> You are a modernization analyst. Your sole input is the attached `agent_packet/` — an evidence-grounded knowledge graph of the AWS CardDemo mainframe application (COBOL/JCL/BMS/CICS/VSAM). **You may not access the source code, the corpus, or anything outside this packet.** Read `README.md` then `kb_capabilities.md` first; use `known_unknowns.md` to flag gaps rather than guessing; load `carddemo_graph.db` into kuzu and query in Cypher (`query_examples.md` shows patterns). Every factual claim must cite KB entities/edges with their provenance.
>
> Produce two documents grounded in this packet, targeting **Java 21 + Spring Boot + Spring Batch + PostgreSQL Aurora + AWS-native orchestration (Step Functions, ECS Fargate, S3)**:
> 1. `operations_manual.md` — runtime topology, failure surfaces, change-safety surfaces of the current system.
> 2. `modernization_strategy.md` — architecture abstraction, decomposition candidates, migration sequencing, risk-ranked unknowns.
>
> Where the KB does not know something, say so explicitly and cite `known_unknowns.md`. Do not invent program, dataset, transaction, map, or job names.

---

## 8. Acceptance criteria (gate exit)

**Precondition:** scoring is performed by the independent named reviewer per §6 (the sponsor and/or an independent reviewer) — never by the KB-builder chair.

Gate 4 **passes** when the reviewer scores:
- **adequate-or-better on all 7 dimensions**, AND
- **strong on at least 3**.

For any dimension scored *insufficient*, the reviewer must classify the cause:
- **KB shortfall** — the packet genuinely lacks the information (→ feeds back into the extractor/schema as a future-version requirement), or
- **Agent/prompting** — the information was in the packet but the agent didn't use it (→ not a KB failure; refine the framing prompt and note it).

Only KB-shortfall failures block the gate. The distinction is the point of Test B.

---

## 9. What the harness does NOT decide

- The run itself (a separate fresh-agent spawn) and the reviewer scoring are downstream of this document.
- Whether to proceed to v1.0 / open contributions is the sponsor's call after the trial.

---

_Harness prepared by engineer/carddemo-graph, 2026-05-28. Target stack is the sponsor's approved default; time-box figure is a suggestion pending his confirmation._
