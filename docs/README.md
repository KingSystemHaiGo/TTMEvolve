# TTMEvolve 文档 / TTMEvolve Documentation

这里是面向用户、贡献者和维护者的公开文档入口。

This directory contains public documentation for users, contributors, and maintainers.

## 从这里开始 / Start Here

- [项目 README / Project README](../README.md)
- [中文 README / Chinese README](../README.zh-CN.md)
- [贡献者快速开始 / Contributor Quick Start](getting-started.md)
- [开发指南 / Development Guide](DEVELOPMENT.md)
- [App Server API](API.md)
- [路线图 / Roadmap](ROADMAP.md)
- [架构说明 / Architecture Notes](architecture/README.md)
- [发布说明 / Release Notes](releases/README.md)

### v1.1.0 Slice #1 文档地图 / v1.1.0 Documentation Map

- [Feature flags inventory](feature-flags.md) — five new flags
  (default off) introduced in v1.1.0.
- [Release gates](release-gates.md) — the 10 gates that must pass
  before promoting a release.
- [Research basis](research/2026-memory-and-control.md) — 17 cited
  references backing the v1.1.0 design.
- [ADR-0004 Graph RAG](architecture/adr-0004-profile-aware-graph-memory.md)
- [ADR-0007 Progressive Context Loader](architecture/adr-0007-progressive-context-loader.md)
- [ADR-0008 Plan v2 + Cybernetic Control](architecture/adr-0008-plan-v2-cybernetic-control.md)
- [Release candidate template](research/baseline/candidate-v1.0.0.md)

## 文档边界 / Documentation Boundary

公开文档应该帮助用户安装、运行、验证、扩展或安全评估 TTMEvolve。

Public docs should help users install, run, verify, extend, or safely evaluate TTMEvolve.

内部项目记忆、sprint logs、私有 agent handoff notes 和本地运行时状态会被刻意排除在 GitHub 之外。它们可以留在本地 checkout 中，但不应作为公开仓库文档发布。

Internal project memory, sprint logs, private agent handoff notes, and local runtime state are intentionally excluded from GitHub. They can remain in a local checkout, but they should not be published as repository documentation.
