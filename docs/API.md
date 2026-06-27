# App Server API

Default local server:

```text
http://127.0.0.1:7345
```

## Core Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Health and runtime status |
| `POST` | `/sessions` | Create an Agent session |
| `GET` | `/sessions/{id}/events` | SSE event stream |
| `POST` | `/sessions/{id}/cancel` | Cancel a session |
| `POST` | `/config/llm` | Update LLM configuration |
| `POST` | `/llm/probe` | Probe configured LLM provider |

## Runtime Evidence

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/runtime/readiness` | No-network runtime readiness gate |
| `GET` | `/runtime/portable` | Portable environment diagnostics |
| `GET` | `/sessions/{id}/evidence?steps=20` | Compact runtime evidence bundle |
| `GET` | `/agent/onboarding?session_id=...&steps=20` | External Agent onboarding bundle |

## Maker Integration

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/maker/setup-status` | Maker setup status |
| `GET` | `/maker/tool-audit` | Maker remote/local tool audit |
| `POST` | `/maker/repair` | Repair Maker access where supported |

## Provider Proof

Use `/llm/probe` to verify that a configured provider is actually called. MiniMax should observe `/text/chatcompletion_v2`; OpenAI-compatible providers should observe `/chat/completions`; Claude-style providers should observe `/messages`.
