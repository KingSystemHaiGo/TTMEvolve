from agent.rescue_application import append_direct_action_rescue_step
from agent.rescue_orchestrator import RescueOrchestrator
from core.config import Config
from llm.expert_protocol import RescueAction


def test_append_direct_action_rescue_step_keeps_stable_shape():
    trajectory = [{"iteration": 0, "source": "local"}]
    action = {"tool": "read_file", "params": {"path": "exists.txt"}}
    observation = {"ok": True, "content": "hello"}

    step = append_direct_action_rescue_step(
        trajectory=trajectory,
        action=action,
        observation=observation,
        thought="read existing file",
        timestamp=123.5,
    )

    assert step is trajectory[-1]
    assert step == {
        "iteration": 1,
        "timestamp": 123.5,
        "source": "expert",
        "thought": "read existing file",
        "action": action,
        "observation": observation,
    }


def test_rescue_orchestrator_direct_action_uses_append_helper_shape():
    class DummyReact:
        def __init__(self):
            self.trajectory = []
            self.injected_actions = []

        def inject_expert_action(self, action):
            self.injected_actions.append(action)
            return {"ok": True, "tool": action.get("tool"), "result": "done"}

    cfg = Config()
    cfg.data = {"rescue": {"max_rescue_per_session": 1, "cooldown_seconds": 0}}
    cfg._profiles = {}
    react = DummyReact()
    orchestrator = RescueOrchestrator(
        react_loop=react,
        expert_rescuer=object(),
        trigger=object(),
        distiller=None,
        health=None,
        config=cfg,
    )
    action = {"tool": "read_file", "params": {"path": "exists.txt"}}

    orchestrator._apply_rescue(RescueAction(
        mode="direct_action",
        thought="read existing file",
        action=action,
    ))

    assert react.injected_actions == [action]
    assert len(react.trajectory) == 1
    step = react.trajectory[0]
    assert step["iteration"] == 0
    assert step["source"] == "expert"
    assert step["thought"] == "read existing file"
    assert step["action"] == action
    assert step["observation"]["ok"] is True
    assert step["observation"]["tool"] == "read_file"
