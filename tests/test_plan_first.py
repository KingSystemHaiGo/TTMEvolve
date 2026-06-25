"""Tests for Plan First: plan_format + plan_review + plan_prompt."""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

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
            {"tool": ""},  # missing tool → dropped
            {"id": "s2", "tool": "shell", "params": {}, "intent": "run"},
            "garbage",  # not a dict → dropped
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
    update_step_status(plan, "s1", "done", note="ok")
    statuses = {s["id"]: s["status"] for s in plan["steps"]}
    assert statuses["s1"] == "done"
    assert statuses["s2"] == "pending"
    assert "ok" in plan["steps"][0]["notes"]


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
    update_step_status(plan, "s1", "done")
    progress = plan_progress(plan)
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
                {"id": "s1", "tool": "shell", "params": {}, "expected_evidence": ["ok"], "depends_on": ["s2"]},
                {"id": "s2", "tool": "shell", "params": {}, "expected_evidence": ["ok"], "depends_on": ["s1"]},
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