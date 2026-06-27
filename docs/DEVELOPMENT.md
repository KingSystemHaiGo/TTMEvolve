# Development Guide

## Requirements

- Windows is the primary verified development environment.
- Python virtual environment under `.venv/`.
- Node/npm for `frontend/` and legacy `electron/` compatibility builds.
- Rust/Cargo for `src-tauri/`.

## Common Commands

```powershell
npm.cmd --prefix frontend run build
npm.cmd --prefix electron run build
cargo test --manifest-path src-tauri\Cargo.toml
.venv\Scripts\python.exe -m pytest -q
```

## Release Checks

```powershell
.venv\Scripts\python.exe scripts\package_release.py
.venv\Scripts\python.exe scripts\release_readiness.py --mode source-checkpoint --json
.venv\Scripts\python.exe scripts\release_readiness.py --mode full-offline --json
```

`source-checkpoint` proves the source package and launch surface. `full-offline` is stricter and currently requires evidence that is not yet claimed: signed installer, Maker remote build smoke, and production RAG semantic quality.

## Private State

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

Internal memory documents are ignored and kept local.
