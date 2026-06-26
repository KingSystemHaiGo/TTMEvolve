# TTMEvolve Sprint Board

> COS 协议 §三：门槛 0 分类 + 任务分级
> 当前 Sprint：v1.4.0 完整 release 准备

---

## 🎯 v1.4.0 — Release Check Sprint

### ✅ 已完成

| 版本 | 主题 | 状态 | 测试 |
|------|------|------|------|
| v0.7.0 | Tauri 桌面 + 主题 + Settings + LLM Router + portable | ✅ tag | 132 |
| v0.7.1 | Electron 删除准备（dry-run 工具 + 文档） | ✅ 脚本 | 17 |
| v0.7.2 | Rust fast_ops 模块 | ✅ tag | 13 |
| v0.7.3 | Rust ↔ Python HTTP 桥接 | ✅ tag | 14 |
| v0.8.0 | Tauri 自动桥接 + 生命周期 | ✅ tag | 12 |
| v0.9.0 | 跨平台 + 启动器完善 | ✅ tag | 14 |
| v1.0.0 | 自动更新 + 图标 | ✅ 集成 | 32 |
| v1.1.0 | 代码签名（Win/macOS/Linux） | ✅ 集成 | 18 |
| v1.2.0 | E2E 测试 | ✅ 集成 | 19 |
| v1.3.0 | 国际化（i18n） | ✅ 集成 | 31 |
| **总计** | | | **390/390** |

### 📋 v1.4.0 待办（当前 sprint）

- [ ] 时间戳同步（cos-time.sh all）
- [ ] memory-index.md 追加 v1.0-v1.3 条目
- [ ] CHANGELOG.md 撰写
- [ ] v1.4.0 tag 创建 + 推送
- [ ] 实际签名测试（待用户授权 + 证书）
- [ ] GitHub Release 创建
- [ ] 全文档更新（README + ROADMAP）

### ⏸️ 阻塞

| 项 | 原因 | 状态 |
|----|------|------|
| 实际代码签名 | 需要 EV 证书 | 待用户准备 |
| macOS 公证 | 需要 Apple Developer ID | 待用户准备 |
| Tauri 编译验证 | Rust 工具链已本机验证 | ✅ 32/32 |

### 📊 整体进度

| 模块 | 进度 |
|------|------|
| Plan First + Todolist | ✅ 100% |
| Coding Agent 强化 | ✅ 100% |
| Maker 游戏策划 | ✅ 100% |
| 知识整合 | ✅ 100% |
| 主题系统 | ✅ 100% |
| Settings 页面 | ✅ 100% |
| LLM Router | ✅ 100% |
| Tauri 桌面壳 | ✅ 100% |
| portable runtime | ✅ 100% |
| 自动更新 | ✅ 100% |
| 代码签名（脚本） | ✅ 100% |
| E2E 测试 | ✅ 100% |
| i18n | ✅ 100% |
| **总测试** | **598 Python + 32 Rust + frontend/Electron build** ✅ |

---

## 📊 整体进度

| 模块 | 进度 |
|------|------|
| Plan First + Todolist | ✅ 100% |
| Coding Agent 强化 | ✅ 100% |
| Maker 游戏策划 | ✅ 100% |
| 知识整合 | ✅ 100% |
| 主题系统 | ✅ 100% |
| Settings 页面 | ✅ 100% |
| LLM Router | ✅ 100% |
| Tauri 桌面壳 | ✅ 100% |
| portable runtime | ✅ 100% |
| **总测试覆盖** | **192/192** ✅ |

---

## 🐛 已知问题

| 问题 | 优先级 | 状态 |
|------|--------|------|
| Tauri 首次编译慢 | 🟢 | 已知，不阻塞 |
| Maker MCP 长任务轮询 | 🟡 | 设计中 |
| macOS / Linux WebView 适配 | 🟡 | v0.8.0 |
| Electron 代码清理 | 🟢 | v0.7.1 |
| 普通用户界面暴露候选工具/英文状态 | 🔴 | 已修复：主聊天隐藏候选工具列表，历史浮层可关闭，状态文案中文化 |
| 查看项目状态/了解项目工具选择不稳定 | 🔴 | 已修复：新增只读 `project_status` 并提高排序权重 |

---

## 📌 下一 Sprint（v2.0.0 路线）

- [ ] Tauri GUI 测试套件（Playwright + WebView2）
- [ ] macOS / Linux 正式版
- [ ] 国际化（i18n）前端集成
- [ ] pyo3 直接绑定（避免 HTTP 序列化）
- [ ] 多 Agent 协作模式

---

## 🎓 回顾要点

### 本 Sprint 学到的

1. **架构演进需要分阶段**：v0.6.0 → v0.7.0 保持 Electron 兼容，v0.7.1 才删除
2. **测试覆盖是迁移信心**：192/192 测试让 Tauri 迁移零回归
3. **借鉴 > 重新设计**：从 taptap-maker-plus 学 Settings 5 面板，从 COS 学记忆系统
4. **云端 LLM 是正确选择**：减少 60% 包体积，提升维护性

### 风险登记

- ⚠️ Maker MCP 远端依赖：网络抖动会失败
- ⚠️ Rust 学习曲线：未来热路径优化需 Rust 能力
- ⚠️ 跨平台 WebView 差异：Windows WebView2 / macOS webkit / Linux webkit2gtk

---

## 📞 沟通

- **用户**：灰語（Taptap Maker 开发者）
- **AI**：嗒啦啦（自进化 Agent）
- **下次更新**：v0.7.1 启动时

---

> 最后更新：2026-06-26 10:15
> 版本：v1.5.1 全量运行 bugfix
> 触发：全量 pytest / frontend build / Electron build / Cargo test
## Last updated: 2026-06-26 08:42

## 2026-06-26 13:52 Native Maker Preview

- Status: done.
- Fixed: Tauri desktop preview now uses a native child WebView2 (`maker-preview`) for normal users instead of screenshot polling.
- Preserved: Playwright browser service remains the Agent automation path.
- Verified: frontend build, Rust build/test, lifecycle/start-script tests, release build, and real `TTMEvolve.vbs` smoke with one visible app window and WebView2 child window evidence.

## 2026-06-26 14:51 Cockpit Status Placement

- Status: done.
- Moved project/model/config to the left-top chat context area.
- Kept Maker MCP status in the top bar with Maker actions.
- Moved token/latency evidence to assistant-message usage chips.
- Verified: frontend build and Tauri release build.

## 2026-06-26 MakerMCP Auto Update + Real Probe

- Status: done.
- Added automatic cached npm latest-version checks to Maker setup status.
- Added fresh Maker MCP stdio initialize/tools-list probe surfaced through `/mcp/probe`, `/mcp/status?probe=true`, and Maker setup evidence.
- GUI now shows package update evidence and real probe result, while normal polling uses cached checks.
- Verified: focused Python MCP/setup diagnostics and frontend build.

## 2026-06-26 Desktop Visual Rhythm Polish

- Status: done.
- Unified titlebar, Maker action topbar, chat context cards, conversation bar, input row, and tool buttons around shared radius/control-height tokens.
- Reduced mismatched mint panels and aligned the shell into one desktop surface.
- Verified: frontend build and browser screenshot check at 1600x900.

## 2026-06-26 Desktop UX Evidence Pass

- Status: verifying.
- Principle: screenshots are treated as stale evidence unless confirmed by current code/tests/runtime.
- Updated: history popover has explicit icon close plus Esc/outside-click dismissal.
- Updated: Workbench normal labels use Chinese product language and no longer expose candidate-count wording in user-facing summaries.
- Updated: chat status/event filtering maps tool-selection/candidate/ranking internals to "正在判断下一步".
- Added: regression coverage that project_status and execute_shell stay ahead of Maker tools for project-state/cmd requests.

## 2026-06-26 Runtime Event Bus Foundation

- Status: verifying.
- Added a shared in-process RuntimeEventBus with typed envelopes, filtered subscriptions, bounded replay, unsubscribe, stats, and observer error isolation.
- Wired AppServer sessions through the shared server event bus while preserving existing SQLite/SSE event shape.
- Verified focused runtime-event and AppServer session bus tests.
- Next: migrate more Agent/Core/Learning producers and project-management observers onto the bus instead of direct event queues.

## 2026-06-26 Agent Event Bus Migration

- Status: verifying.
- TapMakerAgent now publishes ReAct and layer events through an Agent-owned RuntimeEventBus before keeping the compatibility session queue.
- Agent event replay no longer requires direct _event_queues access for consumers that can subscribe to the bus.
- Verified layer-event tests plus runtime/AppServer bus focused tests.
- Next: expose bus stats/evidence in runtime readiness and move project-management observers onto subscriptions.

## 2026-06-26 Runtime Event Bus Evidence Surface

- Status: verified.
- Runtime Readiness now reports `runtime_event_bus` plus a release-gate check for the server/Agent bus surface.
- Session Evidence JSON/Markdown and LLM Onboarding JSON/Markdown now expose bus stats, session event counts, layer-event counts, and compatibility evidence.
- Chat/history/input surfaces were cleaned for normal users: explicit history close, Chinese/English visible labels, and no candidate-tool ranking in the main conversation.
- Verified: focused readiness/evidence endpoint pytest and `frontend` production build.
- Next: wire project-management observers onto bus subscriptions and continue replacing direct queue reads.

## 2026-06-26 Runtime Metrics Observer

- Status: verified.
- Added a live RuntimeMetricsObserver that subscribes to Runtime Event Bus session events and derives compact metrics without coupling to Session internals.
- `/sessions/{id}/runtime-metrics` now reports observer/store counts and uses observer history when available, preserving SQLite as durable fallback.
- Runtime Readiness/Evidence expose observer status so attached agents can tell whether metrics came from bus snapshots or persisted replay.
- Verified: bus observer unit test plus AppServer runtime-metrics/readiness/evidence focused tests.
- Next: add project-management task state observers on the same bus path.

## 2026-06-26 Project Management Observer

- Status: verified.
- Added a live ProjectManagementObserver that subscribes to Runtime Event Bus session events and derives next action, goal status, plan verdict, continuation readiness, artifacts, and risk flags.
- Added `/sessions/{id}/project-state` plus Evidence/Onboarding/Readiness project-state fields so external agents and the GUI can inspect project control state directly.
- Runtime Contract now advertises project-state in communication endpoints and external-agent attach sequence.
- Verified: runtime event observer tests, AppServer project-state endpoint, Evidence bundle, and Runtime Contract focused tests.
- Next: wire this project-state snapshot into the Workbench UI and use it to drive proactive next-step recommendations.

## 2026-06-26 22:29 Chinese-First Desktop UI Polish

- Status: verified.
- Fixed: main chat no longer shows candidate-tool/ranking internals; it maps those events to user-facing progress and filters raw tool-selection events.
- Fixed: history is a compact popover with an explicit close button, outside-click and Esc dismissal, and no instructional clutter.
- Fixed: primary chat/input/topbar labels are Chinese-first; GitHub README remains bilingual.
- Fixed: topbar/chat context/history surfaces share the same control heights, radii, shadows, and theme tokens.
- Verified: `npm.cmd --prefix frontend run build`, focused project-status/cmd ToolRegistry pytest (`4 passed`), and `git diff --check`.

## 2026-06-26 22:46 Vector Index Fast Path

- Status: verified.
- Fixed: FAISS search result materialization now uses `_reverse_id_map` for O(1) internal-id lookup instead of scanning every chunk id.
- Fixed: batch vector add now allocates unique internal ids even when many chunks are added in the same timestamp window.
- Preserved: keyword fallback and profile-aware cold-memory recall behavior.
- Verified: `tests/test_vector_index.py tests/test_cold_memory_vector.py tests/test_memory_manager_recall.py` -> `18 passed, 2 skipped`.

## 2026-06-26 23:08 Desktop History + Project Tool Reliability

- Status: verified.
- Fixed: history trigger now switches to `关闭历史` while open; the popover states close button, Esc, and outside-click dismissal.
- Fixed: normal chat and active status keep candidate/ranking internals hidden behind user-facing progress language.
- Fixed: `project_status` and `execute_shell` are pinned for project-state/cmd/git-status tasks even if Maker context is present.
- Preserved: `Token` and `tok/s` remain technical units in assistant usage chips.
- Verified: `npm.cmd --prefix frontend run build` and focused ToolRegistry pytest (`6 passed`).
