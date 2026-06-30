# 变更记录 / Changelog

所有值得公开说明的变更都应记录在这里。项目采用证据优先的 release 表述：未证明的能力必须明确标注。

All notable public changes should be summarized here. This project uses evidence-based release wording: unproven capabilities are called out explicitly.

## Post-v1.0.0 Slice #2 — Agent Goal Loop Evolution (multimodal, skill packs, typed DAG, feature state)

This slice upgrades the agent goal loop from a single-threaded
text-only pipeline into a typed, parallel, project-aware orchestrator.
Default behaviour for end users is unchanged; the new surfaces are
exposed through the existing agent runtime and the project-side
``docs/skill_packs/`` and ``.ttmevolve/features.jsonl`` files.

### Agent internal layers

- **Multimodal LLM interface** (`llm/content.py`,
  `llm/{claude,openai,minimax,local,mock,unconfigured}_llm.py`):
  ``ContentBlock`` carries text or image blocks through the
  provider boundary. Each provider translates the blocks into
  the right wire format (``base64`` for Anthropic, ``data:`` URL
  for OpenAI-compatible). ``MockLLM`` records every multimodal
  call so tests can assert what the agent sent. ``LLMInterface``
  gains a default ``think_multimodal`` that flattens to text
  when a provider does not opt in via ``supports_multimodal``.
- **ReAct multimodal observation handling**
  (`agent/react_loop.py`): when a tool returns image-bearing
  observations, ``_collect_think_attachments`` extracts the
  blocks and routes the next ``think`` through
  ``think_multimodal`` automatically. Text-only observations
  and text-only LLMs keep the legacy path untouched.
- **Project introspection tools** (`agent/project_introspection.py`):
  six read-only tools exposed to the agent — ``project.manifest``,
  ``project.asset_read`` (returns multimodal content), ``project.asset_search``,
  ``project.code_search`` (Lua symbol grep), ``project.preview_capture``
  (writes a placeholder PNG, returns an image block), and
  ``project.build_state``. All registered through the executor's
  dynamic-tool path with ``risk_level = "low"``.
- **Skill pack system** (`agent/skill_packs/`): project-side
  markdown knowledge base under ``docs/skill_packs/`` (engine / genre
  / project). Five seed packs ship with the package
  (UrhoX engine, Maker MCP, platformer, RPG, puzzle) and are
  auto-seeded when a project has none. The GoalLoop UNDERSTAND
  stage auto-recalls the top three packs by keyword overlap.
- **Typed sub-goal DAG** (`agent/goal_dag.py`): every sub-goal
  carries a type (code / asset / scene / audio / integration /
  test), a dependency list, a capability hint
  (``fast`` / ``balanced`` / ``deep``), and an acceptance list.
  Topological layers, parallel execution bounded by
  ``max_concurrent_subgoals``, and per-type sub-loops
  (``agent/typed_subloop.py``) ship in one commit. The legacy
  ``sub_goal_runner`` callback is still supported for backward
  compatibility.
- **Feature / ticket state machine** (`agent/feature_state.py`):
  append-only ``.ttmevolve/features.jsonl`` ledger keyed by
  task slug. Lifecycle: proposed -> approved -> in_progress ->
  blocked -> shipped -> deprecated. GoalLoop POST advances the
  feature and refreshes ``docs/sprint-board.md`` and
  ``docs/progress.md``.

### Test isolation

- New ``GoalLoop(artifacts_root=...)`` constructor argument and
  ``TTMEVOLVE_GOAL_ARTIFACTS_ROOT`` env var redirect every
  project-side write (decisions, contracts, progress, sprint
  board, skill packs) to an alternate root. ``tests/conftest.py``
  installs an autouse fixture that points the env var at a
  per-test temp dir so no test can accidentally pollute the
  dev environment. See ``CONTRIBUTING.md`` for the rule.

### Tests

- 47 new test cases across ``test_llm_content``,
  ``test_llm_multimodal``, ``test_react_multimodal``,
  ``test_project_introspection``, ``test_skill_packs``,
  ``test_goal_dag``, ``test_feature_state``,
  ``test_boss_fight_e2e``. The end-to-end boss-fight test
  exercises every layer in a single goal run.

## v1.1.0 Slice #1 — RAG / Memory / Cybernetic Control (opt-in)

这是 v1.0.0 之后的第一个功能切片。所有新能力都通过 feature flag
关闭，**默认行为与 v1.0.0 完全一致**。任何切换必须先通过
`docs/release-gates.md` 列出的 13 个 gate。

This is the first feature slice after v1.0.0. Every new capability
is feature-flagged off, so **default behaviour is identical to
v1.0.0**. Any flip must pass the 13 gates in
`docs/release-gates.md` first.

### 新增能力 / New capabilities

- **图 RAG 记忆 / Graph RAG memory** (`memory.graph.enabled`):
  cold memory 升级为带 8 种类型边的 typed-edge graph
  (references / supersedes / contradicts / supports / caused_by /
  temporal_next / decomposes_into / similar_to)。查询路径
  `ColdMemory.retrieve_with_graph` 返回五因子排序结果
  (vector + posterior + freshness + edge_support + occam)。
- **贝叶斯先验 + 奥卡姆评分 / Bayesian prior + Occam score**
  (`memory.bayes.enabled`): 每条记忆带 Beta-Bernoulli 状态，
  log1p 长度惩罚 + 0.15 上限的 evidence bonus。auto-share
  仍 forbidden，可见性决定权仍在
  `review_shared_memory_outcome()`。
- **渐进式 prompt/context loader** (`loader.enabled`): 替换
  `MemoryManager.prepare_think_payload` 的 monolithic 组装；
  按 ADR-0007 priority table 排序，stub-and-expand 模式，
  失败时优雅 defer。LLM provider adapters 零修改。
- **Plan v2 + 递归执行** (`plan.v2_enabled`):
  `core/plan_executor.py` 支持 `kind: sub_plan / branch / loop`，
  iterative DFS cycle detection，max_depth 防护。v1 plan
  自动 promote 保持兼容。
- **VSM 控制论** (`vsm.enabled`): thin `VSMShell` adapter
  (S1-S5) 接 `ControlLoop.verdict`，auto-replan 由
  `vsm.auto_replan=true` AND cooldown AND `max_replan_depth`
  三重门控；不创建第二个 control dashboard。

### 文档 / Documentation

- `docs/research/2026-memory-and-control.md` — 17 条带直接链接
  的引文（GraphRAG / HippoRAG / LightRAG / RAPTOR / MemGPT /
  Letta / A-MEM / Mem0 / DSPy / LongLLMLingua / MemoryBank /
  Bayesian RL / ADaPT / LATS / PlanBench / VSM 等）。
- `docs/architecture/adr-0004-profile-aware-graph-memory.md` —
  graph memory 的架构决策。
- `docs/architecture/adr-0007-progressive-context-loader.md` —
  prompt loader 的架构决策（编号 0007 跳过原 backlog 的 0005/0006）。
- `docs/architecture/adr-0008-plan-v2-cybernetic-control.md` —
  plan v2 + VSM 的架构决策。
- `docs/release-gates.md` — 10 个可发版 gate（G1-G10）。
- `docs/feature-flags.md` — 5 个新 feature flag 的 inventory。
- `docs/research/baseline/candidate-v1.0.0.md` — release
  candidate 摘要与升级路径。

### 测试 / Tests

- 30 个新测试（graph + bayes + prompt loader + plan v2 + VSM
  单元 / 集成），4 个 cross-surface 集成场景，3 个 live
  evidence smoke，1 个 all-flags-on end-to-end，11 个 regression
  guards。
- 30 new tests; 4 cross-surface integration scenarios; 3 live
  evidence smoke tests; 1 all-flags-on end-to-end; 11 regression
  guards.

### 可持续发布流程 / Sustainable Release Process

- `scripts/check_release_ready.py` — 一键检查 13/13 gate，
  退出码 0 表示 READY。任何 contributor 提交前都可跑。
- `tests/test_regression_guards.py` — 锁住不变量（flag 默认 off、
  production_rag_quality 保持 unproven、LLM provider 零修改、
  plan v1 向后兼容、关键文档不被删）。
- `docs/release-gates.md` 是所有 gate 的唯一真相。

### 边界 / Boundaries

- `production_rag_quality` 仍 `unproven` — 必须保持直到
  `/memory/rag-quality` 在真实 labelled corpus + 生产 embedding
  上通过。
- `signed_installer` / `maker_remote_build` 仍 `unproven` —
  下个 release 才做。
- `offline_runtime_bundle` 仍 `blocked`（vendor 6.87GB > 500MB
  预算）— pre-existing，超出本 slice 范围。
- LLM provider adapters (`claude_llm` / `local_llm` / `openai_llm` /
  `minimax_llm` / `mock_llm`) **零修改**。
- VSM 是 thin naming layer，不创建第二个 control dashboard。

### Deferred to next slice

- v1.0.0 → production cut-over
  (`scripts/release_readiness.py` 的 `DEFAULT_PACKAGE` 切换)。
- GUI smoke（Workbench 三块新 evidence 面板的实际 UI 验证）。
- Maker remote build smoke。
- Signed installer。
- Production RAG 语义质量证明。

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
