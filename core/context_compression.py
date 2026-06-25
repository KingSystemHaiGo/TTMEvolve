"""Context compression for long ReAct trajectories.

Inspired by Abidingenuity's `memory.py` (running summary + per-turn structured
fact extraction). TTMEvolve keeps the trajectory verbatim until it exceeds a
threshold; then it produces a deterministic summary that preserves:

- The original task
- The current goal checklist status
- The latest plan validation verdict
- A bulleted timeline of major actions with their pass/fail outcome
- Tool-call counts

The summary is deterministic so it can be unit-tested without an LLM, and so
two runs with the same trajectory produce the same compressed context.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


COMPRESSION_VERSION = "context-compression.v1"

DEFAULT_VERBATIM_TURNS = 4
DEFAULT_SUMMARY_THRESHOLD = 8
DEFAULT_MAX_CONTEXT_TURNS = 20


def should_compress(
    trajectory: List[Dict[str, Any]],
    *,
    summary_threshold: int = DEFAULT_SUMMARY_THRESHOLD,
    max_turns: int = DEFAULT_MAX_CONTEXT_TURNS,
) -> bool:
    if len(trajectory) >= max_turns:
        return True
    return len(trajectory) >= summary_threshold


def compress_trajectory(
    trajectory: List[Dict[str, Any]],
    *,
    task: str = "",
    checklist: Optional[Dict[str, Any]] = None,
    plan: Optional[Dict[str, Any]] = None,
    verbatim_turns: int = DEFAULT_VERBATIM_TURNS,
    max_turns: int = DEFAULT_MAX_CONTEXT_TURNS,
) -> Dict[str, Any]:
    """Produce a compressed view of the trajectory.

    Returns:
        {
            "version": ...,
            "summary": "<deterministic text>",
            "verbatim_steps": [step, ...],
            "compressed_step_count": int,
            "skipped_step_count": int,
            "stats": {...},
        }
    """
    if not isinstance(trajectory, list):
        trajectory = []
    safe_verbatim = max(1, int(verbatim_turns))
    safe_max = max(safe_verbatim + 1, int(max_turns))

    truncated = trajectory[:safe_max]
    verbatim = truncated[-safe_verbatim:] if truncated else []
    older = truncated[: max(0, len(truncated) - safe_verbatim)]

    summary_text = _build_summary_text(
        task=task,
        checklist=checklist,
        plan=plan,
        older_steps=older,
        verbatim=verbatim,
    )
    stats = _stats(truncated)

    return {
        "version": COMPRESSION_VERSION,
        "summary": summary_text,
        "verbatim_steps": verbatim,
        "compressed_step_count": len(older),
        "skipped_step_count": max(0, len(trajectory) - safe_max),
        "stats": stats,
        "task": task,
    }


def render_compression_hint(compressed: Dict[str, Any], *, max_chars: int = 1200) -> str:
    """Render the compressed view as a compact context block for the next iteration."""
    summary = compressed.get("summary", "")
    if len(summary) > max_chars:
        summary = summary[: max_chars - 3] + "..."
    parts = [
        "\n[compressed_context]\n",
        f"# task\n{compressed.get('task') or '(no task)'}\n",
        f"# compressed_summary\n{summary}\n",
        f"# verbatim_recent_steps ({len(compressed.get('verbatim_steps') or [])} kept)\n",
    ]
    for step in (compressed.get("verbatim_steps") or [])[-4:]:
        action = step.get("action") if isinstance(step.get("action"), dict) else {}
        observation = step.get("observation") if isinstance(step.get("observation"), dict) else {}
        tool = action.get("tool") or observation.get("tool") or "?"
        ok = "ok" if observation.get("ok") else ("fail" if observation.get("ok") is False else "?")
        parts.append(f"- iter={step.get('iteration', '?')} tool={tool} {ok}\n")
    parts.append("[/compressed_context]\n")
    return "".join(parts)


def _stats(steps: List[Dict[str, Any]]) -> Dict[str, int]:
    tool_count: Dict[str, int] = {}
    pass_count = 0
    fail_count = 0
    for step in steps:
        action = step.get("action") if isinstance(step.get("action"), dict) else {}
        observation = step.get("observation") if isinstance(step.get("observation"), dict) else {}
        tool = str(action.get("tool") or observation.get("tool") or "")
        if tool:
            tool_count[tool] = tool_count.get(tool, 0) + 1
        if observation.get("ok") is True:
            pass_count += 1
        elif observation.get("ok") is False:
            fail_count += 1
    return {
        "step_count": len(steps),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "tool_count": tool_count,
    }


def _build_summary_text(
    *,
    task: str,
    checklist: Optional[Dict[str, Any]],
    plan: Optional[Dict[str, Any]],
    older_steps: List[Dict[str, Any]],
    verbatim: List[Dict[str, Any]],
) -> str:
    lines: List[str] = []
    if task:
        lines.append(f"Task: {task.strip()[:160]}")

    if isinstance(plan, dict) and plan.get("steps"):
        pending = [step for step in plan.get("steps", []) if step.get("status") in {"pending", "in_progress"}]
        lines.append(
            f"Plan: {plan.get('summary', '')[:120]} | "
            f"{len(plan.get('steps', []))} steps | "
            f"{len(pending)} open"
        )

    if isinstance(checklist, dict):
        overall = checklist.get("overall", "active")
        counts = checklist.get("counts") or {}
        lines.append(
            f"Goal: {overall} | done={counts.get('done', 0)} "
            f"warn={counts.get('warn', 0)} fail={counts.get('fail', 0)} "
            f"pending={counts.get('pending', 0)}"
        )

    if older_steps:
        lines.append(f"Earlier {len(older_steps)} compressed steps (highlights):")
        for step in _pick_highlights(older_steps, max_items=5):
            lines.append(f"  - {step}")

    if verbatim:
        last = verbatim[-1]
        action = last.get("action") if isinstance(last.get("action"), dict) else {}
        observation = last.get("observation") if isinstance(last.get("observation"), dict) else {}
        verdict = ""
        pv = observation.get("plan_validation") if isinstance(observation.get("plan_validation"), dict) else None
        if isinstance(pv, dict):
            verdict = f" | verdict={pv.get('verdict')}"
        lines.append(
            "Latest step: "
            f"iter={last.get('iteration', '?')} "
            f"tool={action.get('tool') or observation.get('tool') or '?'} "
            f"ok={observation.get('ok')}{verdict}"
        )

    return "\n".join(lines)


def _pick_highlights(steps: List[Dict[str, Any]], *, max_items: int = 5) -> List[str]:
    """Pick a few representative older steps to keep in the summary."""
    highlights: List[str] = []
    seen_tools: Dict[str, int] = {}
    for step in steps:
        action = step.get("action") if isinstance(step.get("action"), dict) else {}
        observation = step.get("observation") if isinstance(step.get("observation"), dict) else {}
        tool = str(action.get("tool") or observation.get("tool") or "?")
        seen_tools[tool] = seen_tools.get(tool, 0) + 1
        verdict = ""
        pv = observation.get("plan_validation") if isinstance(observation.get("plan_validation"), dict) else None
        if isinstance(pv, dict):
            verdict = f" verdict={pv.get('verdict')}"
        ok = "ok" if observation.get("ok") else ("fail" if observation.get("ok") is False else "?")
        highlights.append(f"i={step.get('iteration', '?')} tool={tool} {ok}{verdict}")
        if len(highlights) >= max_items:
            break
    if seen_tools:
        tool_summary = ", ".join(f"{name}×{count}" for name, count in sorted(seen_tools.items()))
        highlights.append(f"tool totals: {tool_summary}")
    return highlights


def extract_repeated_tool_warnings(trajectory: List[Dict[str, Any]], *, threshold: int = 3) -> List[str]:
    """Detect loops where the same tool is called many times back-to-back."""
    if len(trajectory) < threshold:
        return []
    warnings: List[str] = []
    streak_tool = None
    streak_count = 0
    streak_start = -1
    for step in trajectory:
        action = step.get("action") if isinstance(step.get("action"), dict) else {}
        tool = action.get("tool")
        if tool == streak_tool:
            streak_count += 1
            continue
        if streak_count >= threshold:
            warnings.append(
                f"Loop risk: tool '{streak_tool}' called {streak_count} times in a row "
                f"(starting at iteration {streak_start})."
            )
        streak_tool = tool
        streak_count = 1
        streak_start = step.get("iteration", -1)
    if streak_count >= threshold:
        warnings.append(
            f"Loop risk: tool '{streak_tool}' called {streak_count} times in a row "
            f"(starting at iteration {streak_start})."
        )
    return warnings


def extract_text_signals(text: str) -> List[str]:
    """Extract a few short signal words from a longer block (helper for summaries)."""
    if not text:
        return []
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    return [cleaned[:160]]