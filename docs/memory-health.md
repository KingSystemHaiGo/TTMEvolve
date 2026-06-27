# Memory Health

## Memory Boundary

- This file records TTMEvolve project memory health and delivery POST notes.
- It is not Codex private self-memory.
- TTMEvolve is the product being developed; Codex is the developer assistant doing repository work under the user's direction.
- Runtime memory, learning, shared-memory policy, and persona files are TTMEvolve product surfaces. Keep them separate from assistant memory.
- Future entries should record product facts and verification, not imply mutual development between TTMEvolve and the assistant.

## 2026-06-27 13:33 Release Readiness Claim Modes POST

- Status: verified.
- Fixed: `scripts/release_readiness.py` now has explicit `--mode source-checkpoint` and `--mode full-offline` claim gates.
- Added: mode-scoped `required_checks`, `informational_checks`, and `out_of_scope` evidence so blocked full-offline requirements do not invalidate the source checkpoint claim.
- Preserved: full offline release remains strict. `--mode full-offline` currently returns `status=blocked` because `portable/python/python.exe` is missing and portable state is over the 500MB budget; signed installer, Maker remote build smoke, and production RAG semantic quality remain unproven.
- Verification: `py_compile scripts\release_readiness.py tests\test_release_readiness.py` passed; `tests\test_release_readiness.py` -> `6 passed`; source-checkpoint audit -> `status=ready`; full-offline audit -> `status=blocked`.
- Boundary: this is a truthfulness/control-gate fix. It does not build the offline runtime, sign an installer, run Maker remote build smoke, or prove production RAG semantic quality.
- Next: build or clean a real portable runtime bundle without deleting Maker auth state, then rerun the full-offline readiness gate.

## 2026-06-27 12:57 Source Release Checkpoint POST

- Status: verified.
- Added: `scripts/package_release.py` now builds a source checkpoint zip under `release-artifacts/` by default.
- Fixed: release packaging now excludes runtime/private/build state including `config.json`, `.env*`, `.mcp.json`, `storage/`, `portable/`, `vendor/`, `models/`, `workspace/`, `node_modules/`, `src-tauri/target/`, and local agent/editor state.
- Added: package manifest with SHA-256, file count, size, excluded prefixes, and forbidden-entry findings.
- Added: pre-write and post-write forbidden-entry validation; packaging fails if blocked entries appear in the candidate or final archive.
- Added: `tests/test_package_release.py` for release exclusion policy and archive blocker detection.
- Added: `scripts/release_readiness.py` and `tests/test_release_readiness.py` to audit package safety, manifest consistency, visible launch surface, ignored artifacts, and unproven release claims.
- Artifact: `release-artifacts/TTMEvolve-source-v0.4.5-one-click-practice-entry.zip` plus manifest. The manifest is the authoritative file-count, size, SHA-256, and forbidden-entry evidence.
- Verification: `py_compile` for package/readiness scripts/tests passed; `tests/test_package_release.py` -> `2 passed`; release readiness/package tests -> `5 passed`; package dry-run passed; package build created zip+manifest; independent zip scan -> `forbidden_count=0`, `probe_hits={}`; package/build/start-script focused pytest -> `36 passed`; release readiness audit -> `status=partial`, blockers `[]`, source checkpoint gate `true`, full publishable release gate `false`; `git diff --check` passed with existing LF/CRLF warnings only.
- Boundary: this is a source release checkpoint, not a full offline runtime bundle, signed installer, Maker remote build side-effect proof, or production RAG semantic-quality proof.
- Next: decide whether to run Maker remote build smoke, then prepare the final release checkpoint summary.

## 2026-06-27 12:41 Architecture Boundary Control POST

- Status: verified.
- Added: `docs/architecture/adr-0003-modular-monolith-runtime-event-bus.md` accepts the modular monolith plus `RuntimeEventBus` spine decision.
- Updated: `docs/architecture/architecture-control-roadmap-2026-06-27.md` now records the 12:41 line-count audit, ADR status, and core-boundary closure.
- Fixed: `core/harness.py` and `core/project_context.py` keep backward-compatible exports through lazy `__getattr__`, so importing core compatibility modules no longer loads `cli.harness` or `ecosystem.project_context` during normal operation.
- Added: `tests/test_core_boundary.py` proves the lazy boundary while preserving compatibility symbol access.
- Verification: `tests/test_core_boundary.py tests/test_runtime_events.py tests/test_runtime_contract.py` -> `19 passed`; static core import audit found no `from cli` / `from ecosystem`; `git diff --check` passed with existing LF/CRLF warnings only.
- Boundary: this closes the known core compatibility import leak. Remaining architecture-control work still includes full AppServer route dispatch extraction, production RAG golden-corpus evidence, GUI smoke for Workbench learning controls, release packaging, and optional Maker remote build smoke.
- Next: split remaining AppServer route groups or add real project RAG golden-corpus/local embedding evidence.

## 2026-06-27 02:43 Project Control Evidence POST

- Status: verified.
- Added: project-control evidence now turns COS Gate 0 plus project-state evidence into a compact project-manager summary.
- Added: Session Evidence and LLM Onboarding now expose project-control status, next action, blockers, verification state, and memory updates due.
- Fixed: runtime-advice warnings no longer steal the project observer's known next action; MakerMCP warnings stay visible in runtime advice/live gaps.
- POST-mem touch: `docs/memory-index.md` edited.
- POST-sync touch: `docs/sprint-board.md` edited.
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` edited.
- Verification: project-control/AppServer evidence focused pytest -> `4 passed`; readiness/contract/session-store/intent focused pytest -> `50 passed`; `git diff --check` passed with existing CRLF warnings only.
- Next: wire `project_control` into GUI project-manager mode and automatic POST/Sprint Board writeback.

## 2026-06-27 02:58 Workbench Project Control POST

- Status: verified.
- Added: Agent Workbench now renders a Project Control card from Evidence Bundle `project_control` data.
- Added: the card exposes status, COS gate progress, verification state, POST due count/files, blockers, and next action without moving internal debug events into the main chat.
- Preserved: existing Workbench semantic theme tokens and evidence stack layout.
- Verification: `npm.cmd --prefix frontend run build` passed; project-control/evidence pytest -> `3 passed`; `git diff --check` passed with existing CRLF warnings only; Vite `http://127.0.0.1:5177/` returned HTTP 200.
- Next: automatic POST/Sprint Board writeback from `project_control.memory_updates_due`.

## 2026-06-27 02:12 COS Gate 0 Evidence Surface

- Status: verified.
- Added: `core.intent_classifier.classify_cos_gate()` now produces deterministic COS Gate 0 fields: task type, S/M/L/XL level, System 1/System 2 mode, understanding status, declaration line, required gates, POST requirements, truthfulness rule, vague-instruction protocol, multi-agent guidance, and project-management guidance.
- Added: `AppServer.create_session()` now emits a `cos_gate` event through the shared RuntimeEventBus and persists it through `SessionStore`, preserving SQLite/SSE compatibility without adding a schema migration.
- Added: Runtime Readiness, Session Evidence JSON/Markdown, and LLM Onboarding JSON/Markdown now expose `cos_gate`; Onboarding closure gates include a `cos_gate` check.
- Verified: `.venv\Scripts\python.exe -m pytest tests\test_intent_classifier.py tests\test_app_server_resume.py::test_app_server_create_session_persists_cos_gate_event tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `33 passed`.
- Verified: `.venv\Scripts\python.exe -m pytest tests\test_session_store.py tests\test_runtime_contract.py tests\test_app_server_resume.py::test_app_server_runtime_readiness_endpoint tests\test_app_server_resume.py::test_app_server_runtime_metrics_endpoint_uses_bus_observer tests\test_runtime_events.py -q` -> `29 passed`.
- Verified: `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py -q` -> `24 passed`.
- Verified: intent e2e classifier checks -> `2 passed`; `git diff --check` passed with only existing CRLF warnings.
- Next: add POST/project-manager automation on top of the emitted COS gate and continue splitting AppServer route/session dispatch.

## 2026-06-27 01:44 AppServer Evidence Builder Extraction

- Status: verified.
- Added: `server/evidence_bundle.py` now owns compact evidence/readiness/onboarding/quickstart builders and supporting summaries.
- Reduced: `server/app_server.py` is now focused more tightly on HTTP routing, AppServer lifecycle, sessions, and mutable runtime state; line count is `2104` after extraction.
- Preserved: public endpoints and payloads for runtime readiness, runtime metrics, project state, session evidence, onboarding, quickstart, RAG benchmark, and LLM feedback remain routed through AppServer.
- Verified: `tests/test_runtime_contract.py tests/test_rag_performance.py tests/test_app_server_resume.py::test_app_server_runtime_readiness_endpoint tests/test_app_server_resume.py::test_app_server_runtime_metrics_endpoint tests/test_app_server_resume.py::test_app_server_evidence_bundle_endpoint` -> `13 passed`.
- Verified: `tests/test_app_server_resume.py::test_app_server_runtime_metrics_endpoint_uses_bus_observer tests/test_app_server_resume.py::test_app_server_project_state_endpoint_uses_bus_observer tests/test_runtime_events.py` -> `11 passed`.
- Verified: `git diff --check` passed.
- Next: split AppServer route dispatch/session API, then attach COS classification and gates to session evidence.

## 2026-06-27 01:28 Workbench RAG Benchmark Surface

- Status: verified.
- Added: Agent Workbench now shows a `rag_benchmark` panel sourced from Evidence Bundle data when available.
- Added: the panel can refresh `GET /memory/rag-benchmark?force=true` directly and displays budget status, record count, first recall latency, warm p95 recall latency, endpoint/cache/no-network details, and the benchmark truthfulness boundary.
- Preserved: Maker preview/layout is not hidden; the panel is inside the existing Workbench evidence stack and uses existing semantic theme tokens.
- Verified: `npm.cmd --prefix frontend run build` passed.
- Verified: Vite dev entry responded at `http://127.0.0.1:5177/` with HTTP 200.
- Verified: `git diff --check` passed.
- Next: extract AppServer evidence/readiness/onboarding builders and attach COS classification/gates to session evidence.

## 2026-06-27 01:12 RAG Benchmark Evidence Endpoint

- Status: verified.
- Added: deterministic no-network RAG benchmark service in `memory/rag_benchmark.py`.
- Added: `GET /memory/rag-benchmark` product endpoint with a 300-second cache; `force=true` refreshes the local report.
- Added: Runtime Contract, Runtime Readiness, Session Evidence JSON/Markdown, and LLM Onboarding JSON/Markdown now expose compact `rag_benchmark` status, budget result, p95 recall latency, and endpoint.
- Truth boundary: this benchmark proves deterministic local memory/RAG pipeline performance only; it does not prove production embedding quality.
- Measured: 10,001 records, build `760.314 ms`, cold start `128.648 ms`, first recall `13.494 ms`, warm p95 `16.282 ms`, profile/fallback hit rates `1.0`, budget `pass`.
- Verified: `tests/test_rag_performance.py tests/test_runtime_contract.py tests/test_app_server_resume.py::test_app_server_evidence_bundle_endpoint` -> `11 passed`.
- Verified: vector/RAG/memory/shared-policy/runtime-contract focused suite -> `41 passed`.
- Verified: `git diff --check` passed.
- Next: surface the benchmark in the Workbench UI and continue extracting AppServer evidence/readiness/onboarding builders into smaller modules.

## 2026-06-27 00:42 Runtime Learning/Memory Observer Evidence

- Status: verified.
- Added: `server/learning_observer.py` derives compact learning-layer state from RuntimeEventBus `layer` events without reading TapMakerAgent private learning job state.
- Added: `server/memory_observer.py` derives memory/RAG recall metrics from `context_budget` events and shares the same aggregation logic with SQLite replay fallback.
- Added: AppServer Runtime Readiness, Session Evidence JSON/Markdown, and LLM Onboarding JSON/Markdown now expose `learning_observer` and `memory_recall` evidence.
- Preserved: SQLite remains durable replay; live bus observers are preferred when present, while persisted `context_budget` events can still produce Memory/RAG summaries after restart.
- Verified: `tests/test_runtime_events.py` plus focused AppServer readiness/evidence tests -> `11 passed`; `tests/test_session_store.py` plus runtime-metrics endpoint -> `11 passed`; `git diff --check` passed.
- Next: extract Evidence/Readiness/Onboarding builders out of `server/app_server.py` and add deterministic RAG performance benchmarks.

## 2026-06-27 00:54 Deterministic RAG Performance Benchmark

- Status: verified.
- Added: `ColdMemory.bulk_index()` for batch archive/index loading with one JSON save and one vector add batch.
- Added: `tests/test_rag_performance.py` with a deterministic fake-FAISS benchmark over 10k+1 memory records.
- Measured: build `637.869 ms`, cold start `102.919 ms`, first recall `17.17 ms`, warm recall p95 `13.61 ms`, profile hit rate `1.0`, fallback hit rate `1.0`.
- Budget gates: build `<2000 ms`, cold start `<500 ms`, first recall `<75 ms`, warm recall p95 `<50 ms`, profile/fallback hit rates `1.0`.
- Verified: `tests/test_rag_performance.py` -> `2 passed`; RAG/memory policy focused suite -> `23 passed`; vector+RAG suite -> `11 passed`.
- Next: surface benchmark reports through Evidence/Workbench and continue AppServer evidence-builder extraction.

## 2026-06-27 00:06 Architecture Control + Vector Index Correctness POST

- Added `docs/architecture/architecture-control-roadmap-2026-06-27.md` with an evidence-based audit for module coupling, RuntimeEventBus migration, RAG/vector memory, three-layer runtime independence, COS gates, multi-agent memory, engineering control loops, truthfulness gates, project management, and long-task continuity.
- Audit facts recorded: 114 Python files scanned; largest coupling hotspots are `server/app_server.py`, `agent/react_loop.py`, `agent/agent.py`, and `core/executor.py`; compatibility imports still create `core -> cli` and `core -> ecosystem` boundary debt.
- Fixed vector index correctness: first vector add now builds the FAISS index when FAISS/encoder are available, and `_rebuild_index()` now creates a fresh FAISS index instead of appending duplicate chunks to an old one.
- Added regression coverage using fake FAISS so rebuild semantics are verified without requiring the local FAISS package.
- Verified: `.venv\Scripts\python.exe -m pytest tests\test_vector_index.py tests\test_cold_memory_vector.py tests\test_memory_manager_recall.py -q` -> `21 passed`.
- Next: extract evidence/readiness/onboarding builders from `server/app_server.py`, add a deterministic RAG performance benchmark, attach COS classification to session evidence, and add RuntimeEventBus observer failure counters.

## 2026-06-27 00:20 Runtime Event Bus Observer Failure Evidence POST

- Fixed RuntimeEventBus observability gap: observer callback exceptions still do not break publish/replay, but they now increment `observer_error_count`, update `observer_errors_by_handler`, and retain compact `last_observer_error` details.
- Added AppServer summary evidence: `runtime_event_bus.observer_health` and `runtime_event_bus.observer_error_count` now appear in Runtime Readiness, Session Evidence JSON/Markdown, and LLM Onboarding Markdown through the existing runtime event bus summary.
- Updated architecture roadmap to mark base observer failure counters as done and move next bus work toward dedicated learning/memory observers.
- Verified: `.venv\Scripts\python.exe -m pytest tests\test_runtime_events.py tests\test_app_server_resume.py::test_app_server_runtime_readiness_endpoint tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `9 passed`.
- Verified: `git diff --check` passed.
- Next: add learning/memory bus observers and start extracting `server/app_server.py` evidence builders into smaller modules.

2026-06-22: Captured layout/runtime reality check and refactor direction. Memory paths in project instructions reference missing `.Codex/memory`; used `docs/memory-index.md` and `docs/sessions/` instead.
2026-06-22: Captured API-first LLM runtime refactor. Important lesson: GUI may boot with `UnconfiguredLLM`, but normal execution must use a real API provider or explicit local GGUF, never mock.
2026-06-22: Captured provider model discovery fix. Future provider integrations should include model list discovery or model hints, not only a freeform model input.
2026-06-22: Captured layout correction. Avoid letting persisted pane widths dominate the first viewport; default IDE must prioritize editor space and avoid recursive self-preview.
2026-06-22: Captured agent conversation correction. Successful API calls still feel wrong if thoughts/actions are rendered as raw logs; show thought as agent cognition and keep the three core layers visible.
2026-06-22: Captured shell layout correction. IDE workspace should be primary; Agent belongs as a right copilot panel with provider config collapsed by default.
2026-06-22: Corrected layout principle after comparing TapTap Maker web: default Maker mode should be left Agent/task console plus right stage/workspace, not a generic right-copilot IDE shell. Closing GUI must terminate the whole local runtime.
2026-06-22: Corrected workspace priority: Preview/stage must be central, code editor should behave like an optional drawer when no file is open.
2026-06-22: Captured full runtime review. Principal contradiction is deterministic, trustworthy Agent runs; shared runtime is serialized for now, next step is per-session AgentRuntime plus structured workbench state.
2026-06-22: Upgraded runtime isolation from `_run_lock` serialization to session-scoped agents with shared Maker MCP attachment. Next risk is turning raw SSE into structured workbench state.
2026-06-22: Added frontend AgentWorkbenchState normalization. Next bottleneck is action reliability: constrained JSON, tool subset ranking, and less prompt weight.
2026-06-22: Addressed Maker cockpit usability complaints and runtime prompt weight. Default preview opens TapTap Maker; chat queues messages; file attach opens Electron dialog; Workbench consumes real layer/tool-selection events; ReAct now ranks/caps tools and API action prompts use constrained JSON.
2026-06-22: Captured Agent transcript rule. Chat/event rows must not be fixed-size cards with hidden overflow; tool calls, observations, thoughts, and outputs should show full content, with virtualization only at the outer list level if needed.
2026-06-22: Captured transcript/debug separation. Hide internal `status` and `tool_selection` events from main chat; use Workbench/debug surfaces for runtime internals. Collapsed rails should be narrow controls, not content-like vertical cards.
2026-06-22: Captured preview-stage rule. Central preview must be Maker browser only; file preview belongs with file tree/editor. Current browser is screenshot-backed Playwright, so clicks must map to page coordinates and polling must stay conservative until BrowserView/WebView replaces it.
2026-06-23: Upgraded Electron GUI preview to native `BrowserView` via `electronAPI.makerBrowser`; Playwright screenshot preview is now fallback/Agent-tool surface, not the primary user preview.
2026-06-23: Closed first real LLM self-feedback loop. MiniMax-M3 identified opaque tool validation as the top runtime pain; ReAct validation observations now include stable `failure_type=tool_validation`, `rule_id`, `path`, `reason`, `suggested_fix`, and `structured_errors` so the model can repair tool calls instead of guessing from prose.
2026-06-23: Added cooperative session cancellation after follow-up LLM interview timed out. GUI now has a Stop button, backend exposes `POST /sessions/{id}/cancel`, ReAct/Agent check cancellation between phases, approval waits are unblocked, and SQLite persists `status=canceled`. Boundary: blocking external calls still stop at the next checkpoint until provider/tool-level timeouts are added.
2026-06-23: Added runtime latency telemetry. ReAct now emits `latency` events for first response, LLM think/action, iteration planning, tool calls, and total session time. Agent Workbench summarizes first response, latest LLM, latest tool, and total runtime without putting debug timing rows into the main chat.
2026-06-23: Hardened API timeout behavior. Remote LLM clients default to 45s, expose structured `LLMTimeoutError`/`LLMAPIError`, and preserve failure stats in `last_call_stats`. LLM runtime interview uses a cloned config with `llm.interview_timeout` defaulting to 30s and returns structured timeout JSON instead of hanging.
2026-06-23: Added Maker MCP diagnostics. `MCPIntegration.status()` and `/mcp/status` expose connected state, tool schemas, last error, and last call elapsed time; `/mcp/tools` exposes discovered Maker tools. Cockpit header now shows connected/disconnected plus tool count instead of only package version.
2026-06-23: Promoted three-layer architecture from UI labels to a typed communication protocol. LayerEvent now carries source/target layer, event, cause, correlation id, and metrics; Workbench displays real Agent -> Runtime -> Learning -> Storage handoffs. Compliance report lives at docs/architecture/self-evolving-agent-compliance-2026-06-23.md. Next gap: surface repair/evolution EventLog events and make learning async/proposal-based.
2026-06-23: Started LLM-as-user feedback loop. Actual MiniMax-M3 feedback interviews timeout even in light mode, so feedback collection now has independent llm.feedback provider/model/base_url/timeout routing, durable docs/llm-feedback artifacts, and summary tooling. Next: configure a faster feedback model and iterate from successful JSON feedback.
2026-06-23: Added shared runtime event envelope for internal communication. AppServer/SSE/SessionStore events now carry event_id/channel/source/correlation_id metadata, and LLM feedback artifacts include llm_feedback events on the feedback channel. Next: surface feedback/meta in UI and bridge repair/evolution EventLog into the same channel.
2026-06-23: Verified MiniMax API is genuinely called; slow feedback runs are service-side generation/reasoning latency, not a dead API path. Implemented the LLM's P0 feedback: shell/MCP tool calls now have timeouts, partial observations, timeout diagnostics, and ReAct `[tool_timeout]` context hints so the model can continue after blocked tools.
2026-06-23: Continued real LLM-as-user loop after tool timeouts. New MiniMax feedback identified uncertainty after write timeout/cancel as P0. Added `idempotency_key`, `committed`, and `observed_at` to side-effecting tool observations and surfaced latest commit state in AgentWorkbench. Next: reconcile/query support for `committed=null` Maker MCP writes and persistent commit-state history.
2026-06-23: Strengthened the LLM feedback loop so it is not blindly followed. Interview prompts now state already-completed mechanisms and artifacts include a `critique` block for stale claims. Implemented the latest valid feedback by adding commit-state history plus ReAct `commit_reconcile` events for `committed=null`; local file writes/deletes can now be verified automatically, while remote Maker effects stay explicit `unknown` until task/file ids are available.
2026-06-23: Implemented the latest successful LLM feedback P0: long-running tools now emit `tool_progress` heartbeat SSE events with elapsed time and heartbeat count, and AgentWorkbench shows progress on running tool rows without spamming main chat. Follow-up MiniMax feedback timed out before headers after 25.1s (`response_started=false`), so the next loop should route `llm.feedback` to a faster provider/model.
2026-06-23: Continued LLM-as-user loop with fallback repair. MiniMax still timed out before headers at 8s, but DeepSeek fallback plus larger repair token budget returned complete JSON. Implemented valid mapped feedback: MCP status now diagnoses remote task/file id lookup and latest id fields; health/workbench now expose context saturation instead of blindly adding a new compression algorithm.
2026-06-23: Latest LLM feedback, after prompt facts were refreshed, advanced to remote `committed=null` reconciliation. Fixed feedback repair timeout/skipped-fallback masking, then implemented conservative Maker MCP remote commit lookup via discovered task/file tools. Important guardrail: remote lookup only marks committed when explicit identity matches; tool-name-only matches are rejected to avoid false positives.
2026-06-23: Continued LLM-as-user loop through multiple refreshed interviews. Implemented tool preflight alternatives, per-step `plan_validation`, active context compression metrics/important-step retention, and `/sessions/{id}/commit-history` plus `/submissions` read-only history endpoints. Latest next direction: richer cross-step goal decomposition/acceptance criteria and feedback artifact UI.
2026-06-23: Added ReAct `goal_checklist` acceptance tracking and cross-Agent skill sync manifest/conflict detection. Future feedback saying "no skill sync" is stale unless it specifically asks for automated repair/export/heartbeat on top of `ecosystem/skill_sync.py`, `scripts/sync_skills.py`, and `/skills/sync-status`.
2026-06-23: Extended skill sync into a shared runtime registry: safe export plans, `storage/skill_sync/registry.json`, dynamic `skill_graph`, ReAct `skill_sync` events after session start/plan validation, compatibility warnings, and Agent-callable `query_skills`. Future generic "cross-Agent skill sync missing" feedback is stale unless it asks for remote invocation, external MCP broadcast, or graph UI.
2026-06-23: Added Workbench Skill Graph UI plus ReAct `context_sync` snapshots. Runtime now emits revisioned/deduped compact session context after meaningful changes, including last tool, plan/goal state, commit/skill summaries, and artifact refs; Workbench displays this without clipping thought text. Future generic "missing context sync" feedback is stale unless it asks for cross-process broadcast or distributed context sharing.
2026-06-23: Added pull-based context sync API: `GET /sessions/{id}/context-sync?steps=N` reads persisted `context_sync` snapshots for external agents/processes. MiniMax feedback still times out before headers at 8s; DeepSeek continues to give stale generic skill-registry feedback with fictional paths.
2026-06-23: User updated the goal: arbitrary LLM onboarding + MakerMCP deep binding, independent-but-communicating Agent/Core/Learning layers, extreme token efficiency, full frontend/backend connection, and modern TapTapMaker-themed UI. Added feedback actionability gate so stale/fictional-path LLM suggestions become `actionable=false` instead of driving implementation blindly. External feedback run now requires explicit approval because it sends internal architecture to third-party LLMs.
2026-06-23: Added Runtime Contract foundation for arbitrary LLM onboarding. `core/runtime_contract.py`, Agent tool `runtime_contract`, ReAct prompt injection, and `GET /agent/runtime-contract` now expose MakerMCP readiness, layer responsibilities/events, communication endpoints, token-efficiency rules, and skill graph status in one compact contract.
2026-06-23: Surfaced Runtime Contract in AgentWorkbench. Frontend fetches `GET /agent/runtime-contract?session_id=...` after session creation and shows MakerMCP readiness, tool count, remote identity, context endpoint, token rules, and warnings with TapTapMaker-like status styling.
2026-06-23: Added MakerMCP first-action checklist and warning codes to Runtime Contract and Workbench. Important lesson: prompt-side contracts must put machine-readable critical state before long UI-friendly text, or truncation can hide the exact warning an LLM needs.
2026-06-23: Added Maker task templates and external-agent attach protocol to Runtime Contract. Important lesson: full workflow detail belongs in the UI/API contract; prompt rendering should keep only action IDs, statuses, suggested tools, and communication endpoints.
2026-06-23: Wired Maker task template acceptance criteria into live goal_checklist and added `/agent/handoff`. Important lesson: onboarding contracts become operational only when they seed runtime state and expose a single compact handoff payload for other agents.
2026-06-23: Surfaced Maker-template acceptance criteria in Workbench. Important lesson: runtime state is not useful enough unless users can see which Maker workflow is driving acceptance and why a criterion is open/done.
2026-06-23: Added Workbench handoff surface for external agents. Important lesson: cross-agent compatibility needs a visible copyable entry point, not only a backend endpoint or prompt contract.
2026-06-23: Added live Workbench preview for `/agent/handoff`. Important lesson: show summaries of compact handoff bundles, not raw JSON, and fetch them on demand to keep normal sessions light.
2026-06-23: Made ranked tool/context retrieval observable and cache-aware. ToolRegistry now caches rank results and emits candidate/selected/ranking/cache stats; ContextBudget/MemoryManager expose token cache, AGENTS.md recall, cold recall, and context build timings through ReAct `context_budget` and Workbench Runtime metrics. Next use these numbers in a real GUI session before guessing at further latency fixes.
2026-06-23: Added pullable runtime diagnostics API. `GET /sessions/{id}/runtime-metrics?steps=N` compacts latency, LLM usage, tool ranking, and context budget events; Runtime Contract, handoff bundle, and Workbench now expose it. Important lesson: external agents should read compact diagnostics instead of replaying raw SSE when diagnosing latency/token cost.
2026-06-23: Made the learning layer genuinely asynchronous and bridged Agent layer events into AppServer. `agent.run()` now returns after Runtime audit while eligible reflection continues as a tracked background learning job; `/sessions/{id}/learning` and handoff `learning_latest` expose status. Important lesson: three-layer architecture is only real when layer events survive the AppServer/SSE/persistence path.
2026-06-23: Added Maker first-action briefing. `/agent/maker-briefing` and Agent tool `maker_briefing` compress Runtime Contract + Maker templates into a concrete first action, authority choice, suggested tools, and evidence endpoints. Important lesson: LLM onboarding improves when the next action is computed from live contract state, not left as prose instructions.
2026-06-23: Injected Maker briefing into the first ReAct context and Workbench runtime state. Important lesson: a contract is not enough for arbitrary LLMs; the next action must be present before first tool selection and visible as runtime evidence, while staying out of the main chat transcript.
2026-06-23: Added Maker first-action guard. Important lesson: arbitrary LLM onboarding needs runtime enforcement as well as prompt injection; block local side effects before Maker authority, emit structured guard evidence, and let Workbench show the alignment without main-chat noise.
2026-06-23: Added pullable Maker guard history and handoff evidence. Important lesson: runtime alignment checks must be available as compact APIs for external agents; raw SSE replay is too expensive and too noisy for cross-agent handoff.
2026-06-23: Closed Workbench display for Maker guard evidence and reran broad AppServer/layer regression successfully. Important lesson: backend runtime evidence is only useful when the UI handoff surface shows it beside briefing/runtime/learning summaries.
2026-06-23: Added runtime_advice over briefing/guard/metrics/learning/context evidence. Important lesson: external LLMs need a compact next diagnostic action, not only many separate evidence endpoints.
2026-06-23: Added external LLM quickstart bundle. Important lesson: "any LLM can start coding quickly" needs one startup packet with prompt, boot order, advice, Maker authority, endpoints, and rules.
2026-06-23: Added Workbench Quickstart preview and Copy Prompt. Important lesson: onboarding is incomplete until the UI gives users a one-click prompt, not just an API endpoint.
2026-06-23: Upgraded quickstart copy target to Markdown. Important lesson: external agents need structured startup cards with sections/endpoints/rules, not only a short instruction sentence.
2026-06-23: Added direct Markdown quickstart endpoint and Copy MD URL. Important lesson: external agents may prefer fetching a markdown URL over parsing JSON or receiving pasted text.
2026-06-23: Added quickstart surface profiles for generic/Codex/Claude Code/opencode. Important lesson: compatibility with agent ecosystems needs explicit memory/skill conventions, not only a generic prompt.
2026-06-23: Added Workbench surface selector and API runtime evidence. Important lesson: diagnose MiniMax/API usage through provider endpoint stats, not local model loaded/cold language.
2026-06-23: Added active LLM runtime probe. Important lesson: provider wiring should be proven with a tiny explicit request and endpoint stats before spending a full agent run.
2026-06-23: Threaded LLM probe evidence through quickstart/handoff/advice. Important lesson: diagnostics only help arbitrary LLMs when they appear in the same compact evidence surfaces used for onboarding.
2026-06-23: Made LLM probe evidence session-scoped. Important lesson: handoff evidence should survive refresh/restart and be pullable by session, not only live in process memory.
2026-06-23: Made session-scoped LLM probes live in the GUI. Important lesson: pullable diagnostics are not enough for cockpit UX; active sessions must emit the same evidence through SSE/Workbench, and recreated session ids must not inherit stale events.
2026-06-23: Promoted runtime_advice from endpoint-only to a live Workbench control surface. Important lesson: arbitrary LLM onboarding needs a visible next-action diagnosis that refreshes from probe/guard/context/latency/learning evidence, not only copied URLs.
2026-06-23: Promoted runtime_metrics from handoff-only evidence to a live Workbench instrument panel. Important lesson: token efficiency work needs visible latency/token/cache/retrieval/tool-ranking numbers in the cockpit, not only after-the-fact endpoint pulls.
2026-06-23: Promoted learning status from endpoint/layer-pill evidence to a live Workbench panel. Important lesson: three-layer architecture feels real only when the Learning layer's async reflection state is visible beside Runtime advice and metrics.
2026-06-23: Added one-click External Agent Boot links in Workbench. Important lesson: "any LLM can start quickly" needs a copyable boot checklist of compact evidence endpoints, not scattered URL blocks the user has to assemble manually.
2026-06-23: Added compact Evidence Bundle. Important lesson: arbitrary LLMs should pull `/sessions/{id}/evidence?steps=20` first for advice/briefing/latest metrics/learning/guard/probe/counts/endpoints, then fetch Handoff or raw histories only when the bundle is insufficient.
2026-06-23: Made Workbench consume Evidence Bundle for auto-refresh. Important lesson: compact evidence endpoints only improve speed if the GUI hydrates live panels from the bundle and reserves detail endpoints for manual drill-down.
2026-06-23: Added pasteable Evidence Markdown. Important lesson: external LLM onboarding must work even when the LLM cannot fetch localhost; provide `/sessions/{id}/evidence.md` and Workbench Copy Evidence as a text artifact.
2026-06-23: Added three-layer evidence summary. Important lesson: external agents should diagnose Agent/Runtime/Learning ownership from compact `layer_summary`, not by replaying raw SSE.
2026-06-23: Added MakerMCP authority evidence and learned `styles.css` visual language. Important lesson: compact evidence must show MakerMCP readiness/tool authority, and TapTapMaker styling should flow from shared tokens (`#00D9C5`, `#F7F9FA`, 6/8/10/16px radii, subtle shadows, thin scrollbars, teal focus ring).
2026-06-23: Cleaned Workbench panels onto semantic TapTapMaker tokens and removed clipped Workbench error display. Important lesson: visual alignment should be enforced through shared tokens, and diagnostic/error text must always wrap/show full content because agents need inspectable evidence.
2026-06-23: Cut v0.4.1 Runtime Readiness as a stable checkpoint. Important lesson: before Quickstart/Evidence/Handoff, arbitrary LLMs need one no-network readiness gate that says provider/Maker/layer status, release blockers, and next actions without spending tokens or calling APIs.
2026-06-24: Added v0.4.1 completion audit and synchronized package metadata. Important lesson: do not mark a broad product goal complete from feature presence alone; distinguish a verified stable checkpoint from real-environment proof still needed.
2026-06-24: Added no-network API call proof and local LLM feedback summary. Important lesson: answer "did MiniMax really get called?" with expected-vs-observed endpoint evidence (`llm_call_proof`), and reuse saved feedback artifacts when fresh external LLM interviews are blocked by data-disclosure policy.
2026-06-24: Cleaned frontend mojibake in Workbench status text. Important lesson: after writing Chinese through shell/Python on Windows, scan for `????`, private-use characters, and mojibake markers before trusting the UI.
2026-06-24: Cut v0.4.2 Onboarding Closure. Important lesson: any-LLM startup should begin with one closure-aware evidence packet (`/agent/onboarding`) that combines readiness, Maker authority, layer state, token strategy, API proof, and next action before raw SSE or detailed histories.
2026-06-24: Cut v0.4.3 Maker Setup + Chat-First. Important lesson: real Maker testing must be gated by install/init/auth/project/tool-audit evidence first; chat-native UX should make setup and IDE tools supporting surfaces around the conversation, not the starting burden.
2026-06-24: Cut v0.4.4 Portable Agent Root. Important lesson: before real Maker testing, verify `/runtime/portable`; runtime home/cache/temp/Maker auth/npm/pip/HF/Playwright state must stay under the Agent root (`portable/` and `storage/`), and `C:\Users\...` leakage is a blocker.
2026-06-24: Cut v0.4.5 One-Click Practice Entry. Important lesson: real Maker testing should start from the GUI Maker Setup `Practice` button when the GUI is available; `start-practice.bat` is the bootstrap fallback. Maker CLI logs, PAT/auth URL, app-index input, and cancel should stay inside TTMEvolve rather than making cmd the primary UX.
2026-06-24: Corrected launch UX requirement. Important lesson: visible GUI launcher/shortcut is the user entry; `.bat`/`.ps1` are backend details and should not be presented as normal operation.
2026-06-24: Fixed GUI startup and transcript noise. Important lesson: backend health-check timeout is a GUI-degraded state, not a native modal blocker; `thought` events should feed Workbench/currentThought, while the main chat should receive only one final assistant reply per session.
2026-06-24: Updated visible GUI information architecture. Important lesson: first screen should expose only Agent chat, Maker preview, and compact status/topbar controls; file tree and asset library belong behind chat-adjacent tool buttons, and user-visible text must be Chinese for the primary China user base.
2026-06-24: Fixed GUI overlay hierarchy after screenshot review. Important lesson: Electron BrowserView is a native layer and must be explicitly hidden while HTML settings overlays are open; duplicate Maker entry points and always-visible process/setup strips should be removed from the main screen, while file/assets should open as side drawers rather than floating popovers.
2026-06-24: Corrected file/assets drawer placement. Important lesson: file tree and asset library should render as a middle workspace column between Agent chat and Maker preview, not as overlays inside the chat panel.
2026-06-24: Generalized auxiliary GUI surfaces. Important lesson: tools, settings, file tree, and asset library should all render as middle workspace columns so the native Maker BrowserView keeps running; startup should show a progress window until backend health and renderer readiness are complete.
2026-06-24: Deduplicated GUI settings/tool entries. Important lesson: status pills are passive only; actionable `可用工具` belongs with top actions, settings has one chat-bottom entry, and tools/settings should open as page-like list/settings surfaces while file/assets remain middle side drawers.
2026-06-24: Compact preview chrome and added dark mode/forum. Important lesson: do not spend a full row on chat title plus browser URL toolbar by default; top actions should handle Maker/forum navigation, and dark mode must cover both TTMEvolve shell tokens and native Maker BrowserView injection.
2026-06-24: Corrected chat message shape. Important lesson: user instructions are right-aligned bubbles, assistant replies are full-width Markdown-rendered answer pages, and runtime/tool events are compact status rows with details hidden unless needed.
2026-06-24: Integrated chat status controls into the panel. Important lesson: `ready/history/collapse` controls should be a slim in-flow chat bar, not an absolute floating card over the empty conversation area.
2026-06-24: Fixed BrowserView theme drift. Important lesson: native Maker preview needs explicit light and dark injection plus DOM normalization; removing dark CSS alone can leave black preview chrome, and dark mode must actively cover Maker's white/gray toolbar surfaces.
2026-06-24: Hardened BrowserView theme sync after screenshot proved CSS-only failed. Important lesson: Maker's own SPA theme state must be updated through classes/data attrs/localStorage/sessionStorage/meta color-scheme and then reloaded; otherwise TTMEvolve can be light while Maker remains dark.
2026-06-24: Replaced Settings native selects with custom pickers. Important lesson: Windows/Electron native select popups can ignore app dark tokens and become unreadable white/light-gray surfaces; critical settings controls need theme-aware custom dropdowns.
2026-06-24: Added GUI Maker Access Center and preview-bottom cockpit bar. Important lesson: Maker install/init/upgrade/auth/tool audit must be a first-class page opened from `Maker 接入`, not a CLI/backstage strip; tool reconnect must clear stale `maker_mcp` ToolRegistry entries and Executor handlers before re-registering remote tools.
2026-06-24: Fixed Maker BrowserView light-mode washout. Important lesson: light mode must preserve the official Maker page colors; only dark mode may normalize near-white surfaces, and light mode should restore TTMEvolve-marked inline styles instead of forcing Maker backgrounds to app shell colors.
2026-06-24: Fixed GUI Maker init non-interactive failure. Important lesson: `npx -y @taptap/maker init` can fail in GUI/non-interactive mode unless an app selection is passed; TTMEvolve should default initialization to `app_selection="0"` / create-new-project and execute `maker init 0`, while keeping stdin input only as fallback.
2026-06-24: Localized Maker Access Center visible text. Important lesson: primary GUI surfaces must not expose raw backend enums or CLI English logs; translate readiness, next actions, log kinds, and common Maker CLI messages in the frontend, and keep backend recommended actions/user-facing runner logs in Chinese.
2026-06-24: Added Maker Access failure-prevention gate. Important lesson: setup UI should distinguish blockers from degradation; project directory/init/auth are hard gates, while missing remote creative proxy tools should show as capability degradation with feature-gating instead of making the whole Maker workflow look failed.
2026-06-26: Ran full repository validation after v1.5 cleanup and fixed cross-stack regressions. Important lesson: `pytest` should be scoped away from runtime state, AppServer should only force portable env for app-root configs, Maker-first guard must be task-intent scoped, Tauri bundles must not include live `portable/home/cache/tmp`, and Rust/Cargo must be part of the release gate alongside frontend/Electron builds.
2026-06-26: Fixed the GitHub-facing README after the v1.5.1 push. Important lesson: release sync is not complete until README/GitHub landing content matches the current architecture, launch path, validation evidence, and removed legacy scripts.
2026-06-26: Corrected README language strategy after user feedback. Important lesson: GitHub landing content for TTMEvolve should be Chinese/English bilingual, not English-only, because the primary user base is Chinese while GitHub readers may be international.
2026-06-26: Fixed Tauri GUI startup from source after user reported the frontend could not open. Important lesson: Tauri must own `frontend/dist`; Vite must not build only into Electron's renderer directory, Tauri beforeDev/beforeBuild commands must target `frontend/` directly, and `start-tauri` must run Cargo/Tauri from source instead of falling back to backend-only Python when no binary exists.
2026-06-26: Hardened desktop startup UX after user requested a real ready state. Important lesson: Tauri and frontend must agree on App Server port 7345; the GUI should keep a startup gate until config/health/Maker setup/MCP checks return, auto-open Maker Access when Maker authority is not ready, expose per-session permission profile at message send time, and explain that Tauri preview uses WebView2 rather than Electron BrowserView.
2026-06-26: Tightened the GitHub-facing README into an explicit English/Chinese paired layout after user clarified GitHub README should be bilingual. Important lesson: local UTF-8 content can look garbled in Windows terminal output, so verify bytes/API content before assuming the file itself is corrupt; GitHub landing pages should make bilingual structure obvious, not merely sprinkle translations inline.
2026-06-26: Fixed the Tauri usability regression reported from screenshot: native window controls disappeared because `decorations` was disabled, and Maker preview showed a refused iframe because TapTap Maker blocks embedding. Important lesson: Tauri/WebView2 is not Electron BrowserView; blocked third-party pages need explicit external-open flow plus diagnostic preview, and desktop builds should keep native window decorations unless custom controls are fully implemented.
2026-06-26: Refined the Tauri desktop UX to the user's actual product bar: users should see one coherent desktop app, not cmd windows, debug warnings, or web-embedding explanations. Important lesson: when screenshot/diagnostic fallback can show the page, hide the implementation detail; GUI launchers must detach from cmd and prefer no-console release binaries; custom frameless titlebars must include working window controls and blend into the app theme.
2026-06-26: Replaced the Tauri Maker preview screenshot fallback with a real Tauri child WebView2 surface. Important lesson: normal users need a live clickable embedded browser, while Playwright/browser_service remains a separate Agent automation layer; do not make screenshot polling or iframe/refusal explanations the primary desktop preview.
2026-06-26: Rebalanced cockpit status placement after user feedback. Important lesson: project/model/config are current-context data and belong at the upper-left of the chat surface; Maker MCP is global runtime status and belongs in the top bar; token and latency are per-answer evidence and should render below assistant replies.

2026-06-26: Added MakerMCP automatic update detection and real MCP probe evidence. Important lesson: setup/status must not treat cached integration state as proof; use cached npm latest checks for routine polling, but expose a fresh stdio initialize/tools-list probe via `/mcp/status?probe=true` and `/mcp/probe` for real detection.

2026-06-26: Unified desktop shell visual rhythm after screenshot review. Important lesson: TTMEvolve should use a single desktop design system for titlebar/topbar/chat/input/preview chrome: 32px titlebar, 44px topbar, 34-36px controls, 8/10px panel radii, shared teal/neutral tokens, and no mismatched card-like strips.

2026-06-26: Hid internal tool-candidate chatter and made history/project status user-grade after screenshot feedback. Important lesson: normal users should see dismissible surfaces and task progress, not ranking/debug internals; "查看项目状态/了解项目" needs a first-class read-only `project_status` tool instead of hoping generic shell access is selected.

2026-06-26: Audited the Agent core against the user's "can it really program?" question. Important lesson: prove coding-agent claims with an end-to-end smoke that inspects project state, writes a file, runs a command, records events, and validates layered evidence; do not claim Claude Code/Codex parity until real large-repo benchmarks, GUI task loops, terminal depth, patch review gates, and performance baselines prove it.

2026-06-26: Promoted user document creation to a first-class Agent tool. Important lesson: user-facing OS/document abilities should not be hidden behind generic `modify_file`; expose `create_document` through the same ToolRegistry, Sandbox, Executor, approval, snapshot, and commit-state pipeline so "新建文档" is selectable, testable, and safe.

2026-06-26: Added a performance guard to local file search. Important lesson: a coding Agent that recursively scans `.git`, `node_modules`, `.venv`, runtime logs, or large files will feel broken on real repositories; `search_files` must skip heavy/runtime paths, cap file size, normalize hit paths, and return scan metrics.

2026-06-26: Reviewed Zleap-Agent for Agent-core improvement ideas. Important lesson: the most useful pattern is workspace-first context control, not exposing every tool/memory/history item every turn; TTMEvolve now records a `workspace_profile` in tool-ranking stats as the first step toward profile-scoped tools and memory.

2026-06-26: Turned workspace profile from telemetry into ranking behavior. Important lesson: workspace-first should change the prompt surface, not only label it; docs tasks should see document/read tools first, Maker tasks should see Maker/browser tools first, and coding tasks should see project/read/write/shell/git tools first.

2026-06-26: Passed workspace profile into MemoryManager context budgeting. Important lesson: RAG/vector-memory optimization needs a routing signal before retrieval can be safely narrowed; emit `workspace_profile` through context text and `context_budget` stats first, then use it to filter vector memory in later work.

2026-06-26: Polished the normal-user desktop UI after screenshot review. Important lesson: the main chat must translate tool activity into user intent such as `查看项目状态` or `执行系统命令`, never expose candidate/ranking internals; history must be an obvious dismissible popover with a clear close action; primary settings labels should be Chinese-first; and basic project/cmd work needs tests proving `project_status` and `execute_shell` stay selectable for ordinary "查看项目状态/了解项目/运行 cmd" requests.

2026-06-26: Added long-task continuation checkpoints to context_sync. Important lesson: do not claim full hot resume unless process resurrection is proven; instead expose a durable handoff checkpoint with workspace profile, open plan steps, goal focus, last tool/result, artifact refs, deterministic compression summary, and explicit resume limits through the existing context-sync pull API.

2026-06-26: Promoted continuation checkpoints into Evidence and Onboarding bundles. Important lesson: a handoff feature is not operational until the default external-agent entry points expose it directly; Evidence JSON/Markdown and Onboarding JSON/Markdown now include `continuation`, and `TrajectoryCollector.append()` recreates its storage directory so the Learning layer does not strand running sessions when temp/storage directories drift.
## 2026-06-26 UI/Internal Tool Wording + Shell Route POST

- User complained that history close behavior, English/internal labels, visible candidate tools, and basic project/cmd capabilities still felt wrong.
- Confirmed history popover already supports explicit close, Esc, and outside click; tightened the adjacent Workbench diagnostics so visible labels use Chinese product language instead of raw candidate(s) / Runtime / Retry / Loading wording where normal users can see it.
- Main chat already maps candidate/tool-selection events to action language such as 正在判断下一步; added Workbench-side userFacingWorkbenchStatus() for the same boundary.
- Strengthened ToolRegistry.rank_tools() so project/cmd/terminal/Git-status wording keeps project_status and execute_shell selected ahead of Maker-only tools.
- README remains bilingual and now documents advanced evidence hiding plus shell-command routing.
- Verification:
pm.cmd --prefix frontend run build passed; focused tool-routing pytest for project status and cmd requests passed (3 passed).
## 2026-06-26 Workspace Profile RAG Filtering POST

- Implemented profile-aware cold memory/RAG retrieval. ColdMemory.index() now persists workspace_profile metadata, and ColdMemory.search() first filters vector and keyword recall to the active profile plus general.
- Added safe fallback: if a non-general profile search returns no hits, recall retries globally so the agent does not lose all useful memory because of overly strict routing.
- MemoryManager.prepare_think_payload() now passes its normalized profile into recall(), and archive_session() can persist profile metadata for future session summaries.
- Added focused tests for profile filtering, general-memory inclusion, global fallback, keyword fallback behavior, and prompt injection behavior.
- Architecture audit updated: the previous next step Use workspace_profile to filter vector memory retrieval is now implemented; next work should move to per-profile retrieval policy and multi-agent shared-memory policy surfaces.
## 2026-06-26 Per-Profile RAG Policy POST

- Added configurable cold-memory profile policies under memory.vector_index.profile_policies. Each profile can now control top_k, include_general, and allow_fallback without changing call sites.
- Defaults preserve the previous safe behavior: non-general profiles include general memory and can globally fallback when narrowed recall has no hits; general has no extra global fallback.
- MemoryManager now asks ColdMemory.profile_policy() for the effective recall size, so docs/maker/coding can use different recall budgets.
- Added tests for excluding general memory, disabling global fallback, top_k overrides, and Manager-level policy use in prepare_think_payload().
- Architecture next step moves from per-profile retrieval policy to multi-agent shared-memory policy surfaces and profile evidence visibility.
## 2026-06-26 Shared Memory Policy Surface POST

- Added memory/shared_policy.py with SharedMemoryPolicy, a conservative multi-agent memory policy surface.
- Cold memory entries now persist agent_id and visibility metadata. Default visibility is private, so existing single-agent behavior remains safe while multi-agent sharing must be explicit.
- ColdMemory.search() can now filter by agent_id and shared-memory policy: agents can read their own private memory, shared/public memory according to policy, and cannot read another agent's private records by default.
- ColdMemory.index() enforces write-profile gates when configured, preventing a specialized agent from writing outside its allowed workspace profiles.
- MemoryManager.archive_session() and recall() accept agent_id / visibility metadata so session summaries can participate in the same policy.
- Added focused tests for private/shared/public visibility, disabled shared reads, write-profile rejection, and Manager archive/recall metadata.
- This is a policy foundation, not a full multi-agent collaboration runtime yet; next work should expose policy evidence in Evidence Bundle/Workbench and add promotion/demotion rules based on verified task outcomes.
## 2026-06-26 Shared Memory Evidence Surface POST

- Added a compact shared-memory policy summary to the session Evidence Bundle under shared_memory.
- Evidence Markdown now renders a ## Shared Memory section with agent id, boundary, default visibility, readable profile sets, and whether another agent's private memory is readable.
- LLM Onboarding Bundle now includes the same shared_memory object and a shared_memory_policy closure-gate check, so external agents can inspect memory-sharing boundaries before reusing memory.
- The summary is intentionally non-secret: it exposes policy shape and counts, not raw memory contents or private records.
- Added endpoint-level assertions to test_app_server_evidence_bundle_endpoint covering Evidence JSON, Evidence Markdown, Onboarding JSON, and closure gate.
## 2026-06-26 Desktop UX And Tool Routing Evidence POST

- Treat screenshots as historical clues only; current truth must come from code, tests, builds, and live runtime evidence.
- Tightened the history popover affordance with an explicit icon close control, while preserving Esc and outside-click dismissal.
- Replaced visible Workbench English/status labels with Chinese product-facing labels and removed candidate-count wording from normal runtime summaries.
- Expanded chat event filtering so candidate/tool-selection/ranking wording is translated to user intent instead of leaking internal tool names or ranking internals.
- Added a regression test proving basic project/cmd work keeps project_status and execute_shell ahead of Maker tools even when many Maker remote tools are registered.
## 2026-06-26 Runtime Event Bus Foundation POST

- Added RuntimeEventBus in core/runtime_events.py as a shared in-process communication primitive for session/feedback/layer event channels.
- The bus preserves the existing event dictionary shape, adds the shared RuntimeEvent envelope, supports filtered subscriptions by event type/channel/session, bounded replay, unsubscribe, stats, and observer exception isolation.
- AppServer sessions now publish through a shared AppServer.event_bus before writing SQLite/SSE queues, so future runtime metrics, learning, and project-management components can subscribe without direct coupling to Session internals.
- Added focused tests for bus filtering/replay/history bounds/error isolation and for Session/AppServer bus integration.
- This is a decoupling foundation, not a claim that every producer/consumer has been migrated to the bus yet.
## 2026-06-26 Agent Event Bus Migration POST

- TapMakerAgent now owns a RuntimeEventBus and records ReActLoop events through the bus before appending to the existing per-session compatibility queue.
- Layer events now use the same _record_event path, so Agent/Core Runtime/Learning transition events are replayable through agent.event_bus without direct queue access.
- Existing get_events() and AppServer event_sink behavior remain compatible, but future observers can subscribe to the bus instead of coupling to _event_queues.
- Added tests proving ReAct status/output and layer events appear on the Agent bus, preserving event order and envelope metadata.
- This continues the event-bus migration; AppServer still receives session events through event_sink to avoid double-publishing during this incremental step.

## 2026-06-26 Runtime Event Bus Evidence Surface POST

- Exposed compact Runtime Event Bus status in Runtime Readiness, Session Evidence JSON/Markdown, and LLM Onboarding JSON/Markdown.
- Evidence includes server bus stats, Agent bus stats, session-scoped event counts, layer-event counts, and the compatibility flag `sse_sqlite_shape_preserved`.
- Added release/closure gate checks so external agents can verify the bus surface before depending on decoupled observers.
- Cleaned the main chat/history/input surfaces to use Chinese/English visible labels and keep candidate-tool ranking out of the user conversation; internal routing still remains available in Workbench/debug evidence.
- Verified focused readiness/evidence endpoint tests and the frontend production build.

## 2026-06-26 Runtime Metrics Observer POST

- Added `server/runtime_observer.py` as the first real Runtime Event Bus subscriber for project/runtime observability.
- RuntimeMetricsObserver subscribes to session-channel events, derives compact `context_budget`, `tool_selection`, `latency`, and `llm_usage` metrics, and keeps session-scoped live histories without reading private queues.
- `/sessions/{id}/runtime-metrics` now prefers the bus observer when live metrics exist, while returning store counts and observer counts so fallback behavior is explicit.
- Runtime Readiness and Evidence now expose `runtime_metrics_source`, `runtime_metrics_observer`, and observer stats under `runtime_event_bus`.
- Verified focused bus observer and AppServer endpoint tests; this moves the bus from passive evidence to an actual consumer path.

## 2026-06-26 Project Management Observer POST

- Added `server/project_observer.py` as a Runtime Event Bus subscriber for engineering-control/project-management state.
- The observer derives next action, next focus, goal status/counts, plan verdict, latest tool, continuation readiness, artifacts, and risk flags from public bus events, especially `context_sync`.
- Added `/sessions/{id}/project-state` and exposed `project_state` in Runtime Readiness, Session Evidence JSON/Markdown, and LLM Onboarding JSON/Markdown.
- Runtime Contract now includes the project-state endpoint in both communication surfaces and external-agent attach sequence.
- Verified unit and AppServer tests for bus-derived project state plus Evidence/Runtime Contract assertions.

## 2026-06-26 Chinese-First Desktop UI Polish POST

- User reported five concrete desktop UX issues: history close was not obvious enough, visible English remained, candidate tools leaked into normal chat, project/cmd ability looked unavailable, and the UI still lacked cohesive product polish.
- Applied the product rule learned from current UI references: normal workflow uses progressive disclosure; debug/ranking evidence remains in Workbench, while the main chat shows only user-facing task progress.
- Updated ChatPanel, ChatInput, ChatMessage, CockpitHeader, App Maker version detail, and the final CSS polish layer so primary desktop surfaces are Chinese-first, history is a compact dismissible popover, topbar height/radius is consistent, and candidate/tool-selection events are filtered out of the main conversation.
- Confirmed `project_status` and `execute_shell` routing remains available for "查看项目状态 / 了解项目 / cmd / git status" requests through focused ToolRegistry regression tests.
- README remains bilingual for GitHub, but the app's normal user-facing surface is now Chinese-first with Workbench retaining technical diagnostics.
- Verification: `npm.cmd --prefix frontend run build` passed; focused project-status/cmd ToolRegistry pytest passed (`4 passed`); `git diff --check` passed.

## 2026-06-26 Vector Index Fast Path POST

- Continued the long-term RAG/vector-memory performance objective with a narrow but real hot-path fix in `memory/vector_index.py`.
- `VectorIndex.search()` previously resolved each FAISS result id by scanning `self._id_map.items()`, making vector result materialization O(k*n) for k returned ids and n indexed chunks.
- Added `_reverse_id_map: Dict[int, str]` and maintain it across add, delete, clear, rebuild, and load, so FAISS internal ids resolve to chunk ids in O(1).
- Fixed batch internal-id allocation at the same boundary: ids are now allocated as a unique sequence for each add batch instead of repeatedly sampling the same microsecond timestamp.
- Added tests for reverse-map maintenance, unique batch ids, and a fake FAISS search path that fails if search tries to linearly scan `_id_map.items()`.
- Verification: `.venv\Scripts\python.exe -m pytest tests\test_vector_index.py tests\test_cold_memory_vector.py tests\test_memory_manager_recall.py -q` -> `18 passed, 2 skipped`. Skips are FAISS-availability guarded; the fast-path logic is still covered with a fake index.

## 2026-06-26 History Close + Foundation Tool Pinning POST

- User reported five remaining product issues: history close was unclear, some visible wording still felt wrong, candidate tools should not be visible, project/cmd work appeared unavailable, and desktop UI/product thinking needed stronger grounding.
- Applied the design/product rule from current UI references: command bars/toolbar controls should be grouped around user actions, and advanced/internal details should use progressive disclosure. In TTMEvolve this means normal chat shows task progress, while candidate/ranking diagnostics stay in Workbench/evidence.
- Tightened history affordance: the toolbar trigger changes to `关闭历史` while open, the popover explains close/Esc/outside-click, and the close icon has consistent radius/transition styling.
- Preserved technical units after user correction: usage chips keep `Token` and `tok/s` because they are units, not prose labels.
- Added foundation tool pinning in `ToolRegistry`: project-state and shell/cmd/git-status intent pins `project_status` and `execute_shell` ahead of Maker-only tools, even when Maker context is present.
- Verification: `npm.cmd --prefix frontend run build` passed; focused ToolRegistry pytest for project/cmd routing and safe operation wording passed (`6 passed`).

## 2026-06-26 Maker Dynamic Tool Execution POST

- User screenshot showed the GUI stuck in repeated `maker_status_lite` failures: `MCPIntegration._maker_handler() missing 1 required positional argument: 'tool_name'`, followed by rescue telemetry and a secondary string/float comparison error.
- Root cause: `Executor._execute()` only passed `tool_name` for the fixed creative proxy set, but real Maker tools discovered from `tools/list` are also registered through `register_maker_tool()` and share the same Maker handler signature.
- Fixed the execution boundary so every registered Maker tool in `_maker_tool_names` receives `handler(tool_name, **params)`.
- Hardened `RescueOrchestrator` numeric config/state handling so malformed rescue values cannot create a second failure while reporting or skipping rescue.
- Regression: fake MCP now exposes `maker_status_lite`, and diagnostics tests execute it through `agent.executor.propose_action()` to match the GUI path.
- Verification: `.venv\Scripts\python.exe -m pytest tests/test_mcp_diagnostics.py tests/test_rescue_loop.py -q` -> `12 passed`; `.venv\Scripts\python.exe -m pytest tests/test_tool_timeouts.py -q` -> `5 passed`; `npm.cmd --prefix frontend run build` passed.

## 2026-06-26 Memory Boundary Correction POST

- User identified a core documentation problem: Codex/嗒啦啦 memory and TTMEvolve project memory had been blended together, creating a false story that TTMEvolve and the assistant were mutually developing each other.
- Corrected the ownership model in core entry docs: 灰語 directs, Codex/嗒啦啦 implements, and TTMEvolve is the application/product under development.
- Rewrote `docs/persona.md` as product persona documentation for the in-app TTMEvolve Agent, not assistant private memory.
- Added explicit memory/ownership boundary headers to `AGENTS.md`, `docs/memory-index.md`, `docs/memory-health.md`, and `docs/sprint-board.md`.
- Rule going forward: project POST notes record neutral product facts and verification; assistant/private self-memory must not be mixed into TTMEvolve runtime/product memory.
# Memory Boundary

- This file records TTMEvolve project memory health and delivery POST notes.
- It is not Codex private self-memory.
- TTMEvolve is the product being developed; Codex/嗒啦啦 is the developer assistant doing repository work under 灰語's direction.
- Runtime memory, learning, shared-memory policy, and persona files are TTMEvolve product surfaces. Keep them separate from assistant memory.
- Future entries should record product facts and verification, not imply mutual development between TTMEvolve and the assistant.

## 2026-06-27 03:33 Project Writeback Plan POST

- Status: verified.
- Added a guarded project writeback loop from `project_control.memory_updates_due` to append-only POST document updates.
- Safety controls: explicit `apply=true` required, allowed POST doc list, root-contained path validation, path traversal rejection, per-session idempotency marker, and dry-run default.
- Evidence surfaces now show `project_writeback` in Session Evidence, LLM Onboarding, Runtime Contract endpoint maps, and Workbench Project Control.
- Workbench displays the writeback plan and target files without offering an apply button, preserving human-visible control over memory writes.
- Verified: focused backend suite (`16 passed`), `npm.cmd --prefix frontend run build`, and `git diff --check` with existing CRLF warnings only.
- Next: continue structural AppServer route/session decoupling and shared-memory promotion/demotion rules.

## 2026-06-27 03:55 AppServer Session API Extraction POST

- Status: verified.
- Added `server/session_api.py` to own reusable session-route payload construction and bounded `steps`/`limit` parsing.
- Fixed structural coupling by moving session route response assembly for status/history/context/runtime/project/writeback/learning/guard/probe/evidence/advice out of `server/app_server.py`.
- Preserved public endpoint behavior: AppServer still owns route matching, existence checks, Markdown vs JSON response choice, and HTTP status codes.
- Verified: focused session/API endpoint suite (`6 passed`), broader AppServer/runtime-contract/project-control/writeback suite (`39 passed`), `npm.cmd --prefix frontend run build`, and `git diff --check` with existing LF/CRLF warnings only.
- Next: continue Phase 1 decoupling with remaining AppServer route groups or the `agent/react_loop.py` phase split; keep shared-memory promotion/demotion and layer-health queues as next architecture gates.

## 2026-06-27 04:05 Agent Maker Guard Phase Extraction POST

- Status: verified.
- Added `agent/maker_guard.py` to own Maker authority first-action decisions as pure, directly testable logic.
- Fixed structural coupling by removing Maker guard rule methods from `agent/react_loop.py`; `ReActLoop` now delegates guard decision, guard observation, and guard context-hint generation to the extracted module.
- Preserved runtime behavior: existing ReAct event emission, Maker guard block path, plan validation, context sync, and goal checklist flow remain in `ReActLoop`.
- Verified: focused Maker guard/ReAct block suite (`9 passed`), adjacent ReAct/runtime-contract suite (`50 passed`), plan/goal suite (`11 passed`), and `git diff --check` with existing LF/CRLF warnings only.
- Next: continue Agent-layer phase split by extracting action validation/execution result handling or context sync/checkpoint builders; keep truthfulness claims tied to tests and runtime evidence.

## 2026-06-27 04:23 Agent Action Execution Phase Extraction POST

- Status: verified.
- Added `agent/action_execution.py` to own ReAct action validation/execution as a runtime boundary service.
- Fixed structural coupling by moving progress heartbeat emission, executor dispatch, direct tool-call validation, commit reconciliation, validation failure payloads, and timeout context hints out of `agent/react_loop.py`.
- Preserved runtime behavior: `ReActLoop` still owns planning, event ordering, trajectory writes, plan validation, goal checklist, and context sync.
- Verified: focused action execution/ReAct suite (`10 passed`), adjacent Agent/runtime suite (`65 passed`), `npm.cmd --prefix frontend run build`, and `git diff --check` with existing LF/CRLF warnings only.
- Next: continue Agent-layer phase split with context sync/checkpoint builders, then move to shared-memory promotion/demotion and layer-health queue gates.

## 2026-06-27 04:40 Agent Context Sync Phase Extraction POST

- Status: verified.
- Added `agent/context_sync.py` to own ReAct context-sync snapshot, continuation checkpoint, signature, diff, open-plan, artifact, and commit-state builders as pure directly testable logic.
- Fixed structural coupling by removing context handoff/checkpoint helper methods from `agent/react_loop.py`; `ReActLoop` now delegates snapshot construction and only emits the existing `context_sync` event payload.
- Preserved runtime behavior: context-sync signature stability, deduplication, checkpoint payload shape, artifact refs, compression summary, and AppServer context-sync/evidence endpoint behavior remain covered by tests.
- Size evidence: `agent/react_loop.py` is now `857` lines after this extraction; `agent/context_sync.py` is `277` lines.
- Verified: focused context-sync builder/ReAct suite (`7 passed`), adjacent context/runtime/evidence suite (`49 passed`), `npm.cmd --prefix frontend run build`, and `git diff --check` with existing LF/CRLF warnings only.
- Boundary: this is durable context-handoff extraction, not proof of hot process resurrection. Restart/resume drills remain required before stronger long-task resume claims.
- Next: add shared-memory promotion/demotion rules with verified outcome evidence, then continue remaining ReAct planning or AppServer route dispatch splits.

## 2026-06-27 05:13 Shared Memory Outcome Rules POST

- Status: verified.
- Added `memory/shared_outcome.py` as the shared-memory promotion, demotion, and conflict-rule engine.
- Added `ColdMemory.record_shared_outcome()` plus a persisted `shared_memory_conflicts.json` ledger for unresolved claim conflicts.
- Safety rule: memory remains private by default; promotion to shared requires verified positive task evidence, `task_success=true`, evidence references, and no unresolved same-claim conflict.
- Demotion rule: stale evidence, regression/contradiction evidence, or repeated misleading evidence moves records back to private and records the reason in `shared_memory` metadata.
- Evidence surfaces now expose shared-memory outcome rules and unresolved conflict counts through Session Evidence JSON/Markdown.
- RAG speed improvement: `VectorIndex.search()` now tries vector results first and only scans keyword fallback when vector results cannot fill the request, removing the normal 10k-record O(n) keyword scan from warm recall.
- Verified: focused shared-memory/evidence suite (`10 passed`), vector/RAG suite (`19 passed`), adjacent memory/RAG/evidence suite (`30 passed`), `npm.cmd --prefix frontend run build`, and `git diff --check` with existing LF/CRLF warnings only.
- Boundary: this proves deterministic local policy behavior and fake-FAISS pipeline speed. Production embedding quality and real multi-agent handoff behavior remain separate gates.
- Next: connect outcome recording to learning worker validation and add two-agent handoff simulation.

## 2026-06-27 05:31 Learning Shared-Memory Bridge POST

- Status: verified.
- Added `learning/shared_memory_bridge.py` as the learning-to-cold-memory bridge for validated reflection insights.
- Fixed the learning worker path so `TapMakerAgent._learn_from_session()` returns insight and shared-memory summaries, stores them on the learning job, and emits shared-memory archive/promote/conflict metrics through the learning layer event.
- Safety rule: learning insights are archived as private `learning_insight` records first; only shareable high-confidence insights with verified positive task evidence call `ColdMemory.record_shared_outcome()`.
- Added deterministic bridge tests for private-first archiving, verified promotion, unverified/private isolation, two-agent shared handoff, same-claim conflict blocking, and agent learning-session integration.
- Verified: bridge/shared-memory suite (`13 passed`), adjacent memory/RAG/evidence/runtime suite (`30 passed`), vector/cold-memory/bridge suite (`21 passed`), `npm.cmd --prefix frontend run build`, and `git diff --check` with LF/CRLF warnings only.
- Boundary: this proves the local learning-validation to shared-memory policy bridge and deterministic two-agent simulation. It is not yet a real multi-process agent collaboration runtime or a production embedding-quality benchmark.
- Next: define fuller layer-health snapshots and learning worker queue gates, then continue ReAct planning/AppServer route decoupling or begin resume-drill work.

## 2026-06-27 05:52 Layer Health Snapshot POST

- Status: verified.
- Added `server/layer_health.py` as the compact Agent/Core Runtime/Learning health snapshot builder.
- Added `GET /sessions/{id}/layer-health?steps=N` through `server/session_api.py` and `server/app_server.py`.
- Evidence Bundle, Runtime Readiness, LLM Onboarding, Markdown evidence, and Runtime Contract now expose `layer_health` with per-layer health/state/event/route/latency/error, learning queue depth, active learning job status, observer error count, and expected communication-route observations.
- Fixed the evidence endpoint regression test to assert the routes actually present in the fixture (`user->agent`, `runtime->learning`, `learning->storage`) instead of pretending `agent->runtime` was observed.
- Verified: focused layer-health/runtime-contract/evidence suite (`12 passed`), adjacent readiness/evidence/layer/session API suite (`14 passed`), `npm.cmd --prefix frontend run build`, and `git diff --check` with existing LF/CRLF warnings only.
- Boundary: this is a compact local evidence snapshot and queue-depth surface. It is not yet a full managed learning-worker scheduler, cancellation/retry system, or hot process resurrection proof.
- Next: add corrective thresholds/actions for layer latency, failed routes, learning queue backlog, and runtime failure states.

## 2026-06-27 06:06 Layer Control Thresholds POST

- Status: verified.
- Added `server/layer_control.py` as a pure engineering-control builder over `layer_health`.
- Added `GET /sessions/{id}/layer-control?steps=N` through `server/session_api.py` and `server/app_server.py`.
- Runtime Contract, Runtime Readiness, Session Evidence JSON/Markdown, LLM Onboarding JSON/Markdown, and compact endpoint lists now expose `layer_control`.
- Control statuses are `ready`, `watch`, `needs_action`, and `blocked`; watch-level missing route or active learning queue allows progress with monitoring, while failed layers, severe latency, or observer-error thresholds block completion claims.
- Verified: direct layer-control tests (`4 passed`), focused layer-control/layer-health/runtime-contract/evidence suite (`16 passed`), adjacent readiness/evidence/layer/session API suite (`14 passed`), `npm.cmd --prefix frontend run build`, and `git diff --check` with existing LF/CRLF warnings only.
- Boundary: this adds thresholds and corrective-action evidence, not automatic remediation, managed learning-worker cancellation/retry, or restart-resume proof.
- Next: connect layer-control corrective actions to project-control/workbench review and add thresholds for memory misses, repeated tool failures, and plan-gate failures.

## 2026-06-27 06:20 Layer Control Project Surface POST

- Status: verified.
- Project Control now accepts `layer_control` evidence and exposes compact `layer_control` plus `control_actions` fields.
- `/sessions/{id}/project-state` now includes layer-control-derived project-control evidence.
- Session Evidence project-state/project-control data now carries the top layer-control corrective action, so Workbench can show project management and engineering-control state together.
- Agent Workbench Project Control card now displays layer-control status, decision, signal count, claim gate, and the highest-priority corrective action inside the existing project-control card.
- Verified: project-control/layer-control/AppServer focused suite (`8 passed`), adjacent session/runtime-contract/readiness/evidence suite (`13 passed`), `npm.cmd --prefix frontend run build`, and `git diff --check` with existing LF/CRLF warnings only.
- Boundary: this is project-management visibility and review guidance. It still does not automatically execute layer-control remediation or cancel/retry learning jobs.
- Next: add control gates for memory misses, repeated tool failures, and failed plan gates; then consider guarded apply/review UX for corrective actions.

## 2026-06-27 06:44 Engineering Control Runtime Gates POST

- Status: verified.
- Added `server/engineering_control.py` as a pure control builder for memory/RAG misses, repeated tool failures, same-tool retry loops, failed plan gates, and memory recall latency.
- Added `GET /sessions/{id}/engineering-control?steps=N` through `server/session_api.py` and `server/app_server.py`.
- Runtime Contract, Runtime Readiness, Session Evidence JSON/Markdown, LLM Onboarding JSON/Markdown, Quickstart endpoint lists, and Workbench Project Control now expose `engineering_control`.
- Project Control now includes compact `engineering_control` summaries and merges engineering-control corrective actions with layer-control actions for project-management visibility.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_engineering_control.py tests\test_project_control.py tests\test_runtime_contract.py -q` -> `15 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_runtime_readiness_endpoint tests\test_app_server_resume.py::test_app_server_project_state_endpoint_uses_bus_observer tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `3 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_session_api.py tests\test_layer_control.py tests\test_layer_health.py tests\test_runtime_events.py -q` -> `18 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_external_llm_quickstart_endpoint tests\test_app_server_resume.py::test_app_server_external_agent_handoff_endpoint tests\test_app_server_resume.py::test_app_server_runtime_advice_endpoint_prioritizes_blocked_maker_guard tests\test_app_server_resume.py::test_app_server_context_sync_endpoint tests\test_app_server_resume.py::test_app_server_runtime_metrics_endpoint -q` -> `5 passed`.
  - `.venv\Scripts\python.exe -m py_compile server\engineering_control.py server\project_control.py server\evidence_bundle.py server\session_api.py server\app_server.py core\runtime_contract.py` -> passed.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: this adds evidence, thresholds, closure gates, and corrective actions. It does not automatically remediate memory indexes, change tool parameters, or rewrite failed plans.
- Next: add guarded corrective-action review/apply flows only after the evidence remains stable, then continue managed learning-worker queue policy or restart/resume drills.

## 2026-06-27 07:13 Durable Resume Drill POST

- Status: verified.
- Added `server/resume_drill.py` as a pure durable long-task resume drill builder over persisted `SessionStore` evidence.
- Added `GET /sessions/{id}/resume-drill?steps=N` through `server/session_api.py` and `server/app_server.py`.
- Evidence Bundle, Runtime Readiness, LLM Onboarding JSON/Markdown, Quickstart endpoint lists, Runtime Contract, and Workbench external-agent boot summaries now expose `resume_drill`.
- Truthfulness gate: long-task durable handoff can be claimed only when the drill recovers task, open plan, latest result, artifact refs, and next action from persisted context evidence. Warm process resume and hot in-process tool-call resurrection remain `unproven`.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile server\resume_drill.py server\evidence_bundle.py server\session_api.py server\app_server.py core\runtime_contract.py` -> passed.
  - `.venv\Scripts\python.exe -m pytest tests\test_resume_drill.py tests\test_runtime_contract.py -q` -> `10 passed`.
  - AppServer context/readiness/evidence/quickstart/handoff focused suite -> `5 passed`.
  - Session API/resume/runtime/project/engineering focused suite -> `19 passed`.
  - Full `tests\test_app_server_resume.py` -> `25 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` passed with existing LF/CRLF warnings only.
- Boundary: this is a store-replay durable handoff drill, not a process restart runner, warm process continuation mechanism, or hot tool-call resurrection proof.
- Next: add managed learning-worker cancellation/retry policy or continue remaining ReAct planning/trajectory extraction.

## 2026-06-27 07:48 Managed Learning Job Queue POST

- Status: verified.
- Added `agent/learning_queue.py` as the managed learning job queue for scheduling, cooperative cancellation state, retry policy, worker idle behavior, and public job snapshots.
- Refactored `TapMakerAgent` learning dispatch to delegate queue state to `LearningJobQueue`; removed the old private `_learning_jobs` dict/thread path from `agent/agent.py`.
- Added learning control methods and HTTP routes: `POST /sessions/{id}/learning/cancel` and `POST /sessions/{id}/learning/retry`. These operate only when a live session-scoped agent queue is attached; durable replay returns an explicit 409 boundary instead of pretending historical events can be cancelled.
- Expanded `/sessions/{id}/learning?steps=N`, `learning_job_from_server()`, `layer_health`, Runtime Contract, Evidence/Onboarding endpoint lists, and tests with managed job fields: `policy`, `attempts`, `max_attempts`, `retryable`, and `cancel_requested`.
- Truthfulness rule: learning failure no longer has to fail the user task, but the learning job itself must surface `error`/`failed` and retry policy evidence instead of being reported as successful.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile agent\learning_queue.py agent\agent.py server\evidence_bundle.py server\session_api.py server\app_server.py server\layer_health.py core\runtime_contract.py` -> passed.
  - `.venv\Scripts\python.exe -m pytest tests\test_learning_job_queue.py -q` -> `3 passed`.
  - Focused layer/runtime-contract suite -> `23 passed`.
  - Focused AppServer/session/project/control suite -> `13 passed`.
  - Combined AppServer/layer/runtime suite -> `48 passed`, `1` timeout in `test_app_server_evidence_bundle_endpoint` while reading `/memory/rag-benchmark?force=true` under long-suite load.
  - Rerun `tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint` -> `1 passed`; `tests\test_rag_performance.py` -> `2 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: this verifies a managed queue and control policy inside each live `TapMakerAgent`. It is not yet a global multi-process learning scheduler, a GUI control surface, or a production learning throughput benchmark.
- Next: add project-control/Workbench review controls for learning cancel/retry, or continue remaining `agent/react_loop.py` planning/trajectory extraction.

## 2026-06-27 08:06 Workbench Learning Control Review POST

- Status: verified.
- Added Workbench learning job preview fields for `job` and `policy`, including attempts, retryability, cancellation marker, shared-memory counts, policy mode/source, and durable replay source.
- Added compact learning control UI in the existing Workbench learning card: `Cancel` appears only for live queued/running jobs, `Retry` appears only for live failed/cancelled retryable jobs, and durable replay/history-only jobs show an explicit unavailable boundary instead of offering fake controls.
- Wired the UI to `POST /sessions/{id}/learning/cancel` and `POST /sessions/{id}/learning/retry`, then refreshes `/sessions/{id}/learning` plus the Evidence Bundle after each control attempt.
- Evidence Bundle auto-refresh now can derive learning job status from `learning_job` when present or `layer_health.layers.learning` fallback, while `/sessions/{id}/learning` remains the authoritative job/policy detail endpoint.
- Verification:
  - `npm.cmd --prefix frontend run build` -> passed.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_learning_control_uses_live_agent_or_reports_replay_boundary tests\test_runtime_contract.py::test_runtime_contract_summarizes_maker_and_communication_surfaces -q` -> `2 passed`.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: this verifies frontend type/JSX integration and backend control contract. It is not a visual GUI smoke run, global learning scheduler, or production learning throughput benchmark.
- Next: either continue remaining `agent/react_loop.py` planning/trajectory extraction, add production embedding quality benchmarks, or add a real GUI smoke pass for the Workbench learning controls.

## 2026-06-27 08:21 Plan First Phase Extraction POST

- Status: verified.
- Added: `agent/plan_first.py` now owns Plan First drafting, known-tool discovery, deterministic review, approval-provider handling, parse-failure event emission, approval-error event emission, and no-approval result shape.
- Refactored: `agent/react_loop.py` delegates the Plan First phase to the new module while keeping `_draft_plan_from_llm()`, `_known_tool_names()`, and `_build_plan_first_result()` wrappers for existing integration tests and monkeypatches.
- Preserved: public event names and result contracts remain `plan_first_phase`, `plan_draft`, `plan_approval_error`, `plan_draft_parse_failed`, `plan_progress`, `plan_review`, and `plan_first_phase=not_approved`.
- Measured: `agent/react_loop.py` is `801` lines and `agent/plan_first.py` is `158` lines after the extraction.
- Verification: `py_compile agent\plan_first.py agent\react_loop.py` passed; plan-first focused suite passed (`9 passed`); restored/expanded plan-first and adjacent runtime suite passed (`72 passed`); `npm.cmd --prefix frontend run build` passed; `git diff --check` passed with existing LF/CRLF warnings only.
- Boundary: this extracts the Plan First phase only. It does not complete the whole planning/trajectory runtime split or add automatic plan remediation.
- Next: extract remaining trajectory/result handling from `ReActLoop`, add production embedding-quality benchmarks, or run a GUI smoke pass for Workbench learning controls.

## 2026-06-27 08:34 Trajectory Result Helper Extraction POST

- Status: verified.
- Added: `agent/trajectory_result.py` now owns normal ReAct output-step recording, observation-step recording, latest-output selection, final result building, and compact result summary building.
- Refactored: `agent/react_loop.py` now delegates done-output steps and the three repeated observation paths (Maker guard block, tool preflight validation failure, normal tool observation) to the helper module.
- Preserved: public event order remains output before goal/context sync for done steps, and observation -> plan_validation -> goal_checklist -> skill/context sync for observed action steps.
- Added tests: `tests/test_trajectory_result.py` covers event order, trajectory append semantics, optional plan fields, plan-validation summary, latest-output selection, and compact summary output.
- Measured: `agent/react_loop.py` is `799` lines and `agent/trajectory_result.py` is `108` lines after the extraction.
- Verification: `py_compile agent\trajectory_result.py agent\react_loop.py` passed; focused trajectory/ReAct branch suite passed (`11 passed`); broad adjacent suite passed (`87 passed`); `npm.cmd --prefix frontend run build` passed; `git diff --check` passed with existing LF/CRLF warnings only.
- Boundary: this extracts normal trajectory/result recording only. Expert takeover trajectory handling, rescue-specific paths, and full ReActLoop orchestration split remain pending.
- Next: extract expert-takeover/rescue trajectory handling, add production embedding-quality benchmarks, or run a GUI smoke pass for Workbench learning controls.

## 2026-06-27 08:49 Expert Takeover Runner Extraction POST

- Status: verified.
- Added: `agent/expert_takeover.py` now owns bounded expert loop takeover execution, including expert thought/action events, expert tool-call execution, expert output steps, expert observation steps, failure context append, and `on_step` callback dispatch.
- Refactored: `ReActLoop.takeover()` is now a thin wrapper around `run_expert_takeover()`; the public rescue interface still calls `react.takeover(expert_llm, steps)`.
- Added tests: `tests/test_expert_takeover.py` covers done-output stop behavior, expert event order, tool observation recording, `on_step` callback behavior, and failure context being visible to the next expert thought.
- Measured: `agent/react_loop.py` is `761` lines and `agent/expert_takeover.py` is `94` lines after the extraction.
- Verification: `py_compile agent\expert_takeover.py agent\react_loop.py` passed; expert takeover + rescue loop suite passed (`7 passed`); broad expert/rescue/action/context/runtime suite passed (`69 passed`); `npm.cmd --prefix frontend run build` passed; `git diff --check` passed with existing LF/CRLF warnings only.
- Boundary: loop-takeover behavior is extracted. `RescueOrchestrator._apply_rescue()` still owns direct-action rescue trajectory append and should be split separately before claiming rescue trajectory handling is fully modular.
- Next: extract the rescue direct-action append path, add production embedding-quality benchmarks, or run a GUI smoke pass for Workbench learning controls.

## 2026-06-27 08:57 Rescue Direct-Action Append Extraction POST

- Status: verified.
- Added: `agent/rescue_application.py` now owns the stable direct-action rescue trajectory entry shape.
- Refactored: `RescueOrchestrator._apply_rescue()` now delegates direct-action expert trajectory append to `append_direct_action_rescue_step()` after `react.inject_expert_action()` returns the observation.
- Added tests: `tests/test_rescue_application.py` covers helper step shape, deterministic timestamp behavior, and the orchestrator direct-action path preserving expert action execution plus expert trajectory append.
- Measured: `agent/rescue_orchestrator.py` is `259` lines and `agent/rescue_application.py` is `27` lines after the extraction.
- Verification: `py_compile agent\rescue_application.py agent\rescue_orchestrator.py` passed; rescue application + rescue loop suite passed (`6 passed`); broad expert/rescue/action/context/runtime suite passed (`71 passed`); `npm.cmd --prefix frontend run build` passed; `git diff --check` passed with existing LF/CRLF warnings only.
- Boundary: direct-action trajectory append is extracted. `_apply_rescue()` still owns rescue mode validation/dispatch, and no new rescue telemetry or event shape was added.
- Next: add production embedding-quality benchmark boundaries, split remaining AppServer route groups, or run a GUI smoke pass for Workbench learning controls.

## 2026-06-27 09:11 RAG Embedding Quality Boundary POST

- Status: verified.
- Added structured `embedding_quality` and `closure_gate` fields to `memory/rag_benchmark.py` reports.
- Deterministic `/memory/rag-benchmark` speed evidence now carries `benchmark_scope=deterministic_local_pipeline_speed`; production semantic quality remains `unproven` unless a real embedding model, labelled corpus/golden query set, quality metric, and sample count are present.
- Runtime Readiness, Session Evidence JSON/Markdown, LLM Onboarding JSON/Markdown, Runtime Contract, and Workbench RAG benchmark card now expose the production quality boundary.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile memory\rag_benchmark.py server\evidence_bundle.py core\runtime_contract.py` -> passed.
  - `.venv\Scripts\python.exe -m pytest tests\test_rag_performance.py tests\test_runtime_contract.py -q` -> `12 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `1 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_runtime_readiness_endpoint tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint tests\test_runtime_contract.py tests\test_rag_performance.py -q` -> `14 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_engineering_control.py tests\test_memory_manager.py tests\test_memory_manager_recall.py tests\test_cold_memory_vector.py tests\test_vector_index.py -q` -> `30 passed`.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: this is a truthfulness and evidence boundary. It does not run a production embedding model or prove semantic recall quality yet.
- Next: add a real production embedding quality evaluation runner/golden corpus, split remaining AppServer route groups, or run a GUI smoke pass for Workbench learning controls.

## 2026-06-27 09:35 RAG Quality Evaluator POST

- Status: verified.
- Added `memory/rag_quality.py` as the labelled golden-corpus semantic retrieval evaluator for production embedding quality.
- Added `GET /memory/rag-quality` through AppServer. The endpoint defaults to `storage/rag_quality/golden_corpus.json` or `memory.rag_quality.corpus_path`, returns `unproven` when corpus/model evidence is missing, and never upgrades semantic quality claims from deterministic speed evidence alone.
- `memory/rag_benchmark.py` now can attach the latest quality evaluation to `embedding_quality` and keep `closure_gate.can_claim_production_embedding_quality` aligned with the labelled evaluation result.
- Runtime Contract, Session Evidence, LLM Onboarding, Quickstart endpoint lists, and tests now expose `/memory/rag-quality`.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile memory\rag_quality.py memory\rag_benchmark.py server\app_server.py server\evidence_bundle.py core\runtime_contract.py` -> passed.
  - `.venv\Scripts\python.exe -m pytest tests\test_rag_performance.py tests\test_runtime_contract.py -q` -> `14 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `1 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_runtime_readiness_endpoint tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint tests\test_runtime_contract.py tests\test_rag_performance.py -q` -> `16 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_engineering_control.py tests\test_memory_manager.py tests\test_memory_manager_recall.py tests\test_cold_memory_vector.py tests\test_vector_index.py -q` -> `30 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: the evaluator is implemented and endpoint-backed. A real project golden corpus and local production embedding artifact are still required before production semantic recall quality can be claimed.
- Next: add the project golden corpus/local embedding artifact, split remaining AppServer route groups, or run GUI smoke for Workbench controls.

## 2026-06-27 09:49 RAG Evidence Service Extraction POST

- Status: verified.
- Added `server/rag_evidence_service.py` as the owner of deterministic RAG benchmark caching, production embedding quality evaluation caching, quality corpus path resolution, vector-index config handoff, and claim-gate evidence attachment.
- Refactored `server/app_server.py` so `rag_benchmark_status()`, `rag_benchmark_report()`, `rag_quality_status()`, and `rag_quality_report()` are thin delegates. AppServer still owns HTTP routing for `/memory/rag-benchmark` and `/memory/rag-quality`.
- Preserved dynamic config behavior: the service uses a current-config provider, so project/agent reload paths do not pin a stale config object.
- Added `tests/test_rag_evidence_service.py` covering cache hits, quality evidence enrichment of benchmark reports, relative corpus path resolution from the config file directory, quality eval storage path resolution, vector config propagation, and cache invalidation when `memory.rag_quality` config changes.
- Measured: `server/app_server.py` is `1941` lines after this slice; `server/rag_evidence_service.py` is `159` lines.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile server\rag_evidence_service.py server\app_server.py memory\rag_benchmark.py memory\rag_quality.py` -> passed.
  - `.venv\Scripts\python.exe -m pytest tests\test_rag_evidence_service.py tests\test_rag_performance.py tests\test_runtime_contract.py -q` -> `16 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_runtime_readiness_endpoint tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `2 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_external_llm_quickstart_endpoint tests\test_app_server_resume.py::test_app_server_external_agent_handoff_endpoint tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `3 passed`.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: this is an AppServer decoupling and evidence-service extraction. It does not add a real project golden corpus, a local production embedding artifact, or stronger production semantic-quality proof.
- Next: add that corpus/artifact, continue AppServer route dispatch splitting, or run GUI smoke for Workbench controls.

## 2026-06-27 10:01 Agent Bootstrap API Extraction POST

- Status: verified.
- Added `server/agent_bootstrap_api.py` as the payload builder for external Agent startup and handoff routes.
- Refactored `server/app_server.py` so `/agent/onboarding`, `/agent/onboarding.md`, `/agent/handoff`, `/agent/quickstart`, `/agent/quickstart.md`, and `/agent/maker-briefing` delegate payload assembly to `AgentBootstrapApi`. AppServer keeps HTTP parsing, 404 handling, and JSON/Markdown response transport.
- Added `tests/test_agent_bootstrap_api.py` covering service-level handoff and quickstart payload construction from persisted context, runtime metrics, LLM probe evidence, skill summary evidence, surface selection, and session availability checks.
- Measured: `server/app_server.py` is `1838` lines after this slice; `server/agent_bootstrap_api.py` is `122` lines.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile server\agent_bootstrap_api.py server\app_server.py server\evidence_bundle.py` -> passed.
  - `.venv\Scripts\python.exe -m pytest tests\test_agent_bootstrap_api.py tests\test_session_api.py tests\test_runtime_contract.py -q` -> `11 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_external_llm_quickstart_endpoint tests\test_app_server_resume.py::test_app_server_external_agent_handoff_endpoint tests\test_app_server_resume.py::test_app_server_maker_briefing_endpoint tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `4 passed`.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: this improves AppServer modularity and gives external-Agent bootstrap payloads a direct test seam. It does not complete the full route-dispatch split, GUI smoke, warm/hot resume proof, or production embedding-quality proof.
- Next: continue AppServer route dispatch extraction, add the real project golden corpus/local embedding artifact, or run GUI smoke for Workbench controls.

## 2026-06-27 10:55 Release Stability Verification POST

- Status: verified.
- Fixed: `tests/test_app_server.py` now uses an ephemeral local port for AppServer smoke checks, so a running GUI or stale service on `127.0.0.1:7345` cannot pollute mock-provider assertions.
- Fixed: `create_default_app_server(provider=...)` now applies an explicit provider override through base config and active-profile LLM config before constructing the runtime LLM.
- Fixed: AppServer tracks background session threads and `stop()` now cancels live sessions, answers pending approvals negatively, joins briefly, shuts down HTTP, and closes the server socket to avoid Windows SQLite/temp-dir locks during tests.
- Fixed: long-running AppServer/GUI integration tests now use timeouts that match full-suite runtime load instead of focused-test timing.
- Fixed: deterministic fake FAISS in `memory/rag_benchmark.py` now stores vectors and ranks by dot-product similarity instead of returning the newest IDs, so RAG profile/fallback hit-rate evidence is order-stable.
- Verification:
  - `.venv\Scripts\python.exe -m pytest -q` -> `732 passed, 14 skipped`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `npm.cmd --prefix electron run build` -> passed with Vite CJS deprecation warnings only.
  - `cargo test --manifest-path src-tauri\Cargo.toml` -> `34 passed`, warnings only.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: this proves automated release verification on the current workspace. It does not prove a visible GUI launcher smoke, Maker remote build, production embedding semantic quality, or a packaged installer.
- Next: run visible GUI smoke from the launcher, then create a release checkpoint/tag/package if the GUI smoke is clean.

## 2026-06-27 12:24 Visible GUI Release Smoke POST

- Status: verified.
- Verified: old 7345 backend listener was stopped before smoke, `cargo build --release --manifest-path src-tauri\Cargo.toml` refreshed `src-tauri\target\release\ttmevolve.exe`, and `TTMEvolve.vbs` launched the current release Tauri GUI.
- Verified: one visible Tauri top-level window titled `TTMEvolve` opened from `src-tauri\target\release\ttmevolve.exe`.
- Verified: `/health` returned `status=ok`, provider `minimax`, runtime kind `api`, model `MiniMax-M3`, and API key configured.
- Verified: `/runtime/portable` returned `status=ready`, with no blockers, no warnings, no outside-project paths, and no Windows user-dir leaks.
- Verified: `/llm/probe` returned `ok=true`, `output_preview=TTM_PROBE_OK`, HTTP 200, endpoint `https://api.minimax.chat/v1/text/chatcompletion_v2`, and `total_tokens=323`.
- Verified: `/runtime/readiness` returned `status=ready`, `call_proof=api_call_observed`, Maker readiness `ready`, Maker connected `true`, and Maker tool count `10`.
- Verified: `/maker/setup-status` and `/maker/tool-audit` returned `ready`; required Maker proxy tools were exposed, registered, handler-backed, and side-effect marked.
- Verified: Windows child-window enumeration showed visible `TTMEvolve` shell WebView and visible `TapTap 制造` Maker preview WebView inside the Tauri window.
- Verified: closing the GUI stopped the Tauri window and left no `ttmevolve.exe`, no embedded `main.py --embedded` process, and no listening `7345` port.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_start_scripts.py tests\test_tauri_lifecycle.py -q` -> `28 passed`.
  - `git diff --check` after documentation updates -> passed with existing LF/CRLF warnings only.
- Boundary: this proves visible launcher/runtime smoke for the current release exe. It does not prove a Maker remote build smoke, installer/package generation, signing, or production embedding semantic quality.
- Next: decide whether to run a Maker remote build smoke; otherwise prepare the release checkpoint/package.

## 2026-06-27 14:33 Release Push Stabilization POST

- Status: verified.
- Fixed: full-suite async learning test stability by separating fast user-result return from slower background learning completion under load.
- Fixed: deterministic RAG benchmark test stability by giving first recall a full-suite budget while keeping warm p95 and hit-rate gates strict.
- Cleaned: generated portable caches were removed through the guarded cleanup script; `portable/home/.taptap-maker` was preserved.
- Verified: source checkpoint package was rebuilt and audited with no forbidden entries.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_layer_events.py::test_agent_learning_layer_runs_async_after_result tests\test_rag_performance.py::test_rag_benchmark_fake_embeddings_meets_budget -q` -> `2 passed`.
  - `.venv\Scripts\python.exe -m pytest -q` -> `748 passed, 14 skipped`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `npm.cmd --prefix electron run build` -> passed with Vite CJS deprecation warnings only.
  - `cargo test --manifest-path src-tauri\Cargo.toml` -> `34 passed`, warnings only.
  - `.venv\Scripts\python.exe -m pytest tests\test_package_release.py tests\test_release_readiness.py -q` -> `8 passed`.
  - Source release readiness -> `ready`.
  - Full-offline readiness -> `partial`; offline runtime is ready, signed installer/Maker remote build/production RAG quality are unproven.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Boundary: this records the verified source release checkpoint before GitHub push. It does not upgrade unproven external gates.
- Next: commit and push.

## 2026-06-27 14:45 GitHub README Language Split POST

- Status: verified.
- Updated: `README.md` is a clean English GitHub README.
- Added: `README.zh-CN.md` is a clean standalone Chinese README.
- Fixed: removed corrupted mixed-language README text and added mutual language links.
- Verified: README files decode as UTF-8 and contain the expected language cross-links.
- Verified: source package rebuilt locally and source readiness remains `ready`.
- Verification:
  - UTF-8/readme assertions -> passed.
  - `.venv\Scripts\python.exe scripts\package_release.py` -> passed.
  - `.venv\Scripts\python.exe scripts\release_readiness.py --mode source-checkpoint --json` -> `status=ready`.
  - `.venv\Scripts\python.exe -m pytest tests\test_package_release.py tests\test_release_readiness.py -q` -> `8 passed`.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Boundary: documentation/readme update only; runtime and release claim gates are unchanged.
- Next: commit and push.
