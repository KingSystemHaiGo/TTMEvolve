"""Tests for Plan First: plan_format + plan_review + plan_prompt + phase runner."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.plan_first import (
    build_plan_first_result,
    draft_plan_from_llm,
    known_tool_names,
    run_plan_first_phase,
)
from core.plan_format import (
    empty_plan,
    normalize_plan,
    plan_progress,
    plan_to_context_block,
    update_step_status,
)
from core.plan_prompt import build_plan_prompt, extract_plan_from_llm_text
from core.plan_review import KNOWN_TOOLS, review_plan


# ---------- plan_format ----------


def test_empty_plan_has_required_fields():
    plan = empty_plan("do something")
    assert plan["task"] == "do something"
    assert plan["status"] == "draft"
    assert plan["approved"] is False
    assert plan["steps"] == []


def test_normalize_plan_filters_invalid_steps():
    raw = {
        "summary": "two steps",
        "assumptions": ["a1"],
        "steps": [
            {"id": "s1", "tool": "modify_file", "params": {"path": "a.txt"}, "expected_evidence": ["ok"]},
            {"tool": ""},  # missing tool -> dropped
            {"id": "s2", "tool": "shell", "params": {}, "intent": "run"},
            "garbage",  # not a dict -> dropped
        ],
    }
    plan = normalize_plan(raw, task="x")
    assert plan["summary"] == "two steps"
    assert plan["assumptions"] == ["a1"]
    assert len(plan["steps"]) == 2
    assert plan["steps"][0]["id"] == "s1"


def test_plan_to_context_block_includes_step_intent():
    plan = normalize_plan(
        {
            "summary": "demo",
            "steps": [
                {"id": "s1", "tool": "modify_file", "params": {"path": "a.txt"}, "intent": "create", "expected_evidence": ["ok"]}
            ]
        },
        task="t",
    )
    block = plan_to_context_block(plan)
    assert "approved_plan" in block
    assert "modify_file" in block
    assert "create" in block


def test_update_step_status_changes_only_target():
    plan = normalize_plan(
        {
            "steps": [
                {"id": "s1", "tool": "modify_file", "params": {}, "expected_evidence": ["ok"]},
                {"id": "s2", "tool": "shell", "params": {}, "expected_evidence": ["ok"]},
            ]
        },
        task="t",
    )
    new_plan = update_step_status(plan, "s1", "done", note="ok")
    statuses = {s["id"]: s["status"] for s in new_plan["steps"]}
    assert statuses["s1"] == "done"
    assert statuses["s2"] == "pending"
    assert "ok" in new_plan["steps"][0]["notes"]
    # Original plan must remain untouched (immutability).
    assert plan["steps"][0]["status"] == "pending"


def test_plan_progress_counts():
    plan = normalize_plan(
        {
            "steps": [
                {"id": "s1", "tool": "modify_file", "params": {}, "expected_evidence": ["ok"]},
                {"id": "s2", "tool": "shell", "params": {}, "expected_evidence": ["ok"]},
            ]
        },
        task="t",
    )
    new_plan = update_step_status(plan, "s1", "done")
    progress = plan_progress(new_plan)
    assert progress["counts"]["done"] == 1
    assert progress["counts"]["pending"] == 1
    assert progress["current_step"] == "s2"


# ---------- plan_review ----------


def test_review_passes_for_valid_plan():
    plan = normalize_plan(
        {
            "summary": "ok",
            "steps": [
                {"id": "s1", "tool": "modify_file", "params": {}, "expected_evidence": ["ok"], "depends_on": []},
                {"id": "s2", "tool": "read_file", "params": {}, "expected_evidence": ["ok"], "depends_on": ["s1"]},
            ]
        },
        task="t",
    )
    review = review_plan(plan)
    assert review["verdict"] == "pass"


def test_review_fails_for_unknown_tool():
    plan = normalize_plan(
        {
            "summary": "x",
            "steps": [
                {"id": "s1", "tool": "nuke_everything", "params": {}, "expected_evidence": ["ok"]}
            ]
        },
        task="t",
    )
    review = review_plan(plan)
    codes = {issue["code"] for issue in review["issues"]}
    assert "unknown_tool" in codes
    assert review["verdict"] == "fail"


def test_review_detects_dependency_cycle():
    plan = normalize_plan(
        {
            "summary": "cycle",
            "steps": [
                {"id": "s1", "tool": "read_file", "params": {}, "expected_evidence": ["ok"], "depends_on": ["s2"]},
                {"id": "s2", "tool": "read_file", "params": {}, "expected_evidence": ["ok"], "depends_on": ["s1"]},
            ]
        },
        task="t",
    )
    review = review_plan(plan)
    codes = {issue["code"] for issue in review["issues"]}
    assert "dependency_cycle" in codes


def test_review_warns_about_destructive_steps():
    plan = normalize_plan(
        {
            "summary": "x",
            "steps": [
                {"id": "s1", "tool": "delete_file", "params": {}, "expected_evidence": ["committed"]}
            ]
        },
        task="t",
    )
    review = review_plan(plan)
    codes = {issue["code"] for issue in review["issues"]}
    assert "destructive_step" in codes
    assert review["verdict"] == "warn"


def test_review_fails_on_empty_plan():
    review = review_plan(empty_plan("t"))
    assert review["verdict"] == "fail"
    assert any(issue["code"] == "empty_plan" for issue in review["issues"])


# ---------- plan_prompt ----------


def test_build_plan_prompt_contains_task_and_tools():
    prompt = build_plan_prompt(
        task="create a file",
        context="user is on Windows",
        runtime_hints={"sandbox": "embedded"},
        tool_list=["modify_file", "shell"],
    )
    assert "create a file" in prompt
    assert "modify_file" in prompt
    assert "shell" in prompt
    assert "expected_evidence" in prompt


def test_extract_plan_from_llm_text_parses_json_object():
    text = 'Here is the plan:\n{"summary": "x", "steps": []}\nDone.'
    plan = extract_plan_from_llm_text(text)
    assert plan == {"summary": "x", "steps": []}


def test_extract_plan_from_llm_text_returns_none_for_garbage():
    assert extract_plan_from_llm_text("no json here") is None
    assert extract_plan_from_llm_text("") is None


def test_known_tools_includes_maker_faults():
    assert "maker_setup_status" in KNOWN_TOOLS
    assert "maker_repair" in KNOWN_TOOLS


# ---------- agent.plan_first ----------


class _Response:
    def __init__(self, text: str) -> None:
        self.text = text


class _LLM:
    def __init__(self, text: str) -> None:
        self.text = text
        self.prompts: List[str] = []

    def generate(self, prompt: str, max_tokens: int = 0) -> _Response:
        self.prompts.append(prompt)
        return _Response(self.text)


class _Tool:
    def __init__(self, name: str) -> None:
        self.name = name


class _Tools:
    def __init__(self, tools: List[Any] | None = None, fail: bool = False) -> None:
        self.tools = tools or [
            {"name": "modify_file"},
            _Tool("read_file"),
        ]
        self.fail = fail

    def list_tools(self) -> List[Any]:
        if self.fail:
            raise RuntimeError("tool listing failed")
        return self.tools


def _plan_text(tool: str = "modify_file") -> str:
    return (
        '{"summary": "edit safely", "steps": ['
        '{"id": "s1", "tool": "' + tool + '", "params": {"path": "a.txt"}, '
        '"intent": "edit", "expected_evidence": ["file changed"]}'
        ']}'
    )


def _events() -> tuple[List[Dict[str, Any]], Any]:
    events: List[Dict[str, Any]] = []

    def emit(session_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        events.append({"session_id": session_id, "type": event_type, "payload": payload})

    return events, emit


def test_run_plan_first_phase_approves_reviewed_plan():
    events, emit = _events()
    result = run_plan_first_phase(
        llm=_LLM(_plan_text()),
        tools=_Tools(),
        task="edit a file",
        context="context",
        session_id="s1",
        emit=emit,
        approval_provider=lambda plan: True,
    )

    assert result.approved is True
    assert result.plan["approved"] is True
    assert result.plan["status"] == "approved"
    assert result.review["verdict"] == "pass"
    assert [event["type"] for event in events] == ["plan_first_phase", "plan_draft"]


def test_run_plan_first_phase_auto_rejects_failed_review():
    events, emit = _events()
    result = run_plan_first_phase(
        llm=_LLM(_plan_text(tool="missing_tool")),
        tools=_Tools(),
        task="edit a file",
        context="context",
        session_id="s1",
        emit=emit,
        approval_provider=lambda plan: True,
    )

    assert result.approved is False
    assert result.review["verdict"] == "fail"
    assert events[-1]["type"] == "plan_first_phase"
    assert events[-1]["payload"]["phase"] == "auto_rejected"


def test_draft_plan_from_llm_emits_parse_failure_and_returns_empty_plan():
    events, emit = _events()
    plan = draft_plan_from_llm(
        llm=_LLM("not json"),
        tools=_Tools(),
        task="unclear task",
        context="context",
        session_id="s1",
        emit=emit,
    )

    assert plan["task"] == "unclear task"
    assert plan["steps"] == []
    assert events == [{
        "session_id": "s1",
        "type": "plan_draft_parse_failed",
        "payload": {"raw_excerpt": "not json"},
    }]


def test_known_tool_names_tolerates_list_failure_and_objects():
    assert known_tool_names(_Tools()) == ["modify_file", "read_file"]
    assert known_tool_names(_Tools(fail=True)) == []


def test_build_plan_first_result_keeps_public_shape():
    result = build_plan_first_result(
        session_id="s1",
        task="task",
        plan={"steps": [], "approved": False},
        review={"verdict": "warn"},
        reason="not_approved",
    )

    assert result["session_id"] == "s1"
    assert result["done"] is False
    assert result["trajectory"] == []
    assert result["plan_review"]["verdict"] == "warn"
    assert result["plan_first_phase"] == "not_approved"
