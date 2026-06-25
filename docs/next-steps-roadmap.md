# TTMEvolve v0.6.0 路线图

> 当前版本：v0.5.0
> 目标版本：v0.6.0（四大方向全部完成）

---

## 方向一：Plan First + Todolist

| 任务 | 文件 |
|------|------|
| 结构化计划格式 | `core/plan_format.py` |
| 计划阶段入口 | `agent/react_loop.py` |
| 计划审查机制 | `core/plan_review.py` |
| 计划工具（edit/approve） | `agent/builtin_tools.py` |
| 前端计划展示 | `frontend/` |
| 测试 | `tests/test_plan_first.py` |

**验收：** 用户输入 → Agent 输出计划 → 用户确认 → 执行

---

## 方向二：Coding Agent 强化

| 任务 | 文件 |
|------|------|
| `/loop` 循环模式 | `agent/react_loop.py` |
| `spawn_subagent()` | `agent/subagent.py` |
| 条件 hook 触发器 | `core/hooks.py` |
| 上下文压缩 | `core/context_compression.py` |
| 工具版本管理 | `agent/tool_registry.py` |

---

## 方向三：Maker 游戏策划与文案

| 任务 | 文件 |
|------|------|
| 游戏类型知识库 | `learning/game_knowledge.py` |
| 文案知识库 | `learning/copy_knowledge.py` |
| 机制设计知识库 | `learning/mechanics_knowledge.py` |
| Maker 案例库 | `learning/maker_cases.py` |
| 引导式策划工具 | `agent/builtin_tools.py` |

---

## 方向四：知识整合

| 任务 | 来源 |
|------|------|
| physics-2d / audio / network / graphics | `engine-docs/` |
| `urhox-libs/` 源码 API | 核心库 |
| `AGENTS.md` 开发规范 | 45KB |
| 游戏模板 | `learning/maker_templates.py` |

---

## 验收标准

```bash
python -m pytest tests/ -v
python scripts/one_click_fix_maker.py [--fix]
python scripts/verify_maker_mcp_full_path.py
```

**v0.6.0 完成条件：** 四大方向全部交付 + 测试通过 + 推送远程 + tag 创建。

---

> 开发者：灰语 & 嗒啦啦
> 原则：TTMEvolve 是主体 — Maker MCP 是能力，Coding Agent 是方法，知识库是大脑。