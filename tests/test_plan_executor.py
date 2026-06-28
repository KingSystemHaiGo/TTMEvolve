"""
tests/test_plan_executor.py - recursive plan executor tests.

The executor handles dependency enforcement, branch/loop steps, sub-plan
recursion, and refuses cycles / unknown deps. It does NOT execute tools
itself — the caller supplies a ``step_runner`` callback.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.plan_executor import (  # noqa: E402
    PlanExecutor,
    PlanExecutorError,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

class _Runner:
    """A no-op step runner that records invocations and returns a
    fixed observation. Tests can read ``self.calls`` to verify order.
    """

    def __init__(self, *, fail_steps: set = None, fail_message: str = "boom"):
        self.calls: List[Dict[str, Any]] = []
        self._fail_steps = set(fail_steps or set())
        self._fail_message = fail_message

    def __call__(self, step, plan, depth):
        self.calls.append({"step_id": step.get("id"), "depth": depth, "tool": step.get("tool")})
        if step.get("id") in self._fail_steps:
            return {"ok": False, "error": self._fail_message, "step_id": step.get("id")}
        return {"ok": True, "step_id": step.get("id")}


# ---------------------------------------------------------------------------
# Dependency enforcement
# ---------------------------------------------------------------------------

def test_executor_runs_steps_in_dependency_order():
    plan = {
        "version": "plan-format.v2",
        "task": "test",
        "summary": "t",
        "steps": [
            {"id": "a", "kind": "tool", "tool": "read_file", "depends_on": []},
            {"id": "b", "kind": "tool", "tool": "write_file", "depends_on": ["a"]},
            {"id": "c", "kind": "tool", "tool": "git_commit", "depends_on": ["b"]},
        ],
    }
    runner = _Runner()
    executor = PlanExecutor(step_runner=runner, config={"max_depth": 3})
    result = executor.execute_plan(plan)
    assert result["status"] == "completed"
    order = [c["step_id"] for c in runner.calls]
    assert order == ["a", "b", "c"]


def test_executor_refuses_unknown_dependency():
    plan = {
        "version": "plan-format.v2",
        "task": "t",
        "summary": "s",
        "steps": [
            {"id": "a", "kind": "tool", "tool": "read_file", "depends_on": ["ghost"]},
        ],
    }
    runner = _Runner()
    executor = PlanExecutor(step_runner=runner, config={"max_depth": 3})
    try:
        executor.execute_plan(plan)
    except PlanExecutorError:
        return
    raise AssertionError("unknown dependency should raise PlanExecutorError")


def test_executor_refuses_cycle():
    plan = {
        "version": "plan-format.v2",
        "task": "t",
        "summary": "s",
        "steps": [
            {"id": "a", "kind": "tool", "tool": "x", "depends_on": ["b"]},
            {"id": "b", "kind": "tool", "tool": "y", "depends_on": ["a"]},
        ],
    }
    runner = _Runner()
    executor = PlanExecutor(step_runner=runner, config={"max_depth": 3})
    try:
        executor.execute_plan(plan)
    except PlanExecutorError:
        return
    raise AssertionError("cycle should raise PlanExecutorError")


def test_executor_refuses_max_depth_overflow():
    plan = {
        "version": "plan-format.v2",
        "task": "t",
        "summary": "s",
        "steps": [
            {
                "id": "outer", "kind": "sub_plan", "sub_plan": {
                    "version": "plan-format.v2", "task": "inner", "summary": "i",
                    "steps": [
                        {
                            "id": "inner", "kind": "sub_plan", "sub_plan": {
                                "version": "plan-format.v2", "task": "deepest", "summary": "d",
                                "steps": [{"id": "d1", "kind": "tool", "tool": "x", "depends_on": []}],
                            },
                            "depends_on": [],
                        }
                    ],
                },
                "depends_on": [],
            }
        ],
    }
    runner = _Runner()
    executor = PlanExecutor(step_runner=runner, config={"max_depth": 1})
    try:
        executor.execute_plan(plan)
    except PlanExecutorError:
        return
    raise AssertionError("depth overflow should raise PlanExecutorError")


# ---------------------------------------------------------------------------
# Sub-plan recursion
# ---------------------------------------------------------------------------

def test_executor_executes_sub_plan_steps():
    plan = {
        "version": "plan-format.v2",
        "task": "outer", "summary": "o",
        "steps": [
            {
                "id": "outer", "kind": "sub_plan",
                "sub_plan": {
                    "version": "plan-format.v2", "task": "inner", "summary": "i",
                    "steps": [
                        {"id": "i1", "kind": "tool", "tool": "x", "depends_on": []},
                        {"id": "i2", "kind": "tool", "tool": "y", "depends_on": ["i1"]},
                    ],
                },
                "depends_on": [],
            }
        ],
    }
    runner = _Runner()
    executor = PlanExecutor(step_runner=runner, config={"max_depth": 3})
    result = executor.execute_plan(plan)
    assert result["status"] == "completed"
    # Both sub-plan steps should have been called, with depth=1
    step_ids = [(c["step_id"], c["depth"]) for c in runner.calls]
    assert ("i1", 1) in step_ids
    assert ("i2", 1) in step_ids


# ---------------------------------------------------------------------------
# Branch / loop
# ---------------------------------------------------------------------------

def test_executor_branch_picks_then_branch_when_condition_true():
    plan = {
        "version": "plan-format.v2",
        "task": "t", "summary": "s",
        "steps": [
            {
                "id": "b1", "kind": "branch", "depends_on": [],
                "condition": "observation.ok == True",
                "then": {"id": "then", "kind": "tool", "tool": "a", "depends_on": []},
                "else": {"id": "else", "kind": "tool", "tool": "b", "depends_on": []},
            }
        ],
    }
    runner = _Runner()
    executor = PlanExecutor(
        step_runner=runner,
        condition_runner=lambda expr, ctx: True,
        config={"max_depth": 3},
    )
    result = executor.execute_plan(plan)
    order = [c["step_id"] for c in runner.calls]
    assert "then" in order
    assert "else" not in order


def test_executor_branch_picks_else_branch_when_condition_false():
    plan = {
        "version": "plan-format.v2",
        "task": "t", "summary": "s",
        "steps": [
            {
                "id": "b1", "kind": "branch", "depends_on": [],
                "condition": "observation.ok == True",
                "then": {"id": "then", "kind": "tool", "tool": "a", "depends_on": []},
                "else": {"id": "else", "kind": "tool", "tool": "b", "depends_on": []},
            }
        ],
    }
    runner = _Runner()
    executor = PlanExecutor(
        step_runner=runner,
        condition_runner=lambda expr, ctx: False,
        config={"max_depth": 3},
    )
    result = executor.execute_plan(plan)
    order = [c["step_id"] for c in runner.calls]
    assert "else" in order
    assert "then" not in order


def test_executor_loop_stops_at_max_iterations():
    plan = {
        "version": "plan-format.v2",
        "task": "t", "summary": "s",
        "steps": [
            {
                "id": "loop1", "kind": "loop", "depends_on": [],
                "max_iterations": 3,
                "condition": "observation.ok == True",  # always true
                "body": {"id": "body", "kind": "tool", "tool": "x", "depends_on": []},
            }
        ],
    }
    runner = _Runner()
    executor = PlanExecutor(
        step_runner=runner,
        condition_runner=lambda expr, ctx: True,
        config={"max_depth": 3, "max_loop_iterations": 3},
    )
    executor.execute_plan(plan)
    body_calls = sum(1 for c in runner.calls if c["step_id"] == "body")
    assert body_calls == 3


def test_executor_loop_stops_when_condition_false():
    plan = {
        "version": "plan-format.v2",
        "task": "t", "summary": "s",
        "steps": [
            {
                "id": "loop1", "kind": "loop", "depends_on": [],
                "max_iterations": 10,
                "condition": "control_signal.signal > 0.5",
                "body": {"id": "body", "kind": "tool", "tool": "x", "depends_on": []},
            }
        ],
    }
    runner = _Runner()
    # First call: condition true. Second call: condition false → stop.
    flag = {"value": 0}

    def _cond(expr, ctx):
        flag["value"] += 1
        return flag["value"] == 1

    executor = PlanExecutor(
        step_runner=runner,
        condition_runner=_cond,
        config={"max_depth": 3, "max_loop_iterations": 10},
    )
    executor.execute_plan(plan)
    body_calls = sum(1 for c in runner.calls if c["step_id"] == "body")
    assert body_calls == 1


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------

def test_executor_marks_step_failed_on_runner_error():
    plan = {
        "version": "plan-format.v2",
        "task": "t", "summary": "s",
        "steps": [
            {"id": "a", "kind": "tool", "tool": "x", "depends_on": []},
            {"id": "b", "kind": "tool", "tool": "y", "depends_on": ["a"]},
        ],
    }
    runner = _Runner(fail_steps={"a"})
    executor = PlanExecutor(step_runner=runner, config={"max_depth": 3})
    result = executor.execute_plan(plan)
    # Status is "needs_recovery" because step a failed and b depends on it
    assert result["status"] in {"needs_recovery", "completed"}
    # b should not have been called because a failed
    called = {c["step_id"] for c in runner.calls}
    assert "a" in called
    assert "b" not in called


# ---------------------------------------------------------------------------
# Plan v2 normalization
# ---------------------------------------------------------------------------

def test_executor_accepts_v1_plan_and_normalizes_to_v2():
    plan_v1 = {
        "version": "plan-format.v1",
        "task": "t",
        "summary": "s",
        "steps": [
            {"id": "a", "tool": "read_file", "params": {}, "intent": "x",
             "expected_evidence": ["file contents"], "depends_on": []}
        ],
    }
    runner = _Runner()
    executor = PlanExecutor(step_runner=runner, config={"max_depth": 3})
    result = executor.execute_plan(plan_v1)
    assert result["status"] == "completed"
    # v1 step should have been treated as kind="tool" with vsm_layer="S1"
    assert runner.calls[0]["step_id"] == "a"
    assert runner.calls[0]["tool"] == "read_file"
