# TTMEvolve 记忆索引

## 项目信息

- **名称**: TTMEvolve
- **路径**: `D:/CC/TTMEvolve`
- **目标**: 自进化 TapMaker 开发 Agent，兼容主流 Agent 生态
- **版本**: v0.4.5-one-click-practice-entry+gui-chat-readable
- **创建**: 2026-06-13
- **最后更新**: 2026-06-19

## 架构决策

### 三层架构

1. **Agent 层**: ReAct 推理循环 + ToolRegistry + MCP 客户端
2. **核心运转层**: HealthMonitor + Executor（Shield）+ RepairScheduler + VersionManager + EventLog + Sandbox + ApprovalEngine + ResourceRegistry + EvolutionProtocol
3. **学习转化层**: TrajectoryCollector + ReflectionEngine + SkillGenerator + KnowledgeBase + SkillValidator

### 新增关键能力

- **默认本地模型**: MiniCPM5-1B-Q4_K_M-GGUF
- **上下文压缩与 KV Cache**: `llm/context_budget.py` 统一管理 token 预算；`memory/manager.py` 编排 ReAct 实时上下文并注入 AGENTS.md 向量检索结果；`LocalLLM` 修复 system KV cache 复用并返回 budget stats；`HealthMonitor` 接收真实 `token_usage_ratio` / `context_window_ratio`。
- **AGENTS.md 向量索引**: `memory/vector_index.py` + `memory/agents_md_index.py` + `memory/agents_md_parser.py` 实现项目规范文件的语义检索与动态工具提取；`agent/agent.py` 启动时自动注册动态工具。
- **向量记忆系统**: `memory/vector_index.py` 已作为统一后端接入 `memory/cold.py` 与 `learning/knowledge_base.py`，沉淀的 session summary / 知识规则均支持语义检索；`MemoryManager.prepare_think_payload()` 把冷记忆召回结果作为【历史归档】注入 ReAct 上下文。
- **沙箱**: `read-only` / `workspace-write` / `danger-full-access`
- **审批策略**: `on-request` / `never` / `always`
- **配置 Profile**: `default` / `safe` / `autonomous`
- **桌面级服务**: App Server (HTTP + SSE)，CLI 为薄客户端
- **桌面 GUI**: Electron + React + Vite，左侧聊天 + 右侧 IDE（文件树 / Monaco 编辑器 / Markdown·HTML·图片预览），左侧支持 Explorer / Assets 素材库切换，右侧预览区新增内嵌 Chromium 浏览器模式
  - 新增 `start-gui.bat` / `start-gui.ps1`：一键启动 Electron 桌面窗口；`start.bat --gui` 也可打开 GUI
  - React IDE 已消费后端 SSE 全部事件类型，实时渲染 ReAct 时间线卡片（`thought`/`action`/`tool_call`/`observation`/`output`/`status`/`error`）
  - 审批闭环：前端弹窗 → `POST /sessions/{id}/approve` → `ApprovalBridge` 唤醒工作线程
  - 文件树自动刷新：Agent 成功写入/删除文件后触发 `refreshKey`
- **浏览器服务**: `server/browser_service.py` 通过 Playwright 管理单例 Chromium，持久化 `storage/browser_profile`，Agent 与前端共享同一实例
- **浏览器端点**: `/browser/info`、`/browser/screenshot`、`/browser/logs`、`/browser/navigate`、`/browser/refresh`、`/browser/evaluate`、`/browser/click`
- **Agent 浏览器工具**: `browser_navigate`、`browser_click`、`browser_evaluate`、`browser_screenshot`
- **Tool-call JSON Schema 校验 + 本地修复**: `agent/tool_validator.py` 轻量校验工具参数（type/required/properties/items/enum 等）；`agent/react_loop.py` 在动作执行前校验，失败时不执行工具，而是把错误注入上下文让 LLM 下一轮自修复，降低本地小模型畸形输出导致的不必要专家救援。
- **SQLite 会话持久化 + 事件回放**: `server/session_store.py` 将会话元数据与全部 SSE 事件持久化到 SQLite；UI 刷新/重连 `/sessions/{id}/events` 时先回放历史事件再进入实时流；新增 `GET /sessions` 与 `GET /sessions/{id}` 端点。服务端重启后可查看已完成会话历史（暂不恢复中断中的执行状态）。
- **素材库端点**: `/fs/assets` 扫描项目媒体文件，`/fs/stat` 返回文件元数据，`/preview/file` 扩展支持 audio/video/webp/ogg/mkv 等格式
- **IDE 文件端点**: `/fs/list`、`/fs/read`、`/fs/write`、`/fs/delete`、`/preview/file`，复用 `Sandbox` 路径校验
- **自进化协议**: propose → validate → deploy → rollback
- **Hook 系统**: `user_prompt` / `pre_action` / `post_action`
- **跨生态兼容**: Hermes / OpenClaw / Claude Code / Codex

### 关键约束

- Agent 层没有直接执行权限，所有动作经 Executor + Sandbox + Approval 验证。
- 修改文件前自动打版本快照。
- 事件日志只追加，Agent 层不可修改。
- 高风险修改（agent_code / config_profile）默认需要人类确认。
- 所有自我修改必须通过 EvolutionProtocol 走验证门。

## 文件索引

| 文件 | 用途 |
|------|------|
| `docs/roadmap-v0.4.md` | v0.4 整合路线图 |
| `package.json` | Node.js workspace 脚本 |
| `frontend/` | Electron 渲染进程（React + Vite） |
| `frontend/src/hooks/useBackend.ts` | React IDE SSE 流处理 + 审批状态管理 |
| `frontend/src/components/ChatPanel.tsx` | 聊天面板 + 审批模态框 |
| `frontend/src/components/ChatMessage.tsx` | ReAct 事件时间线卡片渲染 |
| `frontend/src/styles/index.css` | Agent 事件卡片与模态框样式 |
| `frontend/src/components/IdeLayout.tsx` | IDE 三栏布局容器 + Explorer/Assets 切换 |
| `frontend/src/components/FileTree.tsx` | 文件树组件 |
| `frontend/src/components/AssetLibrary.tsx` | 素材库网格组件 |
| `frontend/src/components/EditorTabs.tsx` | Monaco 编辑器 + 标签页 |
| `frontend/src/components/PreviewPane.tsx` | 文件/URL/音视频/浏览器预览面板 |
| `frontend/src/components/BrowserPreview.tsx` | 内嵌 Chromium 浏览器预览组件 |
| `frontend/src/hooks/useFs.ts` | 文件系统 API hook |
| `frontend/src/hooks/useAssets.ts` | 素材库 API hook |
| `frontend/src/hooks/useBrowser.ts` | 浏览器控制 API hook |
| `frontend/src/App.tsx` | 顶层布局（聊天 + IDE） |
| `frontend/src/styles/index.css` | 全局样式 |
| `electron/` | Electron 主进程与 preload |
| `server/electron_entry.py` | Electron 启动 Python 后端入口 |
| `main.py` | CLI 薄客户端 |
| `start.bat` | 一键启动脚本（CLI） |
| `start-gui.bat` / `start-gui.ps1` | 一键启动 Electron 桌面 GUI |
| `server/app_server.py` | 桌面级 HTTP/SSE 服务（会话持久化 + 事件回放） |
| `server/ide_service.py` | IDE 文件系统服务（list/read/write/delete/preview） |
| `server/browser_service.py` | Playwright Chromium 浏览器服务 |
| `server/protocol.py` | App Server 协议定义 |
| `server/session_store.py` | SQLite 会话与事件持久化 |
| `agent/agent.py` | 顶层 Agent 组装 |
| `agent/react_loop.py` | ReAct 循环（事件流化 + 校验失败本地修复） |
| `agent/tool_registry.py` | 工具注册表（含 function schema + validate_action） |
| `agent/tool_validator.py` | 轻量级 tool-call JSON Schema 校验器 |
| `agent/mcp_client.py` | 通用 MCP stdio 客户端 |
| `agent/config.py` | 配置加载（支持 profile） |
| `core/health.py` | 健康状态 |
| `core/executor.py` | 执行网关/Shield |
| `core/sandbox.py` | Codex 式沙箱 |
| `core/approval.py` | 审批策略引擎 |
| `core/config_profiles.py` | 配置 profile |
| `core/resource_registry.py` | 可进化资源注册表 |
| `core/evolution_protocol.py` | 自进化协议层 |
| `core/hooks.py` | 声明式 Hook 系统 |
| `core/harness.py` | 统一 Harness 入口 |
| `core/project_context.py` | 项目上下文聚合 |
| `core/repair.py` | 修复调度器 |
| `core/version_manager.py` | 版本快照/回滚 |
| `core/event_log.py` | 不可变事件日志 |
| `core/config.py` | 配置加载（已从 agent 下沉） |
| `core/rescue_telemetry.py` | 救援遥测数据结构 |
| `cli/harness.py` | 统一 Agent 执行 Harness |
| `ecosystem/project_context.py` | 多生态项目上下文发现 |
| `agent/builtin_tools.py` | 内置工具注册 |
| `agent/mcp_integration.py` | Maker MCP 连接与工具同步 |
| `llm/local_llm.py` | 本地 GGUF 模型（KV cache / 性能日志） |
| `llm/utils.py` | LLM JSON / DSML tool_calls 解析 |
| `scripts/build_embedded.py` | 收集内嵌运行环境 |
| `scripts/setup_embedded.py` | 在目标机器初始化内嵌环境 |
| `scripts/package_release.py` | 打包离线发布包 |
| `scripts/validate_offline.py` | 验证离线环境可用性 |
| `scripts/verify_offline.py` | 校验离线包完整性 |
| `start-embedded.bat` | 内嵌环境一键启动 |
| `electron/electron-builder.yml` | Electron 打包配置 |
| `learning/trajectory_collector.py` | 轨迹收集 |
| `learning/reflection.py` | 反思引擎 |
| `learning/skill_generator.py` | 技能生成（canonical 格式） |
| `learning/validator.py` | 技能验证门 |
| `learning/knowledge_base.py` | 知识库 |
| `memory/hot.py` | 工作记忆 |
| `memory/warm.py` | 温记忆 |
| `memory/cold.py` | 冷记忆/归档 |
| `memory/manager.py` | 记忆协调器 + ReAct 实时上下文编排 |
| `memory/vector_index.py` | FAISS + sentence-transformers 向量索引 |
| `memory/agents_md_index.py` | AGENTS.md 向量索引与动态工具规范提取 |
| `memory/agents_md_parser.py` | markdown 分块与 Tool 规范解析 |
| `llm/interface.py` | LLM 接口 |
| `llm/context_budget.py` | Token 预算与上下文截断策略 |
| `llm/local_llm.py` | MiniCPM5-1B 本地实现（含 KV cache 复用） |
| `llm/llm_factory.py` | LLM 工厂 |
| `llm/claude_llm.py` | Claude 实现 |
| `llm/mock_llm.py` | Mock 实现 |
| `ecosystem/skill_schema.py` | Canonical skill 格式 |
| `ecosystem/hermes_adapter.py` | Hermes 适配器 |
| `ecosystem/openclaw_adapter.py` | OpenClaw 适配器 |
| `ecosystem/claude_code_adapter.py` | Claude Code 适配器 |
| `ecosystem/codex_adapter.py` | Codex 适配器 |
| `scripts/import_mcp_config.py` | 导入外部 MCP 配置 |
| `scripts/export_skills.py` | 导出 skills 到各生态 |

## 测试索引

| 测试 | 覆盖 |
|------|------|
| `tests/test_rescue_trigger.py` | 救援触发器信号 |
| `tests/test_expert_protocol.py` | 专家救援协议解析 |
| `tests/test_rescue_loop.py` | 救援闭环流程 |
| `tests/test_rescue_benchmark.py` | 真实任务救援闭环实测 |
| `tests/helpers/degraded_mock_llm.py` | 故意失败的 Mock LLM |
| `tests/helpers/always_failing_mock_llm.py` | 每步失败的 Mock LLM |
| `tests/helpers/scripted_expert_llm.py` | 预设脚本的专家 LLM |
| `tests/benchmark_tasks/seasonal_festival_task.json` | 季度祭典 benchmark 任务定义 |
| `tests/test_sandbox.py` | 沙箱校验 |
| `tests/test_approval.py` | 审批策略 |
| `tests/test_resource_registry.py` | 资源注册/回滚 |
| `tests/test_evolution_protocol.py` | 进化协议闭环 |
| `tests/test_skill_generation.py` | 技能生成链路 |
| `tests/test_cross_ecosystem.py` | 跨生态 skill 导出/导入 |
| `tests/test_app_server.py` | App Server 端点 |
| `tests/test_ide_endpoints.py` | IDE 文件系统端点 |
| `tests/test_asset_endpoints.py` | 素材库端点 / 媒体预览 MIME |
| `tests/test_browser_service.py` | Playwright Chromium 浏览器服务 |
| `tests/test_browser_endpoints.py` | `/browser/*` HTTP 端点 |
| `tests/test_local_llm.py` | 本地模型与 KV cache mock 测试 |
| `tests/test_context_budget.py` | Token 预算管理 |
| `tests/test_hot_memory.py` | HotMemory 摘要压缩 |
| `tests/test_memory_manager.py` | 记忆管理器上下文编排 |
| `tests/test_vector_index.py` | 向量索引（FAISS/mock/keyword fallback） |
| `tests/test_agents_md_parser.py` | AGENTS.md 分块与工具规范解析 |
| `tests/test_agents_md_index.py` | AGENTS.md 向量索引与上下文注入 |
| `tests/test_dynamic_tools_from_agents_md.py` | AGENTS.md 动态工具注册 |
| `tests/test_tool_call_validation.py` | tool-call JSON Schema 校验与本地修复 |
| `tests/test_session_store.py` | SQLite 会话持久化单元测试 |
| `tests/test_app_server_resume.py` | App Server 会话重连与事件回放 |

## 任务状态（v0.4 路线图）

| 阶段 | 任务 | 状态 |
|---|---|---|
| Phase 1 | Electron + Python 后端骨架 | ✅ 已完成 |
| Phase 2 | LLM KV Cache 与上下文压缩 | ✅ 已完成 |
| Phase 3 | AGENTS.md 向量索引与动态工具 | ✅ 已完成 |
| Phase 4 | 向量记忆系统（M2） | ✅ 已完成 |
| Phase 5 | IDE 界面（文件树/编辑器/预览） | ✅ 已完成 |
| Phase 6 | 素材库与图片/音频/视频预览 | ✅ 已完成 |
| Phase 7 | 内嵌浏览器与 Playwright CDP | ✅ 已完成 |
| Phase 8 | 专家救援闭环实测 | ✅ 已完成 |
| Phase 9 | 真实 TapTapMaker 游戏功能开发 | ⏭️ 跳过 |
| Phase 10 | 结构优化 + 本地模型性能优化 + 全运行环境内嵌 | ✅ 已完成 |
| Phase 11 | 跨平台内嵌（macOS / Linux portable） | ⏳ 待开始 |

## 下一步

1. ✅ Phase 6：素材库与图片/音频/视频预览。
2. ✅ Phase 7：内嵌 Chromium + Playwright CDP。
3. ✅ Phase 8：专家救援闭环实测。
4. ✅ Phase 10：结构优化、本地模型性能优化、全运行环境内嵌。
5. Phase 11：跨平台内嵌（macOS / Linux portable）。
6. 递归 Meta-Agent（改进改进机制本身）。
## 2026-06-22 Layout And Runtime Reality Check

- User remains dissatisfied with current GUI/agent maturity and asked whether to refactor from the bottom up after studying Claude Code, Codex, opencode, Cursor, Reasonix, and agent IDE patterns.
- Concrete usability gap fixed this turn: Agent sidebar, file/assets panel, and preview panel now support draggable split panes, collapsible rails, and persistent layout state in localStorage.
- GUI now polls `/health` and surfaces local runtime/model status in the top cockpit header instead of requiring manual log inspection.
- Evidence from `logs/gui/start-gui-20260622-145234.log`: `.venv` Python 3.12.10 starts, bootstrap finds `models/MiniCPM5-1B-Q4_K_M.gguf`, llama.cpp reports `Loading weights: 100%`, and `llama_context` is created. Local model startup is real; agent quality problems are workflow/action reliability problems, not simply "model never packaged."
- Correction from later verification: `Loading weights: 199/199` during startup can be embedding/model-adjacent loading, not proof that llama.cpp generation ran. Reliable local LLM signals are `/health.llm_loaded` and `/health.last_call_stats`, plus `llama_context` after an actual generation call.
- Local LLM smoke via GUI API generated with `n_ctx=8192`, `n_batch=1024`, `n_threads=6`, `kv_cache=false`: 2685 prompt tokens, 2 completion tokens, ~15.8s, ~0.13 tok/s. The model runs, but local path is not practically usable until prompt weight and action selection are reduced.
- Disabled unsafe LocalLLM KV cache by default because the previous implementation could save post-generation state and contaminate later turns.
- New architecture doc: `docs/architecture/agent-ide-redesign.md`. Current verdict: Electron shell is acceptable, Maker MCP-first is correct, but runtime must move from raw ReAct feed to structured agent workbench with health, plan, tool timeline, diff/review, verification, and debug drawer.
- Next best step: implement AgentWorkbench state normalization, constrained local action JSON, and a lightweight local prompt path.

## 2026-06-22 llama.cpp Tuning Update

- Added `llm/llama_tuning.py` to resolve llama.cpp params adaptively instead of using magic config values.
- Current machine resolves to CPU-only: `logical_cpus=12`, `gpu_offload=unavailable`, `n_gpu_layers=0`, `offload_kqv=false`, `n_threads=6`, `n_threads_batch=12`, `n_batch=1024`, `n_ubatch=512`.
- `/health.llm_params` now reports actual resolved runtime params plus notes.
- Config now uses `n_gpu_layers: "auto"` and explicit `n_threads_batch` / `n_ubatch`.
- Remaining bottleneck is prompt/runtime design, not only llama.cpp parameters.

## 2026-06-22 API-first LLM Runtime Refactor

- Architecture direction changed: API LLMs are now the primary agent runtime. Local GGUF remains available as explicit `local` experimental fallback, not the default brain.
- Built-in presets live in `llm/provider_presets.py`: DeepSeek, OpenAI, OpenRouter, DashScope/Qwen, Zhipu GLM, Moonshot/Kimi, SiliconFlow, MiniMax, Claude, and Local GGUF.
- GUI provider settings are real now: `frontend/src/components/ProviderSelector.tsx` saves provider/model/base URL/API key through `POST /config/llm`; `useBackend.ts` sends overrides with `POST /sessions`.
- Backend runtime switching is real now: `server/app_server.py` applies session/config overrides and `agent/agent.py:set_llm()` updates every component holding an LLM reference.
- API keys are provider-scoped via `llm.api_keys`; switching providers without a matching key enters `UnconfiguredLLM` instead of reusing a stale key.
- `UnconfiguredLLM` is not mock fallback. It only allows the desktop GUI to boot and then fails task execution with a clear configuration error.
- API clients no longer require optional SDK packages or `requests`; `OpenAILLM` and `ClaudeLLM` use Python standard library HTTP and expose `last_call_stats()` for token meter events.
- New doc: `docs/architecture/api-first-llm-runtime.md`.
- Verified with `npm.cmd run build`, bundled Python `py_compile`, and provider-key isolation smoke test.
- Next step: real GUI run with a chosen API key/provider, then redesign the agent workbench flow beyond raw ReAct transcript.
- Follow-up: added `POST /llm/models` and GUI model dropdown/refresh. Model ids should be auto-discovered where possible and backed by provider-specific hints where online discovery is unavailable.

## 2026-06-22 Full Runtime Review And Roadmap

- User asked for full code review, performance optimization, architecture uplift, and a development roadmap.
- Principal contradiction identified: reliable, deterministic Agent workbench behavior matters more than further local GGUF parameter tuning.
- Fixed immediate runtime hazards:
  - `LLMFactory` explicitly supports `mock` again for tests/offline development.
  - `AppServer.run_session()` serializes the shared `TapMakerAgent` with `_run_lock` to prevent provider/event/approval callback contamination.
  - Session LLM reconfiguration now only happens when a session explicitly sends provider/model/base URL/API key overrides.
  - Unconfigured provider failures now persist session status as `error` and emit terminal `status.done`.
  - Frontend `useBackend.ts` treats recoverable ReAct `error` events as timeline feedback instead of closing SSE.
  - `SessionStore` now uses SQLite foreign keys, busy timeout, WAL, and normal synchronous mode.
  - Static file serving uses `Path.relative_to()` boundary checks; SSE/client disconnect log noise is suppressed.
- Added docs:
  - `docs/architecture/code-review-roadmap-2026-06-22.md`
  - `docs/architecture/adr-0001-serialize-shared-agent-runtime.md`
- Verification passed:
  - Bundled Python `py_compile` for changed backend modules.
  - `npm.cmd --prefix frontend run build`.
  - `tests/test_gui_flow.py` script.
  - Direct function runs for `tests/test_session_store.py` and `tests/test_app_server_resume.py`.
- Environment notes:
  - Project `.venv` and bare `python` are currently unreliable in this Codex shell; bundled Python worked.
  - Root `npm run build:frontend` can miss nested Vite on Windows; `npm --prefix frontend run build` works.
- Next best step: extract per-session `AgentRuntime`, then implement `AgentWorkbenchState` normalization and constrained action JSON.

## 2026-06-22 Session-Scoped Runtime Upgrade

- Continued from the review roadmap and replaced the temporary `AppServer._run_lock` serialization approach.
- `run_session()` now creates a session-scoped `TapMakerAgent` per task. The base AppServer agent remains the control-plane owner for health/config/tools/IDE/shared MCP.
- Added `Config.clone()` so session provider overrides are isolated from global GUI config.
- Added `MCPIntegration.attach()` so session agents reuse the shared Maker MCP client and do not spawn a new Maker MCP process.
- `TapMakerAgent` now accepts `connect_mcp` and `shared_mcp_integration`; `close()` only stops MCP when the agent owns it.
- Added `docs/architecture/adr-0002-session-scoped-agent-runtime.md`; ADR-0001 is now superseded.
- Added `test_app_server_runs_sessions_without_shared_runtime_queue()` to prevent regression to queued shared-Agent execution.
- Verification passed: Python compile, `tests/test_gui_flow.py`, `tests/test_mcp_client.py`, `tests/test_app_server.py`, direct function runs for app server resume/session store, and `npm.cmd --prefix frontend run build`.
- Next best step: implement `AgentWorkbenchState` in the frontend, then add constrained action JSON in `agent/react_loop.py`.

## 2026-06-22 AgentWorkbenchState Frontend Normalization

- Added a structured `AgentWorkbenchState` in `frontend/src/hooks/useBackend.ts` while preserving the raw event timeline.
- New state tracks `stage`, `currentStatus`, `currentThought`, `currentTool`, `toolRuns`, `lastError`, `finalOutput`, and `iteration`.
- Added `frontend/src/components/AgentWorkbench.tsx` and rendered it in `ChatPanel` above chat messages.
- Added compact workbench styling in `frontend/src/styles/index.css`.
- Verification passed: `npm.cmd --prefix frontend run build` and `tests/test_gui_flow.py`.
- Next best step: implement constrained action JSON and tool subset ranking to reduce action parse failures and prompt bloat.

## 2026-06-22 Maker Cockpit Usability And Action Routing

- User reported seven concrete gaps: default preview, chat scrolling, static three-layer UI, file/assets rail, add-file button, queued input, latency/tool/Maker MCP/runtime architecture.
- GUI fixes landed: preview defaults to `https://maker.taptap.cn/`, chat remains usable and queues messages during active runs, file attach opens Electron native dialog, collapsed rail exposes `文档`/`素材`, scrollbars are visible for chat/file/assets panes.
- Workbench is now event-backed: backend emits `layer` events for Agent/Runtime/Learning and ReAct emits `tool_selection`; frontend stores them in `AgentWorkbenchState.layers`.
- Runtime prompt optimization landed: `ToolRegistry.rank_tools()` ranks/caps candidate tools; ReAct uses smaller tool subsets for think/action; OpenAI-compatible, Claude, and MiniMax action prompts use constrained JSON plus short repair fallback.
- Roadmap updated in `docs/architecture/code-review-roadmap-2026-06-22.md`.
- Verification passed: frontend build, Electron build, Python compile, GUI flow, tool validation direct run, app server resume direct run, MCP client direct run.
- Next best step: extract lean `SessionRunner`/`AgentRuntime`, then promote Maker MCP health/latency/retry diagnostics as a first-class UI/runtime surface.

## 2026-06-23 LLM-As-User Runtime Iteration

- Real LLM feedback loop now refreshes prompt facts after each implementation and rejects hallucinated/stale file paths.
- Added tool preflight with alternatives: `ToolRegistry.preflight_action()`, ReAct `tool_preflight` events, and Workbench display.
- Added lightweight plan validation: `core/plan_validation.py`, ReAct `plan_validation` events, trajectory/result summaries, and Workbench display.
- Added active context compression evidence: `BudgetStats.compression_applied/dropped_parts/truncated_chars`, context compression marker, high-priority task/tools retention, and important old trajectory step retention.
- Added persistent commit-state history query: `SessionStore.get_commit_history()`, `/sessions/{id}/commit-history`, and `/sessions/{id}/submissions`.
- Added cross-step acceptance tracking: `core/goal_tracking.py`, ReAct `goal_checklist` events/result, context hints, and AgentWorkbench display.
- Added cross-Agent skill sync status: `ecosystem/skill_sync.py`, `scripts/sync_skills.py`, `storage/skill_sync/manifest.json`, and read-only `/skills/sync-status`.
- Skill sync now detects version conflicts and same-version content fingerprint drift across canonical, Hermes, OpenClaw, Claude Code, and local Codex-style skill folders.
- Extended skill sync into shared runtime coordination: `storage/skill_sync/registry.json`, safe export plans, dynamic `skill_graph`, ReAct `skill_sync` events, generated-skill rediscovery on signature change, and compatibility warnings after `plan_validation`.
- Added Agent-callable `query_skills` over the dynamic skill graph, with filters for text, ecosystem, callability, and limit.
- Latest valid LLM feedback after these changes is no longer generic "missing skill sync"; next real directions are remote invocation semantics for discovered skills, external MCP broadcast to other processes, skill graph UI, feedback artifact/event metadata UI, or stronger Maker-specific acceptance criteria.

## 2026-06-23 Workbench Skill Graph UI And Context Sync

- AgentWorkbench now displays Skill Graph sync state, skill/action/conflict counts, and preview rows for conflicts/export actions.
- ReAct emits compact `context_sync` events at session start and after meaningful plan/observation/output changes.
- `context_sync` uses stable signatures to dedupe unchanged snapshots and carries revision, diff keys, last tool/action keys, plan verdict, goal checklist, commit summary, skill sync summary, and artifact refs.
- Artifact refs merge action params with observations so paths/ids remain visible even when tool observations are terse.
- Frontend `AgentWorkbenchState` consumes `context_sync` and exposes Runtime layer metrics for context revision, diff keys, and artifact count.
- Workbench thoughts no longer use fixed-height hidden overflow; full agent text should remain visible within the outer scroll area.
- Latest LLM feedback artifact: `docs/llm-feedback/llm-runtime-interview-20260623-074309.json`. MiniMax still timed out before headers at 8s; DeepSeek fallback returned stale generic skill-sync feedback with fictional Rust paths. Treat it as stale unless future feedback asks for external-process broadcast, remote invocation semantics, or distributed context sharing on top of the existing registry/context sync.

## 2026-06-23 Context Sync Pull API

- Added `SessionStore.get_context_sync_history(session_id, limit)` over persisted append-only session events.
- Added read-only `GET /sessions/{id}/context-sync?steps=N`, returning `context_sync`, `latest`, and `count`.
- This upgrades `context_sync` from UI/SSE-only telemetry into a pullable shared-context surface for external agents/processes.
- Verification passed: AppServer resume tests, tool-call validation tests, frontend build, and Python compile for changed server files.
- Latest LLM artifact: `docs/llm-feedback/llm-runtime-interview-20260623-075850.json`. MiniMax still timed out before headers at 8s; DeepSeek fallback again returned stale generic skill registry feedback with fictional Go paths. Treat generic "skill sync missing" as stale.

## 2026-06-23 Updated Goal And Feedback Actionability

- User updated the target:
  - Any LLM should quickly start coding in TTMEvolve and use MakerMCP naturally.
  - Agent/Core/Learning layers should run independently while communicating efficiently.
  - Token use should be highly optimized via context compression, tool retrieval, vector memory, and caching.
  - Frontend/backend should be fully connected.
  - UI should be modern, high-quality, and TapTapMaker-themed.
- `scripts/llm_runtime_interview.py` now produces actionability metadata:
  - `actionable=true/false`
  - `decision`
  - `actionable_blockers`
  - `next_feedback_prompt`
- Stale claims against completed mechanisms are rejected with `decision=reject_stale_feedback`.
- Fictional repository paths like non-existent `src/` or `internal/` are rejected with `decision=needs_repo_mapping`.
- Fallback selection now prefers actionable feedback and avoids replacing actionable feedback with stale `ok=true` JSON.
- Verification passed for `tests/test_llm_runtime_interview.py` and Python compile.
- Broader regression was limited by disk exhaustion (`WinError 112`) while temp memory index files were being written.
- External LLM feedback execution now needs explicit user approval because it sends TTMEvolve internal architecture/workflow data to third-party providers.

## 2026-06-23 Runtime Contract For LLM Onboarding

- Added `core/runtime_contract.py`.
- `TapMakerAgent.runtime_contract(session_id)` now builds a live compact contract from MakerMCP status and skill graph status.
- Added low-risk Agent tool `runtime_contract`.
- ReAct initial context now includes a capped `[runtime_contract]...[/runtime_contract]` block so any provider starts with the same MakerMCP/TTMEvolve operating rules.
- Added `GET /agent/runtime-contract?session_id=...` for frontend/external agent access.
- Contract covers:
  - MakerMCP readiness and top tools
  - remote identity diagnostics and warnings
  - Agent/Core/Learning layer ownership and emitted events
  - context-sync, commit-history, MCP, skills, and tools endpoints
  - token-efficiency rules and available mechanisms
- Verification passed: Python compile, `tests/test_runtime_contract.py`, and `tests/test_llm_runtime_interview.py`.
- Next useful step: display Runtime Contract readiness in Workbench/Cockpit and add MakerMCP first-action task templates/checklists.

## 2026-06-23 Runtime Contract Workbench Surface

- Frontend now fetches `GET /agent/runtime-contract?session_id=...` after session creation.
- `AgentWorkbenchState` includes `runtimeContract`.
- AgentWorkbench displays a Runtime Contract panel with:
  - MakerMCP readiness
  - Maker tool count
  - remote identity status
  - token rule count
  - top Maker tools
  - context-sync endpoint
  - runtime warnings
- Runtime layer metrics now include `contract_tools` and `contract_warnings`.
- Styling uses dense TapTapMaker-like mint/blue/orange states instead of large clipped cards.
- Verification passed: frontend build, Python compile, and `tests/test_runtime_contract.py`.
- Next useful step: add MakerMCP first-action checklist/task templates into Runtime Contract and Workbench.

## 2026-06-23 MakerMCP First-Action Checklist

- Runtime Contract now includes `maker_mcp.first_action_checklist` for arbitrary LLM onboarding.
- Checklist steps cover:
  - read Runtime Contract
  - check MakerMCP readiness
  - discover Maker authority tools
  - plan one verifiable Maker change
  - verify side effects through commit/context evidence
  - sync compact context
- Contract includes `warning_codes` so prompt-side consumers can detect `maker_mcp_disconnected`, `maker_remote_identity_incomplete`, and `skill_registry_needs_review` even when longer text is truncated.
- `render_runtime_contract_for_llm()` now puts warning codes near the front and compacts checklist rows to `id/status/evidence`.
- AgentWorkbench displays checklist rows and warning codes with dense TapTapMaker-like styling and no fixed-height clipping.
- Runtime layer metrics include `contract_warning_codes`, `maker_checklist_ready`, and `maker_checklist_warn`.
- Verification passed:
  - Python compile for Runtime Contract tests
  - `tests/test_runtime_contract.py`
  - `npm.cmd --prefix frontend run build`
- Next useful step: convert checklist into Maker-specific task templates/acceptance criteria and expose the contract/context surfaces for external Claude Code/Codex/opencode-style agents.

## 2026-06-23 Maker Task Templates And External Agent Attach Contract

- Runtime Contract now includes `maker_mcp.task_templates`.
- Templates:
  - `maker_inspect_project`
  - `maker_plan_small_change`
  - `maker_execute_and_verify`
  - `maker_build_or_submit`
  - `external_agent_handoff`
- Each template carries status, authority surfaces, concrete steps, acceptance criteria, token strategy, and suggested tools.
- Template status is derived from MakerMCP connectivity, discovered tools, and remote identity lookup availability.
- Runtime Contract now includes `external_agents`:
  - compatible surfaces: Claude Code, Codex, opencode, OpenClaw, Hermes-style agents
  - attach sequence: runtime contract, context sync, MCP status/tools, then skill graph only when relevant
  - handoff rule: use runtime contract + context_sync instead of replaying raw SSE
- Prompt renderer was tuned for token efficiency:
  - communication endpoints moved near the front
  - LLM prompt task templates are compact `id/status/suggested_tools`
  - top tools are compact `name/params`, not long descriptions
- AgentWorkbench displays Maker task templates and adds Runtime metrics:
  - `maker_templates`
  - `maker_templates_warn`
- Verification passed:
  - Python compile for Runtime Contract tests
  - `tests/test_runtime_contract.py`
  - `npm.cmd --prefix frontend run build`
  - prompt-size smoke with 30 Maker tools under a 900-char cap
- Next useful step: seed `goal_checklist` from Maker task template acceptance criteria and add a compact external-agent handoff endpoint/bundle.

## 2026-06-23 Maker Template Goal Seeds And Handoff Bundle

- Maker task template acceptance criteria now seed live `goal_checklist` entries.
- `core/goal_tracking.py` now accepts `maker_templates` in `derive_goal_checklist()` and `update_goal_checklist()`.
- Seeded Maker criteria include:
  - `source=maker_template`
  - `template_id`
  - original acceptance criterion label
  - runtime evidence such as `runtime_contract`
- Template applicability:
  - Maker inspect + plan for Maker-related tasks
  - execute/verify for side-effect Maker tasks
  - build/submit for build/submit/publish tasks
  - external handoff for Claude/Codex/opencode/agent handoff tasks
- ReAct now:
  - loads Runtime Contract at session start
  - extracts `maker_mcp.task_templates`
  - seeds initial `goal_checklist`
  - preserves Maker template criteria during checklist refresh
- Added `GET /agent/handoff?session_id=...&steps=N`.
  - Returns runtime contract, context_sync history/latest snapshot, skill summary, attach sequence, and token rule.
  - Runtime Contract communication now exposes `handoff_bundle`.
  - External-agent attach sequence starts with the handoff bundle.
- Compact LLM rendering now prioritizes `external_agent_handoff` and omits empty suggested-tool fields.
- Verification passed:
  - Python compile for runtime/API/tests
  - `tests/test_goal_tracking.py`
  - `tests/test_runtime_contract.py`
  - focused `test_app_server_external_agent_handoff_endpoint`
- Next useful step: surface Maker-template checklist source/template IDs in AgentWorkbench and add a small external-agent handoff panel or copy surface.

## 2026-06-23 Workbench Maker Acceptance Visibility

- AgentWorkbench now exposes Maker-template acceptance criteria instead of hiding them behind generic checklist rows.
- `WorkbenchGoalCriterion` includes:
  - `source`
  - `template_id`
- `goal_checklist` SSE handling no longer truncates criteria to the first six entries.
- Agent layer metrics now include `maker_goal_templates`.
- Acceptance panel shows:
  - Maker flow count
  - dedicated Maker-template row styling
  - template id
  - evidence or next check
- Styling remains dense and non-clipped; rows wrap inside the Workbench scroll area.
- Verification passed:
  - `npm.cmd --prefix frontend run build`
  - `tests/test_goal_tracking.py`
  - `tests/test_runtime_contract.py`
- Next useful step: add a UI handoff surface for `/agent/handoff`, including a copyable endpoint and compact attach sequence.

## 2026-06-23 Workbench External Agent Handoff Surface

- Runtime Contract panel now includes an `Agent Handoff` block.
- It displays:
  - full local handoff URL from `communication.handoff_bundle`
  - first three attach sequence steps
  - copy button for the URL
  - copied/error button feedback
- Handoff URL uses `http://127.0.0.1:7345` plus the contract path.
- Styling is compact, TapTapMaker-like, and non-clipped.
- Verification passed:
  - `npm.cmd --prefix frontend run build`
  - focused `test_app_server_external_agent_handoff_endpoint`
  - `tests/test_runtime_contract.py`
- Next useful step: optionally fetch and preview `/agent/handoff` live in a collapsible drawer, but keep the copyable Runtime Contract block as the fast path.

## 2026-06-23 Live Handoff Bundle Preview

- Workbench `Agent Handoff` block now has Preview/Refresh behavior.
- Preview fetches `/agent/handoff` on demand only.
- Preview displays compact summaries:
  - latest context revision
  - task
  - last tool
  - plan verdict
  - goal state
  - artifact count
  - skill registry state
  - skill count
  - conflict count
  - token rule
- The full handoff bundle remains available through the copied endpoint; Workbench does not render large raw JSON.
- Styling remains dense, TapTapMaker-like, and non-clipped.
- Verification passed:
  - `npm.cmd --prefix frontend run build`
  - focused `test_app_server_external_agent_handoff_endpoint`
  - `tests/test_runtime_contract.py`
- Next useful step: turn back to token/cache/tool retrieval improvements, especially making ranked tool/context retrieval more observable and cache-aware for arbitrary LLM sessions.

## 2026-06-23 Cache-Aware Retrieval Metrics

- `ToolRegistry.rank_tools()` now has a small deterministic cache and exposes `last_rank_stats()` with candidate count, selected count, ranking latency, cache hit, and cache size.
- ReAct `tool_selection` events carry ranking stats, and a new compact `context_budget` event carries token/context fit stats without adding rows to the main chat.
- `ContextBudgetManager` tracks token estimation cache hits/misses/cache size.
- `MemoryManager.prepare_think_payload()` reports AGENTS.md hits, cold recall hits, retrieval timings, and context build time through `BudgetStats`.
- Agent Runtime audit metrics now preserve cache/retrieval stats after the run finishes.
- AgentWorkbench Runtime layer displays tool ranking, token cache, AGENTS/cold recall, and context build metrics.
- Verification passed: Python compile for changed runtime files, `tests/test_context_budget.py`, `tests/test_memory_manager.py`, `tests/test_tool_call_validation.py`, and `npm.cmd --prefix frontend run build`.
- Next useful step: run a real API-backed GUI task and use these metrics to target the remaining latency instead of guessing.

## 2026-06-23 Pullable Runtime Metrics API

- Added `SessionStore.get_runtime_metrics_history(session_id, limit)` to compact persisted `latency`, `llm_usage`, `tool_selection`, and `context_budget` events.
- Added `GET /sessions/{id}/runtime-metrics?steps=N`.
- Response includes `runtime_metrics`, `latest`, `count`, and `summary`:
  - total LLM tokens
  - max latency
  - token cache hits/misses/size
  - AGENTS.md/cold recall/context build stats
  - latest tool ranking candidate/selected/cache state
- Runtime Contract now exposes `communication.runtime_metrics` and tells external agents to fetch it when diagnosing latency/token cost.
- `/agent/handoff` includes `runtime_metrics_summary`.
- AgentWorkbench Runtime Contract panel displays the endpoint, and handoff preview displays a compact Runtime summary.
- Cleaned the unreachable mojibake block from `tests/test_tool_call_validation.py`.
- Verification passed: Python compile for changed runtime/API/tests, `tests/test_runtime_contract.py`, `tests/test_tool_call_validation.py`, `tests/test_app_server_resume.py`, and `npm.cmd --prefix frontend run build`.
- Next useful step: run a real API-backed GUI task and use runtime metrics to decide whether to optimize provider routing, prompt size, tool execution, or async learning/repair.

## 2026-06-23 Async Learning Layer And Event Bridge

- Added `TapMakerAgent.event_sink` so Agent-level `layer` events reach AppServer, SSE, and SessionStore instead of only `agent.get_events()`.
- AppServer now sets `session_agent.event_sink = session.emit` during each run and restores it afterward.
- Replaced synchronous post-run learning with learning jobs:
  - `queued`
  - `running`
  - `done`
  - `error`
  - `skipped`
- Eligible learning defaults to async through `learning.async_enabled` (default true), so `agent.run()` can return after Runtime audit while reflection continues in the background.
- Short/ineligible runs emit `learning.reflection.skipped`.
- Added `TapMakerAgent.get_learning_job()` and `list_learning_jobs()` for local state.
- Added `SessionStore.get_learning_history()` and `GET /sessions/{id}/learning?steps=N` for persisted status.
- Runtime Contract exposes `communication.learning_status`; external attach sequence includes it.
- `/agent/handoff` includes `learning_latest`.
- AgentWorkbench shows the learning status endpoint and handoff Learning summary.
- Verification passed: Python compile for changed runtime/API/tests, `tests/test_layer_events.py`, `tests/test_runtime_contract.py`, `tests/test_app_server_resume.py`, and `npm.cmd --prefix frontend run build`.
- Next useful step: run a real API-backed Maker task and use runtime + learning metrics to choose the next latency/quality fix.

## 2026-06-23 Maker First-Action Briefing

- Added `build_maker_briefing(contract, task)` in `core/runtime_contract.py`.
- Briefing selects the most relevant Maker template for the current task:
  - build/submit/publish/preview -> `maker_build_or_submit`
  - handoff/external-agent tasks -> `external_agent_handoff`
  - inspect/status/query tasks -> `maker_inspect_project`
  - verify/timeout/commit tasks -> `maker_execute_and_verify`
  - fallback -> `maker_plan_small_change`
- Briefing returns:
  - readiness
  - connected
  - warning_codes
  - authority (`maker_mcp`, `local_files`, or `maker_mcp_status`)
  - selected_template
  - recommended_first_action
  - recommended_endpoint
  - suggested_tools
  - checklist
  - evidence_endpoints
  - token_rule
- Runtime Contract exposes `communication.maker_briefing`.
- External attach sequence tells agents to fetch maker briefing before the first Maker action.
- Added Agent-callable `maker_briefing` tool.
- Added `GET /agent/maker-briefing?session_id=...&task=...`.
- `/agent/handoff` includes `maker_briefing`.
- AgentWorkbench displays the briefing endpoint and handoff Maker summary.
- Verification passed: Python compile for changed runtime/API/tests, `tests/test_runtime_contract.py`, `tests/test_layer_events.py`, `tests/test_app_server_resume.py`, and `npm.cmd --prefix frontend run build`.
- Next useful step: verify in a real API-backed Maker run whether the LLM uses maker briefing; if not, add a first-action guard/injection before tool selection.

## 2026-06-23 Maker Briefing First-Step Injection

- Added `render_maker_briefing_for_llm()` and ReAct `[maker_briefing]` prompt injection so arbitrary LLM providers see a concrete MakerMCP next action before first tool selection.
- ReAct emits a persisted `maker_briefing` event at session start; this makes the guard visible to SSE replay, AppServer history, and AgentWorkbench.
- Frontend `AgentWorkbenchState` now carries `makerBriefing`; main chat stays clean while Workbench shows authority, selected template, recommended first action, tools, endpoints, and acceptance hints.
- Verification passed: Python compile, `tests/test_runtime_contract.py`, `tests/test_layer_events.py`, `tests/test_app_server_resume.py`, and `npm.cmd --prefix frontend run build`.
- Next useful step: run a real API-backed Maker session and inspect whether first action follows `maker_briefing`; if not, add a stricter first-action guard before tool selection.

## 2026-06-23 Maker First-Action Guard

- ReAct now runs `_maker_first_action_guard()` before tool preflight/execution.
- If MakerMCP is connected and the first action attempts a local side effect before using Maker authority, ReAct blocks the step, emits `maker_briefing_guard`, records a structured observation, and injects a correction hint.
- AgentWorkbench consumes guard events into `makerGuard` and shows a compact First Action Guard panel with pass/warn/block state, reason, tool, suggested tools, and endpoint.
- Verification passed: Python compile, `tests/test_runtime_contract.py`, `tests/test_tool_call_validation.py`, and frontend build.
- Broader AppServer/layer regression was blocked by Windows `WinError 112` disk exhaustion while writing temp/log files.
- Next useful step: free disk space, rerun AppServer/layer regression, then verify a real API-backed Maker task follows `maker_briefing_guard`.

## 2026-06-23 Pullable Maker Guard History

- Added `SessionStore.get_maker_guard_history()` and `GET /sessions/{id}/maker-guard?steps=N`.
- `/agent/handoff` now includes `maker_guard_latest` and compact guard history so external agents can inspect Maker first-action alignment without raw SSE replay.
- Runtime Contract communication and external attach sequence expose `maker_guard`; Maker briefing evidence endpoints include it.
- Prompt renderer compacts communication/external-agent fields to keep Maker templates, especially `external_agent_handoff`, visible under small prompt budgets.
- Verification passed: Python compile, `tests/test_runtime_contract.py`, focused maker-guard endpoint test, and focused handoff endpoint test.
- Next useful step: broad AppServer/layer regression after disk pressure clears, then real API-backed Maker run using maker_briefing + maker_guard + runtime_metrics + learning.

## 2026-06-23 Workbench Maker Guard Evidence Loop

- AgentWorkbench handoff preview now displays `maker_guard_latest` as a compact Guard row with decision, tool, authority, flow, tools, and reason.
- Runtime Contract panel displays the `maker_guard` endpoint so users/external agents can see where first-action alignment evidence lives.
- Broad regression recovered from the earlier disk-space failure: `tests/test_app_server_resume.py` and `tests/test_layer_events.py` passed.
- Verification passed: frontend build, Runtime Contract tests, focused guard/handoff endpoint tests, full AppServer resume tests, and layer event tests.
- Next useful step: real GUI/API-backed Maker task with simultaneous inspection of maker_briefing, maker_guard, runtime_metrics, and learning.

## 2026-06-23 Runtime Advice For Evidence-Driven Next Actions

- Added `build_runtime_advice()` in `server/app_server.py`.
- Added `GET /sessions/{id}/runtime-advice?steps=N`.
- `/agent/handoff` now includes `runtime_advice`.
- Runtime Contract communication and external attach sequence expose `runtime_advice`.
- AgentWorkbench handoff preview shows an Advice row with status, priority, next action, and reason.
- Advice uses maker briefing, maker guard, runtime metrics, learning status, and context sync to choose priorities such as maker alignment, MakerMCP connection, latency, token efficiency, async learning, missing context sync, or continue.
- Verification passed: Python compile, Runtime Contract tests, frontend build, focused runtime-advice/handoff tests, full AppServer resume tests, and layer event tests.
- Next useful step: real GUI/API-backed Maker task; read `runtime_advice` first and only drill into detailed endpoints when it points there.

## 2026-06-23 External LLM Quickstart Bundle

- Added `GET /agent/quickstart?session_id=...&steps=N`.
- Runtime Contract communication now includes `quickstart_bundle`, and external attach sequence starts with quickstart.
- Quickstart returns a compact external-agent prompt, boot sequence, Maker readiness, runtime advice, Maker briefing, latest context sync, endpoint map, and operating rules.
- AgentWorkbench Runtime Contract panel displays the Quickstart endpoint.
- Verification passed: Python compile, Runtime Contract tests, frontend build, focused quickstart/handoff tests, full AppServer resume tests, and layer event tests.
- Next useful step: use quickstart as the first surface for a real Claude/Codex/opencode-style Maker session, then inspect first-action alignment via runtime_advice and maker_guard.

## 2026-06-23 Workbench Quickstart Preview

- AgentWorkbench now has an `LLM Quickstart` block with Preview and Copy Prompt controls.
- Quickstart preview shows advice summary, Maker summary, the generated startup prompt, and first boot sequence steps.
- Styling is dense, mint-accented, wrapping, and avoids fixed-height clipping.
- Verification passed: frontend build, focused quickstart/handoff endpoint tests, Runtime Contract tests, full AppServer resume tests, and layer event tests.
- Next useful step: copy the prompt into a real external/API-backed LLM and inspect first-action alignment through runtime_advice and maker_guard.

## 2026-06-23 Markdown Quickstart Prompt

- `/agent/quickstart` now returns `prompt_markdown`.
- Markdown startup card includes session/task, runtime advice, Maker authority, boot sequence, compact endpoints, and rules.
- Workbench Quickstart preview/copy prefers `prompt_markdown` and falls back to the short prompt.
- Verification passed: Python compile, focused quickstart markdown endpoint test, frontend build, Runtime Contract tests, full AppServer resume tests, and layer event tests.
- Next useful step: paste the Markdown startup card into a real external/API-backed LLM and inspect first-action alignment.

## 2026-06-23 Direct Markdown Quickstart Endpoint

- `/agent/quickstart?format=markdown` and `/agent/quickstart.md` now return `text/markdown` startup cards directly.
- Workbench Quickstart block has Copy MD URL in addition to Copy Prompt.
- JSON quickstart remains unchanged for GUI preview.
- Verification passed: Python compile, focused quickstart direct Markdown endpoint test, frontend build, Runtime Contract tests, full AppServer resume tests, and layer event tests.
- Next useful step: use Copy MD URL when an external agent can fetch local URLs; otherwise use Copy Prompt.

## 2026-06-23 Quickstart Surface Profiles

- `/agent/quickstart` and `/agent/quickstart.md` accept `surface=generic|codex|claude-code|opencode`.
- Quickstart JSON returns `surface`; Markdown includes a `Surface Profile` section.
- Profiles encode ecosystem memory files, start rule, and skill style for Codex, Claude Code, opencode, and generic agents.
- Workbench Quickstart preview shows surface summary.
- Verification passed: Python compile, focused quickstart surface profile test, frontend build, Runtime Contract tests, full AppServer resume tests, and layer event tests.
- Next useful step: add a Workbench surface selector only if real external-agent use shows switching profiles from the UI is common.

## 2026-06-23 Workbench Surface Selector And API Runtime Evidence

- Workbench Quickstart now lets the user choose `generic`, `codex`, `claude-code`, or `opencode`; selected surface is appended to JSON and Markdown quickstart URLs.
- Copy Prompt can fetch the selected Markdown quickstart directly, so Preview is optional.
- MiniMax is wired through `LLMFactory -> MiniMaxLLM`, not the OpenAI-compatible client; its default call endpoint is `/text/chatcompletion_v2`.
- `/health` now reports `runtime_kind`, `model`, `base_url`, `api_key_set`, and `last_call_stats.endpoint`, and CockpitHeader uses API-ready semantics for remote providers.
- Next useful step: run a real API-backed Maker session and inspect `/health.last_call_stats.endpoint`, runtime_advice, maker_guard, runtime_metrics, and learning before optimizing further.

## 2026-06-23 Active LLM Runtime Probe

- Added `POST /llm/probe` plus ProviderSelector `Probe`.
- Probe uses a cloned config and one tiny request, then returns provider/class/model/base URL, endpoint, tokens, latency, output preview, and error diagnostics.
- `/config/llm` now persists provider-scoped `llm.api_keys` through the shared config path and avoids stale model/base URL when switching providers.
- OpenAI-compatible, Claude, and MiniMax clients now expose endpoint-level call stats consistently.
- Next useful step: run Probe with a real API key, then a minimal Maker task, and use runtime_advice/maker_guard/runtime_metrics/learning to choose the next fix.

## 2026-06-23 LLM Probe Evidence Loop

- Runtime Contract, Quickstart, Handoff, Runtime Advice, and Workbench now carry compact `llm_probe` evidence.
- Failed probe drives `runtime_advice.priority=llm_provider`; no probe remains non-blocking.
- Prompt renderer was tightened so adding `llm_probe` does not push `external_agent_handoff` out of the capped contract.
- Next useful step: use a real provider Probe, then a small Maker task, and compare provider evidence with Maker guard/runtime metrics before optimizing.

## 2026-06-23 Session-Scoped LLM Probe History

- `POST /llm/probe` accepts `session_id` and appends an `llm_probe` event to SessionStore.
- `GET /sessions/{id}/llm-probe?steps=N` exposes compact provider probe history for external agents.
- Quickstart/Handoff/Runtime Advice prefer session probe evidence over global last_probe.
- Next useful step: pass active session_id from the GUI Probe button, then run a real API-backed Maker task and inspect session probe history alongside guard/metrics/learning.

## 2026-06-23 Live LLM Probe Workbench Loop

- ProviderSelector Probe now passes the active `session_id` from `workbench.sessionId` when one exists.
- During an active run, provider/model/base URL/API key controls stay locked, but Probe remains clickable so the user can verify the current provider without changing runtime config.
- `POST /llm/probe` now emits live `llm_probe` SSE through `Session.emit()` for active sessions, while inactive sessions still persist probe events directly to SessionStore.
- `AgentWorkbenchState` carries `llmProbe`; Workbench shows provider/model/endpoint/latency/tokens/error as a compact wrapping evidence row.
- `SessionStore.create_session()` clears previous events for reused session ids before replacing session metadata, preventing stale fixed-id probe history from polluting tests or external handoffs.
- Verification passed: frontend build, Python compile, AppServer smoke, SessionStore, AppServer resume, Runtime Contract, and layer events tests.
- Next useful step: run a real API-backed Maker task and inspect live Workbench probe evidence beside `/sessions/{id}/llm-probe`, runtime_advice, maker_guard, runtime_metrics, and learning.

## 2026-06-23 Live Runtime Advice Workbench Control Surface

- AgentWorkbench now fetches `runtime_advice` directly from `communication.runtime_advice` or `/sessions/{id}/runtime-advice?steps=20`.
- The advice preview auto-refreshes from live evidence changes:
  - `llmProbe.status/errorType`
  - `makerGuard.decision`
  - `contextSync.revision`
  - `goalChecklist.overall`
  - `latency.totalMs`
  - `learning` layer event
- The UI shows a compact next-action surface with status, priority, next action, reasons, and summarized evidence instead of raw JSON.
- Priority styling maps provider/Maker/MakerMCP problems to danger, latency/token/context watch states to warning, and continue/ready states to success.
- This improves arbitrary LLM onboarding because the GUI now exposes the same evidence-driven next action that Quickstart/Handoff carry, without requiring manual endpoint inspection.
- Verification passed: frontend build, AppServer resume tests, and Runtime Contract tests.
- Next useful step: run a real API-backed Maker task and let live Runtime Advice decide whether the next fix is provider wiring, Maker alignment, latency, token efficiency, context sync, or learning.

## 2026-06-23 Live Runtime Metrics Workbench Panel

- AgentWorkbench now fetches `runtime_metrics` directly from `communication.runtime_metrics` or `/sessions/{id}/runtime-metrics?steps=20`.
- Metrics auto-refreshes when runtime-layer events or first/LLM/tool/total latency values change.
- The panel displays:
  - `count`
  - total LLM tokens
  - token cache hits/misses/size
  - tool ranking selected/candidates/cache-hit
  - max latency, context build time, and latest metric details
- Handoff Runtime summary now reuses the same `runtimeMetricsSummary()` helper as the live panel.
- Styling is dense, blue, and non-clipping; this is an instrument panel, not a fixed-size content card.
- Verification passed: frontend build, AppServer resume tests, and Runtime Contract tests.
- Next useful step: run a real API-backed Maker task and use Runtime Advice + Runtime Metrics together to choose provider, prompt/context, ranking, cache, Maker alignment, or learning fixes from evidence.

## 2026-06-23 Live Learning Status Workbench Panel

- AgentWorkbench now fetches Learning layer state directly from `communication.learning_status` or `/sessions/{id}/learning?steps=20`.
- Learning Status auto-refreshes when session stage or Learning layer status/event/timestamp changes.
- The panel shows latest learning/reflection event, state, event count, detail, and compact metrics such as async/elapsed/trajectory/skill/knowledge/error counts.
- Styling is green/mint, dense, and non-clipping, with error/skipped/running states differentiated.
- This makes Agent/Core/Learning independence more observable: Learning now appears as a real async layer next to Runtime Advice and Runtime Metrics rather than only as a layer pill or handoff summary.
- Verification passed: frontend build, layer event tests, and AppServer resume tests.
- Next useful step: run a real API-backed Maker task and inspect LLM Probe + Runtime Advice + Runtime Metrics + Learning Status + Maker Guard together before deciding the next optimization.

## 2026-06-23 External Agent Boot Links Panel

- AgentWorkbench now includes an `External Agent Boot` panel before the detailed Quickstart/Handoff blocks.
- The panel summarizes ready boot surfaces and has one-click `Copy Boot`.
- The copied checklist includes Quickstart Markdown/JSON, Handoff Bundle, Runtime Advice, Maker Briefing, Maker Guard, Runtime Metrics, Learning Status, Context Sync, and LLM Probe History.
- This reduces external LLM onboarding friction: users can paste one compact endpoint checklist into Claude/Codex/opencode/other agents instead of manually collecting scattered URLs.
- Styling is compact mint/blue and wraps long URLs without fixed-height clipping.
- Verification passed: frontend build, Runtime Contract tests, and AppServer resume tests.
- Next useful step: run a real API-backed Maker task or external-agent handoff using Copy Boot, then inspect first-action alignment through Runtime Advice and Maker Guard.

## 2026-06-23 Compact Evidence Bundle

- Added `GET /sessions/{id}/evidence?steps=N` as a compact current-state evidence bundle for arbitrary LLM onboarding and runtime diagnosis.
- Bundle contents: runtime advice, Maker briefing, latest context sync, runtime metrics summary, latest Learning status, latest Maker guard, compact LLM probe, history counts, endpoint map, and token rule.
- Runtime Contract now exposes `communication.evidence_bundle` and attach sequence reads Quickstart -> Evidence Bundle -> Handoff.
- Quickstart and Workbench External Agent Boot now prefer Evidence Bundle before Handoff/detail histories.
- Important lesson: cross-agent speed improves when the default pull is one compact summary endpoint, while detailed histories remain available only on demand.

## 2026-06-23 Evidence Bundle-Driven Workbench Refresh

- AgentWorkbench now auto-fetches `communication.evidence_bundle` when available instead of independently auto-pulling runtime advice, runtime metrics, and learning status.
- The bundle hydrates the existing Runtime Advice, Runtime Metrics, and Learning Status panels while preserving each panel's manual detail Refresh button.
- External Agent Boot shows a Bundle status row summarizing advice/context/metrics/learning/guard/probe state and has a manual Evidence refresh action.
- Important lesson: compact backend bundles only reduce latency/noise if the frontend actually uses them as the default refresh path.

## 2026-06-23 Pasteable Evidence Markdown

- Evidence Bundle now supports Markdown output through `/sessions/{id}/evidence?format=markdown` and `/sessions/{id}/evidence.md`.
- Markdown includes next action, Maker authority, latest context/guard/learning/probe/runtime evidence, counts, detail endpoints, and token rule.
- AgentWorkbench External Agent Boot has `Copy Evidence`, which copies the Markdown card itself for LLMs that cannot fetch localhost URLs.
- Boot checklist now points to Evidence MD when available while JSON Evidence remains the Workbench auto-refresh data source.
- Important lesson: arbitrary LLM onboarding needs both pullable local endpoints and pasteable artifacts.

## 2026-06-23 Three-Layer Evidence Summary

- Added `SessionStore.get_layer_history()` for persisted Agent/Runtime/Learning layer communication events.
- Evidence Bundle now includes `layer_summary` with event count, latest state/event/route by layer, and recent source->target routes.
- Evidence Markdown includes `Layer Communication` so external LLMs can diagnose Agent vs Runtime vs Learning ownership without raw SSE replay.
- Workbench Evidence summary line includes layer event count/current layer state.
- Important lesson: three-layer architecture is not truly useful to external agents until the compact evidence artifact exposes layer state alongside Maker/runtime evidence.

## 2026-06-23 MakerMCP Authority Evidence And styles.css Alignment

- Evidence Bundle now includes `maker_mcp` readiness, connected, tool_count, top_tools, remote_identity, and last_call from Runtime Contract.
- Evidence Markdown now separates MakerMCP runtime state from Maker briefing, so external LLMs can tell whether Maker authority is available before asking for detailed tools.
- Workbench Bundle summary includes `maker={readiness}:{tool_count}`.
- Read the referenced `styles.css`; learned design tokens are brand `#00D9C5/#00CDBA`, app `#F7F9FA`, white panels, text `#060A26`, rgba muted text, 6/8/10/16px radius scale, subtle shadows, thin scrollbars, and teal focus ring.
- Updated `frontend/src/styles/index.css` root tokens and global focus/scrollbar behavior to match that design language.
- Important lesson: "TapTapMaker theme" should be enforced through shared tokens first, not one-off panel recoloring.

## 2026-06-23 Workbench Semantic Token Cleanup

- Added semantic Workbench tokens in `frontend/src/styles/index.css` for primary/mint, info, warning, danger, success, and reusable panel surfaces.
- Replaced ad hoc Workbench diagnostic colors across External Agent Boot, Quickstart, Runtime Contract, Maker Briefing/Guard, LLM Probe, Runtime Advice, Runtime Metrics, Learning Status, Context Sync, Skill Sync, maker checklist/template, and early run-state panels.
- `.workbench-error` now uses full wrapping display instead of a fixed clipped block.
- Verification passed: `npm.cmd --prefix frontend run build`.
- Next useful step: run a real API-backed Maker session and let Evidence Bundle + Provider Probe + Runtime Advice decide whether the next fix belongs to provider wiring, MakerMCP alignment, latency/token budget, or Learning.

## 2026-06-23 v0.4.1 Runtime Readiness

- Stable checkpoint: `docs/releases/v0.4.1-runtime-readiness.md`.
- Added `GET /runtime/readiness?session_id=...` as a no-network first diagnostic gate for humans and arbitrary LLMs.
- Runtime Readiness aggregates provider config, API-key presence, latest LLM Probe endpoint/status, MakerMCP authority, layer/context/runtime/learning/guard summaries, release gate checks, and next actions.
- Runtime Contract communication now includes `runtime_readiness`, and external attach sequence starts there before Quickstart/Evidence/Handoff.
- Quickstart boot sequence now starts with Runtime Readiness.
- Workbench External Agent Boot now copies Runtime Readiness as the first checklist item.
- Verification passed: Python compile, `tests/test_runtime_contract.py`, `tests/test_app_server_resume.py`, and `npm.cmd --prefix frontend run build`.
- Next useful step: one real API-backed Maker task using Probe -> Runtime Readiness -> Evidence Bundle -> Runtime Advice/Maker Guard/Metrics/Learning.

## 2026-06-24 v0.4.1 Closure Audit

- Added `docs/releases/v0.4.1-completion-audit.md` with a six-requirement audit against current code/docs/test evidence.
- Synchronized root/frontend/Electron package metadata and lockfiles to `0.4.1-runtime-readiness`.
- Updated `docs/releases/v0.4.1-runtime-readiness.md` with the audit link, Electron build gate, and package metadata note.
- Updated the memory-index top version to `v0.4.1-runtime-readiness`.
- Verification passed: Python compile, Runtime Contract tests, AppServer resume tests, frontend build, and Electron build.
- Completion decision: stable small version is complete; full thread goal remains active until a real API-backed Maker run proves provider/MakerMCP/guard/metrics/learning/GUI behavior.

## 2026-06-24 API Call Proof And Feedback Summary

- Added no-network `llm_call_proof` to Runtime Readiness and Evidence Bundle.
- `llm_call_proof` compares expected endpoint with observed endpoint and records evidence source. MiniMax expects `/text/chatcompletion_v2`, OpenAI-compatible providers expect `/chat/completions`, and Claude expects `/messages`.
- Added `GET /llm/feedback-summary` to summarize saved `docs/llm-feedback` artifacts without sending new project data to an external LLM.
- Runtime Contract communication and External Agent attach sequence expose `llm_feedback_summary`.
- AgentWorkbench Evidence summary now shows API proof and feedback state.
- Fresh real MiniMax self-feedback was not run because the environment rejected external disclosure of the internal architecture summary; use saved feedback summary unless the user explicitly approves a safe external disclosure path.
- Verification passed: Python compile, Runtime Contract tests, AppServer resume tests, LLM runtime interview tests, frontend build, and Electron build.

## 2026-06-24 v0.4.2 Onboarding Closure

- Stable checkpoint: `docs/releases/v0.4.2-onboarding-closure.md`.
- Added `GET /agent/onboarding?session_id=...&steps=20` and `/agent/onboarding.md` as the first one-stop startup/closure packet for arbitrary LLMs.
- Runtime Contract now exposes `communication.onboarding_bundle` and makes onboarding the first external-agent attach step before Runtime Readiness, Quickstart, Evidence, and Handoff.
- Onboarding Bundle combines Runtime Readiness, Evidence Bundle, Runtime Advice, MakerMCP authority, layer summary, runtime metrics, learning latest, API call proof, token strategy, endpoint map, TapTap Maker Plus reference principles, and closure gate checks.
- AgentWorkbench External Agent Boot now prioritizes Onboarding and adds `Copy Onboarding`; Copy Boot starts with the onboarding markdown/JSON URL.
- Package metadata is synchronized to `0.4.2-onboarding-closure` across root, frontend, Electron, and lockfiles.
- Verification passed: Python compile, Runtime Contract tests, AppServer resume tests, frontend build, and Electron build.
- Completion decision: the local stable small version is closed; remaining proof is one real API-backed Maker validation run through Onboarding -> Probe -> tiny Maker task -> Readiness/Evidence/Guard/Metrics/Learning/GUI.
- Important lesson: arbitrary LLM onboarding is fastest when the first packet is a closure-aware evidence bundle, not a list of scattered endpoints.

## 2026-06-24 v0.4.3 Maker Setup + Chat-First

- Stable checkpoint: `docs/releases/v0.4.3-maker-setup-chat-first.md`.
- Added Maker Setup Doctor endpoints: `GET /maker/setup-status`, `/maker/setup-status.md`, and optional `check_latest=true`.
- Setup Doctor detects configured `@taptap/maker`, `npx`, project root/app-root misuse, `.maker-mcp/config.json`, `.project/settings.json`, project id, TapTap auth/PAT files, tool audit, and recommended next action.
- Added Maker Tool Audit endpoint `GET /maker/tool-audit`, comparing remote MCP tools, ToolRegistry registration, Executor handlers, and side-effect proxy marking.
- Required creative proxy tools now include image, video, music, and 3D task tools; `Executor.MAKER_PROXY_TOOLS` now marks `query_video_task`, `create_3d_model_task`, and `query_3d_model_task`.
- Added `POST /maker/project/select` to switch/create active Maker project directories and rebuild the base agent/IDE/Maker MCP runtime when no session is active.
- Added embedded auth flow preparation/completion endpoints: `POST /maker/auth/prepare`, `POST /maker/auth/complete`, and `GET /maker/auth/state`.
- Runtime Contract, Evidence Bundle, and Onboarding Bundle now expose Maker setup/audit endpoints and results for arbitrary LLMs.
- Electron exposes a directory picker; frontend adds a Maker Setup strip and a wider chat-first default layout.
- Verification passed: Python compile, Maker setup tests, Runtime Contract tests, MCP diagnostics, AppServer tests, AppServer resume tests, frontend build, and Electron build.
- Remaining real-world validation: run actual `npx -y @taptap/maker install/init/login`, confirm CLI auth URL handling, then start a tiny API-backed Maker coding task.

## 2026-06-24 v0.4.4 Portable Agent Root

- Stable checkpoint: `docs/releases/v0.4.4-portable-agent-root.md`.
- Added `core/portable_env.py` to pin TTMEvolve runtime home/cache/temp/Maker auth/npm/pip/HuggingFace/sentence-transformers/torch/matplotlib/Playwright paths under repo-local `portable/`.
- Added `GET /runtime/portable` as the first no-network diagnostic for the self-contained Agent folder requirement. It reports unset portable variables, paths outside the Agent root, and `C:\Users\...` leakage blockers.
- Runtime Contract, Runtime Readiness, Evidence, Onboarding, Quickstart, and Handoff now expose `portable_runtime`; external agent boot order starts with `/runtime/portable` before `/runtime/readiness`.
- `Config` now resolves `project_root`, `storage_root`, `runtime.portable_root`, `llm.model_path`, and `maker_mcp.cwd` relative to the config file directory.
- Defaults moved Maker game work out of the app root: `project_root` and `maker_mcp.cwd` now point to `./workspace/default-maker-project`.
- Maker auth now uses `TTM_MAKER_HOME`; Playwright downloads fall back to `portable/cache/playwright`; bootstrap subprocesses inherit portable env for pip/wheels/Playwright/offline setup.
- Package metadata is synchronized to `0.4.4-portable-agent-root`.
- Verification passed: Python compile, portable env tests, Maker setup tests, Runtime Contract tests, MCP diagnostics, AppServer tests, AppServer resume tests, frontend build, and Electron build.
- Remaining next step: create a clean distributable `TTMEvolve-Agent/` layout/packager, then run the real Maker CLI install/init/auth validation and a tiny API-backed Maker task.

## 2026-06-24 v0.4.5 One-Click Practice Entry

- Stable checkpoint: `docs/releases/v0.4.5-one-click-practice-entry.md`.
- Added visible Windows GUI launchers `TTMEvolve.vbs` and `TTMEvolve-Practice.vbs`; they start GUI/practice hidden through PowerShell so the user does not see a command window.
- Added `scripts/create_windows_shortcuts.ps1` to generate `TTMEvolve.lnk` and `TTMEvolve Practice.lnk`.
- Kept `start-practice.ps1` and `start-practice.bat` as backend/bootstrap fallback entries, not the primary UX.
- Added in-GUI Maker Practice flow through `server/maker_practice.py` and `/maker/practice/*`.
- Maker Setup strip now has `Practice`, live logs, `Open Auth`, CLI input, and `Stop`, so Maker install/init/auth/project selection no longer need to be primarily handled in a command window.
- The script applies portable runtime paths, creates/reuses `workspace/smoke-maker-game`, refuses to use the TTMEvolve app root as the Maker game project, writes `config.json`, runs Maker MCP install, runs Maker init when needed, launches the GUI, and prints `/runtime/portable`, `/maker/setup-status`, `/maker/tool-audit`, and `/runtime/readiness`.
- Added compatibility fixes for Windows PowerShell: avoid `$HOME` variable collision and avoid `[System.IO.Path]::GetRelativePath`.
- Important boundary: TapTap account authorization may still require human interaction if Maker CLI requests login; auth state remains under `portable/home/.taptap-maker`.
- Product rule: `.bat` and `.ps1` are now backend/bootstrap support, not the primary user-facing entry. Normal users should see/click GUI launchers or shortcuts.
- Launcher reliability fixes: shortcuts target `wscript.exe`, VBS writes `logs/gui/launcher.log`, hidden PowerShell launch no longer crashes on `[Console]::OutputEncoding`, config reads `utf-8-sig` for BOM tolerance, Electron shows the window before backend readiness, and Electron uses a single-instance lock to avoid cache conflicts.
- Verification passed: `powershell -ExecutionPolicy Bypass -File .\start-practice.ps1 -DryRun -NoGui -SkipMakerInstall -SkipMakerInit`, Python compile, `tests/test_maker_practice.py`, AppServer resume tests, frontend build, and Electron build.

## 2026-06-24 Maker Remote Creative Tool Root Cause

- Real field test created `D:\TTMEvolveMakerImageProbe-20260624-230557`, pulled a Maker project with portable PAT/auth, and called official Maker MCP `generate_image`.
- Root cause of TTMEvolve remote creative tool failure: official `@taptap/maker` remote proxy reads `TAPTAP_MAKER_HOME`, while TTMEvolve only set `TTM_MAKER_HOME`.
- After adding official `TAPTAP_MAKER_HOME` everywhere, official MCP `tools/list` expanded from 2 tools to 10 tools, including `generate_image`, `batch_generate_images`, `edit_image`, `text_to_music`, video, and 3D tools.
- Real `generate_image` succeeded after passing required schema fields `prompt`, `name`, and `target_size`; output downloaded to `D:\TTMEvolveMakerImageProbe-20260624-230557\assets\image\asset_20260624151624.png`.
- TTMEvolve `MCPIntegration` now registers `generate_image` as real `source=maker_mcp` with required schema `prompt/name/target_size`; validation passes for a complete request.
- Updated portable env, Electron child env, PowerShell launchers, Setup Doctor, Agent-root MCP registration, tests, and current `.cursor/.codex/.mcp` root configs.
- New rule: always set both `TAPTAP_MAKER_HOME` and `TTM_MAKER_HOME`; prefer `TAPTAP_MAKER_HOME` for official Maker auth compatibility.

## 2026-06-24 GUI Launch + Main Chat Dedupe Patch

- User screenshots exposed two remaining practice-test blockers: a native `Python backend health check timeout` modal and duplicate assistant content in the main transcript.
- Electron now keeps the GUI open and logs backend startup/health degraded state instead of showing a blocking native error dialog.
- `frontend/src/hooks/useBackend.ts` no longer appends `thought` events as `Agent 正在思考` cards in the main chat; thoughts update Workbench/currentThought only.
- Final assistant output now has a per-session commit guard, so terminal status/event replay cannot add the same final answer twice.
- Product rule reinforced: main chat is conversation-first; runtime cognition and diagnostics belong in the `过程` Workbench surface unless they are essential user-facing actions.
- Verification passed: frontend build, Electron build, Maker Practice test, AppServer resume test, and `TTMEvolve.vbs` GUI smoke launch with `/health.status=ok`.

## 2026-06-24 GUI Workspace Sidebar Correction

- User clarified that the file tree and asset library sidebars should appear between the Agent chat and Maker preview, not inside or over the chat panel.
- `ChatPanel` now stays conversation-first and only emits `文件` / `素材` / `模型` button actions.
- `App` owns `workspaceDrawer` state and inserts a real `workspace-side-drawer` grid column between the chat sidebar and preview stage.
- File/asset selection still routes through the existing preview/editor path, then closes the middle drawer.
- Cleaned visible Chinese labels in the affected chat, file tree, asset library, and optional code drawer surfaces.
- Verification passed: `npm.cmd --prefix frontend run build` and `npm.cmd --prefix electron run build`.
- Important lesson: file/assets are workspace aids, not chat content; keep them in the middle workspace column while the Maker browser remains the central preview stage.

## 2026-06-24 GUI Auxiliary Sidebar And Splash Startup

- User clarified that `可用工具` and `设置` have the same problem as file/assets if they float over Maker preview.
- `CockpitHeader` now only emits open actions; it no longer renders the tools popover.
- `App.workspaceDrawer` now supports `files`, `assets`, `tools`, and `settings`, all rendered as the middle workspace column between Agent chat and Maker preview.
- Removed the settings overlay and BrowserView hide/show event; the native Maker preview stays active and resizes with its column instead of becoming a white screen.
- Electron startup is now splash-first: a small progress window appears, backend `/health` is awaited, then the main GUI is created hidden and shown only after renderer readiness.
- Verification passed: frontend build, Electron build, GUI launch through `TTMEvolve.vbs`, and `/health.status=ok` with MiniMax API runtime.
- Important lesson: solve native BrowserView layering with layout, not overlays or hiding; normal users should see startup progress until the cockpit is actually ready.

## 2026-06-24 GUI Settings And Tool Entry Deduplication

- User clarified that duplicate settings/model/settings entries waste attention and make the GUI feel less agent-native.
- `CockpitHeader` now keeps status passive and moves `可用工具` into the top action area beside `打开 Maker`; top `设置` was removed.
- Chat bottom keeps `文件` / `素材` / `设置`; this bottom `设置` is the single visible settings entry.
- File tree and asset library remain middle workspace side drawers between Agent chat and Maker preview.
- Tools and settings now open as page-like surfaces inside the preview workspace, with Maker preview still visible/resized on the right instead of being blanked or covered.
- Verification passed: `npm.cmd --prefix frontend run build` and `npm.cmd --prefix electron run build`.
- Important lesson: passive status, action buttons, and auxiliary pages must be separate; do not reintroduce multiple settings buttons or status-area action buttons.

## 2026-06-24 GUI Compact Preview Chrome + Forum + Dark Mode

- Removed the full-width chat/preview URL toolbar row from the default cockpit. Chat run state/collapse now use a small floating control, and Browser preview no longer shows a full URL bar by default.
- Added top action `制造论坛`, navigating the native Maker BrowserView to `https://www.taptap.cn/app/810249/topic`.
- Added top action `深色` / `浅色`, persisted in `localStorage` and applied through `data-theme`.
- Added dark shell tokens based on neutral charcoal, `#181818` / `#262626`, `#e5e5e5`, and the TapTap Maker cyan accent.
- Integrated the local TapTap Maker darkmode extension concept without copying the full extension bundle: Electron now exposes `makerBrowser:setDarkMode` and injects Maker-specific dark CSS into BrowserView, including bg-pattern removal, `bg-white` darkening, iframe dimming, and image/SVG brightness reduction.
- Verification passed: `npm.cmd --prefix frontend run build` and `npm.cmd --prefix electron run build`.
- Important lesson: keep navigation in top actions; default preview should be visually quiet, and dark mode must cover both React shell and native BrowserView.

## 2026-06-24 Chat Conversation Shape Correction

- User clarified the correct chat model: user instructions are right-aligned bubbles, but AI replies are not bubbles; they should be full-width answer pages.
- `ChatMessage` now renders:
  - `user` as right-side `user-bubble`.
  - `assistant` as full-width `assistant-answer`.
  - `assistant` Markdown through `marked`, so users see rendered Markdown rather than raw Markdown source.
  - Runtime/tool events as compact one-line status rows, with failure details collapsed behind `查看详情`.
- `useBackend` now exposes `resetConversation()` to close active SSE, clear session refs, clear queues, reset Workbench state, and stop loading.
- `ChatPanel` now includes mini controls for `新对话` and `历史`; history reads `GET /sessions` and shows recent persisted sessions.
- Verification passed: `npm.cmd --prefix frontend run build`.
- Important lesson: main chat must not become a terminal log. Distinguish intent/result/process by layout: right bubble / full-width answer / compact status row.

## 2026-06-24 Chat Status Bar Integration

- User screenshot showed the floating `ready/collapse` mini-control felt abrupt over the empty chat area.
- Replaced absolute chat mini controls with an in-flow `.chat-conversation-bar` owned by the Agent chat panel.
- Status dot/text, `新对话`, `历史`, and collapse now live in one slim top row; `.chat-messages` no longer reserves top padding for a floating widget.
- Verification passed: `npm.cmd --prefix frontend run build` and `npm.cmd --prefix electron run build`.
- Important lesson: chat status/actions must feel structurally attached to the conversation panel, not like temporary debug UI floating between chat and preview.

## 2026-06-24 Maker Access Center And Preview Bottom Bar

- User clarified that Maker install/init/upgrade/tool registration must be directly visible and fully GUI-driven.
- Moved the cockpit action/status strip into the preview column bottom only: left side actions (`Maker 接入`, `可用工具`, `制造论坛`, theme, `打开 Maker`), right side passive status pills (project, Maker MCP, model, token, latency, profile).
- Added a page-like `Maker 接入` surface with install/upgrade, project directory selection, initialization, authorization, live logs, and tool audit/reconnect actions.
- Tool list now merges Maker remote tools, required creative proxy tools, and Agent fallback tools, with per-tool remote/register/executor status instead of only showing the few remote tools returned by `/mcp/tools`.
- Added `POST /mcp/reconnect` to stop/reconnect Maker MCP, clear stale `maker_mcp` ToolRegistry entries and Executor handlers, and rebuild current tool audit.
- Verification passed: frontend build, Electron build, Python compile, and `tests/test_maker_setup.py`.
- Important lesson: Maker setup is not a startup strip or CLI transcript; it is an always-available GUI center. Tool availability must be audited against remote exposure, Agent registration, and Executor handler state, and reconnect must clear stale registrations before re-adding current tools.

## 2026-06-24 Maker Creative Tool Full Field Matrix

- Real D-drive project `D:\TTMEvolveMakerImageProbe-20260624-230557` proved the Maker MCP remote proxy root cause and full creative-tool state.
- Official `@taptap/maker` requires `TAPTAP_MAKER_HOME`; TTMEvolve must always set both `TAPTAP_MAKER_HOME` and compatibility `TTM_MAKER_HOME`.
- After the env fix, official MCP `tools/list` exposed 10 tools: status, build, image, batch image, edit image, music, video create/query, and 3D create/query.
- Real successes:
  - `generate_image` -> `assets\image\asset_20260624151624.png`.
  - `text_to_music` -> `assets\audio\Puzzle_Pop_Loop_20260624152837.mp3`.
  - `create_video_task` / `query_video_task` -> task `cgt-20260624232932-h6zm6`, MP4 in `assets\video`.
  - `create_3d_model_task` / `query_3d_model_task` -> task `a1d1c4d1-c822-4d5d-969b-3ee809bf7025`, GLB/ZIP/render outputs.
- Real remote business failures despite correct TTMEvolve integration:
  - `batch_generate_images` -> remote `500 图片生成失败，请稍后重试`.
  - `edit_image` -> remote `500 图片编辑失败，请稍后重试`.
- New product rule: GUI and Agent must not collapse all tool states into "registered". Show separate states for remote exposure, local registration, schema validation, remote business failure, async pending/succeeded, and output evidence.
- Runtime rule: MCP JSON-RPC `ok` only proves transport. If tool payload has `isError=true` or `structuredContent.success=false`, mark it as `remote_business_failure`.

## 2026-06-24 Maker Project Binding Correction

- User screenshot correctly showed the active GUI still had only 2 remote tools. The active project `D:\本地开发测试` had `.maker-mcp/config.json` with `project_id: "0"` and no `.project/settings.json`.
- Direct official MCP `tools/list` in that active project, even with explicit `TAPTAP_MAKER_HOME` / `TTM_MAKER_HOME`, returned only `maker_status_lite` and `maker_build_current_directory`.
- The earlier 10-tool success came from the fully bound probe project `D:\TTMEvolveMakerImageProbe-20260624-230557`, which has a real UUID project id and `.project/settings.json`.
- New rule: `.maker-mcp/config.json` existence is not enough. Treat empty ids, `0`, `none`, `null`, and `undefined` as `maker_project_not_bound`.
- Setup Doctor now exposes `project_bound`; `maker_project_not_bound` is a blocker. GUI one-click repair should run Maker init/binding for this state, not just reconnect MCP.
- Internal Maker MCP config normalization must explicitly write `TAPTAP_MAKER_HOME` and `TTM_MAKER_HOME` into `config.json`, and AppServer startup runs this normalization before first MCP connection.

## 2026-06-25 / 2026-06-26 v0.6.0 + v0.7.0 Grand Releases

- v0.6.0 完成并推送：Plan First + Coding Agent 强化 + Maker 策划与文案 + 知识整合。详见 `docs/v0.6.0-module-index.md`。
- v0.6.0 含 30 项代码审查修复（Critical 5 / Medium 13 / Low 12）。
- v0.7.0 完成并推送 tag：完整 Windows 桌面应用。详见 `docs/releases/v0.7.0-grand-release.md`。
- v0.7.0 关键变更：
  - **架构**：Electron → Tauri 2.x（Rust + WebView2）
  - **LLM**：本地模型 → 全面云端（LLMRouter + 9 Provider + 故障转移）
  - **包体积**：~450MB → ~200MB（-60%）
  - **新增主题系统** + Settings 5 面板 + UI 组件库
  - **192/192 测试通过**
- v0.7.0 借鉴 Rinorsi/taptap-maker-plus 的主题与 Settings 设计；借鉴 taptap-maker-project 的 COS 协议。
- 七大终极目标规划见 `docs/seven-grand-goals.md`。
- COS 协议融入计划见 `docs/cos-integration.md`。

## 2026-06-26 v0.8.0 - v1.3.0 系列

- v0.8.0：Tauri 启动时自动拉起 fast_ops HTTP 桥接（端口 8766），统一生命周期管理（关闭时同时停 Python + 桥接）。`tests/test_tauri_lifecycle.py` 12 个测试。
- v0.9.0：Tauri 三平台 targets（Windows NSIS+MSI、Linux DEB+AppImage、macOS DMG+APP）；启动器三模式（gui / cli / headless）；`tests/test_start_scripts.py` 14 个测试。
- v1.0.0：tauri-plugin-updater 集成 + Python 客户端；`src-tauri/src/updater.rs` + `core/updater_client.py`；31 个测试覆盖版本比较、prerelease 语义、离线 fallback。
- v1.0.0：5 个桌面图标（PNG 32x32 / 128x128 / 256x256 + icon.ico + icon.icns），通过 `scripts/build_portable/build_icons.py` 自动生成（品牌色 #00D9C5）。
- v1.1.0：跨平台代码签名（Windows signtool、macOS codesign+notarytool、Linux GPG）；`scripts/build_portable/build_*.py` 4 个独立脚本 + 1 个编排器；18 个 dry-run 测试。
- v1.2.0：E2E 测试（19 个）覆盖 Settings API、fast_ops fallback、LLM Router、Intent Classifier、Maker Knowledge、Updater、Critical modules；不依赖 HTTP server boot。
- v1.3.0：国际化（i18n）— `core/i18n.py` + `i18n/en-US.json` + `i18n/zh-CN.json`（63 翻译字符串）；支持 locale 解析、prefix fallback、占位符替换、复数辅助、线程安全；31 个测试。
- v1.4.0：完整 release 检查 + CHANGELOG.md + sprint-board 更新。
- 累计：**390/390 测试通过**。

## 2026-06-26 v1.5.0 Bug + 仓库整理

- 实际运行 `python main.py --serve --mock` 发现 4 个 bug：
  - **Bug #1** `/api/settings/runtime-info` 返回 404（待修复）
  - **Bug #2** `main.py --serve --port X` 报 "unrecognized arguments: --port"（**已修复**：新增 `--port` argparse 参数 + `create_default_app_server` port 参数）
  - **Bug #3** `--mock` 选项可能未生效（待进一步调试）
  - **Bug #4** main.py 在 Windows 下 GBK 编码读取问题（**已修复**：添加 UTF-8 文件头声明）
- 仓库整理：
  - 删除 `docs/llm-feedback/*.json`（22 个 v0.4.x 测试记录）
  - 删除 `docs/architecture/{llama-cpp-tuning, self-evolving-agent-compliance, code-review-roadmap, agent-ide-redesign, adr-0001, api-first-llm-runtime}.md`（被 v0.7.0+ 取代）
  - 删除 `docs/design/ttmevolve-maker-cockpit.md`（设计稿过期）
  - 删除 `docs/sessions/2026-06-{22,23,24}.md`（阶段性 session 笔记）
  - 删除 `docs/roadmap-v0.4.md`（被 `next-steps-roadmap.md` 取代）
  - 删除 `start-gui.bat/.ps1`、`start-practice.bat/.ps1`（旧 Electron 启动器）
  - 删除 `config.embedded.json`（旧 config）

## Last updated: 2026-06-26 08:42

## Last updated: 2026-06-26 08:43

## 2026-06-26 v1.5.1 全量运行 Bugfix + GitHub 同步准备

- 用户目标：全量运行、记录 bug、修复 bug、同步 GitHub。
- 全量验证发现并修复：
  - `main.py` 不接受 Tauri 启动传入的 `--embedded --host`，导致桌面后端启动链断；已新增 `--host` / `--embedded`，并让 embedded 启动 AppServer。
  - 前端 Settings 构建失败：type-only re-export、未使用 React import、缺少 `@tauri-apps/api`；已修复导出/import 并加入 frontend 依赖。
  - 裸跑 `pytest` 会收集 `portable/home/.../INetCache` 并权限失败；新增 `pytest.ini` 限定 `tests/`，并在测试夹具中稳定 TEMP/TMPDIR。
  - 动态工具执行路径把 AGENTS.md/generated tools 误按 Maker proxy 签名调用；Executor 现在只对 Maker proxy 传 `tool_name`，并按 handler 签名决定是否注入 `_session_id`。
  - `Config.clone()` 对测试/脚本构造的轻量 Config 缺少 `base_dir` 不够防御；已补 fallback。
  - Maker first-action guard 过度拦截普通本地文件任务；现在只在任务文本明显需要 Maker authority 时拦截本地副作用。
  - AppServer portable env 强制策略污染临时测试 config；现在仅 app-root config 强制 portable env，避免临时 storage 被 teardown 后后台 session 断裂。
  - `test_local_llm_smoke` 默认真实 GGUF 跑法不稳定且耗时；改为 `TTMEVOLVE_RUN_REAL_LOCAL_LLM=1` 显式开启。
  - Tauri config `bundle.targets` schema 形状错误，并且 resources 打包整个 live `portable/` 导致锁文件失败；改为标准 targets 数组并移除运行态 `portable/` 整目录资源。
  - Rust fast_ops bridge/commands 编译问题：私有常量、缺 `DEFAULT_HOST`、错误 Builder 泛型、devtools feature gate、BufReader 包装 `Option<TcpStream>`、BridgeHandle fallback 构造、prerelease 版本比较；均已修复。
  - GUI flow 测试启动等待过短导致 Windows 下偶发 health timeout；放宽等待。
- 最终验证：
  - `.venv\Scripts\python.exe -m pytest -q` -> **598 passed, 14 skipped**。
  - `npm.cmd --prefix frontend run build` -> passed。
  - `npm.cmd --prefix electron run build` -> passed。
  - `cargo test --manifest-path src-tauri/Cargo.toml` -> **32 passed**。
- 重要经验：全量运行必须覆盖 Python/TS/Electron/Rust 四条链路；Tauri resources 不能包含 live runtime state（cache/home/tmp/electron profile），否则构建会扫描用户状态和锁文件。

## Last updated: 2026-06-26 10:15

## 2026-06-26 v1.5.1 README/GitHub Landing Fix

- User caught that GitHub README was not updated after the full v1.5.1 validation/fix/push cycle.
- Rewrote `README.md` as readable UTF-8 content aligned with the current architecture: Tauri 2.x + Rust + WebView2 as the primary GUI, React frontend, Python App Server, Maker MCP, API-first LLM routing, and Electron only as a legacy compatibility build surface.
- Removed stale GitHub-facing launch docs for deleted legacy scripts (`start-gui.*`, `start-practice.*`) and old Electron-primary commands.
- Added latest validation evidence to README: Python `598 passed, 14 skipped`, Rust `32 passed`, frontend build passed, Electron compatibility build passed, and synced commit `a3e7626`.
- Lesson: GitHub sync is incomplete if README/release-facing docs still describe an older architecture, even when code/tests/commit/push are already complete.

## Last updated: 2026-06-26 10:41
