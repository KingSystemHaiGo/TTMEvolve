"""
tests/test_loop_homeostasis.py - loop homeostasis tests.

Phase R3 exit gate. The 2026-06-28 project_status stuck trace
must be detected by the controller. A subsequent regression
test in the wider suite replays the exact scenario.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.loop_homeostasis import LoopHomeostasis  # noqa: E402


def test_homeostasis_disabled_by_default():
    """When the flag is off, every update is a no-op."""
    h = LoopHomeostasis(enabled=False)
    for i in range(10):
        out = h.update(
            step={"action": {"tool": "project_status", "params": {}}},
            observation={"ok": True, "i": i},
        )
        assert out is None
    assert h.last_stuck is None


def test_homeostasis_detects_result_stable_after_3_calls():
    """Three identical observations for the same (tool, params)
    trigger ``reason="result_stable"``.
    """
    h = LoopHomeostasis(enabled=True)
    obs = {"ok": True, "project_root": "/x"}
    for i in range(2):
        out = h.update(
            step={"action": {"tool": "project_status", "params": {}}},
            observation=obs,
        )
        assert out is None
    out = h.update(
        step={"action": {"tool": "project_status", "params": {}}},
        observation=obs,
    )
    assert out is not None
    assert out["reason"] == "result_stable"
    assert out["tool"] == "project_status"


def test_homeostasis_resets_when_observation_changes():
    """An alternating observation pattern does not reach the
    result-stability limit. The deque-based history keeps the
    last N values; with frequent changes, the last N are not
    all identical.
    """
    h = LoopHomeostasis(enabled=True)
    # Interleave so the last 3 are mixed: 1, 2, 1, 2, 1, 2
    for i in range(6):
        out = h.update(
            step={"action": {"tool": "x", "params": {}}},
            observation={"a": (i % 2) + 1},
        )
    assert out is None
    # Now 3 in a row: 7, 8, 9 (all different from 1, 2; but all
    # identical to each other)
    h.reset()
    h.update(step={"action": {"tool": "x", "params": {}}}, observation={"a": 7})
    h.update(step={"action": {"tool": "x", "params": {}}}, observation={"a": 7})
    out = h.update(
        step={"action": {"tool": "x", "params": {}}}, observation={"a": 7}
    )
    assert out is not None
    assert out["reason"] == "result_stable"


def test_homeostasis_does_not_mix_different_tools():
    """Different tools have independent result-stability histories.

    Three calls to tool A with the same obs fires A. Three
    calls to tool B with the same obs fires B. They are
    independent.
    """
    h = LoopHomeostasis(enabled=True)
    obs = {"ok": True}
    # 3 tool A, same obs
    a_stuck = None
    for _ in range(3):
        a_stuck = h.update(
            step={"action": {"tool": "a", "params": {}}},
            observation=obs,
        )
    assert a_stuck is not None
    assert a_stuck["tool"] == "a"
    # Reset and try tool B
    h.reset()
    b_stuck = None
    for _ in range(3):
        b_stuck = h.update(
            step={"action": {"tool": "b", "params": {}}},
            observation=obs,
        )
    assert b_stuck is not None
    assert b_stuck["tool"] == "b"


def test_homeostasis_detects_no_progress():
    """Five iterations with the same plan_progress fingerprint
    trigger ``reason="no_progress"``.
    """
    h = LoopHomeostasis(enabled=True)
    for _ in range(4):
        out = h.update(plan_progress={"done": 0, "pending": 5})
        assert out is None
    out = h.update(plan_progress={"done": 0, "pending": 5})
    assert out is not None
    assert out["reason"] == "no_progress"
    assert out["iterations"] == 5


def test_homeostasis_detects_rescue_failure():
    """Two consecutive rescue failures trigger ``reason="rescue_failure"``."""
    h = LoopHomeostasis(enabled=True)
    h.update(rescue_failed=True)
    out = h.update(rescue_failed=True)
    assert out is not None
    assert out["reason"] == "rescue_failure"


def test_homeostasis_latches_first_stuck():
    """Once stuck is emitted, subsequent updates return None
    (terminal-once) until ``reset()``.
    """
    h = LoopHomeostasis(enabled=True)
    obs = {"ok": True}
    for _ in range(3):
        h.update(
            step={"action": {"tool": "x", "params": {}}},
            observation=obs,
        )
    assert h.last_stuck is not None
    # Subsequent calls return None
    for _ in range(5):
        assert h.update(
            step={"action": {"tool": "x", "params": {}}},
            observation=obs,
        ) is None
    # After reset, the controller can fire again
    h.reset()
    for _ in range(3):
        h.update(
            step={"action": {"tool": "x", "params": {}}},
            observation=obs,
        )
    assert h.last_stuck is not None


def test_homeostasis_2026_06_28_trace_replay():
    """The exact trace from the 2026-06-28 incident.

    Three calls to ``project_status`` returning the same dict must
    trigger ``reason="result_stable"`` before the rescue orchestrator
    gets to fire. The test name doubles as a regression marker.
    """
    h = LoopHomeostasis(enabled=True)
    obs = {
        "ok": True,
        "project_root": "D:\\CC\\taptep-maker-project",
        "exists": True,
        "top_level": [],
        "git": {},
        "markers": {
            "git": False,
            "package_json": False,
            "pyproject": False,
            "config": False,
            "maker_config": False,
            "project_settings": False,
        },
    }
    stuck = None
    for i in range(5):
        stuck = h.update(
            step={"action": {"tool": "project_status", "params": {}}},
            observation=obs,
        )
        if stuck is not None:
            break
    assert stuck is not None, "R3 controller failed to detect the stuck trace"
    assert stuck["reason"] == "result_stable"
    assert stuck["tool"] == "project_status"
    # The controller must fire by the 3rd call, not the 5th.
    assert i + 1 <= 3, f"controller fired at iteration {i+1}, expected <=3"
