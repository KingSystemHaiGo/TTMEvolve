# ADR-0003: 模块化单体与 RuntimeEventBus / Modular Monolith With RuntimeEventBus Spine

## 状态 / Status

已接受 / Accepted

## 背景 / Context

TTMEvolve 是一个桌面应用，包含 Tauri/React shell、Python AppServer、本地存储、Maker MCP 集成、RAG/memory services 和 session-scoped agent runtimes。当前的扩展问题不是多服务器部署，而是内部复杂度：大型 orchestration 文件、HTTP transport 与 runtime evidence ownership 混杂、直接读取状态、上下文加载过重，以及 layer boundaries 难以审计。

TTMEvolve is a desktop application with a Tauri/React shell, a Python AppServer, local storage, Maker MCP integration, RAG/memory services, and session-scoped agent runtimes. The current scaling problem is not multi-server deployment. The pressure is internal: large orchestration files, mixed ownership between HTTP transport and runtime evidence, direct state reads, heavy context loading, and hard-to-audit layer boundaries.

产品需要独立的 Agent、Core Runtime、Learning 三层，同时保持一键本地启动和稳定 GUI 行为。它也需要 durable evidence 来支持 truthfulness gates、COS project control、multi-agent memory policy 和 long-task continuity。

The product needs independent Agent, Core Runtime, and Learning layers while preserving one-click local startup and stable GUI behavior. It also needs durable evidence for truthfulness gates, COS project control, multi-agent memory policy, and long-task continuity.

## 决策 / Decision

保持 TTMEvolve 为模块化单体，并使用 `RuntimeEventBus` 作为进程内通信主干。

Keep TTMEvolve as a modular monolith and use `RuntimeEventBus` as the in-process communication spine.

模块职责：

- Agent layer：规划、工具选择、用户可见回答、消费 compact advice。
- Core Runtime layer：validation、execution、sandbox、Maker/browser/shell authority、runtime events、side-effect evidence。
- Learning layer：异步 reflection、knowledge extraction、shared-memory promotion proposals、validation results。
- Server layer：HTTP/SSE transport、session lifecycle、persistence、evidence surfaces、GUI-facing APIs。
- Memory layer：hot/warm/cold recall、vector index、quality evaluation、privacy policy、shared outcome ledger。

Modules should own clear responsibilities:

- Agent layer: planning, tool choice, user-facing answers, and compact advice consumption.
- Core Runtime layer: validation, execution, sandbox, Maker/browser/shell authority, runtime events, and side-effect evidence.
- Learning layer: async reflection, knowledge extraction, shared-memory promotion proposals, and validation results.
- Server layer: HTTP/SSE transport, session lifecycle, persistence, evidence surfaces, and GUI-facing APIs.
- Memory layer: hot/warm/cold recall, vector index, quality evaluation, privacy policy, and shared outcome ledger.

Live cross-layer facts 默认通过 `RuntimeEventBus` observers 流动。SQLite 保留为 durable replay。SSE 保留为 UI transport 和兼容层，而不是架构 source of truth。

Live cross-layer facts should move through `RuntimeEventBus` observers by default. SQLite remains durable replay. SSE remains a UI transport and compatibility surface, not the architectural source of truth.

## 影响 / Consequences

### 正向 / Positive

- 保持本地桌面部署简单，同时强化模块边界。
- 避免过早引入 microservice 运维成本。
- Runtime Readiness、Evidence Bundle、Layer Health、Engineering Control 和 Onboarding 共享同一事件来源。
- runtime metrics、project state、learning state、memory recall 等消费者可以在不读取私有 ReAct state 的情况下测试。
- 支持 truthfulness gates，因为 claims 可以引用 event、benchmark、endpoint 或 persisted evidence。

- Keeps local desktop deployment simple while allowing strong module boundaries.
- Avoids premature microservice operational cost.
- Gives Runtime Readiness, Evidence Bundle, Layer Health, Engineering Control, and Onboarding a common event source.
- Allows consumers such as runtime metrics, project state, learning state, and memory recall to be tested without reading private ReAct state.
- Supports truthfulness gates because claims can cite event, benchmark, endpoint, or persisted evidence.

### 负向 / Negative

- In-process bus 的 failure handling 和 observer health 需要谨慎维护。
- 模块边界仍依赖 discipline 和 tests；Python 无法强制全部 ownership rules。
- Long-running 或 CPU-heavy work 仍需要 worker queues 和 budgets，而不只是发布事件。

- In-process bus failure handling and observer health must be maintained carefully.
- Module boundaries still depend on discipline and tests; Python cannot enforce all architectural ownership rules.
- Long-running or CPU-heavy work still needs worker queues and budgets, not just event publication.

### 中性 / Neutral

- 当前阶段 AppServer 仍是 HTTP owner。
- Existing endpoint shapes、SQLite replay 和 SSE streams 保持兼容。
- 未来 multi-process agents 可以复用同一事件 vocabulary，但当前不声明该能力。

- AppServer remains the HTTP owner during this phase.
- Existing endpoint shapes, SQLite replay, and SSE streams stay compatible.
- Future multi-process agents can reuse the same event vocabulary, but that is not claimed yet.

## 备选方案 / Alternatives Considered

### 拆成 microservices / Split into microservices

暂时拒绝。TTMEvolve 当前瓶颈是本地 orchestration complexity 和 evidence quality，而不是独立服务部署或云端 scale。

Rejected for now. TTMEvolve's current bottleneck is local orchestration complexity and evidence quality, not independent service deployment or cloud scale.

### 保持直接 method reads 和临时 session state / Keep direct method reads and ad hoc session state

拒绝。它会让 layer independence 难以证明，并鼓励 Agent、Runtime、Learning 和 GUI evidence 之间的 hidden coupling。

Rejected because it makes layer independence hard to prove and encourages hidden coupling between Agent, Runtime, Learning, and GUI evidence.

### 只使用 SQLite 作为通信主干 / Use SQLite as the only communication spine

拒绝。Durable replay 必要，但作为 live control path 太慢且笨重。SQLite 保留为 audit/replay layer。

Rejected because durable replay is necessary but too slow and awkward as the live control path. SQLite remains the audit/replay layer.

## 参考 / References

- `core/runtime_events.py`
- `server/runtime_observer.py`
- `server/project_observer.py`
- `server/learning_observer.py`
- `server/memory_observer.py`
- `server/layer_health.py`
- `server/engineering_control.py`
