"""
tests/test_rescue_trigger.py — 救援触发器测试
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config
from agent.rescue_trigger import RescueTrigger, RescueRequired
from core.health import AgentHealthState


def _config(**kwargs) -> Config:
    data = {"rescue": kwargs}
    cfg = Config()
    cfg.data = data
    cfg._profiles = {}
    return cfg


def test_consecutive_errors():
    trigger = RescueTrigger(_config(max_consecutive_errors=3))
    trajectory = [
        {"observation": {"ok": False}},
        {"observation": {"ok": False}},
        {"observation": {"ok": False}},
    ]
    assert trigger.evaluate(trajectory) is True
    print("[PASS] consecutive errors trigger")


def test_not_enough_consecutive_errors():
    trigger = RescueTrigger(_config(max_consecutive_errors=3))
    trajectory = [
        {"observation": {"ok": False}},
        {"observation": {"ok": True}},
        {"observation": {"ok": False}},
    ]
    assert trigger.evaluate(trajectory) is False
    print("[PASS] not enough consecutive errors")


def test_repeated_actions():
    trigger = RescueTrigger(_config(detect_repeated_actions=True))
    trajectory = [
        {"action": {"tool": "read_file", "params": {"path": "a"}}, "observation": {"ok": False}},
        {"action": {"tool": "read_file", "params": {"path": "a"}}, "observation": {"ok": False}},
        {"action": {"tool": "read_file", "params": {"path": "a"}}, "observation": {"ok": False}},
    ]
    assert trigger.evaluate(trajectory) is True
    print("[PASS] repeated actions trigger")


def test_iteration_exhaustion():
    trigger = RescueTrigger(_config(max_iterations_ratio=0.75, max_iterations=20))
    trajectory = [{"iteration": 15, "observation": {"ok": False}}]
    assert trigger.evaluate(trajectory) is True
    print("[PASS] iteration exhaustion trigger")


def test_health_degraded():
    trigger = RescueTrigger(_config(health_degraded=True))
    state = AgentHealthState(
        pid=1,
        last_heartbeat=0,
        last_progress_event=0,
        iteration_count=0,
        progress_metric=0.0,
        token_usage_ratio=0.0,
        context_window_ratio=0.0,
        error_count=0,
        status="degraded",
    )
    assert trigger.evaluate([], state) is True
    print("[PASS] health degraded trigger")


def test_check_and_raise():
    trigger = RescueTrigger(_config(max_consecutive_errors=1))
    try:
        trigger.check_and_raise([{"observation": {"ok": False}}])
        raise AssertionError("应该抛出 RescueRequired")
    except RescueRequired:
        pass
    print("[PASS] check_and_raise")


def test_disabled_rescue():
    trigger = RescueTrigger(_config(max_consecutive_errors=0))
    trajectory = [{"observation": {"ok": False}}] * 10
    assert trigger.evaluate(trajectory) is False
    print("[PASS] disabled rescue")


if __name__ == "__main__":
    test_consecutive_errors()
    test_not_enough_consecutive_errors()
    test_repeated_actions()
    test_iteration_exhaustion()
    test_health_degraded()
    test_check_and_raise()
    test_disabled_rescue()
    print("[PASS] all rescue trigger tests")
