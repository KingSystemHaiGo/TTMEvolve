# TTMEvolve vs Rinorsi/taptap-maker-plus — 对比分析

> 通过 GitHub API 探索（未克隆，仅拉取关键文件）
> 目的：借鉴 taptap-maker-plus 的设计，同时保持 TTMEvolve 的优势

---

## 1. 仓库对比

| 维度 | taptap-maker-plus | TTMEvolve |
|------|-------------------|-----------|
| 桌面壳 | Tauri 2.x (Rust) | Electron |
| 前端 | React + Vite + Tailwind | React + Vite + 自定义 CSS |
| 后端 | Fastify (Node TS) | Python (FastAPI/uvicorn) |
| 内嵌 runtime | ❌ 依赖 npm install | ✅ portable/ Python + node |
| MCP | taptap-maker (Tauri stdio) | Maker MCP 全通路（自愈） |
| Agent | Mastra (Node) | 自研 ReAct + Plan First |

---

## 2. 模块结构（11 个）

```
home / assets / studio-image / studio-video / studio-music / studio-3d
   ↓
workflow / build / runs / agent / settings
```

**TTMEvolve 当前缺失：**

| 模块 | taptap-plus 有 | TTMEvolve 现状 |
|------|---------------|---------------|
| **首页** | 简洁仪表盘 | 有（CockpitHeader）但分散 |
| 资产库 | AssetLibrary + grid/table 视图 | ✅ 有 |
| 图像工作室 | studio-image（schema 表单） | ⚠️ 缺 |
| 视频工作室 | studio-video | ⚠️ 缺 |
| 音频工作室 | studio-music | ⚠️ 缺 |
| 3D 工作室 | studio-3d | ⚠️ 缺 |
| 节点流 | workflow（React Flow） | ⚠️ 缺 |
| 构建中心 | build | ⚠️ 缺独立页 |
| 运行记录 | runs | ⚠️ 缺独立页 |
| 助手上下文 | agent | ✅ AgentWorkbench |
| **设置** | SettingsView（5 面板） | ❌ **完全没有** |

---

## 3. Settings 页面（参考设计）

taptap-maker-plus 的 SettingsView 有 **5 个面板**：

1. **当前项目** — 项目名 / 路径 / project_id / config.json
2. **MCP Runtime** — 状态 / processId / cwd / tools/list 时间 / 启动命令
3. **真实 MCP Schema** — 工具总数 / 各分类数量 / 表单来源
4. **本地工作台能力** — HTTP API / 前端 / Schema Form / Workflow Canvas / Asset Table
5. **开发者模式** — F12 开关 / 日志 / DevTools 按钮 / 复制日志 / 清空

附加：
- 前端诊断日志（RawViewer）
- Runtime Error 面板

---

## 4. 设计原则（用户提出）

> "设置和次级页面什么的，都需要有设置等等"

**原则确认：**

| 原则 | 实现要点 |
|------|---------|
| ✅ 不装环境依赖 | portable/ 推到 git（已实现） |
| ✅ 优先用内嵌 runtime | start.sh / start.bat 优先 .venv + portable node |
| ✅ 首屏简洁 | 当前首屏 OK，保留 |
| ✅ **设置页面要丰富** | **需新建 SettingsView** |
| ✅ 次级页面齐全 | 缺 8 个模块：studio-image/video/music/3d、workflow、build、runs、settings |

---

## 5. 路线图更新（v0.7.0）

### Phase 1：设置页面（最高优先）
- `frontend/src/components/SettingsView.tsx` — 5 面板
- `frontend/src/components/SettingsPanel.tsx` — 通用面板容器
- `frontend/src/components/SettingRow.tsx` — key/value 行
- `core/runtime_info.py` — 后端：暴露 MCP / 项目 / runtime 信息
- `server/app_server.py` — `/api/settings/runtime-info` 端点

### Phase 2：Studio 模块（4 个）
- studio-image / studio-video / studio-music / studio-3d
- 每个 = `inputSchema`-driven 表单 + 历史记录 + 资产关联
- 后端：`server/studio_routes.py`

### Phase 3：Workflow / Build / Runs
- workflow：React Flow 节点流（@xyflow/react）
- build：构建中心 + 日志
- runs：运行历史 + 错误诊断

### Phase 4：portable runtime 强化
- 确保 `start.bat` 优先 portable/python + portable/node
- 验证离线安装（断网测试）
- README 加 "无需任何依赖" 徽章

---

## 6. 可借鉴代码

| 借鉴项 | 文件 |
|--------|------|
| SettingsView 5 面板 | `apps/web/src/features/settings/SettingsView.tsx` |
| Routes 11 模块 | `apps/web/src/app/routes.ts` |
| Tauri portable 配置 | `src-tauri/Cargo.toml` |
| Fastify 服务启动 | `apps/server/src/index.ts` |

---

> 决策：克隆权限被拒，未本地克隆。仅通过 GitHub API 学习。
> 下一步：用户决定是否同意克隆完整代码 / 接受当前 API 学习程度。