# 贡献指南 / Contributing to TTMEvolve

感谢你愿意参与 TTMEvolve。项目仍在快速演进，最有价值的贡献通常是范围清晰、验证充分、并且明确说明影响了哪个运行时表面的改动。

Thanks for considering a contribution. TTMEvolve is still moving quickly, so the most useful contributions are small, well-tested, and clear about the runtime surface they affect.

## 开始之前 / Before You Start

- 先阅读 [README.md](README.md)、[中文 README](README.zh-CN.md) 和 [docs/README.md](docs/README.md)。
- 大改动前请先开 issue 或简短 proposal，避免方向偏差。
- 不要提交私有运行时状态：API keys、Maker auth、`portable/`、`storage/`、`workspace/`、models、logs、release artifacts。

- Read [README.md](README.md), [README.zh-CN.md](README.zh-CN.md), and [docs/README.md](docs/README.md).
- Open an issue or a short proposal before large changes.
- Keep private runtime state out of commits: API keys, Maker auth, `portable/`, `storage/`, `workspace/`, models, logs, and release artifacts.

## 开发环境 / Development Setup

```powershell
npm.cmd --prefix frontend run build
.venv\Scripts\python.exe -m pytest -q
cargo test --manifest-path src-tauri\Cargo.toml
```

开发中可以先跑更小的 focused tests；提交前请跑相关 release gate。

Use narrower tests while iterating, then run the relevant release gate before submitting.

## PR 要求 / Pull Request Expectations

- 说明改了什么、为什么改。
- 写清楚验证命令和结果。
- 公开能力声明必须有证据；未证明的能力请写 `unproven`、`partial` 或 `experimental`。
- 不要提交本地/私有项目记忆文件。公开仓库会刻意排除内部 sprint logs 和 agent handoff memory。

- Explain what changed and why.
- Include verification commands and results.
- Keep public claims evidence-based. If a capability is not proven, call it `unproven`, `partial`, or `experimental`.
- Do not include local/private project memory files. The public repository intentionally excludes internal sprint logs and agent handoff memory.

## 文档 / Documentation

- 面向用户和贡献者的公开文档放在 `docs/`。
- 内部项目记忆留在本地，并通过 `.gitignore` 排除。
- 用户可见变化请更新 [CHANGELOG.md](CHANGELOG.md)。

- Public user/developer docs belong under `docs/`.
- Internal project memory stays local and is ignored by Git.
- Update [CHANGELOG.md](CHANGELOG.md) for user-visible changes.
