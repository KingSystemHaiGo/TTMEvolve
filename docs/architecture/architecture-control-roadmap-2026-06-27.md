# TTMEvolve Architecture Control Roadmap - 2026-06-27 12:41

This document records an evidence-based architecture audit and control roadmap for TTMEvolve. It is project memory, not assistant private memory.

## Request Classification

- Type: refactor/architecture optimization
- Level: XL
- Mode: System 2
- Scope: code audit, module decoupling, internal communication bus, vector/RAG memory performance, three-layer independence, COS rules, multi-agent shared memory, engineering control loops, truthfulness gates, autonomous project management, and long-task continuity.

## Evidence Snapshot

Audit commands and local facts:

- Python package scan covered 114 files under `core/`, `agent/`, `memory/`, `learning/`, `server/`, `llm/`, `ecosystem/`, and `cli/`.
- Largest files found:
  - `server/app_server.py`: 3941 lines at initial audit; 2104 lines after the 2026-06-27 01:44 evidence-builder extraction; 1867 lines at the 2026-06-27 12:41 boundary audit.
  - `agent/react_loop.py`: 1415 lines at initial audit; about 1141 lines after the 2026-06-27 04:05 Maker guard phase extraction; 702 lines at the 2026-06-27 12:41 boundary audit.
  - `agent/agent.py`: 858 lines
  - `server/maker_setup.py`: 891 lines
  - `core/executor.py`: 773 lines
  - `core/runtime_contract.py`: 670 lines
  - `ecosystem/skill_sync.py`: 662 lines
  - `agent/tool_registry.py`: 582 lines
  - `server/session_store.py`: 532 lines
  - `agent/mcp_integration.py`: 479 lines
- Boundary import findings:
  - 2026-06-27 12:41 update: `core/harness.py` and `core/project_context.py` now keep compatibility through lazy `__getattr__` exports instead of top-level imports.
  - Static import audit no longer reports `core -> cli` or `core -> ecosystem` as normal imports.
  - `tests/test_core_boundary.py` verifies that importing the core compatibility modules does not load `cli.harness` or `ecosystem.project_context` until the compatibility symbol is accessed.
- Current bus facts:
  - `core/runtime_events.py` defines `RuntimeEventBus`.
  - `server/runtime_observer.py` and `server/project_observer.py` already consume bus events.
  - `agent/agent.py` has an agent-owned event bus.
  - AppServer still keeps compatibility paths through session emit, SQLite replay, and SSE.
  - 2026-06-27 00:20 update: `RuntimeEventBus.stats()` now reports observer failure counters and latest observer error details, and Evidence/Readiness summaries expose `observer_health` plus `observer_error_count`.
  - 2026-06-27 00:42 update: dedicated `LearningStateObserver` and `MemoryRecallObserver` now subscribe to RuntimeEventBus session events. Runtime Readiness, Session Evidence JSON/Markdown, and LLM Onboarding JSON/Markdown expose learning observer state and memory/RAG recall summaries with SQLite replay fallback.
- Current RAG facts:
  - `memory/cold.py` supports `workspace_profile`, per-profile policies, `agent_id`, and visibility.
  - `memory/shared_policy.py` provides conservative private/shared/public boundaries.
  - `memory/vector_index.py` had two correctness/performance problems fixed in this pass:
    - first vector add did not build a FAISS index because `add()` required `is_available`, and `is_available` required an existing index;
    - `_rebuild_index()` reused the old FAISS index and could duplicate indexed records.
  - 2026-06-27 00:54 update: `ColdMemory.bulk_index()` adds batch archive/index loading so benchmark and future knowledge-base imports can persist once and add vectors once.
  - 2026-06-27 00:54 update: `tests/test_rag_performance.py` provides a deterministic fake-FAISS benchmark for 10k+1 records covering build cost, cold-start load, first recall, warm p95 recall, profile filter hit rate, and fallback hit rate.
  - 2026-06-27 01:12 update: `memory/rag_benchmark.py` exposes the deterministic benchmark as a product service behind `GET /memory/rag-benchmark`, with Runtime Readiness, Session Evidence, and LLM Onboarding surfacing compact `rag_benchmark` status/budget evidence.
  - 2026-06-27 01:28 update: Agent Workbench now renders a RAG benchmark card from Evidence Bundle data and can refresh `GET /memory/rag-benchmark?force=true` directly.
  - 2026-06-27 05:13 update: `memory/shared_outcome.py` now provides verified shared-memory promotion/demotion/conflict rules, and `ColdMemory.record_shared_outcome()` persists outcome metadata plus unresolved conflict records.
  - 2026-06-27 05:13 update: `memory/vector_index.py` now tries vector results before keyword fallback, so warm vector recall no longer performs a full keyword scan when FAISS results fill the request.
  - 2026-06-27 05:31 update: `learning/shared_memory_bridge.py` now archives reflection insights into ColdMemory as private `learning_insight` records and calls `ColdMemory.record_shared_outcome()` only for shareable, verified-positive learning outcomes. `TapMakerAgent._learn_from_session()` now returns shared-memory summaries and emits archived/promoted/conflict metrics through learning layer events.
  - 2026-06-27 09:11 update: `memory/rag_benchmark.py` now separates deterministic RAG speed claims from production embedding semantic-quality claims. Reports include `embedding_quality.status=unproven` and `closure_gate.can_claim_production_embedding_quality=false` unless a production embedding model, labelled corpus/golden query set, quality metric, and nonzero sample count are present. Runtime Readiness, Evidence/Onboarding JSON+Markdown, Runtime Contract, and Workbench expose this boundary.
  - 2026-06-27 09:35 update: `memory/rag_quality.py` now runs labelled golden-corpus embedding quality evaluation with recall@k, precision@k, MRR, query-count budgets, per-query evidence, and missing-evidence reports. `GET /memory/rag-quality` is exposed through AppServer and endpoint lists; `memory/rag_benchmark.py` attaches the latest quality evaluation into `embedding_quality`.
  - 2026-06-27 09:49 update: `server/rag_evidence_service.py` now owns deterministic RAG benchmark caching, production embedding quality evaluation caching, config-file-relative quality corpus path resolution, eval-index storage path selection, and benchmark/quality evidence attachment. AppServer keeps the public `/memory/rag-benchmark` and `/memory/rag-quality` routes but delegates RAG evidence status/report work to the service.
- Current three-layer health facts:
  - 2026-06-27 05:52 update: `server/layer_health.py` now builds `layer-health.v1` snapshots for Agent, Core Runtime, and Learning.
  - Snapshots expose per-layer health/state/event/route/latency/error, learning queue depth, active learning job status, insight count, shared-memory metrics, observer error count, latency budget status, and observed communication routes.
  - `/sessions/{session_id}/layer-health?steps=20` is now available through `server/session_api.py` and `server/app_server.py`, and is listed in `core/runtime_contract.py`.
  - Runtime Readiness, Session Evidence JSON/Markdown, and LLM Onboarding JSON/Markdown now include compact `layer_health` evidence.
- Current engineering-control facts:
  - 2026-06-27 06:06 update: `server/layer_control.py` now converts `layer_health` into control signals, thresholds, corrective actions, closure gates, and a truthfulness rule.
  - `/sessions/{session_id}/layer-control?steps=20` is now available through `server/session_api.py` and `server/app_server.py`, and is listed in `core/runtime_contract.py`.
  - Runtime Readiness, Session Evidence JSON/Markdown, and LLM Onboarding JSON/Markdown now include compact `layer_control` evidence.
  - First thresholds cover failed layers, missing layer evidence, missing expected routes, max layer latency, learning queue depth, and RuntimeEventBus observer errors.
  - Status semantics: `ready` can claim layer independence, `watch` can continue with monitoring but cannot claim completion, `needs_action` requires correction, and `blocked` blocks completion claims.
  - 2026-06-27 06:20 update: `server/project_control.py` now accepts layer-control evidence and exposes compact `layer_control` plus `control_actions`; `/sessions/{session_id}/project-state` and Agent Workbench Project Control show the highest-priority corrective action.
  - 2026-06-27 06:44 update: `server/engineering_control.py` now adds non-layer control signals for memory/RAG zero-hit samples, context/cold recall latency, repeated tool failures, same-tool retry loops, failed plan gates, and failed goal gates.
  - 2026-06-27 06:44 update: `/sessions/{session_id}/engineering-control?steps=20` is available through `server/session_api.py` and `server/app_server.py`, listed in Runtime Contract, and exposed in Runtime Readiness, Session Evidence JSON/Markdown, LLM Onboarding JSON/Markdown, Quickstart endpoint lists, Project Control, and Workbench.
  - Truthfulness gate: `engineering_control.closure_gate.can_claim_engineering_control_ready` is true only when status is `ready`; memory/RAG optimization claims require observed recall evidence with hits and no active memory-control signals.
- Current managed learning-worker facts:
  - 2026-06-27 07:48 update: `agent/learning_queue.py` now owns live learning job scheduling, cooperative cancellation state, retry policy, worker idle timeout, and public job snapshots for each `TapMakerAgent`.
  - `TapMakerAgent` delegates learning dispatch to `LearningJobQueue`; the old private `_learning_jobs` dict and per-job thread path were removed from `agent/agent.py`.
  - Live learning controls are exposed through `TapMakerAgent.cancel_learning_job()`, `TapMakerAgent.retry_learning_job()`, `AppServer.cancel_learning_job()`, `AppServer.retry_learning_job()`, `POST /sessions/{id}/learning/cancel`, and `POST /sessions/{id}/learning/retry`.
  - `/sessions/{id}/learning?steps=N`, `learning_job_from_server()`, `layer_health`, Runtime Contract, Evidence Bundle, and Onboarding endpoint lists now expose managed job fields: `policy`, `attempts`, `max_attempts`, `retryable`, and `cancel_requested`.
  - 2026-06-27 08:06 update: Agent Workbench now reads learning job/policy evidence and shows guarded `Cancel`/`Retry` controls in the existing learning card for live queue jobs.
  - Workbench truthfulness boundary: durable replay/history-only learning jobs show a live-queue-unavailable message instead of fake controls; each control attempt refreshes learning status and Evidence Bundle.
  - Boundary: this is verified for live session-scoped agent queues and frontend contract wiring. Durable replay can reconstruct conservative status but cannot cancel or retry historical events; global cross-session worker pooling, visual GUI smoke, and production learning throughput budgets remain pending.
- Current long-task continuity facts:
  - 2026-06-27 07:13 update: `server/resume_drill.py` now builds `resume-drill.v1` reports from persisted `SessionStore` evidence without live ReActLoop state, private queues, or raw SSE replay.
  - 2026-06-27 07:13 update: `/sessions/{session_id}/resume-drill?steps=20` is available through `server/session_api.py` and `server/app_server.py`, listed in Runtime Contract, and exposed in Runtime Readiness, Session Evidence JSON/Markdown, LLM Onboarding JSON/Markdown, Quickstart endpoint lists, and Workbench external-agent boot summaries.
  - Capability levels are explicit: `durable_handoff` can become `ready`; `warm_process` and `hot_tool_call` remain `unproven`.
  - Truthfulness gate: durable handoff claims require recovered task, open plan steps, latest result, artifact refs, and next action from persisted context evidence. Missing fields produce `partial`, not `ready`.
- Current decoupling facts:
  - 2026-06-27 01:44 update: `server/evidence_bundle.py` now owns Runtime Readiness, Portable Runtime status, Session Evidence, LLM Onboarding, Quickstart, LLM proof/feedback summaries, runtime metrics summaries, and observer replay summaries. `server/app_server.py` retains HTTP routing, AppServer lifecycle, sessions, and mutable runtime services.
  - 2026-06-27 03:55 update: `server/session_api.py` now owns session-route payload construction for status, commit history, context sync, runtime metrics, project state, project writeback, learning, Maker guard, LLM probe history, Evidence Bundle, and runtime advice. `server/app_server.py` delegates those payloads while retaining route dispatch, existence checks, Markdown/JSON response choice, and HTTP status codes.
  - 2026-06-27 10:01 update: `server/agent_bootstrap_api.py` now owns external Agent onboarding, handoff, quickstart, and Maker briefing payload assembly. `server/app_server.py` delegates `/agent/onboarding`, `/agent/handoff`, `/agent/quickstart`, and `/agent/maker-briefing` payload work while retaining HTTP transport and 404 behavior.
  - 2026-06-27 04:05 update: `agent/maker_guard.py` now owns Maker first-action guard rules, side-effect detection, Maker-task keyword detection, and machine-readable guard observation/context payloads. `agent/react_loop.py` delegates to this module while retaining event emission, plan validation, goal checklist, and context sync flow.
  - 2026-06-27 04:23 update: `agent/action_execution.py` now owns action validation/execution service behavior: direct tool-call validation, executor dispatch, progress heartbeats, uncertain commit reconciliation, validation failure payloads, timeout context hints, and output tail trimming. `agent/react_loop.py` delegates normal actions and expert action paths to this service while retaining planning/trajectory/event ordering.
  - 2026-06-27 04:40 update: `agent/context_sync.py` now owns context-sync snapshot construction, continuation checkpoint assembly, signature generation, diff keys, open-plan extraction, artifact refs, and commit-state extraction. `agent/react_loop.py` delegates context handoff builders and retained planning/trajectory/event ordering; line count was `857` immediately after that slice.
  - 2026-06-27 08:21 update: `agent/plan_first.py` now owns Plan First drafting, known-tool discovery, deterministic review, approval-provider handling, parse-failure events, approval-error events, and no-approval result shape. `agent/react_loop.py` delegates the Plan First flow while keeping compatibility wrappers; current measured line counts are `agent/react_loop.py` `801` and `agent/plan_first.py` `158`.
  - 2026-06-27 08:34 update: `agent/trajectory_result.py` now owns normal ReAct output-step recording, observation-step recording, latest-output lookup, final result construction, and compact result summaries. `agent/react_loop.py` delegates done-output, Maker guard observation, tool-preflight validation observation, and normal tool observation recording; current measured line counts are `agent/react_loop.py` `799` and `agent/trajectory_result.py` `108`.
  - 2026-06-27 08:49 update: `agent/expert_takeover.py` now owns expert loop-takeover thought/action/tool-call/output/observation/error events, expert trajectory append behavior, failure context append, and `on_step` callback dispatch. `agent/react_loop.py` delegates `takeover()` to this runner; current measured line counts are `agent/react_loop.py` `761` and `agent/expert_takeover.py` `94`.
  - 2026-06-27 08:57 update: `agent/rescue_application.py` now owns direct-action rescue trajectory entry construction and append behavior. `agent/rescue_orchestrator.py` delegates this after `react.inject_expert_action()` returns the observation; current measured line counts are `agent/rescue_orchestrator.py` `259` and `agent/rescue_application.py` `27`.
  - 2026-06-27 09:49 update: `server/rag_evidence_service.py` extracts another AppServer responsibility. Current measured line counts are `server/app_server.py` `1941` and `server/rag_evidence_service.py` `159`. Service tests cover cache behavior, config path resolution, quality evidence enrichment, and config invalidation.
  - 2026-06-27 12:41 update: `core/harness.py` and `core/project_context.py` no longer import `cli.harness` or `ecosystem.project_context` during normal core import. Compatibility remains available lazily, and focused boundary tests pass.
- Current COS facts:
  - 2026-06-27 02:12 update: `core.intent_classifier.classify_cos_gate()` now produces deterministic COS Gate 0 evidence with task type, level, mode, understanding status, declaration, required gates, POST/truthfulness rules, vague-instruction protocol, multi-agent guidance, and project-management guidance.
  - 2026-06-27 02:12 update: `AppServer.create_session()` emits and persists `cos_gate` through RuntimeEventBus + SessionStore; Runtime Readiness, Session Evidence JSON/Markdown, and LLM Onboarding JSON/Markdown expose the replayed or computed gate.
  - 2026-06-27 02:12 verification: full `tests/test_app_server_resume.py` passed after updating the shared-bus expectation for the new session-start `cos_gate` event.
  - 2026-06-27 02:43 update: `server/project_control.py` now merges `project_state`, `cos_gate`, and optional `runtime_advice` into a compact project-control summary with current focus, next action, blockers, verification status, required/completed/pending gates, and POST memory updates due.
  - 2026-06-27 02:43 update: Session Evidence and LLM Onboarding JSON/Markdown now expose `project_control`; runtime-advice warnings are preserved as evidence without overriding the project observer's next action when project state is already known.
  - 2026-06-27 02:58 update: Agent Workbench now renders a `project_control` card from the Evidence Bundle, showing status, pending gates, verification status, POST updates due, blockers, and next action inside the existing evidence stack.
  - 2026-06-27 03:33 update: `server/project_writeback.py` now builds and applies guarded append-only writeback plans from `project_control.memory_updates_due`. `GET /sessions/{id}/project-writeback` returns the plan, while `POST /sessions/{id}/project-writeback` writes only when `{"apply": true}` is sent. Session Evidence, LLM Onboarding, Runtime Contract, Quickstart endpoint summaries, and Workbench expose compact `project_writeback` status.
- Verification after the RAG fix:
  - `.venv\Scripts\python.exe -m pytest tests\test_vector_index.py tests\test_cold_memory_vector.py tests\test_memory_manager_recall.py -q`
  - Result: `21 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_rag_performance.py tests\test_cold_memory_vector.py tests\test_memory_manager_recall.py tests\test_memory_manager.py tests\test_shared_memory_policy.py -q`
  - Result: `23 passed`.
  - Latest benchmark sample: index size `10001`, build `637.869 ms`, cold start `102.919 ms`, first recall `17.17 ms`, warm recall p95 `13.61 ms`, profile hit rate `1.0`, fallback hit rate `1.0`.
  - `.venv\Scripts\python.exe -m pytest tests\test_rag_performance.py tests\test_runtime_contract.py tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q`
  - Result: `11 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_rag_performance.py tests\test_vector_index.py tests\test_cold_memory_vector.py tests\test_memory_manager_recall.py tests\test_memory_manager.py tests\test_shared_memory_policy.py tests\test_runtime_contract.py tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q`
  - Result: `41 passed`.
  - Latest endpoint-backed benchmark sample: index size `10001`, build `760.314 ms`, cold start `128.648 ms`, first recall `13.494 ms`, warm recall p95 `16.282 ms`, profile hit rate `1.0`, fallback hit rate `1.0`, budget `pass`.

## Target Architecture

Use a modular monolith with an event-driven internal spine.

Do not split into external microservices yet. TTMEvolve is a desktop application with Rust/Tauri, React, Python AppServer, Maker MCP, and local storage. The main bottleneck is not deployment scaling; it is module size, mixed ownership, direct state reads, prompt/context weight, and insufficient performance baselines.

The target shape:

```text
Frontend/Tauri
  -> AppServer HTTP API
    -> Session Runtime
      -> Agent layer: planning, tool choice, user-facing answer
      -> Runtime layer: executor, sandbox, MCP, shell, browser, event log
      -> Learning layer: async reflection, knowledge extraction, memory promotion
    -> RuntimeEventBus
      -> metrics observer
      -> project observer
      -> learning observer
      -> memory observer
      -> evidence/onboarding surfaces
```

Design rules:

- Agent layer proposes and explains; it does not directly perform side effects.
- Runtime layer owns side effects, validation, sandbox, approval, timeouts, and commit evidence.
- Learning layer runs asynchronously unless a task explicitly requires synchronous knowledge generation.
- RuntimeEventBus is the default path for live observers.
- SQLite/session store remains durable replay, not the only integration surface.
- Evidence endpoints stay compact and are preferred over raw SSE.
- Normal UI shows user-facing progress; internal ranking/debug details stay in Workbench/evidence.

## Goal Mapping

| User Goal | Current State | Required Next Gate |
| --- | --- | --- |
| Code audit, decoupling, efficient bus | RuntimeEventBus exists; evidence/readiness/onboarding builders are extracted to `server/evidence_bundle.py`; session-route payloads are extracted to `server/session_api.py`; Maker guard rules are extracted to `agent/maker_guard.py`; action execution is extracted to `agent/action_execution.py`; context-sync/checkpoint builders are extracted to `agent/context_sync.py`; Plan First logic is extracted to `agent/plan_first.py`; normal trajectory/result helpers are extracted to `agent/trajectory_result.py`; expert loop takeover is extracted to `agent/expert_takeover.py`; direct-action rescue append is extracted to `agent/rescue_application.py`; AppServer route dispatch still needs more splits. | Continue splitting remaining AppServer route groups and migrate more consumers to bus observers. |
| Vector memory and RAG speed | Profile policies and shared-memory policy exist; vector first-add/rebuild bugs fixed; memory/RAG recall evidence is observable through the bus/store surface; deterministic RAG benchmark now covers 10k+1 fake-FAISS records and is pullable through `/memory/rag-benchmark`, Evidence, Readiness, Onboarding, and Workbench; vector-first search removes the normal full keyword scan from warm vector recall; `embedding_quality` now prevents deterministic speed evidence from being reported as production semantic quality proof; `/memory/rag-quality` can run labelled golden-corpus quality evaluation. | Add a real project golden corpus/local production embedding artifact and optimize any quality or speed budget regressions. |
| Agent/Core/Learning independence | Layer events, async learning jobs, bus-backed learning observer summaries, compact `layer_health` snapshots, `layer_control` thresholds/actions, live session-scoped `LearningJobQueue` cancellation/retry policy evidence, and Workbench guarded learning controls exist. | Consider global cross-session learning scheduling only after session-scoped policy and GUI smoke remain stable. |
| COS rules and thresholds | `core/intent_classifier.py` now exposes deterministic COS Gate 0 classification; session creation persists `cos_gate`; Evidence/Readiness/Onboarding expose task grade, mode, required gates, closure check, `project_control`, and guarded `project_writeback`; Workbench renders the same project-control/writeback state. | Add higher-level GUI apply/review controls only after the guarded backend writeback path remains stable. |
| Multi-agent shared memory | Policy surface exists; Evidence exposes outcome rules; `ColdMemory.record_shared_outcome()` can promote verified positive records, demote stale/regressed/repeatedly misleading records, persist unresolved same-claim conflicts, and receive validated learning outcomes through `learning/shared_memory_bridge.py`. Deterministic tests now simulate agent-b reading agent-a shared memory and a same-claim conflict blocking agent-b promotion. | Add real multi-process/multi-agent orchestration, conflict resolution UX, and compact handoff consumption beyond local deterministic tests. |
| Engineering cybernetics/systematic practice | Control loop, health, project observer, runtime metrics, `layer_health`, `layer_control`, and `engineering_control` exist. Control thresholds/actions now cover layer latency, missing routes, learning backlog, observer errors, layer failures, memory/RAG misses, memory recall latency, repeated tool failures, same-tool retry loops, and failed plan/goal gates; top corrective actions flow into project-control and Workbench. | Add guarded corrective-action review/apply UX only after the evidence remains stable. |
| Truthfulness/no guessing | Evidence and readiness endpoints exist; docs now state product-memory boundaries. | Add claim gates: product claims require command/test/runtime evidence or must be marked unproven. |
| Agent project management | Project observer can derive next action from bus/context events; `project_control` combines it with COS gates, blockers, verification state, memory updates due, layer-control summary, and compact corrective actions; `project_writeback` plans/applies explicit append-only POST updates; Workbench shows the compact project-manager/writeback/control-action state. | Continue route/session decoupling, then add higher-level project-manager review/apply flows if needed. |
| Ultra-long task continuity | Context sync and continuation checkpoints exist and their builders are directly tested outside `ReActLoop`; `/sessions/{id}/resume-drill?steps=20` now verifies durable store-replay handoff and exposes capability levels. | Add a real process-restart runner if needed, plus warm-process and hot-tool-call drills before making stronger resume claims. |

## Phase Plan

### Phase 0 - Stabilize Facts

Status: started.

Outputs:

- Architecture audit document.
- RAG correctness fix for vector first-add and rebuild.
- Focused vector/RAG test pass.

Acceptance:

- Audit document records current facts and does not claim untested parity.
- Focused tests pass.
- Existing dirty worktree changes are preserved.

### Phase 1 - Reduce Structural Coupling

Work:

- Split `server/app_server.py` into:
  - `server/routes.py` or `server/http_handler.py` for request dispatch;
  - `server/evidence_bundle.py` for evidence/onboarding/readiness builders. Status: done for the first extracted evidence module.
  - `server/agent_bootstrap_api.py` for external Agent onboarding/quickstart/handoff payloads. Status: done on 2026-06-27 10:01.
  - `server/llm_probe_service.py` for probe/proof flows;
  - `server/session_api.py` for session endpoints. Status: done for the first payload-builder extraction on 2026-06-27 03:55.
  - `server/rag_evidence_service.py` for RAG benchmark/quality evidence cache and config resolution. Status: done on 2026-06-27 09:49.
- Split `agent/react_loop.py` into:
  - planning phase. Status: Plan First drafting/review/approval/no-approval extraction done in `agent/plan_first.py` on 2026-06-27 08:21.
  - action parsing/validation phase. Status: action execution/validation service extraction done in `agent/action_execution.py` on 2026-06-27 04:23.
  - context sync/checkpoint phase. Status: context-sync/checkpoint builder extraction done in `agent/context_sync.py` on 2026-06-27 04:40.
  - Maker guard phase. Status: first pure guard-rule extraction done in `agent/maker_guard.py` on 2026-06-27 04:05.
  - trajectory/result phase. Status: normal output/observation/result helper extraction done in `agent/trajectory_result.py` on 2026-06-27 08:34; expert loop-takeover extraction done in `agent/expert_takeover.py` on 2026-06-27 08:49; direct-action rescue append extraction done in `agent/rescue_application.py` on 2026-06-27 08:57.
- Replace `core/harness.py` and `core/project_context.py` compatibility imports with a deprecation-safe boundary that does not make `core` import higher layers during normal operation. Status: done on 2026-06-27 12:41 with lazy compatibility exports and boundary tests.

Acceptance:

- No behavior change in public endpoints.
- Existing route tests pass.
- Import audit no longer reports `core -> cli` or `core -> ecosystem` as normal imports. Status: focused audit passes.

### Phase 2 - Complete Event Bus Migration

Work:

- Make runtime metrics, project state, learning state, and selected memory metrics bus consumers by default.
- Keep SQLite as durable replay and SSE as UI transport.
- Add bus channel contracts for `session`, `learning`, `memory`, `project`, and `diagnostics`.
- Add observer failure counters instead of silent-only drops. Status: done for the base RuntimeEventBus and AppServer evidence summaries.
- Add dedicated learning and memory/RAG observers. Status: done for the first bus-backed observer path with store fallback.

Acceptance:

- Evidence Bundle exposes observer source for runtime/project/learning/memory.
- Bus tests cover replay, filtering, observer errors, and channel summaries.
- No consumer reads ReAct private queues when equivalent bus evidence exists.

### Phase 3 - RAG/Memory Performance

Work:

- Add `tests/test_rag_performance.py` or a benchmark script with deterministic fake embeddings.
  - Status: done for the first deterministic pytest benchmark.
- Record index size, first recall latency, warm recall latency, profile filter hit rate, fallback hit rate, and memory load time.
  - Status: done for the first fake-FAISS benchmark report.
- Add memory promotion/demotion:
  - private by default;
  - shared only after verified positive task evidence;
  - demote stale or repeatedly misleading memory.
  - Status: done for local policy and cold-memory ledger through `memory/shared_outcome.py` and `ColdMemory.record_shared_outcome()` on 2026-06-27 05:13.
- Connect learning validation to shared-memory outcome recording.
  - Status: done for the local bridge through `learning/shared_memory_bridge.py` and `TapMakerAgent._learn_from_session()` on 2026-06-27 05:31.
- Surface profile policy and recall stats in Workbench/evidence.
  - Status: done for compact Evidence/Readiness/Onboarding RAG benchmark status and Workbench RAG benchmark card.
  - 2026-06-27 05:13 update: Evidence JSON/Markdown also expose shared-memory outcome rules and unresolved conflict count.
- Separate deterministic speed evidence from production embedding semantic-quality claims.
  - Status: done for structured `embedding_quality` and `closure_gate` fields on 2026-06-27 09:11.
- Add a production embedding quality evaluation runner.
  - Status: done for `memory/rag_quality.py` and `/memory/rag-quality` on 2026-06-27 09:35.
  - Status: AppServer RAG evidence cache/config responsibility extracted to `server/rag_evidence_service.py` on 2026-06-27 09:49.
  - Pending: real project golden corpus, local production embedding artifact, and stable semantic recall quality budgets.

Acceptance:

- RAG benchmark has a budget and fails only on clear regressions.
- Evidence shows `workspace_profile`, top_k, recall hits, fallback state, and latency.
- Evidence/Onboarding show `rag_benchmark` status and budget result before strong memory/RAG speed claims.
- Evidence/Onboarding show `embedding_quality.status` and forbid production semantic-quality claims while `can_claim_production_embedding_quality=false`.
- Shared memory never exposes another agent's private records by default. Status: direct policy tests pass; promotion tests prove unverified records remain private.

### Phase 4 - Three-Layer Runtime Independence

Work:

- Give Agent, Runtime, and Learning independent health snapshots.
  - Status: first compact snapshot done through `server/layer_health.py` and `/sessions/{session_id}/layer-health?steps=20` on 2026-06-27 05:52.
- Define allowed communication:
  - Agent -> Runtime: validated action request.
  - Runtime -> Agent: observation/result.
  - Runtime -> Learning: trajectory and outcome.
  - Learning -> Memory: proposed knowledge record.
  - Learning -> Agent: compact advice only after validation.
  - Status: `layer_health.communication_contract.expected_routes` now reports observed route evidence for `user->agent`, `agent->runtime`, `runtime->learning`, and `learning->storage`; route absence remains visible instead of assumed.
- Define engineering-control thresholds and corrective actions.
  - Status: first layer-control surface done through `server/layer_control.py` and `/sessions/{session_id}/layer-control?steps=20` on 2026-06-27 06:06.
  - Covered: layer failures, missing layers, missing expected routes, max latency, learning queue depth, and observer errors.
  - Status: project-control and Workbench top corrective-action visibility done on 2026-06-27 06:20.
  - Status: non-layer engineering-control surface done through `server/engineering_control.py` and `/sessions/{session_id}/engineering-control?steps=20` on 2026-06-27 06:44.
  - Covered: memory/RAG zero-hit samples, memory recall latency, repeated tool failures, same-tool retry loops, failed plan gates, and failed goal gates.
  - Pending: automatic remediation and guarded corrective-action review/apply UX.
- Move learning jobs toward a managed worker queue with cancellation and retry policy.
  - Status: live session-scoped `LearningJobQueue` done on 2026-06-27 07:48 with cooperative cancellation, retry policy, worker idle timeout, public job snapshots, HTTP cancel/retry routes, and layer-health policy evidence.
  - Status: Workbench learning cancel/retry review controls done on 2026-06-27 08:06 with live-queue gating and durable replay unavailable messaging.
  - Pending: global cross-session worker pooling, visual GUI smoke, and production learning throughput budgets.

Acceptance:

- Layer evidence shows last event, state, latency, failure, and queue depth per layer. Status: first compact evidence surface verified on 2026-06-27 05:52.
- Layer-control evidence shows thresholds, signals, corrective actions, and truthfulness closure gates. Status: first compact control surface verified on 2026-06-27 06:06.
- Learning failure does not fail a successful user task, but the learning job itself surfaces failed/retryable evidence.
- Runtime side-effect failure cannot be silently rewritten as success.

### Phase 5 - COS Control Gates

Work:

- Attach COS classification to session creation. Status: done through `classify_cos_gate()` and the `cos_gate` RuntimeEventBus/SessionStore event.
- Persist classification, level, mode, and required gates in session evidence. Status: done through durable `cos_gate` event replay and computed fallback from session task.
- Implement POST automation for memory-health and sprint-board updates after substantive delivery. Status: partial; `project_control.memory_updates_due` now names the required POST files, but automatic writeback is not yet implemented.
  - 2026-06-27 03:33 update: guarded writeback is implemented as explicit plan/apply endpoints. Default POST is dry-run; file writes require `apply=true`, allowed POST docs, root-contained path validation, and idempotency markers.
- Enforce minute-precision timestamps in project memory docs.
- Add a project manager surface that can answer:
  - current focus;
  - next action;
  - blockers;
  - verification status;
  - memory updates due.
  Status: done for Evidence/Onboarding JSON/Markdown through `server/project_control.py`; Workbench card done on 2026-06-27 02:58; automatic POST/Sprint Board writeback remains pending.

Acceptance:

- Every session created through AppServer has a classification evidence item. Status: done for `AppServer.create_session()`.
- Evidence/Onboarding includes COS gate status. Status: done for JSON and Markdown surfaces.
- Evidence/Onboarding includes project-control status, next action, verification state, and memory updates due. Status: done for JSON and Markdown surfaces.
- POST memory update states touched files and verification result. Status: done for the explicit guarded writeback path; GUI apply/review remains a later UX decision.

### Phase 6 - Multi-Agent Collaboration

Work:

- Treat each agent as an identity with read/write memory policy.
- Add shared-memory promotion proposal records. Status: local cold-memory outcome records exist for verified promotion decisions.
- Add conflict records when agents disagree or overwrite assumptions. Status: unresolved same-claim conflict records are persisted by `ColdMemory.record_shared_outcome()`.
- Add learning-driven shared-memory handoff simulation. Status: deterministic local tests prove agent-b can read agent-a promoted learning memory while a conflicting agent-b claim stays private and records an unresolved conflict.
- Add a compact handoff protocol:
  - goal;
  - current plan;
  - evidence bundle;
  - memory policy;
  - open risks;
  - next action.

Acceptance:

- Two simulated agents can read shared/public memory while private memory remains isolated.
- Conflicting memory updates are recorded and require resolution. Status: local conflict-ledger and learning-bridge two-agent simulation tests pass; real multi-process orchestration remains pending.
- Handoff can be consumed without raw transcript replay.

### Phase 7 - Long-Task Continuity

Work:

- Emit scheduled continuation checkpoints during long runs.
- Add resume drills that restart the runtime and continue from Evidence/Context Sync.
  - Status: first durable store-replay drill done through `server/resume_drill.py` and `/sessions/{session_id}/resume-drill?steps=20` on 2026-06-27 07:13.
- Distinguish:
  - durable handoff resume;
  - warm process resume;
  - unproven in-process tool-call resurrection.
  - Status: capability levels are now explicit in `resume_drill`; warm process and hot tool-call remain `unproven`.

Acceptance:

- Resume evidence is explicit about capability level. Status: done for durable store-replay handoff on 2026-06-27 07:13.
- A restart drill can recover goal, open plan steps, last result, artifacts, and next action. Status: done for persisted store replay; a real process restart runner remains optional future work.
- The product does not claim hot-resume beyond proven behavior. Status: enforced by `resume_drill.closure_gate`.

## Performance Budgets

Initial budgets to prove or revise with benchmarks:

| Area | Target |
| --- | --- |
| App health endpoint | p95 < 50 ms locally |
| Evidence Bundle | p95 < 200 ms with 20 steps |
| RAG warm recall | p95 < 50 ms for 10k chunks with fake embeddings. Latest endpoint-backed vector-first sample: about 0.446 ms p95 for 10k+1 fake-FAISS records under `/memory/rag-benchmark?force=true`. |
| Production embedding quality | Unproven until `/memory/rag-quality` runs with a real project golden corpus and local production embedding artifact, then sets `embedding_quality.can_claim_production_embedding_quality=true`. |
| Context build | p95 < 150 ms excluding remote LLM call |
| Tool ranking | p95 < 25 ms for normal tool set |
| GUI first actionable state | < 2 s after backend readiness |

These budgets are not claims. They are gates to measure in future work.

## Truthfulness Gate

TTMEvolve should only make strong product claims when the claim has evidence:

- Code capability claim: requires a test, benchmark, or real GUI task run.
- Provider claim: requires `/llm/probe` or `llm_call_proof`.
- Maker authority claim: requires Maker setup/MCP readiness evidence.
- Memory/RAG speed claim: requires benchmark numbers.
- Production embedding semantic-quality claim: requires `rag_benchmark.embedding_quality.can_claim_production_embedding_quality=true`; deterministic fake-FAISS speed evidence is not enough.
- Multi-agent claim: requires a two-agent simulation or real handoff evidence.
- Long-task resume claim: requires a restart/resume drill.

If evidence is missing, the product wording must say `unproven`, `instrumented`, or `partial`.

## ADR Backlog

- ADR-0003: Modular Monolith With RuntimeEventBus Spine. Status: accepted on 2026-06-27 12:41.
- ADR-0004: Profile-Aware RAG And Shared Memory Policy.
- ADR-0005: COS Gates As Runtime Project Control.
- ADR-0006: Long-Task Continuation Capability Levels.

## Immediate Next Work

1. Extract evidence/readiness/onboarding builders from `server/app_server.py`.
   - Status: done for `server/evidence_bundle.py` on 2026-06-27 01:44.
2. Split AppServer route dispatch/session API from `server/app_server.py`.
   - Status: session-route payload builders extracted to `server/session_api.py` on 2026-06-27 03:55; RAG evidence service extracted on 2026-06-27 09:49; external Agent bootstrap payloads extracted to `server/agent_bootstrap_api.py` on 2026-06-27 10:01; full route dispatch split remains pending.
3. Implement automatic POST/Sprint Board writeback from `project_control.memory_updates_due`.
   - Status: done for guarded explicit plan/apply endpoints on 2026-06-27 03:33.
4. Add production embedding quality benchmark boundaries and shared-memory conflict resolution UX.
   - Status: benchmark truthfulness boundary done on 2026-06-27 09:11; evaluator endpoint done on 2026-06-27 09:35; AppServer RAG evidence service extraction done on 2026-06-27 09:49; real project golden corpus/local embedding artifact remains pending.
5. Define fuller layer-health snapshots and learning worker queue gates.
   - Status: first compact layer-health snapshot and queue-depth evidence surface done on 2026-06-27 05:52; first layer-control thresholds/actions done on 2026-06-27 06:06; live session-scoped managed learning queue/cancel/retry policy done on 2026-06-27 07:48; Workbench learning cancel/retry controls done on 2026-06-27 08:06.
6. Continue remaining `agent/react_loop.py` phase extraction with planning/trajectory boundaries, or begin restart/resume drills for long-task continuity.
   - Status: first durable resume drill done on 2026-06-27 07:13; Plan First phase extraction done on 2026-06-27 08:21; normal trajectory/result helper extraction done on 2026-06-27 08:34; expert loop-takeover extraction done on 2026-06-27 08:49; rescue direct-action append extraction done on 2026-06-27 08:57; warm/hot resume remain pending.
7. Feed layer-control corrective actions into Workbench/project-control review.
   - Status: done for compact visibility on 2026-06-27 06:20; guarded apply/review UX remains pending.
8. Add engineering-control thresholds for memory misses, repeated tool failures, and failed plan gates.
   - Status: done for the first evidence/control surface on 2026-06-27 06:44; automatic remediation remains pending.
9. Remove normal-operation `core -> cli` and `core -> ecosystem` imports from compatibility re-exports.
   - Status: done on 2026-06-27 12:41 through lazy compatibility exports plus `tests/test_core_boundary.py`.
10. Add a real project golden corpus/local production embedding artifact, split remaining AppServer route groups, or run a visual GUI smoke pass for Workbench learning controls.

Last updated: 2026-06-27 12:41
