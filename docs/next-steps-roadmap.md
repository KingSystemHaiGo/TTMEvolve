# TTMEvolve v0.6.0 路线图

> 当前版本：v0.5.0
> 目标版本：v0.6.0（四大方向 + 外部项目学习）
> 约束：Abidingenuity 前端设计不变，仅可增加选择卡片类功能

---

## 学习输入

| 来源 | 关键产出 | 约束 |
|------|----------|------|
| `D:\Claude code (2)\Abidingenuity` | 滚动章节树记忆、苏格拉底式提问、可玩原型生成、HTML 持久化 | **前端设计不变，仅增加选择卡片类功能** |
| `D:\CC\Ima导出\` 自进化agent 之一~七 | 四层进化层次、ReAct+反思、控制论、权威回溯+隔离、终身学习、Harness | 自由借鉴 |

---

## 方向一：Plan First + Todolist（优先级最高）

| 任务 | 文件 | 说明 |
|------|------|------|
| 结构化计划格式 | `core/plan_format.py` | 定义计划数据结构（步骤、依赖、预期证据） |
| 计划阶段入口 | `agent/react_loop.py` | `_run()` 开始前增加计划阶段 |
| 计划审查机制 | `core/plan_review.py` | LLM 或规则驱动计划审查 |
| 计划工具（edit/approve） | `agent/builtin_tools.py` | `edit_plan` / `approve_plan` 工具 |
| 前端计划展示 | `frontend/` | **仅新增选择卡片**，不改动现有 UI |
| 测试 | `tests/test_plan_first.py` | 端到端测试 |

**验收：** 用户输入 → Agent 输出结构化计划 → 用户通过卡片确认 → 执行

---

## 方向二：Coding Agent 强化

| 任务 | 文件 | 说明 |
|------|------|------|
| `/loop` 循环模式 | `agent/react_loop.py` | 定期轮询、检查、迭代 |
| `spawn_subagent()` | `agent/subagent.py`（新建） | Codex 并行子代理 |
| 条件 hook 触发器 | `core/hooks.py` | 工具执行前后条件判断 |
| 上下文压缩 | `core/context_compression.py` | 长对话自动摘要（Abidingenuity memory.py 借鉴） |
| 工具版本管理 | `agent/tool_registry.py` | 工具版本历史、回滚 |
| 权威回溯+隔离 | `core/event_log.py` 强化 | Ima 之七：不可篡改审计日志 |

---

## 方向三：Maker 游戏策划与文案

| 任务 | 文件 | 说明 |
|------|------|------|
| 游戏类型知识库 | `learning/game_knowledge.py` | 放置、RPG、益智、跑酷等模板 |
| 文案知识库 | `learning/copy_knowledge.py` | 引导、剧情、对话、通知 |
| 机制设计知识库 | `learning/mechanics_knowledge.py` | 核心循环、进度、奖励 |
| Maker 案例库 | `learning/maker_cases.py` | 成功游戏案例分析 |
| 苏格拉底式策划工具 | `agent/builtin_tools.py` | Abidingenuity socratic.py 借鉴 |
| 引导式策划工具 | `agent/builtin_tools.py` | "做一个跑酷游戏" → 自动生成 GDD |
| 文案生成工具 | `agent/builtin_tools.py` | 引导、剧情、运营文案生成 |

**验收：** 用户说"做一个跑酷游戏" → Agent 输出游戏设计文档 + 推荐玩法 + 文案样例

---

## 方向四：知识整合

| 任务 | 文件 | 来源 |
|------|------|------|
| 滚动章节树记忆 | `core/scroll_chapter.py`（新建） | Abidingenuity memory.py |
| embedding 语义排序 | `learning/knowledge_base.py` | Abidingenuity embedding.py |
| Harness Engineering | `core/harness.py`（新建） | Ima 之五 |
| 控制论 PID 自我校正 | `core/control_loop.py`（新建） | Ima 之五 |
| physics-2d / audio / network / graphics | `learning/engine_knowledge.py` | engine-docs |
| `urhox-libs/` 源码 API | `learning/urhox_api.py` | 核心库 |
| `AGENTS.md` 开发规范 | `learning/agents_md_knowledge.py` | 45KB |
| 游戏模板 | `learning/maker_templates.py` | 综合 |

---

## UI/前端约束

| 规则 | 说明 |
|------|------|
| 不改 Abidingenuity 前端设计 | 现有 UI 完全保留 |
| 仅可增加选择卡片类功能 | 卡片化展示、卡片化选择、卡片化确认 |
| TTMEvolve 前端 | 自由扩展（计划展示、知识库浏览、文案生成 UI 等） |

---

## 验收标准

```bash
python -m pytest tests/ -v
python scripts/one_click_fix_maker.py [--fix]
python scripts/verify_maker_mcp_full_path.py
```

**v0.6.0 完成条件：**
- [ ] 四大方向全部交付
- [ ] 外部项目学习已吸收
- [ ] Abidingenuity 前端设计未改动
- [ ] 测试通过
- [ ] 推送远程 + tag v0.6.0

---

> 开发者：灰语 & 嗒啦啦
> 原则：TTMEvolve 是主体 — Maker MCP 是能力，Coding Agent 是方法，知识库是大脑。