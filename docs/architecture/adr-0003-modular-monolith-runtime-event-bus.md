# ADR-0003: Use A Modular Monolith With RuntimeEventBus Spine

## Status

Accepted

## Context

TTMEvolve is a desktop application with a Tauri/React shell, a Python AppServer, local storage, Maker MCP integration, RAG/memory services, and session-scoped agent runtimes. The current scaling problem is not multi-server deployment. The pressure is internal: large orchestration files, mixed ownership between HTTP transport and runtime evidence, direct state reads, heavy context loading, and hard-to-audit layer boundaries.

The product needs independent Agent, Core Runtime, and Learning layers while preserving one-click local startup and stable GUI behavior. It also needs durable evidence for truthfulness gates, COS project control, multi-agent memory policy, and long-task continuity.

## Decision

Keep TTMEvolve as a modular monolith and use `RuntimeEventBus` as the in-process communication spine.

Modules should own clear responsibilities:

- Agent layer: planning, tool choice, user-facing answers, and compact advice consumption.
- Core Runtime layer: validation, execution, sandbox, Maker/browser/shell authority, runtime events, and side-effect evidence.
- Learning layer: async reflection, knowledge extraction, shared-memory promotion proposals, and validation results.
- Server layer: HTTP/SSE transport, session lifecycle, persistence, evidence surfaces, and GUI-facing APIs.
- Memory layer: hot/warm/cold recall, vector index, quality evaluation, privacy policy, and shared outcome ledger.

Live cross-layer facts should move through `RuntimeEventBus` observers by default. SQLite remains durable replay. SSE remains a UI transport and compatibility surface, not the architectural source of truth.

## Consequences

### Positive

- Keeps local desktop deployment simple while allowing strong module boundaries.
- Avoids premature microservice operational cost.
- Gives Runtime Readiness, Evidence Bundle, Layer Health, Engineering Control, and Onboarding a common event source.
- Allows consumers such as runtime metrics, project state, learning state, and memory recall to be tested without reading private ReAct state.
- Supports truthfulness gates because claims can cite event, benchmark, endpoint, or persisted evidence.

### Negative

- In-process bus failure handling and observer health must be maintained carefully.
- Module boundaries still depend on discipline and tests; Python cannot enforce all architectural ownership rules.
- Long-running or CPU-heavy work still needs worker queues and budgets, not just event publication.

### Neutral

- AppServer remains the HTTP owner during this phase.
- Existing endpoint shapes, SQLite replay, and SSE streams stay compatible.
- Future multi-process agents can reuse the same event vocabulary, but that is not claimed yet.

## Alternatives Considered

**Split into microservices**

Rejected for now. TTMEvolve's current bottleneck is local orchestration complexity and evidence quality, not independent service deployment or cloud scale.

**Keep direct method reads and ad hoc session state**

Rejected because it makes layer independence hard to prove and encourages hidden coupling between Agent, Runtime, Learning, and GUI evidence.

**Use SQLite as the only communication spine**

Rejected because durable replay is necessary but too slow and awkward as the live control path. SQLite remains the audit/replay layer.

## References

- `core/runtime_events.py`
- `server/runtime_observer.py`
- `server/project_observer.py`
- `server/learning_observer.py`
- `server/memory_observer.py`
- `server/layer_health.py`
- `server/engineering_control.py`
- `docs/architecture/architecture-control-roadmap-2026-06-27.md`
