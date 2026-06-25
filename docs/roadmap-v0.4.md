# TTMEvolve v0.4 路线图

> 整合新需求与原路线图的统一规划。
> 更新时间：2026-06-17

---

## 一、目标

将 TTMEvolve 从「CLI/GUI 薄客户端 + Python Server」升级为：

- **自然语言优先**的跨平台桌面 Agent
- **Electron + Python 后端**架构
- 内嵌 **Chromium 浏览器预览**，支持用户登录与 Agent 自动化测试
- 轻量 **IDE 能力**：文件树、编辑器、MD/HTML 预览、素材库
- **动态知识库**：AGENTS.md 向量索引 + 动态工具调用
- **本地 LLM KV Cache**，提升 MiniCPM5-1B 多轮推理性能

---

## 二、阶段规划

| 阶段 | 内容 | 对应原路线图 |
|---|---|---|
| **Phase 1** | Electron + Python 后端骨架，IPC 通信，左侧聊天 + 右侧预览布局 | 原 #3 升级 |
| **Phase 2** | LLM KV Cache（system + prefix） | 原 #4「优化 local model 输出质量」 |
| **Phase 3** | AGENTS.md 向量索引 + 动态工具 | 新增知识库化 |
| **Phase 4** | 向量记忆系统 sentence-transformers + FAISS | 原 #6（M2） |
| **Phase 5** | IDE 界面：文件树、Monaco 编辑器、MD/HTML 预览 | 新 GUI 改造 |
| **Phase 6** | 素材库 + 图片/音视频预览 | 新功能 |
| **Phase 7** | 内嵌 Chromium 浏览器 + Playwright CDP | 新浏览器需求 |
| **Phase 8** | 专家救援闭环实测 ✅ | 原 #5 |
| **Phase 9** | 真实 TapTapMaker 游戏功能开发 ⏭️ 跳过 | 原 #8 |
| **Phase 10** | 结构优化 + 本地模型性能优化 + 全运行环境内嵌（免安装）✅ | 原 #4/#7 性能/打包 |
| **Phase 11** | 跨平台内嵌（macOS / Linux portable）⏳ | 新 |

---

## 三、技术栈

- **前端**：Electron + React + Vite
- **编辑器**：Monaco Editor
- **后端**：Python + FastAPI / stdio
- **Agent**：ReAct + Tool Registry + MCP
- **浏览器**：内嵌 Chromium（Electron WebView / WebView2 CDP）+ Playwright
- **记忆**：Hot/Warm/Cold + FAISS 向量检索
- **LLM**：MiniCPM5-1B 本地 + API 兜底
- **知识库**：AGENTS.md 向量化 + 动态工具

---

## 四、关键设计原则

1. **自然语言是入口**，CLI 退化为调试工具。
2. **AGENTS.md 是动态知识库**，不是硬编码规则；硬性规则用 `validate_policy` 拦截。
3. **浏览器内嵌桌面**，用户登录态持久化，Agent 通过 CDP 共享同一 Chromium 实例。
4. **跨平台优先**，不绑定 Windows WebView2。
5. **性能红线**：KV cache、流式输出、异步 IO、IPC 精简、懒加载。
6. **COS 记忆骨架**：POST 循环、五层记忆、任务分级 [S/M/L/XL]。

---

## 五、交付节奏

### 第一轮：Agent 底座升级
- Phase 1：Electron + Python 后端骨架
- Phase 2：LLM KV Cache
- Phase 3：AGENTS.md 向量索引与动态工具
- Phase 4：向量记忆系统

### 第二轮：IDE 界面
- Phase 5：文件树 / 编辑器 / 预览
- Phase 6：素材库
- Phase 7：内嵌浏览器 + Playwright CDP

### 第三轮：实战验证
- Phase 8：专家救援闭环实测
- Phase 9：真实 TapTapMaker 游戏功能开发
- Phase 10：性能优化与一键打包

---

## 六、不做的事

- 不做通用 IDE（不追求 VS Code 级别功能）
- 不替代 Claude Code / Cursor
- Agent 不处理用户登录凭证
- 不照搬 COS 游戏专属文档体系
- 不做多窗口/复杂窗口管理（首期）

---

## 七、关联文件

- `AGENT.md`：项目核心记忆
- `docs/cos-collaboration-os.md`：COS 框架规则
- `taptap-maker-project/AGENTS.md`：TapTap Maker Agent 行为规范
