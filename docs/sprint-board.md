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
