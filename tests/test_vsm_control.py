"""
tests/test_vsm_control.py - VSMShell write surface (Phase R4).

Covers:
  - disable_tool / is_tool_disabled public API
  - S5 policy gate (off / audit / cautious)
  - Persist + expire behavior across step_counter ticks
  - disabled_tools() snapshot

The preflight hard block for Issue 5 was R2. R4 closes the
control loop: when the shell observes a stuck pattern, it
writes a tool disable; rank_tools (R4.2) consults the
blacklist.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.control_loop import ControlLoop  # noqa: E402
from core.vsm import VSMShell  # noqa: E402


def _make_shell(*, policy: str = "audit", persistence: int = 3, cooldown: int = 3) -> VSMShell:
    return VSMShell(
        control_loop=ControlLoop(),
        config={
            "enabled": True,
            "auto_replan": False,
            "replan_cooldown_steps": cooldown,
            "max_replan_depth": 1,
            "policy": policy,
            "s3_star_persistence": persistence,
        },
    )


# ---------------------------------------------------------------------------
# disable_tool / is_tool_disabled
# ---------------------------------------------------------------------------

def test_disable_tool_when_disabled_returns_false():
    """When the shell is itself disabled, writes are no-ops."""
    shell = VSMShell(control_loop=ControlLoop(), config={"enabled": False})
    assert shell.disable_tool("x") is False
    assert shell.is_tool_disabled("x") is False


def test_disable_tool_then_check():
    shell = _make_shell()
    assert shell.is_tool_disabled("project_status") is False
    shell.disable_tool("project_status", until_iter=10, reason="test")
    assert shell.is_tool_disabled("project_status") is True


def test_disabled_tool_expires_after_until_iter():
    """The blacklist expires when step_counter passes until_iter."""
    shell = _make_shell()
    shell.disable_tool("x", until_iter=5, reason="test")
    # step_counter starts at 0
    assert shell.is_tool_disabled("x") is True
    # Bump the counter past 5
    for _ in range(6):
        shell._step_counter += 1
    assert shell.is_tool_disabled("x") is False


def test_disabled_tools_returns_snapshot():
    shell = _make_shell()
    shell.disable_tool("a", until_iter=10, reason="x")
    shell.disable_tool("b", until_iter=10, reason="x")
    snap = shell.disabled_tools()
    assert set(snap) == {"a", "b"}


def test_disable_tool_extends_until_iter():
    """Disabling a tool again extends the deadline to the max of
    the existing and new until_iter values.
    """
    shell = _make_shell()
    shell.disable_tool("x", until_iter=5, reason="first")
    shell.disable_tool("x", until_iter=3, reason="second")
    assert shell._disabled["x"] == 5
    shell.disable_tool("x", until_iter=10, reason="third")
    assert shell._disabled["x"] == 10


# ---------------------------------------------------------------------------
# Policy gate
# ---------------------------------------------------------------------------

def test_policy_off_silently_writes():
    """With policy=off, no audit event is emitted."""
    events = []
    shell = _make_shell(policy="off")
    shell._emit = lambda sid, name, payload: events.append((name, payload))
    shell.disable_tool("x", until_iter=10, reason="test")
    assert not any(name == "vsm_write_audit" for name, _ in events)


def test_policy_audit_emits_vsm_write_audit():
    """With policy=audit, every write emits a vsm_write_audit event."""
    events = []
    shell = _make_shell(policy="audit")
    shell._emit = lambda sid, name, payload: events.append((name, payload))
    shell.disable_tool("x", until_iter=10, reason="r")
    audit_events = [p for n, p in events if n == "vsm_write_audit"]
    assert len(audit_events) == 1
    assert audit_events[0]["tool"] == "x"
    assert audit_events[0]["policy"] == "audit"


def test_policy_cautious_also_emits_policy_check_pending():
    """With policy=cautious, both audit and policy_check_pending fire."""
    events = []
    shell = _make_shell(policy="cautious")
    shell._emit = lambda sid, name, payload: events.append((name, payload))
    shell.disable_tool("x", until_iter=10, reason="r")
    assert any(n == "vsm_write_audit" for n, _ in events)
    pending = [p for n, p in events if n == "policy_check_pending"]
    assert len(pending) == 1
    assert pending[0]["action"] == "disable_tool"


# ---------------------------------------------------------------------------
# Persistent S3* trigger disables a tool
# ---------------------------------------------------------------------------

def test_persistent_s3_star_disables_tool():
    """When S3* fires ``s3_star_persistence`` times in a row, the
    shell disables the offending tool. This is the R4 control-
    surface behavior.
    """
    class _Stub:
        def last_verdict(self):
            return "diverging"
        def last_signal(self):
            return 5.0
        def evaluate(self, trajectory):
            return {"verdict": "diverging", "signal": 5.0}
    shell = VSMShell(
        control_loop=_Stub(),
        config={
            "enabled": True,
            "auto_replan": False,
            "replan_cooldown_steps": 5,
            "max_replan_depth": 1,
            "policy": "audit",
            "s3_star_persistence": 2,
        },
    )
    events = []
    shell._emit = lambda sid, name, payload: events.append((name, payload))
    step = {"action": {"tool": "project_status"}}
    plan = {}
    # First post_step: S3* fires, _s3_star_run=1, not yet 2.
    shell.post_step(step, {"ok": True}, [], plan)
    assert not shell.is_tool_disabled("project_status")
    # Second post_step: _s3_star_run=2, threshold hit, disable.
    shell._step_counter += 1
    shell.post_step(step, {"ok": True}, [], plan)
    assert shell.is_tool_disabled("project_status")
    # The audit event fired.
    audit = [p for n, p in events if n == "vsm_write_audit"]
    assert any(a.get("tool") == "project_status" for a in audit)


def test_s2_repeat_disables_tool():
    """Same step id 2x in a row -> S2 disable."""
    class _Stub:
        def last_verdict(self):
            return "stable"
        def last_signal(self):
            return 0.0
        def evaluate(self, trajectory):
            return {"verdict": "stable", "signal": 0.0}
    shell = VSMShell(
        control_loop=_Stub(),
        config={
            "enabled": True,
            "auto_replan": False,
            "replan_cooldown_steps": 5,
            "max_replan_depth": 1,
            "policy": "off",
        },
    )
    # Build a trajectory with 2 entries of the same tool.
    trajectory = [
        {"action": {"tool": "project_status"}, "step_id": "x"},
        {"action": {"tool": "project_status"}, "step_id": "x"},
    ]
    step = {"action": {"tool": "project_status"}, "step_id": "x"}
    plan = {}
    shell.post_step(step, {"ok": True}, trajectory, plan)
    assert shell.is_tool_disabled("project_status")


# ---------------------------------------------------------------------------
# Reset behavior
# ---------------------------------------------------------------------------

def test_disabled_cleaned_when_expired():
    """After expiration, the disabled entry is removed from the dict
    so subsequent snapshots are clean.
    """
    shell = _make_shell()
    shell.disable_tool("x", until_iter=3, reason="t")
    shell.disable_tool("y", until_iter=100, reason="t")
    assert "x" in shell.disabled_tools()
    assert "y" in shell.disabled_tools()
    for _ in range(5):
        shell._step_counter += 1
    snap = shell.disabled_tools()
    assert "x" not in snap
    assert "y" in snap
