"""Lightweight deterministic validation for ReAct plan steps.

This is not a second planner. It turns each executed step into a small,
machine-readable verdict so the runtime and UI can see whether the last action
proved its own success, needs confirmation, or should be repaired.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List


def validate_plan_step(
    *,
    task: str,
    step: Dict[str, Any],
    trajectory: List[Dict[str, Any]],
) -> Dict[str, Any]:
    action = step.get("action") if isinstance(step.get("action"), dict) else {}
    observation = step.get("observation") if isinstance(step.get("observation"), dict) else {}
    tool = str(action.get("tool") or observation.get("tool") or "")
    iteration = step.get("iteration")

    issues: List[Dict[str, Any]] = []
    evidence: List[str] = []
    expected = _expected_evidence(tool, action)

    if not tool:
        issues.append(_issue("missing_tool", "No tool was selected for this step.", "Choose an executable tool."))

    if observation.get("ok") is True:
        evidence.append("observation.ok=true")
    else:
        issues.append(_issue(
            str(observation.get("failure_type") or observation.get("error_type") or "tool_failed"),
            str(observation.get("reason") or observation.get("error") or "Tool did not report success."),
            str(observation.get("suggested_next_step") or observation.get("suggested_fix") or "Repair or choose an alternative action before continuing."),
        ))

    if observation.get("failure_type") == "tool_validation":
        _add_once(
            issues,
            _issue(
                "tool_validation_failed",
                "Tool call failed local schema/name validation.",
                "Use suggested_next_step or one of alternatives, then retry.",
            ),
        )

    if observation.get("partial") is True or observation.get("error_type") == "tool_timeout":
        _add_once(
            issues,
            _issue(
                "partial_or_timeout",
                "The tool returned a partial or timeout observation.",
                "Inspect partial output or run a narrower verification before assuming success.",
            ),
        )

    if observation.get("idempotency_key"):
        evidence.append("idempotency_key")
        committed = observation.get("committed")
        if committed is True:
            evidence.append("committed=true")
        elif committed is False:
            issues.append(_issue("not_committed", "Side effect was not committed.", "Do not continue as if the write succeeded."))
        elif committed is None:
            issues.append(_issue("commit_unknown", "Side effect commit state is unknown.", "Run commit reconciliation or a direct state lookup."))

    repeat_count = _count_recent_repeats(action, trajectory)
    if repeat_count >= 2:
        issues.append(_issue(
            "repeated_action",
            "The same action and parameters repeated recently.",
            "Change the route, inspect evidence, or stop looping.",
        ))

    verdict = _verdict(issues)
    summary = _summary(verdict, tool, issues)
    return {
        "iteration": iteration,
        "tool": tool,
        "verdict": verdict,
        "summary": summary,
        "expected_evidence": expected,
        "evidence": evidence,
        "issues": issues,
        "next_check": _next_check(verdict, issues, tool),
    }


def summarize_plan_validation(trajectory: List[Dict[str, Any]]) -> Dict[str, Any]:
    reports = [
        step.get("plan_validation")
        for step in trajectory
        if isinstance(step.get("plan_validation"), dict)
    ]
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for report in reports:
        verdict = report.get("verdict")
        if verdict in counts:
            counts[verdict] += 1
    return {
        "step_count": len(reports),
        "counts": counts,
        "last": reports[-1] if reports else None,
    }


def _expected_evidence(tool: str, action: Dict[str, Any]) -> List[str]:
    params = action.get("params") if isinstance(action.get("params"), dict) else {}
    expected = ["observation.ok=true"]
    if tool in {"modify_file", "delete_file", "write_file", "git_commit"}:
        expected.append("committed=true or reconcile_status")
    if params.get("path"):
        expected.append(f"path={params.get('path')}")
    return expected


def _issue(code: str, message: str, suggested_fix: str) -> Dict[str, str]:
    return {"code": code, "message": message, "suggested_fix": suggested_fix}


def _add_once(issues: List[Dict[str, Any]], issue: Dict[str, Any]) -> None:
    if not any(existing.get("code") == issue.get("code") for existing in issues):
        issues.append(issue)


def _count_recent_repeats(action: Dict[str, Any], trajectory: List[Dict[str, Any]], window: int = 4) -> int:
    if not action:
        return 0
    try:
        signature = json.dumps(action, sort_keys=True, ensure_ascii=False)
    except TypeError:
        signature = str(action)
    count = 0
    for previous in trajectory[-window:]:
        previous_action = previous.get("action") if isinstance(previous.get("action"), dict) else {}
        try:
            previous_signature = json.dumps(previous_action, sort_keys=True, ensure_ascii=False)
        except TypeError:
            previous_signature = str(previous_action)
        if previous_signature == signature:
            count += 1
    return count


def _verdict(issues: List[Dict[str, Any]]) -> str:
    codes = {str(issue.get("code")) for issue in issues}
    if {"tool_validation_failed", "not_committed", "missing_tool"} & codes:
        return "fail"
    if any(code not in {"commit_unknown"} for code in codes):
        return "fail"
    if issues:
        return "warn"
    return "pass"


def _summary(verdict: str, tool: str, issues: List[Dict[str, Any]]) -> str:
    name = tool or "step"
    if verdict == "pass":
        return f"{name} produced acceptable evidence."
    first = issues[0] if issues else {}
    return f"{name} needs verification: {first.get('message', 'unknown issue')}"


def _next_check(verdict: str, issues: List[Dict[str, Any]], tool: str) -> str:
    if verdict == "pass":
        return "Continue to the next step."
    for issue in issues:
        fix = issue.get("suggested_fix")
        if fix:
            return str(fix)
    return f"Verify {tool or 'this step'} before continuing."
