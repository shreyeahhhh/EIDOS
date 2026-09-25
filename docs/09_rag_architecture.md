# 09 — Agentic RAG Architecture

**Status:** DERIVED — **V1.3 (decisions.md D-208 to D-220, 2026-09-25) assigns the knowledge/evidence layer only (§9); only the pure structures and the evidence ledger are implemented (Steps 2 and 3: identity, chunking, the snapshot, the independent-source count, evidence records, the ledger and the mapping of V1.2 documents). The agentic loop, reranking, the evidence judge and Qdrant stay deferred and unassigned (D-184).**
**Derived from:** handoff §24, §25, §26, §31, §33, §50, §51, §63, §74, §76
**Authority:** This document is derived from `EIDOS_CLAUDE_CODE_HANDOFF.md` and subordinate to it.
If this document and the handoff conflict, stop and report the conflict to the human owner.

> **Only the pure structures and the evidence ledger of §9 are implemented** (`eidos.knowledge`, V1.3 Steps 2 and 3); nothing else in this document is. There is no retrieval, no Qdrant, no
> embedding model, no reranker and no dependency for any of them. §50 named this V0.8 in the
> handoff's own original sequence; the owner has since redefined V0.8 as the Strategy Selector
> (`decisions.md` D-178 onward, V0.7 Step 1's own naming) and ruled, as **D-184**, that RAG is not
> renumbered into the V0.7–V1.0 strategy-intelligence sequence — it gets a milestone only when a
> concrete requirement or benchmark needs it. See `decisions.md` D-028, D-184.
>
> **Update (2026-09-25, D-208):** the concrete requirement now exists (the V1.2 limitation of D-207 reading 1) and the owner assigned the knowledge/evidence layer to **V1.3**, as a staged subset of this
> design. §9 records what was ruled. The package is `eidos.knowledge`, not `eidos.rag` (D-219).

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
collections serve the strategy-memory work (V1.0, and any later learning work), not document retrieval.

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
cross-encoder / reranker, local Qdrant. No paid API. **V1.3 (D-208, D-214, D-220):** the first semantic candidate is a locally cached Sentence Transformer, run only in an isolated benchmark process; Qdrant and
the cross-encoder are not part of the first slice.

## 6. Evidence

The RAG layer produces the evidence that verification consumes. Two requirements constrain it:

- **Evidence lineage** (§74, invariant 16): conclusion → evidence → source → retrieval query →
  agent → tool → verification. The retrieval query must be recorded as part of the evidence, not
  discarded after use.
- **Evidence evaluation** is a distinct step from retrieval. §50 names an "evidence judge" as part
  of V0.8, and §33 names `EVIDENCE_REJECTED` as a structured event.

The reliability contract may require a minimum count of independent evidence items (§30), and
evidence coverage is one of the measurable quality proxies (§19).

**V1.3 (D-208, D-209, D-218, §9):** evidence is held in a typed `EvidenceLedger`; the retrieval query is recorded as `query_id` on the recorded retrieval facts and the citation edges are recorded, so the lineage above
can be walked from the log; independence is counted by declared source identity, not by reference strings. Evidence *evaluation* (the evidence judge, `EVIDENCE_REJECTED`) is not part of V1.3.

## 7. Required tests

§63's minimum failure-scenario list includes: bad retrieval, conflicting evidence.

`VERIFICATION_FAILED` following insufficient evidence, then a replan with additional retrieval, then
successful verification, is the flagship demo path (§43) and belongs in `tests/scenarios/`.

## 8. Prerequisites

| Prerequisite | Where |
|---|---|
| MCP tool boundary — retrieval is reached through `search_documents` / `retrieve_evidence` | `08_mcp_contract.md`. V1.2 implemented `search_documents` only; V1.3 reaches knowledge through a separate `KnowledgePort` seam, not the tool path (D-208, §9) |
| How evidence sufficiency is judged | `decisions.md` D-015 |
| Collection schemas | explicitly deferred by §25; V1.3 uses a pinned snapshot with a manifest instead of Qdrant collections (D-220) |

## 9. V1.3 — the knowledge/evidence layer (ruled 2026-09-25; the pure structures and the evidence ledger are implemented, nothing else)

Decisions D-208 to D-220 (`decisions.md`). This section describes what V1.3 will build; **only the pure structures and the evidence ledger exist** (Steps 1 to 3 are done: identity, chunking, the snapshot and the independent-source count in `eidos.knowledge`, evidence records and set-based resolution there, and the ledger and the V1.2 resolver in `eidos.agents.evidence_ledger`). Sections 1 to 8 remain the handoff-derived
specification of the full agentic design, of which V1.3 builds a staged subset.

**Scope (D-208).** Local documents only: ingestion, document and chunk identity, indexing, retrieval, source and provenance tracking, retrieval-query identity, evidence references, duplicate-source handling,
bounded retrieval, traceability into verification, and replay without the knowledge store. Excluded: web crawling and autonomous acquisition, LLM query planning, multiple knowledge agents, the
reformulate-and-retrieve-again loop of §2, reranking and an evidence judge, Qdrant, RAG chains, and any new plan step, agent or event type. The V1.2 contracts are consumed, not changed.

**The boundary.**

```text
ResearchAgent                            (integration begins only after the retrieval comparison is reviewed)
   -> KnowledgeAccess / KnowledgeGate    admission, duplicate service, bounds, the evidence ledger
        -> KnowledgePort                 retrieve(request) -> result | failure
             |- LexicalKnowledgePort
             '- SemanticKnowledgePort -> Embedder (the Sentence Transformer adapter lives only here)
                                       -> a derived vector index -> exact cosine search
   (later, only if a measured need justifies it: QdrantKnowledgePort)
```

`KnowledgePort` is a seam of its own, parallel to and independent of the V1.2 `ToolPort`. The package is `eidos.knowledge` (D-219) and stays independent of Qdrant, Sentence Transformers, BM25 and any specific
embedding model.

**The evidence model.** Source, document, chunk, retrieval result, evidence reference, conclusion. **A retrieval result is not automatically an independent source.** Retrieved evidence lives in a typed
`EvidenceLedger`, one per execution, and not in the supplied-artifact set: `put_supplied` is not the knowledge model (`decisions.md` D-207 reading 1). **Step 3 built it (D-224):** an `EvidenceRecord` is a chunk with its scheme, its snapshot and the sorted ids of the queries that retrieved it, and it re-derives its own chunk id; the ledger keeps one record per evidence reference, adds a query id when the same chunk is retrieved again, and refuses a different chunk under a held reference and the same chunk from another snapshot. A model still cites `[[ref]]`, and the citation is the one
model-asserted edge: traceable means the chain exists, not that the cited text supports the claim (D-015, Open).

**Identity (D-211, D-212).** No identifier depends on the query order, the plan, the execution, a random UUID or the wall clock.

| Id | Derived from |
|---|---|
| `source_id` | Declared in the manifest. Mandatory; no default is invented. |
| `document_id` | SHA-256 of the normalised document text. |
| `chunk_id` | SHA-256 of a version tag, `source_id`, `document_id`, `chunking_scheme_id`, the chunk boundaries and the chunk-text digest. |
| `query_id` | SHA-256 of the canonical retrieval request. |
| `evidence_ref` | Deterministic from `chunk_id`. |
| `snapshot_id` | The sorted source/document manifest and the scheme identifiers. |

**Independence (D-209).** Counted by declared source identity, content-derived document identity and declared `derived_from`. The same chunk retrieved again, several chunks of one document and several documents of
one declared source are one source; identical content under different declared sources is separate sources; known derived content can collapse through `derived_from`; undeclared derivation is not inferred, and no
semantic plagiarism detection is attempted. The resolver is pure and deterministic, and the verifier behaves byte-identically when none is supplied. D-221 (ruled 2026-09-25) confirmed it: different declared sources stay
distinct even for identical content, and `derived_from` applies to documents, is explicit only and is non-transitive. Step 2 implements it in `independent_sources` (D-223, reading 1): a cited document that
directly declares an origin which is also cited is set aside, and the distinct declared sources of the rest are counted. D-210 (ruled 2026-09-25): an existing V1.2 supplied or tool document receives a deterministic knowledge identity from its reference identity and normalised content, and the resolver maps old evidence into it without modifying any historical record. Step 3 implements it (`resolve_supplied_evidence`, D-224): a caller document's source is derived from its reference, a tool document's from the tool and the provider's own document id (the request digest takes no part), the document id is the digest of the normalised content, and the whole document is one chunk under the scheme `legacy-artifact-v1`. Independence is resolved over the set of cited evidence, not key by key, and the verifier is not changed.

**Bounds and the query (D-216, D-217).** Retrieval is bounded by per-knowledge-base configuration (`top_k`, a maximum result count, a maximum returned size); there is no new global retrieval budget. The Research
agent forms one deterministic query from the mission goal: no LLM query planning and no autonomous decomposition. This answers the loop question below for V1.3 only (D-029 stays Open).

**Recording and replay (D-218).** Additive fields on the existing `NODE_SETTLED` facts record `scheme_id`, `snapshot_id`, `query_id`, the outcome, the ordered hits (`chunk_id`, `document_id`, `source_id`, rank,
content digest, an optional score and its kind), the sizes and the elapsed time, plus the citation edges as a tuple. There is no new event; `RAG_SEARCH` and `EVIDENCE_REJECTED` stay unused. The existing replay
architecture stays authoritative: replay folds the recorded log and needs no store, index, embedder or knowledge package. As with tool facts, they are captured through `record_baseline` only (D-204 is unchanged).

**Retrieval technology and the benchmark (D-208, D-213 to D-215, D-220).** The retrieval method is chosen by measurement, not in advance. One frozen, English-only, gold-query fixture (a fictional facility: about 12
documents, 6 sources, 48 to 60 chunks, about 36 queries of which about 30 are frozen test queries) is run against lexical retrieval and Sentence Transformer semantic retrieval behind the same port. It includes
lexical-overlap, paraphrase, multi-source and distractor-bait queries, a byte-identical mirror under another source and an undeclared paraphrased copy, and is frozen before any result is observed, with nothing
tuned against the test set. Measures: Recall@1, Recall@3, Recall@5, MRR and source-coverage@k, plus latency, memory, dependency cost and reproducibility, from actual runs only. The semantic candidate is the
locally cached `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, pinned by revision and weight digest and run only in an isolated process in the existing Python 3.13 environment; it is not a runtime
dependency, and EIDOS stays on Python 3.12 (D-214). Its 128-token window is a hard bound: chunks are checked against the tokenizer's word-piece count and never silently truncated (D-215). The vector index is
derived from the pinned snapshot, rebuildable and not replay authority; Qdrant and approximate search are not part of the first slice (D-220). The cross-encoder is excluded.

**Determinism (D-220).** Deterministic: identifiers, normalisation, chunking, filtering, ordering and tie-breaking, and the replay of recorded retrieval. Potentially environment-dependent: embedding generation and
floating-point similarity (an informal probe saw vector bits move by about 3e-7 with the thread count and the batch shape on one machine). Bit-identical semantic retrieval across machines is not promised.

**Trust.** Retrieved text is data: it is never read as an instruction (invariant 3), and the knowledge layer cannot modify MissionState, tool permissions, strategy policy or budgets, bypass verification, or
execute tools. A retrieval outcome, like a tool outcome, is not evidence sufficiency (invariant 12).

---

## Open questions

| Id | Question |
|---|---|
| D-015 | How evidence sufficiency and verification confidence are computed. §24's "Enough?" branch is the same unanswered question as §31's confidence threshold |
| D-024 | Is the FAISS comparison an out-of-runtime experiment or a runtime abstraction with two backends? |
| D-016 | Retrieval confidence is listed as a quality proxy (§19) but not defined |
| — | Collection schemas — deferred by §25 itself |
| — | Which embedding model and which cross-encoder; chunking strategy; whether reranking is always applied or conditional. **V1.3 (D-208, D-213 to D-215):** the embedding model is chosen by a measured comparison, not in advance; the chunking scheme is part of chunk identity and stays within the semantic model's 128-token window; the cross-encoder and reranking are excluded from the first slice |
| — | The bound on retrieval rounds. `rag_rounds` is measured (§33) but no `max_rag_rounds` appears in the §14/§32 bound lists, so the reformulation loop in §2 has no stated termination limit. This needs an answer before implementation — it is the one loop in the handoff without an explicit bound. **V1.3 (D-216, D-217):** answered for the initial implementation only (per-knowledge-base bounds, one deterministic query, no loop); D-029 stays Open |
| D-210 | V1.3: how existing V1.2 supplied and tool documents are keyed for independence once a resolver exists. **Ruled 2026-09-25** (identity from the reference identity plus normalised content; nothing recorded is modified) and implemented at Step 3; the readings taken are D-224 (Open) |
| D-221 | V1.3: confirmation of the ruled independence rule. **Ruled 2026-09-25:** different declared sources stay distinct; `derived_from` is between documents, explicit and non-transitive |

## Out of scope for this document

The MCP boundary itself (`08_mcp_contract.md`), verification mechanics (`10_reliability.md`),
strategy memory (`11_evaluation.md`).
