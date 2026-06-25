# TTMEvolve 后续工作路线图

> 生成时间：2026-06-25
> 当前版本：v0.5.0
> 下一目标：v0.6.0（Coding Agent 强化 + Plan First）

---

## v0.5.0 已完成 ✅

| 项目 | 状态 |
|------|------|
| Maker MCP 全通路自愈（14 种故障、7 层分类） | ✅ |
| 知识种子扩展（45+ 条） | ✅ |
| 指数退避重试 | ✅ |
| 技能生成自动导出 | ✅ |
| 一键修复脚本 + 全通路验证脚本 | ✅ |
| 发布说明 + tag v0.5.0 + 已推送 | ✅ |

---

## 四大方向（v0.6.0 主线）

### 方向一：Agent Plan First + Todolist 实现

**现状分析：**
- `goal_checklist`（todolist）：✅ 已实现，`core/goal_tracking.py`，每次迭代注入 context
- `plan_validation`（事后验证）：✅ 已实现，`core/plan_validation.py`
- `plan_first`（先计划后执行）：❌ 未实现

**实现计划：**

| 任务 | 文件 | 说明 |
|------|------|------|
| [ ] 添加计划阶段入口 | `agent/react_loop.py` | `_run()` 开始前增加计划阶段 |
| [ ] 结构化计划输出格式 | `core/plan_format.py`（新建） | 定义计划数据结构（步骤、依赖、预期证据） |
| [ ] 计划审查机制 | `core/plan_review.py`（新建） | LLM 或规则驱动计划审查 |
| [ ] 计划可编辑/确认 | `agent/builtin_tools.py` | 提供 `edit_plan` / `approve_plan` 工具 |
| [ ] 计划与执行解耦 | `agent/react_loop.py` | 计划阶段结束后再进入执行循环 |
| [ ] 前端计划展示 | `frontend/` | 计划列表、步骤状态、编辑功能 |
| [ ] 测试 | `tests/test_plan_first.py`（新建） | 端到端测试 |

**验收标准：**
- 用户输入任务 → Agent 先输出结构化计划 → 用户确认 → 执行
- 计划可编辑、跳过、强制执行
- todolist 与计划步骤联动

---

### 方向二：Coding Agent 能力强化

**ReAct Loop 优化：**

| 任务 | 文件 | 说明 |
|------|------|------|
| [ ] `/loop` 循环执行模式 | `agent/react_loop.py` | 支持定期轮询、检查、迭代 |
| [ ] `spawn_subagent()` 工具 | `agent/subagent.py`（新建） | Codex 并行子代理 |
| [ ] 条件 hook 触发器 | `core/hooks.py` | 工具执行前后条件判断 |
| [ ] 更好的上下文压缩 | `core/context_compression.py` | 长对话自动摘要 |
| [ ] 多轮反思整合 | `learning/reflection.py` | 每次迭代后自动反思 |

**Tool Registry 增强：**

| 任务 | 文件 | 说明 |
|------|------|------|
| [ ] 工具版本管理 | `agent/tool_registry.py` | 工具版本历史、回滚 |
| [ ] 工具发现增强 | `agent/tool_discovery.py` | 自动发现项目中的工具 |
| [ ] 跨 Agent 工具调用 | `ecosystem/opencode_adapter.py` | opencode 工具互操作 |

**MCP 集成增强：**

| 任务 | 文件 | 说明 |
|------|------|------|
| [ ] MCP 工具 schema 缓存 | `agent/mcp_integration.py` | 避免重复 schema 获取 |
| [ ] MCP 连接池 | `agent/mcp_client.py` | 多 MCP 服务器复用 |
| [ ] MCP 健康检查 | `agent/mcp_integration.py` | 定期检查 MCP 可用性 |

---

### 方向三：Maker 游戏开发策划与文案能力

**知识库扩展：**

| 任务 | 优先级 | 说明 |
|------|--------|------|
| [ ] 游戏类型知识库 | `learning/game_knowledge.py`（新建） | 放置类、RPG、益智、跑酷等模板 |
| [ ] 游戏文案知识库 | `learning/copy_knowledge.py`（新建） | 引导语、剧情、对话、通知文案 |
| [ ] 游戏机制设计 | `learning/mechanics_knowledge.py`（新建） | 核心循环、进度系统、奖励设计 |
| [ ] Maker 案例库 | `learning/maker_cases.py`（新建） | 成功游戏案例分析 |

**游戏策划技能：**

| 任务 | 说明 |
|------|------|
| [ ] 引导式游戏策划 | 用户说"做一个跑酷游戏"，自动生成游戏设计文档 |
| [ ] 玩法原型建议 | 根据游戏类型推荐核心玩法、关卡设计思路 |
| [ ] 数值平衡建议 | 速度、难度、奖励的平衡参数 |
| [ ] 美术风格指南 | 根据游戏类型推荐美术风格、色彩方案 |

**文案生成能力：**

| 任务 | 说明 |
|------|------|
| [ ] 游戏引导文案 | 开始画面、教程、提示文案生成 |
| [ ] 剧情文案 | 任务描述、对话、故事背景生成 |
| [ ] 运营文案 | 活动通知、成就描述、排行榜文案生成 |

---

### 方向四：知识整合（持续）

**引擎知识补全：**

| 任务 | 说明 |
|------|------|
| [ ] physics-2d 深入 | 碰撞、刚体、物理事件 |
| [ ] audio 深入 | 背景音乐、音效、空间音频 |
| [ ] input 深入 | 触摸、键盘、手柄输入 |
| [ ] network 深入 | P2P、HTTP、WebSocket |
| [ ] graphics 深入 | 渲染管线、材质、着色器 |

**源码萃取：**

| 任务 | 说明 |
|------|------|
| [ ] `urhox-libs/` 核心库 | 源码 API 知识提取 |
| [ ] `AGENTS.md` 完整内容 | Maker 项目开发规范萃取 |
| [ ] `engine-docs/` 示例代码 | 转化为可执行知识条目 |

**游戏模板：**

| 任务 | 说明 |
|------|------|
| [ ] `learning/maker_templates.py` | 内置游戏模板（跑酷、射击、益智） |

---

## 版本规划

| 版本 | 主题 | 主要任务 |
|------|------|----------|
| **v0.5.0** | Maker MCP 自愈 | ✅ 已完成 |
| **v0.6.0** | Coding Agent 强化 | Plan First、todolist、Coding 能力强化 |
| **v0.7.0** | 游戏策划能力 | 游戏知识库、文案生成、玩法设计 |
| **v0.8.0** | 知识整合完成 | 引擎源码、完整模板库 |

---

## 关键检查点

```bash
# 运行所有测试
python -m pytest tests/ -v

# Maker MCP 一键诊断
python scripts/one_click_fix_maker.py [--fix]

# Maker MCP 全通路验证
python scripts/verify_maker_mcp_full_path.py
```

---

## 相关文件

- Maker 项目：`D:\本地开发测试`
- Maker MCP Guide：见 npm-cache
- 引擎文档：`D:\本地开发测试\engine-docs\`
- Lua 示例：`D:\本地开发测试\examples\`

---

> **开发者**：灰语 & 嗒啦啦
> **核心原则**：TTMEvolve 是主体 — Maker MCP 是能力，Coding Agent 是方法，知识库是大脑。
