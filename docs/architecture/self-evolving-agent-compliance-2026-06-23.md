# Self-Evolving Agent Compliance Review - 2026-06-23

## Scope

Reviewed against `D:/CC/Ima导出/自进化agent之一.md` through `自进化agent之七.md`, plus current TTMEvolve code.

## Verdict

The project now has the right three-layer skeleton and several real mechanisms: ReAct agent execution, runtime health/repair, append-only session events, tool validation, resource registry, evolution protocol, trajectory collection, reflection, skill generation, API-first LLM routing, Maker MCP diagnostics, and latency telemetry.

The main gap was that the three layers were visible mostly as UI labels and coarse `layer` events. This pass promotes them to a typed communication contract with source layer, target layer, transition event, cause, correlation id, and metrics.

## Compliance Matrix

| Design requirement | Current implementation | Gap | Next step |
| --- | --- | --- | --- |
| Agent layer only reasons and proposes actions | `ReActLoop` + `ToolRegistry`; actions pass through `Executor`, sandbox, approval, schema validation | Some built-in plumbing still lets Agent assembly know many runtime objects | Extract a narrower `AgentRuntime` facade so ReAct cannot bypass execution gateway |
| Core runtime detects, diagnoses, recovers | `HealthMonitor`, `RepairScheduler`, `VersionManager`, cancellation, session status, latency events | Repair is still coarse: rollback/factory reset, limited live diagnostic categories | Add failure taxonomy events for stall, repeated actions, tool validation bursts, context saturation |
| Learning layer is independent and governed | `TrajectoryCollector`, `ReflectionEngine`, `KnowledgeBase`, `SkillGenerator`, `SkillValidator` | Learning runs inline after session; not yet a durable async queue with validation/rollback for every knowledge write | Move reflection into a background job queue with knowledge proposal states |
| Three-layer communication is explicit | Added `core/layer_events.py`; `TapMakerAgent` emits ordered Agent -> Runtime -> Learning -> Storage handoff events | Runtime internal events like repair start/finish are still in `EventLog`, not mirrored to Workbench | Bridge selected `EventLog` repair/evolution events into `layer` SSE events |
| Safe self-modification follows proposal -> validation -> deploy -> monitor -> rollback | `EvolutionProtocol` has proposal, validation, deploy, rollback; high-risk resources ask human confirmation | No Workbench surface for proposals; monitoring/rollback is not yet connected to session outcomes | Add evolution proposal drawer and runtime gate event stream |
| Authority / audit trail is immutable and replayable | `SessionStore` persists append-only SSE events; `EventLog` persists runtime events | SessionStore is append-only by convention, not tamper-evident; cross-store correlation is partial | Add event ids/hash chain and shared correlation ids across SessionStore/EventLog |
| Performance: reduce tool and context tax | Tool ranking/capping, constrained action JSON, context budget, latency telemetry, API-first runtime | No p50/p95 dashboard; tool result cache and model router are not fully operational | Aggregate latency metrics per phase and add cache for stable tool observations |
| Compatibility with Codex/Claude Code/skills | Ecosystem adapters and skill export/import exist; generated skills sync to executor | Compatibility is mostly file-level/export-level, not a live shared protocol | Define canonical skill manifest and adapter conformance tests |

## Communication Contract Added

`LayerEvent` payload:

```json
{
  "schema_version": 1,
  "layer": "agent",
  "state": "active",
  "event": "agent.run.started",
  "detail": "理解目标并规划下一步",
  "source_layer": "user",
  "target_layer": "agent",
  "correlation_id": "session-id",
  "cause": "user_task",
  "metrics": {},
  "timestamp": 1782190000.0
}
```

The GUI Workbench now consumes these fields and shows the actual route, event name, and selected metrics for each layer.

## Current Layer Flow

1. `user -> agent`: `agent.run.started`
2. `agent -> runtime`: `agent.run.finished`
3. `agent -> runtime`: `runtime.audit.started`
4. `runtime -> learning`: `runtime.audit.finished`
5. `runtime -> learning`: `learning.reflection.started`
6. `learning -> storage`: `learning.reflection.finished`

## Priority Roadmap

1. Make runtime diagnostics first-class: repeated action, stalled progress, context saturation, validation burst, MCP disconnect.
2. Convert learning to async proposal queue: trajectory summary -> insight proposal -> validation -> storage commit.
3. Add evolution proposal UI: show proposed resource, diff, validator result, risk, approve/reject.
4. Add tamper-evident audit: event ids, parent hash, correlation between session SSE and runtime EventLog.
5. Add performance dashboard: p50/p95 first response, LLM, tool, MCP, browser, learning.
6. Add canonical skill compatibility tests for Codex, Claude Code, OpenClaw, Hermes-style skills.
