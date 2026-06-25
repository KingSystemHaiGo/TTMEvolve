"""Performance monitor — lightweight timing instrumentation.

Tracks per-tool-call and per-phase latency to surface slow paths during
ReAct iteration. Designed to be zero-cost when disabled (the default).

Usage:
    monitor = PerformanceMonitor()
    monitor.start("think")
    # ... do work
    elapsed_ms = monitor.stop("think")
    summary = monitor.summary()
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, Optional


PERF_MONITOR_VERSION = "perf-monitor.v1"


class PerformanceMonitor:
    """Lightweight, opt-in performance monitor."""

    def __init__(self, max_samples: int = 200, enabled: bool = True) -> None:
        self._enabled = bool(enabled)
        self.max_samples = max(0, int(max_samples))
        self._samples: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=self.max_samples) if self.max_samples > 0 else deque()
        )
        self._pending: Dict[str, float] = {}
        self._error_count = 0

    def start(self, phase: str) -> None:
        if not self._enabled:
            return
        self._pending[phase] = time.perf_counter()

    def stop(self, phase: str) -> float:
        """Stop timing a phase; returns elapsed milliseconds (0 if disabled)."""
        if not self._enabled:
            return 0.0
        started_at = self._pending.pop(phase, None)
        if started_at is None:
            self._error_count += 1
            return 0.0
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        if self.max_samples > 0:
            self._samples[phase].append(elapsed_ms)
        return elapsed_ms

    def record(self, phase: str, elapsed_ms: float) -> None:
        if not self._enabled or self.max_samples <= 0:
            return
        self._samples[phase].append(float(elapsed_ms))

    def summary(self) -> Dict[str, Any]:
        """Return per-phase p50 / p95 / max / count stats."""
        result: Dict[str, Any] = {
            "version": PERF_MONITOR_VERSION,
            "enabled": self._enabled,
            "error_count": self._error_count,
            "phases": {},
        }
        for phase, samples in self._samples.items():
            if not samples:
                continue
            ordered = sorted(samples)
            n = len(ordered)
            result["phases"][phase] = {
                "count": n,
                "min_ms": round(ordered[0], 3),
                "max_ms": round(ordered[-1], 3),
                "avg_ms": round(sum(ordered) / n, 3),
                "p50_ms": round(ordered[n // 2], 3),
                "p95_ms": round(ordered[int(n * 0.95) - 1] if n > 1 else ordered[-1], 3),
            }
        return result

    def reset(self) -> None:
        self._samples.clear()
        self._pending.clear()
        self._error_count = 0


_GLOBAL_MONITOR: Optional[PerformanceMonitor] = None


def get_global_monitor() -> PerformanceMonitor:
    """Return the process-wide singleton monitor."""
    global _GLOBAL_MONITOR
    if _GLOBAL_MONITOR is None:
        _GLOBAL_MONITOR = PerformanceMonitor()
    return _GLOBAL_MONITOR


def set_global_monitor(monitor: PerformanceMonitor) -> None:
    """Replace the global monitor (mostly for tests)."""
    global _GLOBAL_MONITOR
    _GLOBAL_MONITOR = monitor