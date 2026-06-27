"""Action validation and execution service for ReAct.

The ReAct loop decides what to do next. This module owns the local action
boundary: validate tool calls, execute through Executor, emit progress
heartbeats, and reconcile uncertain side effects.
"""

from __future__ import annotations

import concurrent.futures
import json
import time
from typing import Any, Callable, Dict, Optional


EmitFn = Callable[[str, str, Dict[str, Any]], None]
CancelFn = Callable[[], None]


class ActionExecutionService:
    """Runtime-side action execution helper used by ReActLoop."""

    def __init__(
        self,
        *,
        tools: Any,
        executor: Any,
        emit: Optional[EmitFn] = None,
        check_cancelled: Optional[CancelFn] = None,
        progress_interval_seconds: float = 5.0,
    ) -> None:
        self.tools = tools
        self.executor = executor
        self.emit = emit
        self.check_cancelled = check_cancelled
        self.progress_interval_seconds = max(0.1, float(progress_interval_seconds or 5.0))

    def execute_with_progress(
        self,
        session_id: str,
        tool_name: Optional[str],
        params: Dict[str, Any],
        *,
        iteration: int,
        started_at: float,
    ) -> Dict[str, Any]:
        heartbeat_count = 0
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = pool.submit(self.execute, session_id, tool_name, params)
        try:
            while True:
                try:
                    return future.result(timeout=self.progress_interval_seconds)
                except concurrent.futures.TimeoutError:
                    self._check_cancelled()
                    heartbeat_count += 1
                    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
                    self._emit(session_id, "tool_progress", {
                        "iteration": iteration,
                        "tool": tool_name,
                        "status": "running",
                        "elapsed_ms": elapsed_ms,
                        "heartbeat_count": heartbeat_count,
                        "partial": True,
                    })
        except Exception:
            future.cancel()
            raise
        finally:
            pool.shutdown(wait=future.done(), cancel_futures=True)

    def execute(
        self,
        session_id: str,
        tool_name: Optional[str],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not tool_name:
            return {"ok": False, "error": "No tool selected."}
        if not self.tools.has(tool_name):
            return {"ok": False, "error": f"Tool {tool_name} does not exist."}

        self._check_cancelled()
        validation = self.tools.validate_action(tool_name, params)
        if not validation["ok"]:
            return validation_observation(tool_name, validation)

        self._check_cancelled()
        return self.executor.propose_action(session_id, tool_name, params)

    def reconcile_if_uncertain_commit(
        self,
        session_id: str,
        iteration: int,
        tool_name: Optional[str],
        observation: Dict[str, Any],
    ) -> Dict[str, Any]:
        if observation.get("committed") is not None or not observation.get("idempotency_key"):
            return observation
        self._emit(session_id, "commit_reconcile", {
            "iteration": iteration,
            "tool": tool_name,
            "idempotency_key": observation.get("idempotency_key"),
            "status": "checking",
        })
        reconciler = getattr(self.executor, "reconcile_commit_state", None)
        if not callable(reconciler):
            return observation
        reconciled = reconciler(observation)
        self._emit(session_id, "commit_reconcile", {
            "iteration": iteration,
            "tool": tool_name,
            "idempotency_key": reconciled.get("idempotency_key"),
            "status": reconciled.get("reconcile_status", "unknown"),
            "committed": reconciled.get("committed"),
            "observation": reconciled,
        })
        return reconciled

    def _emit(self, session_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        if callable(self.emit):
            self.emit(session_id, event_type, payload)

    def _check_cancelled(self) -> None:
        if callable(self.check_cancelled):
            self.check_cancelled()


def validation_observation(tool_name: Optional[str], validation: Dict[str, Any]) -> Dict[str, Any]:
    errors = validation.get("errors", [])
    structured_errors = validation.get("structured_errors", [])
    first = structured_errors[0] if structured_errors else {}
    return {
        "ok": False,
        "valid": False,
        "failure_type": "tool_validation",
        "tool": tool_name,
        "error": "; ".join(errors),
        "validation_errors": errors,
        "structured_errors": structured_errors,
        "rule_id": first.get("rule_id"),
        "path": first.get("path"),
        "reason": first.get("reason"),
        "suggested_fix": first.get("suggested_fix"),
        "alternatives": validation.get("alternatives", []),
        "suggested_next_step": validation.get("suggested_next_step"),
    }


def validation_context_hint(tool_name: Optional[str], validation: Dict[str, Any]) -> str:
    errors = validation.get("errors", [])
    structured_errors = validation.get("structured_errors", [])
    payload = {
        "valid": False,
        "failure_type": "tool_validation",
        "tool": tool_name,
        "errors": structured_errors or errors,
        "alternatives": validation.get("alternatives", []),
        "suggested_next_step": validation.get("suggested_next_step"),
    }
    return (
        "\n[tool_validation_failed]\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n"
        "Fix the tool name or params exactly as suggested, or choose one of the alternatives before retrying.\n"
    )


def tool_timeout_context_hint(tool_name: Optional[str], observation: Dict[str, Any]) -> str:
    payload = {
        "failure_type": "tool_timeout",
        "tool": tool_name,
        "elapsed_ms": observation.get("elapsed_ms"),
        "timeout_seconds": observation.get("timeout_seconds"),
        "partial": observation.get("partial", False),
        "stdout_tail": tail_text(observation.get("stdout")),
        "stderr_tail": tail_text(observation.get("stderr")),
        "suggested_fix": (
            "Do not repeat the same long call blindly. Use a smaller timeout, "
            "narrow the command/tool params, inspect partial output, or choose "
            "a cheaper diagnostic tool before continuing."
        ),
    }
    return (
        "\n[tool_timeout]\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n"
        "Continue reasoning in the next step with the partial result instead of blocking.\n"
    )


def tail_text(value: Any, limit: int = 1200) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) <= limit:
        return text
    return text[-limit:]
