# TTMEvolve Sprint Board

> COS 协议 §三：门槛 0 分类 + 任务分级
> 当前 Sprint：v0.7.0 发布后 → v0.7.1 启动

---

## 🎯 当前 Sprint（2026-06-26 ~ 2026-07-10）

### ✅ 已完成（v0.7.0）

- [x] M1a 内嵌环境包 + LLM 路由层（云端）
- [x] M1b 主题系统 + Settings 页面（5 面板）
- [x] M2 后端 API（/api/settings/*）
- [x] M3 Tauri 壳 + Rust 服务管理
- [x] M4 portable 启动 + 离线测试
- [x] M5 性能优化 + 测试 + 发布（tag v0.7.0 推送）
- [x] COS 基础设施：persona.md / memory-index.md

### 🔄 进行中

- [ ] sprint-board.md（本文件）— 进行中
- [ ] costime.sh 工具脚本
- [ ] intent_classifier.py（门槛 0 分类器）

### 📋 即将开始

- [ ] v0.7.1：删除 Electron 代码
- [ ] v0.7.1：Tauri 调试模式优化
- [ ] v0.7.1：完整 E2E 测试（Tauri + Python）

### ⏸️ 阻塞

（无）

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

## 📌 下一 Sprint（v0.7.1，2026-07-10 ~ 2026-07-24）

- [ ] 删除 Electron 全部代码
- [ ] Tauri 端到端测试套件
- [ ] intent_classifier.py（门槛 0）
- [ ] costime.sh 自动化
- [ ] POST 步骤自动化（git commit hook）
- [ ] desktop 图标设计
- [ ] 桌面打包测试（Windows installer）

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

> 最后更新：2026-06-26 22:30
> 版本：v0.7.0
> 触发：git commit / git push 后手工同步 + 每周 review