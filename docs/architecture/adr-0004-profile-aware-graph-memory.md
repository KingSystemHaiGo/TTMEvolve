# ADR-0004: Profile-Aware Graph Memory (Cold Memory As A Typed-Edge Graph)

## 状态 / Status

Draft (Phase 0) — will move to Accepted after Phase A exit gate.

## 背景 / Context

TTMEvolve 当前 cold memory 是一组扁平的 JSON 记录（`storage/cold_memory/cold_index.json`），通过 `VectorIndex(namespace="cold_memory")` 索引，summary 被向量化后做 top-k 相似度搜索。`shared_outcome.py` 维护一份冲突账本和 verified-positive / regression / stale / misleading 的可见性规则。

Current TTMEvolve cold memory is a flat JSON record set indexed by a single `VectorIndex(namespace="cold_memory")`. `shared_outcome.py` already handles verified-positive promotion, regression/stale/misleading demotion, and unresolved conflict records.

The current shape has three concrete limits:

1. **No typed relationships.** Two memories can be near each other in vector space, but the system has no way to say "memory A caused memory B", "memory A contradicts memory B", or "memory A is decomposed into B + C". This blocks any multi-hop reasoning and any causal debugging of agent failures.
2. **No cross-memory joins.** A query that wants "all session outcomes after session X that reference a tool error" cannot be expressed against the flat list.
3. **No soft-delete / restore.** A bad record has no recovery path; either it lives forever or it must be hard-deleted.

The upgrade must:

- preserve the existing `VectorIndex`, `ColdMemory.search()`, and `SharedMemoryPolicy` semantics;
- add an additive, feature-flagged graph layer (`memory.graph.enabled`, default `false`);
- keep RAG benchmark and RAG quality evidence unproven-until-evaluated (existing tests `test_compact_rag_benchmark_keeps_production_quality_unproven_until_evaluated` and `test_production_embedding_quality_boundary_requires_real_quality_evidence` already enforce this);
- feed `engineering_control` and `project_control` evidence, not create a parallel dashboard.

## 决策 / Decision

Adopt a typed-edge graph memory layered **on top of** the existing flat cold memory, not as a replacement.

1. **New module `memory/graph.py`** with `MemoryNode`, `MemoryEdge`, `MemoryGraph`, and an `EDGE_TYPES` allowlist:
   ```python
   EDGE_TYPES = {
       "references", "supersedes", "contradicts", "supports",
       "caused_by", "temporal_next", "decomposes_into", "similar_to",
   }
   ```
2. **Storage additions** under `storage/cold_memory/`:
   - `cold_graph_nodes.jsonl` — append-only `MemoryNode` stream
   - `cold_graph_edges.jsonl` — append-only `MemoryEdge` stream
   - `cold_graph_tombstones.jsonl` — append-only soft deletes
   - `cold_graph_meta.json` — version, counts, last compaction timestamp
   - `graph_edges/` — second `VectorIndex` namespace `cold_memory_edges` for edge glue text
3. **Read-through integration.** `ColdMemory.__init__` instantiates `MemoryGraph` only when `memory.graph.enabled=true`. Existing `ColdMemory.search()` keeps its flat-vector behavior. A new `ColdMemory.retrieve_with_graph()` adds the typed-edge expansion.
4. **First-boot migration.** On first boot with the flag enabled, every entry in `cold_index.json` is mirrored into `cold_graph_nodes.jsonl` with default `bayes={alpha:1.0, beta:1.0}` and `soft_deleted=False`. No entry's id changes. The migration is one-way per session; subsequent writes are append-only.
5. **Edge creation rules (deterministic only in Phase A):**
   - Same `claim_key` + different summary → `supersedes` edge
   - Verified conflict → `contradicts` edge
   - Session outcome referencing a prior session id → `temporal_next` edge
6. **Scoring.** `MemoryGraph.retrieve()` ranks candidates by:
   ```
   final_score = 0.55 * vector_score
              + 0.20 * posterior
              + 0.10 * freshness_score
              + 0.10 * edge_support_score
              + 0.05 * occam_score
   ```
   When FAISS or the real encoder is unavailable, the report must say `fallback="keyword"` or `fallback="fake_encoder"` clearly — this is the same boundary already enforced by `memory/rag_quality.py`.
7. **Soft-delete / restore.** Pruning is a tombstone write, not a hard delete. Tombstoned nodes stay in `cold_graph_tombstones.jsonl` until compaction. `restore_node(id)` is a first-class operation.
8. **SharedMemoryPolicy stays authoritative.** Even if a node's `posterior` is high, promotion to `shared`/`public` only happens through `review_shared_memory_outcome()`. The graph layer never sets `visibility` directly.

## 后果 / Consequences

### Positive / 正面

- Cross-memory joins become possible (e.g., "all session outcomes after X that reference a tool error").
- Soft-delete and restore give operators a safety net when pruning misfires.
- Read-through design means existing tests and CLI flows keep working with `memory.graph.enabled=false`.
- The second `VectorIndex` namespace (`cold_memory_edges`) keeps the existing `cold_memory` namespace untouched, so FAISS storage is not forked.
- Evidence Bundle can carry `graph_recall` and `posterior_summary` fields that downstream surfaces (`engineering_control`, Workbench) can consume without inventing a new dashboard.

### Negative / 负面

- Three new JSONL files plus a second FAISS namespace means more disk and more startup work. Mitigated by `memory.graph.compact_after_nodes` (default 5000) and `edge_index_enabled` (default true, can be set false to skip edge indexing in dev).
- The deterministic edge-creation rules in Phase A are conservative. LLM-driven edge creation (à la A-MEM) is a possible follow-up, not Phase A.
- The graph layer is **not** a full GraphRAG / HippoRAG implementation. It is the storage and retrieval substrate those systems would build on. Calling this "graph RAG" without further work would overstate the claim.

### Compliance / 合规

- New tests: `tests/test_memory_graph.py`, `tests/test_memory_manager_graph_recall.py`, `tests/test_rag_performance.py` (extended).
- The four existing critical tests must continue to pass:
  - `test_compact_rag_benchmark_keeps_production_quality_unproven_until_evaluated`
  - `test_production_embedding_quality_boundary_requires_real_quality_evidence`
  - `test_embedding_quality_evaluation_missing_corpus_stays_unproven`
  - `test_cold_memory_bulk_index_preserves_profile_and_shared_policy`
- RAG benchmark `graph-on` p95 must be `<= 1.5x` `graph-off` p95 against the deterministic 10k fake corpus (this is the same shape the existing `test_rag_benchmark_fake_embeddings_meets_budget` already verifies for the flat path).

## 替代方案 / Alternatives Considered

- **Replace `ColdMemory` entirely with a graph store.** Rejected — would break every existing test, every existing evidence surface, and every existing skill that touches the flat index. Read-through is the smaller blast radius.
- **Use an external graph DB (Neo4j, Memgraph).** Rejected — the project explicitly avoids new infrastructure dependencies. JSONL + a second FAISS namespace is enough for Phase A.
- **LLM-driven edge extraction on every write.** Rejected for Phase A — adds a second LLM call per write and is hard to gate. May revisit after Phase A's deterministic rules prove the substrate.
- **Build only a "soft-delete" feature without a graph.** Rejected — soft-delete is part of the graph; standalone it does not justify the change.

## References / 引用

See `docs/research/2026-memory-and-control.md` for the full source list. The directly relevant ones:

- [GraphRAG paper](https://arxiv.org/abs/2404.16130) and [GraphRAG docs](https://microsoft.github.io/graphrag/)
- [GraphRAG DRIFT search docs](https://microsoft.github.io/graphrag/query/drift_search/)
- [HippoRAG paper](https://arxiv.org/abs/2405.14831)
- [LightRAG paper](https://arxiv.org/abs/2410.05779) and [LightRAG repo](https://github.com/HKUDS/LightRAG)
- [RAPTOR paper](https://arxiv.org/abs/2401.18059)
- [A-MEM paper](https://arxiv.org/abs/2502.12110)
- [Mem0 repo](https://github.com/mem0ai/mem0)
- [MemoryBank paper](https://arxiv.org/abs/2305.10250)
- [LLM-agent memory survey](https://arxiv.org/abs/2404.13501)

## 退出条件 / Exit Gate (Phase A)

- `memory.graph.enabled=false` keeps all existing tests passing.
- New `tests/test_memory_graph.py` covers: node/edge CRUD, load/save, graph cycles (visited set + `max_hops`), read policy, soft-delete, restore.
- First-boot mirror of `cold_index.json` into `cold_graph_nodes.jsonl` is a one-way operation that does not change ids.
- Evidence Bundle `graph_recall` is reported only when the flag is enabled.
