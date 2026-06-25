"""Tests for v0.6.0 Coding Agent enhancements:
- core/conditional_hooks.py
- agent/subagent.py
- core/context_compression.py
- core/loop_scheduler.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Dict, List

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.conditional_hooks import (
    matches_predicate,
    select_applicable_hooks,
    _eval_simple_expr,
)
from core.context_compression import (
    compress_trajectory,
    extract_repeated_tool_warnings,
    render_compression_hint,
    should_compress,
)
from core.loop_scheduler import LoopScheduler, schedule_loop


# ---------- conditional hooks ----------


def test_empty_predicate_matches_everything():
    assert matches_predicate(None, {}) is True
    assert matches_predicate({}, {"action": {"tool": "x"}}) is True


def test_predicate_matches_tool():
    ctx = {"action": {"tool": "modify_file"}}
    assert matches_predicate({"tool": "modify_file"}, ctx) is True
    assert matches_predicate({"tool": "delete_file"}, ctx) is False


def test_predicate_matches_tool_prefix():
    ctx = {"action": {"tool": "maker_setup_status"}}
    assert matches_predicate({"tool_prefix": "maker_"}, ctx) is True
    assert matches_predicate({"tool_prefix": "git_"}, ctx) is False


def test_predicate_matches_verdict():
    ctx = {"observation": {"plan_validation": {"verdict": "pass"}}}
    assert matches_predicate({"verdict": "pass"}, ctx) is True
    assert matches_predicate({"verdict": "fail"}, ctx) is False


def test_predicate_matches_ok_observation():
    assert matches_predicate({"ok": True}, {"observation": {"ok": True}}) is True
    assert matches_predicate({"ok": True}, {"observation": {"ok": False}}) is False


def test_predicate_matches_iteration_gte():
    assert matches_predicate({"iteration_gte": 3}, {"iteration": 5}) is True
    assert matches_predicate({"iteration_gte": 3}, {"iteration": 2}) is False


def test_predicate_expr_simple_eq():
    ctx = {"iteration": 5}
    assert _eval_simple_expr("iteration==5", ctx) is True
    assert _eval_simple_expr("iteration==6", ctx) is False


def test_predicate_expr_numeric_compare():
    ctx = {"iteration": 3, "ok": True}
    assert _eval_simple_expr("iteration>=3 and ok==True", ctx) is True
    assert _eval_simple_expr("iteration>=5 and ok==True", ctx) is False


def test_select_applicable_hooks_filters_out_non_matching():
    items = [
        {"type": "append", "content": "A"},
        {"type": "append", "content": "B", "when": {"tool": "modify_file"}},
        {"type": "append", "content": "C", "when": {"tool": "delete_file"}},
    ]
    ctx = {"action": {"tool": "modify_file"}}
    applicable = select_applicable_hooks(items, ctx)
    contents = [item.get("content") for item in applicable]
    assert "A" in contents
    assert "B" in contents
    assert "C" not in contents


# ---------- context compression ----------


def test_should_compress_triggers_at_threshold():
    trajectory = [{"iteration": i, "action": {"tool": "x"}} for i in range(8)]
    assert should_compress(trajectory, summary_threshold=8) is True


def test_should_compress_holds_until_threshold():
    trajectory = [{"iteration": i, "action": {"tool": "x"}} for i in range(4)]
    assert should_compress(trajectory, summary_threshold=8) is False


def test_compress_trajectory_returns_summary_and_verbatim():
    trajectory = [
        {"iteration": i, "action": {"tool": "modify_file"}, "observation": {"ok": i % 2 == 0}}
        for i in range(10)
    ]
    result = compress_trajectory(trajectory, task="demo", verbatim_turns=4)
    assert result["compressed_step_count"] == 6
    assert len(result["verbatim_steps"]) == 4
    assert result["stats"]["step_count"] == 10
    assert "Task: demo" in result["summary"]


def test_compress_trajectory_includes_checklist_and_plan():
    trajectory = [
        {"iteration": 0, "action": {"tool": "x"}, "observation": {"ok": True}},
    ]
    checklist = {"overall": "active", "counts": {"done": 1, "pending": 1, "warn": 0, "fail": 0}}
    plan = {"summary": "build demo", "steps": [{"status": "pending"}, {"status": "done"}]}
    result = compress_trajectory(trajectory, task="t", checklist=checklist, plan=plan)
    assert "build demo" in result["summary"]
    assert "active" in result["summary"]


def test_render_compression_hint_is_compact():
    trajectory = [
        {"iteration": i, "action": {"tool": "modify_file"}, "observation": {"ok": True}}
        for i in range(10)
    ]
    compressed = compress_trajectory(trajectory, task="t", verbatim_turns=3)
    hint = render_compression_hint(compressed)
    assert "compressed_context" in hint
    assert "verbatim_recent_steps" in hint


def test_extract_repeated_tool_warnings_detects_loop():
    trajectory = [
        {"iteration": i, "action": {"tool": "modify_file"}, "observation": {"ok": True}}
        for i in range(5)
    ]
    warnings = extract_repeated_tool_warnings(trajectory, threshold=3)
    assert any("Loop risk" in w for w in warnings)


def test_extract_repeated_tool_warnings_clean_for_diverse_tools():
    trajectory = [
        {"iteration": 0, "action": {"tool": "modify_file"}, "observation": {"ok": True}},
        {"iteration": 1, "action": {"tool": "shell"}, "observation": {"ok": True}},
        {"iteration": 2, "action": {"tool": "modify_file"}, "observation": {"ok": True}},
    ]
    warnings = extract_repeated_tool_warnings(trajectory, threshold=3)
    assert warnings == []


# ---------- loop scheduler ----------


def test_loop_scheduler_runs_blocking_with_predicate_stop():
    calls: List[int] = []

    def task(iter_index: int) -> Dict[str, Any]:
        calls.append(iter_index)
        return {"ok": iter_index >= 1}

    scheduler = schedule_loop(
        task,
        interval_seconds=0.001,
        max_iterations=5,
        jitter_seconds=0,
        stop_predicate=lambda out: bool(out.get("ok")),
        blocking=True,
    )
    status = scheduler.status()
    assert status["iterations"] == 2
    assert calls == [0, 1]


def test_loop_scheduler_invalid_interval_raises():
    try:
        LoopScheduler(task_fn=lambda i: {}, interval_seconds=0)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_loop_scheduler_invalid_max_iterations_raises():
    try:
        LoopScheduler(task_fn=lambda i: {}, max_iterations=0)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_loop_scheduler_status_contains_required_keys():
    scheduler = LoopScheduler(task_fn=lambda i: {"ok": True})
    status = scheduler.status()
    for key in ("version", "interval_seconds", "max_iterations", "iterations", "running"):
        assert key in status