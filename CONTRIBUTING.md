# Contributing to TTMEvolve

Thanks for considering a contribution. TTMEvolve is still moving quickly, so the most useful contributions are small, well-tested, and clear about the runtime surface they affect.

## Before You Start

- Read [README.md](README.md) and [docs/README.md](docs/README.md).
- Check existing issues or open a short proposal before large changes.
- Keep private runtime state out of commits: API keys, Maker auth, `portable/`, `storage/`, `workspace/`, models, logs, and release artifacts.

## Development Setup

```powershell
npm.cmd --prefix frontend run build
.venv\Scripts\python.exe -m pytest -q
cargo test --manifest-path src-tauri\Cargo.toml
```

Use narrower tests while iterating, then run the relevant release gate before submitting.

## Pull Request Expectations

- Explain what changed and why.
- Include verification commands and results.
- Keep public claims evidence-based. If a capability is not proven, call it `unproven`, `partial`, or `experimental`.
- Do not include local/private project memory files. The public repository intentionally excludes internal sprint logs and agent handoff memory.

## Documentation

- Public user/developer docs belong under `docs/`.
- Internal project memory stays local and is ignored by Git.
- Update [CHANGELOG.md](CHANGELOG.md) for user-visible changes.
