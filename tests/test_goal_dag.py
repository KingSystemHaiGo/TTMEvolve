"""Tests for the typed sub-goal DAG (Q4 / Slice B)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.goal_dag import (
    GOAL_DAG_VERSION,
    HINT_BALANCED,
    HINT_DEEP,
    HINT_FAST,
    KNOWN_HINTS,
    GoalDAGError,
    GoalDAGScheduler,
    SubGoalResult,
    SubGoalSpec,
    SubGoalType,
    topological_layers,
)
from agent.goal_loop import GoalLoop
from agent.typed_subloop import (
    DEFAULT_SUBLOOPS,
    asset_subloop,
    audio_subloop,
    build_default_runners,
    code_subloop,
    integration_subloop,
    scene_subloop,
    _subloop_test,
)


# ---------------------------------------------------------------------------
# SubGoalSpec
# ---------------------------------------------------------------------------


def test_sub_goal_spec_complexity_uses_boundary_signals():
    """Complexity is a function of acceptance / dependency /
    capability signals — not a count of source lines."""
    spec = SubGoalSpec(
        sub_id="simple",
        task="trivial change",
        type=SubGoalType.CODE,
    )
    base = spec.complexity_score()
    rich = SubGoalSpec(
        sub_id="rich",
        task="wide change",
        type=SubGoalType.CODE,
        acceptance=["compiles", "tests pass", "no regressions"],
        depends_on=["asset-hero"],
        model_hint=HINT_DEEP,
        assigned_agent="programmer-1",
    )
    assert rich.complexity_score() > base


def test_sub_goal_spec_to_dict_includes_complexity():
    spec = SubGoalSpec(
        sub_id="x", task="t", type=SubGoalType.ASSET,
        acceptance=["exists"],
    )
    out = spec.to_dict()
    assert out["sub_id"] == "x"
    assert out["type"] == "asset"
    assert "complexity" in out


# ---------------------------------------------------------------------------
# topological_layers
# ---------------------------------------------------------------------------


def test_topological_layers_respects_dependencies():
    specs = [
        SubGoalSpec(sub_id="a", task="A", type=SubGoalType.CODE),
        SubGoalSpec(sub_id="b", task="B", type=SubGoalType.ASSET, depends_on=["a"]),
        SubGoalSpec(sub_id="c", task="C", type=SubGoalType.SCENE, depends_on=["a"]),
        SubGoalSpec(
            sub_id="i", task="I", type=SubGoalType.INTEGRATION,
            depends_on=["b", "c"],
        ),
    ]
    layers = topological_layers(specs)
    assert [s.sub_id for s in layers[0]] == ["a"]
    assert {s.sub_id for s in layers[1]} == {"b", "c"}
    assert [s.sub_id for s in layers[2]] == ["i"]


def test_topological_layers_detects_cycle():
    specs = [
        SubGoalSpec(sub_id="x", task="X", type=SubGoalType.CODE, depends_on=["y"]),
        SubGoalSpec(sub_id="y", task="Y", type=SubGoalType.ASSET, depends_on=["x"]),
    ]
    with pytest.raises(GoalDAGError):
        topological_layers(specs)


def test_topological_layers_detects_unknown_dependency():
    specs = [SubGoalSpec(sub_id="a", task="A", type=SubGoalType.CODE, depends_on=["ghost"])]
    with pytest.raises(GoalDAGError):
        topological_layers(specs)


def test_topological_layers_detects_duplicate_id():
    specs = [
        SubGoalSpec(sub_id="dup", task="A", type=SubGoalType.CODE),
        SubGoalSpec(sub_id="dup", task="B", type=SubGoalType.ASSET),
    ]
    with pytest.raises(GoalDAGError):
        topological_layers(specs)


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


def _recording_runner(results: List[SubGoalResult], status: str = "done"):
    def _runner(spec: SubGoalSpec, gid: str, sid: str) -> SubGoalResult:
        results.append(SubGoalResult(spec=spec, status=status, output={"summary": f"ran {spec.sub_id}"}))
        return results[-1]
    return _runner


def test_scheduler_runs_independent_subgoals_in_parallel_chunks():
    """When max_concurrent >= layer size, every sub-goal in a layer
    runs before the next layer. We assert ordering, not real
    concurrency, because the test is single-threaded."""
    order: List[str] = []
    runners = {
        SubGoalType.CODE: lambda spec, gid, sid: (
            order.append(spec.sub_id) or SubGoalResult(spec=spec, status="done")
        ),
        SubGoalType.INTEGRATION: lambda spec, gid, sid: (
            order.append(spec.sub_id) or SubGoalResult(spec=spec, status="done")
        ),
    }
    specs = [
        SubGoalSpec(sub_id="a", task="A", type=SubGoalType.CODE),
        SubGoalSpec(sub_id="b", task="B", type=SubGoalType.CODE),
        SubGoalSpec(sub_id="i", task="I", type=SubGoalType.INTEGRATION, depends_on=["a", "b"]),
    ]
    scheduler = GoalDAGScheduler(runners, max_concurrent=4)
    results = scheduler.run(specs, parent_goal_id="g", parent_session_id="s")
    assert [r.sub_id for r in results] == ["a", "b", "i"]
    # a and b must run before i.
    assert order.index("a") < order.index("i")
    assert order.index("b") < order.index("i")


def test_scheduler_skips_downstream_when_dependency_fails():
    runners = {
        SubGoalType.CODE: _recording_runner([], status="needs_fix"),
        SubGoalType.INTEGRATION: _recording_runner([], status="done"),
    }
    specs = [
        SubGoalSpec(sub_id="a", task="A", type=SubGoalType.CODE),
        SubGoalSpec(
            sub_id="i", task="I", type=SubGoalType.INTEGRATION,
            depends_on=["a"],
        ),
    ]
    scheduler = GoalDAGScheduler(runners, max_concurrent=2)
    results = scheduler.run(specs, parent_goal_id="g", parent_session_id="s")
    statuses = {r.sub_id: r.status for r in results}
    assert statuses["a"] == "needs_fix"
    assert statuses["i"] == "skipped"


def test_scheduler_blocks_when_runner_missing():
    """A sub-goal whose type has no registered runner becomes
    ``blocked`` rather than crashing the whole DAG."""
    runners = {SubGoalType.CODE: _recording_runner([])}
    specs = [SubGoalSpec(sub_id="a", task="A", type=SubGoalType.ASSET)]
    scheduler = GoalDAGScheduler(runners, max_concurrent=1)
    results = scheduler.run(specs, parent_goal_id="g", parent_session_id="s")
    assert results[0].status == "blocked"
    assert "asset" in results[0].error


# ---------------------------------------------------------------------------
# Per-type sub-loops
# ---------------------------------------------------------------------------


def test_asset_subloop_records_artifacts():
    spec = SubGoalSpec(
        sub_id="asset-hero", task="create hero sprite",
        type=SubGoalType.ASSET,
        artifacts_expected=["assets/sprites/hero.png"],
        acceptance=["png exists", "size < 64KB"],
    )
    result = asset_subloop(spec, "g", "s")
    assert result.status == "done"
    assert result.artifacts[0]["path"] == "assets/sprites/hero.png"


def test_code_subloop_requires_dev_runner():
    spec = SubGoalSpec(sub_id="c", task="write code", type=SubGoalType.CODE)
    result = code_subloop(spec, "g", "s")
    assert result.status == "blocked"
    assert "dev_runner" in result.error


def test_code_subloop_passes_through_to_dev_runner():
    spec = SubGoalSpec(sub_id="c", task="write code", type=SubGoalType.CODE)
    def dev_runner(task, session_id):
        return {"session_id": session_id, "task": task, "done": True, "output": "ok"}
    result = code_subloop(spec, "g", "s", dev_runner=dev_runner)
    assert result.status == "done"
    assert "ok" in result.output["summary"]


def test_code_subloop_marks_needs_fix_when_runner_errors():
    spec = SubGoalSpec(sub_id="c", task="write code", type=SubGoalType.CODE)
    def dev_runner(task, session_id):
        return {"session_id": session_id, "task": task, "done": False, "error": "boom"}
    result = code_subloop(spec, "g", "s", dev_runner=dev_runner)
    assert result.status == "needs_fix"
    assert "boom" in result.error


def test_scene_subloop_records_scene_id():
    spec = SubGoalSpec(
        sub_id="scene-1", task="build level 1",
        type=SubGoalType.SCENE,
        metadata={"scene_id": "level_1", "nodes": ["player", "boss"]},
    )
    result = scene_subloop(spec, "g", "s")
    assert result.status == "done"
    assert result.output["scene_id"] == "level_1"


def test_audio_subloop_lists_tracks():
    spec = SubGoalSpec(
        sub_id="audio-1", task="bgm + sfx",
        type=SubGoalType.AUDIO,
        metadata={"tracks": ["bgm", "hit_sfx"]},
    )
    result = audio_subloop(spec, "g", "s")
    assert result.status == "done"
    assert {a["name"] for a in result.artifacts} == {"bgm", "hit_sfx"}


def test_integration_subloop_records_evidence():
    spec = SubGoalSpec(
        sub_id="i", task="wire everything",
        type=SubGoalType.INTEGRATION,
        depends_on=["a", "b"],
    )
    result = integration_subloop(
        spec, "g", "s",
        integration_evidence={"passed": True, "tests": 12},
    )
    assert result.status == "done"
    assert result.output["evidence"]["passed"] is True


def test_test_subloop_records_acceptance():
    spec = SubGoalSpec(
        sub_id="t", task="run acceptance",
        type=SubGoalType.TEST,
        acceptance=["builds", "tests pass"],
    )
    result = _subloop_test(spec, "g", "s")
    assert result.status == "done"
    assert result.output["acceptance"] == ["builds", "tests pass"]


# ---------------------------------------------------------------------------
# build_default_runners
# ---------------------------------------------------------------------------


def test_build_default_runners_registers_every_type():
    runners = build_default_runners()
    expected = {SubGoalType.ASSET, SubGoalType.CODE, SubGoalType.SCENE,
                SubGoalType.AUDIO, SubGoalType.TEST, SubGoalType.INTEGRATION}
    assert set(runners.keys()) == expected


def test_build_default_runners_threads_dev_runner_into_code():
    seen: List[str] = []
    def dev_runner(task, sid):
        seen.append(task)
        return {"session_id": sid, "task": task, "done": True, "output": "ok"}
    runners = build_default_runners(dev_runner=dev_runner)
    result = runners[SubGoalType.CODE](
        SubGoalSpec(sub_id="c", task="code here", type=SubGoalType.CODE),
        "g", "s",
    )
    assert result.status == "done"
    assert seen == ["code here"]


# ---------------------------------------------------------------------------
# GoalLoop integration: typed sub-goal path
# ---------------------------------------------------------------------------


def _code_dev_runner(task, sid):
    return {
        "session_id": sid,
        "task": task,
        "done": True,
        "output": f"ok: {task}",
        "iteration_count": 1,
    }


class _TypedLLM:
    """LLM that proposes a typed sub-goal DAG including an integration."""

    def reflect(self, prompt: str) -> str:
        if "PROPOSE stage" in prompt:
            return json.dumps({
                "recommended": "build the boss",
                "sub_goals": [
                    {
                        "task": "generate boss sprite",
                        "type": "asset",
                        "id": "asset-boss",
                        "acceptance": ["png exists"],
                        "model_hint": "fast",
                    },
                    {
                        "task": "implement boss AI",
                        "type": "code",
                        "id": "code-boss",
                        "depends_on": ["asset-boss"],
                        "acceptance": ["compiles", "tests pass"],
                        "model_hint": "balanced",
                    },
                    {
                        "task": "wire boss into level",
                        "type": "scene",
                        "id": "scene-boss",
                        "depends_on": ["code-boss"],
                        "acceptance": ["scene loads"],
                    },
                ],
            })
        return "{}"


import json


def test_goal_loop_uses_typed_dag_when_no_user_runner(tmp_path: Path):
    events: List[Dict[str, Any]] = []
    loop = GoalLoop(
        project_root=tmp_path,
        emit=events.append,
        dev_runner=_code_dev_runner,
        approval_policy="never",
        llm=_TypedLLM(),
        max_subgoals=4,
    )
    result = loop.run("build the boss feature", session_id="e2e")
    assert result["done"] is True
    # All four sub-goals were recorded (3 from LLM + integration).
    assert len(result["goal_loop"]["sub_goals"]) == 4
    statuses = {s["sub_id"]: s["status"] for s in result["goal_loop"]["sub_goals"]}
    assert statuses["asset-boss"] == "done"
    assert statuses["code-boss"] == "done"
    assert statuses["scene-boss"] == "done"
    assert statuses["integration"] == "done"
    # Integration sub-goal depends on the LLM's three.
    integration = next(
        s for s in result["goal_loop"]["sub_goals"] if s["sub_id"] == "integration"
    )
    assert set(integration["depends_on"]) == {"asset-boss", "code-boss", "scene-boss"}


def test_goal_loop_keeps_legacy_runner_for_backward_compat(tmp_path: Path):
    """When the user supplies a custom sub_goal_runner (the legacy
    interface) the goal loop still calls it with the old signature."""
    captured: Dict[str, Any] = {}

    def legacy_runner(tasks, sid, parent_depth):
        captured["tasks"] = list(tasks)
        captured["session_id"] = sid
        captured["parent_depth"] = parent_depth
        return [{"goal_id": "child", "task": tasks[0], "status": "completed", "summary": "ok"}]

    class _LegacyLLM:
        def reflect(self, prompt: str) -> str:
            if "PROPOSE stage" in prompt:
                return json.dumps({
                    "recommended": "do it",
                    "sub_goals": ["build schema", "build query layer"],
                })
            return "{}"

    loop = GoalLoop(
        project_root=tmp_path,
        emit=lambda e: None,
        dev_runner=_code_dev_runner,
        approval_policy="never",
        llm=_LegacyLLM(),
        sub_goal_runner=legacy_runner,
    )
    result = loop.run("legacy", session_id="leg")
    assert result["done"] is True
    assert captured["tasks"] == ["build schema", "build query layer"]
    assert captured["session_id"] == "leg"
    assert captured["parent_depth"] == 0


def test_goal_loop_appends_integration_when_missing(tmp_path: Path):
    events: List[Dict[str, Any]] = []
    class _NoIntegrationLLM:
        def reflect(self, prompt: str) -> str:
            if "PROPOSE stage" in prompt:
                return json.dumps({
                    "recommended": "split work",
                    "sub_goals": [
                        {"task": "first half", "type": "code", "id": "first"},
                        {"task": "second half", "type": "code", "id": "second", "depends_on": ["first"]},
                    ],
                })
            return "{}"
    loop = GoalLoop(
        project_root=tmp_path,
        emit=events.append,
        dev_runner=_code_dev_runner,
        approval_policy="never",
        llm=_NoIntegrationLLM(),
    )
    result = loop.run("do two halves", session_id="h")
    ids = {s["sub_id"] for s in result["goal_loop"]["sub_goals"]}
    assert ids == {"first", "second", "integration"}


def test_goal_loop_complexity_signal_in_sub_goal_records(tmp_path: Path):
    events: List[Dict[str, Any]] = []
    class _RichAcceptanceLLM:
        def reflect(self, prompt: str) -> str:
            if "PROPOSE stage" in prompt:
                return json.dumps({
                    "recommended": "complex feature",
                    "sub_goals": [
                        {
                            "task": "do everything",
                            "type": "code",
                            "id": "all",
                            "acceptance": ["a", "b", "c", "d", "e"],
                            "model_hint": "deep",
                        },
                    ],
                })
            return "{}"
    loop = GoalLoop(
        project_root=tmp_path,
        emit=events.append,
        dev_runner=_code_dev_runner,
        approval_policy="never",
        llm=_RichAcceptanceLLM(),
    )
    result = loop.run("complex thing", session_id="c")
    all_sub = next(s for s in result["goal_loop"]["sub_goals"] if s["sub_id"] == "all")
    # complexity comes from acceptance count + deep model hint + 1 base
    assert all_sub["complexity"] >= 7
