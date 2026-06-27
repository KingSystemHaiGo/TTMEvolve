# 开发指南 / Development Guide

## 环境要求 / Requirements

- Windows 是当前主要验证过的开发环境。
- Python 虚拟环境位于 `.venv/`。
- `frontend/` 和旧 `electron/` 兼容构建需要 Node/npm。
- `src-tauri/` 需要 Rust/Cargo。

- Windows is the primary verified development environment.
- Python virtual environment lives under `.venv/`.
- Node/npm is used for `frontend/` and legacy `electron/` compatibility builds.
- Rust/Cargo is used for `src-tauri/`.

## 常用命令 / Common Commands

```powershell
npm.cmd --prefix frontend run build
npm.cmd --prefix electron run build
cargo test --manifest-path src-tauri\Cargo.toml
.venv\Scripts\python.exe -m pytest -q
```

## 发布检查 / Release Checks

```powershell
.venv\Scripts\python.exe scripts\package_release.py
.venv\Scripts\python.exe scripts\release_readiness.py --mode source-checkpoint --json
.venv\Scripts\python.exe scripts\release_readiness.py --mode full-offline --json
```

`source-checkpoint` 用来证明源码包和可见启动入口。`full-offline` 更严格，目前仍依赖尚未声明的证据：签名安装包、Maker 远程构建 smoke、生产 RAG 语义质量。

`source-checkpoint` proves the source package and launch surface. `full-offline` is stricter and currently requires evidence that is not yet claimed: signed installer, Maker remote build smoke, and production RAG semantic quality.

## 私有状态 / Private State

不要提交本地运行时或私有状态：

- `config.json`
- `.env*`
- `.mcp.json`
- `portable/`
- `storage/`
- `workspace/`
- `vendor/`
- `models/`
- `logs/`
- `release-artifacts/`

Do not commit local runtime or private state:

- `config.json`
- `.env*`
- `.mcp.json`
- `portable/`
- `storage/`
- `workspace/`
- `vendor/`
- `models/`
- `logs/`
- `release-artifacts/`

内部记忆文档会被 ignore，并保留在本地。

Internal memory documents are ignored and kept local.
