# Architecture Notes

Public architecture records are kept small and evidence-oriented.

## Decisions

- [ADR-0002: Session-Scoped Agent Runtime](adr-0002-session-scoped-agent-runtime.md)
- [ADR-0003: Modular Monolith Runtime Event Bus](adr-0003-modular-monolith-runtime-event-bus.md)

## Summary

TTMEvolve is a desktop modular monolith:

- Tauri/Rust owns the desktop shell and native lifecycle.
- React/Vite owns the workbench UI.
- Python App Server owns local HTTP/SSE APIs.
- TapMakerAgent owns planning, tool execution, Maker integration, and runtime evidence.
- RuntimeEventBus provides in-process event observation while SQLite/SSE remain durable replay and UI transport surfaces.
