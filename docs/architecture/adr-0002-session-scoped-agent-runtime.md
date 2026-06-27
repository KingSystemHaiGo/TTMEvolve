# ADR-0002: 使用会话级 Agent 运行时 / Use Session-Scoped Agent Runtime

## 状态 / Status

已接受 / Accepted

## 背景 / Context

早期 `AppServer` 在所有 sessions 之间共享一个 `TapMakerAgent`。ADR-0001 通过串行化 `run_session()` 来避免 LLM provider、ReAct event sinks、approval callbacks 和 executor state 的跨会话污染。

`AppServer` originally shared one `TapMakerAgent` across all sessions. ADR-0001 serialized `run_session()` to prevent cross-session mutation of LLM provider, ReAct event sinks, approval callbacks, and executor state.

串行化降低了状态污染风险，但阻塞并发 session，也没有表达真实 ownership model。一个 session 应该拥有自己的 LLM、ReAct loop、executor、memory budget state 和 callbacks。App Server、session store、browser worker 和 Maker MCP client 这类服务则应保持共享。

Serialization removed corruption risk but blocked concurrent sessions and did not express the real ownership model. A session needs its own LLM, ReAct loop, executor, memory budget state, and callbacks. Some services should remain shared: App Server, session store, browser worker, and Maker MCP client.

## 决策 / Decision

每个任务 session 都从 cloned `Config` 构建一个 session-scoped `TapMakerAgent`。

Each task session now builds a session-scoped `TapMakerAgent` from a cloned `Config`.

基础 AppServer agent 保留为 GUI/control-plane agent，负责 health、config、tools、IDE endpoints 和共享 Maker MCP connection。Session agents 使用 `connect_mcp=False` 创建，并挂接到 base agent 的共享 MCP integration。它们拥有自己的 ReAct loop、executor、LLM reference、callbacks 和 session state，运行结束后关闭，但不会停止共享 MCP client。

The base AppServer agent remains the GUI/control-plane agent for health, config, tools, IDE endpoints, and the shared Maker MCP connection. Session agents are created with `connect_mcp=False` and attach to the base agent's shared MCP integration. They own their ReAct loop, executor, LLM reference, callbacks, and session state, then close after the run without stopping the shared MCP client.

## 影响 / Consequences

### 正向 / Positive

- 移除 `_run_lock` 队列，避免 shared-Agent callback mutation。
- Provider/model/API key overrides 被隔离在 cloned session config 中。
- 保留单个共享 Maker MCP client，避免每个 session 启动一个 MCP process。
- 保持现有 HTTP/SSE protocol 稳定。

- Removes the `_run_lock` queue and allows session runs without shared-Agent callback mutation.
- Isolates provider/model/API key overrides to a cloned session config.
- Preserves one shared Maker MCP client instead of launching one MCP process per session.
- Keeps the existing HTTP/SSE protocol stable.

### 负向 / Negative

- Session startup 会构建新的 `TapMakerAgent`，重复少量轻量 setup。
- Shared Maker MCP calls 仍会被 MCP client lock 串行化。
- Base agent health endpoint 尚未展示 per-session runtime health。

- Session startup constructs a new `TapMakerAgent`, which repeats some lightweight setup.
- Shared Maker MCP calls are still serialized by the MCP client lock.
- The base agent health endpoint does not yet expose per-session runtime health.

### 中性 / Neutral

- Browser service 保持共享 worker，因为它建模的是一个 embedded browser instance。
- Tests 仍可注入 custom LLM；没有 session override 时，会尽可能 clone active LLM。

- Browser service remains a shared worker because it models one embedded browser instance.
- Tests can still inject a custom LLM; when no session override is provided, the active LLM is cloned when possible.

## 备选方案 / Alternatives Considered

### 保留 ADR-0001 串行化 / Keep ADR-0001 serialization

拒绝。它阻止并发 session，并把 lifecycle 问题当成 lock 问题处理。

Rejected because it prevented concurrent sessions and treated a lifecycle problem as a lock problem.

### 每个 session 启动完整 MCP client / Start a full MCP client per session

拒绝。Maker MCP 启动成本高，也可能创建多个 `npx @taptap/maker` 进程。

Rejected because Maker MCP startup is expensive and may create multiple `npx @taptap/maker` processes.

### 共享整个 `TapMakerAgent`，只复制 callbacks / Share the whole `TapMakerAgent` and only copy callbacks

拒绝。ReAct trajectory、memory manager state、executor callbacks 和 LLM references 仍然容易互相污染。

Rejected because ReAct trajectory, memory manager state, executor callbacks, and LLM references would still be easy to contaminate.

## 参考 / References

- `server/app_server.py`
- `agent/agent.py`
- `agent/mcp_integration.py`
- `core/config.py`
