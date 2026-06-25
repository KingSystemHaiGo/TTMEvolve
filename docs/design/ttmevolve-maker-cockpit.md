# TTMEvolve Maker Cockpit Design Baseline

## Product Direction

TTMEvolve is a local desktop IDE and self-evolving runtime for TapTap Maker projects.
The CLI remains the power interface for automation, debugging, and batch work.
The GUI is the cockpit: it makes the same runtime visible, recoverable, and easy to operate.

## Architecture Principle

- One engine: CLI and GUI both use App Server sessions, SSE events, ToolRegistry, Executor, EventLog, and SessionStore.
- Maker MCP first: TapTap Maker MCP tools are treated as core capabilities, not optional plugins.
- Runtime as guardrail: Agent proposes actions; Runtime validates, approves, executes, records, and recovers.
- Learning is offline by default: trajectories, rescue logs, and user feedback become skills, memory, and fault patterns after validation.

## Architecture Judgment

The current direction is right: TTMEvolve should not become "one CLI agent plus one separate GUI".
It should be one local runtime with several operating surfaces.
The durable boundary is the App Server session/event layer; CLI, Electron, and future Maker panels should all drive the same executor, approval bridge, MCP client, browser service, and persisted event stream.

The main risk is letting the learning layer write back into tools too early.
Keep self-evolution asynchronous and replayable: record trajectories first, validate improvements second, then promote only audited skills or configuration changes.
That keeps the system powerful without making it unstable.

## UI Information Architecture

1. Cockpit header
   - Brand identity
   - Maker MCP version and status
   - Runtime state
   - active provider/profile/project

2. Task cockpit
   - user task input
   - model/provider switch
   - approval modal
   - ReAct event timeline

3. Workspace
   - project files
   - asset library
   - Monaco editor
   - diff/save states

4. Preview and publish
   - file preview
   - embedded browser preview
   - screenshot capture
   - future TapTap publish flow and material generation

5. Evolution visibility
   - tool calls
   - rescue events
   - generated skills
   - memory/fault-pattern updates

## Visual Theme

The interface follows a TapTap Maker-like light cockpit style:

- mostly white and pale gray surfaces
- teal/mint primary actions
- dark slate preview surface for game/browser rendering
- small rounded controls, restrained shadows, high scan density
- semantic accents for success, warning, danger, and blue runtime status

Core tokens live in `frontend/src/styles/index.css`.

## Next Integration Milestones

1. Add `/mcp/status` and `/mcp/tools` endpoints with Maker tool health, schemas, and last call results.
2. Add a Maker tool center in the GUI.
3. Bind project root, MCP cwd, file explorer, preview, and publish flow to the same project identity.
4. Add session replay and evolution dashboard views backed by SessionStore and EventLog.
5. Add preview/publish automation: refresh preview, capture screenshots, generate TapTap material drafts, then publish with approval.
