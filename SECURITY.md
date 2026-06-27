# Security Policy

## Supported Versions

TTMEvolve is currently pre-1.0 and source-checkpoint based. Security fixes are applied to the default branch first.

## Reporting a Vulnerability

Please do not open a public issue for secrets, auth leaks, command execution bugs, sandbox bypasses, or private project data exposure.

Open a private GitHub security advisory if available, or contact the maintainers through the repository owner profile.

Include:

- affected commit or version
- operating system
- reproduction steps
- expected impact
- whether credentials, Maker auth state, local files, or network calls are involved

## Security Boundaries

Do not commit:

- API keys or provider credentials
- TapTap Maker auth state
- `.env*`, `.mcp.json`, or `config.json`
- `portable/`, `storage/`, `workspace/`, `models/`, `vendor/`, or logs

TTMEvolve uses local tooling, shell execution, browser automation, and Maker MCP integration. Treat untrusted project files and external webpages as potentially hostile.
