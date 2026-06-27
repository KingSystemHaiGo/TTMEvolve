# 架构说明 / Architecture Notes

公开架构文档应保持简洁，并尽量基于证据。

Public architecture records are kept small and evidence-oriented.

## 决策记录 / Decisions

- [ADR-0002: Session-Scoped Agent Runtime / 会话级 Agent 运行时](adr-0002-session-scoped-agent-runtime.md)
- [ADR-0003: Modular Monolith Runtime Event Bus / 模块化单体与 RuntimeEventBus](adr-0003-modular-monolith-runtime-event-bus.md)

## 摘要 / Summary

TTMEvolve 是一个桌面模块化单体：

- Tauri/Rust 负责桌面外壳和原生生命周期。
- React/Vite 负责工作台 UI。
- Python App Server 负责本地 HTTP/SSE APIs。
- TapMakerAgent 负责规划、工具执行、Maker 集成和运行时证据。
- RuntimeEventBus 提供进程内事件观察；SQLite/SSE 继续作为持久回放和 UI transport surface。

TTMEvolve is a desktop modular monolith:

- Tauri/Rust owns the desktop shell and native lifecycle.
- React/Vite owns the workbench UI.
- Python App Server owns local HTTP/SSE APIs.
- TapMakerAgent owns planning, tool execution, Maker integration, and runtime evidence.
- RuntimeEventBus provides in-process event observation while SQLite/SSE remain durable replay and UI transport surfaces.
