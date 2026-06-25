"""Tests for the v0.7.0 performance monitor."""

from __future__ import annotations

import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.perf_monitor import (
    PERF_MONITOR_VERSION,
    PerformanceMonitor,
    get_global_monitor,
    set_global_monitor,
)


def test_start_stop_records_elapsed_ms():
    monitor = PerformanceMonitor()
    monitor.start("phase_a")
    time.sleep(0.01)
    elapsed = monitor.stop("phase_a")
    assert elapsed >= 10  # ≥ 10ms (very safe lower bound)


def test_stop_without_start_returns_zero_and_counts_error():
    monitor = PerformanceMonitor()
    elapsed = monitor.stop("phantom")
    assert elapsed == 0.0
    assert monitor._error_count == 1


def test_summary_contains_p50_p95_max_min_avg_count():
    monitor = PerformanceMonitor()
    for _ in range(10):
        monitor.start("phase_b")
        time.sleep(0.001)
        monitor.stop("phase_b")
    summary = monitor.summary()
    assert summary["version"] == PERF_MONITOR_VERSION
    assert "phase_b" in summary["phases"]
    stats = summary["phases"]["phase_b"]
    assert stats["count"] == 10
    assert stats["min_ms"] <= stats["p50_ms"] <= stats["p95_ms"] <= stats["max_ms"]


def test_disabled_monitor_does_not_record():
    monitor = PerformanceMonitor(enabled=False)
    monitor.start("phase_c")
    time.sleep(0.01)
    elapsed = monitor.stop("phase_c")
    assert elapsed == 0.0
    assert "phase_c" not in monitor.summary()["phases"]


def test_record_method_appends_sample():
    monitor = PerformanceMonitor()
    monitor.record("phase_d", 12.5)
    monitor.record("phase_d", 18.0)
    stats = monitor.summary()["phases"]["phase_d"]
    assert stats["count"] == 2
    assert stats["max_ms"] == 18.0


def test_reset_clears_all_state():
    monitor = PerformanceMonitor()
    monitor.start("phase_e")
    monitor.stop("phase_e")
    monitor.record("phase_f", 10.0)
    monitor.reset()
    summary = monitor.summary()
    assert summary["phases"] == {}
    assert summary["error_count"] == 0


def test_max_samples_zero_disables_recording_but_keeps_count():
    monitor = PerformanceMonitor(max_samples=0)
    monitor.start("phase_g")
    monitor.stop("phase_g")
    summary = monitor.summary()
    # No samples kept
    assert "phase_g" not in summary["phases"]


def test_global_monitor_singleton():
    """get_global_monitor() returns the same instance."""
    set_global_monitor(PerformanceMonitor())
    a = get_global_monitor()
    b = get_global_monitor()
    assert a is b


def test_global_monitor_can_be_replaced():
    a = get_global_monitor()
    replacement = PerformanceMonitor()
    set_global_monitor(replacement)
    b = get_global_monitor()
    assert b is replacement
    assert b is not a