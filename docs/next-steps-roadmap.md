# TTMEvolve 后续工作路线图

> 生成时间：2026-06-25
> 当前版本：v0.4.5 → 迈向 v0.5.0（Maker Self-Healing）

---

## 已完成的工作

### Maker MCP 全通路

| 项目 | 状态 |
|------|------|
| `server/maker_faults.py` — 14 种故障类型，7 层分类 | 已完成 |
| `learning/knowledge_seeds.py` → 45+ 条知识种子（原 10 条） | 已完成 |
| `agent/agent.py` — 集成 `seed_knowledge_base()` | 已完成 |
| `server/maker_setup.py` — 集成 `build_maker_fault_analysis()` | 已完成 |
| `server/app_server.py` — `/maker/repair` 端点 | 已完成 |
| `scripts/one_click_fix_maker.py` — 独立一键修复脚本 | 已完成 |
| `scripts/verify_maker_mcp_full_path.py` — 全通路验证脚本 | 已完成 |
| 空白创世游戏拉取到 `D:\本地开发测试` | 已完成 |
| Maker MCP 全通路 8/8 检查通过 | 已完成 |

### 引擎知识萃取

| 项目 | 状态 |
|------|------|
| Maker MCP Guide 知识提取（初始化、Git 策略、故障恢复、升级） | 已完成 |
| UrhoX Lua 引擎知识提取（Core API、UI、物理、相机陷阱） | 已完成 |
| 知识写入 TTMEvolve 记忆系统 | 已完成 |
| 知识种子扩展（Maker MCP Guide、UrhoX Engine、Coding Agent 模式） | 已完成 |

### Git 状态

已提交文件：
- 修改：`agent/agent.py`、`core/runtime_contract.py`、`server/app_server.py`、`server/maker_setup.py`、`tests/test_maker_setup.py`
- 新增：`learning/knowledge_seeds.py`、`server/maker_faults.py`、`tests/test_knowledge_seeds.py`、`scripts/one_click_fix_maker.py`、`scripts/verify_maker_mcp_full_path.py`

---

## 后续工作（按优先级排序）

### Phase 1：代码清理与第一次发布 ✅

- [x] 审查所有新文件代码品质，确保 docstring 一致
- [x] 更新版本号到 `v0.5.0`
- [x] 撰写发布说明 `docs/releases/v0.5.0-maker-self-healing.md`
- [x] 执行 `git add` + `git commit -m "v0.5.0: Maker MCP self-healing, knowledge seeds expansion"`
- [x] 建立 tag `v0.5.0`
- [ ] 推送到 `KingSystemHaiGo/TTMEvolve`

### Phase 2：剩余知识整合

- [ ] 读取更多 `engine-docs/` 内容（physics-2d、audio、input、network、graphics）
- [ ] 读取 `urhox-libs/` 核心库源码萃取 API 知识
- [ ] 读取 `AGENTS.md`（45KB）萃取 Maker 项目开发规范
- [ ] 将 `engine-docs/` 中的示例代码转化为知识库条目
- [ ] 建立 `learning/maker_templates.py` 游戏模板

### Phase 2：Coding Agent 框架提升

- [x] `core/hooks.py` — pre_session / post_session hooks 已加入
- [x] `core/repair.py` — 指数退避重试（FAULT_MAX_RETRIES + _compute_backoff + jitter）
- [x] `learning/skill_generator.py` — 技能生成后自动触发跨生态导出
- [x] `ecosystem/opencode_adapter.py` — opencode 适配器（新建）
- [ ] `/loop` 循环执行模式
- [ ] `spawn_subagent()` 工具（Codex 并行子代理）
- [ ] TTMEvolve 内部工具支持条件 hook 触发器

### Phase 3：知识整合（持续）

- [x] 已读取 engine-docs/ 核心知识（gotchas、API、UI、physics、camera）
- [ ] 读取 `urhox-libs/` 核心库源码
- [ ] 读取 `AGENTS.md`（45KB）完整内容
- [ ] 建立 `learning/maker_templates.py` 游戏模板
- [ ] 补全 engine-docs/audio、engine-docs/network、engine-docs/graphics

### Phase 4：Maker MCP 深度自修复

- [ ] MCP 子进程看门狗（crash 后自动重启）
- [ ] 远程 MCP 版本兼容性检查
- [ ] `batch_generate_images`/`edit_image` 远程 500 的回退策略
- [ ] MCP 连接历史趋势跟踪
- [ ] 长时间任务进度推送

---

## 关键检查点

```bash
# Maker MCP 一键诊断
python scripts/one_click_fix_maker.py [--fix]

# Maker MCP 全通路验证
python scripts/verify_maker_mcp_full_path.py

# 知识库种子测试
python -m pytest tests/test_knowledge_seeds.py -v
```

---

## 相关文件

- Maker 项目：`D:\本地开发测试` (project_id: `5daf0266-822a-471c-8c43-b92f1d20d5e7`)
- Maker MCP Guide：`C:\Users\WXT\AppData\Local\npm-cache\_npx\...\taptap-maker-local\SKILL.md`
- 引擎文档：`D:\本地开发测试\engine-docs\`
- Lua 示例：`D:\本地开发测试\examples\`
- ATMEvolve 配置：`D:\CC\TTMEvolve\config.json`

---

> **开发者**：灰语 & 嗒啦啦
> **核心原则**：TTMEvolve 是主体 — Maker MCP 是能力，Coding Agent 是方法，知识库是大脑。
