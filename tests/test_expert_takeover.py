from agent.expert_takeover import run_expert_takeover


class _ExpertLLM:
    def __init__(self, actions):
        self.actions = list(actions)
        self.think_contexts = []

    def think(self, task, context, trajectory, tools_description):
        self.think_contexts.append(context)
        return f"think-{len(self.think_contexts)}"

    def choose_action(self, task, thought, tools_description):
        return self.actions.pop(0)


def _events():
    captured = []

    def emit(session_id, event_type, payload):
        captured.append({"session_id": session_id, "type": event_type, "payload": payload})

    return captured, emit


def test_expert_takeover_stops_on_done_and_preserves_event_order():
    events, emit = _events()
    trajectory = []
    expert = _ExpertLLM([{"done": True, "output": "expert done"}])

    result = run_expert_takeover(
        expert_llm=expert,
        steps=3,
        task="task",
        session_id="s1",
        trajectory=trajectory,
        context=lambda: "ctx",
        tools_description=lambda: "tools",
        emit=emit,
        execute_action=lambda session_id, tool, params: {"ok": True},
        append_context=lambda text: None,
    )

    assert result.steps_executed == 1
    assert result.stopped_on_done is True
    assert trajectory[0]["source"] == "expert"
    assert trajectory[0]["done"] is True
    assert trajectory[0]["output"] == "expert done"
    assert [event["type"] for event in events] == ["thought", "action", "output"]
    assert events[-1]["payload"] == {"output": "expert done", "source": "expert"}


def test_expert_takeover_records_observation_and_calls_on_step():
    events, emit = _events()
    trajectory = []
    seen_steps = []
    expert = _ExpertLLM([{"tool": "read_file", "params": {"path": "a.txt"}}])

    result = run_expert_takeover(
        expert_llm=expert,
        steps=1,
        task="task",
        session_id="s1",
        trajectory=trajectory,
        context=lambda: "ctx",
        tools_description=lambda: "tools",
        emit=emit,
        execute_action=lambda session_id, tool, params: {"ok": True, "tool": tool, "content": "hello"},
        append_context=lambda text: None,
        on_step=lambda step, current: seen_steps.append((step, list(current))),
    )

    assert result.steps_executed == 1
    assert result.stopped_on_done is False
    assert trajectory[0]["action"]["tool"] == "read_file"
    assert trajectory[0]["observation"]["ok"] is True
    assert [event["type"] for event in events] == ["thought", "action", "tool_call", "observation"]
    assert events[-1]["payload"]["source"] == "expert"
    assert seen_steps[0][0] is trajectory[0]
    assert seen_steps[0][1] == trajectory


def test_expert_takeover_appends_failure_context_before_next_think():
    events, emit = _events()
    trajectory = []
    context_parts = ["base"]
    expert = _ExpertLLM([
        {"tool": "read_file", "params": {"path": "missing.txt"}},
        {"done": True, "output": "recovered"},
    ])

    def append_context(text):
        context_parts.append(text)

    result = run_expert_takeover(
        expert_llm=expert,
        steps=2,
        task="task",
        session_id="s1",
        trajectory=trajectory,
        context=lambda: "".join(context_parts),
        tools_description=lambda: "tools",
        emit=emit,
        execute_action=lambda session_id, tool, params: {"ok": False, "tool": tool, "error": "missing"},
        append_context=append_context,
    )

    assert result.steps_executed == 2
    assert result.stopped_on_done is True
    assert len(trajectory) == 2
    assert "missing" in context_parts[-1]
    assert "missing" in expert.think_contexts[1]
    assert [event["type"] for event in events] == [
        "thought",
        "action",
        "tool_call",
        "observation",
        "error",
        "thought",
        "action",
        "output",
    ]
