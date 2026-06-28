# 2026 记忆与控制方法论调研 / 2026 Memory And Control Methodology Survey

> **Status / 状态**: Draft for Phase 0 (will be re-verified after each implementation slice).
>
> **Audience / 读者**: TTMEvolve core contributors implementing the [RAG, Memory, Context, And Cybernetic Planning Plan](../architecture/architecture-control-roadmap-2026-06-27.md).
>
> **Scope / 范围**: Only sources with direct, verifiable links. Do not add unverified references from memory.

---

## How To Use This Document / 如何使用本文

Each entry lists:

- **Source** — direct link to the paper, official docs, or canonical repo.
- **Summary** — what the work actually does (one paragraph).
- **Applicability** — which TTMEvolve upgrade uses it and exactly how.
- **Limits** — what we explicitly do **not** claim from this source.

If a future design decision needs new evidence, add an entry here **only after** a working link is verified. Memory-only citations are out of policy.

---

## Baseline Evidence / 基线证据 (2026-06-28)

These are the gates every entry below must survive:

| Gate | Result | Source |
| --- | --- | --- |
| `test_rag_performance.py` + `test_runtime_contract.py` | **14 passed in 1.20s** | `docs/research/baseline/baseline-tests-2026-06-28.log` |
| `release_readiness --mode source-checkpoint` | `status: ready`, `blockers: []` | `docs/research/baseline/baseline-readiness-2026-06-28.json` |
| `production_rag_quality` | `status: unproven` (intentional) | same JSON, `checks.production_rag_quality` |
| `signed_installer` | `status: unproven` (intentional) | same JSON |
| `maker_remote_build` | `status: unproven` (intentional) | same JSON |
| `offline_runtime_bundle` | `status: blocked` (vendor 6.87GB > 500MB budget, out of scope) | same JSON |

These six gates are the contract this document defends. Any new entry that implies a different status must be re-evaluated against them.

---

## 1. Graph RAG / 图检索增强生成

### 1.1 GraphRAG (Microsoft, 2024)

- **Source:** [Paper (arxiv 2404.16130)](https://arxiv.org/abs/2404.16130) · [Official docs](https://microsoft.github.io/graphrag/)
- **Summary:** Indexes a knowledge graph of entities and claims, then supports both *local* retrieval (around a query-relevant subgraph) and *global* retrieval (community-summarized answers across the whole graph). Uses an LLM to extract entities/relationships and to summarize communities.
- **Applicability (TTMEvolve U1):** Justifies turning the cold-memory flat list into a typed-edge graph and supporting a "first hop = vector, second hop = graph expansion" retrieval pattern. The dual local/global split informs the `MemoryGraph.retrieve()` design where vector hits are expanded via neighbor walk.
- **Limits:** We do **not** adopt GraphRAG's LLM-driven entity/relationship extraction pipeline in Phase 0/A — it costs a second LLM call per write. Phase A only adds the storage model; extraction comes later (or via the existing ReflectionEngine).

### 1.2 GraphRAG DRIFT Search

- **Source:** [Official docs](https://microsoft.github.io/graphrag/query/drift_search/)
- **Summary:** DRIFT (Dynamic Reasoning and Inference with Flexible Traversal) combines local neighborhood exploration with broader query decomposition: it expands a query into sub-questions, then iteratively refines by traversing the graph.
- **Applicability (U1/U2):** Inspiration for the progressive loader's idea of "decompose the task, then fetch more on miss" — `LoadedContext.deferred` is a tiny analogue of DRIFT's sub-question list.
- **Limits:** We do **not** ship a full DRIFT loop; only the mental model of "local first, broaden on miss."

### 1.3 HippoRAG (NeurIPS 2024)

- **Source:** [Paper (arxiv 2405.14831)](https://arxiv.org/abs/2405.14831)
- **Summary:** Hippocampal-inspired RAG. Uses OpenIE to build an entity graph from passages, then runs personalized PageRank over it at query time to find multi-hop evidence.
- **Applicability (U1):** Validates multi-hop retrieval over a memory/knowledge graph. Reinforces our decision to keep typed edges (cause, effect, references, decomposes_into) instead of pure similarity.
- **Limits:** PageRank is a runtime cost we are not yet paying. Phase A only adds storage; PageRank-style scoring is a possible Phase B+ add.

### 1.4 LightRAG (2024)

- **Source:** [Paper (arxiv 2410.05779)](https://arxiv.org/abs/2410.05779) · [Repo](https://github.com/HKUDS/LightRAG)
- **Summary:** Dual-level retrieval (entity-level + relation-level) with incremental graph updates and efficient incremental indexing.
- **Applicability (U1):** Direct inspiration for using a **second** `VectorIndex` namespace (`cold_memory_edges`) for edge glue text. Append-only storage and incremental updates match our `cold_graph_*.jsonl` design.
- **Limits:** We are not copying LightRAG's chunking/embedding choices. Our encoder is the existing `paraphrase-multilingual-MiniLM-L12-v2` with offline fallback.

### 1.5 RAPTOR (ICLR 2024)

- **Source:** [Paper (arxiv 2401.18059)](https://arxiv.org/abs/2401.18059)
- **Summary:** Recursive abstractive summarization tree over chunks. Retrieval can pull a leaf or a higher-level summary stub, then expand on demand.
- **Applicability (U2):** The literal source of the "stub-then-expand" pattern in `PromptFragment.stub` and `LoadedContext.deferred`.
- **Limits:** We do **not** build a recursive summary tree in Phase 0/A/C. Stubs come from fragment metadata, not from a precomputed tree.

---

## 2. Long-Term Agent Memory / 智能体长期记忆

### 2.1 MemGPT / Letta

- **Source:** [Paper (arxiv 2310.08560)](https://arxiv.org/abs/2310.08560) · [Letta docs](https://docs.letta.com/)
- **Summary:** Tiered memory with explicit paging between main context (in-prompt) and external storage, exposed as tool calls. Memory operations are first-class agent actions, not hidden side effects.
- **Applicability (U1 + U2):** Justifies keeping the existing hot/warm/cold split (`HotMemory`, `WarmMemory`, `ColdMemory`). Validates the principle that "memory access" is observable — our `BudgetStats` exposes `cold_recall_hits`, `agents_md_hits`, `context_build_ms` for that reason.
- **Limits:** We do **not** expose memory as agent-callable tools in this plan. Loading stays an internal orchestration concern.

### 2.2 A-MEM (Agentic Memory, 2025)

- **Source:** [Paper (arxiv 2502.12110)](https://arxiv.org/abs/2502.12110)
- **Summary:** Zettelkasten-style memory where the agent dynamically creates links between notes as it writes them. Each note carries contextual attributes that drive future linking.
- **Applicability (U1):** The eight `EDGE_TYPES` in our plan (`references`, `supersedes`, `contradicts`, `supports`, `caused_by`, `temporal_next`, `decomposes_into`, `similar_to`) are the A-MEM-style typed-link vocabulary adapted to TTMEvolve's domain.
- **Limits:** A-MEM's link generation is LLM-driven. We start with deterministic link rules (claim_key collision → `supersedes`; conflict → `contradicts`) and may add LLM-driven linking later.

### 2.3 Mem0

- **Source:** [Repo (github.com/mem0ai/mem0)](https://github.com/mem0ai/mem0)
- **Summary:** Production long-term memory layer for LLM apps, with add/search/update/delete APIs, user/session scoping, and a memory-state evolution pipeline.
- **Applicability (U1/U2):** Reference for the **API surface** we should expose over our graph — `upsert`, `search`, `delete`, `get`. Helps us avoid reinventing a memory product without the operations it implies.
- **Limits:** We do **not** vendor Mem0. We adopt the vocabulary only.

### 2.4 MemoryBank (2023)

- **Source:** [Paper (arxiv 2305.10250)](https://arxiv.org/abs/2305.10250)
- **Summary:** Adds a forgetting mechanism and Ebbinghaus-style decay to long-term memory, plus an "AI psychologist" update rule.
- **Applicability (U3):** Validates the **soft-delete** path for auto-forget. The plan's `prune` writes a tombstone rather than deleting immediately, and a node can be restored before compaction.
- **Limits:** We do **not** implement a continuous Ebbinghaus curve. Prune is a discrete posterior-threshold decision.

### 2.5 LLM-Agent Memory Survey (2024)

- **Source:** [Paper (arxiv 2404.13501)](https://arxiv.org/abs/2404.13501)
- **Summary:** Surveys memory designs, evaluation risks, and vocabulary across the LLM-agent literature.
- **Applicability:** General vocabulary reference. Used to confirm that "private by default + verified evidence for promotion" is a recognized pattern, not an over-design.
- **Limits:** Survey, not an algorithm. Do not cite it as evidence for a specific implementation choice.

---

## 3. Progressive Prompt And Context Loading / 渐进式提示与上下文加载

### 3.1 DSPy (2023+)

- **Source:** [Paper (arxiv 2310.03714)](https://arxiv.org/abs/2310.03714) · [Docs](https://dspy.ai/)
- **Summary:** Declarative prompt modules with optimizers that compile signatures into prompts and few-shot examples automatically.
- **Applicability (U2):** `PromptFragment` is a DSPy-style module: each fragment is a typed, prioritized, token-bounded unit. The plan does **not** adopt DSPy optimizers yet; it adopts only the module shape so future optimization is a drop-in.
- **Limits:** We do not vendor DSPy. The plan explicitly forbids touching LLM provider classes.

### 3.2 LongLLMLingua / LLMLingua (Microsoft, 2023-2024)

- **Source:** [Paper (arxiv 2310.06839)](https://arxiv.org/abs/2310.06839) · [Repo](https://github.com/microsoft/LLMLingua)
- **Summary:** Perplexity-based prompt compression that drops low-information tokens while preserving answer quality. `LongLLMLingua` extends this to multi-round dialogue.
- **Applicability (U2):** Justifies the budget-fit semantics in `ContextBudgetManager.fit_fragments()`. We adopt the **shape** (budget-aware drop/defer) but not the perplexity model — fragments are coarse-grained, not token-level.
- **Limits:** Coarse-grained fragment dropping, not token-level perplexity compression.

---

## 4. Bayesian Confidence / 贝叶斯置信度

### 4.1 Bayesian Reinforcement Learning Survey (2016)

- **Source:** [Paper (arxiv 1609.04436)](https://arxiv.org/abs/1609.04436)
- **Summary:** Survey of Bayesian approaches to RL, including conjugate priors over policies, posterior sampling, and uncertainty quantification.
- **Applicability (U3):** Justifies treating memory usefulness as a posterior over evidence, not a hard rule. The plan's `BayesianState` is Beta-Bernoulli, a single conjugate pair.
- **Limits:** The survey covers RL policies; we apply only the prior/posterior intuition to a memory utility signal, not a decision policy.

### 4.2 (Implicit) Information-Theoretic Compression / MDL

- **Source:** Background reference — Grunwald, *The Minimum Description Length Principle* (2007). No specific URL to cite; cited as background only.
- **Applicability (U3):** Occam score as a bounded length penalty is a minimal MDL-style bias.
- **Limits:** Background intuition, not a directly cited implementation. Do not represent this as a paper-grounded decision.

---

## 5. Recursive Planning And Branching / 递归规划与分支

### 5.1 ADaPT (2023)

- **Source:** [Paper (arxiv 2311.05772)](https://arxiv.org/abs/2311.05772)
- **Summary:** Plan-and-decompose agents that recursively break a step into sub-steps **only when needed**. The decomposition is LLM-driven and gated by a controller.
- **Applicability (U4):** Justifies `kind="sub_plan"` in plan v2. Matches our depth limit (`plan.max_depth=3`) and the principle "decompose only when the step is too coarse for one tool call."
- **Limits:** ADaPT's controller is LLM-based; ours is control-signal-based (`ControlLoop.verdict == "diverging"`).

### 5.2 LATS (Language Agent Tree Search, 2023)

- **Source:** [Paper (arxiv 2310.04406)](https://arxiv.org/abs/2310.04406)
- **Summary:** Tree search over plans with LM-evaluated node values, combining reasoning, acting, and planning.
- **Applicability (U4):** Justifies `kind="branch"` and `kind="loop"` in plan v2. The plan explicitly does **not** ship tree search; only the branching structure.
- **Limits:** Tree search is out of scope. Only the static branch/loop surface is adopted.

### 5.3 PlanBench (2022)

- **Source:** [Paper (arxiv 2206.10498)](https://arxiv.org/abs/2206.10498)
- **Summary:** Benchmark for evaluating LLM planning. Provides plan-validation vocabulary (tool-name validity, dependency feasibility, etc.).
- **Applicability (U4):** Source of vocabulary for `core/plan_review.py` extensions. The existing `review_plan()` checks (unknown tools, dependency cycles, orphan steps) are PlanBench-shaped.
- **Limits:** We are not shipping a PlanBench evaluation harness.

---

## 6. Cybernetics / 控制论

### 6.1 Viable System Model (VSM)

- **Source:** [VSM Overview](https://viable-systems.github.io/vsm-docs/overview/what-is-vsm/) · [VSM Subsystems](https://viable-systems.github.io/vsm-docs/subsystems/)
- **Summary:** Stafford Beer's recursive cybernetic model of viable systems. Five subsystems (S1 operations, S2 anti-oscillation, S3 audit, S3* exception, S4 strategy, S5 policy) interact in a sense-compare-act-adjust loop at every level of recursion.
- **Applicability (U4):** Provides the **vocabulary** for `core/vsm.py`. The plan is explicit: VSM is a thin adapter over existing `engineering_control` and `project_control`; it is **not** a second control dashboard. The `ControlLoop.verdict` is S3*'s signal.
- **Limits:** VSM is a metaphor, not an algorithm. We do **not** claim full Beer compliance; we adopt the labels because they make runtime evidence easier to name.

### 6.2 (Implicit) Ashby's Law of Requisite Variety

- **Source:** Background reference — Ashby, *An Introduction to Cybernetics* (1956). No specific URL.
- **Applicability (U4):** Justifies why the control loop's window (`history_window=6`) and thresholds (`repeat_threshold=2`) must match the variety of disturbances we see. Out of scope to change the constants; logged as a tuning principle.
- **Limits:** Background, not a cited paper. Used for vocabulary only.

---

## 7. Anti-Patterns We Explicitly Reject / 明确拒绝的反模式

These do **not** appear in the design, and the citations below are evidence of why:

| Anti-pattern | Source | Why we reject |
| --- | --- | --- |
| Promote memory to shared/public from posterior alone | [GraphRAG docs](https://microsoft.github.io/graphrag/) — promotes summaries through human-in-the-loop | Would weaken `SharedMemoryPolicy` and conflict with `review_shared_memory_outcome()` |
| LLM-orchestrated context assembly inside every provider | [DSPy](https://dspy.ai/) — provider-coupled modules | Violates the "No provider churn" principle |
| Claim production embedding quality from a fake-FAISS benchmark | `tests/test_compact_rag_benchmark_keeps_production_quality_unproven_until_evaluated` (in-repo) | Explicit boundary enforced by an existing test |

---

## 8. Update Log / 更新日志

| Date | Change | Author |
| --- | --- | --- |
| 2026-06-28 | Phase 0 first draft. 17 cited entries, 6 baseline gates documented. | Phase 0 implementation slice |
