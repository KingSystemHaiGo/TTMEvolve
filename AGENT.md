# TTMEvolve — 自进化 TapMaker 开发 Agent

> Agent 核心记忆文件。让 Agent 不仅能开发 TapTap Maker 游戏，还能在开发中持续学习、生成技能、自我改进。

## 当前状态

- 版本：v0.4.0-phase10 ✅ 结构优化 + 本地模型性能优化 + 全运行环境内嵌已落地
- 最新进展：
  - 后端新增 `server/browser_service.py`：Playwright 单例 Chromium、持久化 `storage/browser_profile`、导航/刷新/点击/JS 执行/截图/日志收集
  - App Server 新增 `/browser/*` 端点（info / screenshot / logs / navigate / refresh / evaluate / click）
  - Agent 新增 `browser_navigate`、`browser_click`、`browser_evaluate`、`browser_screenshot` 内置工具，共享同一浏览器实例
  - 前端 `PreviewPane` 新增「文件 / 浏览器」模式切换，`BrowserPreview` 组件支持 URL 加载、截图轮询、点击、JS 执行、console 日志
  - 依赖与安装：`requirements.txt` 加入 `playwright`；`scripts/bootstrap.py` 自动安装并执行 `playwright install chromium`
  - 新增测试 `tests/test_browser_service.py`、`tests/test_browser_endpoints.py`（未安装 Chromium 时自动跳过）
  - Phase 6 已保留：素材库、Explorer/Assets 切换、图片/音频/视频预览
  - Phase 8 已落地：专家救援闭环真实任务实测（Seasonal Festival benchmark）
    - 新增 `core/rescue_telemetry.py`：救援事件可观测性
    - `agent/rescue_orchestrator.py` 发出 `rescue_triggered` / `rescue_calling` / `rescue_action` / `rescue_applied` / `rescue_skipped` / `rescue_distilled` SSE 事件
    - `agent/rescue_trigger.py` 的 `RescueRequired` 携带触发原因
    - `agent/agent.py` 实现 `rescue.skip_if_no_expert_key` 门控
  - 新增 tool-call JSON Schema 校验 + 本地修复：
    - `agent/tool_validator.py` 轻量校验器（支持 type/required/properties/items/enum/length/range，无外部依赖）
    - `agent/tool_registry.py` 新增 `validate_action(name, params)`
    - `agent/react_loop.py` 在动作执行前校验；失败时不执行工具，把校验错误注入上下文，让 LLM 下一轮自修复，降低本地小模型畸形输出触发专家救援的概率
    - 新增 `tests/test_tool_call_validation.py`（7 项通过）
  - 新增 SQLite 会话持久化 + 事件回放：
    - `server/session_store.py` 使用 SQLite 持久化会话元数据与全部 SSE 事件
    - `server/app_server.py` 的 `Session` 在重连 `/sessions/{id}/events` 时先回放历史事件，再进入实时流
    - 新增 `GET /sessions`（会话列表）与 `GET /sessions/{id}`（会话详情）端点
    - 服务端重启后可查看已完成会话的历史与结果（暂不恢复中断中的执行状态）
    - 新增 `tests/test_session_store.py`、`tests/test_app_server_resume.py`（9 项通过）
  - Phase 10 已落地：结构优化 + 本地模型性能优化 + 全运行环境内嵌
    - `core/config.py` 承载配置，`agent/config.py` 仅做向后兼容 re-export
    - 消除 `memory/manager.py` / `memory/agents_md_index.py` 延迟导入
    - 拆分 `agent/agent.py`：`agent/builtin_tools.py` + `agent/mcp_integration.py`
    - `core/harness.py` → `cli/harness.py`，`core/project_context.py` → `ecosystem/project_context.py`
    - `agent/react_loop.py` 使用 `typing.TYPE_CHECKING`
    - 新增 `tests/conftest.py` 共享 fixtures
    - `llm/local_llm.py`：暴露 `n_batch/n_threads/use_mmap/use_mlock/flash_attn/cache_type_k/cache_type_v/turn_cache_max_entries`，新增全轮次 KV cache，异步推理线程池，per-call latency 日志
    - `llm/context_budget.py`：token 计数缓存
    - `llm/utils.py`：DeepSeek DSML tool_calls 解析
    - `memory/vector_index.py`：优先加载 `vendor/embeddings` 离线模型
    - `server/browser_service.py`：支持 `PLAYWRIGHT_BROWSERS_PATH` 离线浏览器包
    - `scripts/build_embedded.py`：收集 Python/Node/Git/wheels/模型/embedding/Chromium
    - `scripts/setup_embedded.py`：在目标机器初始化 `.venv`、环境变量、git 仓库
    - `start-embedded.bat` / `start.ps1`：优先使用 `vendor/` 内嵌运行时
    - `electron/electron-builder.yml` + `package.json`：Electron 打包配置，额外资源包含后端代码与 vendor
    - `llm/expert_protocol.py` 优化 prompt，鼓励复杂任务使用 `loop_takeover`
    - `llm/utils.py` 支持 DeepSeek DSML tool_calls 解析
    - `llm/openai_llm.py` 增大 choose_action max_tokens 以支持大文件写入
    - 新增 `tests/helpers/degraded_mock_llm.py`、`always_failing_mock_llm.py`、`scripted_expert_llm.py`
    - 新增 `tests/benchmark_tasks/seasonal_festival_task.json` 与 `tests/test_rescue_benchmark.py`：在 `taptap-maker-project` 临时副本上运行真实任务，触发真实 DeepSeek 专家救援并验证蒸馏
    - 新增 `main.py --rescue-test`：本地快速观察救援事件
- 本地模型依赖（llama-cpp-python + sentence-transformers + faiss-cpu 等）已安装；`python main.py --provider local` 实测跑通，MiniCPM5-1B 模型 2.3s 加载完成
- 阶段：v0.4 Agent 底座升级中
- 目标：三层架构跑通（Agent 层 / 核心运转层 / 学习转化层），并支持跨生态兼容
- LLM：
  - 默认本地 `MiniCPM5-1B-Q4_K_M-GGUF`（懒加载 + system KV cache + `ContextBudgetManager` + thinking/no-thinking 混合模式）
  - API 兜底：通用 OpenAI 兼容接口，默认 `DeepSeek`，也支持 `OpenAI` / `Claude` / `Mock`
  - Mock 模式已实现零依赖懒加载，网络不通时也能启动测试
- 启动：单一入口 `start.bat`，自动检测/准备环境：
  - 已预置 `vendor/wheels/` + `models/` 时直接本地加载
  - 未预置且联网时自动调用 `scripts/prepare_offline_env.py` 下载（清华 PyPI + ModelScope）
  - 无本地环境且无网络时 fallback Mock
- 国内镜像：PyPI 走清华 tuna，模型走 ModelScope
- 桌面级运行：
  - App Server（`server/app_server.py`）基于 stdlib HTTP + SSE
  - CLI（`main.py`）是薄客户端，自动连接后台 Server
  - Electron + React + Vite GUI，左侧聊天 + 右侧 IDE（文件树/编辑器/预览）
  - 新增 `start-gui.bat` / `start-gui.ps1`：一键启动 Electron 桌面窗口；`start.bat --gui` 也可打开 GUI
  - Electron 主进程自动启动 Python 后端（`server/electron_entry.py`），关闭窗口时停止后端
- 安全：
  - Codex 式沙箱：`read-only` / `workspace-write` / `danger-full-access`
  - 审批策略：`on-request` / `never` / `always`
  - 配置 Profile：`default` / `safe` / `autonomous`
  - IDE 写操作同样受 `Sandbox` 路径约束，`read-only` profile 下会被拒绝
- 自进化：
  - `core/resource_registry.py` + `core/evolution_protocol.py` 实现资源版本化与修改提案闭环
  - 技能生成后自动注册到资源表
  - 修复成功后沉淀故障模式到 `storage/fault_patterns.jsonl`
- 跨生态兼容：
  - `ecosystem/` 适配 Hermes / OpenClaw / Claude Code / Codex
  - `scripts/import_mcp_config.py` 导入外部 MCP 配置
  - `scripts/export_skills.py` 导出 skills 到各生态
- 专家救援教学闭环：
  - 本地模型为主，外部 LLM API 作为专家智脑
  - 触发条件：连续失败/重复动作/迭代耗尽/健康降级
  - 救援动作：thought_injection / direct_action / loop_takeover
  - 救援成功后自动蒸馏为技能（skills/generated）与知识（KnowledgeBase）
  - 新增测试：`test_rescue_trigger.py`、`test_expert_protocol.py`、`test_rescue_loop.py`
- 验证：
  - mock LLM 下 ReAct + Executor + 学习链路已跑通
  - 新增测试：`test_sandbox.py`、`test_approval.py`、`test_resource_registry.py`、`test_evolution_protocol.py`、`test_app_server.py`、`test_cross_ecosystem.py`、`test_ide_endpoints.py`
  - 新增上下文压缩/KV cache 测试：`test_context_budget.py`、`test_hot_memory.py`、`test_memory_manager.py`；`test_local_llm.py` 覆盖 KV cache 复用与预算截断

## 核心架构

```
用户输入
    │
    ▼
┌─────────────────────────────────────┐
│ Agent 层（执行与自修改）             │
│  ReAct 循环 + Tool Registry + MCP   │
│  自动规划 → 调用工具 → 观察结果      │
└───────────┬────────────────────┬────┘
            │ 轨迹                │ 动作提案
            ▼                     ▼
┌─────────────────────┐   ┌─────────────────────┐
│ 学习转化层           │   │ 核心运转层           │
│ 反思 → 技能生成      │   │ 健康探针 → 诊断 → 修复│
│ 验证 → 知识沉淀      │   │ 执行网关 + 事件溯源  │
└──────────┬──────────┘   └──────────┬──────────┘
           │ 知识/技能                │ 版本/快照
           ▼                          ▼
      ┌─────────────────────────────────────┐
      │ 持久化存储层                        │
      │ storage/skills/ storage/memory/     │
      │ storage/trajectories/ storage/log/  │
      └─────────────────────────────────────┘
```

## 快速启动

```powershell
# 一键启动（自动安装依赖、下载模型；失败时自动 fallback 到 Mock 模式）
.\start.bat

# 指定 provider
python main.py --provider local "列出项目文件"
python main.py --provider deepseek "生成一个游戏主菜单"
python main.py --provider openai "编写一个设置界面"
python main.py --provider claude "复杂设计任务"
python main.py --provider mock "测试 ReAct 链路"

# 启动桌面 GUI（pywebview 原生窗口，GUI 为表 CLI 为里）
python main.py --gui
python main.py --gui --provider mock "列出项目文件"
```

> `start.bat` 内部调用 `start.ps1`（PowerShell），以正确处理中文输出和错误暂停。

## 关键目录

| 目录 | 用途 |
|------|------|
| `agent/` | Agent 层：ReAct、工具注册、MCP 客户端 |
| `core/` | 核心运转层：健康、修复、执行网关、版本、事件日志 |
| `learning/` | 学习转化层：轨迹、反思、技能生成、验证 |
| `memory/` | 三层记忆：Hot / Warm / Cold |
| `llm/` | LLM 接口与实现 |
| `gui.py` | 桌面 GUI 启动器（pywebview） |
| `storage/` | 运行时数据（gitignored） |
| `skills/` | 内置技能 + Agent 自生成技能 |
| `web/` | 桌面 GUI 前端（HTML/CSS/JS） |

## 用户画像

- 灰語 / 嗒啦啦
- 风格：Casual friend，equal partner
- 偏好：简单直接、一键启动、完整交付
- 关注点：系统设计、持续改进、AI 自我进化

## 预测下一步

1. ✅ 安装本地模型依赖（llama-cpp-python / huggingface-hub）并确认 MiniCPM5-1B GGUF 可用
2. ✅ 实测 `python main.py --provider local "列出项目文件"` 跑通本地 ReAct 链路
3. ✅ 桌面级 GUI 实现（pywebview + web 前端 + ApprovalBridge）
4. ✅ Electron + Python 后端骨架 + React/Vite 聊天预览布局
5. ✅ Phase 2：LLM KV Cache + 上下文压缩已落地
6. ✅ Phase 3：AGENTS.md 向量索引 + 动态工具已落地
7. ✅ Phase 4：向量记忆系统替换关键词检索已落地
8. ✅ Phase 5：IDE 界面（文件树 / Monaco 编辑器 / 预览）已落地
9. ✅ Phase 6：素材库与图片/音频/视频预览已落地
10. ✅ Phase 7：内嵌 Chromium / Playwright CDP 浏览器预览已落地
11. ✅ Phase 8：专家救援闭环实测
12. ✅ Phase 10：结构优化 + 本地模型性能优化 + 全运行环境内嵌
13. Phase 11：跨平台内嵌（macOS / Linux portable）
14. 在真实任务中验证专家救援闭环（配置有效 API key 实测）
15. 让 Agent 在 `taptap-maker-project` 上完成一次真实游戏功能开发任务
16. 技能遥测与提示词自优化闭环
17. 递归 Meta-Agent（改进改进机制本身）

## v0.4 路线图

- `docs/roadmap-v0.4.md` 已存档，包含 Phase 1~10 完整规划。

## 恢复指令

新会话必读：
1. 读 `AGENT.md`（本文件）
2. 读 `README.md`
3. 读 `docs/memory-index.md`（如果存在）

## POST 规则

每次实质交付后必须执行：
1. git commit
2. memory-index 同步
3. AGENT.md 状态更新
## 专家救援教学闭环（hybrid rescue）

新增专家救援机制：本地模型为主，连续失败/重复动作/迭代耗尽/健康降级时触发外部 LLM 救援；救援成功后自动蒸馏为技能/知识，下次本地模型通过 warm context 复用。

核心组件：
- agent/rescue_orchestrator.py — 编排本地 ReActLoop 与专家 LLM
- agent/rescue_trigger.py — 多因素触发器
- llm/expert_rescuer.py + llm/expert_protocol.py — 专家 prompt 与救援动作协议
- learning/expert_distiller.py — 救援差值蒸馏为技能/知识

配置示例见 config.example.json 中的 expert / rescue / learning 块。

## Phase 8 救援实测补充

### 可观测事件

救援过程会通过 ReActLoop 事件通道发送以下 SSE 事件：
- `rescue_triggered` — 触发原因（consecutive_errors / repeated_actions / iteration_exhaustion / health_degraded）
- `rescue_calling` — 开始调用专家 LLM
- `rescue_action` — 专家返回的 mode / thought / action_tool / takeover_steps / expert_latency_ms
- `rescue_applied` — 救援动作已应用
- `rescue_skipped` — 救援被跳过及原因（max_rescue_reached / cooldown / expert_unavailable）
- `rescue_distilled` — 蒸馏完成，含 insights_count / skill_names / error

### 运行实测

```powershell
# 真实任务 + 真实专家（需 config.json 中配置有效 API key）
python tests/test_rescue_benchmark.py

# 本地快速观察救援事件（使用 ScriptedExpertLLM，不产生 API 费用）
python main.py --rescue-test --mock
```

### 已知边界

- 当前 benchmark 重点验证「救援触发 → 专家接管 → 蒸馏」闭环；完整 Seasonal Festival 功能实现依赖专家模型在有限救援次数内完成多文件编辑，需继续优化 prompt/工具解析/迭代预算。
- DeepSeek 模型可能输出 DSML 格式的 tool_calls，`llm/utils.py` 已做兼容解析。
- 写大文件时需要较大 max_tokens，`llm/openai_llm.py` 已把 choose_action 上限提高到 4096。
