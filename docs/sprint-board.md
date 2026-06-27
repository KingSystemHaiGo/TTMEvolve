# TTMEvolve Sprint Board

## Ownership Boundary

- This board tracks TTMEvolve product work.
- TTMEvolve is the application under development, not a co-developer.
- The user directs priorities; Codex implements and verifies changes in this repository.
- Use neutral product wording in sprint items: Fixed, Added, Verified, Blocked, Next.

## 2026-06-27 13:33 Release Readiness Claim Modes

- Status: verified.
- Done: split readiness auditing into `source-checkpoint` and `full-offline` modes.
- Done: source checkpoint mode now treats offline runtime, signing, Maker remote build, and production RAG quality as explicit out-of-scope evidence instead of hidden blockers.
- Verified: `tests\test_release_readiness.py` -> `6 passed`.
- Verified: `scripts\release_readiness.py --mode source-checkpoint --json` -> `status=ready`, blockers `[]`, source checkpoint gate `true`, full publishable release gate `false`.
- Blocked: `scripts\release_readiness.py --mode full-offline --json` -> `status=blocked`; blocker is `offline_runtime_bundle` due missing portable Python and portable size over budget.
- Boundary: source checkpoint is ready; full offline release is not ready.
- Next: create a clean offline runtime layout or add a dedicated portable builder/cleaner path that preserves Maker auth state.

## 2026-06-27 12:57 Source Release Checkpoint

- Status: verified.
- Done: hardened `scripts/package_release.py` into a safe source release checkpoint packager.
- Done: excluded private/runtime/build directories and files from release zips, including API config, env files, portable state, storage, models, vendor caches, workspace assets, node modules, and Tauri build target output.
- Done: generated `release-artifacts/TTMEvolve-source-v0.4.5-one-click-practice-entry.zip` plus manifest.
- Done: added `tests/test_package_release.py` for package exclusion and forbidden-entry validation.
- Done: added `scripts/release_readiness.py` and `tests/test_release_readiness.py` for repeatable source-checkpoint and release-claim auditing.
- Verified: package dry-run passed.
- Verified: source checkpoint zip and manifest created; the manifest is the authoritative file-count, size, SHA-256, and forbidden-entry evidence.
- Verified: independent zip scan -> `forbidden_count=0`, no probe hits for private/runtime/build paths.
- Verified: release readiness audit -> `status=partial`, blockers `[]`, source checkpoint gate `true`, full publishable release gate `false`.
- Verified: package/build/start-script focused pytest -> `36 passed`; `git diff --check` passed with existing LF/CRLF warnings only.
- Boundary: this is not yet a full offline runtime bundle, signed installer, Maker remote build proof, or production RAG semantic-quality proof.
- Next: run Maker remote build smoke if required, then prepare final release checkpoint summary.

## 2026-06-27 12:41 Architecture Boundary Control

- Status: verified.
- Done: accepted ADR-0003 for modular monolith with `RuntimeEventBus` as the in-process communication spine.
- Done: updated the architecture-control roadmap with current line counts and the resolved core-boundary import finding.
- Done: changed `core/harness.py` and `core/project_context.py` from top-level compatibility imports to lazy compatibility exports.
- Done: added `tests/test_core_boundary.py` to verify `core` compatibility imports do not load `cli` or `ecosystem` until the exported symbol is accessed.
- Verified: boundary/runtime/contract focused pytest -> `19 passed`.
- Verified: static import audit found no normal-operation `core -> cli` or `core -> ecosystem` imports.
- Verified: `git diff --check` passed with existing LF/CRLF warnings only.
- Next: continue AppServer route dispatch extraction, real RAG golden-corpus evidence, or release checkpoint packaging.

## 2026-06-27 02:43 Project Control Evidence Surface

- Status: verified.
- Fixed/Added: `project_control` now provides a project-manager evidence summary from `project_state`, `cos_gate`, and optional `runtime_advice`.
- Fixed/Added: Evidence Bundle and LLM Onboarding JSON/Markdown now carry project-control status, next action, verification state, and memory updates due.
- Guardrail: runtime-advice warnings remain visible but do not override known project-state next action.
- Verified:
  - Project-control + AppServer evidence focused pytest -> `4 passed`.
  - Readiness + Runtime Contract + SessionStore + intent classifier focused pytest -> `50 passed`.
  - `git diff --check` passed with existing CRLF warnings only.
- POST-mem: `docs/memory-index.md` touched.
- POST-sync: `docs/sprint-board.md` touched.
- Next: GUI project-manager mode and automatic POST/Sprint Board writeback from `project_control.memory_updates_due`.

## 2026-06-27 02:58 Workbench Project Control Surface

- Status: verified.
- Done: Agent Workbench now shows a Project Control card sourced from Evidence Bundle project-control data.
- Done: visible project-manager evidence includes status, gate progress, verification state, POST due count/files, blockers, and next action.
- Preserved: main chat remains user-facing; project-control diagnostics live in Workbench/evidence.
- Verified: frontend production build passed.
- Verified: backend project-control/evidence focused pytest -> `3 passed`.
- Verified: `git diff --check` passed with existing CRLF warnings only.
- Verified: Vite preview at `http://127.0.0.1:5177/` returned HTTP 200.
- Next: automatic POST/Sprint Board writeback from `project_control.memory_updates_due`.

## 2026-06-27 02:12 COS Gate 0 Evidence Surface

- Status: verified.
- Done: added deterministic COS Gate 0 classification in `core/intent_classifier.py`.
- Done: session creation now persists a `cos_gate` event through RuntimeEventBus + SessionStore.
- Done: Runtime Readiness, Session Evidence, Evidence Markdown, LLM Onboarding JSON, and Onboarding Markdown expose COS gate status/declaration/required gates.
- Done: LLM Onboarding closure gate now includes `cos_gate`, making the process threshold visible before external agents act.
- Verified: COS classifier + session/evidence endpoint pytest -> `33 passed`.
- Verified: SessionStore/runtime-contract/readiness/bus pytest -> `29 passed`.
- Verified: full `tests/test_app_server_resume.py` -> `24 passed`.
- Verified: intent e2e classifier checks -> `2 passed`; `git diff --check` passed with CRLF warnings only.
- Next: implement POST/project-manager automation from COS gate output and keep splitting AppServer route/session dispatch.

## 2026-06-27 01:44 AppServer Evidence Builder Extraction

- Status: verified.
- Done: extracted evidence/readiness/onboarding/quickstart builders from `server/app_server.py` into `server/evidence_bundle.py`.
- Done: kept AppServer public endpoint routing compatible while reducing `server/app_server.py` to `2104` lines.
- Done: evidence module now centralizes runtime metrics summaries, project/learning/memory observer summaries, LLM call proof, Runtime Readiness, Evidence Bundle, Onboarding Bundle, and Quickstart rendering.
- Verified: endpoint/contract/RAG focused pytest -> `13 passed`.
- Verified: project-state/runtime-event observer focused pytest -> `11 passed`.
- Verified: `git diff --check` passed.
- Next: split route dispatch/session API out of AppServer and attach COS classification/gates to session evidence.

## 2026-06-27 01:28 Workbench RAG Benchmark Surface

- Status: verified.
- Done: Agent Workbench now includes a RAG benchmark card backed by Evidence Bundle `rag_benchmark`.
- Done: the card has a manual refresh action that calls `/memory/rag-benchmark?force=true`.
- Done: the card exposes budget, record count, first recall, warm p95, endpoint/cache/no-network details, and the truthfulness boundary.
- Verified: `npm.cmd --prefix frontend run build` passed.
- Verified: Vite dev entry `http://127.0.0.1:5177/` returned HTTP 200.
- Verified: `git diff --check` passed.
- Next: extract AppServer evidence builders, then attach COS classification/gates to session evidence.

## 2026-06-27 01:12 RAG Benchmark Evidence Endpoint

- Status: verified.
- Done: moved deterministic RAG benchmark logic into `memory/rag_benchmark.py` as a reusable product service.
- Done: added `GET /memory/rag-benchmark` with cached report reads and `force=true` refresh.
- Done: Runtime Readiness, Session Evidence, Evidence Markdown, LLM Onboarding JSON, and Onboarding Markdown now expose compact `rag_benchmark` evidence.
- Done: LLM Onboarding closure gate includes `rag_benchmark` with `ready` only when the local deterministic benchmark passes budget.
- Measured: 10,001 records, build `760.314 ms`, cold start `128.648 ms`, first recall `13.494 ms`, warm p95 `16.282 ms`, profile/fallback hit rates `1.0`, budget `pass`.
- Verified: RAG/contract/evidence focused pytest -> `11 passed`.
- Verified: vector/RAG/memory/shared-policy/runtime-contract focused suite -> `41 passed`.
- Verified: `git diff --check` passed.
- Next: show this benchmark in Workbench, extract AppServer evidence builders, then attach COS classification/gates to session evidence.

## 2026-06-27 00:42 Runtime Learning/Memory Observer Evidence

- Status: verified.
- Done: added RuntimeEventBus-backed learning and memory/RAG observers.
- Done: Runtime Readiness, Session Evidence, Evidence Markdown, LLM Onboarding JSON, and Onboarding Markdown expose observer-backed `learning_observer` and `memory_recall` evidence.
- Done: persisted `context_budget` replay keeps working as the recovery path, now including `workspace_profile`.
- Verified: runtime observer/readiness/evidence focused pytest -> `11 passed`.
- Verified: session-store/runtime-metrics compatibility pytest -> `11 passed`.
- Verified: `git diff --check` passed.
- Next: extract AppServer evidence builders, add RAG performance benchmark, then attach COS classification/gates to session evidence.

## 2026-06-27 00:54 Deterministic RAG Performance Benchmark

- Status: verified.
- Done: added `ColdMemory.bulk_index()` so large knowledge imports can persist once and index vectors once.
- Done: added deterministic fake-FAISS RAG benchmark over 10k+1 records with explicit budget gates.
- Measured: build `637.869 ms`, cold start `102.919 ms`, first recall `17.17 ms`, warm p95 `13.61 ms`, profile/fallback hit rates `1.0`.
- Verified: `tests/test_rag_performance.py` -> `2 passed`.
- Verified: RAG/memory policy focused suite -> `23 passed`.
- Verified: vector+RAG focused suite -> `11 passed`.
- Next: expose benchmark reports through Evidence/Workbench, extract AppServer evidence builders, and attach COS classification/gates to session evidence.

> COS 协议 §三：门槛 0 分类 + 任务分级
> 当前 Sprint：v1.4.0 完整 release 准备

---

## 🎯 v1.4.0 — Release Check Sprint

### ✅ 已完成

| 版本 | 主题 | 状态 | 测试 |
|------|------|------|------|
| v0.7.0 | Tauri 桌面 + 主题 + Settings + LLM Router + portable | ✅ tag | 132 |
| v0.7.1 | Electron 删除准备（dry-run 工具 + 文档） | ✅ 脚本 | 17 |
| v0.7.2 | Rust fast_ops 模块 | ✅ tag | 13 |
| v0.7.3 | Rust ↔ Python HTTP 桥接 | ✅ tag | 14 |
| v0.8.0 | Tauri 自动桥接 + 生命周期 | ✅ tag | 12 |
| v0.9.0 | 跨平台 + 启动器完善 | ✅ tag | 14 |
| v1.0.0 | 自动更新 + 图标 | ✅ 集成 | 32 |
| v1.1.0 | 代码签名（Win/macOS/Linux） | ✅ 集成 | 18 |
| v1.2.0 | E2E 测试 | ✅ 集成 | 19 |
| v1.3.0 | 国际化（i18n） | ✅ 集成 | 31 |
| **总计** | | | **390/390** |

### 📋 v1.4.0 待办（当前 sprint）

- [ ] 时间戳同步（cos-time.sh all）
- [ ] memory-index.md 追加 v1.0-v1.3 条目
- [ ] CHANGELOG.md 撰写
- [ ] v1.4.0 tag 创建 + 推送
- [ ] 实际签名测试（待用户授权 + 证书）
- [ ] GitHub Release 创建
- [ ] 全文档更新（README + ROADMAP）

### ⏸️ 阻塞

| 项 | 原因 | 状态 |
|----|------|------|
| 实际代码签名 | 需要 EV 证书 | 待用户准备 |
| macOS 公证 | 需要 Apple Developer ID | 待用户准备 |
| Tauri 编译验证 | Rust 工具链已本机验证 | ✅ 32/32 |

### 📊 整体进度

| 模块 | 进度 |
|------|------|
| Plan First + Todolist | ✅ 100% |
| Coding Agent 强化 | ✅ 100% |
| Maker 游戏策划 | ✅ 100% |
| 知识整合 | ✅ 100% |
| 主题系统 | ✅ 100% |
| Settings 页面 | ✅ 100% |
| LLM Router | ✅ 100% |
| Tauri 桌面壳 | ✅ 100% |
| portable runtime | ✅ 100% |
| 自动更新 | ✅ 100% |
| 代码签名（脚本） | ✅ 100% |
| E2E 测试 | ✅ 100% |
| i18n | ✅ 100% |
| **总测试** | **598 Python + 32 Rust + frontend/Electron build** ✅ |

---

## 📊 整体进度

| 模块 | 进度 |
|------|------|
| Plan First + Todolist | ✅ 100% |
| Coding Agent 强化 | ✅ 100% |
| Maker 游戏策划 | ✅ 100% |
| 知识整合 | ✅ 100% |
| 主题系统 | ✅ 100% |
| Settings 页面 | ✅ 100% |
| LLM Router | ✅ 100% |
| Tauri 桌面壳 | ✅ 100% |
| portable runtime | ✅ 100% |
| **总测试覆盖** | **192/192** ✅ |

---

## 🐛 已知问题

| 问题 | 优先级 | 状态 |
|------|--------|------|
| Tauri 首次编译慢 | 🟢 | 已知，不阻塞 |
| Maker MCP 长任务轮询 | 🟡 | 设计中 |
| macOS / Linux WebView 适配 | 🟡 | v0.8.0 |
| Electron 代码清理 | 🟢 | v0.7.1 |
| 普通用户界面暴露候选工具/英文状态 | 🔴 | 已修复：主聊天隐藏候选工具列表，历史浮层可关闭，状态文案中文化 |
| 查看项目状态/了解项目工具选择不稳定 | 🔴 | 已修复：新增只读 `project_status` 并提高排序权重 |

---

## 📌 下一 Sprint（v2.0.0 路线）

- [ ] Tauri GUI 测试套件（Playwright + WebView2）
- [ ] macOS / Linux 正式版
- [ ] 国际化（i18n）前端集成
- [ ] pyo3 直接绑定（避免 HTTP 序列化）
- [ ] 多 Agent 协作模式

---

## 🎓 回顾要点

### 本 Sprint 学到的

1. **架构演进需要分阶段**：v0.6.0 → v0.7.0 保持 Electron 兼容，v0.7.1 才删除
2. **测试覆盖是迁移信心**：192/192 测试让 Tauri 迁移零回归
3. **借鉴 > 重新设计**：从 taptap-maker-plus 学 Settings 5 面板，从 COS 学记忆系统
4. **云端 LLM 是正确选择**：减少 60% 包体积，提升维护性

### 风险登记

- ⚠️ Maker MCP 远端依赖：网络抖动会失败
- ⚠️ Rust 学习曲线：未来热路径优化需 Rust 能力
- ⚠️ 跨平台 WebView 差异：Windows WebView2 / macOS webkit / Linux webkit2gtk

---

## 📞 沟通

- **用户**：灰語（Taptap Maker 开发者）
- **AI**：嗒啦啦（自进化 Agent）
- **下次更新**：v0.7.1 启动时

---

> 最后更新：2026-06-26 10:15
> 版本：v1.5.1 全量运行 bugfix
> 触发：全量 pytest / frontend build / Electron build / Cargo test
## Last updated: 2026-06-26 08:42

## 2026-06-26 13:52 Native Maker Preview

- Status: done.
- Fixed: Tauri desktop preview now uses a native child WebView2 (`maker-preview`) for normal users instead of screenshot polling.
- Preserved: Playwright browser service remains the Agent automation path.
- Verified: frontend build, Rust build/test, lifecycle/start-script tests, release build, and real `TTMEvolve.vbs` smoke with one visible app window and WebView2 child window evidence.

## 2026-06-26 14:51 Cockpit Status Placement

- Status: done.
- Moved project/model/config to the left-top chat context area.
- Kept Maker MCP status in the top bar with Maker actions.
- Moved token/latency evidence to assistant-message usage chips.
- Verified: frontend build and Tauri release build.

## 2026-06-26 MakerMCP Auto Update + Real Probe

- Status: done.
- Added automatic cached npm latest-version checks to Maker setup status.
- Added fresh Maker MCP stdio initialize/tools-list probe surfaced through `/mcp/probe`, `/mcp/status?probe=true`, and Maker setup evidence.
- GUI now shows package update evidence and real probe result, while normal polling uses cached checks.
- Verified: focused Python MCP/setup diagnostics and frontend build.

## 2026-06-26 Desktop Visual Rhythm Polish

- Status: done.
- Unified titlebar, Maker action topbar, chat context cards, conversation bar, input row, and tool buttons around shared radius/control-height tokens.
- Reduced mismatched mint panels and aligned the shell into one desktop surface.
- Verified: frontend build and browser screenshot check at 1600x900.

## 2026-06-26 Desktop UX Evidence Pass

- Status: verifying.
- Principle: screenshots are treated as stale evidence unless confirmed by current code/tests/runtime.
- Updated: history popover has explicit icon close plus Esc/outside-click dismissal.
- Updated: Workbench normal labels use Chinese product language and no longer expose candidate-count wording in user-facing summaries.
- Updated: chat status/event filtering maps tool-selection/candidate/ranking internals to "正在判断下一步".
- Added: regression coverage that project_status and execute_shell stay ahead of Maker tools for project-state/cmd requests.

## 2026-06-26 Runtime Event Bus Foundation

- Status: verifying.
- Added a shared in-process RuntimeEventBus with typed envelopes, filtered subscriptions, bounded replay, unsubscribe, stats, and observer error isolation.
- Wired AppServer sessions through the shared server event bus while preserving existing SQLite/SSE event shape.
- Verified focused runtime-event and AppServer session bus tests.
- Next: migrate more Agent/Core/Learning producers and project-management observers onto the bus instead of direct event queues.

## 2026-06-26 Agent Event Bus Migration

- Status: verifying.
- TapMakerAgent now publishes ReAct and layer events through an Agent-owned RuntimeEventBus before keeping the compatibility session queue.
- Agent event replay no longer requires direct _event_queues access for consumers that can subscribe to the bus.
- Verified layer-event tests plus runtime/AppServer bus focused tests.
- Next: expose bus stats/evidence in runtime readiness and move project-management observers onto subscriptions.

## 2026-06-26 Runtime Event Bus Evidence Surface

- Status: verified.
- Runtime Readiness now reports `runtime_event_bus` plus a release-gate check for the server/Agent bus surface.
- Session Evidence JSON/Markdown and LLM Onboarding JSON/Markdown now expose bus stats, session event counts, layer-event counts, and compatibility evidence.
- Chat/history/input surfaces were cleaned for normal users: explicit history close, Chinese/English visible labels, and no candidate-tool ranking in the main conversation.
- Verified: focused readiness/evidence endpoint pytest and `frontend` production build.
- Next: wire project-management observers onto bus subscriptions and continue replacing direct queue reads.

## 2026-06-26 Runtime Metrics Observer

- Status: verified.
- Added a live RuntimeMetricsObserver that subscribes to Runtime Event Bus session events and derives compact metrics without coupling to Session internals.
- `/sessions/{id}/runtime-metrics` now reports observer/store counts and uses observer history when available, preserving SQLite as durable fallback.
- Runtime Readiness/Evidence expose observer status so attached agents can tell whether metrics came from bus snapshots or persisted replay.
- Verified: bus observer unit test plus AppServer runtime-metrics/readiness/evidence focused tests.
- Next: add project-management task state observers on the same bus path.

## 2026-06-26 Project Management Observer

- Status: verified.
- Added a live ProjectManagementObserver that subscribes to Runtime Event Bus session events and derives next action, goal status, plan verdict, continuation readiness, artifacts, and risk flags.
- Added `/sessions/{id}/project-state` plus Evidence/Onboarding/Readiness project-state fields so external agents and the GUI can inspect project control state directly.
- Runtime Contract now advertises project-state in communication endpoints and external-agent attach sequence.
- Verified: runtime event observer tests, AppServer project-state endpoint, Evidence bundle, and Runtime Contract focused tests.
- Next: wire this project-state snapshot into the Workbench UI and use it to drive proactive next-step recommendations.

## 2026-06-26 22:29 Chinese-First Desktop UI Polish

- Status: verified.
- Fixed: main chat no longer shows candidate-tool/ranking internals; it maps those events to user-facing progress and filters raw tool-selection events.
- Fixed: history is a compact popover with an explicit close button, outside-click and Esc dismissal, and no instructional clutter.
- Fixed: primary chat/input/topbar labels are Chinese-first; GitHub README remains bilingual.
- Fixed: topbar/chat context/history surfaces share the same control heights, radii, shadows, and theme tokens.
- Verified: `npm.cmd --prefix frontend run build`, focused project-status/cmd ToolRegistry pytest (`4 passed`), and `git diff --check`.

## 2026-06-26 22:46 Vector Index Fast Path

- Status: verified.
- Fixed: FAISS search result materialization now uses `_reverse_id_map` for O(1) internal-id lookup instead of scanning every chunk id.
- Fixed: batch vector add now allocates unique internal ids even when many chunks are added in the same timestamp window.
- Preserved: keyword fallback and profile-aware cold-memory recall behavior.
- Verified: `tests/test_vector_index.py tests/test_cold_memory_vector.py tests/test_memory_manager_recall.py` -> `18 passed, 2 skipped`.

## 2026-06-26 23:08 Desktop History + Project Tool Reliability

- Status: verified.
- Fixed: history trigger now switches to `关闭历史` while open; the popover states close button, Esc, and outside-click dismissal.
- Fixed: normal chat and active status keep candidate/ranking internals hidden behind user-facing progress language.
- Fixed: `project_status` and `execute_shell` are pinned for project-state/cmd/git-status tasks even if Maker context is present.
- Preserved: `Token` and `tok/s` remain technical units in assistant usage chips.
- Verified: `npm.cmd --prefix frontend run build` and focused ToolRegistry pytest (`6 passed`).

## 2026-06-26 23:34 Maker Dynamic Tool Execution Fix

- Status: verified.
- Fixed: dynamically discovered Maker MCP tools such as `maker_status_lite` now execute through the Maker handler with the required `tool_name` argument instead of being called like ordinary local handlers.
- Fixed: rescue cooldown/count checks now sanitize numeric state/config before comparison, preventing secondary errors such as string-vs-float comparisons during repeated failure recovery.
- Added regression coverage for `Executor.propose_action("maker_status_lite", {})` through the fake MCP server.
- Verified: `tests/test_mcp_diagnostics.py tests/test_rescue_loop.py` -> `12 passed`; `tests/test_tool_timeouts.py` -> `5 passed`; `npm.cmd --prefix frontend run build` passed.

## 2026-06-26 23:39 Memory Boundary Correction

- Status: verified.
- Fixed: core memory docs now state that TTMEvolve is the product under development, not a co-developer.
- Added: ownership/memory boundary headers in the docs most likely to be read at session startup or POST time.
- Rewritten: `docs/persona.md` now describes the product's in-app Agent persona and explicitly separates it from Codex private memory.
- Next: gradually clean older historical docs/footers that use author/persona wording such as "灰語 & 嗒啦啦" when those docs are next touched.

## 2026-06-27 00:06 Architecture Control + RAG Correctness

- Status: verified.
- Added: `docs/architecture/architecture-control-roadmap-2026-06-27.md` as the current control roadmap for code audit, decoupling, RuntimeEventBus migration, RAG performance, three-layer runtime independence, COS gates, multi-agent shared memory, truthfulness gates, project management, and long-task continuity.
- Fixed: fresh `VectorIndex.add()` now builds a FAISS index when vector dependencies are available instead of requiring an index to already exist.
- Fixed: `VectorIndex._rebuild_index()` now replaces the FAISS index instead of appending duplicate records to an old one.
- Added: fake-FAISS regression coverage for rebuild replacement, so the behavior is tested even when real FAISS is not installed.
- Verified: `tests/test_vector_index.py tests/test_cold_memory_vector.py tests/test_memory_manager_recall.py` -> `21 passed`.
- Next: split `server/app_server.py` evidence/readiness/onboarding builders, add RAG performance benchmarks, attach COS classification to session evidence, and add RuntimeEventBus observer failure counters.

## 2026-06-27 00:20 Runtime Event Bus Observer Failure Evidence

- Status: verified.
- Fixed: RuntimeEventBus now records observer callback failures without interrupting event publishing.
- Added: `observer_error_count`, `observer_errors_by_handler`, and `last_observer_error` in bus stats.
- Added: AppServer runtime-event-bus summaries now expose `observer_health` and total `observer_error_count`.
- Added: Evidence Markdown and LLM Onboarding Markdown include observer health/error count, so external agents can diagnose bus observer drift from compact pasted evidence.
- Verified: `tests/test_runtime_events.py` plus focused AppServer readiness/evidence endpoint tests -> `9 passed`.
- Verified: `git diff --check` passed.
- Next: extract AppServer evidence builders, add RAG performance benchmarks, then attach COS classification/gates to session evidence.
# Ownership Boundary

- This board tracks TTMEvolve product work.
- TTMEvolve is the application under development, not a co-developer.
- 灰語 directs priorities; Codex/嗒啦啦 implements and verifies changes in this repository.
- Use neutral product wording in sprint items: Fixed, Added, Verified, Blocked, Next.

## 2026-06-27 03:33 Project Control Writeback

- Status: verified.
- Completed: safe project writeback planner/apply module, AppServer GET/POST endpoint, Runtime Contract communication entry, Session Evidence/Onboarding summaries, and Workbench Project Control readout.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_project_writeback.py tests\test_project_control.py tests\test_runtime_contract.py tests\test_app_server_resume.py::test_app_server_project_writeback_endpoint_plans_and_applies tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `16 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: project writeback is explicit and guarded; default POST is dry-run and no background memory mutation is enabled.
- Next: split AppServer route/session dispatch further, then implement shared-memory promotion/demotion based on verified outcomes.

## 2026-06-27 03:55 AppServer Session Route Split

- Status: verified.
- Completed: `server/session_api.py`, AppServer delegation for session status/history/context/runtime/project/writeback/learning/guard/probe/evidence/advice routes, and focused helper tests.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_session_api.py tests\test_app_server_resume.py::test_app_server_runtime_metrics_endpoint_uses_bus_observer tests\test_app_server_resume.py::test_app_server_project_state_endpoint_uses_bus_observer tests\test_app_server_resume.py::test_app_server_project_writeback_endpoint_plans_and_applies tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `6 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py tests\test_runtime_contract.py tests\test_project_writeback.py tests\test_project_control.py -q` -> `39 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: this is route/payload decoupling, not a new public API behavior change.
- Next: choose the next decoupling slice: remaining AppServer route groups, `agent/react_loop.py` phase modules, or shared-memory promotion/demotion rules.

## 2026-06-27 04:05 Agent Maker Guard Phase Split

- Status: verified.
- Completed: `agent/maker_guard.py`, direct Maker guard rule tests, and `ReActLoop` delegation for first-action Maker authority decisions.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_maker_guard.py tests\test_tool_call_validation.py::test_react_loop_blocks_first_local_side_effect_when_maker_briefing_requires_authority -q` -> `9 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_tool_call_validation.py tests\test_runtime_contract.py tests\test_maker_guard.py -q` -> `50 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_plan_first_integration.py tests\test_plan_validation.py tests\test_goal_tracking.py -q` -> `11 passed`.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: this is the first Maker guard phase extraction from `agent/react_loop.py`, not the full ReActLoop split.
- Next: extract action validation/execution result handling or context sync/checkpoint builders from `agent/react_loop.py`.

## 2026-06-27 04:23 Agent Action Execution Phase Split

- Status: verified.
- Completed: `agent/action_execution.py`, direct action execution service tests, and `ReActLoop` delegation for progress heartbeats, executor dispatch, validation failure payloads, commit reconciliation, and timeout context hints.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_action_execution.py tests\test_tool_call_validation.py::test_react_loop_emits_tool_progress_heartbeat tests\test_tool_call_validation.py::test_react_loop_reconciles_uncertain_commit_state tests\test_tool_call_validation.py::test_react_loop_emits_tool_preflight_for_invalid_action -q` -> `10 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_action_execution.py tests\test_tool_call_validation.py tests\test_tool_timeouts.py tests\test_runtime_contract.py tests\test_plan_first_integration.py tests\test_plan_validation.py tests\test_goal_tracking.py -q` -> `65 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: this is action execution phase extraction, not the complete ReActLoop split.
- Next: extract context sync/checkpoint builders from `agent/react_loop.py`, then add shared-memory promotion/demotion rules.

## 2026-06-27 04:40 Agent Context Sync Phase Split

- Status: verified.
- Completed: `agent/context_sync.py`, direct context sync/checkpoint builder tests, and `ReActLoop` delegation for context-sync snapshot construction, signature calculation, diff keys, continuation checkpoint assembly, artifact refs, and commit-state extraction.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_context_sync.py tests\test_tool_call_validation.py::test_react_loop_emits_context_sync_snapshot tests\test_tool_call_validation.py::test_react_loop_context_sync_includes_continuation_checkpoint tests\test_tool_call_validation.py::test_react_loop_context_sync_deduplicates_unchanged_snapshot -q` -> `7 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_context_sync.py tests\test_tool_call_validation.py tests\test_runtime_events.py tests\test_app_server_resume.py::test_app_server_context_sync_endpoint tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `49 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: this is context handoff/checkpoint builder extraction, not proof of hot process resurrection.
- Next: implement shared-memory promotion/demotion records with conflict handling, or continue ReAct planning phase extraction.

## 2026-06-27 05:13 Shared Memory Outcome Rules

- Status: verified.
- Completed: `memory/shared_outcome.py`, `ColdMemory.record_shared_outcome()`, persisted unresolved conflict ledger, Evidence Bundle outcome-rule fields, and vector-first RAG search fast path.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_shared_memory_policy.py tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `10 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_vector_index.py tests\test_cold_memory_vector.py tests\test_rag_performance.py -q` -> `19 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_shared_memory_policy.py tests\test_cold_memory_vector.py tests\test_memory_manager_recall.py tests\test_memory_manager.py tests\test_rag_performance.py tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint tests\test_app_server_resume.py::test_app_server_runtime_readiness_endpoint -q` -> `30 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: shared promotion/demotion is now a local verified policy ledger, not yet an automatic learning-worker pipeline or real two-agent collaboration run.
- Next: wire learning validation into `record_shared_outcome()` and add a two-agent shared-memory handoff simulation.

## 2026-06-27 05:31 Learning Shared-Memory Bridge

- Status: verified.
- Completed: `learning/shared_memory_bridge.py`, `TapMakerAgent._learn_from_session()` shared-memory summary wiring, learning job shared-memory metrics, and deterministic two-agent handoff/conflict tests.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_learning_shared_memory_bridge.py tests\test_shared_memory_policy.py -q` -> `13 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_learning_shared_memory_bridge.py tests\test_shared_memory_policy.py tests\test_memory_manager_recall.py tests\test_rag_performance.py tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint tests\test_app_server_resume.py::test_app_server_persists_layer_and_learning_events tests\test_runtime_events.py -q` -> `30 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_vector_index.py tests\test_cold_memory_vector.py tests\test_learning_shared_memory_bridge.py -q` -> `21 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: local learning-to-shared-memory bridge and deterministic two-agent simulation are verified; real multi-process shared-memory orchestration and production embedding-quality evaluation remain pending.
- Next: define fuller layer-health snapshots/learning queue gates or continue remaining `agent/react_loop.py` planning phase extraction.

## 2026-06-27 05:52 Layer Health Snapshot

- Status: verified.
- Completed: `server/layer_health.py`, `/sessions/{id}/layer-health?steps=N`, evidence/readiness/onboarding/runtime-contract wiring, and AppServer/session API regression coverage.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_layer_health.py tests\test_runtime_contract.py tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `12 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_runtime_readiness_endpoint tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint tests\test_app_server_resume.py::test_app_server_persists_layer_and_learning_events tests\test_runtime_events.py tests\test_session_api.py -q` -> `14 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: layer-health snapshots are compact evidence and learning queue-depth visibility; managed worker cancellation/retry, real process restart drills, and hot-resume remain pending.
- Next: add engineering-control thresholds/actions for layer latency, missing communication routes, learning backlog, and runtime errors.

## 2026-06-27 06:06 Layer Control Thresholds

- Status: verified.
- Completed: `server/layer_control.py`, `/sessions/{id}/layer-control?steps=N`, Runtime Contract endpoint/mechanism wiring, Runtime Readiness gate wiring, Session Evidence JSON/Markdown, LLM Onboarding JSON/Markdown, and focused regression coverage.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_layer_control.py -q` -> `4 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_layer_control.py tests\test_layer_health.py tests\test_runtime_contract.py tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `16 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_runtime_readiness_endpoint tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint tests\test_app_server_resume.py::test_app_server_persists_layer_and_learning_events tests\test_runtime_events.py tests\test_session_api.py -q` -> `14 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: layer-control emits thresholds and corrective actions only; it does not yet execute remediation, cancel/retry learning jobs, or prove runtime restart resume.
- Next: feed top layer-control actions into Workbench/project-control and add control gates for memory misses, repeated tool failures, and failed plan gates.

## 2026-06-27 06:20 Layer Control Project Surface

- Status: verified.
- Completed: project-control `layer_control`/`control_actions` input and output, `/sessions/{id}/project-state` layer-control wiring, Session Evidence project-control action visibility, and Workbench Project Control card rendering for the top corrective action.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_project_control.py tests\test_layer_control.py tests\test_app_server_resume.py::test_app_server_project_state_endpoint_uses_bus_observer tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `8 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_session_api.py tests\test_runtime_contract.py tests\test_app_server_resume.py::test_app_server_runtime_readiness_endpoint tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint tests\test_app_server_resume.py::test_app_server_project_state_endpoint_uses_bus_observer -q` -> `13 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: corrective actions are surfaced for review and project management only; automatic remediation remains pending.
- Next: add control gates for memory misses, repeated tool failures, and failed plan gates.

## 2026-06-27 06:44 Engineering Control Runtime Gates

- Status: verified.
- Completed: `server/engineering_control.py`, `/sessions/{id}/engineering-control?steps=N`, Runtime Contract endpoint wiring, Runtime Readiness gate wiring, Session Evidence/Onboarding JSON+Markdown wiring, Project Control merge, and Workbench Project Control readout.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_engineering_control.py tests\test_project_control.py tests\test_runtime_contract.py -q` -> `15 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_runtime_readiness_endpoint tests\test_app_server_resume.py::test_app_server_project_state_endpoint_uses_bus_observer tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `3 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_session_api.py tests\test_layer_control.py tests\test_layer_health.py tests\test_runtime_events.py -q` -> `18 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_external_llm_quickstart_endpoint tests\test_app_server_resume.py::test_app_server_external_agent_handoff_endpoint tests\test_app_server_resume.py::test_app_server_runtime_advice_endpoint_prioritizes_blocked_maker_guard tests\test_app_server_resume.py::test_app_server_context_sync_endpoint tests\test_app_server_resume.py::test_app_server_runtime_metrics_endpoint -q` -> `5 passed`.
  - Python `py_compile`, frontend build, and `git diff --check` passed; diff check had existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: this is a control-evidence and project-management surface, not automatic remediation.
- Next: decide between managed learning-worker queue policy, restart/resume drills, or remaining `agent/react_loop.py` planning phase extraction.

## 2026-06-27 07:13 Durable Resume Drill

- Status: verified.
- Completed: `server/resume_drill.py`, `/sessions/{id}/resume-drill?steps=N`, Runtime Contract endpoint/mechanism wiring, Runtime Readiness gate wiring, Session Evidence/Onboarding JSON+Markdown wiring, Quickstart endpoint exposure, and Workbench external-agent boot summary.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile server\resume_drill.py server\evidence_bundle.py server\session_api.py server\app_server.py core\runtime_contract.py` -> passed.
  - `.venv\Scripts\python.exe -m pytest tests\test_resume_drill.py tests\test_runtime_contract.py -q` -> `10 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_context_sync_endpoint tests\test_app_server_resume.py::test_app_server_runtime_readiness_endpoint tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint tests\test_app_server_resume.py::test_app_server_external_llm_quickstart_endpoint tests\test_app_server_resume.py::test_app_server_external_agent_handoff_endpoint -q` -> `5 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_session_api.py tests\test_resume_drill.py tests\test_runtime_contract.py tests\test_project_control.py tests\test_engineering_control.py -q` -> `19 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py -q` -> `25 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: resume drill is durable store-replay handoff evidence only; warm process resume and hot in-flight tool-call resurrection remain unproven.
- Next: managed learning-worker queue/cancel/retry policy or remaining `agent/react_loop.py` planning/trajectory extraction.

## 2026-06-27 07:48 Managed Learning Job Queue

- Status: verified.
- Completed: `agent/learning_queue.py`, `TapMakerAgent` learning dispatch refactor, live learning cancel/retry methods, `POST /sessions/{id}/learning/cancel`, `POST /sessions/{id}/learning/retry`, `/sessions/{id}/learning` job/policy payloads, durable learning-job replay fallback, `layer_health` job policy fields, Runtime Contract endpoint exposure, and regression tests.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile agent\learning_queue.py agent\agent.py server\evidence_bundle.py server\session_api.py server\app_server.py server\layer_health.py core\runtime_contract.py` -> passed.
  - `.venv\Scripts\python.exe -m pytest tests\test_learning_job_queue.py -q` -> `3 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_learning_job_queue.py tests\test_layer_events.py tests\test_layer_health.py tests\test_layer_control.py tests\test_runtime_contract.py -q` -> `23 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_persists_layer_and_learning_events tests\test_app_server_resume.py::test_app_server_learning_control_uses_live_agent_or_reports_replay_boundary tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint tests\test_app_server_resume.py::test_app_server_runtime_readiness_endpoint tests\test_session_api.py tests\test_engineering_control.py tests\test_project_control.py -q` -> `13 passed`.
  - Combined AppServer/layer/runtime suite -> `48 passed`, `1` `/memory/rag-benchmark?force=true` timeout under long-suite load; isolated rerun of the evidence endpoint -> `1 passed`, and `tests\test_rag_performance.py` -> `2 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: managed learning queue is live-agent/session-scoped. It is not a global multi-process scheduler, GUI operation surface, or production throughput benchmark.
- Next: add Workbench/project-control learning cancel/retry review, or continue remaining `agent/react_loop.py` planning/trajectory extraction.

## 2026-06-27 08:06 Workbench Learning Control Review

- Status: verified.
- Completed: Workbench learning card now reads learning `job`/`policy` evidence, shows compact job summaries, exposes guarded `Cancel` and `Retry` controls for live queues, and displays the durable replay boundary when historical learning events cannot be controlled.
- Verification:
  - `npm.cmd --prefix frontend run build` -> passed.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_learning_control_uses_live_agent_or_reports_replay_boundary tests\test_runtime_contract.py::test_runtime_contract_summarizes_maker_and_communication_surfaces -q` -> `2 passed`.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: frontend build and backend contract are verified; no visual GUI smoke was run in this slice.
- Next: continue `agent/react_loop.py` planning/trajectory extraction, production embedding-quality benchmarks, or a GUI smoke pass for the Workbench controls.

## 2026-06-27 08:21 Plan First Phase Extraction

- Status: verified.
- Completed: `agent/plan_first.py` now owns Plan First drafting/review/approval/no-approval behavior, including parse and approval error events.
- Completed: `agent/react_loop.py` delegates Plan First flow to the extracted module and retains compatibility wrapper methods for existing tests/monkeypatches.
- Preserved: public plan-first event names and result shape remain compatible.
- Measured: `agent/react_loop.py` is `801` lines; `agent/plan_first.py` is `158` lines.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile agent\plan_first.py agent\react_loop.py` -> passed.
  - Plan-first focused pytest -> `9 passed`.
  - Restored plan-first plus adjacent runtime/control suite -> `72 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: Plan First is extracted; full planning/trajectory/result runtime decomposition and automatic plan remediation remain pending.
- Next: extract remaining trajectory/result handling from `ReActLoop`, add production embedding-quality benchmarks, or run a GUI smoke pass for Workbench learning controls.

## 2026-06-27 08:34 Trajectory Result Helper Extraction

- Status: verified.
- Completed: `agent/trajectory_result.py` now owns normal ReAct output-step recording, observation-step recording, latest-output lookup, final result construction, and compact result summaries.
- Completed: `agent/react_loop.py` delegates done-output handling plus Maker guard, tool preflight validation, and normal tool observation recording to the extracted helper.
- Preserved: public event/result contracts stay compatible for `output`, `observation`, `plan_validation`, `goal_checklist`, skill/context sync, `plan_validation` summary, `goal_checklist`, `plan`, `plan_review`, and `plan_progress`.
- Measured: `agent/react_loop.py` is `799` lines; `agent/trajectory_result.py` is `108` lines.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile agent\trajectory_result.py agent\react_loop.py` -> passed.
  - Focused trajectory/ReAct branch suite -> `11 passed`.
  - Broad adjacent action/context/plan/goal/runtime suite -> `87 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: expert takeover trajectory handling and remaining ReActLoop orchestration are still inside `agent/react_loop.py`.
- Next: extract expert-takeover/rescue trajectory handling, add production embedding-quality benchmarks, or run a GUI smoke pass for Workbench learning controls.

## 2026-06-27 08:49 Expert Takeover Runner Extraction

- Status: verified.
- Completed: `agent/expert_takeover.py` now owns the expert loop-takeover runner for thought/action/tool-call/output/observation/error event emission.
- Completed: `agent/react_loop.py:takeover()` delegates to the extracted runner while preserving the same public rescue entrypoint.
- Preserved: expert trajectory entries still use `source=expert`; expert event payloads keep `source=expert`; failed expert tool observations append an error hint before the next expert thought.
- Measured: `agent/react_loop.py` is `761` lines; `agent/expert_takeover.py` is `94` lines.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile agent\expert_takeover.py agent\react_loop.py` -> passed.
  - `tests\test_expert_takeover.py tests\test_rescue_loop.py` -> `7 passed`.
  - Expert/rescue/action/context/runtime adjacent suite -> `69 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: direct-action rescue trajectory append remains in `agent/rescue_orchestrator.py`.
- Next: extract the rescue direct-action append path, add production embedding-quality benchmarks, or run a GUI smoke pass for Workbench learning controls.

## 2026-06-27 08:57 Rescue Direct-Action Append Extraction

- Status: verified.
- Completed: `agent/rescue_application.py` now owns direct-action rescue trajectory entry construction and append behavior.
- Completed: `agent/rescue_orchestrator.py` delegates direct-action expert step append after `react.inject_expert_action()` returns the observation.
- Preserved: direct-action rescue still executes through `inject_expert_action()`, keeps `source=expert`, uses the current trajectory length as iteration, stores rescue thought/action/observation, and does not add new observation events.
- Measured: `agent/rescue_orchestrator.py` is `259` lines; `agent/rescue_application.py` is `27` lines.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile agent\rescue_application.py agent\rescue_orchestrator.py` -> passed.
  - `tests\test_rescue_application.py tests\test_rescue_loop.py` -> `6 passed`.
  - Expert/rescue/action/context/runtime adjacent suite -> `71 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: `_apply_rescue()` still owns mode validation and rescue mode dispatch.
- Next: add production embedding-quality benchmark boundaries, split remaining AppServer route groups, or run a GUI smoke pass for Workbench learning controls.

## 2026-06-27 09:11 RAG Embedding Quality Boundary

- Status: verified.
- Completed: `memory/rag_benchmark.py` now returns `embedding_quality` with `status=unproven` by default and `closure_gate.can_claim_production_embedding_quality=false` unless production-quality evidence exists.
- Completed: deterministic RAG speed reports now declare `benchmark_scope=deterministic_local_pipeline_speed` and retain `can_claim_deterministic_rag_speed=true` only when the speed budget passes.
- Completed: Runtime Readiness, Session Evidence JSON/Markdown, LLM Onboarding JSON/Markdown, Runtime Contract, and Workbench RAG benchmark card expose the quality boundary.
- Verification:
  - `py_compile memory\rag_benchmark.py server\evidence_bundle.py core\runtime_contract.py` -> passed.
  - `tests\test_rag_performance.py tests\test_runtime_contract.py` -> `12 passed`.
  - `tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint` -> `1 passed`.
  - Readiness/evidence/runtime-contract/RAG focused suite -> `14 passed`.
  - Engineering-control/memory/vector adjacent suite -> `30 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: no production embedding model, labelled corpus, or semantic recall metric was executed in this slice.
- Next: add the production embedding quality evaluation runner/golden corpus, continue AppServer route splitting, or run GUI smoke for Workbench controls.

## 2026-06-27 09:35 RAG Quality Evaluator

- Status: verified.
- Completed: `memory/rag_quality.py` implements a labelled golden-corpus retrieval quality evaluator with recall@k, precision@k, MRR, query-count budgets, per-query evidence, and explicit unproven reports for missing corpus/model evidence.
- Completed: `GET /memory/rag-quality` runs the evaluator from AppServer with no-network local-model defaults and exposes the result separately from deterministic `/memory/rag-benchmark` speed checks.
- Completed: `memory/rag_benchmark.py` attaches the latest quality evaluation into `embedding_quality`; production semantic-quality claims require `can_claim_production_embedding_quality=true`.
- Completed: Runtime Contract, Evidence, Onboarding, Quickstart endpoint lists, and focused tests expose the new endpoint.
- Verification:
  - `py_compile memory\rag_quality.py memory\rag_benchmark.py server\app_server.py server\evidence_bundle.py core\runtime_contract.py` -> passed.
  - `tests\test_rag_performance.py tests\test_runtime_contract.py` -> `14 passed`.
  - `tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint` -> `1 passed`.
  - Readiness/evidence/runtime-contract/RAG focused suite -> `16 passed`.
  - Engineering-control/memory/vector adjacent suite -> `30 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: a real project golden corpus and local production embedding artifact are not yet present; default AppServer evaluation remains `unproven`.
- Next: add that corpus/artifact, split remaining AppServer route groups, or run GUI smoke for Workbench controls.

## 2026-06-27 09:49 RAG Evidence Service Extraction

- Status: verified.
- Completed: `server/rag_evidence_service.py` now owns RAG benchmark cache/reporting, RAG quality cache/reporting, `memory.rag_quality` config parsing, config-file-relative corpus path resolution, eval-index storage path selection, and embedding-quality claim-gate attachment.
- Completed: `server/app_server.py` delegates RAG benchmark/quality status and report calls to the service while preserving `/memory/rag-benchmark` and `/memory/rag-quality` behavior.
- Added tests: `tests/test_rag_evidence_service.py` covers benchmark cache hits, quality evidence enrichment, path/config propagation, and cache invalidation when quality config changes.
- Measured: `server/app_server.py` is `1941` lines; `server/rag_evidence_service.py` is `159` lines.
- Verification:
  - `py_compile server\rag_evidence_service.py server\app_server.py memory\rag_benchmark.py memory\rag_quality.py` -> passed.
  - `tests\test_rag_evidence_service.py tests\test_rag_performance.py tests\test_runtime_contract.py` -> `16 passed`.
  - AppServer readiness/evidence focused suite -> `2 passed`.
  - AppServer quickstart/handoff/evidence focused suite -> `3 passed`.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: production semantic recall quality is still unproven without a real labelled corpus and local production embedding artifact.
- Next: add the corpus/artifact, continue AppServer route dispatch splitting, or run GUI smoke for Workbench controls.

## 2026-06-27 10:01 Agent Bootstrap API Extraction

- Status: verified.
- Completed: `server/agent_bootstrap_api.py` now owns external Agent onboarding, handoff, quickstart, and Maker briefing payload assembly.
- Completed: `server/app_server.py` delegates `/agent/onboarding`, `/agent/onboarding.md`, `/agent/handoff`, `/agent/quickstart`, `/agent/quickstart.md`, and `/agent/maker-briefing` payload construction while retaining HTTP transport concerns.
- Added tests: `tests/test_agent_bootstrap_api.py` covers service-level handoff/quickstart construction from persisted context sync, runtime metrics, LLM probe history, skill summary, Codex surface selection, and session existence checks.
- Measured: `server/app_server.py` is `1838` lines; `server/agent_bootstrap_api.py` is `122` lines.
- Verification:
  - `py_compile server\agent_bootstrap_api.py server\app_server.py server\evidence_bundle.py` -> passed.
  - `tests\test_agent_bootstrap_api.py tests\test_session_api.py tests\test_runtime_contract.py` -> `11 passed`.
  - AppServer quickstart/handoff/maker-briefing/evidence focused suite -> `4 passed`.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- POST-mem touch: `docs/memory-index.md` [edited].
- POST-sync touch: `docs/sprint-board.md` [edited].
- Health touch: `docs/memory-health.md` [edited].
- Roadmap touch: `docs/architecture/architecture-control-roadmap-2026-06-27.md` [edited].
- Boundary: HTTP behavior is preserved and payload assembly is more testable. Full route dispatcher extraction, GUI smoke, production embedding proof, and warm/hot resume proof remain pending.
- Next: continue AppServer route dispatch extraction, add the real corpus/artifact, or run GUI smoke for Workbench controls.

## 2026-06-27 10:55 Release Stability Verification

- Status: verified.
- Completed: release-blocking Python failures were fixed by isolating AppServer smoke tests from the default GUI port, applying explicit provider overrides through active-profile config, tracking/joining background session threads on AppServer shutdown, using full-suite-safe integration timeouts, and making fake FAISS rank by dot-product similarity.
- Verification:
  - Python full suite: `732 passed, 14 skipped`.
  - Frontend build: passed.
  - Electron build: passed with Vite CJS deprecation warnings only.
  - Tauri/Rust tests: `34 passed`, warnings only.
  - `git diff --check`: passed with existing LF/CRLF warnings only.
- Boundary: automated release verification is green. Visible launcher GUI smoke, Maker remote build, installer/package generation, and production embedding semantic-quality proof are still not claimed.
- Next: run visible GUI smoke from the launcher and prepare a release checkpoint if clean.

## 2026-06-27 12:24 Visible GUI Release Smoke

- Status: verified.
- Completed: refreshed current Tauri release exe with `cargo build --release --manifest-path src-tauri\Cargo.toml`, launched through `TTMEvolve.vbs`, and verified one visible `TTMEvolve` Tauri window.
- Completed: runtime smoke passed through `/health`, `/runtime/portable`, `/runtime/readiness`, `/llm/probe`, `/maker/setup-status`, and `/maker/tool-audit`.
- Completed: MiniMax API call proof observed `/text/chatcompletion_v2` with HTTP 200; Maker MCP was connected with 10 tools; portable runtime had no Windows user-dir leaks.
- Completed: child-window enumeration showed both visible shell `TTMEvolve` WebView and visible `TapTap 制造` Maker preview WebView.
- Completed: GUI close cleanup left no `ttmevolve.exe`, no embedded backend process, and no listening `7345` port.
- Verification: `tests\test_start_scripts.py tests\test_tauri_lifecycle.py` -> `28 passed`.
- Boundary: visible launcher/runtime smoke is verified. Maker remote build smoke, installer/package generation, signing, and production embedding semantic-quality proof remain outside this smoke.
- Next: run Maker remote build smoke if release criteria require remote authority proof; otherwise create the release checkpoint/package.

## 2026-06-27 14:33 Release Push Stabilization

- Status: verified.
- Fixed: async learning layer test now waits up to 30 seconds for background completion under full-suite load while still proving `agent.run()` returns quickly.
- Fixed: RAG benchmark release test now uses a full-suite-safe first-recall budget; warm recall p95 and hit-rate budgets still guard regressions.
- Cleaned: portable cache cleanup removed about 410MB of generated state and preserved `portable/home/.taptap-maker`.
- Packaged: rebuilt the source release checkpoint zip and manifest with 404 files, SHA-256 `7e575a0a71c41b4e5e010b1b23793f1280d9a5b4d5eccf8acdffd7652123ddcc`, and no forbidden archive entries.
- Verification:
  - Focused failed tests -> `2 passed`.
  - Full Python suite -> `748 passed, 14 skipped`.
  - Frontend build -> passed.
  - Electron build -> passed with Vite CJS deprecation warnings only.
  - Tauri/Rust tests -> `34 passed`, warnings only.
  - Package/readiness tests -> `8 passed`.
  - Source readiness -> `ready`.
  - Full-offline readiness -> `partial`; offline runtime bundle is `ready`, but signed installer, Maker remote build smoke, and production RAG semantic quality remain unproven.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: ready to push a stable source checkpoint to GitHub. Do not market this as a fully signed/offline commercial installer until the remaining external gates are proven.
- Next: commit and push verified source checkpoint.
