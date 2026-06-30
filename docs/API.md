# App Server API

默认本地服务：

Default local server:

```text
http://127.0.0.1:7345
```

## 核心端点 / Core Endpoints

| Method | Path | 用途 / Purpose |
| --- | --- | --- |
| `GET` | `/health` | 健康与运行时状态 / Health and runtime status |
| `POST` | `/sessions` | 创建 Agent 会话 / Create an Agent session |
| `GET` | `/sessions/{id}/events` | SSE 事件流 / SSE event stream |
| `POST` | `/sessions/{id}/cancel` | 取消会话 / Cancel a session |
| `POST` | `/config/llm` | 更新 LLM 配置 / Update LLM configuration |
| `POST` | `/llm/probe` | 探测已配置的 LLM Provider / Probe configured LLM provider |

## 运行时证据 / Runtime Evidence

| Method | Path | 用途 / Purpose |
| --- | --- | --- |
| `GET` | `/runtime/readiness` | 无网络运行时就绪 gate / No-network runtime readiness gate |
| `GET` | `/runtime/portable` | portable 环境诊断 / Portable environment diagnostics |
| `GET` | `/sessions/{id}/evidence?steps=20` | 紧凑运行时证据包 / Compact runtime evidence bundle |
| `GET` | `/agent/onboarding?session_id=...&steps=20` | 外部 Agent onboarding bundle / External Agent onboarding bundle |

## Maker 集成 / Maker Integration

| Method | Path | 用途 / Purpose |
| --- | --- | --- |
| `GET` | `/maker/setup-status` | Maker 设置状态 / Maker setup status |
| `GET` | `/maker/tool-audit` | Maker 远端/本地工具审计 / Maker remote/local tool audit |
| `POST` | `/maker/repair` | 在支持时修复 Maker 接入 / Repair Maker access where supported |

## Provider 调用证明 / Provider Proof

使用 `/llm/probe` 验证已配置的 provider 是否真的被调用。MiniMax 应观察到 `/text/chatcompletion_v2`；OpenAI-compatible providers 应观察到 `/chat/completions`；Claude-style providers 应观察到 `/messages`。

Use `/llm/probe` to verify that a configured provider is actually called. MiniMax should observe `/text/chatcompletion_v2`; OpenAI-compatible providers should observe `/chat/completions`; Claude-style providers should observe `/messages`.

## Agent 内部 API (Python) / Agent Internal API (Python)

这些是 agent 进程内**可被新代码直接 import** 的公共 API。文档接口稳定；具体行为以源文件 docstring 为准。

These are **public Python APIs** that new agent code can import directly. The contract is stable; see the per-module docstring for behavior.

### Multimodal LLM / Multimodal LLM

- `from llm.content import ContentBlock, TextBlock, ImageBlock` — pass text or image to a provider. `to_anthropic_messages(blocks)` / `to_openai_messages(blocks)` translate for the wire.
- `from llm.interface import LLMInterface` — providers opt into multimodal via `supports_multimodal = True` and override `think_multimodal`.

### Project introspection / Project introspection

- `from agent.project_introspection import ProjectIntrospector, register_introspection_tools` — six read-only tools (`project.manifest`, `project.asset_read`, `project.asset_search`, `project.code_search`, `project.preview_capture`, `project.skill_pack`).

### Skill packs / Skill packs

- `from agent.skill_packs import SkillPackRegistry, SkillPackStorage, SkillPack` — project-side knowledge base. `get_or_create_registry(project_root)` seeds defaults.
- `from agent.skill_packs.bootstrap import bootstrap_default_packs, get_or_create_registry` — seed and lookup.

### Typed sub-goal DAG / Typed sub-goal DAG

- `from agent.goal_dag import SubGoalSpec, SubGoalType, GoalDAGScheduler, topological_layers` — typed parallel sub-goal execution with per-type sub-loops in `agent.typed_subloop`.

### Feature / ticket state machine / Feature / ticket state machine

- `from agent.feature_state import FeatureLedger, FeatureState, Feature, render_progress_md` — append-only ledger at `<artifacts_root>/.ttmevolve/features.jsonl`.

### Goal loop artifact isolation / Goal loop artifact isolation

`GoalLoop.__init__` accepts an optional `artifacts_root` parameter. Production code passes nothing (artifacts live under the project root); tests pass `artifacts_root=tmp_path` or set the `TTMEVOLVE_GOAL_ARTIFACTS_ROOT` env var. See `CONTRIBUTING.md` for the dev-vs-artifact isolation rule.
