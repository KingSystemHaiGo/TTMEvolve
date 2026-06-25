"""Integration test: Plan First end-to-end inside ReActLoop.

Uses monkeypatching instead of subclassing the abstract LLMInterface.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.react_loop import ReActLoop
from agent.tool_registry import ToolRegistry
from core.event_log import EventLog
from core.executor import Executor
from llm.interface import LLMInterface


class StubLLM:
    """Duck-typed stand-in for LLMInterface. Only implements what we need."""

    def __init__(self, plan_text: str, action_text: str) -> None:
        self.plan_text = plan_text
        self.action_text = action_text
        self.calls: List[str] = []

    def generate(self, prompt: str, max_tokens: int = 0) -> Any:
        class _Resp:
            text: str

        r = _Resp()
        self.calls.append(prompt)
        if "TTMEvolve's planner" in prompt:
            r.text = self.plan_text
        else:
            r.text = self.action_text
        return r


def _stub_think(loop: ReActLoop, stub: StubLLM) -> None:
    """Replace loop._run_iteration so we don't need a real LLMInterface."""
    def fake_run_iteration(i: int) -> Dict[str, Any]:
        return {
            "iteration": i,
            "thought": "x",
            "action": {"tool": "modify_file", "params": {"path": "a.txt"}},
            "done": i == 0,
            "output": "ok" if i == 0 else "",
        }
    loop._run_iteration = fake_run_iteration  # type: ignore[assignment]
    # also short-circuit _draft_plan_from_llm so it returns our canned plan
    from core.plan_format import normalize_plan
    parsed_plan = stub.plan_text  # already a JSON string
    import json
    plan_dict = json.loads(parsed_plan)
    loop._draft_plan_from_llm = lambda task: normalize_plan(plan_dict, task=task)  # type: ignore[assignment]


def make_loop(approval: bool) -> Any:
    plan_text = (
        '{"summary": "demo", "steps": ['
        '{"id": "s1", "tool": "modify_file", "params": {"path": "a.txt"}, '
        '"intent": "create", "expected_evidence": ["ok"]}'
        ']}'
    )
    stub = StubLLM(plan_text=plan_text, action_text="{}")
    tools = ToolRegistry(skills_dir=Path("./skills"))
    tools.register(
        name="modify_file",
        description="x",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
        handler=lambda **kw: {"ok": True, "tool": "modify_file", "idempotency_key": "k", "committed": True},
        source="test",
    )
    events: List[Dict[str, Any]] = []

    def sink(event: Dict[str, Any]) -> None:
        events.append(event)

    def approval_provider(plan: Dict[str, Any]) -> bool:
        return approval

    loop = ReActLoop(
        llm=stub,  # type: ignore[arg-type]
        tools=tools,
        executor=Executor.__new__(Executor),  # bypass __init__
        event_log=EventLog(Path(".")),
        max_iterations=2,
        event_sink=sink,
        plan_first_enabled=True,
        plan_approval_provider=approval_provider,
    )
    _stub_think(loop, stub)
    return loop, events


def test_plan_first_emits_draft_and_blocks_until_approval():
    loop, events = make_loop(approval=True)
    result = loop.run(task="create a file")
    assert result.get("plan"), "result should include plan when plan_first is enabled"
    types = [e["type"] for e in events]
    assert "plan_draft" in types
    assert "plan_first_phase" in types


def test_plan_first_returns_early_when_rejected():
    loop, events = make_loop(approval=False)
    result = loop.run(task="create a file")
    assert result.get("plan_first_phase") == "not_approved"
    types = [e["type"] for e in events]
    assert "tool_call" not in types


def test_plan_first_disabled_skips_phase():
    plan_text = '{"summary": "demo", "steps": []}'
    stub = StubLLM(plan_text=plan_text, action_text="{}")
    tools = ToolRegistry(skills_dir=Path("./skills"))
    tools.register(
        name="modify_file",
        description="x",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
        handler=lambda **kw: {"ok": True, "tool": "modify_file", "idempotency_key": "k", "committed": True},
        source="test",
    )
    events: List[Dict[str, Any]] = []

    def sink(event: Dict[str, Any]) -> None:
        events.append(event)

    loop = ReActLoop(
        llm=stub,  # type: ignore[arg-type]
        tools=tools,
        executor=Executor.__new__(Executor),
        event_log=EventLog(Path(".")),
        max_iterations=1,
        event_sink=sink,
        plan_first_enabled=False,
    )
    _stub_think(loop, stub)
    loop.run(task="do something")
    types = [e["type"] for e in events]
    assert "plan_draft" not in types


def test_plan_first_includes_plan_in_result_when_approved():
    loop, _ = make_loop(approval=True)
    result = loop.run(task="create a file")
    assert "plan" in result
    assert "plan_review" in result
    assert "plan_progress" in result
    assert result["plan"].get("approved") is True