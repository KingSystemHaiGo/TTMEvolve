"""
core/runtime_errors.py - structured runtime error log.

The runtime errors module is the single entry point for "something
went wrong during a tool call / a step / an LLM call" reporting.
It is intentionally small: schema, JSONL writer, and a
``record_error()`` helper that captures the traceback automatically.

Design doc: ``docs/runtime-errors.md``. This file is the
implementation of the storage and helper layer; the hook layer
lives in ``core/error_hooks.py``.

The module is OFF by default. When ``runtime.errors.enabled=false``
the public functions short-circuit and no file is written, so
the slice #1 release gate (``check_release_ready.py``) does not
regress.

Storage
-------
``storage/runtime_errors.jsonl``. Rotation: when the file exceeds
50 MB, the file is moved to ``.1`` and a new file starts. Up to
5 rotations are kept. The cleanest place to run rotation is the
``ErrorLog`` constructor (called once at process start) and on
every write when the file crosses the size threshold.
"""

from __future__ import annotations

import json
import os
import time
import traceback as _traceback
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Optional


RUNTIME_ERROR_SCHEMA_VERSION = "runtime-error.v1"
DEFAULT_MAX_BYTES = 50 * 1024 * 1024  # 50 MB
DEFAULT_MAX_ROTATIONS = 5
DEFAULT_TRACEBACK_LINES = 30


class ErrorSeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    FATAL = "fatal"


class ErrorCategory(str, Enum):
    LLM_API = "llm_api"
    LLM_TIMEOUT = "llm_timeout"
    LLM_PARSE = "llm_parse"
    MAKER_MCP = "maker_mcp"
    TOOL_CALL = "tool_call"
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_VALIDATION = "tool_validation"
    TOOL_BLOCKED = "tool_blocked"
    SANDBOX = "sandbox"
    APPROVAL = "approval"
    PLAN_EXEC = "plan_exec"
    VSM = "vsm"
    MEMORY = "memory"
    GRAPH = "graph"
    LOADER = "loader"
    BAYES = "bayes"
    UNKNOWN = "unknown"


# Category -> default severity. Override by passing ``severity=``
# explicitly to ``record_error``.
_DEFAULT_SEVERITY: Dict[str, str] = {
    ErrorCategory.LLM_TIMEOUT.value: ErrorSeverity.WARNING.value,
    ErrorCategory.LLM_PARSE.value: ErrorSeverity.WARNING.value,
    ErrorCategory.MAKER_MCP.value: ErrorSeverity.ERROR.value,
    ErrorCategory.TOOL_CALL.value: ErrorSeverity.ERROR.value,
    ErrorCategory.TOOL_TIMEOUT.value: ErrorSeverity.WARNING.value,
    ErrorCategory.TOOL_VALIDATION.value: ErrorSeverity.WARNING.value,
    ErrorCategory.TOOL_BLOCKED.value: ErrorSeverity.WARNING.value,
    ErrorCategory.SANDBOX.value: ErrorSeverity.WARNING.value,
    ErrorCategory.APPROVAL.value: ErrorSeverity.WARNING.value,
    ErrorCategory.PLAN_EXEC.value: ErrorSeverity.ERROR.value,
    ErrorCategory.VSM.value: ErrorSeverity.CRITICAL.value,
    ErrorCategory.MEMORY.value: ErrorSeverity.WARNING.value,
    ErrorCategory.GRAPH.value: ErrorSeverity.WARNING.value,
    ErrorCategory.LOADER.value: ErrorSeverity.WARNING.value,
    ErrorCategory.BAYES.value: ErrorSeverity.WARNING.value,
    ErrorCategory.LLM_API.value: ErrorSeverity.ERROR.value,
    ErrorCategory.UNKNOWN.value: ErrorSeverity.ERROR.value,
}


# Category -> default recovery hint. Surfaced to operators so they
# know what was tried and what to try next.
_DEFAULT_RECOVERY_HINT: Dict[str, str] = {
    ErrorCategory.LLM_API.value: "retry; if persistent, switch provider or check API key",
    ErrorCategory.LLM_TIMEOUT.value: "increase n_ctx, reduce history steps, or switch provider",
    ErrorCategory.LLM_PARSE.value: "the model emitted unparseable JSON; prompt may need a few-shot example",
    ErrorCategory.MAKER_MCP.value: "run maker_setup_status; reconnect via maker_repair",
    ErrorCategory.TOOL_CALL.value: "inspect tool params; the tool returned ok=False",
    ErrorCategory.TOOL_TIMEOUT.value: "increase tool_timeout_seconds or split the operation",
    ErrorCategory.TOOL_VALIDATION.value: "fix the tool params to match the schema; see structured_errors",
    ErrorCategory.TOOL_BLOCKED.value: "the call was blocked by guard/sandbox/approval; review the policy",
    ErrorCategory.SANDBOX.value: "the sandbox rejected the action; widen the policy or change the working dir",
    ErrorCategory.APPROVAL.value: "the human approval policy denied the action; review or change the policy",
    ErrorCategory.PLAN_EXEC.value: "the plan executor refused the step; see PlanExecutorError",
    ErrorCategory.VSM.value: "the control loop diverged; review the S4 escalation log",
    ErrorCategory.MEMORY.value: "memory layer error; check cold_memory writes",
    ErrorCategory.GRAPH.value: "graph memory error; verify memory.graph.enabled is appropriate",
    ErrorCategory.LOADER.value: "prompt loader error; verify loader.enabled is appropriate",
    ErrorCategory.BAYES.value: "bayesian scoring error; check memory.bayes.enabled",
    ErrorCategory.UNKNOWN.value: "no specific recovery hint; inspect the traceback",
}


@dataclass
class RuntimeErrorRecord:
    """One structured error record. Appended to the JSONL log."""

    schema_version: str = RUNTIME_ERROR_SCHEMA_VERSION
    timestamp: str = ""
    session_id: str = ""
    step_id: str = ""
    tool_name: str = ""
    category: str = ErrorCategory.UNKNOWN.value
    severity: str = ErrorSeverity.ERROR.value
    error_type: str = ""
    message: str = ""
    traceback: str = ""
    attempt: int = 0
    recovery_hint: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class _GlobalState:
    """Module-level state. Reset by ``ErrorLog.reset_for_tests()``."""

    enabled: bool = False
    log: Optional["ErrorLog"] = None
    lock = RLock()


def configure(*, enabled: bool, log_path: Optional[Path] = None) -> Optional["ErrorLog"]:
    """Configure the global error log.

    Called once at process start from ``agent/agent.py`` (or from
    the integration test). When ``enabled=False`` the existing
    log is closed and the global state is reset. When ``enabled=True``
    a new ``ErrorLog`` is created at ``log_path`` (or the default
    ``storage/runtime_errors.jsonl``).
    """
    with _GlobalState.lock:
        if not enabled:
            if _GlobalState.log is not None:
                try:
                    _GlobalState.log.close()
                except Exception:
                    pass
            _GlobalState.log = None
            _GlobalState.enabled = False
            return None
        path = log_path or _default_log_path()
        log = ErrorLog(path=path)
        _GlobalState.log = log
        _GlobalState.enabled = True
        return log


def is_enabled() -> bool:
    return bool(_GlobalState.enabled and _GlobalState.log is not None)


def record_error(
    category: str,
    *,
    message: str = "",
    severity: Optional[str] = None,
    session_id: str = "",
    step_id: str = "",
    tool_name: str = "",
    attempt: int = 0,
    extra: Optional[Dict[str, Any]] = None,
    error: Optional[BaseException] = None,
) -> bool:
    """Record one error. Returns True on success, False when disabled.

    If ``error`` is provided its type and traceback are captured
    automatically. ``severity`` and the recovery hint default from
    the category table.
    """
    if not is_enabled():
        return False
    cat = str(category or ErrorCategory.UNKNOWN.value)
    if cat not in _DEFAULT_SEVERITY:
        cat = ErrorCategory.UNKNOWN.value
    sev = str(severity or _DEFAULT_SEVERITY[cat])
    err_type = ""
    tb_text = ""
    if error is not None:
        err_type = type(error).__name__
        try:
            tb_lines = _traceback.format_exception(
                type(error), error, error.__traceback__
            )
        except Exception:
            tb_lines = []
        tb_text = "".join(tb_lines).strip()
        if len(tb_text.splitlines()) > DEFAULT_TRACEBACK_LINES:
            tb_text = "\n".join(
                tb_text.splitlines()[-DEFAULT_TRACEBACK_LINES:]
            )
        if not message:
            message = str(error)
    record = RuntimeErrorRecord(
        timestamp=_utcnow_iso(),
        session_id=str(session_id or ""),
        step_id=str(step_id or ""),
        tool_name=str(tool_name or ""),
        category=cat,
        severity=sev,
        error_type=err_type,
        message=str(message or ""),
        traceback=tb_text,
        attempt=int(attempt or 0),
        recovery_hint=_DEFAULT_RECOVERY_HINT.get(cat, ""),
        extra=dict(extra or {}),
    )
    log = _GlobalState.log
    if log is None:
        return False
    try:
        log.append(record)
        return True
    except Exception:
        # The error log itself must never break the runtime.
        return False


def recent(*, since_seconds: int = 3600) -> list:
    """Return the most recent records (up to 10 000), newest first.

    Convenience for the evidence bundle. The filter on
    ``since_seconds`` is applied in Python; for a real log shipper
    this would push the filter to the read side of the JSONL.
    """
    log = _GlobalState.log
    if log is None:
        return []
    cutoff = time.time() - float(since_seconds)
    out = []
    for rec in log.read_recent(limit=10_000):
        try:
            ts = _iso_to_epoch(rec.timestamp)
        except Exception:
            ts = 0.0
        if ts and ts < cutoff:
            continue
        out.append(rec)
    return out


# ---------------------------------------------------------------------------
# ErrorLog
# ---------------------------------------------------------------------------

class ErrorLog:
    """Append-only JSONL writer with size-based rotation."""

    def __init__(
        self,
        path: Path,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_rotations: int = DEFAULT_MAX_ROTATIONS,
    ):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_bytes = int(max_bytes)
        self.max_rotations = int(max_rotations)
        self._lock = RLock()
        self._fh = self.path.open("a", encoding="utf-8")

    def append(self, record: RuntimeErrorRecord) -> None:
        line = json.dumps(record.to_dict(), ensure_ascii=False) + "\n"
        with self._lock:
            self._maybe_rotate(len(line.encode("utf-8")))
            self._fh.write(line)
            self._fh.flush()

    def close(self) -> None:
        with self._lock:
            try:
                self._fh.flush()
                self._fh.close()
            except Exception:
                pass

    def read_recent(self, *, limit: int = 1000) -> list:
        if not self.path.exists():
            return []
        out = []
        try:
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(RuntimeErrorRecord(**json.loads(line)))
                    except Exception:
                        continue
        except Exception:
            return out
        return out[-limit:]

    def _maybe_rotate(self, incoming_bytes: int) -> None:
        try:
            current_size = self.path.stat().st_size
        except OSError:
            current_size = 0
        if current_size + incoming_bytes <= self.max_bytes:
            return
        try:
            self._fh.flush()
            self._fh.close()
        except Exception:
            pass
        # Rotate: .N-1 -> .N, ..., .1 stays
        for i in range(self.max_rotations - 1, 0, -1):
            src = self._rotated_path(i)
            dst = self._rotated_path(i + 1)
            if src.exists():
                try:
                    os.replace(src, dst)
                except OSError:
                    pass
        # Move current -> .1
        try:
            os.replace(self.path, self._rotated_path(1))
        except OSError:
            pass
        # Drop the oldest beyond max_rotations
        oldest = self._rotated_path(self.max_rotations + 1)
        if oldest.exists():
            try:
                oldest.unlink()
            except OSError:
                pass
        # Reopen
        self._fh = self.path.open("a", encoding="utf-8")

    def _rotated_path(self, index: int) -> Path:
        return self.path.with_suffix(self.path.suffix + f".{index}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_log_path() -> Path:
    return Path("storage") / "runtime_errors.jsonl"


def _utcnow_iso() -> str:
    # Use UTC ISO 8601 with 'Z' suffix.
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _iso_to_epoch(iso: str) -> float:
    try:
        import datetime as _dt
        # Allow both 'Z' and '+00:00' suffixes
        if iso.endswith("Z"):
            iso = iso[:-1] + "+00:00"
        return _dt.datetime.fromisoformat(iso).timestamp()
    except Exception:
        return 0.0
