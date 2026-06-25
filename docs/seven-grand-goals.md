# TTMEvolve 七大目标 — 终极规划

> 七大目标来源于用户最终愿景。整合 v0.7.0 大版本、COS 协议、taptap-maker-plus 学习成果。

---

## 目标 1：v0.7.0 完全开发

**里程碑（5 个）：**

| 里程碑 | 内容 | 状态 |
|--------|------|------|
| **M1a** | 内嵌环境包 + LLM 路由层（云端） | ✅ 已完成 |
| **M1b** | 主题系统 + Settings 页面（5 面板） | 🔄 进行中 |
| **M2** | 后端 API：/api/settings/* | ⬜ |
| **M3** | Tauri 2.x 桌面壳 + Rust 服务管理 | ⬜ |
| **M4** | portable 启动逻辑 + 离线测试 | ⬜ |
| **M5** | 性能优化 + 测试 + 文档 + 发布 | ⬜ |

**关键技术决策（已锁定）：**
- 架构：Tauri 2.x + Rust 内核（热路径）+ Python 后端
- LLM：纯云端（删除本地模型），LLMRouter 多 Provider + 故障转移
- 包体积：~200MB（不含可选模型）
- 性能：启动 < 2s，内存 < 80MB

---

## 目标 2：整体结构全部优化

### 2.1 代码结构

```
TTMEvolve/
├── core/                   ← 核心运行时（事件日志、Hook、Plan、Control、Scroll）
├── agent/                  ← Agent 层（ReAct、SubAgent、Tools）
├── llm/                    ← LLM 层（Router、Providers、Factory）
├── learning/               ← 学习层（Reflection、Skill、Knowledge、Game）
├── memory/                 ← 记忆层（Manager、Index、Self）
├── ecosystem/              ← 跨生态适配器
├── server/                 ← HTTP 服务（API、Maker、Studio）
├── frontend/               ← React UI（components/ui、components/settings、hooks、styles）
├── src-tauri/              ← Tauri 桌面壳（Rust）
├── electron/               ← 旧 Electron 壳（deprecated，v0.8.0 删除）
├── scripts/                ← 构建脚本、诊断脚本
├── docs/                   ← 文档
├── portable/               ← 内嵌环境（Python、Node、Maker MCP）
└── tests/                  ← 测试
```

### 2.2 优化清单

| 类别 | 内容 | 优先级 |
|------|------|--------|
| 公共 API | `core/__init__.py` 暴露所有公开符号 | ✅ 已做 |
| 模块边界 | `core`、`agent`、`llm`、`learning` 严格分层 | 🔄 进行中 |
| 类型注解 | 全模块加 type hints（mypy --strict 友好） | 🟡 |
| 文档字符串 | 每个模块顶部说明用途 + 使用示例 | 🟡 |
| 命名规范 | 移除 `_*` 私有泄漏，统一 snake_case | 🟢 |
| 测试覆盖 | v0.7.0 完成后覆盖率 > 80% | 🟡 |

### 2.3 性能优化

| 维度 | 现状 | 目标 |
|------|------|------|
| 启动时间 | ~5s | < 2s |
| 后台内存 | ~150MB | < 80MB |
| 包体积 | ~120MB | < 80MB |
| API 响应 | ~50ms | < 16ms |

---

## 目标 3：TapTapMaker 能力完全掌握

### 3.1 已掌握

- ✅ Maker MCP 全通路（14 种故障、7 层分类）
- ✅ 一键修复脚本（`scripts/one_click_fix_maker.py`）
- ✅ 全通路验证脚本（`scripts/verify_maker_mcp_full_path.py`）
- ✅ Maker 集成测试（`tests/test_maker_setup.py`，8 项）

### 3.2 待掌握

- ⬜ Maker 资产库集成（生成图片 / 视频 / 音乐 / 3D）
- ⬜ Maker 长任务轮询（异步任务进度跟踪）
- ⬜ Maker 远端同步（多端资产一致性）
- ⬜ Maker Build 流程深度集成（自动 commit / push / build）

### 3.3 学习资源

- `D:\Claude code (2)\Abidingenuity` — 创意工作流参考
- `D:\Claude code (2)\taptap-maker-plus` — Maker 工作台设计
- `D:\本地开发测试` — 真实 Maker 项目
- `D:\Claude code (2)\taptap-maker-project\docs\` — Maker 完整文档

---

## 目标 4：Maker MCP 一键修复（"出任何问题都能一键修复"）

### 4.1 已实现

- `scripts/one_click_fix_maker.py [--fix]` — 检测 + 自动修复
- `scripts/verify_maker_mcp_full_path.py` — 8 步端到端验证
- 14 种故障分类、7 层修复策略

### 4.2 待加强

| 故障场景 | 检测 | 自动修复 |
|---------|------|---------|
| npx 缺失 | ✅ | ✅ |
| Maker MCP 配置缺失 | ✅ | ✅ |
| 项目未绑定 | ✅ | ⚠️ 引导 |
| Auth 过期 | ⚠️ | ⬜ |
| npx 进程崩溃 | ⚠️ | ⬜ |
| 远端 500 错误 | ✅ | ⚠️ 重试 |
| tools/list 为空 | ✅ | ✅ |
| 上传超时 | ⚠️ | ⬜ |

### 4.3 "出任何问题" 的承诺

- ✅ 检测覆盖所有已知故障
- ✅ 自动修复常见问题
- ⚠️ 未知故障 → 友好报错 + 详细诊断报告
- ⬜ 远端 Maker MCP 故障 → 等待 + 重试 + 降级

---

## 目标 5：现代化桌面级应用

### 5.1 功能要求

| 类别 | 现状 | 目标 |
|------|------|------|
| 首屏 | 简洁 | ✅ 保留 |
| 设置页 | ❌ | ✅ v0.7.0 M1b |
| 主题切换 | ❌ | ✅ v0.7.0 M1b |
| 资产库 | ✅ | ✅ |
| Agent 助手 | ✅ | ✅ |
| 节点流 | ❌ | ⬜ |
| Studio | ❌ | 不做 |
| Build | ⚠️ | ✅ |
| Runs | ❌ | ⬜ |

### 5.2 UI 标准

- 设计令牌系统（CSS 变量）✅ v0.7.0 M1b
- 亮色 / 暗色主题 ✅ v0.7.0 M1b
- 通用组件库（Button / Panel / Toggle）✅ v0.7.0 M1b
- 卡片化展示（settings 选择卡片）✅ v0.7.0 M1b
- 响应式（桌面 1600×900 主屏）✅

### 5.3 性能标准

- 启动 < 2s
- 内存 < 80MB
- API 响应 < 16ms
- UI 渲染 < 16ms / 60fps

---

## 目标 6：Coding 能力 + 游戏开发思路 + 项目管理能力

### 6.1 Coding 能力

| 能力 | 状态 |
|------|------|
| ReAct 推理循环 | ✅ |
| Plan First + Todolist | ✅ |
| SubAgent 并行 | ✅ |
| Context 压缩 | ✅ |
| Hook 系统 | ✅ |
| Loop 调度 | ✅ |
| PID 自我校正 | ✅ |
| 滚动章节树记忆 | ✅ |
| LLM 路由 + 故障转移 | ✅ |

### 6.2 游戏开发思路

| 知识 | 状态 |
|------|------|
| 6 种游戏类型（runner/tower/match3/shooter/idle/puzzle） | ✅ |
| 机制设计 5 类规则 | ✅ |
| 文案模板 + 批评 | ✅ |
| Maker 案例库 | ✅ |
| 苏格拉底式策划 | ✅ |
| UrhoX 引擎 5 子系统 | ✅ |

### 6.3 项目管理能力

| 能力 | 状态 |
|------|------|
| Roadmap 文档 | ✅ |
| 发布说明 | ✅ |
| 标签管理（v0.5.0 / v0.6.0 / v0.7.0） | ✅ |
| Commit 规范 | ✅ |
| 模块索引 | ✅ |
| 路线图 | ✅ |

---

## 目标 7：COS 协议融入

### 7.1 COS 是什么

**游戏开发协作操作系统（Collaboration OS）**，来自 `D:\Claude code (2)\taptap-maker-project\docs\cos-collaboration-os.md`：

- 跨会话持久记忆
- 游戏开发全流程文档体系
- 多角色工作流
- 规定动作（门槛 0、TodoWrite 模板、POST 步骤）

### 7.2 融入策略

| COS 组件 | TTMEvolve 对应 | 状态 |
|---------|---------------|------|
| 记忆系统 | `memory/manager.py` + `learning/knowledge_seeds.py` | ✅ 已有 |
| CLAUDE.md | `D:\CC\CLAUDE.md` | ✅ 已有 |
| POST 步骤 | `MEMORY.md` 自动更新 | ⚠️ 手动 |
| 门槛 0 请求分类 | 需补 | ⬜ |
| TodoWrite 模板 | TaskCreate / TaskUpdate | ✅ 等价 |
| 时间戳铁律 | docs/ 时间戳精确到分钟 | ⚠️ 部分 |
| Health-check | `scripts/verify_*` | ✅ 已有 |
| 文档体系 | `docs/` 已具备 | ✅ 已有 |

### 7.3 待融入

| 项 | 工作量 |
|----|--------|
| 门槛 0 分类器（识别 Coding / Game / Project / Plan） | 中 |
| POST 步骤自动触发（每次 commit 后自动更新 docs/memory-health.md） | 小 |
| 时间戳精确到分钟（统一更新所有 docs/ 文件） | 小 |
| COS 模板文件 → TTMEvolve docs 模板 | 中 |
| multi-role 工作流（PM / Dev / Designer / Tester） | 大 |

### 7.4 融入方案

```
TTMEvolve/
├── docs/
│   ├── CLAUDE.md              ← 已有（用户记忆）
│   ├── next-steps-roadmap.md  ← 已有（路线图）
│   ├── memory-health.md       ← 已有（COS 风格）
│   ├── v0.6.0-module-index.md ← 已有
│   ├── v0.7.0-grand-plan.md   ← 已有
│   ├── seven-grand-goals.md   ← 本文件
│   ├── cos-integration.md     ← COS 融入详细计划（待写）
│   └── archive/               ← COS 归档
├── memory/
│   ├── manager.py             ← 已有
│   └── index/                 ← COS 风格索引
└── .claude/
    └── hooks/                 ← COS 钩子
```

---

## 七大目标依赖关系

```
目标 1（v0.7.0 完全开发）
   │
   ├─→ 目标 5（现代化桌面应用）
   │     │
   │     └─→ 目标 2（结构优化）
   │
   ├─→ 目标 6.1（Coding 能力）— 已具备大部分
   │     │
   │     └─→ 目标 6.2（游戏开发思路）— 已在 v0.6.0 知识整合
   │           │
   │           └─→ 目标 6.3（项目管理）— 已有路线图
   │
   ├─→ 目标 3（Maker 能力完全掌握）
   │     │
   │     └─→ 目标 4（Maker MCP 一键修复）— 已具备，需要加强
   │
   └─→ 目标 7（COS 协议融入）
         │
         └─→ 与目标 6.3 互补（项目管理）
```

---

## 接下来怎么做

### 第一优先级（M1b 完成后）

| 任务 | 工期 |
|------|------|
| 完善 Settings 页面 5 面板接线 | 1 天 |
| 主题切换集成到 AppShell | 1 天 |
| M2 后端 API（/api/settings/runtime-info 等） | 3 天 |
| 写 COS 融入详细计划 | 1 天 |

### 第二优先级

| 任务 | 工期 |
|------|------|
| M3 Tauri 壳 | 1 周 |
| M4 portable 启动 | 3 天 |
| M5 测试 + 文档 + 发布 | 1 周 |

### 第三优先级（持续）

- 目标 3（Maker 能力补全）
- 目标 4（一键修复增强）
- 目标 7（COS 融入）

---

> 制定者：灰语 & 嗒啦啦
> 原则：性能优先 / 响应速度 / 后台占用 / 持续升级 / COS 协作 / 不装环境 / 云端 LLM