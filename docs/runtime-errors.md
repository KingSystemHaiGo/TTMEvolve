# Runtime Error Log — Status and Design

This document is the source of truth for **how TTMEvolve records,
classifies, and surfaces runtime errors**. It covers the current
state, the gaps, and the proposed design. Status as of 2026-06-28:
**current logging is general-purpose; there is no dedicated error
log yet.**

## Current state (as of 2026-06-28)

### What exists

| Module | Role | What it does for errors |
| --- | --- | --- |
| `core/event_log.py` | Append-only JSONL of agent events (actions, state, health checks) | Records "action_rejected" / "state_changed" with payload, but does not call them out as errors. |
| `core/runtime_events.py` | In-process event bus for RuntimeEventBus (channel, source) | Bus-level observability; no severity / no traceback. |
| `core/repair.py` | Fault-classification + exponential-backoff repair scheduler | Knows the fault type (`maker_mcp_disconnected`, `llm_api_error`, `tool_timeout`, etc.) and `FAULT_MAX_RETRIES`, but does not log structured errors — it only emits events. |
| `core/loop_scheduler.py` | Background periodic runner | The only file using `logging.getLogger`. |
| `logs/gui/*.err.log` | Per-component stderr dumps from `start-gui.ps1` and the launcher's `electron-detached` blocks | Plain text; no schema; no rotation. |
| `start-gui.log` | Shell trace of the launcher | Plain text; informational only. |
| `core/executor.py` (and 12 other files) | Various `except Exception as e:` blocks | The error is **silently swallowed** (`continue` / `return default`). No traceback capture. |

### What is missing

1. **No structured error log.** Errors flow into `EventLog` as
   generic events, not as a dedicated error channel.
2. **No severity.** There is no `warning / error / critical / fatal`
   taxonomy. Operators cannot filter "everything that was fatal."
3. **No error type taxonomy.** `RepairScheduler` has one internally
   but it does not leak into the log.
4. **No traceback capture.** `except Exception as e:` blocks
   everywhere discard the stack.
5. **No recovery hint.** When an error is logged, the operator
   does not know what was tried next (retry? rollback? skip?).
6. **No dedup.** A 1000-call hot path that throws every call
   produces 1000 log lines.
7. **No rotation.** `event_log.jsonl` and the various stderr
   files grow forever. The `.gitignore` does ignore them but no
   policy exists for cleanup.
8. **No dashboard surface.** The evidence bundle has no
   `errors` block; the Workbench cannot show "what failed in
   the last 10 minutes."
9. **No grep-friendly fields.** Errors do not consistently carry
   `session_id / step_id / attempt / tool_name`, so an operator
   asking "what failed in session X?" has to grep raw text.

## Gaps relative to common practice

Compare to the [Microsoft REST API Guidelines §8 (errors)](https://github.com/Microsoft/api-guidelines/blob/vNext/Guidelines.md#8-errors)
and the [Google SRE Book ch. 11 (being on call)](https://sre.google/sre-book/being-on-call/):

| Practice | TTMEvolve today |
| --- | --- |
| One canonical error model | ✗ — events are heterogeneous; no schema |
| Severity levels | ✗ — none |
| Stable error codes | ✗ — none |
| User-facing message + operator-facing details | ✗ — single opaque payload |
| Retry / no-retry signal | partial — `RepairScheduler` knows but does not log |
| Correlation id (session_id / request_id) | partial — events have it; stderr logs do not |
| Structured log shipping (JSONL) | partial — `event_log.jsonl` yes; stderr no |
| Log rotation | ✗ — no policy |
| Operator runbook link | ✗ — none |

## Proposed design (Phase L follow-up, NOT IMPLEMENTED YET)

This section is the design. It is **not** the runtime yet; the user
has not seen the runtime errors in question. Locking the design
before implementing prevents the "edit-to-green" pattern where the
code grows to match whatever error happened to surface.

### 1. New module: `core/runtime_errors.py`

A small, dedicated error log with a strict schema. The schema is
versioned so future changes are migration-safe.

```python
# core/runtime_errors.py
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

class ErrorSeverity(str, Enum):
    WARNING = "warning"   # recoverable, no action needed
    ERROR = "error"       # recoverable, user-visible impact
    CRITICAL = "critical" # recoverable, loop exited
    FATAL = "fatal"       # not recoverable without restart

class ErrorCategory(str, Enum):
    LLM_API = "llm_api"
    LLM_TIMEOUT = "llm_timeout"
    LLM_PARSE = "llm_parse"
    MAKER_MCP = "maker_mcp"
    TOOL_CALL = "tool_call"
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_VALIDATION = "tool_validation"
    SANDBOX = "sandbox"
    APPROVAL = "approval"
    PLAN_EXEC = "plan_exec"
    VSM = "vsm"
    MEMORY = "memory"
    GRAPH = "graph"
    LOADER = "loader"
    BAYES = "bayes"
    UNKNOWN = "unknown"

@dataclass
class RuntimeErrorRecord:
    schema_version: str        # "runtime-error.v1"
    timestamp: str             # ISO 8601 UTC
    session_id: str            # "" if pre-session
    step_id: str               # "" if not in a step
    tool_name: str             # "" if not a tool call
    category: str              # ErrorCategory value
    severity: str              # ErrorSeverity value
    error_type: str            # e.g. "TimeoutError", "PermissionError"
    message: str               # short human description
    traceback: str             # full traceback (truncated to N lines)
    attempt: int               # retry attempt number
    recovery_hint: str         # what was tried / what to do
    extra: Dict[str, Any]      # category-specific context
```

### 2. Storage: `storage/runtime_errors.jsonl`

Append-only, one record per line, atomic write per record. Same
`asdict(json)` pattern as `EventLog`. The path is configurable
via `config["runtime.errors.path"]` with a sensible default.

Rotation policy:

- Rotate when the file exceeds 50 MB.
- Keep the current file plus 5 rotated (`runtime_errors.jsonl.1`
  through `.5`).
- Older files are deleted at startup if the new file is also
  fresh.

### 3. Integration: existing `except Exception` blocks

Add a small `record_error(category, ...)` helper in
`core/runtime_errors.py` that:
- Captures `traceback.format_exc()` automatically.
- Defaults `severity` from `category` via a small lookup table.
- Defaults `recovery_hint` from `category` (e.g. for `llm_timeout`
  the hint is "increase n_ctx or switch provider").
- Is safe to call from any code path (never raises).

Roll-out:
- `core/executor.py` — every `except (TypeError, ValueError)` becomes
  a `record_error(ErrorCategory.TOOL_CALL, ...)` + original behavior.
- `core/plan_executor.py` — `PlanExecutorError` is a category, not
  a free-form string.
- `core/control_loop.py` — emit when `verdict == "diverging"`.
- `core/vsm.py` — emit when S4 escalation fires.

### 4. Evidence bundle surface

Add a new field to `build_session_evidence_bundle`:

```python
errors = {
    "schema_version": "runtime-error.v1",
    "recent_count_5m": 12,
    "recent_count_1h": 47,
    "by_severity": {"warning": 30, "error": 15, "critical": 2, "fatal": 0},
    "by_category": {"llm_timeout": 8, "tool_call": 5, "maker_mcp": 2, "...": "..."},
    "last_error": {...}      # last full record (compact)
}
```

This is the Workbench-side dashboard surface. Operators can
spot trends without reading raw log files.

### 5. Roll-out gate

The new `runtime_errors.py` and the surface changes only land
behind a feature flag `runtime.errors.enabled` (default `false`),
so:

- v1.1.0 ships with the new module but it's dormant.
- The next slice that turns it on does so via the same
  `check_release_ready.py` gate list — adds a new gate that
  records the enabled flag, the rotation policy, and the
  evidence-bundle surface.
- `tests/test_regression_guards.py` gets a new entry: the
  default for `runtime.errors.enabled` is `false`.

## What we do **NOT** do in this design

- We do not add error reporting over the network. Errors stay
  local; "report to a remote" is a future feature.
- We do not add a GUI error popup. The Workbench dashboard reads
  the evidence bundle; it does not push real-time toasts.
- We do not change `EventLog`. It is fine as a generic event log;
  errors are a separate, smaller surface.
- We do not introduce a third-party logger (structlog / loguru).
  Plain `json.dumps(asdict(record))` matches the existing
  `EventLog` pattern and keeps the dep surface flat.

## What the user (operator) gets

After Phase L rolls out:

```bash
# last 50 errors in the last hour, by category
jq -r 'select(.timestamp > (now - 3600 | strftime("%Y-%m-%dT%H:%M:%S"))) | .category' \
  storage/runtime_errors.jsonl | sort | uniq -c | sort -rn | head

# errors in a specific session
jq -r 'select(.session_id == "s-12345")' storage/runtime_errors.jsonl

# Workbench shows:
#   "12 errors in the last 5 min, 2 critical, top: llm_timeout(8)"
```

This is the target. Implementation does **not** start until the
user confirms the design above (or suggests changes) and pastes at
least one real error string from their test session so the schema
is sized correctly.
