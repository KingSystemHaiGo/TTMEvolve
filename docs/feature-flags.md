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
| `homeostasis.enabled` | `false` | `core/loop_homeostasis.py` (`LoopHomeostasis(enabled=...)`) | `agent/react_loop.py` (`__init__` accepts the controller; main loop consults it after each step) | When on, the homeostatic dead-man's switch detects three stuck patterns (3 same-tool-same-observation, 5 same plan_progress, 2 rescue failures) and forces the loop to terminate with `step["done"] = True` and `output = {"stuck": true, "reason": ...}`. When off, the loop runs unchanged. Fixes the 2026-06-28 project_status hard-stuck trace. See [`docs/react-loop-redesign.md`](react-loop-redesign.md) §R3. |
| `thought_chain.strict` | `false` | `llm/thought_record.py` (`parse_thought_record(..., enabled=...)`) | `agent/react_loop.py` (`thought_chain_strict` init flag) | When on, `llm.think()` output is parsed into a structured `ThoughtRecord` (plan_step, observation_summary, hypothesis, expected_outcome, confidence, decision). The control loop and evidence bundle read the record. When off (default), the parser is a no-op and the existing free-text path runs unchanged. Backward compatible: free text returns an empty record; broken JSON keeps the raw text with a warning. See [`docs/react-loop-redesign.md`](react-loop-redesign.md) §R1. |
| `runtime.tool_contracts.enabled` | `false` (implicit) | `agent/tool_contracts.py` (`ContractStore`, `default_contract_store`) | `core/executor.py` (`propose_action` checks the contract preflight before sandbox) | The tool contract system is registered statically at process start. When a tool has a contract and the state is `unavailable` / `needs_config` / `busy`, `propose_action` returns `{"ok": False, "error_type": "precondition_not_satisfied"}` and the runtime errors hook fires `tool_blocked`. This is the **preflight hard block** that fixes Issue 5 from the redesign: tools with unmet preconditions (e.g. Maker MCP not ready) cannot be called. Tools without a contract are unaffected (legacy path). Tools contract-aware ranking lands in R4. |
| `vsm.policy` | `audit` (default) | `core/vsm.py` (`VSMShell(..., config={"policy": ...})`) | `core/vsm.py` (S2 write actions) and `agent/react_loop.py` (consumes the blacklist) | Phase R4: VSMShell becomes a real control surface. When S3* persists or S2 detects a same-tool repeat, the shell calls `disable_tool(name, until_iter=N)` and rank_tools filters the disabled tool out. Three policy levels: `off` (writes pass silently, no audit), `audit` (default; every write emits `vsm_write_audit`), `cautious` (audit + `policy_check_pending` for future R5 operator-approval hook). Closes the loop between observation and tool selection. |

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
