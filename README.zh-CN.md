# TTMEvolve 中文说明 / Chinese README

TTMEvolve 是面向 TapTap Maker 游戏开发的桌面 AI Agent 工作台。项目主要面向中文开发者，因此公开文档采用中文优先、中英双语维护。

TTMEvolve is a desktop AI Agent workbench for TapTap Maker game development. The project primarily serves Chinese developers, so public documentation is maintained bilingually with Chinese first.

- 默认 GitHub 首页 / Default GitHub landing page: [README.md](README.md)
- 公开文档索引 / Public docs index: [docs/README.md](docs/README.md)

## 当前状态 / Current Status

| 项目 / Item | 状态 / Status |
| --- | --- |
| 源码 checkpoint / Source checkpoint | Ready |
| 可分发版本线 / Distributable version | `1.0.0`（保持在 1.0.0，新能力作为 Post-v1.0.0 Slice 追加） |
| Agent 内部切片 / Agent internal slices | `Post-v1.0.0 Slice #1`（RAG / Memory / Cybernetic Control）+ `Slice #2`（多模态 / 知识包 / 类型化 DAG / Feature 状态机） |
| 桌面壳 / Desktop shell | Tauri 2.x + Rust + WebView2 |
| 前端 / Frontend | React + Vite workbench |
| 后端 / Backend | Python App Server, default `http://127.0.0.1:7345` |
| LLM 运行时 / LLM runtime | API providers first; local GGUF is explicit fallback |
| 完整离线发布 / Full offline release | Partial / not claimed |

当前公开发布声明 v1.0.0 源码 checkpoint ready + 离线 zip 产物 ready。签名安装包、Maker 远程构建 smoke、生产 RAG 语义质量、本机 `portable/` 缓存状态都不作为当前公开发布承诺。

**Post-v1.0.0 Slice #2** 新增 5 个 agent 内部层（多模态 LLM、项目内省工具、技能包系统、类型化 sub-goal DAG、Feature 状态机），全部以 Post-v1.0.0 Slice 形式追加，**版本号保持在 1.0.0**，详见 `CHANGELOG.md` 和 `README.md` 的架构段。

The current public release claims v1.0.0 source checkpoint ready plus the offline zip artifact ready. Signed installers, Maker remote build smoke, production RAG semantic quality, and local `portable/` cache state are not claimed as public release guarantees.

**Post-v1.0.0 Slice #2** adds five agent-internal layers (multimodal LLM, project introspection tools, skill packs, typed sub-goal DAG, feature-state machine). The distributable version stays at 1.0.0; see `CHANGELOG.md` and the architecture section in `README.md`.

## 快速启动 / Quick Start

Windows GUI:

```powershell
.\start-tauri.bat
```

CLI / Headless:

```powershell
.\start-tauri.bat --cli
.\start-tauri.bat --headless
```

后端 smoke check / Backend-only smoke check:

```powershell
python main.py --serve --mock
```

启动器优先使用 `portable/`，其次 `.venv/`，最后使用系统工具。源码 checkout 中没有 Tauri 二进制时，会构建前端并通过 Cargo 启动 Tauri。

The launcher prefers `portable/`, then `.venv/`, then system tools. In a source checkout, if no Tauri binary exists, it builds the frontend and starts Tauri through Cargo.

## 核心能力 / Core Capabilities

- Chat-first TapTap Maker 桌面 Agent。
- Chat-first desktop Agent for TapTap Maker work.
- 原生 Maker 预览、项目目录切换、文件/素材侧栏。
- Native Maker preview, project directory switching, and file/asset sidebars.
- Maker MCP readiness、setup doctor、tool audit、reconnect。
- Maker MCP readiness, setup doctor, tool audit, and reconnect flows.
- MiniMax、OpenAI-compatible、Claude-style provider 与本地 fallback 的 probe 证据。
- Probe evidence for MiniMax, OpenAI-compatible providers, Claude-style providers, and local fallback paths.
- Runtime Readiness、Evidence Bundle、LLM Onboarding、外部 Agent handoff。
- Runtime Readiness, Evidence Bundle, LLM Onboarding, and external Agent handoff.
- Plan-first Agent 执行，带 sandbox、approval、tool validation、事件回放。
- Plan-first Agent execution with sandbox, approval, tool validation, and event replay.

## 文档 / Documentation

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

## 开发命令 / Development Commands

```powershell
npm.cmd --prefix frontend run build
npm.cmd --prefix electron run build
cargo test --manifest-path src-tauri\Cargo.toml
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\package_release.py
.venv\Scripts\python.exe scripts\release_readiness.py --mode source-checkpoint --json
.venv\Scripts\python.exe scripts\release_readiness.py --mode full-offline --json
```

`source-checkpoint` 是当前公开发布 gate；`full-offline` 仍是保守的完整离线发布审计，当前不声明完成。

`source-checkpoint` is the current public release gate. `full-offline` remains the conservative full offline release audit and is not claimed as complete.

## 发布边界 / Release Boundary

可以声明 / Ready to claim:

- 稳定源码 checkpoint。 / Stable source checkpoint.
- 可见 GUI 启动入口。 / Visible GUI launch surface.
- 源码包审计通过。 / Source package audit passes.

暂不声明 / Not yet claimed:

- 签名安装包。 / Signed installer artifacts.
- Maker 远程构建 side-effect smoke。 / Maker remote build side-effect smoke.
- 生产 RAG 语义质量证明。 / Production RAG semantic-quality proof.
- 本机 `portable/` 缓存状态的公开可复现保证。 / Public reproducibility guarantee for local `portable/` cache state.

## 安全边界 / Safety Notes

不要提交 API keys、TapTap Maker auth state、本地模型、用户缓存、构建输出或私有项目素材。

Do not commit API keys, TapTap Maker auth state, local models, user caches, build outputs, or private project assets.

默认忽略的本地路径包括 `storage/`、`portable/`、`workspace/`、`vendor/`、`models/`、`node_modules/`、`src-tauri/target/`、`logs/`、`.env*`、`.mcp.json` 和 `release-artifacts/`。

Ignored local paths include `storage/`, `portable/`, `workspace/`, `vendor/`, `models/`, `node_modules/`, `src-tauri/target/`, `logs/`, `.env*`, `.mcp.json`, and `release-artifacts/`.

## License

本项目使用 [MIT License](LICENSE)。

This project is released under the [MIT License](LICENSE).
