from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.goal_loop import GOAL_STAGES, GoalLoop, GoalLoopError
from server.goal_loop_api import build_goal_loop_summary


def _dev_runner(task: str, session_id: str) -> Dict[str, Any]:
    return {
        "session_id": session_id,
        "task": task,
        "done": True,
        "output": f"dev done: {task}",
        "trajectory": [{"observation": {"ok": True}}],
        "iteration_count": 1,
    }


class _StageLLM:
    """Fake LLM that returns stage-shaped JSON via reflect()."""

    def __init__(self, *, broken: bool = False):
        self.broken = broken
        self.prompts: List[str] = []

    def reflect(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.broken:
            return "not json at all"
        if "UNDERSTAND stage" in prompt:
            return (
                '{"restated_goal": "Ship the widget", '
                '"subtasks": ["design", "build"], '
                '"success_criteria": ["tests pass"], "open_questions": []}'
            )
        if "RESEARCH stage" in prompt:
            return '```json\n{"constraints": ["use modular monolith"], "risks": ["scope creep"], "summary": "researched"}\n```'
        if "PROPOSE stage" in prompt:
            return (
                '{"recommended": "Implement behind a feature flag", '
                '"alternatives": ["big bang"], "risks": ["flag debt"], '
                '"acceptance": ["flag off by default"]}'
            )
        if "REV stage" in prompt:
            return '{"intent_match": true, "issues": [], "summary": "looks good"}'
        return "{}"


class _RevLLM:
    """Fake LLM whose REV verdict fails the first N times, then passes."""

    def __init__(self, *, rev_fails: int):
        self.rev_fails = rev_fails
        self.rev_calls = 0

    def reflect(self, prompt: str) -> str:
        if "REV stage" in prompt:
            self.rev_calls += 1
            if self.rev_calls <= self.rev_fails:
                return '{"intent_match": false, "issues": ["missing tests"], "summary": "incomplete"}'
            return '{"intent_match": true, "issues": [], "summary": "ok"}'
        return "{}"


class _SubGoalLLM:
    """Fake LLM that proposes sub-goals in PROPOSE."""

    def reflect(self, prompt: str) -> str:
        if "PROPOSE stage" in prompt:
            return (
                '{"recommended": "split it", "alternatives": [], "risks": [], '
                '"acceptance": ["each sub-task passes"], '
                '"sub_goals": ["build schema", "build query layer"]}'
            )
        return "{}"


def test_propose_triggers_sub_goals_via_runner(tmp_path: Path):
    events: List[Dict[str, Any]] = []
    sub_called_with: Dict[str, Any] = {}

    def runner(tasks, session_id, parent_depth):
        sub_called_with["tasks"] = list(tasks)
        sub_called_with["session_id"] = session_id
        sub_called_with["parent_depth"] = parent_depth
        return [
            {"goal_id": "child-a", "task": t, "status": "completed", "summary": "ok"}
            for t in tasks
        ]

    loop = GoalLoop(
        project_root=tmp_path,
        emit=events.append,
        dev_runner=_dev_runner,
        approval_policy="never",
        llm=_SubGoalLLM(),
        sub_goal_runner=runner,
    )

    result = loop.run("decompose a large goal", session_id="parent")

    assert result["done"] is True
    assert sub_called_with["tasks"] == ["build schema", "build query layer"]
    assert sub_called_with["parent_depth"] == 0
    sub_started = [e for e in events if e["type"] == "goal_sub_goals_started"]
    sub_done = [e for e in events if e["type"] == "goal_sub_goals_completed"]
    assert sub_started and sub_done
    assert result["goal_loop"]["sub_goals"][0]["parent_goal_id"] == result["goal_loop"]["goal_id"]


def test_sub_goal_runner_failure_does_not_crash_parent(tmp_path: Path):
    events: List[Dict[str, Any]] = []

    def crashing_runner(tasks, session_id, parent_depth):
        raise RuntimeError("runner exploded")

    loop = GoalLoop(
        project_root=tmp_path,
        emit=events.append,
        dev_runner=_dev_runner,
        approval_policy="never",
        llm=_SubGoalLLM(),
        sub_goal_runner=crashing_runner,
    )

    result = loop.run("decompose with broken runner", session_id="crash")

    # Parent still completes; the failure is captured in the evidence.
    assert result["done"] is True
    goal_payload = result["goal_loop"]
    assert goal_payload["sub_goals"][0]["status"] == "failed"
    assert "runner exploded" in goal_payload["sub_goals"][0]["summary"]


def test_sub_goals_respect_max_subgoals_budget(tmp_path: Path):
    called_with: List[str] = []

    def runner(tasks, session_id, parent_depth):
        called_with.extend(tasks)
        return [{"goal_id": f"c{i}", "task": t, "status": "completed", "summary": "ok"} for i, t in enumerate(tasks)]

    class _LoudLLM:
        def reflect(self, prompt: str) -> str:
            if "PROPOSE stage" in prompt:
                return (
                    '{"recommended": "split", "sub_goals": ["a", "b", "c", "d", "e", "f"], '
                    '"alternatives": [], "risks": [], "acceptance": []}'
                )
            return "{}"

    loop = GoalLoop(
        project_root=tmp_path,
        emit=lambda e: events.append(e) if False else None,
        dev_runner=_dev_runner,
        approval_policy="never",
        llm=_LoudLLM(),
        sub_goal_runner=runner,
        max_subgoals=2,
    )
    events = []  # noqa: rebind for clarity
    loop.run("cap sub-goals", session_id="cap")

    assert called_with == ["a", "b"]


def test_sub_goals_skip_at_max_depth(tmp_path: Path):
    called: List[str] = []

    def runner(tasks, session_id, parent_depth):
        called.extend(tasks)
        return [{"goal_id": "c", "task": t, "status": "completed", "summary": "ok"} for t in tasks]

    loop = GoalLoop(
        project_root=tmp_path,
        dev_runner=_dev_runner,
        approval_policy="never",
        llm=_SubGoalLLM(),
        sub_goal_runner=runner,
        max_depth=0,
    )

    result = loop.run("no recursion allowed", session_id="depth0")

    assert result["done"] is True
    assert called == []  # never invoked — depth check stopped it
    assert result["goal_loop"]["sub_goals"] == []


def _stage_starts(events):
    return [e["payload"]["stage"] for e in events if e["type"] == "goal_stage_started"]


def _stage_output(events, stage):
    for e in events:
        if e["type"] == "goal_stage_output" and e["payload"]["stage"] == stage:
            return e["payload"]["stage_run"]["output"]
    raise AssertionError(f"no output event for stage {stage}")


def test_goal_loop_uses_llm_reasoning_when_available(tmp_path: Path):
    events: List[Dict[str, Any]] = []
    llm = _StageLLM()
    loop = GoalLoop(
        project_root=tmp_path,
        emit=events.append,
        dev_runner=_dev_runner,
        approval_policy="never",
        llm=llm,
    )

    result = loop.run("ship the widget", session_id="llm")

    assert result["done"] is True
    understand = _stage_output(events, "UNDERSTAND")
    assert understand["reasoning"] == "llm"
    assert understand["subtasks"] == ["design", "build"]
    assert understand["success_criteria"] == ["tests pass"]
    propose = _stage_output(events, "PROPOSE")
    assert propose["reasoning"] == "llm"
    assert propose["proposal"]["recommended"] == "Implement behind a feature flag"
    research = _stage_output(events, "RESEARCH")
    assert research["constraints"] == ["use modular monolith"]


def test_goal_loop_falls_back_to_template_when_llm_output_unparseable(tmp_path: Path):
    events: List[Dict[str, Any]] = []
    loop = GoalLoop(
        project_root=tmp_path,
        emit=events.append,
        dev_runner=_dev_runner,
        approval_policy="never",
        llm=_StageLLM(broken=True),
    )

    result = loop.run("ship the widget", session_id="broken-llm")

    assert result["done"] is True
    understand = _stage_output(events, "UNDERSTAND")
    assert understand["reasoning"] == "template"
    assert understand["subtasks"]  # template subtasks still present
    assert any(e["type"] == "goal_reasoning_failed" for e in events)


def test_rev_failure_reworks_dev_then_completes(tmp_path: Path):
    events: List[Dict[str, Any]] = []
    loop = GoalLoop(
        project_root=tmp_path,
        emit=events.append,
        dev_runner=_dev_runner,
        approval_policy="never",
        llm=_RevLLM(rev_fails=1),
        max_rework_cycles=1,
    )

    result = loop.run("ship with review gate", session_id="rework")

    assert result["done"] is True
    starts = _stage_starts(events)
    # DEV runs twice (original + one rework), REV runs twice (fail then pass).
    assert starts.count("DEV") == 2
    assert starts.count("REV") == 2
    fix_events = [e for e in events if e["type"] == "goal_stage_fix"]
    assert fix_events and fix_events[0]["payload"]["mode"] == "rework"
    assert fix_events[0]["payload"]["target_stage"] == "DEV"


def test_rev_failure_accepts_degraded_result_when_rework_budget_exhausted(tmp_path: Path):
    events: List[Dict[str, Any]] = []
    loop = GoalLoop(
        project_root=tmp_path,
        emit=events.append,
        dev_runner=_dev_runner,
        approval_policy="never",
        llm=_RevLLM(rev_fails=5),  # always fails
        max_rework_cycles=1,
    )

    result = loop.run("ship with strict reviewer", session_id="exhaust")

    starts = _stage_starts(events)
    # One rework allowed: DEV runs twice, then loop proceeds past REV degraded.
    assert starts.count("DEV") == 2
    assert "REPORT" in starts
    assert "POST" in starts


def test_goal_loop_runs_fixed_stage_order_and_writes_confirm_artifacts(tmp_path: Path):
    events: List[Dict[str, Any]] = []
    loop = GoalLoop(
        project_root=tmp_path,
        emit=events.append,
        dev_runner=_dev_runner,
        approval_policy="never",
        artifacts_root=tmp_path,
    )

    result = loop.run("implement GoalLoop architecture", session_id="s1")

    assert result["done"] is True
    stage_starts = [e["payload"]["stage"] for e in events if e["type"] == "goal_stage_started"]
    assert stage_starts == GOAL_STAGES
    assert (tmp_path / "system-contracts" / "goals" / "goal-s1.md").exists()
    assert list((tmp_path / "decisions").glob("*.md"))
    confirm_index = stage_starts.index("CONFIRM")
    dev_index = stage_starts.index("DEV")
    assert confirm_index < dev_index


def test_goal_loop_blocks_before_doc_read_when_understand_rejected(tmp_path: Path):
    events: List[Dict[str, Any]] = []
    loop = GoalLoop(
        project_root=tmp_path,
        emit=events.append,
        confirm=lambda message: False,
        dev_runner=_dev_runner,
        approval_policy="on-request",
    )

    result = loop.run("do the thing", session_id="reject-understand")

    assert result["done"] is False
    stage_starts = [e["payload"]["stage"] for e in events if e["type"] == "goal_stage_started"]
    assert stage_starts == ["UNDERSTAND"]
    assert not (tmp_path / "system-contracts").exists()


def test_goal_loop_blocks_confirm_before_dev_and_does_not_write_artifacts(tmp_path: Path):
    approvals = iter([True, False])
    events: List[Dict[str, Any]] = []
    loop = GoalLoop(
        project_root=tmp_path,
        emit=events.append,
        confirm=lambda message: next(approvals),
        dev_runner=_dev_runner,
        approval_policy="on-request",
    )

    result = loop.run("implement a confirmed change", session_id="reject-confirm")

    assert result["done"] is False
    stage_starts = [e["payload"]["stage"] for e in events if e["type"] == "goal_stage_started"]
    assert "CONFIRM" in stage_starts
    assert "DEV" not in stage_starts
    assert not (tmp_path / "system-contracts").exists()


def test_goal_loop_refuses_depth_over_max(tmp_path: Path):
    loop = GoalLoop(project_root=tmp_path, approval_policy="never", max_depth=2)

    try:
        loop.run("too deep", session_id="deep", depth=3)
    except GoalLoopError as exc:
        assert "exceeds max_depth" in str(exc)
        return
    raise AssertionError("depth overflow should raise GoalLoopError")


def test_stage_review_compiles_handoff_as_next_stage_input(tmp_path: Path):
    events: List[Dict[str, Any]] = []
    loop = GoalLoop(
        project_root=tmp_path,
        emit=events.append,
        dev_runner=_dev_runner,
        approval_policy="never",
    )

    loop.run("architecture control loop", session_id="handoff")

    doc_read_started = [
        e for e in events
        if e["type"] == "goal_stage_started" and e["payload"]["stage"] == "DOC_READ"
    ][0]
    stage_input = doc_read_started["payload"]["stage_run"]["input"]
    assert stage_input["from_stage"] == "UNDERSTAND"
    assert stage_input["to_stage"] == "DOC_READ"
    assert "summary" in stage_input["data"]
    assert "output" not in stage_input["data"]


def test_post_stage_builds_plan_without_applying_by_default(tmp_path: Path):
    events: List[Dict[str, Any]] = []
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "memory-index.md").write_text("# Memory Index\n", encoding="utf-8")
    loop = GoalLoop(
        project_root=tmp_path,
        emit=events.append,
        dev_runner=_dev_runner,
        approval_policy="never",
    )
    result = loop.run("ship a small change", session_id="post-default")

    post = _stage_output(events, "POST")
    assert post["ok"] is True
    assert post["plan"]["status"] in {"ready", "already_applied", "no_updates_due"}
    assert post["auto_post"] is False
    assert "applied" not in post  # no apply without auto_post
    assert (tmp_path / "docs" / "memory-index.md").read_text(encoding="utf-8") == "# Memory Index\n"


def test_post_stage_auto_apply_writes_marker_to_allowed_files(tmp_path: Path):
    events: List[Dict[str, Any]] = []
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "sprint-board.md").write_text("# Sprint\n", encoding="utf-8")
    loop = GoalLoop(
        project_root=tmp_path,
        emit=events.append,
        dev_runner=_dev_runner,
        approval_policy="never",
        auto_post=True,
    )
    result = loop.run("ship a real change", session_id="post-apply")

    post = _stage_output(events, "POST")
    assert post["auto_post"] is True
    assert post["ok"] is True
    assert post.get("applied", {}).get("applied_count", 0) >= 1
    body = (tmp_path / "docs" / "sprint-board.md").read_text(encoding="utf-8")
    assert "TTMEVOLVE-PROJECT-WRITEBACK" in body
    assert "post-apply" in body  # marker includes session id
    post_events = [e for e in events if e["type"] == "goal_post_completed"]
    assert post_events


def test_post_stage_refuses_to_write_outside_allowed_files(tmp_path: Path):
    events: List[Dict[str, Any]] = []

    def report_with_bad_due(goal, handoff):
        # Simulate a stage that mistakenly proposes a non-whitelisted file.
        return {
            "ok": True,
            "summary": "manual report",
            "report": "ok",
            "memory_updates_due": [
                {"gate": "POST", "file": "secrets/leak.txt"},
                {"gate": "POST", "file": "docs/memory-index.md"},
            ],
        }

    loop = GoalLoop(
        project_root=tmp_path,
        emit=events.append,
        dev_runner=_dev_runner,
        approval_policy="never",
        auto_post=True,
    )
    # Patch the REPORT dispatcher to inject the malicious file.
    loop._stage_report = report_with_bad_due  # type: ignore[assignment]
    loop.run("adversarial report", session_id="post-block")

    post = _stage_output(events, "POST")
    # Either the planner refused the bad target (status=blocked) or the
    # apply step errored, but nothing under secrets/ ever exists.
    assert not (tmp_path / "secrets").exists()
    secrets = list((tmp_path / "docs" / "memory-index.md").read_text(encoding="utf-8")) if (
        tmp_path / "docs" / "memory-index.md"
    ).exists() else ""
    assert "secrets/leak.txt" not in secrets


def test_post_stage_is_idempotent_on_repeat_run(tmp_path: Path):
    events: List[Dict[str, Any]] = []
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "sprint-board.md").write_text("# Sprint\n", encoding="utf-8")
    loop = GoalLoop(
        project_root=tmp_path,
        emit=events.append,
        dev_runner=_dev_runner,
        approval_policy="never",
        auto_post=True,
    )
    loop.run("first run", session_id="idem-session")
    first_body = (tmp_path / "docs" / "sprint-board.md").read_text(encoding="utf-8")
    first_marker_count = first_body.count("TTMEVOLVE-PROJECT-WRITEBACK")

    # Reuse the same session_id so the marker matches and a second run
    # observes already-applied state.
    events.clear()
    loop.run("second run", session_id="idem-session")
    second_body = (tmp_path / "docs" / "sprint-board.md").read_text(encoding="utf-8")
    second_marker_count = second_body.count("TTMEVOLVE-PROJECT-WRITEBACK")
    assert second_marker_count == first_marker_count  # no duplicate append


def test_goal_loop_summary_rebuilds_from_events(tmp_path: Path):
    events: List[Dict[str, Any]] = []
    loop = GoalLoop(
        project_root=tmp_path,
        emit=events.append,
        dev_runner=_dev_runner,
        approval_policy="never",
    )
    loop.run("summarize goal events", session_id="summary")

    summary = build_goal_loop_summary(session_id="summary", events=events)

    assert summary["status"] == "completed"
    assert summary["current_stage"] == "POST"
    assert summary["counts"]["stages"] == len(GOAL_STAGES)
    assert summary["counts"]["confirmations"] == 2
    assert summary["counts"]["artifacts"] == 2
