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
.venv\Scripts\python.exe scripts\check_release_ready.py
```

前三条是常规 build + test 套件；第四条是 v1.1.0+ 的必跑 gate check。
提交前**所有四条都要绿**。

The first three are the standard build + test suite; the fourth is
the v1.1.0+ required gate check. **All four must be green before
submitting**.

## PR 要求 / Pull Request Expectations

- 说明改了什么、为什么改。
- 写清楚验证命令和结果。
- 公开能力声明必须有证据；未证明的能力请写 `unproven`、`partial` 或 `experimental`。
- 不要提交本地/私有项目记忆文件。公开仓库会刻意排除内部 sprint logs 和 agent handoff memory。
- **v1.1.0+ 提交前必跑**：[`scripts/check_release_ready.py`](scripts/check_release_ready.py) 必须输出 `READY`。
  PR description 附上 13/13 gate 截图或最后几行输出。

- Explain what changed and why.
- Include verification commands and results.
- Keep public claims evidence-based. If a capability is not proven, call it `unproven`, `partial`, or `experimental`.
- Do not include local/private project memory files. The public repository intentionally excludes internal sprint logs and agent handoff memory.
- **Required before any v1.1.0+ PR**:
  [`scripts/check_release_ready.py`](scripts/check_release_ready.py) must
  print `READY`. Attach the gate output to the PR description.

## v1.1.0 Slice #1 贡献须知 / Slice #1 Contributor Notes

如果你的改动涉及 v1.1.0 的任何 feature flag 或 release gate：

If your change touches any v1.1.0 feature flag or release gate:

1. **新增 feature flag** — 在 `docs/feature-flags.md` 加一行
   inventory；在 `tests/test_regression_guards.py` 的
   `test_feature_flags_default_off` 路径里加一行
   `("scope", "name")`。默认必须 `false`。
2. **修改 release gate** — 在 `docs/release-gates.md` 同步更新
   gate 描述；在 `scripts/check_release_ready.py` 同步更新
   gate 检查。
3. **覆盖 LLM provider adapter** — 默认禁止；
   `tests/test_regression_guards.py::test_llm_provider_files_unchanged`
   会失败，请把改动放到 `MemoryManager` / `PromptLoader` /
   `VSMShell` 那一层。
4. **改动 plan v1 解析** — 必须保持 v1 plan 能正常 execute。
   `tests/test_regression_guards.py::test_plan_v1_backward_compat`
   会卡住。

## 文档 / Documentation

- 面向用户和贡献者的公开文档放在 `docs/`。
- 内部项目记忆留在本地，并通过 `.gitignore` 排除。
- 用户可见变化请更新 [CHANGELOG.md](CHANGELOG.md)。

- Public user/developer docs belong under `docs/`.
- Internal project memory stays local and is ignored by Git.
- Update [CHANGELOG.md](CHANGELOG.md) for user-visible changes.

## 测试隔离 / Test Isolation

开发环境（dev tree）和 GoalLoop 的运行产物（decisions / system-contracts / progress / sprint board / skill packs）**必须严格分开**。任何把测试数据写到真实项目根目录的提交都会被退回。

Production GoalLoop writes and the dev tree **must stay separate**. PRs that leak test data into the real project root will be rejected.

### Rule

- 写测试时**不要**给 `GoalLoop(project_root=<真实项目>)` 同时让 GoalLoop 跑出 side effects（CONFIRM artifacts、progress.md、sprint board、skill packs）。
- Do **not** pass the real project root to `GoalLoop` while letting it run with side effects (CONFIRM artifacts, progress.md, sprint board, skill packs).
- 测试用 `tmp_path` 当 `project_root`，**或**显式传 `artifacts_root=tmp_path`。
- Use `tmp_path` as `project_root`, **or** pass `artifacts_root=tmp_path` explicitly.

### How it works

- `GoalLoop.__init__` 接受可选的 `artifacts_root` 参数。`artifacts_root` 不传时默认等于 `project_root`（生产行为）。`artifacts_root=tmp_path` 把所有写到 `decisions/`、`system-contracts/goals/`、`docs/progress.md`、`docs/sprint-board.md`、`docs/skill_packs/` 的内容重定向到 tmp。
- `GoalLoop(artifacts_root=...)` defaults to `project_root` (production). Pass `artifacts_root=tmp_path` to redirect every write under decisions, system-contracts, progress, sprint board, and skill packs to a temp dir.
- `tests/conftest.py` 装了一个 `autouse` fixture：每个测试默认把 `TTMEVOLVE_GOAL_ARTIFACTS_ROOT` 设到 per-test tmp dir。**任何新测试即使传了真项目根，artifacts 也会自动隔离**。
- `tests/conftest.py` installs an autouse fixture that points `TTMEVOLVE_GOAL_ARTIFACTS_ROOT` at a per-test temp dir. New tests that pass the real project root are isolated automatically.
- 在 ad-hoc 跑 GoalLoop 演示时也可用环境变量手动覆盖：`TTMEVOLVE_GOAL_ARTIFACTS_ROOT=/tmp/foo`。
- For ad-hoc demos, override the env var: `TTMEVOLVE_GOAL_ARTIFACTS_ROOT=/tmp/foo`.

### Diagnosing leaks

跑测试后 `git status` 应当不出现 `decisions/`、`system-contracts/`、`docs/progress.md`、`docs/sprint-board.md`、`docs/skill_packs/` 等 untracked 条目。出现就是隔离破坏，立刻定位测试加 `artifacts_root=tmp_path` 或 `project_root=tmp_path`。

After running tests, `git status` should not show `decisions/`, `system-contracts/`, `docs/progress.md`, `docs/sprint-board.md`, or `docs/skill_packs/` as untracked. If they do, isolation is broken — locate the offending test and add `artifacts_root=tmp_path` or use `project_root=tmp_path`.
