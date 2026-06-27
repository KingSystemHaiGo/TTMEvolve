from agent.trajectory_result import (
    build_react_result,
    latest_output_from_trajectory,
    record_observation_step,
    record_output_step,
    summarize_react_result,
)


def test_record_observation_step_preserves_public_event_order():
    trajectory = []
    step = {"iteration": 0, "action": {"tool": "read_file"}}
    observation = {"ok": True, "content": "hello"}
    order = []
    events = []

    def emit(session_id, event_type, payload):
        order.append(("emit", event_type))
        events.append({"session_id": session_id, "type": event_type, "payload": payload})

    def validate_step(recorded_step):
        assert recorded_step["observation"] == observation
        return {"verdict": "pass", "summary": "checked"}

    def refresh_goal(**kwargs):
        order.append(("refresh_goal", kwargs))

    def skill_sync(**kwargs):
        order.append(("skill_sync", kwargs))

    def context_sync(**kwargs):
        order.append(("context_sync", kwargs))

    report = record_observation_step(
        trajectory=trajectory,
        step=step,
        iteration=0,
        session_id="s1",
        tool_name="read_file",
        observation=observation,
        emit=emit,
        validate_step=validate_step,
        refresh_goal=refresh_goal,
        emit_skill_sync=skill_sync,
        emit_context_sync=context_sync,
        reason="plan_validation",
    )

    assert report["verdict"] == "pass"
    assert trajectory == [step]
    assert step["plan_validation"]["summary"] == "checked"
    assert [event["type"] for event in events] == ["observation", "plan_validation"]
    assert events[0]["payload"]["tool"] == "read_file"
    assert order == [
        ("emit", "observation"),
        ("emit", "plan_validation"),
        ("refresh_goal", {}),
        ("skill_sync", {"iteration": 0, "reason": "plan_validation"}),
        ("context_sync", {"iteration": 0, "reason": "plan_validation"}),
    ]


def test_record_output_step_appends_and_refreshes_goal_before_context_sync():
    trajectory = []
    step = {"iteration": 2, "done": True, "output": "finished"}
    order = []
    events = []

    def emit(session_id, event_type, payload):
        order.append(("emit", event_type))
        events.append({"session_id": session_id, "type": event_type, "payload": payload})

    def refresh_goal(**kwargs):
        order.append(("refresh_goal", kwargs))

    def context_sync(**kwargs):
        order.append(("context_sync", kwargs))

    record_output_step(
        trajectory=trajectory,
        step=step,
        iteration=2,
        session_id="s1",
        emit=emit,
        refresh_goal=refresh_goal,
        emit_context_sync=context_sync,
    )

    assert trajectory == [step]
    assert events == [{"session_id": "s1", "type": "output", "payload": {"output": "finished"}}]
    assert order == [
        ("emit", "output"),
        ("refresh_goal", {"output": "finished"}),
        ("context_sync", {"iteration": 2, "reason": "output"}),
    ]


def test_build_react_result_uses_latest_output_and_optional_plan_fields():
    trajectory = [
        {"iteration": 0, "output": "older"},
        {"iteration": 1, "plan_validation": {"verdict": "pass"}},
        {"iteration": 2, "done": True, "output": "latest"},
    ]
    result = build_react_result(
        session_id="s1",
        task="do work",
        trajectory=trajectory,
        goal_checklist={"overall": "done"},
        plan={"steps": [{"id": "s1", "status": "done"}]},
        plan_review={"verdict": "pass"},
        include_plan=True,
    )

    assert result["trajectory"] is trajectory
    assert result["output"] == "latest"
    assert result["iteration_count"] == 3
    assert result["plan_validation"]["counts"]["pass"] == 1
    assert result["goal_checklist"]["overall"] == "done"
    assert result["plan_review"]["verdict"] == "pass"
    assert result["plan_progress"]["counts"]["done"] == 1
    assert summarize_react_result(result) == {"iteration_count": 3, "output_length": 6}


def test_latest_output_from_trajectory_handles_missing_output():
    assert latest_output_from_trajectory([]) == ""
    assert latest_output_from_trajectory([{"iteration": 0}, {"done": True}]) == ""
