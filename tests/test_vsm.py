"""
tests/test_vsm.py - VSMShell thin adapter tests.

The shell labels existing control signals with VSM vocabulary (S1, S2,
S3, S3*, S4, S5) and routes them to the right control points. It must
NOT create a parallel control dashboard.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.vsm import (  # noqa: E402
    VSM_LAYERS,
    VSMShell,
)


class _StubControlLoop:
    def __init__(self, verdicts: List[str]):
        self._verdicts = list(verdicts)
        self._index = 0
        self.last_signal_value = 0.0
        # Seed last_verdict with the first verdict so callers that read
        # it before any ``evaluate()`` call see a deterministic value.
        self.last_verdict_value = verdicts[0] if verdicts else "stable"

    def evaluate(self, trajectory):
        if self._index < len(self._verdicts):
            self.last_verdict_value = self._verdicts[self._index]
            self._index += 1
        return {"verdict": self.last_verdict_value, "signal": 0.0}

    def last_verdict(self) -> str:
        return self.last_verdict_value

    def last_signal(self) -> float:
        return self.last_signal_value


# ---------------------------------------------------------------------------
# Layer mapping
# ---------------------------------------------------------------------------

def test_vsm_layers_match_adr():
    assert VSM_LAYERS == {
        "S1", "S2", "S3", "S3*", "S4", "S5",
    }


def test_vsm_shell_classifies_each_step_to_a_layer():
    shell = VSMShell(control_loop=_StubControlLoop([]), config={
        "auto_replan": False,
        "replan_cooldown_steps": 3,
        "max_replan_depth": 1,
    })
    # A plain tool call is S1
    s1_step = {"id": "x", "kind": "tool", "vsm_layer": "S1"}
    assert shell.classify(s1_step) == "S1"
    # Default to S1 when not specified
    default_step = {"id": "y", "kind": "tool"}
    assert shell.classify(default_step) == "S1"


# ---------------------------------------------------------------------------
# Pre-step / post-step
# ---------------------------------------------------------------------------

def test_vsm_pre_step_records_s5_policy_observation():
    shell = VSMShell(control_loop=_StubControlLoop([]), config={
        "enabled": True,
        "auto_replan": False,
        "replan_cooldown_steps": 3,
        "max_replan_depth": 1,
    })
    events: List[Dict[str, Any]] = []
    shell.pre_step(
        step={"id": "x", "kind": "tool", "vsm_layer": "S1"},
        plan={},
        trajectory=[],
        policy={"sandbox": "workspace-write", "approval": "on-request"},
        emit=lambda name, kind, payload: events.append({"name": name, "kind": kind, "payload": payload}),
    )
    s5_events = [e for e in events if e["payload"].get("layer") == "S5"]
    assert len(s5_events) >= 1


def test_vsm_post_step_returns_continue_on_stable():
    shell = VSMShell(control_loop=_StubControlLoop(["stable"]), config={
        "enabled": True,
        "auto_replan": False,
        "replan_cooldown_steps": 3,
        "max_replan_depth": 1,
    })
    events: List[Dict[str, Any]] = []
    verdict = shell.post_step(
        step={"id": "x", "kind": "tool", "vsm_layer": "S1"},
        observation={"ok": True},
        trajectory=[],
        plan={},
        emit=lambda name, kind, payload: events.append({"name": name, "kind": kind, "payload": payload}),
    )
    assert verdict == "continue"


# ---------------------------------------------------------------------------
# S4 escalation
# ---------------------------------------------------------------------------

def test_vsm_post_step_returns_continue_when_diverging_but_auto_replan_disabled():
    shell = VSMShell(control_loop=_StubControlLoop(["diverging"]), config={
        "enabled": True,
        "auto_replan": False,
        "replan_cooldown_steps": 3,
        "max_replan_depth": 1,
    })
    verdict = shell.post_step(
        step={"id": "x", "kind": "tool", "vsm_layer": "S1"},
        observation={"ok": False},
        trajectory=[],
        plan={},
        emit=lambda *args, **kwargs: None,
    )
    # No auto-replan, so the verdict is "continue" (or "needs_action");
    # the runtime layer should still raise RescueRequired via the existing
    # RescueTrigger path. The shell's job is to surface the signal, not
    # block on it.
    assert verdict in {"continue", "needs_action"}


def test_vsm_post_step_signals_replan_when_diverging_and_auto_replan_enabled():
    shell = VSMShell(control_loop=_StubControlLoop(["diverging"]), config={
        "enabled": True,
        "auto_replan": True,
        "replan_cooldown_steps": 1,
        "max_replan_depth": 1,
    })
    events: List[Dict[str, Any]] = []
    verdict = shell.post_step(
        step={"id": "x", "kind": "tool", "vsm_layer": "S1"},
        observation={"ok": False},
        trajectory=[],
        plan={"version": "plan-format.v2", "steps": []},
        emit=lambda name, kind, payload: events.append({"name": name, "kind": kind, "payload": payload}),
    )
    # Cooldown is 1 step; this is the first step, so cooldown allows replan
    assert verdict == "replan"
    replan_events = [e for e in events if e["payload"].get("action") == "replan"]
    assert len(replan_events) == 1


def test_vsm_post_step_respects_replan_cooldown():
    shell = VSMShell(control_loop=_StubControlLoop(["diverging", "diverging"]), config={
        "enabled": True,
        "auto_replan": True,
        "replan_cooldown_steps": 3,
        "max_replan_depth": 1,
    })
    # First call: cooldown 3, post_step has run 0 steps since init → replan fires
    shell.post_step(
        step={"id": "x", "kind": "tool", "vsm_layer": "S1"},
        observation={"ok": False},
        trajectory=[],
        plan={},
        emit=lambda *args, **kwargs: None,
    )
    # Second call immediately after: only 1 step since the last signal,
    # cooldown requires 3 → "continue" (not replan)
    events: List[Dict[str, Any]] = []
    verdict = shell.post_step(
        step={"id": "y", "kind": "tool", "vsm_layer": "S1"},
        observation={"ok": False},
        trajectory=[],
        plan={},
        emit=lambda name, kind, payload: events.append({"name": name, "kind": kind, "payload": payload}),
    )
    replan_events = [e for e in events if e["payload"].get("action") == "replan"]
    assert len(replan_events) == 0
    assert verdict in {"continue", "needs_action"}


# ---------------------------------------------------------------------------
# Disabled by default
# ---------------------------------------------------------------------------

def test_vsm_shell_disabled_does_nothing():
    """When ``vsm.enabled=false`` the shell is bypassed entirely."""
    shell = VSMShell(control_loop=_StubControlLoop(["diverging"]), config={
        "enabled": False,
        "auto_replan": True,
        "replan_cooldown_steps": 1,
        "max_replan_depth": 1,
    })
    # When disabled, ``is_active()`` is False and post_step should
    # always return "continue" without firing replan events.
    assert shell.is_active() is False
    events: List[Dict[str, Any]] = []
    verdict = shell.post_step(
        step={"id": "x", "kind": "tool", "vsm_layer": "S1"},
        observation={"ok": False},
        trajectory=[],
        plan={},
        emit=lambda name, kind, payload: events.append({"name": name, "kind": kind, "payload": payload}),
    )
    assert verdict == "continue"
    assert not any(e["payload"].get("action") == "replan" for e in events)
