# 发布说明 / Release Notes

GitHub Releases 是公开发布入口。本目录保存辅助 release notes 和 source checkpoint 证据。

GitHub Releases are the public release surface. This directory keeps supporting release notes and source checkpoint evidence.

## 当前公开 checkpoint / Current Public Checkpoint

- [v0.4.5 Source Release Checkpoint / v0.4.5 源码 checkpoint](v0.4.5-source-release-checkpoint.md)

## 发布真实性边界 / Release Truthfulness

当前 source checkpoint 是 ready。完整 offline release readiness 在以下 gate 被证明之前不声明：

- 签名安装包
- Maker 远程构建 side-effect smoke
- 生产 RAG 语义质量证明

The current source checkpoint is ready. Full offline release readiness is not claimed until these gates are proven:

- signed installer artifacts
- Maker remote build side-effect smoke
- production RAG semantic-quality proof
