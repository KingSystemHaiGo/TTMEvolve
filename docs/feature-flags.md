# Feature Flags Inventory — Slice #1

This document lists every feature flag introduced by the RAG/Memory/
Cybernetic Control plan, its default, the entry point that consumes it,
and the test that locks the default down. Treat this list as
authoritative: changing a default requires updating this doc and the
matching regression guard in `tests/test_regression_guards.py`.

## Defaults (all `false`)

| Flag | Default | Path | Read by | Effect when on |
| --- | --- | --- | --- | --- |
| `memory.graph.enabled` | `false` | `core/plan_format.py` (data model); `memory/cold.py` (`graph_config`); `core/config.py` (`vector_index_config` for legacy access) | `ColdMemory.__init__` (instantiates `MemoryGraph`); `ColdMemory.retrieve_with_graph` (returns five-factor ranked list) | Cold memory exposes a typed-edge graph layer; `retrieve_with_graph(query)` returns results with `vector_score / posterior / freshness_score / edge_support_score / occam_score / graph_score / fallback` fields. |
| `memory.bayes.enabled` | `false` | `memory/cold.py` (`bayes_config`) | `ColdMemory.record_shared_outcome` | Each entry gains a `bayes: {alpha, beta, occurrences, last_update, posterior}` sub-object updated on every outcome. |
| `loader.enabled` | `false` | `memory/manager.py` (`self.config.get("loader.enabled", False)`) | `MemoryManager.prepare_think_payload` (thin shim) | The shim delegates to `PromptLoader.build`; `BudgetStats` carries `fragment_count / deferred_count / stubbed_count / graph_recall_hits / posterior_pruned_count / occam_pruned_count / deferred_ids`. |
| `plan.v2_enabled` | `false` | (handled in `PlanExecutor._normalize_for_execution`; v1 plans always pass through) | `core/plan_executor.py` | Plan v2 features (`kind: sub_plan / branch / loop`, `condition`, `vsm_layer`) are accepted and routed. v1 plans are auto-promoted. |
| `vsm.enabled` | `false` | `core/vsm.py` (`VSMShell.from_config`) | `agent/agent.py` (auto-constructs the shell and passes it to `ReActLoop`) | The shell calls `pre_step` / `post_step` around each iteration; on `ControlLoop.verdict == "diverging"` it routes to S4 escalation (re-plan or expert rescue), gated by `vsm.auto_replan=true` AND cooldown AND `max_replan_depth`. |
| `runtime.errors.enabled` | `false` | `core/runtime_errors.py` (`configure(enabled=...)`) | `core/error_hooks.py` (default subscriber) | When on, the structured error log (`storage/runtime_errors.jsonl`) records tool call failures, sandbox / approval blocks, tool timeouts, generic exceptions in `_execute`, and `ControlLoop` / `RescueTrigger` diverging verdicts. When off (default), every `error_hooks.fire()` is a no-op. See [`docs/runtime-errors.md`](runtime-errors.md) for the schema. |

## Why all defaults are `false`

- **Production RAG quality is still `unproven` until a real labelled
  corpus + production embedding artifact passes
  `release_readiness --check production_rag_quality` with
  `can_claim_production_embedding_quality=true`.** Enabling
  `memory.graph.enabled` or `loader.enabled` in production before
  that gate is met would let unverified output reach users.
- The Phase D work touches `ControlLoop` and `PlanExecutor` paths
  that the ReAct loop relies on. We want to observe the new code
  via unit tests + opt-in integration tests before any flag flips
  in production.
- A flag flip should always be a deliberate, reviewable action,
  not a side-effect of another change.

## How to flip a flag

1. Open `config.json` and add or change the relevant block.
2. Restart the AppServer.
3. Run `python scripts/check_release_ready.py` (see
   `docs/release-gates.md`) and confirm every gate is green.
4. Run the integration tests in
   `tests/test_integration_all_flags_on.py` and
   `tests/test_integration_scenarios.py` and confirm they pass.
5. Update `docs/memory-index.md` and `docs/memory-health.md` with a
   POST entry that records the flip and the evidence.
6. Promote the next release candidate (see `docs/release-gates.md`).

## How to test the flag wiring (off-by-default path)

The regression guard `tests/test_regression_guards.py::test_feature_flags_default_off`
walks the public config surface and asserts that the five flags
above are read as `False` when no explicit override is present. If
you intentionally flip a default, that test must be updated in the
same commit and the new default must be documented in this file.
