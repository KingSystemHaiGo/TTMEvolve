# ADR-0001: Serialize Shared Agent Runtime Before Session Isolation

## Status

Superseded by ADR-0002

## Context

The desktop App Server currently owns one `TapMakerAgent`. A session run temporarily replaces mutable runtime fields on that shared object: active LLM, ReAct event sink, human confirmation callback, executor callback, and evolution callback.

This is unsafe under concurrent sessions. Session A and Session B can overwrite each other's callbacks, provider configuration, approval bridge behavior, and event stream routing.

## Decision

Serialize `AppServer.run_session()` with a process-local runtime lock. When another session is already running, the new session is kept queued and receives a status event explaining that it is waiting.

The lock is a mitigation, not the final architecture. The target architecture is one isolated `AgentRuntime` per session, with explicitly shared services such as browser, session store, and Maker MCP proxy.

This mitigation has now been replaced by session-scoped agents. See `docs/architecture/adr-0002-session-scoped-agent-runtime.md`.

## Consequences

### Positive

- Prevents cross-session event, approval, and provider contamination immediately.
- Keeps the current AppServer and GUI protocol stable.
- Low-risk change that is easy to verify with existing tests.

### Negative

- Only one agent task can run at a time.
- Long-running approval waits block later sessions.
- Does not solve lifecycle ownership as cleanly as per-session runtimes.

### Neutral

- Browser operations remain shared and serialized by `BrowserService`.
- This decision should be revisited when `AgentRuntime` is extracted.

## Alternatives Considered

**Per-session `TapMakerAgent` immediately**

Rejected for this patch because construction touches memory, event logs, executor, browser service, generated tools, and optional MCP state. It is the right direction, but it needs a deliberate extraction with tests.

**Keep shared Agent and rely on UI to avoid concurrency**

Rejected because backend safety should not depend on frontend behavior.

## References

- `server/app_server.py`
- `docs/architecture/code-review-roadmap-2026-06-22.md`
