"""
core/error_hooks.py - automatic error-logging hooks.

This module gives the runtime **one** place to register error-log
callbacks. Producers (the tool executor, the control loop, the
plan executor, etc.) call ``fire(category, ...)`` at the error
site; subscribers (``record_error`` from ``core.runtime_errors``,
a future webhook notifier, a future Workbench push, etc.) get
called automatically.

Design contract:

  - The hook layer is **passive**. It does not change tool
    behavior. It only observes.
  - Hook functions must never raise. ``fire()`` swallows every
    exception from every subscriber.
  - Subscribers are global. There is no per-tool hook; if you
    need one, filter inside the subscriber by ``tool_name``.
  - The hook layer is OFF by default. ``configure_hooks()`` is a
    no-op until ``runtime.errors.enabled=true`` is set.

The single canonical registration is in ``agent/agent.py`` at
process start: it calls ``configure_hooks(enabled=True)`` which
in turn registers ``record_error`` as the default subscriber.

See ``docs/runtime-errors.md`` for the design.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional

from .runtime_errors import ErrorCategory, record_error


HookFn = Callable[[str, Dict[str, Any]], None]


class _HookState:
    """Module-level state. Reset by ``reset_for_tests()``."""

    enabled: bool = False
    subscribers: List[HookFn] = []
    lock = threading.RLock()


def configure_hooks(*, enabled: bool) -> None:
    """Enable or disable the global hook layer.

    When enabled, ``fire()`` invokes every registered subscriber.
    When disabled, ``fire()`` is a no-op (and the underlying
    ``record_error`` short-circuits too).
    """
    with _HookState.lock:
        _HookState.enabled = bool(enabled)
        if enabled and not _HookState.subscribers:
            # Auto-register the canonical subscriber so the user
            # does not have to remember to call ``register``
            # explicitly. This is the only built-in subscriber;
            # others can be added with ``register``.
            _HookState.subscribers.append(_default_subscriber)


def is_enabled() -> bool:
    return bool(_HookState.enabled)


def register(fn: HookFn) -> None:
    """Register a subscriber. ``fn(category, payload)`` is invoked
    on every fire when the layer is enabled.
    """
    with _HookState.lock:
        if fn not in _HookState.subscribers:
            _HookState.subscribers.append(fn)


def unregister(fn: HookFn) -> None:
    with _HookState.lock:
        if fn in _HookState.subscribers:
            _HookState.subscribers.remove(fn)


def reset_for_tests() -> None:
    with _HookState.lock:
        _HookState.enabled = False
        _HookState.subscribers = []


def fire(
    category: str,
    *,
    message: str = "",
    severity: Optional[str] = None,
    session_id: str = "",
    step_id: str = "",
    tool_name: str = "",
    attempt: int = 0,
    error: Optional[BaseException] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Fire a hook.

    All subscribers are called. Subscriber exceptions are
    swallowed. Safe to call from any code path, including the
    tool executor and the control loop.
    """
    if not _HookState.enabled:
        return
    payload: Dict[str, Any] = {
        "message": str(message or ""),
        "severity": severity,
        "session_id": str(session_id or ""),
        "step_id": str(step_id or ""),
        "tool_name": str(tool_name or ""),
        "attempt": int(attempt or 0),
        "error": error,
        "extra": dict(extra or {}),
    }
    with _HookState.lock:
        # Snapshot to avoid holding the lock while invoking.
        subscribers = list(_HookState.subscribers)
    for fn in subscribers:
        try:
            fn(category, payload)
        except Exception:
            # A bad subscriber must never affect the runtime.
            pass


# ---------------------------------------------------------------------------
# Default subscriber
# ---------------------------------------------------------------------------

def _default_subscriber(category: str, payload: Dict[str, Any]) -> None:
    """The default subscriber: record to the structured log."""
    record_error(
        category,
        message=payload.get("message") or "",
        severity=payload.get("severity"),
        session_id=payload.get("session_id") or "",
        step_id=payload.get("step_id") or "",
        tool_name=payload.get("tool_name") or "",
        attempt=payload.get("attempt") or 0,
        error=payload.get("error"),
        extra=payload.get("extra") or {},
    )


# ---------------------------------------------------------------------------
# Convenience: ready-to-use categories
# ---------------------------------------------------------------------------

CAT = ErrorCategory  # re-export for ergonomics
