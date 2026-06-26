# Agent Core Health Audit - 2026-06-26

> English below each Chinese section. This document is an evidence-based audit, not a marketing claim.

## 结论 / Conclusion

TTMEvolve 当前已经具备一个可验证的本地编程 Agent 核心：它可以读取项目状态、新建用户文档、创建/修改文件、运行受控系统命令、记录执行事件、输出运行证据，并通过 Agent/Runtime/Learning 三层事件暴露内部状态。

TTMEvolve now has a verifiable local coding-agent core: it can inspect project state, create user documents, create/modify files, run controlled shell commands, record execution events, produce runtime evidence, and expose Agent/Runtime/Learning state through layer events.

但它还不能诚实宣称已经达到 Claude Code 或 Codex 的完整水平。差距主要在大型真实仓库任务 benchmark、长期自主规划质量、交互式终端深度、补丁质量自动评估、跨会话工程记忆质量、真实 GUI 编程任务闭环，以及更强的代码审查/回滚/分支工作流。

It should not yet claim full Claude Code or Codex parity. The remaining gaps are large-repo benchmarks, long-horizon planning quality, deep interactive terminal support, automated patch quality assessment, cross-session engineering memory quality, real GUI coding-task loops, and stronger review/rollback/branch workflows.

## 已证明能力 / Proven Capabilities

| Capability | Evidence | 中文说明 |
| --- | --- | --- |
| Agent execution chain | `TapMakerAgent -> ReActLoop -> ToolRegistry -> Executor -> Sandbox/Approval -> EventLog` | Agent 动作不是直接乱跑命令，而是经过注册、校验、沙箱、审批、事件日志。 |
| Project inspection | `project_status` tool, `tests/test_tool_call_validation.py::test_executor_project_status_reports_git_and_top_level` | 能查看项目根、顶层目录、常见项目标记和 Git 摘要。 |
| User document creation | `create_document` tool, `tests/test_tool_call_validation.py::test_coding_agent_can_create_user_document` | 能新建 Markdown/text/JSON 文档，默认不覆盖已有文件。 |
| File creation/editing | `modify_file`, `VersionManager` snapshot before write, commit-state recording | 能新建/修改项目内文件，并对副作用工具记录提交状态。 |
| Shell execution | `execute_shell`, sandbox prefix checks, timeout handling | 能运行受控命令，超时会杀进程树并返回机器可读观察。 |
| Minimal coding loop | `tests/test_tool_call_validation.py::test_coding_agent_minimal_programming_smoke` | ReAct 可在临时项目里看状态、新建 Python 文件、运行文件并总结结果。 |
| Multi-layer observability | `tests/test_app_server_resume.py::test_app_server_persists_layer_and_learning_events` | Agent/Runtime/Learning 层事件可持久化并进入 Evidence Bundle。 |
| Runtime readiness/evidence | `tests/test_runtime_contract.py`, `/runtime/readiness`, `/sessions/{id}/evidence` | 外部或任意 LLM 可拉取紧凑证据，而不是读原始日志。 |
| Tool-call validation | `tests/test_tool_call_validation.py` | 错误工具名/参数会返回结构化错误和替代建议。 |
| Safety boundaries | `tests/test_sandbox.py`, `tests/test_tool_timeouts.py` | read-only/workspace/danger 模式有边界；危险命令和超时场景有测试。 |

## 当前测试证据 / Current Test Evidence

Commands run on 2026-06-26:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_tool_call_validation.py::test_coding_agent_minimal_programming_smoke -q
# 1 passed

.venv\Scripts\python.exe -m pytest tests\test_tool_call_validation.py::test_coding_agent_can_create_user_document -q
# 1 passed

.venv\Scripts\python.exe -m pytest tests\test_e2e_runtime.py tests\test_runtime_contract.py tests\test_app_server_resume.py::test_app_server_persists_layer_and_learning_events -q
# 28 passed

.venv\Scripts\python.exe -m pytest tests\test_tool_call_validation.py tests\test_sandbox.py tests\test_tool_timeouts.py tests\test_plan_first.py tests\test_plan_first_integration.py tests\test_plan_validation.py tests\test_coding_agent_v060.py tests\test_runtime_events.py tests\test_runtime_contract.py -q
# 86 passed
```

## 健康度判断 / Health Assessment

| Area | Status | Notes |
| --- | --- | --- |
| Core coding actions | Ready for controlled local use | 读文件、写文件、新建文档、命令执行、项目状态已经可测。 |
| Architecture layering | Healthy but still young | 三层事件已存在；需要更多用户任务级可视化诊断。 |
| Safety | Baseline ready | 沙箱、审批、超时、提交状态存在；还需要更细的命令策略和用户可理解解释。 |
| Performance | Instrumented, not fully optimized | 已有 latency/runtime metrics；缺少持续性能基准和大仓库压力测试。 |
| Product usability | Improving | GUI 越来越像应用；Agent 能力解释和失败恢复还要更“用户语言”。 |
| Claude Code/Codex parity | Not proven | 不能只靠小烟测声称达到，需要真实 benchmark 和大型任务成功率。 |

## 必须补强 / Required Next Work

1. Build a real coding benchmark suite.
   建立真实编程 benchmark：修 bug、加功能、跑测试、解释 diff、失败恢复，覆盖小/中/大仓库。

2. Expand OS/document operations as first-class tools.
   `create_document` 已补齐；下一步把读取常见文件类型、打开目录/文件、终端会话等做成明确工具，而不是都塞进 `execute_shell`。

3. Improve shell capability without losing safety.
   增强终端能力：支持长任务、流式输出、交互式进程、后台服务管理，同时保持沙箱和审批。

4. Add automated patch review gates.
   增加自动补丁审查：diff 摘要、风险点、测试覆盖匹配、回滚建议。

5. Make multi-layer architecture user-visible only where useful.
   三层架构继续保留证据，但普通用户界面只展示“正在规划/执行/验证/学习”这类可理解状态。

6. Add performance baselines.
   记录工具排序耗时、首 token/首响应、上下文构建、文件搜索、大目录扫描、Maker MCP 调用延迟。

7. Verify real GUI coding task loop.
   从桌面 GUI 发起一个真实任务，证明它能在用户可见体验里完成读写文件、跑测试、显示结果。

## Product Claim Boundary

Acceptable claim:

> TTMEvolve has a verified local coding-agent core with controlled document creation, file edits, shell execution, project inspection, runtime evidence, and layered observability.

可接受表述：

> TTMEvolve 已有可验证的本地编程 Agent 核心，支持受控文档创建、文件编辑、命令执行、项目状态检查、运行证据和分层可观测性。

Not acceptable yet:

> TTMEvolve is already at full Claude Code/Codex level.

暂时不应宣称：

> TTMEvolve 已经达到 Claude Code/Codex 完整水平。
