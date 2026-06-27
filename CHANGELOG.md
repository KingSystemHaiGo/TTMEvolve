# 变更记录 / Changelog

所有值得公开说明的变更都应记录在这里。项目采用证据优先的 release 表述：未证明的能力必须明确标注。

All notable public changes should be summarized here. This project uses evidence-based release wording: unproven capabilities are called out explicitly.

## v1.0.0 第一个稳定分发 / v1.0.0 First Stable Distribution

- 第一个可分发的自包含 zip 产物，内嵌 Python 3.12.10 + Node 20.15.1 + MinGit 2.45.2 + 所有 Python 依赖 + embedding 模型 + Playwright Chromium。
- First distributable self-contained zip artifact, embedding Python 3.12.10 + Node 20.15.1 + MinGit 2.45.2 + all Python dependencies + embedding models + Playwright Chromium.
- 首次 build Tauri release exe 并将其与 vendor/ 运行时一起打包。
- First Tauri release exe built and packaged together with the vendor/ embedded runtime.
- 路径统一：`portable/` → `vendor/`（start-tauri.bat、release_readiness.py 全部更新）。
- Path unification: `portable/` → `vendor/` (start-tauri.bat, release_readiness.py all updated).
- 验证：Windows 11 干净机器解压后双击启动无 error，/health 端点返回 200。
- Verified: Windows 11 clean machine, extract and double-click launch, no error in launcher.log, /health returns 200.
- Defer 到 v1.0.x：签名安装包、GitHub Release、updater 自动更新、Maker 远程构建 smoke、RAG 语义质量证明。
- Deferred to v1.0.x: signed installer, GitHub Release publishing, tauri-plugin-updater, Maker remote build smoke, production RAG semantic-quality proof.

## Unreleased / 未发布

- 公开文档改为中英双语，中文优先。
- Split public documentation into bilingual Chinese-first documents.
- 新增 GitHub 社区文件：`LICENSE`、`CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`、`SECURITY.md`、`SUPPORT.md`。
- Added public open-source community files: `LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, and `SUPPORT.md`.
- 围绕 `docs/README.md`、API、开发指南、路线图、架构决策和 release notes 重组公开文档。
- Reorganized public documentation around `docs/README.md`, API, development, roadmap, architecture decisions, and release notes.
- 从 Git 追踪中移除内部项目记忆和私有规划日志，但保留本地文件。
- Removed internal project memory and private planning logs from Git tracking while keeping them local.

## v0.4.5 Source Checkpoint / v0.4.5 源码 checkpoint

- 已验证稳定源码 checkpoint。
- Verified a stable source checkpoint for TTMEvolve.
- 增加可重复的 source package 和 release readiness audit。
- Added repeatable source package and release readiness audits.
- 当前 source checkpoint gate 为 `ready`。
- Current source checkpoint gate is `ready`.
- full offline release 仍为 `partial`：签名安装包、Maker 远程构建 smoke、生产 RAG 语义质量证明尚未声明。
- Full offline release remains `partial`: signed installer, Maker remote build smoke, and production RAG semantic-quality proof are not claimed.
