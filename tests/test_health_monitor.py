from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.health import HealthMonitor


def test_context_window_pressure_degrades_health():
    with tempfile.TemporaryDirectory() as tmp:
        monitor = HealthMonitor(Path(tmp))
        state = monitor.heartbeat({
            "pid": 1,
            "iteration_count": 3,
            "progress_metric": 0.5,
            "token_usage_ratio": 0.2,
            "context_window_ratio": 0.91,
            "error_count": 0,
        })

        assert state.status == "degraded"
        assert state.context_saturation == "high"


def test_context_saturation_bands_are_reported():
    with tempfile.TemporaryDirectory() as tmp:
        monitor = HealthMonitor(Path(tmp))

        state = monitor.heartbeat({"context_window_ratio": 0.79})
        assert state.context_saturation == "normal"

        state = monitor.heartbeat({"context_window_ratio": 0.8})
        assert state.context_saturation == "elevated"

        state = monitor.heartbeat({"context_window_ratio": 0.9})
        assert state.context_saturation == "high"

        state = monitor.heartbeat({"context_window_ratio": 0.95})
        assert state.context_saturation == "critical"


if __name__ == "__main__":
    test_context_window_pressure_degrades_health()
    test_context_saturation_bands_are_reported()
    print("[PASS] health monitor tests")
