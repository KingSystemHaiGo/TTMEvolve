# ADR-0002: Use Session-Scoped Agent Runtime

## Status

Accepted

## Context

`AppServer` originally shared one `TapMakerAgent` across all sessions. ADR-0001 serialized `run_session()` to prevent cross-session mutation of LLM provider, ReAct event sinks, approval callbacks, and executor state.

Serialization removed corruption risk but blocked concurrent sessions and did not express the real ownership model. A session needs its own LLM, ReAct loop, executor, memory budget state, and callbacks. Some services should remain shared: App Server, session store, browser worker, and Maker MCP client.

## Decision

Each task session now builds a session-scoped `TapMakerAgent` from a cloned `Config`.

The base AppServer agent remains the GUI/control-plane agent for health, config, tools, IDE endpoints, and the shared Maker MCP connection. Session agents are created with `connect_mcp=False` and attach to the base agent's shared MCP integration. They own their ReAct loop, executor, LLM reference, callbacks, and session state, then close after the run without stopping the shared MCP client.

## Consequences

### Positive

- Removes the `_run_lock` queue and allows session runs without shared-Agent callback mutation.
- Isolates provider/model/API key overrides to a cloned session config.
- Preserves one shared Maker MCP client instead of launching one MCP process per session.
- Keeps the existing HTTP/SSE protocol stable.

### Negative

- Session startup constructs a new `TapMakerAgent`, which repeats some lightweight setup.
- Shared Maker MCP calls are still serialized by the MCP client lock.
- The base agent health endpoint does not yet expose per-session runtime health.

### Neutral

- Browser service remains a shared worker because it models one embedded browser instance.
- Tests can still inject a custom LLM; when no session override is provided, the active LLM is cloned when possible.

## Alternatives Considered

**Keep ADR-0001 serialization**

Rejected because it prevented concurrent sessions and treated a lifecycle problem as a lock problem.

**Start a full MCP client per session**

Rejected because Maker MCP startup is expensive and may create multiple `npx @taptap/maker` processes.

**Share the whole `TapMakerAgent` and only copy callbacks**

Rejected because ReAct trajectory, memory manager state, executor callbacks, and LLM references would still be easy to contaminate.

## References

- `server/app_server.py`
- `agent/agent.py`
- `agent/mcp_integration.py`
- `core/config.py`
