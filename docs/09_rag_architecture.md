# 09 — Agentic RAG Architecture

**Status:** DERIVED — **DEFERRED to V0.8.** Specification only; nothing is implemented.
**Derived from:** handoff §24, §25, §26, §31, §33, §50, §51, §63, §74, §76
**Authority:** This document is derived from `EIDOS_CLAUDE_CODE_HANDOFF.md` and subordinate to it.
If this document and the handoff conflict, stop and report the conflict to the human owner.

> **Nothing in this document is implemented.** There is no `eidos.rag` package, no Qdrant, no
> embedding model, no reranker and no dependency for any of them. Per §50, this arrives at V0.8.
> See `decisions.md` D-028.

---

## 1. Not basic RAG

EIDOS must **not** use only:

```text
question -> embedding -> vector search -> LLM
```

That is basic RAG (§24).

## 2. The intended flow

```text
Information required
        -> Determine what is missing
        -> Generate retrieval strategy
        -> Retrieve
        -> Rerank
        -> Evaluate evidence
        -> Enough?
             NO -> Reformulate -> Retrieve again
             YES -> Continue
```

The defining property: **retrieval itself becomes part of execution planning** (§24). Retrieval
strategy is one of the strategy factors in §17, and `rag_rounds` is a measured per-mission quantity
in §33.

## 3. Qdrant's role

Qdrant is the planned local vector database (§25). It should support:

```text
document retrieval
knowledge memory
historical task memory
strategy memory
performance-related retrieval
```

> **Do not assume Qdrant is only for PDF chunks.** (§25)

Potential conceptual collections:

```text
knowledge
tasks
strategies
executions
evidence
```

The handoff states explicitly that **the exact schema should be designed later.** It is therefore
not specified here, and must not be invented in passing.

Note the overlap with strategy memory (`11_evaluation.md`): the `strategies` and `executions`
collections serve the V1.0/V1.1 strategy-memory work, not document retrieval.

## 4. FAISS

FAISS can be useful as an **experimental baseline** (§26). A potential experiment compares FAISS and
Qdrant on retrieval latency, memory, filtering capability, setup complexity, and behaviour at
different corpus sizes.

Qdrant is preferred for the actual architecture because it behaves more like a vector database with
metadata and filtering concerns, and **Qdrant is the default**.

> **Do not introduce both into the core runtime unless there is a clear research reason.** (§26)

The natural reading is that the comparison lives outside the core runtime as an experiment rather
than as a runtime abstraction with two backends — but that is a reading, not a statement. See
`decisions.md` **D-024**.

## 5. Local components

From §51 and §76, all local and zero-cost: sentence-transformers for embeddings, a local
cross-encoder / reranker, local Qdrant. No paid API.

## 6. Evidence

The RAG layer produces the evidence that verification consumes. Two requirements constrain it:

- **Evidence lineage** (§74, invariant 16): conclusion → evidence → source → retrieval query →
  agent → tool → verification. The retrieval query must be recorded as part of the evidence, not
  discarded after use.
- **Evidence evaluation** is a distinct step from retrieval. §50 names an "evidence judge" as part
  of V0.8, and §33 names `EVIDENCE_REJECTED` as a structured event.

The reliability contract may require a minimum count of independent evidence items (§30), and
evidence coverage is one of the measurable quality proxies (§19).

## 7. Required tests

§63's minimum failure-scenario list includes: bad retrieval, conflicting evidence.

`VERIFICATION_FAILED` following insufficient evidence, then a replan with additional retrieval, then
successful verification, is the flagship demo path (§43) and belongs in `tests/scenarios/`.

## 8. Prerequisites

| Prerequisite | Where |
|---|---|
| MCP tool boundary — retrieval is reached through `search_documents` / `retrieve_evidence` | `08_mcp_contract.md`, V0.7 |
| How evidence sufficiency is judged | `decisions.md` D-015 |
| Collection schemas | explicitly deferred by §25 |

---

## Open questions

| Id | Question |
|---|---|
| D-015 | How evidence sufficiency and verification confidence are computed. §24's "Enough?" branch is the same unanswered question as §31's confidence threshold |
| D-024 | Is the FAISS comparison an out-of-runtime experiment or a runtime abstraction with two backends? |
| D-016 | Retrieval confidence is listed as a quality proxy (§19) but not defined |
| — | Collection schemas — deferred by §25 itself |
| — | Which embedding model and which cross-encoder; chunking strategy; whether reranking is always applied or conditional |
| — | The bound on retrieval rounds. `rag_rounds` is measured (§33) but no `max_rag_rounds` appears in the §14/§32 bound lists, so the reformulation loop in §2 has no stated termination limit. This needs an answer before implementation — it is the one loop in the handoff without an explicit bound |

## Out of scope for this document

The MCP boundary itself (`08_mcp_contract.md`), verification mechanics (`10_reliability.md`),
strategy memory (`11_evaluation.md`).
