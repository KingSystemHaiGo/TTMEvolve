"""Plan review — deterministic checks before a plan is approved.

Goals:
- Catch missing tools (unknown tool name)
- Detect cycles or orphan dependencies
- Surface risks like destructive file ops, missing evidence, or unbounded loops
- Provide a stable verdict so the UI can colour review cards (pass/warn/fail)
"""

from __future__ import annotations

from typing import Any, Dict, List, Set


KNOWN_TOOLS = {
    "modify_file", "write_file", "delete_file", "read_file", "list_files",
    "git_commit", "git_push", "git_status",
    "shell", "run_python",
    "search", "knowledge_lookup",
    "spawn_subagent", "loop_schedule",
    "maker_init", "maker_setup_status", "maker_tool_audit", "maker_repair",
}


DESTRUCTIVE_TOOLS = {"delete_file", "git_push", "shell"}


REVIEW_VERSION = "plan-review.v1"


def review_plan(plan: Dict[str, Any], known_tools: Set[str] = None) -> Dict[str, Any]:
    known = set(known_tools or KNOWN_TOOLS)
    issues: List[Dict[str, Any]] = []
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    seen_ids: Set[str] = set()
    edges: Dict[str, List[str]] = {}

    if not steps:
        issues.append(_issue("empty_plan", "Plan has no steps.", "Add at least one step before approval."))
    if not str(plan.get("summary") or "").strip():
        issues.append(_issue("missing_summary", "Plan summary is empty.", "Write a one-line plan summary."))

    for step in steps:
        step_id = step.get("id")
        tool = step.get("tool")
        if step_id in seen_ids:
            issues.append(_issue("duplicate_step", f"Duplicate step id '{step_id}'.", "Give every step a unique id."))
        seen_ids.add(step_id)
        if tool not in known:
            issues.append(_issue(
                "unknown_tool",
                f"Step '{step_id}' uses unknown tool '{tool}'.",
                "Pick a registered tool or remove the step.",
            ))
        if tool in DESTRUCTIVE_TOOLS:
            issues.append(_issue(
                "destructive_step",
                f"Step '{step_id}' uses destructive tool '{tool}'.",
                "Confirm the user has authorized this destructive action.",
            ))
        if not step.get("expected_evidence"):
            issues.append(_issue(
                "missing_expected_evidence",
                f"Step '{step_id}' has no expected_evidence.",
                "Describe how the agent should know the step succeeded.",
            ))
        deps = step.get("depends_on") or []
        if isinstance(deps, list):
            edges[step_id] = [str(item) for item in deps]
        else:
            edges[step_id] = []

    cycles = _find_cycles(edges)
    for cycle in cycles:
        issues.append(_issue(
            "dependency_cycle",
            f"Plan has a dependency cycle: {' -> '.join(cycle)}.",
            "Remove the circular dependency between these steps.",
        ))

    orphans = [step_id for step_id in edges if not edges.get(step_id)] if len(steps) > 1 else []
    if len(steps) > 4 and len(orphans) == len(steps):
        issues.append(_issue(
            "no_dependencies_declared",
            "Plan has many steps but no dependencies were declared.",
            "Declare depends_on to express step ordering.",
        ))

    verdict = _verdict(issues)
    return {
        "version": REVIEW_VERSION,
        "verdict": verdict,
        "summary": _summary(verdict, issues),
        "issues": issues,
        "step_count": len(steps),
    }


def _find_cycles(edges: Dict[str, List[str]]) -> List[List[str]]:
    cycles: List[List[str]] = []
    visited: Set[str] = set()
    path: List[str] = []
    path_set: Set[str] = set()

    def dfs(node: str) -> None:
        if node in path_set:
            cycle_start = path.index(node)
            cycles.append(path[cycle_start:] + [node])
            return
        if node in visited:
            return
        path.append(node)
        path_set.add(node)
        for child in edges.get(node, []):
            dfs(child)
        path.pop()
        path_set.remove(node)
        visited.add(node)

    for node in edges:
        dfs(node)
    return cycles


def _verdict(issues: List[Dict[str, Any]]) -> str:
    blocking = {"empty_plan", "duplicate_step", "unknown_tool", "dependency_cycle"}
    if any(issue.get("code") in blocking for issue in issues):
        return "fail"
    if issues:
        return "warn"
    return "pass"


def _summary(verdict: str, issues: List[Dict[str, Any]]) -> str:
    if verdict == "pass":
        return "Plan is internally consistent and ready to execute."
    if verdict == "warn":
        first = issues[0]
        return f"Plan has {len(issues)} note(s): {first.get('message', '')}"
    first = issues[0]
    return f"Plan cannot be approved: {first.get('message', '')}"


def _issue(code: str, message: str, suggested_fix: str) -> Dict[str, str]:
    return {"code": code, "message": message, "suggested_fix": suggested_fix}