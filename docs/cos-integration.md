# TTMEvolve × COS 协议融入计划

> 来源：`D:\Claude code (2)\taptap-maker-project\docs\cos-collaboration-os.md`
> 目标：将 COS 协议的核心组件融入 TTMEvolve，提升跨会话记忆 + 项目管理能力

---

## 1. COS 协议核心组件

COS（Collaboration OS）定义了一套游戏开发协作规范：

| 组件 | 作用 |
|------|------|
| 记忆系统 | 跨会话持久记忆 |
| 门槛 0 请求分类 | 每次用户输入立即分类（Coding/Game/Project/Plan） |
| TodoWrite 模板 | 强制结构化任务清单 |
| POST 步骤 | 每次交付后自动更新记忆 + sprint board |
| 时间戳铁律 | 所有文档时间戳精确到分钟 |
| Health-check | POST-5 自检清单 |
| 多角色工作流 | PM / Dev / Designer / Tester |
| CLAUDE.md 注入 | AI 人格初始化 |
| 领域扩展 | 防御记忆、bug-list 等 |

---

## 2. TTMEvolve 现状对照

| COS 组件 | TTMEvolve 对应 | 状态 |
|---------|---------------|------|
| 记忆系统 | `memory/manager.py` + `learning/knowledge_seeds.py` | ✅ 已具备 |
| CLAUDE.md | `D:\CC\CLAUDE.md` | ✅ 已有 |
| MEMORY.md | `D:\ClaudeCode\config\projects\.../MEMORY.md` | ✅ 已有 |
| docs/memory-health.md | `docs/memory-health.md` | ✅ 已有 |
| Roadmap | `docs/next-steps-roadmap.md` | ✅ 已有 |
| 路线图 | `docs/v0.7.0-grand-plan.md` | ✅ 已有 |
| 测试覆盖 | `tests/` | ✅ 已有 |
| 启动器 | `start.bat` / `start.sh` | ✅ 已有 |
| **门槛 0 请求分类** | 需新增 | ⬜ |
| **TodoWrite 模板强制** | TaskCreate 等价，但需对齐 COS 格式 | ⚠️ |
| **POST 步骤自动触发** | 手动 | ⚠️ |
| **时间戳精确到分钟** | 部分 | ⚠️ |
| **Health-check 自动化** | `scripts/verify_*` 部分覆盖 | ⚠️ |
| **多角色工作流** | 缺失 | ⬜ |
| **防御记忆** | 缺失 | ⬜ |

---

## 3. 融入实施

### 3.1 第一步：基础设施（1 周）

| 文件 | 内容 |
|------|------|
| `docs/persona.md` | AI 人格文件（参考 COS §十八） |
| `docs/memory-index.md` | 记忆索引（参考 COS §七） |
| `docs/sprint-board.md` | Sprint 板（当前 sprint + 任务） |
| `scripts/costime.sh` | 时间戳铁律工具（统一写入 YYYY-MM-DD HH:MM） |
| `scripts/cos_post.sh` | POST 步骤自动触发 |

### 3.2 第二步：门槛 0 分类器（1 周）

创建 `core/intent_classifier.py`：

```python
class IntentClassifier:
    """门槛 0：根据用户输入自动分类（Coding / Game / Plan / Project）。"""

    CATEGORIES = {
        "coding": ["实现", "修复", "重构", "加功能", "测试"],
        "game": ["游戏", "策划", "文案", "案例", "Maker"],
        "plan": ["路线图", "规划", "下一步", "计划"],
        "project": ["发布", "tag", "版本", "文档"],
        "ops": ["部署", "打包", "内嵌", "启动"],
    }

    def classify(self, user_input: str) -> str:
        # 简单关键词匹配 → 可升级到 LLM 分类
        ...
```

### 3.3 第三步：POST 步骤自动化（3 天）

`scripts/cos_post.sh`：

```bash
#!/usr/bin/env bash
# POST 步骤：每次 git commit 后自动执行
set -e

# 1. 更新 memory-health.md 时间戳
TIMESTAMP=$(date +"%Y-%m-%d %H:%M")
echo "## Last updated: $TIMESTAMP" >> docs/memory-health.md

# 2. 更新 sprint-board.md
# ... (检查当前 sprint 任务完成情况)

# 3. 提示下次 POST-mem 和 POST-sync 任务
```

Git hook：

```bash
# .git/hooks/post-commit
#!/usr/bin/env bash
./scripts/cos_post.sh
```

### 3.4 第四步：时间戳铁律（2 天）

`scripts/costime.sh`：

```bash
#!/usr/bin/env bash
# 将所有 docs/*.md 中"## Last updated"时间戳更新到当前时间
TIMESTAMP=$(date +"%Y-%m-%d %H:%M")
for f in docs/*.md; do
    sed -i "s/^## Last updated: .*/## Last updated: $TIMESTAMP/" "$f"
done
```

### 3.5 第五步：Health-check 自动化（3 天）

`scripts/cos_healthcheck.sh`：

```bash
#!/usr/bin/env bash
# POST-5: Health-check 自检清单
echo "=== TTMEvolve Health Check ==="

# 1. 测试
.venv/Scripts/python.exe -m pytest tests/ -q

# 2. Lint
.venv/Scripts/python.exe -m ruff check .

# 3. 类型检查
.venv/Scripts/python.exe -m mypy core/ agent/ llm/ learning/

# 4. 文档时间戳
./scripts/costime.sh --verify

# 5. Roadmap 更新
git status docs/
```

### 3.6 第六步：多角色工作流（持续）

定义 `docs/roles/`：

```
docs/roles/
├── pm.md           ← PM 角色
├── developer.md    ← 开发者角色
├── designer.md     ← 设计师角色
└── tester.md       ← 测试角色
```

每个角色文件描述：
- 工作流
- 文档权限
- 工具权限

---

## 4. 验证清单（COS 风格）

| 项 | 检查方法 |
|----|---------|
| CLAUDE.md 存在 | `ls CLAUDE.md` |
| MEMORY.md 存在 | `ls MEMORY.md` |
| memory-index.md 存在 | `ls docs/memory-index.md` |
| sprint-board.md 存在 | `ls docs/sprint-board.md` |
| 门槛 0 分类器工作 | `./scripts/cos_intent_test.sh` |
| POST 步骤自动触发 | `git commit` 后验证 |
| 时间戳精确到分钟 | `grep "HH:MM" docs/*.md` |
| Health-check 通过 | `./scripts/cos_healthcheck.sh` 退出码 0 |

---

## 5. 与 TTMEvolve 现有机制的桥接

### 5.1 TaskCreate ↔ TodoWrite 模板

| TTMEvolve | COS 等价 |
|-----------|---------|
| `TaskCreate` | TodoWrite 创建条目 |
| `TaskUpdate status: in_progress` | 标记 "执行中" |
| `TaskUpdate status: completed` | 标记 "完成" |
| `TaskList` | TodoWrite 列表 |

### 5.2 MEMORY.md ↔ memory-index.md

`MEMORY.md` 已是 cross-project 索引。`memory-index.md` 是 per-project 索引：

```
memory-index.md:
- v0.7.0-grand-plan.md — current sprint
- seven-grand-goals.md — long-term goals
- v0.7.0-roadmap.md — near-term tasks
- bug-list-2026-06-26.md — known issues
```

### 5.3 next-steps-roadmap.md ↔ sprint-board.md

`next-steps-roadmap.md` 是长期路线，`sprint-board.md` 是当前 sprint（2 周）：

```
sprint-board.md (this sprint):
- [x] LLM Router
- [x] Theme + Settings UI
- [ ] M2 Backend API
- [ ] M3 Tauri shell
- [ ] M4 Portable startup
- [ ] M5 Test + Release
```

---

## 6. 不变的原则

> COS 的核心哲学与 TTMEvolve 一致：
> - **记忆优先**：跨会话记忆是基础
> - **结构化输出**：每个交付都有明确格式
> - **铁律不妥协**：时间戳、POST、健康检查不能跳过
> - **多角色协作**：不只一个人 + 一个 AI

---

## 7. 实施时间表

| 阶段 | 时间 | 内容 |
|------|------|------|
| 第 1 阶段 | v0.7.0 内 | 基础设施（persona、memory-index、sprint-board）+ 时间戳工具 |
| 第 2 阶段 | v0.8.0 | 门槛 0 分类器 + POST 自动化 |
| 第 3 阶段 | v0.9.0 | Health-check 自动化 + 多角色工作流 |
| 持续 | 永久 | 文档维护 + sprint 节奏 |

---

> 制定者：灰语 & 嗒啦啦
> 来源：COS v3.13（taptap-maker-project）
> 目标：把 COS 协议融入 TTMEvolve，让跨会话协作更稳定