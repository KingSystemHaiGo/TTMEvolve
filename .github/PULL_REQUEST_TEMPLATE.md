## 摘要 / Summary

<!-- 改了什么，为什么改？ / What changed and why? -->

## 验证 / Verification

<!-- 粘贴命令和结果。 / Paste commands and results. -->

### v1.1.0+ release gates

- [ ] 跑了 `scripts/check_release_ready.py`，输出 `READY` (13/13 gates)。
- [ ] Ran `scripts/check_release_ready.py`, output `READY` (13/13 gates).
- [ ] baseline tests (`tests/test_rag_performance.py` + `tests/test_runtime_contract.py`) 14/14 pass。
- [ ] Baseline tests pass (14/14).
- [ ] 受影响的 integration test 都 pass（`test_integration_all_flags_on.py` / `test_integration_scenarios.py` / `test_smoke_evidence_new_fields.py`）。
- [ ] All affected integration tests pass.
- [ ] 11 个 regression guards 全 pass（`tests/test_regression_guards.py`）。
- [ ] All 11 regression guards pass.

### 文档同步

- [ ] `CHANGELOG.md` 加了 user-visible 的 entry。
- [ ] Added a user-visible entry to `CHANGELOG.md`.
- [ ] 新 feature flag（如有）已加到 `docs/feature-flags.md`。
- [ ] Any new feature flag is in `docs/feature-flags.md`.
- [ ] 新 release gate（如有）已加到 `docs/release-gates.md` 和 `scripts/check_release_ready.py`。
- [ ] Any new release gate is in `docs/release-gates.md` and `scripts/check_release_ready.py`.

## 发布与安全说明 / Release / Safety Notes

- [ ] 未包含私有运行时状态、credentials、Maker auth、models 或 build artifacts。
- [ ] No private runtime state, credentials, Maker auth, models, or build artifacts are included.
- [ ] 公开能力声明有测试、运行证据支撑，或已标记为 unproven。
- [ ] Public capability claims are backed by tests, runtime evidence, or marked unproven.
- [ ] 用户可见行为变化已同步文档。
- [ ] Documentation was updated when user-facing behavior changed.
- [ ] LLM provider adapters（`llm/claude_llm.py` / `local_llm.py` / `openai_llm.py` / `minimax_llm.py` / `mock_llm.py`）未被修改，或改动在 PR 描述里单独说明。
- [ ] LLM provider adapters are not modified, or any change is explicitly justified in the PR description.

## v1.1.0 Slice #1 触碰点 / Slice #1 Touch Points

如果 PR 涉及下列任一项，请在描述里单独列出：

If the PR touches any of the following, call them out explicitly:

- [ ] `memory/graph.py` / `memory/bayes.py` / `memory/cold.py`（graph / bayes / retrieve_with_graph）
- [ ] `llm/prompt_loader.py` / `llm/context_budget.py`（loader / fit_fragments）
- [ ] `core/plan_executor.py` / `core/condition_dsl.py` / `core/vsm.py` / `core/plan_format.py`（plan v2 / VSM）
- [ ] `server/evidence_bundle.py` / `server/rag_evidence_service.py`（evidence surfaces）
- [ ] `scripts/check_release_ready.py`（release-gate 脚本）
- [ ] `tests/test_regression_guards.py`（防回归锁）
