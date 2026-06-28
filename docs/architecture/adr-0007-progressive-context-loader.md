# ADR-0007: Progressive Prompt, Context, And Memory Loader

## 状态 / Status

Draft (Phase 0) — will move to Accepted after Phase C exit gate.

## 背景 / Context

`MemoryManager.prepare_think_payload()` (`memory/manager.py:85`) currently builds the LLM context as a fixed list of priority-weighted parts (`task`, `profile_context`, `agents_context`, `cold_context`, `context`, `tools_description`, `trajectory_str`) and asks `ContextBudgetManager.fit_parts()` to fit them under a token budget. The fit is a **monolithic truncation**: when the budget is tight, the lowest-priority parts are dropped wholesale.

The current shape has three concrete limits:

1. **No progressive loading.** A dropped memory hit or a truncated tool description is gone for the rest of the step. The agent cannot ask "fetch the full version of fragment X" on a later iteration.
2. **No stub-and-expand.** Fragments either fit or they don't. A graph-memory hit that is 800 chars cannot be reduced to a 60-char summary that the agent can later expand.
3. **No observability into what was dropped.** The current `BudgetStats` exposes `dropped_parts` (a count) but not *which* parts were dropped, *why*, or what they would have been.

The upgrade must:

- preserve the existing `MemoryManager.prepare_think_payload()` and `ContextBudgetManager.fit_parts()` behavior when `loader.enabled=false`;
- add a new `PromptLoader` that builds typed, prioritized fragments and exposes deferred/stubbed/dropped lists;
- keep all LLM provider classes (`claude_llm`, `local_llm`, `minimax_llm`, `openai_llm`, `mock_llm`) unchanged — the loader is wired from `MemoryManager` / `ReActLoop`, **not** from providers;
- feed compact stats into the existing Evidence Bundle rather than creating a new dashboard;
- not combine with eager-to-lazy skill import unless profiling proves it is a real bottleneck.

## 决策 / Decision

Adopt a fragment-based progressive loader that lives at the orchestration layer, not in providers.

1. **New module `llm/prompt_loader.py`** with `PromptFragment`, `LoadedContext`, `PromptLoader`:
   ```python
   @dataclass
   class PromptFragment:
       id: str
       role: str               # policy | task | plan | project_rules | tools | memory | trajectory
       content: str
       priority: int           # 10 down to 1
       token_estimate: int = 0
       full_ref: str = ""      # if non-empty, can be expanded later
       stub: bool = False
       source: str = ""
       meta: dict[str, Any] = field(default_factory=dict)
   ```
2. **Fragment priority table** (intentionally narrower than the old `fit_parts` priorities):
   | Priority | Fragment |
   | --- | --- |
   | 10 | Safety/runtime policy, current task, active approved plan step |
   | 8  | Project rules from AGENTS.md and Runtime Readiness blockers |
   | 7  | Relevant tool subset schema |
   | 6  | Graph/cold memory hits |
   | 5  | Workbench/runtime advice |
   | 3  | Trajectory tail |
   | 1  | Older trajectory or low-confidence memories |
3. **Budget manager extension.** Add `ContextBudgetManager.fit_fragments(system, fragments, max_tokens)` returning the same `BudgetStats` plus new fields: `fragment_count`, `deferred_count`, `stubbed_count`, `graph_recall_hits`, `posterior_pruned_count`, `occam_pruned_count`. `fit_parts()` stays unchanged for back-compat.
4. **Stub-and-expand.** When a fragment does not fit, the loader first attempts a stub (one-line summary) if `full_ref` is set. The stub is a 1-sentence summary produced by a deterministic extractor (no LLM call in Phase C). If even the stub does not fit, the fragment's `id` is added to `LoadedContext.deferred` and dropped. The `expand_fragment(full_id)` method allows a subsequent step to pull the full content back into the budget.
5. **Provider non-churn.** `LLM.think()`, `LLM.choose_action()`, `LLM.reflect()`, `LLM.generate_code()` keep their signatures. The loader writes to `context` (the second positional argument) and to `trajectory_for_llm` (cleared, since the loader already incorporated the trajectory tail). No provider learns about `PromptFragment` or `MemoryGraph`.
6. **Wiring.** `MemoryManager.prepare_think_payload()` becomes a thin shim: when `loader.enabled=false` it calls the legacy `fit_parts` path; when `loader.enabled=true` it builds fragments (task, plan step, project rules, tool subset, graph recall, trajectory tail) and calls `PromptLoader.build()`. `ReActLoop` calls into this shim; no change to its iteration shape.
7. **Skill loading is two-step.** Phase C only includes a relevant tool subset as a fragment (using the existing `ToolRegistry.schema_for_llm(tools=...)`). A later, optional step is to make `ToolRegistry` metadata-first / lazy-handler; this is **not** part of Phase C and is **not** combined with the prompt-loader rollout unless startup profiling proves eager import is a real bottleneck.

## 后果 / Consequences

### Positive / 正面

- When the budget is tight, the agent keeps task + active plan + policy (priority 10) and gracefully defers memory hits and trajectory tail, instead of dropping them silently.
- A drop event becomes a structured record (`LoadedContext.deferred`, `BudgetStats.deferred_count`, `BudgetStats.stubbed_count`) that the Workbench and Evidence Bundle can render directly.
- LLM provider classes stay unchanged. Future provider swaps do not require re-coordinating with prompt or memory logic.
- The fragment priority table is a **single source of truth** for what counts as critical vs. deferrable. The old scattered priority integers in `fit_parts` go away (kept only for back-compat in `fit_parts`).

### Negative / 负面

- The fragment path adds a new code path that must be tested independently. A regression in `PromptLoader` would silently degrade context quality without a LLM-visible failure.
- The deterministic stub extractor is a small new component. It must not call an LLM in the hot path; it must be a one-pass summarizer (truncate + format). If a richer stub is needed later, it must be gated behind a feature flag, not added silently.
- `MemoryManager.prepare_think_payload` becomes a shim. The legacy path is preserved but adds a small amount of dead code to keep back-compat.

### Compliance / 合规

- New tests: `tests/test_prompt_loader.py`, `tests/test_context_budget.py` (extended), `tests/test_memory_manager.py` (extended).
- `loader.enabled=false` must produce a payload that is byte-equivalent (or close enough) to the old payload for the existing tests in `tests/test_memory_manager_recall.py` and `tests/test_runtime_contract.py`.
- `loader.enabled=true` must keep the task + active plan + policy fragments at priority 10 even under a tight budget. This is verified by a test that uses a 200-token budget and asserts the policy/task/plan fragments are present.
- Evidence Bundle reports `prompt_loader` stats only when the flag is enabled. The legacy path's payload is not duplicated into evidence.

## 替代方案 / Alternatives Considered

- **Put `PromptLoader` inside every LLM provider class.** Rejected — would force every future provider to re-implement fragment logic and would couple providers to `MemoryGraph`. Violates the "No provider churn" principle.
- **Adopt DSPy optimizers end-to-end.** Rejected — the optimizers require labelled training data we do not have, and they would couple the agent to DSPy's signatures. The plan adopts only the module *shape* (fragments), not the optimizer.
- **Build token-level compression (LLMLingua-style perplexity drop) into the loader.** Rejected — coarse-grained fragment dropping is the simpler, more observable choice. Token-level compression can be a future refinement.
- **Lazy-import skill handlers as part of Phase C.** Rejected — the plan explicitly defers this until startup profiling proves eager import is a real bottleneck.

## References / 引用

See `docs/research/2026-memory-and-control.md` for the full source list. The directly relevant ones:

- [DSPy paper](https://arxiv.org/abs/2310.03714) and [DSPy docs](https://dspy.ai/) — module shape
- [LongLLMLingua paper](https://arxiv.org/abs/2310.06839) and [LLMLingua repo](https://github.com/microsoft/LLMLingua) — budget-fit semantics
- [RAPTOR paper](https://arxiv.org/abs/2401.18059) — stub-then-expand pattern
- [MemGPT paper](https://arxiv.org/abs/2310.08560) and [Letta docs](https://docs.letta.com/) — memory access as observable operation

## 退出条件 / Exit Gate (Phase C)

- `loader.enabled=false` keeps all existing tests passing.
- New `tests/test_prompt_loader.py` covers: priority ordering, deferral, stub expansion, stats.
- A tight-budget test (200 tokens) asserts that policy + task + plan fragments are present and lower-priority fragments are deferred or stubbed.
- LLM provider classes (`llm/claude_llm.py`, `llm/local_llm.py`, `llm/minimax_llm.py`, `llm/openai_llm.py`, `llm/mock_llm.py`) have **no** new mandatory methods.
- Evidence Bundle reports compact loader stats without leaking full prompt content.
