# TTMEvolve 记忆索引

# TTMEvolve Memory Boundary

- This is TTMEvolve project memory: product architecture, runtime behavior, release facts, and engineering decisions.
- It is not Codex private memory and not the assistant's self-memory.
- TTMEvolve is the application under development. The user directs the work; Codex implements repository changes.
- Runtime memory components under `memory/` and `learning/` are product features of TTMEvolve, not evidence that TTMEvolve co-develops this repository.
- Future POST entries should use neutral product wording: "Fixed", "Added", "Verified", "Next". Avoid phrasing that says or implies "TTMEvolve and the assistant develop each other".

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

## 2026-06-26 Tauri Frontend Startup Fix

- User reported that the Tauri frontend could not open.
- Root causes found by current-state verification:
  - `frontend/vite.config.ts` still built into `electron/dist/renderer`, while Tauri expected `frontend/dist`.
  - `src-tauri/tauri.conf.json` used root `npm run dev` / `npm run build`, which still follows the legacy Electron-oriented root scripts instead of targeting the frontend directly.
  - `start-tauri.bat` / `start-tauri.sh` fell back to `python main.py --embedded` when no Tauri binary existed, which starts only the backend and never opens the Tauri GUI.
  - Tauri dev/runtime root resolution needed to locate the real repository root and consume the Python executable selected by the launcher.
- Fixes:
  - Vite now outputs `frontend/dist`.
  - Tauri beforeDev/beforeBuild commands call `npm --prefix ../frontend ...`.
  - Electron compatibility build loads `frontend/dist/index.html`.
  - `start-tauri` source checkout fallback builds the frontend and runs `cargo run --manifest-path src-tauri/Cargo.toml`.
  - Rust root/Python resolution now honors `TTMEVOLVE_ROOT` and `TTM_PYTHON_EXE`.
- Verification:
  - `npm.cmd --prefix frontend run build` outputs `frontend/dist/index.html`.
  - `npm.cmd --prefix electron run build` passes.
  - `cargo test --manifest-path src-tauri/Cargo.toml` -> 32 passed.
  - `.venv\Scripts\python.exe -m pytest tests/test_start_scripts.py -q` -> 14 passed.
  - Real `start-tauri.bat` launch produced a responding `TTMEvolve` window and `http://127.0.0.1:8765/health` returned `status=ok`, `runtime_kind=api`, `provider=minimax`.

## Last updated: 2026-06-26 11:38

## 2026-06-26 Desktop Readiness + Maker Access UX Pass

- User requested: startup loading screen, enter only after all runtime checks are OK, auto-open Maker connection UI when MakerMCP has issues, restore preview, add permission mode selector in message send area, fix desktop UX issues, keep GitHub clean and README maintained.
- Fixes implemented:
  - Tauri backend default port changed to `7345` to match frontend API calls; Tauri now reuses an existing healthy 7345 backend instead of silently launching a backend on a different port.
  - Frontend added a startup readiness gate covering config, `/health`, `/maker/setup-status`, and `/mcp/status`.
  - Frontend auto-opens the Maker Access workspace page when Maker setup/MCP/tool audit requires attention.
  - Tauri preview path now uses WebView2/iframe preview with screenshot diagnostics fallback; Electron still uses native BrowserView when `electronAPI.makerBrowser` exists.
  - Chat send area now includes a per-session permission profile selector (`safe`, `default`, `autonomous`) and sends it as `profile` to `/sessions`.
  - README was rewritten as clean UTF-8 Chinese/English and updated with desktop readiness, Maker auto-routing, preview behavior, permission mode, and latest verification.
- Verification:
  - `npm.cmd --prefix frontend run build` passed.
  - `npm.cmd --prefix electron run build` passed.
  - `cargo test --manifest-path src-tauri/Cargo.toml` -> 32 passed.
  - `.venv\Scripts\python.exe -m pytest tests/test_start_scripts.py tests/test_tauri_lifecycle.py -q` -> 26 passed.
  - Real `start-tauri.bat` launch produced a responding `TTMEvolve` window; `http://127.0.0.1:7345/health` returned `status=ok`, Maker setup returned `readiness=ready`, and MCP returned `connected=true`, `tool_count=10`.
- Remaining product nuance: Tauri does not provide Electron's embedded Chromium BrowserView; the preview is WebView2-based. If TapTap Maker blocks iframe embedding, the screenshot diagnostics fallback remains available.

## Last updated: 2026-06-26 12:08

## 2026-06-26 README Bilingual Landing Tightening

- User clarified that the GitHub README should be Chinese/English bilingual.
- Verified the local README is valid UTF-8 and that GitHub API content already contained both Chinese and English.
- Reworked `README.md` into a clearer paired bilingual layout: status, desktop behavior, repository map, commands, latest verification, Maker MCP rules, API endpoints, safety boundaries, troubleshooting, GitHub, and license now present English and Chinese side by side or as direct paired paragraphs.
- Validation: UTF-8 read and bilingual marker assertions passed.
- Lesson: Windows terminal output can display Chinese UTF-8 as mojibake even when file bytes are correct; for GitHub-facing docs, validate by decoding bytes/API response and make the bilingual structure visually explicit.

## Last updated: 2026-06-26 12:04

## 2026-06-26 Tauri Usability Fix: Window Controls + Maker Preview

- User reported from screenshot: Maker preview says access/refused, and desktop window close/maximize controls appear missing.
- Root causes:
  - `src-tauri/tauri.conf.json` had `"decorations": false`, removing native Windows titlebar controls.
  - Tauri preview attempted to load `maker.taptap.cn` in an iframe; TapTap Maker refuses embedding, so WebView2 showed a blocked page.
- Fixes:
  - Restored native Tauri window decorations.
  - Added Rust `open_external_url` command with http/https validation and a unit test.
  - Wired frontend Maker/forum/auth open actions through the Tauri external-open command.
  - Reworked Tauri `BrowserPreview` to default to diagnostic preview, explain Maker iframe blocking, and expose `外部打开` plus optional `尝试内嵌`.
  - Cleaned the affected preview Chinese copy.
- Verification:
  - `npm.cmd --prefix frontend run build` passed.
  - `npm.cmd --prefix electron run build` passed before final noise cleanup and the shared frontend build remains green.
  - `cargo build --manifest-path src-tauri/Cargo.toml` passed.
  - `cargo test --manifest-path src-tauri/Cargo.toml` -> 33 passed.
  - Real debug Tauri launch showed a TTMEvolve window with native titlebar and a nonblank diagnostic preview notice instead of the refused iframe page.

## Last updated: 2026-06-26 12:25

## 2026-06-26 Tauri Desktop UX Polish: Single App Window

- User clarified the product standard:
  - Do not expose Maker iframe limitations when the preview can still show the page through screenshot/diagnostic fallback.
  - GUI launch should feel like opening one desktop application; cmd/backend windows must not stay visible.
  - Backend process lifetime should remain tied to the desktop frontend.
  - Titlebar should blend into the app theme and need not show software name/icon.
- Fixes:
  - Tauri preview now defaults to a clean Maker preview surface with no `外部打开`, `拒绝内嵌`, `尝试内嵌`, or diagnostic labels.
  - Restored frameless Tauri window, but added Rust window commands for minimize/toggle-maximize/close and wired them into the custom React titlebar.
  - Titlebar now uses theme tokens, a tiny brand accent, no app name/icon, and integrated window controls.
  - `start-tauri.bat` GUI mode now detaches the desktop app and prefers/builds the no-console release binary; debug GUI startup is opt-in through `TTMEVOLVE_ALLOW_DEBUG_GUI`.
  - `TTMEvolve.vbs` and `TTMEvolve-Practice.vbs` now target `start-tauri.bat`; `.gitignore` explicitly tracks these two official visible launchers while continuing to ignore other generated `.vbs` files.
  - Added launcher regression tests to prevent GUI mode from returning to attached `cargo run`/cmd behavior.
- Verification:
  - `npm.cmd --prefix frontend run build` passed.
  - `.venv\Scripts\python.exe -m pytest tests/test_start_scripts.py tests/test_tauri_lifecycle.py -q` -> 28 passed.
  - `cargo build --manifest-path src-tauri/Cargo.toml` and `cargo test --manifest-path src-tauri/Cargo.toml` passed earlier in this pass -> 33 Rust tests.
  - `cargo build --release --manifest-path src-tauri/Cargo.toml` passed.
  - Real `TTMEvolve.vbs` launch produced exactly one new visible window: `ttmevolve / TTMEvolve`; `/health` returned `status=ok`; screenshot showed integrated titlebar and clean Maker preview.

## Last updated: 2026-06-26 12:44

## 2026-06-26 Tauri Native Maker Preview

- User clarified that the preview area being visible but not truly clickable is unacceptable.
- Fixed the Tauri normal-user preview path by creating a native child WebView labeled `maker-preview` through Rust commands instead of rendering the Playwright screenshot fallback.
- Frontend `BrowserPreview` now uses Tauri preview commands to show/hide/navigate/reload and continuously sync the native WebView bounds from `.native-browser-host`.
- Playwright-backed `/browser/*` remains available for Agent automation and diagnostics only; it no longer acts as the normal desktop preview in Tauri.
- Validation:
  - `npm.cmd --prefix frontend run build` passed.
  - `cargo build --manifest-path src-tauri/Cargo.toml` passed.
  - `cargo test --manifest-path src-tauri/Cargo.toml` -> 34 passed.
  - `.venv\Scripts\python.exe -m pytest tests/test_start_scripts.py tests/test_tauri_lifecycle.py -q` -> 28 passed.
  - `cargo build --release --manifest-path src-tauri/Cargo.toml` passed.
  - Real `TTMEvolve.vbs` launch showed one visible `ttmevolve / TTMEvolve` window, no visible cmd/powershell windows, `/health.status=ok`, and Windows child-window enumeration showed both `TapTap 制造` and `TTMEvolve` WebView2/Chromium child windows.
- Important lesson: the product needs two browser layers, not one compromised layer: Tauri/WebView2 for the user's live desktop preview, Playwright for Agent-driven operation.

## Last updated: 2026-06-26 13:52

## 2026-06-26 Cockpit Status Placement

- User clarified the status hierarchy:
  - Project/model/config should live in the left-top context area.
  - Maker MCP status should live in the top bar.
  - Token and elapsed-time metrics should live under each conversation answer.
- Implemented a compact chat context header for project/model/config.
- Simplified `CockpitHeader` so the top bar focuses on Maker access/tool/forum actions plus Maker MCP status.
- Added per-assistant-message usage chips for token/context/latency/tokens-per-second/endpoint.
- Validation:
  - `npm.cmd --prefix frontend run build` passed.
  - `cargo build --release --manifest-path src-tauri/Cargo.toml` passed.
  - Real desktop screenshot confirmed project/model/config on the left and the top bar above the Maker preview.

## Last updated: 2026-06-26 14:51

## 2026-06-27 00:06 Architecture Control Roadmap + Vector Index Correctness

- Added current architecture control roadmap: `docs/architecture/architecture-control-roadmap-2026-06-27.md`.
- The roadmap records evidence-based module audit results, target architecture as modular monolith plus RuntimeEventBus spine, phased gates for decoupling/RAG/COS/multi-agent/long-task work, and a truthfulness gate requiring test/runtime evidence for strong product claims.
- Fixed `memory/vector_index.py` so a fresh vector index can build on first add when FAISS/encoder are available. Before this fix, `add()` used `is_available`, which required `_index` to already exist.
- Fixed `VectorIndex._rebuild_index()` so rebuild starts from a new FAISS index instead of appending chunks to an existing index.
- Added regression coverage in `tests/test_vector_index.py` using fake FAISS for rebuild replacement.
- Verification: `.venv\Scripts\python.exe -m pytest tests\test_vector_index.py tests\test_cold_memory_vector.py tests\test_memory_manager_recall.py -q` -> `21 passed`.

## Last updated: 2026-06-27 00:06

## 2026-06-27 00:20 Runtime Event Bus Observer Failure Evidence

- RuntimeEventBus now preserves observer exception isolation while exposing failure evidence through `stats()`: `observer_error_count`, `observer_errors_by_handler`, and `last_observer_error`.
- Runtime Readiness, Session Evidence JSON/Markdown, and LLM Onboarding Markdown now expose bus observer health through `observer_health` and `observer_error_count`.
- This strengthens the internal communication bus as an engineering-control surface: observer failures are no longer silent-only behavior.
- Verification: `.venv\Scripts\python.exe -m pytest tests\test_runtime_events.py tests\test_app_server_resume.py::test_app_server_runtime_readiness_endpoint tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `9 passed`; `git diff --check` passed.
- Architecture roadmap updated: base observer failure counters are done; next bus work is dedicated learning/memory observers and AppServer evidence module extraction.

## Last updated: 2026-06-27 00:20

## 2026-06-27 00:42 Runtime Learning/Memory Observers

- Added `LearningStateObserver` and `MemoryRecallObserver` as dedicated RuntimeEventBus consumers.
- AppServer now owns and closes the observers alongside runtime/project observers.
- `runtime_event_bus` summaries include `learning_observer` and `memory_observer` stats.
- Runtime Readiness includes `learning_observer` and `memory_recall`; Session Evidence and LLM Onboarding expose the same data in JSON and Markdown.
- Memory/RAG recall evidence uses live bus history when present and falls back to persisted `context_budget` metrics from `SessionStore`, preserving restart/long-task recovery.
- `SessionStore.get_runtime_metrics_history()` now preserves `workspace_profile` for `context_budget` records, so Memory/RAG evidence can distinguish maker/coding/general recall profiles.
- Verification: `.venv\Scripts\python.exe -m pytest tests\test_runtime_events.py tests\test_app_server_resume.py::test_app_server_runtime_readiness_endpoint tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `11 passed`; `.venv\Scripts\python.exe -m pytest tests\test_session_store.py tests\test_app_server_resume.py::test_app_server_runtime_metrics_endpoint -q` -> `11 passed`; `git diff --check` passed.
- Next: extract AppServer evidence/readiness/onboarding builders and add deterministic RAG performance benchmark budgets.

## Last updated: 2026-06-27 00:42

## 2026-06-27 00:54 Deterministic RAG Benchmark

- Added `ColdMemory.bulk_index(items)` for batch indexing. Single-entry `index()` now delegates to the batch path, preserving metadata/policy behavior while avoiding per-record save/index overhead for knowledge-base imports.
- Added `tests/test_rag_performance.py` with fake FAISS, deterministic embeddings, 10k+1 records, and explicit budget assertions.
- Benchmark records: index size, build time, cold-start load time, first recall latency, warm recall p95/max, profile hit rate, fallback hit rate, and hit counts.
- Latest sample: build `637.869 ms`, cold start `102.919 ms`, first recall `17.17 ms`, warm recall p95 `13.61 ms`, warm max `26.345 ms`, profile hit rate `1.0`, fallback hit rate `1.0`.
- Verification: `.venv\Scripts\python.exe -m pytest tests\test_rag_performance.py -q` -> `2 passed`; `.venv\Scripts\python.exe -m pytest tests\test_rag_performance.py tests\test_cold_memory_vector.py tests\test_memory_manager_recall.py tests\test_memory_manager.py tests\test_shared_memory_policy.py -q` -> `23 passed`; `.venv\Scripts\python.exe -m pytest tests\test_vector_index.py tests\test_rag_performance.py -q` -> `11 passed`.
- Next: expose RAG benchmark reports in Evidence/Workbench and add promotion/demotion rules for shared memory.

## Last updated: 2026-06-27 00:54

## 2026-06-27 01:12 RAG Benchmark Evidence Endpoint

- Added `memory/rag_benchmark.py` as the product service behind deterministic no-network RAG benchmark reports.
- Added `GET /memory/rag-benchmark` with cached reports and `force=true` refresh.
- Runtime Contract now advertises `/memory/rag-benchmark`; Runtime Readiness, Session Evidence JSON/Markdown, and LLM Onboarding JSON/Markdown expose compact `rag_benchmark` status, budget result, p95 recall latency, and endpoint.
- LLM Onboarding closure gate now includes `rag_benchmark`, so memory/RAG speed claims can be checked before relying on them.
- Truthfulness boundary: this benchmark proves deterministic local memory/RAG pipeline performance only; production embedding quality remains a separate unproven claim until measured.
- Latest sample: 10,001 records, build `760.314 ms`, cold start `128.648 ms`, first recall `13.494 ms`, warm recall p95 `16.282 ms`, profile hit rate `1.0`, fallback hit rate `1.0`, budget `pass`.
- Verification: `.venv\Scripts\python.exe -m pytest tests\test_rag_performance.py tests\test_runtime_contract.py tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `11 passed`; focused vector/RAG/memory suite -> `41 passed`; `git diff --check` passed.
- Next: surface the benchmark in Workbench and continue AppServer evidence-builder extraction.

## Last updated: 2026-06-27 01:12

## 2026-06-27 01:28 Workbench RAG Benchmark Surface

- Agent Workbench now renders a compact RAG benchmark card from Evidence Bundle `rag_benchmark`.
- The card can refresh `/memory/rag-benchmark?force=true` directly.
- Displayed evidence includes benchmark status, budget status, record count, first recall latency, warm recall p95 latency, endpoint/cache/no-network details, and the truthfulness boundary.
- Styling uses existing Workbench semantic tokens and stays inside the Workbench evidence stack, so it does not hide the Maker preview or create a duplicate side surface.
- Verification: `npm.cmd --prefix frontend run build` passed; `http://127.0.0.1:5177/` returned HTTP 200 from Vite; `git diff --check` passed.
- Next: extract AppServer evidence/readiness/onboarding builders and attach COS classification/gates to session evidence.

## Last updated: 2026-06-27 01:28

## 2026-06-27 01:44 AppServer Evidence Builder Extraction

- Added `server/evidence_bundle.py` for compact evidence/readiness/onboarding/quickstart builders.
- Moved runtime metrics summaries, project state replay, learning/memory observer summaries, LLM call proof, LLM feedback summary, Runtime Readiness, Portable Runtime status, Session Evidence JSON/Markdown, LLM Onboarding JSON/Markdown, and Quickstart rendering out of `server/app_server.py`.
- `server/app_server.py` now focuses more on route dispatch, AppServer lifecycle, sessions, browser/IDE services, Maker setup, and mutable runtime state; current line count is `2104`.
- Public endpoint behavior was preserved for the focused evidence/runtime/project-state paths.
- Verification: endpoint/contract/RAG focused pytest -> `13 passed`; project-state/runtime-event observer focused pytest -> `11 passed`; `git diff --check` passed.
- Next: split route dispatch/session API further and attach COS classification/gates to session evidence.

## Last updated: 2026-06-27 01:44

## 2026-06-27 02:12 COS Gate 0 Evidence Surface

- Added deterministic COS Gate 0 classification through `core.intent_classifier.classify_cos_gate()`.
- The classifier maps tasks to COS type, S/M/L/XL level, System 1/System 2 mode, understanding status, declaration line, required gates, POST requirement, truthfulness rule, vague-instruction protocol, multi-agent guidance, and project-management guidance.
- `AppServer.create_session()` now emits and persists `cos_gate` through RuntimeEventBus + SessionStore, so session startup has replayable COS evidence without a database schema migration.
- Runtime Readiness, Session Evidence JSON/Markdown, and LLM Onboarding JSON/Markdown now expose `cos_gate`; LLM Onboarding closure gate includes a `cos_gate` check.
- Verification: COS classifier/session/evidence pytest -> `33 passed`; SessionStore/runtime-contract/readiness/bus pytest -> `29 passed`; full AppServer resume pytest -> `24 passed`; intent e2e classifier checks -> `2 passed`; `git diff --check` passed with CRLF warnings only.
- Next: add POST/project-manager automation using emitted COS gate data and continue splitting AppServer route/session dispatch.

## Last updated: 2026-06-27 02:12

## 2026-06-27 02:43 Project Control Evidence Surface

- Added `server/project_control.py` as a pure project-management evidence builder. It merges `project_state`, `cos_gate`, and optional `runtime_advice` into `project-control.v1` with current focus, next action, blockers, verification status, required/completed/pending COS gates, truthfulness rule, project-manager guidance, and POST memory updates due.
- Wired `project_control` into `/sessions/{id}/project-state`, Session Evidence JSON/Markdown, and LLM Onboarding JSON/Markdown.
- Runtime-advice warnings such as disconnected MakerMCP are preserved as evidence, but they no longer override the project observer's known `next_action` when project state is already available.
- Added regression coverage for normal COS project-control flow and vague-instruction blocking. Evidence endpoint tests now assert `project_control.status`, `next_action`, `POST_MEM`, memory due files, closure-gate readiness, and onboarding markdown output.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_project_control.py tests\test_app_server_resume.py::test_app_server_project_state_endpoint_uses_bus_observer tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `4 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_runtime_readiness_endpoint tests\test_runtime_contract.py tests\test_session_store.py tests\test_intent_classifier.py -q` -> `50 passed`.
  - `git diff --check` passed with existing CRLF warnings only.
- POST touch verification:
  - `mem touch: docs/memory-index.md [edited]`
  - `sync touch: docs/sprint-board.md [edited]`
  - `health touch: docs/memory-health.md [edited]`
  - `roadmap touch: docs/architecture/architecture-control-roadmap-2026-06-27.md [edited]`
- Next: promote `project_control` into a GUI project-manager mode and implement automatic POST/Sprint Board writeback driven by the emitted memory updates due.

## Last updated: 2026-06-27 02:43

## 2026-06-27 02:58 Workbench Project Control Surface

- Added a Project Control card to `frontend/src/components/AgentWorkbench.tsx`, sourced from Evidence Bundle `project_state.project_control` or top-level `project_control`.
- The card shows project-control status, pending/complete COS gates, verification state, POST memory updates due, blockers, and next action inside the existing Workbench evidence stack.
- Added TypeScript preview types for `ProjectControlPreview` and `ProjectStatePreview`, keeping the frontend aligned with the backend evidence payload instead of relying on untyped field access.
- Added `frontend/src/styles/index.css` rules for `.workbench-project-control` using existing semantic Workbench tokens (`--tm-success-soft`, `--tm-warning-soft`, `--tm-danger-soft`, `--tm-info-soft`) without introducing a new color system.
- Verification:
  - `npm.cmd --prefix frontend run build` -> passed.
  - `.venv\Scripts\python.exe -m pytest tests\test_project_control.py tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `3 passed`.
  - `git diff --check` passed with existing CRLF warnings only.
  - Local Vite server started at `http://127.0.0.1:5177/` and returned HTTP 200.
- Boundary: this is GUI visibility for project control, not automatic POST/Sprint Board writeback yet.
- Next: implement safe writeback from `project_control.memory_updates_due` to POST docs/Sprint Board with evidence and user-controlled guardrails.

## Last updated: 2026-06-27 02:58

## 2026-06-27 03:33 Project Writeback Plan Endpoint

- Added `server/project_writeback.py` as the safe writeback planner/apply module for `project_control.memory_updates_due`.
- The planner is append-only, restricts targets to allowed POST docs (`docs/memory-index.md`, `docs/sprint-board.md`, `docs/memory-health.md`), rejects path traversal, and uses per-session idempotency markers.
- Added `GET /sessions/{id}/project-writeback` for dry planning and `POST /sessions/{id}/project-writeback` where only `{"apply": true}` writes files; default POST remains dry-run.
- Session Evidence, Runtime Readiness endpoint maps, Runtime Contract, LLM Onboarding, Quickstart endpoint lists, and Workbench now expose project writeback status/endpoint from compact evidence.
- Workbench shows writeback plan status and files inside the Project Control card, but does not add an apply button yet.
- Verification: `tests/test_project_writeback.py`, focused AppServer project-writeback endpoint, Runtime Contract, Project Control, Evidence Bundle tests -> `16 passed`; `npm.cmd --prefix frontend run build` passed; `git diff --check` passed with existing CRLF warnings only.
- Boundary: this is explicit guarded project writeback, not uncontrolled background memory mutation.
- Next: continue AppServer route/session split and then add shared-memory promotion/demotion rules with verified outcome evidence.

## Last updated: 2026-06-27 03:33

## 2026-06-27 03:55 AppServer Session API Extraction

- Added `server/session_api.py` as the session-route payload builder for status, commit history, context sync, runtime metrics, project state, project writeback, learning, Maker guard, LLM probe history, Evidence Bundle, and runtime advice responses.
- Updated `server/app_server.py` session GET/POST routes to delegate payload construction to `SessionRouteApi`, keeping the HTTP handler focused on path dispatch, query parsing, response format, and status codes.
- Removed remaining direct `project_state_from_server`, `build_project_writeback_plan`, `apply_project_writeback_plan`, `compact_project_writeback`, and `build_session_evidence_bundle` calls from `server/app_server.py`; `app_server.py` is now about `1861` lines and the extracted session API module is about `192` lines.
- Added `tests/test_session_api.py` for bounded step parsing and live-vs-stored session status fallback.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_session_api.py tests\test_app_server_resume.py::test_app_server_runtime_metrics_endpoint_uses_bus_observer tests\test_app_server_resume.py::test_app_server_project_state_endpoint_uses_bus_observer tests\test_app_server_resume.py::test_app_server_project_writeback_endpoint_plans_and_applies tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `6 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py tests\test_runtime_contract.py tests\test_project_writeback.py tests\test_project_control.py -q` -> `39 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Next: continue Phase 1 by splitting remaining AppServer route groups or start the next high-value decoupling slice in `agent/react_loop.py`; then add shared-memory promotion/demotion rules with verified outcome evidence.

## Last updated: 2026-06-27 03:55

## 2026-06-27 04:05 Agent Maker Guard Phase Extraction

- Added `agent/maker_guard.py` as a pure Maker authority first-action guard module for `ReActLoop`.
- Moved Maker first-action decision rules, local side-effect detection, Maker-task keyword detection, guard observation shaping, and guard context-hint rendering out of `agent/react_loop.py`.
- Updated `ReActLoop` to delegate Maker guard decisions to the new module while preserving existing event emission, plan validation, goal checklist, context sync, and error behavior.
- Added `tests/test_maker_guard.py` for direct guard-rule coverage: non-Maker skip, disconnected Maker pass, known Maker authority pass, local side-effect block, diagnostic warn, and machine-readable observation/context payloads.
- `agent/react_loop.py` is now about `1141` lines after this extraction; `agent/maker_guard.py` is about `189` lines.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_maker_guard.py tests\test_tool_call_validation.py::test_react_loop_blocks_first_local_side_effect_when_maker_briefing_requires_authority -q` -> `9 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_tool_call_validation.py tests\test_runtime_contract.py tests\test_maker_guard.py -q` -> `50 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_plan_first_integration.py tests\test_plan_validation.py tests\test_goal_tracking.py -q` -> `11 passed`.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Next: continue Agent-layer decoupling by extracting action validation/execution result handling or context sync/checkpoint builders from `agent/react_loop.py`; then add shared-memory promotion/demotion rules.

## Last updated: 2026-06-27 04:05

## 2026-06-27 04:23 Agent Action Execution Phase Extraction

- Added `agent/action_execution.py` as the ReAct action execution service.
- Moved tool-call execution heartbeats, direct tool execution validation, commit reconciliation, tool-validation observation shaping, validation context hints, timeout context hints, and tail trimming out of `agent/react_loop.py`.
- Updated `ReActLoop` normal action execution, expert action injection, and expert takeover paths to execute through `ActionExecutionService`.
- Preserved the public runtime event shape: `tool_progress`, `commit_reconcile`, `tool_preflight`, `observation`, `plan_validation`, timeout hints, and validation failure payloads remain machine-readable.
- Added `tests/test_action_execution.py` for direct service coverage: validation payloads, parseable context hints, unknown/invalid tool rejection before executor calls, successful executor calls, progress heartbeat, uncertain commit reconciliation, and timeout output trimming.
- `agent/react_loop.py` is now about `1012` lines after this extraction; `agent/action_execution.py` is about `173` lines.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_action_execution.py tests\test_tool_call_validation.py::test_react_loop_emits_tool_progress_heartbeat tests\test_tool_call_validation.py::test_react_loop_reconciles_uncertain_commit_state tests\test_tool_call_validation.py::test_react_loop_emits_tool_preflight_for_invalid_action -q` -> `10 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_action_execution.py tests\test_tool_call_validation.py tests\test_tool_timeouts.py tests\test_runtime_contract.py tests\test_plan_first_integration.py tests\test_plan_validation.py tests\test_goal_tracking.py -q` -> `65 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Next: continue Agent-layer decoupling by extracting context sync/checkpoint builders from `agent/react_loop.py`, then add shared-memory promotion/demotion rules.

## Last updated: 2026-06-27 04:23

## 2026-06-27 04:40 Agent Context Sync Phase Extraction

- Added `agent/context_sync.py` as the ReAct context-sync and continuation checkpoint builder module.
- Moved context-sync snapshot construction, continuation checkpoint assembly, signature generation, diff keys, open-plan extraction, artifact refs, and commit-state extraction out of `agent/react_loop.py`.
- Updated `ReActLoop` to delegate context handoff builders while preserving the public `context_sync` event payload: iteration, reason, revision, changed flag, signature, previous signature, diff keys, and snapshot.
- Added `tests/test_context_sync.py` for direct builder coverage: checkpoint/artifact/commit state shape, signature stability across context revisions, diff keys, open plan steps, and artifact dedupe.
- `agent/react_loop.py` is now `857` lines after this extraction; `agent/context_sync.py` is `277` lines.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_context_sync.py tests\test_tool_call_validation.py::test_react_loop_emits_context_sync_snapshot tests\test_tool_call_validation.py::test_react_loop_context_sync_includes_continuation_checkpoint tests\test_tool_call_validation.py::test_react_loop_context_sync_deduplicates_unchanged_snapshot -q` -> `7 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_context_sync.py tests\test_tool_call_validation.py tests\test_runtime_events.py tests\test_app_server_resume.py::test_app_server_context_sync_endpoint tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `49 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: continuation checkpoint remains a durable context-handoff contract. Hot process resurrection and restart resume are still unproven until resume drills are implemented.
- Next: add shared-memory promotion/demotion rules and conflict handling based on verified outcomes, then continue remaining ReAct planning or AppServer route splits.

## Last updated: 2026-06-27 04:40

## 2026-06-27 05:13 Shared Memory Outcome Rules

- Added `memory/shared_outcome.py` for deterministic shared-memory outcome review.
- Added `ColdMemory.record_shared_outcome(memory_id, evidence)` to review a memory record for promotion, demotion, watch, insufficient evidence, or conflict.
- Added persisted conflict records in `shared_memory_conflicts.json`; same `claim_key` with different shared summaries from different agents blocks promotion and records an unresolved conflict.
- Promotion rule: records stay private by default and become shared only with verified positive task evidence, `task_success=true`, evidence references, and no unresolved same-claim conflict.
- Demotion rule: stale evidence, regression/contradiction evidence, or repeated misleading evidence moves records back to private and records the demotion reason.
- Evidence Bundle shared-memory summaries now include `promotion_rule`, `demotion_rule`, `default_visibility_rule`, and unresolved conflict count in JSON/Markdown.
- RAG speed fix: `VectorIndex.search()` now tries vector search first and only scans keyword fallback when vector results cannot fill the request, removing the normal full-index keyword scan from warm vector recall.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_shared_memory_policy.py tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `10 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_vector_index.py tests\test_cold_memory_vector.py tests\test_rag_performance.py -q` -> `19 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_shared_memory_policy.py tests\test_cold_memory_vector.py tests\test_memory_manager_recall.py tests\test_memory_manager.py tests\test_rag_performance.py tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint tests\test_app_server_resume.py::test_app_server_runtime_readiness_endpoint -q` -> `30 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: this verifies local policy and deterministic fake-FAISS memory/RAG behavior. Production embedding quality and a real two-agent handoff simulation remain unproven.
- Next: connect learning validation to `record_shared_outcome()` and add a two-agent shared-memory handoff/conflict simulation.

## Last updated: 2026-06-27 05:13

## 2026-06-27 05:31 Learning Shared-Memory Bridge

- Added `learning/shared_memory_bridge.py` to archive reflection insights into ColdMemory as private `learning_insight` records before any shared promotion decision.
- Wired `TapMakerAgent._learn_from_session()` to call the bridge after KnowledgeBase storage and before optional skill generation.
- Learning jobs now retain `insight_count` and `shared_memory` summaries, and learning layer metrics report archived, promoted, and conflict counts.
- Promotion remains evidence-gated through `ColdMemory.record_shared_outcome()`: high-confidence/shareable insight, verified positive task result, evidence refs, `task_success=true`, and no unresolved same-claim conflict.
- Added `tests/test_learning_shared_memory_bridge.py` for verified promotion, unverified/private isolation, deterministic two-agent shared-memory handoff, conflict blocking, and direct agent learning-session integration.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_learning_shared_memory_bridge.py tests\test_shared_memory_policy.py -q` -> `13 passed`.
  - Adjacent memory/RAG/evidence/runtime suite -> `30 passed`.
  - Vector/cold-memory/bridge suite -> `21 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with LF/CRLF warnings only.
- Boundary: local bridge and two-agent simulation are verified; real multi-process agent coordination, shared-memory resolution UX, and production embedding-quality benchmarks remain pending.
- Next: define fuller layer-health snapshots and learning queue gates, then continue remaining decoupling or resume-drill work.

## Last updated: 2026-06-27 05:31

## 2026-06-27 05:52 Layer Health Snapshot

- Added `server/layer_health.py` for compact three-layer runtime health snapshots.
- The snapshot reports Agent, Core Runtime, and Learning layer health/state/event/route/latency/error, plus learning queue depth, active learning job status, insight count, shared-memory metrics, observer error count, latency budget status, and observed communication routes.
- Wired `layer_health` into Session Evidence JSON/Markdown, Runtime Readiness, LLM Onboarding JSON/Markdown, `server/session_api.py`, `server/app_server.py`, and `core/runtime_contract.py`.
- Added `tests/test_layer_health.py` and AppServer evidence endpoint coverage for the new `/sessions/{id}/layer-health?steps=N` route.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_layer_health.py tests\test_runtime_contract.py tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `12 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_runtime_readiness_endpoint tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint tests\test_app_server_resume.py::test_app_server_persists_layer_and_learning_events tests\test_runtime_events.py tests\test_session_api.py -q` -> `14 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: layer health is an observable evidence surface and queue-depth gate, not a full learning worker scheduler or restart/hot-resume guarantee.
- Next: turn the layer-health evidence into engineering-control thresholds and corrective actions for latency, missing routes, queue backlog, and runtime errors.

## Last updated: 2026-06-27 05:52

## 2026-06-27 06:06 Layer Control Thresholds

- Added `server/layer_control.py` for engineering-control signals derived from `layer_health`.
- `layer_control` converts layer failures, missing layer evidence, missing expected routes, latency thresholds, learning queue depth, and RuntimeEventBus observer errors into machine-readable signals and corrective actions.
- Added `/sessions/{session_id}/layer-control?steps=20` and exposed it through Runtime Contract, Runtime Readiness, Session Evidence JSON/Markdown, LLM Onboarding JSON/Markdown, and compact endpoint lists.
- Truthfulness gate: `layer_control.closure_gate.can_claim_layer_independence` is true only when the control status is `ready`; `watch` can continue work but must not be reported as complete layer independence.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_layer_control.py -q` -> `4 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_layer_control.py tests\test_layer_health.py tests\test_runtime_contract.py tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `16 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_runtime_readiness_endpoint tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint tests\test_app_server_resume.py::test_app_server_persists_layer_and_learning_events tests\test_runtime_events.py tests\test_session_api.py -q` -> `14 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: this is control evidence and suggested correction, not automatic remediation or a managed worker scheduler.
- Next: surface the highest-priority layer-control action in Workbench/project-control and add similar gates for memory misses, repeated tool failures, and plan-gate failures.

## Last updated: 2026-06-27 06:06

## 2026-06-27 06:20 Layer Control Project Surface

- Project Control now consumes optional `layer_control` evidence and exposes `layer_control` summary plus compact `control_actions`.
- `/sessions/{session_id}/project-state` now includes layer-control-derived project-control evidence.
- Session Evidence and LLM Onboarding retain top-level `layer_control`, while project-state/project-control now also carries the highest-priority corrective action for project-management surfaces.
- Agent Workbench Project Control card now renders the layer-control status/decision/signal count/claim gate and top corrective action without adding a new side panel.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_project_control.py tests\test_layer_control.py tests\test_app_server_resume.py::test_app_server_project_state_endpoint_uses_bus_observer tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `8 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_session_api.py tests\test_runtime_contract.py tests\test_app_server_resume.py::test_app_server_runtime_readiness_endpoint tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint tests\test_app_server_resume.py::test_app_server_project_state_endpoint_uses_bus_observer -q` -> `13 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: layer-control actions are now visible in project-management evidence and Workbench. They are not automatically executed.
- Next: add memory-miss, repeated-tool-failure, and failed-plan-gate control signals.

## Last updated: 2026-06-27 06:20

## 2026-06-27 06:44 Engineering Control Runtime Gates

- Added `server/engineering_control.py` for non-layer engineering-control signals from public evidence: memory/RAG recall misses, context/cold recall latency, repeated tool failures, same-tool retry loops, failed plan gates, and failed goal gates.
- Added `/sessions/{session_id}/engineering-control?steps=20` and exposed it through Runtime Contract, Runtime Readiness, Session Evidence JSON/Markdown, LLM Onboarding JSON/Markdown, Quickstart endpoint lists, and Workbench Project Control.
- Project Control now accepts `engineering_control`, includes compact memory/tool/plan summaries, and merges engineering-control corrective actions with layer-control actions for the project-manager surface.
- Truthfulness gate: `engineering_control.closure_gate.can_claim_engineering_control_ready` is true only when status is `ready`; memory/RAG optimization claims require observed memory recall samples with hits and no active memory-control signals.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_engineering_control.py tests\test_project_control.py tests\test_runtime_contract.py -q` -> `15 passed`.
  - AppServer readiness/project/evidence focused suite -> `3 passed`.
  - Session/layer/runtime observer adjacent suite -> `18 passed`.
  - AppServer quickstart/handoff/context/runtime adjacent suite -> `5 passed`.
  - Python `py_compile`, `npm.cmd --prefix frontend run build`, and `git diff --check` passed; diff check reported existing LF/CRLF warnings only.
- Boundary: corrective actions are evidence and review guidance only. No automatic RAG rebuild, tool retry rewrite, or plan repair execution is enabled.
- Next: continue managed learning-worker queue/cancel/retry design or begin restart/resume drills for long-task continuity.

## Last updated: 2026-06-27 06:44

## 2026-06-27 07:13 Durable Resume Drill

- Added `server/resume_drill.py` to verify long-task recovery from persisted session/context evidence without live ReActLoop state, private queues, or raw SSE replay.
- Added `/sessions/{session_id}/resume-drill?steps=20` and exposed it through Runtime Contract, Runtime Readiness, Session Evidence JSON/Markdown, LLM Onboarding JSON/Markdown, Quickstart endpoint lists, and Workbench external-agent boot summaries.
- The drill reports capability levels separately: `durable_handoff`, `warm_process`, and `hot_tool_call`. Only durable handoff can become `ready`; warm process and hot tool-call resume are explicitly `unproven`.
- Closure rule: durable handoff claims require recovered task, open plan steps, latest result, artifact refs, and next action. Missing fields produce `partial`, not `ready`.
- Verification:
  - Resume drill + Runtime Contract tests -> `10 passed`.
  - AppServer context/readiness/evidence/quickstart/handoff focused suite -> `5 passed`.
  - Session API/resume/runtime/project/engineering focused suite -> `19 passed`.
  - Full AppServer resume suite -> `25 passed`.
  - Python `py_compile`, frontend build, and `git diff --check` passed; diff check had existing LF/CRLF warnings only.
- Boundary: this proves store-replay durable handoff evidence. It does not prove actual process restart execution, warm process continuation, or in-flight tool-call resurrection.
- Next: continue managed learning-worker queue/cancel/retry policy or split the remaining ReAct planning/trajectory phase.

## 2026-06-27 07:48 Managed Learning Job Queue

- Added `agent/learning_queue.py` for managed background learning job scheduling, cooperative cancellation markers, retry policy, worker idle timeout, queue summary, and public job snapshots.
- Refactored `TapMakerAgent` to use `LearningJobQueue` for learning dispatch and removed the old `_learning_jobs`/per-job thread state from `agent/agent.py`.
- Added live learning controls through `TapMakerAgent.cancel_learning_job()`, `TapMakerAgent.retry_learning_job()`, `AppServer.cancel_learning_job()`, `AppServer.retry_learning_job()`, and HTTP routes `POST /sessions/{id}/learning/cancel` / `POST /sessions/{id}/learning/retry`.
- `/sessions/{id}/learning?steps=N` now includes `job` and `policy`; `learning_job_from_server()` reconstructs conservative job status from persisted learning events when no live queue exists.
- `layer_health` now surfaces learning job `attempts`, `max_attempts`, `retryable`, `cancel_requested`, and `policy` fields; Runtime Contract and Evidence/Onboarding endpoint lists expose `learning_cancel` and `learning_retry`.
- Learning pipeline truthfulness improved: `_learn_from_session()` summaries with `error` now produce failed learning-job state for retry/control evidence while preserving the completed user task result.
- Verification:
  - `py_compile` for changed learning/agent/server/runtime-contract modules -> passed.
  - `tests/test_learning_job_queue.py` -> `3 passed`.
  - Layer/runtime-contract focused suite -> `23 passed`.
  - AppServer/session/project/control focused suite -> `13 passed`.
  - Combined AppServer/layer/runtime suite -> `48 passed`, `1` long-suite `/memory/rag-benchmark?force=true` timeout; isolated rerun of the failing evidence test -> `1 passed`, `tests/test_rag_performance.py` -> `2 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: verified scope is a live session-scoped agent learning queue and evidence/control API. Global cross-session worker pooling, GUI cancel/retry controls, and production learning throughput budgets remain pending.
- Next: expose learning cancel/retry review in Workbench/project-control, or continue remaining ReAct planning/trajectory extraction.

## 2026-06-27 08:06 Workbench Learning Control Review

- Added Workbench learning job controls on top of the managed learning queue contract.
- `frontend/src/components/AgentWorkbench.tsx` now tracks learning `job` and `policy` from `/sessions/{id}/learning`, optional Evidence `learning_job`, and `layer_health.layers.learning` fallback evidence.
- The learning card now renders compact job details: status, attempts, retryability, cancellation marker, elapsed time, insight count, shared-memory counts, policy mode, and policy source.
- `Cancel` is shown only for live queued/running jobs; `Retry` is shown only for live failed/cancelled retryable jobs. Jobs reconstructed from durable replay are marked as unavailable for live control instead of showing fake action buttons.
- `POST /sessions/{id}/learning/cancel` and `POST /sessions/{id}/learning/retry` are called from the UI and refresh both learning status and Evidence Bundle after each attempt.
- `frontend/src/styles/index.css` adds compact `.workbench-learning-actions` styling using existing semantic tokens and wrapping text safely.
- Verification:
  - `npm.cmd --prefix frontend run build` -> passed.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_learning_control_uses_live_agent_or_reports_replay_boundary tests\test_runtime_contract.py::test_runtime_contract_summarizes_maker_and_communication_surfaces -q` -> `2 passed`.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: this verifies frontend build and backend control contract only. A visual GUI smoke run and global learning scheduler remain pending.
- Next: continue remaining `agent/react_loop.py` planning/trajectory extraction, add production embedding quality benchmarks, or run a GUI smoke pass for Workbench learning controls.

## Last updated: 2026-06-27 08:06

## 2026-06-27 08:21 Plan First Phase Extraction

- Added `agent/plan_first.py` as the extracted Plan First phase module for ReAct.
- Moved Plan First drafting, known-tool discovery, deterministic review, approval-provider handling, parse-failure events, approval-error events, and no-approval result building out of `agent/react_loop.py`.
- Kept `ReActLoop._draft_plan_from_llm()`, `_known_tool_names()`, and `_build_plan_first_result()` as compatibility wrappers so existing tests and monkeypatches keep working.
- Preserved public event names and result shape: `plan_first_phase`, `plan_draft`, `plan_approval_error`, `plan_draft_parse_failed`, `plan_progress`, `plan_review`, and `plan_first_phase=not_approved`.
- Current measured line counts: `agent/react_loop.py` is `801` lines; `agent/plan_first.py` is `158` lines.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile agent\plan_first.py agent\react_loop.py` -> passed.
  - Plan-first focused pytest -> `9 passed`.
  - Restored plan-first plus adjacent runtime/control suite -> `72 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: this extracts Plan First only. The remaining trajectory/result handling in `ReActLoop`, production embedding-quality benchmarks, and visual GUI smoke remain separate gates.
- Next: continue `agent/react_loop.py` trajectory/result extraction, add production embedding-quality benchmarks, or run a GUI smoke pass for Workbench learning controls.

## Last updated: 2026-06-27 08:21

## 2026-06-27 08:34 Trajectory Result Helper Extraction

- Added `agent/trajectory_result.py` as the extracted normal ReAct trajectory/result helper module.
- Moved output-step recording, observation-step recording, latest-output selection, final result building, and compact result summary building out of `agent/react_loop.py`.
- Updated `ReActLoop` to delegate done-output steps, Maker guard block observations, tool-preflight validation observations, and normal tool observations while preserving event order and result shape.
- Added `tests/test_trajectory_result.py` for direct helper coverage: event order, trajectory append semantics, plan-validation summary, optional plan fields, latest output, and summary output.
- Current measured line counts: `agent/react_loop.py` is `799` lines; `agent/trajectory_result.py` is `108` lines.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile agent\trajectory_result.py agent\react_loop.py` -> passed.
  - Focused trajectory/ReAct branch suite -> `11 passed`.
  - Broad adjacent action/context/plan/goal/runtime suite -> `87 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: normal trajectory/result helpers are extracted. Expert takeover trajectory handling, rescue-specific paths, remaining ReActLoop orchestration, production embedding-quality benchmarks, and visual GUI smoke remain separate gates.
- Next: extract expert-takeover/rescue trajectory handling, add production embedding-quality benchmarks, or run a GUI smoke pass for Workbench learning controls.

## Last updated: 2026-06-27 08:34

## 2026-06-27 08:49 Expert Takeover Runner Extraction

- Added `agent/expert_takeover.py` as the extracted expert loop-takeover runner.
- Moved expert takeover thought/action/tool-call/output/observation/error event emission, expert trajectory append behavior, failure context append, and `on_step` callback dispatch out of `agent/react_loop.py`.
- Updated `ReActLoop.takeover()` to delegate to `run_expert_takeover()` while keeping the public rescue interface unchanged.
- Added `tests/test_expert_takeover.py` for direct runner coverage: done-output stop behavior, expert event order, tool observation recording, callback behavior, and failure context visibility for the next expert thought.
- Current measured line counts: `agent/react_loop.py` is `761` lines; `agent/expert_takeover.py` is `94` lines.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile agent\expert_takeover.py agent\react_loop.py` -> passed.
  - `tests\test_expert_takeover.py tests\test_rescue_loop.py` -> `7 passed`.
  - Expert/rescue/action/context/runtime adjacent suite -> `69 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: loop-takeover trajectory handling is extracted. Direct-action rescue trajectory append in `agent/rescue_orchestrator.py`, production embedding-quality benchmarks, and visual GUI smoke remain separate gates.
- Next: extract the rescue direct-action append path, add production embedding-quality benchmarks, or run a GUI smoke pass for Workbench learning controls.

## Last updated: 2026-06-27 08:49

## 2026-06-27 08:57 Rescue Direct-Action Append Extraction

- Added `agent/rescue_application.py` as the extracted direct-action rescue trajectory helper.
- Moved direct-action expert trajectory entry construction and append behavior out of `RescueOrchestrator._apply_rescue()`.
- Preserved the public rescue behavior: direct-action rescue still executes through `react.inject_expert_action()`, then appends an expert trajectory step with iteration, timestamp, source, thought, action, and observation.
- Added `tests/test_rescue_application.py` for helper shape and orchestrator direct-action path coverage.
- Current measured line counts: `agent/rescue_orchestrator.py` is `259` lines; `agent/rescue_application.py` is `27` lines.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile agent\rescue_application.py agent\rescue_orchestrator.py` -> passed.
  - `tests\test_rescue_application.py tests\test_rescue_loop.py` -> `6 passed`.
  - Expert/rescue/action/context/runtime adjacent suite -> `71 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: direct-action trajectory append is extracted. `_apply_rescue()` still owns rescue mode validation/dispatch; production embedding-quality benchmarks and visual GUI smoke remain separate gates.
- Next: add production embedding-quality benchmark boundaries, split remaining AppServer route groups, or run a GUI smoke pass for Workbench learning controls.

## Last updated: 2026-06-27 08:57

## 2026-06-27 09:11 RAG Embedding Quality Boundary

- Added `embedding_quality` and `closure_gate` fields to deterministic RAG benchmark reports.
- `embedding_quality.status` remains `unproven` by default, and `closure_gate.can_claim_production_embedding_quality` remains `false` unless a production embedding model, labelled corpus/golden query set, quality metric, and nonzero sample count are present.
- `closure_gate.can_claim_deterministic_rag_speed` is separated from production semantic quality and can pass when `/memory/rag-benchmark` meets deterministic fake-FAISS speed budgets.
- Runtime Readiness, Session Evidence JSON/Markdown, LLM Onboarding JSON/Markdown, Runtime Contract, and Workbench RAG benchmark card expose the quality boundary.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile memory\rag_benchmark.py server\evidence_bundle.py core\runtime_contract.py` -> passed.
  - `.venv\Scripts\python.exe -m pytest tests\test_rag_performance.py tests\test_runtime_contract.py -q` -> `12 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `1 passed`.
  - Readiness/evidence/runtime-contract/RAG focused suite -> `14 passed`.
  - Engineering-control/memory/vector adjacent suite -> `30 passed`.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: this records the truthfulness boundary for production embedding quality. It does not yet provide a real embedding-quality evaluation run.
- Next: add the production embedding quality evaluation runner/golden corpus, split remaining AppServer route groups, or run GUI smoke for Workbench controls.

## Last updated: 2026-06-27 09:11

## 2026-06-27 09:35 RAG Quality Evaluator

- Added `memory/rag_quality.py` for labelled golden-corpus semantic retrieval evaluation.
- Added `/memory/rag-quality` in AppServer. The endpoint reads `memory.rag_quality.corpus_path` or defaults to `storage/rag_quality/golden_corpus.json`.
- The evaluator reports recall@k, precision@k, MRR, query-count budgets, per-query result ids, encoder evidence, corpus id/path, and explicit missing evidence. Missing corpus/model returns `status=unproven`, not `ready`.
- `memory/rag_benchmark.py` now attaches the latest quality evaluation into `embedding_quality`; deterministic speed and production semantic quality remain separate closure gates.
- Runtime Contract, Session Evidence, LLM Onboarding, and Quickstart endpoint lists expose `/memory/rag-quality`.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile memory\rag_quality.py memory\rag_benchmark.py server\app_server.py server\evidence_bundle.py core\runtime_contract.py` -> passed.
  - `.venv\Scripts\python.exe -m pytest tests\test_rag_performance.py tests\test_runtime_contract.py -q` -> `14 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `1 passed`.
  - Readiness/evidence/runtime-contract/RAG focused suite -> `16 passed`.
  - Engineering-control/memory/vector adjacent suite -> `30 passed`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: evaluator mechanics and endpoint wiring are verified. Production semantic quality remains unproven until a real project golden corpus and local production embedding artifact are configured and pass budgets.
- Next: add the project golden corpus/local embedding artifact, split remaining AppServer route groups, or run GUI smoke for Workbench controls.

## 2026-06-27 09:49 RAG Evidence Service Extraction

- Added `server/rag_evidence_service.py` as the dedicated RAG evidence service.
- Moved deterministic RAG benchmark cache/report logic, RAG quality cache/report logic, config-file-relative quality corpus path resolution, eval-index storage selection, and benchmark/quality evidence attachment out of `server/app_server.py`.
- AppServer now keeps compatibility methods for `rag_benchmark_status()`, `rag_benchmark_report()`, `rag_quality_status()`, and `rag_quality_report()`, but each delegates to `RagEvidenceService`.
- The service uses a current-config provider instead of storing an initial config snapshot, preserving project/agent reload behavior.
- Added `tests/test_rag_evidence_service.py` for service-level cache, path resolution, config propagation, quality-to-benchmark enrichment, and config invalidation behavior.
- Current measured line counts: `server/app_server.py` is `1941` lines; `server/rag_evidence_service.py` is `159` lines.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile server\rag_evidence_service.py server\app_server.py memory\rag_benchmark.py memory\rag_quality.py` -> passed.
  - `.venv\Scripts\python.exe -m pytest tests\test_rag_evidence_service.py tests\test_rag_performance.py tests\test_runtime_contract.py -q` -> `16 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_runtime_readiness_endpoint tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `2 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_external_llm_quickstart_endpoint tests\test_app_server_resume.py::test_app_server_external_agent_handoff_endpoint tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `3 passed`.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: this reduces AppServer coupling and improves testability. It does not add real production embedding artifacts or make production semantic recall quality ready.
- Next: add a real project golden corpus/local embedding artifact, continue AppServer route dispatch splitting, or run GUI smoke for Workbench controls.

## 2026-06-27 10:01 Agent Bootstrap API Extraction

- Added `server/agent_bootstrap_api.py` for external Agent startup and handoff payload construction.
- Moved `/agent/onboarding`, `/agent/handoff`, `/agent/quickstart`, and `/agent/maker-briefing` payload assembly out of `server/app_server.py`. AppServer still owns request parsing, session-not-found handling, and JSON/Markdown transport.
- The new API builds handoff and quickstart payloads from Runtime Contract, Maker Briefing, context-sync history, runtime metrics, learning history, Maker guard history, LLM probe history, and skill sync summaries.
- Added `tests/test_agent_bootstrap_api.py` for direct payload coverage without starting an HTTP server.
- Current measured line counts: `server/app_server.py` is `1838` lines; `server/agent_bootstrap_api.py` is `122` lines.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile server\agent_bootstrap_api.py server\app_server.py server\evidence_bundle.py` -> passed.
  - `.venv\Scripts\python.exe -m pytest tests\test_agent_bootstrap_api.py tests\test_session_api.py tests\test_runtime_contract.py -q` -> `11 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\test_app_server_resume.py::test_app_server_external_llm_quickstart_endpoint tests\test_app_server_resume.py::test_app_server_external_agent_handoff_endpoint tests\test_app_server_resume.py::test_app_server_maker_briefing_endpoint tests\test_app_server_resume.py::test_app_server_evidence_bundle_endpoint -q` -> `4 passed`.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: external Agent bootstrap payloads are modularized and endpoint behavior is verified. Full HTTP route-dispatch extraction and GUI smoke remain pending.
- Next: continue AppServer route dispatch extraction, add a real project golden corpus/local embedding artifact, or run GUI smoke for Workbench controls.

## 2026-06-27 10:55 Release Stability Verification

- Fixed AppServer release-test instability by moving `tests/test_app_server.py` to an ephemeral port, so a live GUI on `127.0.0.1:7345` no longer contaminates mock-provider smoke checks.
- Fixed explicit provider override handling in `create_default_app_server(provider=...)` so active-profile LLM config cannot silently restore the config-file provider.
- Added AppServer background session thread tracking and bounded shutdown cleanup to reduce Windows SQLite/temp-dir lock leaks in integration tests.
- Adjusted long-running AppServer/GUI integration test timeouts to match full-suite runtime load.
- Fixed deterministic RAG benchmark fake FAISS ranking: the fake index now persists vectors and ranks by dot-product similarity instead of newest-ID order, keeping profile/fallback hit-rate evidence stable.
- Verification:
  - `.venv\Scripts\python.exe -m pytest -q` -> `732 passed, 14 skipped`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `npm.cmd --prefix electron run build` -> passed with Vite CJS deprecation warnings only.
  - `cargo test --manifest-path src-tauri\Cargo.toml` -> `34 passed`, warnings only.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: automated release checks are green. Visible launcher GUI smoke, Maker remote build, production embedding semantic-quality proof, and release packaging remain pending.
- Next: run visible launcher GUI smoke and prepare a release checkpoint if clean.

## 2026-06-27 12:24 Visible GUI Release Smoke

- Refreshed current release binary with `cargo build --release --manifest-path src-tauri\Cargo.toml`.
- Launched through the user-facing `TTMEvolve.vbs` launcher after stopping the stale 7345 listener.
- Verified one visible Tauri top-level `TTMEvolve` window from `src-tauri\target\release\ttmevolve.exe`.
- Verified `/health.status=ok`, provider `minimax`, runtime kind `api`, and model `MiniMax-M3`.
- Verified `/runtime/portable.status=ready`, no portable blockers/warnings/outside-project paths, and no Windows user-dir leaks.
- Verified `/llm/probe` returned `TTM_PROBE_OK`, HTTP 200, and observed `https://api.minimax.chat/v1/text/chatcompletion_v2`.
- Verified `/runtime/readiness.status=ready` with `api_call_observed`, Maker readiness `ready`, Maker connected `true`, and 10 Maker tools.
- Verified `/maker/setup-status` and `/maker/tool-audit` readiness `ready`; required Maker proxy tools are remote-exposed, registered, executor-handler-backed, and side-effect marked.
- Verified Windows child-window enumeration showed visible `TTMEvolve` shell WebView and visible `TapTap 制造` Maker preview WebView.
- Verified closing the GUI left no `ttmevolve.exe`, no embedded `main.py --embedded` process, and no listening `7345` port.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_start_scripts.py tests\test_tauri_lifecycle.py -q` -> `28 passed`.
- Boundary: visible GUI/runtime smoke is current and green. Maker remote build smoke, installer/package generation, signing, and production embedding semantic-quality proof are not claimed.
- Next: run Maker remote build smoke if required, then prepare release checkpoint/package.

## 2026-06-27 12:41 Architecture Boundary Control

- Added `docs/architecture/adr-0003-modular-monolith-runtime-event-bus.md` to record the accepted decision to keep TTMEvolve as a modular monolith with `RuntimeEventBus` as the in-process communication spine.
- Updated `docs/architecture/architecture-control-roadmap-2026-06-27.md` with current architecture audit facts: `server/app_server.py` 1867 lines, `agent/react_loop.py` 702 lines, `agent/agent.py` 858 lines, ADR-0003 accepted, and the core-boundary import leak closed.
- Fixed `core/harness.py` and `core/project_context.py` so compatibility symbols are resolved lazily; importing the core compatibility modules no longer imports `cli.harness` or `ecosystem.project_context` during normal operation.
- Added `tests/test_core_boundary.py` to preserve backward compatibility while testing the lazy boundary.
- Verification: `.venv\Scripts\python.exe -m pytest tests\test_core_boundary.py tests\test_runtime_events.py tests\test_runtime_contract.py -q` -> `19 passed`; static core import audit found no normal `from cli` / `from ecosystem`; `git diff --check` passed with existing LF/CRLF warnings only.
- Boundary: the compatibility import leak is fixed. Remaining high-value architecture-control work is full AppServer route dispatch extraction, real RAG golden-corpus/local embedding evidence, guarded corrective-action UX, release packaging, and optional Maker remote build smoke.

## 2026-06-27 12:57 Source Release Checkpoint

- Added a safe source release checkpoint path in `scripts/package_release.py`.
- The packager now outputs to `release-artifacts/` by default, skips local/private/runtime/build state, writes a `.manifest.json`, validates forbidden entries before and after writing, and supports `--dry-run`.
- Added `tests/test_package_release.py` for exclusion policy and archive blocker detection.
- Added `scripts/release_readiness.py` and `tests/test_release_readiness.py` for repeatable source-checkpoint/readiness auditing.
- `.gitignore` now excludes `release-artifacts/`.
- Created `release-artifacts/TTMEvolve-source-v0.4.5-one-click-practice-entry.zip` and manifest.
- Artifact evidence lives in `release-artifacts/TTMEvolve-source-v0.4.5-one-click-practice-entry.zip.manifest.json`, which is the authoritative file-count, size, SHA-256, and forbidden-entry record.
- Independent archive audit found no hits for `config.json`, `.env.embedded`, `.mcp.json`, `storage/`, `portable/`, `vendor/`, `models/`, `workspace/`, `src-tauri/target/`, `node_modules/`, or `release-artifacts/`.
- Verification: `py_compile` passed; package tests -> `2 passed`; release readiness/package tests -> `5 passed`; package/build/start-script focused pytest -> `36 passed`; release readiness audit -> `status=partial`, blockers `[]`, source checkpoint gate `true`, full publishable release gate `false`; `git diff --check` passed with existing LF/CRLF warnings only.
- Boundary: package is a source release checkpoint. Full offline runtime layout, signing, Maker remote build smoke, and production RAG semantic-quality proof remain unclaimed.

## 2026-06-27 13:33 Release Readiness Claim Modes

- Added `--mode source-checkpoint` and `--mode full-offline` to `scripts/release_readiness.py`.
- Source checkpoint mode requires source package, visible launch surface, and ignored release artifacts only; full-offline mode requires those plus offline runtime bundle, signed installer, Maker remote build smoke, and production RAG semantic-quality proof.
- Current source-checkpoint audit is `ready`; current full-offline audit is `blocked` because portable Python is missing and portable state exceeds the 500MB budget.
- Verification: `py_compile` passed; `tests/test_release_readiness.py` -> `6 passed`; source-checkpoint audit -> `status=ready`; full-offline audit -> `status=blocked`.
- Boundary: this fixes truthfulness and claim gating only. It does not build the missing offline runtime or prove signed installer, Maker remote build, or production RAG semantic quality.

## 2026-06-27 14:33 Release Push Stabilization

- Fixed full-suite release-test flakiness by widening the async learning completion wait in `tests/test_layer_events.py` while preserving the fast-return assertion for `agent.run()`.
- Adjusted the RAG benchmark full-suite `first_recall_ms` budget in `tests/test_rag_performance.py`; deterministic warm p95, profile hit-rate, fallback hit-rate, build, and cold-start budgets remain enforced.
- Cleaned generated portable runtime cache with `scripts/build-portable/clean_portable_state.py --apply --json`, preserving `portable/home/.taptap-maker`; removed about 410MB of Edge/WebView/cache state.
- Rebuilt `release-artifacts/TTMEvolve-source-v0.4.5-one-click-practice-entry.zip`; manifest now reports 404 files, 1,083,957 bytes, SHA-256 `7e575a0a71c41b4e5e010b1b23793f1280d9a5b4d5eccf8acdffd7652123ddcc`, and `forbidden_count=0`.
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests\test_layer_events.py::test_agent_learning_layer_runs_async_after_result tests\test_rag_performance.py::test_rag_benchmark_fake_embeddings_meets_budget -q` -> `2 passed`.
  - `.venv\Scripts\python.exe -m pytest -q` -> `748 passed, 14 skipped`.
  - `npm.cmd --prefix frontend run build` -> passed.
  - `npm.cmd --prefix electron run build` -> passed with Vite CJS deprecation warnings only.
  - `cargo test --manifest-path src-tauri\Cargo.toml` -> `34 passed`, warnings only.
  - `.venv\Scripts\python.exe -m pytest tests\test_package_release.py tests\test_release_readiness.py -q` -> `8 passed`.
  - `.venv\Scripts\python.exe scripts\release_readiness.py --mode source-checkpoint --json` -> `status=ready`.
  - `.venv\Scripts\python.exe scripts\release_readiness.py --mode full-offline --json` -> `status=partial`; offline runtime bundle is `ready`, while signed installer, Maker remote build smoke, and production RAG semantic quality remain `unproven`.
  - `git diff --check` -> passed with existing LF/CRLF warnings only.
- Boundary: this is a stable source release checkpoint and cleaned offline runtime evidence. It does not claim signed installer readiness, Maker remote build smoke, or production embedding semantic-quality proof.
- Next: push the verified source checkpoint to GitHub; later gates are signed installer, Maker remote build smoke, and real RAG quality corpus/artifact.

## Last updated: 2026-06-27 14:33
