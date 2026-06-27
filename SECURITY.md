# 安全策略 / Security Policy

## 支持版本 / Supported Versions

TTMEvolve 当前仍是 pre-1.0，并以 source checkpoint 方式发布。安全修复会优先进入默认分支。

TTMEvolve is currently pre-1.0 and source-checkpoint based. Security fixes are applied to the default branch first.

## 报告漏洞 / Reporting a Vulnerability

请不要在公开 issue 中披露 secrets、auth 泄漏、命令执行漏洞、sandbox bypass 或私有项目数据暴露。

Please do not open a public issue for secrets, auth leaks, command execution bugs, sandbox bypasses, or private project data exposure.

如果 GitHub Security Advisory 可用，请创建 private advisory；否则通过仓库 owner profile 联系维护者。

Open a private GitHub security advisory if available, or contact the maintainers through the repository owner profile.

请尽量包含：

- 受影响 commit 或版本
- 操作系统
- 复现步骤
- 预期影响
- 是否涉及凭据、Maker auth state、本地文件或网络调用

Include:

- affected commit or version
- operating system
- reproduction steps
- expected impact
- whether credentials, Maker auth state, local files, or network calls are involved

## 安全边界 / Security Boundaries

不要提交：

- API keys 或 provider credentials
- TapTap Maker auth state
- `.env*`、`.mcp.json` 或 `config.json`
- `portable/`、`storage/`、`workspace/`、`models/`、`vendor/` 或 logs

Do not commit:

- API keys or provider credentials
- TapTap Maker auth state
- `.env*`, `.mcp.json`, or `config.json`
- `portable/`, `storage/`, `workspace/`, `models/`, `vendor/`, or logs

TTMEvolve 会使用本地工具、shell 执行、浏览器自动化和 Maker MCP 集成。请把不可信项目文件和外部网页都视为潜在风险输入。

TTMEvolve uses local tooling, shell execution, browser automation, and Maker MCP integration. Treat untrusted project files and external webpages as potentially hostile.
