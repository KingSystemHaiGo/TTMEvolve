# TTMEvolve

中文优先 / Chinese first: TTMEvolve 是面向 TapTap Maker 游戏开发的桌面 AI Agent 工作台。它把 Tauri + React 桌面壳、本地 Python App Server、Maker MCP 诊断、API 优先的 LLM 路由、运行时证据、记忆与学习流程整合到一个本地开发驾驶舱里。

English: TTMEvolve is a desktop AI Agent workbench for TapTap Maker game development. It combines a Tauri + React desktop shell, a local Python App Server, Maker MCP diagnostics, API-first LLM routing, runtime evidence, memory, and learning workflows into one local development cockpit.

- 中文 README: [README.zh-CN.md](README.zh-CN.md)
- English readers: every public GitHub document is maintained bilingually, with Chinese first.

## 当前发布状态 / Current Release State

| 项目 / Item | 状态 / Status |
| --- | --- |
| 源码 checkpoint / Source checkpoint | Ready |
| 可分发版本线 / Distributable version | `1.0.0`（保持在 1.0.0，新能力作为 Post-1.0.0 Slice 追加） |
| Agent 内部切片 / Agent internal slices | `Post-v1.0.0 Slice #1`（RAG / Memory / Cybernetic Control）+ `Slice #2`（多模态 / 知识包 / 类型化 DAG / Feature 状态机） |
| 主桌面壳 / Primary desktop shell | Tauri 2.x + Rust + WebView2 |
| 前端 / Frontend | React + Vite workbench |
| 后端 / Backend | Python App Server on `http://127.0.0.1:7345` |
| LLM 运行时 / LLM runtime | API providers first; local GGUF is an explicit fallback |
| Maker 集成 / Maker integration | Maker setup, readiness, tool audit, and MCP reconnect flows |
| 离线发布 / Offline release | Ready (自包含 zip，含 vendor/ 嵌入运行时) / Ready (self-contained zip with vendor/ embedded runtime) |
| 可分发产物 / Distributable artifact | `release-artifacts/TTMEvolve-v1.0.0-windows-x64.zip` |

当前 v1.0.0 是第一个可分发的稳定版本。产物是自包含 zip，解压后双击 `TTMEvolve.vbs` 即可启动，内嵌 Python 3.12.10 + Node 20.15.1 + MinGit 2.45.2 + 所有 Python 依赖 + embedding 模型 + Playwright Chromium。

**Post-v1.0.0 Slice #2 agent 内部**新增多模态 LLM 接口、知识包系统、类型化 sub-goal DAG、Feature 状态机。版本号保持在 1.0.0。详见 `CHANGELOG.md`。生产行为对外不变，桌面 GUI 无须任何调整。

The current v1.0.0 is the first distributable stable release. The artifact is a self-contained zip — extract and double-click `TTMEvolve.vbs` to launch, embedding Python 3.12.10 + Node 20.15.1 + MinGit 2.45.2 + all Python dependencies + embedding models + Playwright Chromium.

**Post-v1.0.0 Slice #2** adds multimodal LLM interface, project-side skill packs, typed sub-goal DAG, and a feature-state machine. The distributable version stays at 1.0.0. See `CHANGELOG.md`.

## 快速开始 / Quick Start

Windows 桌面 GUI / Windows desktop GUI:

```powershell
.\start-tauri.bat
```

CLI 与无界面模式 / CLI and headless modes:

```powershell
.\start-tauri.bat --cli
.\start-tauri.bat --headless
```

后端 smoke check / Backend-only smoke check:

```powershell
python main.py --serve --mock
```

启动器会优先使用 `vendor/` 下的嵌入式运行时，然后是 `.venv/`，最后才是系统工具。源码 checkout 中如果没有 Tauri 二进制产物，启动器会构建前端并通过 Cargo 启动 Tauri。

The launcher prefers embedded runtimes under `vendor/`, then `.venv/`, then system tools. In a source checkout, if no Tauri binary exists, the launcher builds the frontend and starts Tauri with Cargo.

## 能力概览 / What TTMEvolve Provides

- 面向 TapTap Maker 开发的 chat-first 桌面 Agent 界面。
- A chat-first desktop Agent surface for TapTap Maker game work.
- 通过 Tauri/WebView2 桌面壳提供原生 Maker 预览。
- Native Maker preview through the Tauri/WebView2 shell.
- Maker MCP 设置诊断、readiness 检查、tool audit 与 reconnect 支持。
- Maker MCP setup diagnostics, readiness checks, tool audit, and reconnect support.
- MiniMax、OpenAI-compatible、Claude-style provider 和本地 fallback 的选择与 probe 证据。
- API provider selection and probe evidence for MiniMax, OpenAI-compatible providers, Claude-style providers, and local fallback paths.
- Runtime Readiness、Evidence Bundle、LLM Onboarding 和外部 Agent handoff 端点。
- Runtime Readiness, Evidence Bundle, LLM Onboarding, and handoff endpoints for debugging and external Agent collaboration.
- Plan-first Agent 执行，包含 sandbox、approval、tool validation、runtime events 与持久会话回放。
- Plan-first Agent execution with sandbox, approval, tool validation, runtime events, and durable session replay.
- **多模态 LLM 工具调用**（Post-v1.0.0 Slice #2）：tool 返回图片时 ReAct 自动把图片附到下一步 think context，Claude / OpenAI 兼容 provider 原生支持。
- **Multimodal tool calls** (Post-v1.0.0 Slice #2): when a tool returns an image, ReAct attaches it to the next think context. Claude and OpenAI-compatible providers pass images natively.
- **项目内省工具**（Post-v1.0.0 Slice #2）：agent 暴露 `project.manifest` / `project.asset_read` / `project.code_search` / `project.preview_capture` 等 6 个 read-only 工具，能"看见"项目结构、读 sprite、搜 Lua 符号。
- **Project introspection** (Post-v1.0.0 Slice #2): six read-only tools — `project.manifest`, `project.asset_read`, `project.asset_search`, `project.code_search`, `project.preview_capture`, `project.build_state` — let the agent see project structure, read sprites, search Lua symbols.
- **技能包系统**（Post-v1.0.0 Slice #2）：UrhoX / Maker MCP / 三个 genre（platformer / RPG / puzzle）的项目侧知识自动 recall，UNDERSTAND 阶段直接注入。
- **Skill packs** (Post-v1.0.0 Slice #2): project-side knowledge under `docs/skill_packs/` for UrhoX, Maker MCP, and three genres. Auto-recalled during UNDERSTAND.
- **类型化 sub-goal DAG**（Post-v1.0.0 Slice #2）：一个 goal 可拆成 code / asset / scene / audio / test 子目标并行跑，自动 INTEGRATION 收口，依赖图调度。
- **Typed sub-goal DAG** (Post-v1.0.0 Slice #2): a goal can spawn typed sub-goals (code / asset / scene / audio / test) that run in parallel per the dependency graph; an auto-appended integration sub-goal closes the loop.
- **Feature / Ticket 状态机**（Post-v1.0.0 Slice #2）：每个 goal 关联 feature，跨 session 状态可追踪，`docs/sprint-board.md` / `docs/progress.md` 自动维护。
- **Feature / ticket state machine** (Post-v1.0.0 Slice #2): every goal attaches to a feature; the state persists across sessions; `docs/sprint-board.md` and `docs/progress.md` are auto-refreshed.

## 公开文档 / Public Documentation

这些文档都是 GitHub 公开面向的中英双语文档，中文优先。

These are public GitHub-facing bilingual documents, with Chinese first.

- [文档索引 / Documentation index](docs/README.md)
- [开发指南 / Development guide](docs/DEVELOPMENT.md)
- [App Server API](docs/API.md)
- [路线图 / Roadmap](docs/ROADMAP.md)
- [架构说明 / Architecture notes](docs/architecture/README.md)
- [发布说明 / Release notes](docs/releases/README.md)
- [更新记录 / Changelog](CHANGELOG.md)
- [贡献指南 / Contributing](CONTRIBUTING.md)
- [安全政策 / Security policy](SECURITY.md)
- [支持方式 / Support](SUPPORT.md)

### v1.1.0 Slice #1 — RAG / Memory / Cybernetic Control / RAG、记忆、控制论（opt-in）

v1.1.0 在 v1.0.0 之上加了五项 feature flag 关闭的能力，**默认行为完全不变**。
切任何 flag 之前请跑 `scripts/check_release_ready.py`，确保 13/13 gate READY。

v1.1.0 adds five feature-flagged capabilities on top of v1.0.0;
**default behaviour is unchanged**. Before flipping any flag, run
`scripts/check_release_ready.py` and confirm 13/13 gates READY.

| Flag | Default | When on | Doc |
| --- | --- | --- | --- |
| `memory.graph.enabled` | `false` | Cold memory becomes a typed-edge graph with five-factor ranking | [ADR-0004](docs/architecture/adr-0004-profile-aware-graph-memory.md) |
| `memory.bayes.enabled` | `false` | Each memory carries a Beta-Bernoulli posterior + Occam score | [ADR-0004](docs/architecture/adr-0004-profile-aware-graph-memory.md) |
| `loader.enabled` | `false` | Prompt/context/memory becomes fragment-based with priority, stub, defer | [ADR-0007](docs/architecture/adr-0007-progressive-context-loader.md) |
| `plan.v2_enabled` | `false` | Plans support `sub_plan` / `branch` / `loop` and recursive execution | [ADR-0008](docs/architecture/adr-0008-plan-v2-cybernetic-control.md) |
| `vsm.enabled` | `false` | Stafford-Beer VSM thin adapter drives guarded re-plan / expert rescue | [ADR-0008](docs/architecture/adr-0008-plan-v2-cybernetic-control.md) |

完整 inventory 与 on/off 效果：[`docs/feature-flags.md`](docs/feature-flags.md)。
Research 依据与 anti-patterns：[`docs/research/2026-memory-and-control.md`](docs/research/2026-memory-and-control.md)。
可发版 gate 列表：[`docs/release-gates.md`](docs/release-gates.md)。

Full flag inventory and on/off effects:
[`docs/feature-flags.md`](docs/feature-flags.md).
Research basis and anti-patterns:
[`docs/research/2026-memory-and-control.md`](docs/research/2026-memory-and-control.md).
Release gate list:
[`docs/release-gates.md`](docs/release-gates.md).

## 架构 / Architecture

```mermaid
flowchart TB
    User["用户 / User"] --> GUI["Tauri + React Workbench<br/>(含 GoalLoopPanel)"]
    User --> CLI["CLI / Headless"]

    GUI --> Server["Python App Server<br/>127.0.0.1:7345"]
    CLI --> Server

    Server --> Agent["TapMakerAgent<br/>GoalLoop / ReAct / Tools"]
    Agent --> LLM["LLM Router<br/>Multimodal (Slice #2)"]
    Agent --> Tools["Tool Registry<br/>+ project.* introspection (Slice #2)"]
    Agent --> Runtime["Runtime Controls<br/>Sandbox / Approval / Health"]
    Agent --> Memory["Memory + Learning<br/>Evidence / Vector Index"]
    Server --> Bus["Runtime Event Bus<br/>Session / Layer / Diagnostics"]
    Agent --> Bus
    Runtime --> Bus
    Memory --> Bus

    Agent --> GoalLoop["GoalLoop Orchestrator (Slice #2)<br/>typed sub-goal DAG + rework"]
    GoalLoop --> SkillPacks["Skill packs (Slice #2)<br/>docs/skill_packs/"]
    GoalLoop --> FeatureState["Feature / Ticket ledger (Slice #2)<br/>.ttmevolve/features.jsonl"]
    GoalLoop --> ReAct["ReAct loop<br/>(per sub-goal dev_runner)"]

    Tools --> Maker["TapTap Maker MCP"]
    Tools --> Project["Maker project workspace"]
    Runtime --> Storage["storage/ runtime state"]
    Memory --> Docs["docs/ persistent knowledge"]
    GoalLoop --> Artifacts["artifacts/<br/>decisions/ system-contracts/<br/>docs/progress.md sprint-board.md"]

    LLM --> ContentBlock["ContentBlock<br/>TextBlock / ImageBlock"]
    ContentBlock --> Anthropic["Anthropic base64"]
    ContentBlock --> OpenAI["OpenAI data: URL"]
    ContentBlock --> Fallback["text-only fallback"]
```

### Post-v1.0.0 Slice #2 — Agent Goal Loop

This slice reorganises the agent's internal layers while the
distributable version stays at 1.0.0. The default end-user
behaviour is unchanged; the new surfaces are exposed to
operators and to other agents through existing runtime
contract endpoints and the new project-side files.

| Layer | Module | Effect |
| --- | --- | --- |
| Multimodal LLM | `llm/content.py` | `TextBlock` / `ImageBlock` flow through Anthropic, OpenAI, MiniMax. Text-only fallback for unopt-in providers. |
| ReAct observation | `agent/react_loop.py` | When a tool returns images, the next `think` is routed through `think_multimodal`. |
| Project introspection | `agent/project_introspection.py` | Six read-only tools — `project.manifest`, `project.asset_read`, `project.asset_search`, `project.code_search`, `project.preview_capture`, `project.build_state`. |
| Skill packs | `agent/skill_packs/` | Project-side knowledge under `docs/skill_packs/`. Five seed packs (UrhoX, Maker MCP, platformer, RPG, puzzle). Auto-recalled during UNDERSTAND. |
| Typed sub-goal DAG | `agent/goal_dag.py` + `agent/typed_subloop.py` | Sub-goals carry type, dependency graph, capability hint, and acceptance. Layered, parallel execution with an auto-appended integration. |
| Feature state | `agent/feature_state.py` | Append-only ledger at `.ttmevolve/features.jsonl`. Lifecycle: proposed → approved → in_progress → blocked → shipped → deprecated. |

`GoalLoop(artifacts_root=...)` and the `TTMEVOLVE_GOAL_ARTIFACTS_ROOT`
env var redirect every project-side write (decisions, system-contracts,
progress, sprint board, skill packs) so tests and ad-hoc demos
can keep the dev tree clean. See `CONTRIBUTING.md` →
"Test isolation" for the rule.

## 目录结构 / Repository Map

| 路径 / Path | 用途 / Purpose |
| --- | --- |
| `src-tauri/` | Tauri/Rust 桌面壳、后端生命周期、原生命令、更新器和打包配置。 / Primary Tauri/Rust desktop shell, backend lifecycle, native commands, updater, and bundle config. |
| `frontend/` | React + Vite workbench UI。 / React + Vite workbench UI. |
| `server/` | 本地 App Server、会话 API、证据/readiness API、Maker 设置 API 和 browser service。 / Local App Server, session APIs, evidence/readiness APIs, Maker setup APIs, and browser service. |
| `agent/` | Agent runtime、Plan First、ReAct loop、工具执行、Maker guard、MCP 集成和轨迹辅助模块。 / Agent runtime, Plan First, ReAct loop, tool execution, Maker guard, MCP integration, and trajectory helpers. |
| `core/` | 配置、sandbox、approval、health、runtime events、contracts 与 portable 环境检查。 / Config, sandbox, approval, health, runtime events, contracts, and portable environment checks. |
| `llm/` | LLM providers、router/factory、本地 GGUF 支持和 provider presets。 / LLM providers, router/factory, local GGUF support, and provider presets. |
| `memory/` | 记忆管理、AGENTS.md 索引、向量/冷记忆、RAG benchmark 和 RAG quality evaluation。 / Memory manager, AGENTS.md indexing, vector/cold memory, RAG benchmark, and RAG quality evaluation. |
| `learning/` | 轨迹收集、反思、shared-memory bridge、skill generation 和 validation。 / Trajectory collection, reflection, shared-memory bridge, skill generation, and validation. |
| `ecosystem/` | 跨 Agent adapter 和 skill sync。 / Cross-agent adapters and skill sync. |
| `electron/` | 旧 Electron 兼容构建面。 / Legacy Electron compatibility build surface. |
| `tests/` | Python regression and integration tests。 / Python regression and integration tests. |
| `docs/` | 公开文档、release notes、architecture records 和项目知识。 / Public docs, release notes, architecture records, and project knowledge. |

忽略的本地/运行时状态包括 `storage/`、`portable/`、`workspace/`、`vendor/`、`models/`、`node_modules/`、`src-tauri/target/`、`logs/`、`.env*`、`.mcp.json` 和 `release-artifacts/`。

Ignored local/runtime state includes `storage/`, `portable/`, `workspace/`, `vendor/`, `models/`, `node_modules/`, `src-tauri/target/`, `logs/`, `.env*`, `.mcp.json`, and `release-artifacts/`.

## 开发命令 / Development Commands

前端构建 / Frontend build:

```powershell
npm.cmd --prefix frontend run build
```

Electron 兼容构建 / Electron compatibility build:

```powershell
npm.cmd --prefix electron run build
```

Tauri/Rust 测试 / Tauri/Rust tests:

```powershell
cargo test --manifest-path src-tauri\Cargo.toml
```

Python 测试 / Python tests:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

发布 readiness / Release readiness:

```powershell
.venv\Scripts\python.exe scripts\release_readiness.py --mode source-checkpoint --json
.venv\Scripts\python.exe scripts\release_readiness.py --mode full-offline --json
```

源码 checkpoint 打包 / Source checkpoint package:

```powershell
.venv\Scripts\python.exe scripts\package_release.py
```

## 最新验证 / Latest Verification

最近一次公开 checkpoint 验证记录如下。`full-offline` 的 `partial` 是刻意保守的发布边界，不是源码 checkpoint 失败。

The latest public checkpoint was verified with the commands below. The `full-offline` `partial` result is an intentionally conservative release boundary, not a source checkpoint failure.

- `.venv\Scripts\python.exe -m pytest -q` -> `748 passed, 14 skipped` (v1.0.0 baseline)
- **Post-v1.0.0 Slice #2** (`feature_state`, `goal_dag`, `skill_packs`, `project_introspection`, multimodal LLM): 11 targeted test files -> **136 passed**
- `npm.cmd --prefix frontend run build` -> passed
- `npm.cmd --prefix electron run build` -> passed with Vite CJS deprecation warnings only
- `cargo test --manifest-path src-tauri\Cargo.toml` -> `34 passed`, warnings only
- `.venv\Scripts\python.exe -m pytest tests\test_package_release.py tests\test_release_readiness.py -q` -> `8 passed`
- `.venv\Scripts\python.exe scripts\release_readiness.py --mode source-checkpoint --json` -> `status=ready`
- `.venv\Scripts\python.exe scripts\release_readiness.py --mode full-offline --json` -> `status=partial`
- `git diff --check` -> passed with existing LF/CRLF warnings only

源码包证据会写入生成的 manifest。该目录本地生成，并故意被 Git 忽略。

Source package evidence is written to the generated manifest. The directory is generated locally and intentionally ignored by Git.

```text
release-artifacts/TTMEvolve-source-v0.4.5-one-click-practice-entry.zip
release-artifacts/TTMEvolve-source-v0.4.5-one-click-practice-entry.zip.manifest.json
```

## 发布边界 / Release Boundaries

可以声明 / Ready to claim:

- 稳定源码 checkpoint。 / Stable source checkpoint.
- 可见启动入口存在。 / Visible launch surface exists.
- 源码包审计通过。 / Source package audit passes.

暂不声明 / Not yet claimed:

- 签名安装包。 / Signed installer artifacts.
- Maker 远程构建 side-effect smoke。 / Maker remote build side-effect smoke.
- 使用真实 golden corpus 与生产 embedding artifact 的 RAG 语义质量证明。 / Production RAG semantic-quality proof with a real golden corpus and production embedding artifact.
- 本机 `portable/` 缓存状态的公开可复现保证。 / Public reproducibility guarantee for the current local `portable/` cache state.

## App Server API

默认本地服务 / Default local server:

```text
http://127.0.0.1:7345
```

常用端点 / Useful endpoints:

| Method | Path | 用途 / Purpose |
| --- | --- | --- |
| `GET` | `/health` | 健康与运行时状态 / Health and runtime status |
| `POST` | `/sessions` | 创建 Agent 会话 / Create an Agent session |
| `GET` | `/sessions/{id}/events` | SSE 事件流 / SSE event stream |
| `POST` | `/sessions/{id}/cancel` | 取消会话 / Cancel a session |
| `POST` | `/config/llm` | 更新 LLM 配置 / Update LLM configuration |
| `POST` | `/llm/probe` | Probe configured LLM provider |
| `GET` | `/runtime/readiness` | 无网络 runtime readiness gate / No-network runtime readiness gate |
| `GET` | `/runtime/portable` | portable 环境诊断 / Portable environment diagnostics |
| `GET` | `/maker/setup-status` | Maker 设置状态 / Maker setup status |
| `GET` | `/maker/tool-audit` | Maker 远程/本地工具审计 / Maker remote/local tool audit |
| `GET` | `/sessions/{id}/evidence?steps=20` | 紧凑 runtime evidence bundle / Compact runtime evidence bundle |
| `GET` | `/agent/onboarding?session_id=...&steps=20` | 外部 Agent onboarding bundle / External Agent onboarding bundle |

## 安全边界 / Safety Notes

不要提交 API keys、TapTap Maker auth state、本地模型文件、用户缓存、构建输出或私有项目素材。

Do not commit API keys, TapTap Maker auth state, local model files, user caches, build outputs, or private project assets.

重要忽略/私有路径 / Important ignored/private paths:

- `config.json`
- `.env*`
- `.mcp.json`
- `.venv/`
- `node_modules/`
- `storage/`
- `portable/`
- `workspace/`
- `vendor/`
- `models/`
- `logs/`
- `release-artifacts/`

## 许可证 / License

本项目使用 [MIT License](LICENSE)。

This project is released under the [MIT License](LICENSE).
