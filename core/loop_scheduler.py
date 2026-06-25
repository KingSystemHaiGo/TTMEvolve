"""Loop scheduler — periodic re-execution mode for long-running watches.

`/loop` is a lightweight, deterministic scheduler that periodically re-runs a
caller-supplied callable (typically a small Agent task such as "check the
Maker remote build status"). The scheduler tracks:

- interval: seconds between runs
- max_iterations: hard cap so a runaway loop can't burn tokens
- jitter: randomised offset to avoid thundering herd
- stop predicate: an optional callable that decides when to stop early

The scheduler does NOT touch the ReAct loop directly. It is a standalone
utility the host CLI / server can drive from a background thread.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any, Callable, Dict, Optional


LOOP_SCHEDULER_VERSION = "loop-scheduler.v1"


log = logging.getLogger("ttmevolve.loop")


class LoopScheduler:
    """Run `task_fn` every `interval_seconds` until `max_iterations` or stop."""

    def __init__(
        self,
        task_fn: Callable[[int], Dict[str, Any]],
        *,
        interval_seconds: float = 60.0,
        max_iterations: int = 10,
        jitter_seconds: float = 1.0,
        stop_predicate: Optional[Callable[[Dict[str, Any]], bool]] = None,
        on_iteration: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")
        if max_iterations <= 0:
            raise ValueError("max_iterations must be > 0")
        self._task_fn = task_fn
        self.interval_seconds = float(interval_seconds)
        self.max_iterations = int(max_iterations)
        self.jitter_seconds = max(0.0, float(jitter_seconds))
        self._stop_predicate = stop_predicate
        self._on_iteration = on_iteration
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_result: Optional[Dict[str, Any]] = None
        self._iterations = 0

    def start(self, *, daemon: bool = True) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=daemon)
        self._thread.start()

    def stop(self, *, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def run_blocking(self) -> Dict[str, Any]:
        """Synchronous variant for tests / CLI one-shots.

        Iterates up to max_iterations, honoring stop_predicate and stop_event
        like the threaded variant. Returns the last iteration's payload.
        """
        last: Dict[str, Any] = {}
        for i in range(self.max_iterations):
            if self._stop_event.is_set():
                break
            last = self._run_once(iteration=i, loop=False)
            if self._stop_event.is_set():
                break
            if i < self.max_iterations - 1:
                sleep_for = self.interval_seconds
                if self.jitter_seconds > 0:
                    sleep_for += random.uniform(0, self.jitter_seconds)
                # Blocking variant: respect stop_event without async waits.
                deadline = time.perf_counter() + sleep_for
                while not self._stop_event.is_set() and time.perf_counter() < deadline:
                    time.sleep(min(0.05, deadline - time.perf_counter()))
        return last

    def status(self) -> Dict[str, Any]:
        return {
            "version": LOOP_SCHEDULER_VERSION,
            "interval_seconds": self.interval_seconds,
            "max_iterations": self.max_iterations,
            "iterations": self._iterations,
            "running": bool(self._thread and self._thread.is_alive()),
            "stop_requested": self._stop_event.is_set(),
            "last_iteration_at": (self._last_result or {}).get("started_at"),
        }

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _run(self) -> None:
        for i in range(self.max_iterations):
            if self._stop_event.is_set():
                break
            self._run_once(iteration=i, loop=True)
            if i < self.max_iterations - 1 and not self._stop_event.is_set():
                sleep_for = self.interval_seconds
                if self.jitter_seconds > 0:
                    sleep_for += random.uniform(0, self.jitter_seconds)
                self._stop_event.wait(timeout=sleep_for)

    def _run_once(self, *, iteration: int, loop: bool) -> Dict[str, Any]:
        started_at = time.perf_counter()
        result_payload: Dict[str, Any] = {
            "version": LOOP_SCHEDULER_VERSION,
            "iteration": iteration,
            "started_at": started_at,
            "ok": False,
            "output": None,
            "stop_reason": None,
        }
        try:
            output = self._task_fn(iteration) or {}
        except Exception as e:
            log.exception("loop iteration %s raised", iteration)
            output = {"ok": False, "error": str(e)}
        result_payload["output"] = output
        result_payload["ok"] = bool(output.get("ok", False))
        result_payload["elapsed_ms"] = round((time.perf_counter() - started_at) * 1000, 1)
        self._last_result = result_payload
        self._iterations = iteration + 1
        if self._stop_predicate and self._stop_predicate(output):
            self._stop_event.set()
            result_payload["stop_reason"] = "predicate"
        if self._on_iteration:
            try:
                self._on_iteration(result_payload)
            except Exception:
                log.exception("loop on_iteration callback failed")
        return result_payload


def schedule_loop(
    task_fn: Callable[[int], Dict[str, Any]],
    *,
    interval_seconds: float = 60.0,
    max_iterations: int = 10,
    jitter_seconds: float = 1.0,
    stop_predicate: Optional[Callable[[Dict[str, Any]], bool]] = None,
    on_iteration: Optional[Callable[[Dict[str, Any]], None]] = None,
    blocking: bool = False,
) -> LoopScheduler:
    """Convenience constructor that starts a scheduler in one call."""
    scheduler = LoopScheduler(
        task_fn=task_fn,
        interval_seconds=interval_seconds,
        max_iterations=max_iterations,
        jitter_seconds=jitter_seconds,
        stop_predicate=stop_predicate,
        on_iteration=on_iteration,
    )
    if blocking:
        scheduler.run_blocking()
    else:
        scheduler.start()
    return scheduler