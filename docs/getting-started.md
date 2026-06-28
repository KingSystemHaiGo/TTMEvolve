# 快速开始 / Getting Started — Contributor Edition

This document is for **contributors** who want to set up a working
TTMEvolve checkout, run the test suite, and verify the release
gates. End-user installation is in [README.md](../README.md).

本文面向**贡献者**：本地 checkout 怎么搭、测试怎么跑、release
gates 怎么过。终端用户安装见 [README.md](../README.md)。

## 0. 前置条件 / Prerequisites

- **Windows 10/11** with WebView2 runtime (default on Windows 11)
- **Python 3.12** (the project embeds 3.12.10 in `vendor/python/`)
- **Node 20.x** (embedded in `vendor/node/`)
- **Rust 1.7x+** with `cargo` on PATH (for Tauri)
- **Visual Studio Build Tools 2022** (for the Tauri Rust build)
- **MinGit 2.4x+** (embedded in `vendor/`)

> The launcher (`start-tauri.bat`) prefers the embedded `vendor/`
> runtimes over `.venv/` and over system tools. The instructions
> below assume a source checkout that does **not** have the
> embedded runtimes yet.

## 1. 克隆 / Clone

```powershell
git clone https://github.com/KingSystemHaiGo/TTMEvolve.git
cd TTMEvolve
```

## 2. Python venv

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -U pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt   # if present
```

## 3. Frontend deps

```powershell
cd frontend
npm.cmd install
npm.cmd run build
cd ..
```

## 4. Build the embedded Tauri exe (optional, for the desktop shell)

```powershell
cd src-tauri
cargo build --release
cd ..
```

The release exe ends up in `src-tauri/target/release/ttmevolve.exe`.
If you skip this step, the launcher will build it on first run.

## 5. Run the test suite

```powershell
# Baseline (RAG performance + runtime contract) — 14 tests
.venv\Scripts\python.exe -m pytest tests/test_rag_performance.py tests/test_runtime_contract.py -q

# Slice #1 unit + integration
.venv\Scripts\python.exe -m pytest tests/test_memory_graph.py tests/test_memory_bayes.py tests/test_memory_manager_graph_recall.py tests/test_prompt_loader.py tests/test_loader_integration.py tests/test_condition_dsl.py tests/test_plan_executor.py tests/test_vsm.py tests/test_react_loop_vsm.py -q

# Slice #1 cross-surface + smoke
.venv\Scripts\python.exe -m pytest tests/test_integration_all_flags_on.py tests/test_integration_scenarios.py tests/test_smoke_evidence_new_fields.py -q

# Full sweep
.venv\Scripts\python.exe -m pytest -q
```

> The full sweep takes a few minutes. Some tests are flaky in the
> wide run because they share a Windows temp dir. Run the targeted
> suites above first; only run the full sweep before pushing.

## 6. Run the release gates

```powershell
.venv\Scripts\python.exe scripts\check_release_ready.py
```

Expected output (last 4 lines):

```
========================================================================
Gates passed: 13 / 13

READY -- slice #1 satisfies every gate in docs/release-gates.md.
```

If any gate fails, the script tells you which one. **Do not silence
the gate**; fix the underlying cause.

## 7. Build the source release candidate

```powershell
.venv\Scripts\python.exe scripts/package_release.py
```

The artifact lands in `release-artifacts/TTMEvolve-source-vX.Y.Z.zip`
plus its `*.zip.manifest.json`. See
[`docs/research/baseline/candidate-vX.Y.Z.md`](research/baseline/candidate-v1.0.0.md)
for the candidate template.

## 8. Promote a release (rare, do not script casually)

1. Update `scripts/release_readiness.py`'s `DEFAULT_PACKAGE` to the
   new candidate zip.
2. Run `release_readiness --mode source-checkpoint --json` and
   confirm `status=ready`.
3. Run a real GUI smoke pass (out of scope of this doc).
4. Update `docs/memory-health.md` and `docs/CHANGELOG.md` with the
   promotion record.
5. Tag the commit and push.

## 9. Where to look next

- [`docs/feature-flags.md`](feature-flags.md) — the five new feature
  flags introduced in v1.1.0
- [`docs/release-gates.md`](release-gates.md) — the 10 gates and
  what each protects
- [`docs/architecture/adr-0004-profile-aware-graph-memory.md`](architecture/adr-0004-profile-aware-graph-memory.md)
- [`docs/architecture/adr-0007-progressive-context-loader.md`](architecture/adr-0007-progressive-context-loader.md)
- [`docs/architecture/adr-0008-plan-v2-cybernetic-control.md`](architecture/adr-0008-plan-v2-cybernetic-control.md)
- [`docs/research/2026-memory-and-control.md`](research/2026-memory-and-control.md)
  — the research basis for the slice

## 10. If something goes wrong

- **Tests fail with `ModuleNotFoundError`**: re-run step 2; the venv
  may not be active.
- **Frontend build complains**: re-run step 3; `node_modules` may
  be missing.
- **`check_release_ready.py` reports BLOCKED on
  `release_readiness`**: run
  `scripts/release_readiness.py --mode source-checkpoint --json`
  directly to see the actual blockers.
- **A regression guard fails**: read
  `tests/test_regression_guards.py` to see which invariant
  regressed. Do not silence the guard.
