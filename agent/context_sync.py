"""Context sync and continuation checkpoint builders for ReAct."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

from core.context_compression import compress_trajectory, should_compress


def build_context_sync_snapshot(
    *,
    session_id: str,
    task: str,
    iteration: int,
    trajectory: List[Dict[str, Any]],
    goal_checklist: Dict[str, Any],
    plan: Dict[str, Any],
    latest_skill_sync: Dict[str, Any],
    context_revision: int,
) -> Dict[str, Any]:
    last_step = latest_actionable_step(trajectory)
    action = last_step.get("action") if isinstance(last_step.get("action"), dict) else {}
    observation = last_step.get("observation") if isinstance(last_step.get("observation"), dict) else {}
    plan_validation = (
        last_step.get("plan_validation")
        if isinstance(last_step.get("plan_validation"), dict)
        else {}
    )
    skill_sync = latest_skill_sync if isinstance(latest_skill_sync, dict) else {}
    artifacts = collect_artifact_refs(trajectory, limit=8)
    params = action.get("params") if isinstance(action.get("params"), dict) else {}
    checkpoint = build_continuation_checkpoint(
        session_id=session_id,
        task=task,
        iteration=iteration,
        trajectory=trajectory,
        goal_checklist=goal_checklist,
        plan=plan,
        context_revision=context_revision,
        last_step=last_step,
        artifacts=artifacts,
        skill_sync=skill_sync,
    )
    return {
        "session_id": session_id,
        "task": task,
        "iteration": iteration,
        "trajectory_steps": len(trajectory),
        "workspace_profile": checkpoint.get("workspace_profile", "general"),
        "last_tool": action.get("tool") or observation.get("tool"),
        "last_action": {
            "tool": action.get("tool"),
            "params_keys": sorted(params.keys()),
            "done": bool(action.get("done")),
        },
        "plan_validation": {
            "verdict": plan_validation.get("verdict"),
            "summary": plan_validation.get("summary"),
            "next_check": plan_validation.get("next_check"),
            "issues_count": len(plan_validation.get("issues") or []),
        },
        "goal_checklist": {
            "overall": goal_checklist.get("overall"),
            "counts": goal_checklist.get("counts", {}),
            "next_focus": goal_checklist.get("next_focus"),
        },
        "commit_state": commit_state_from_observation(observation),
        "skill_sync": {
            "ok": skill_sync.get("ok"),
            "state": skill_sync.get("state"),
            "signature": skill_sync.get("signature"),
            "compatibility_status": skill_sync.get("compatibility_status"),
            "changed": bool(skill_sync.get("changed")),
        },
        "artifact_refs": artifacts,
        "artifact_count": len(artifacts),
        "continuation_checkpoint": checkpoint,
    }


def build_continuation_checkpoint(
    *,
    session_id: str,
    task: str,
    iteration: int,
    trajectory: List[Dict[str, Any]],
    goal_checklist: Dict[str, Any],
    plan: Dict[str, Any],
    context_revision: int,
    last_step: Dict[str, Any],
    artifacts: List[Dict[str, Any]],
    skill_sync: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a durable handoff point, not full process resurrection."""
    action = last_step.get("action") if isinstance(last_step.get("action"), dict) else {}
    observation = last_step.get("observation") if isinstance(last_step.get("observation"), dict) else {}
    plan_validation = (
        last_step.get("plan_validation")
        if isinstance(last_step.get("plan_validation"), dict)
        else {}
    )
    budget_stats = (
        last_step.get("budget_stats")
        if isinstance(last_step.get("budget_stats"), dict)
        else {}
    )
    workspace_profile = str(budget_stats.get("workspace_profile") or "general")
    compressed = compress_trajectory(
        trajectory,
        task=task,
        checklist=goal_checklist,
        plan=plan,
        verbatim_turns=4,
        max_turns=20,
    )
    return {
        "version": "continuation-checkpoint.v1",
        "session_id": session_id,
        "context_revision": context_revision + 1,
        "iteration": iteration,
        "trajectory_steps": len(trajectory),
        "workspace_profile": workspace_profile,
        "resume_mode": "context_handoff",
        "resume_ready": True,
        "resume_limits": {
            "process_resurrection": False,
            "requires_runtime_replay": False,
            "raw_sse_replay_required": False,
        },
        "open_plan_steps": open_plan_steps(plan, limit=6),
        "goal_overall": goal_checklist.get("overall"),
        "goal_next_focus": goal_checklist.get("next_focus"),
        "last_tool": action.get("tool") or observation.get("tool"),
        "last_ok": observation.get("ok"),
        "plan_verdict": plan_validation.get("verdict"),
        "artifact_refs": artifacts[:6],
        "artifact_count": len(artifacts),
        "skill_sync": {
            "state": skill_sync.get("state"),
            "compatibility_status": skill_sync.get("compatibility_status"),
            "changed": bool(skill_sync.get("changed")),
        },
        "compression": {
            "needed": should_compress(trajectory),
            "version": compressed.get("version"),
            "compressed_step_count": compressed.get("compressed_step_count", 0),
            "skipped_step_count": compressed.get("skipped_step_count", 0),
            "verbatim_step_count": len(compressed.get("verbatim_steps") or []),
            "stats": compressed.get("stats", {}),
            "summary": compressed.get("summary", "")[:1200],
        },
        "handoff_hint": (
            "Continue from this checkpoint using task, open_plan_steps, "
            "goal_next_focus, last_tool/last_ok, artifact_refs, and compression.summary. "
            "Use context_sync/runtime_metrics instead of raw SSE unless details are missing."
        ),
    }


def context_sync_signature(snapshot: Dict[str, Any]) -> str:
    encoded = json.dumps(snapshot_for_signature(snapshot), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def snapshot_for_signature(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    stable = json.loads(json.dumps(snapshot, ensure_ascii=False, default=str))
    checkpoint = stable.get("continuation_checkpoint")
    if isinstance(checkpoint, dict):
        checkpoint.pop("context_revision", None)
    return stable


def context_sync_diff_keys(previous: Dict[str, Any], current: Dict[str, Any]) -> List[str]:
    if not previous:
        return sorted(current.keys())
    return sorted(
        key for key in current.keys()
        if previous.get(key) != current.get(key)
    )


def open_plan_steps(plan: Dict[str, Any], limit: int = 6) -> List[Dict[str, Any]]:
    steps = plan.get("steps") if isinstance(plan, dict) else []
    if not isinstance(steps, list):
        return []
    open_steps: List[Dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        status = step.get("status")
        if status not in {"pending", "in_progress"}:
            continue
        open_steps.append({
            "id": step.get("id"),
            "title": step.get("title") or step.get("step") or step.get("description"),
            "status": status,
            "tool": step.get("tool"),
        })
        if len(open_steps) >= limit:
            break
    return open_steps


def latest_actionable_step(trajectory: List[Dict[str, Any]]) -> Dict[str, Any]:
    for step in reversed(trajectory):
        action = step.get("action")
        observation = step.get("observation")
        if isinstance(observation, dict):
            return step
        if isinstance(action, dict) and action.get("tool"):
            return step
    return trajectory[-1] if trajectory else {}


def collect_artifact_refs(trajectory: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    refs: List[Dict[str, Any]] = []
    seen = set()
    for step in reversed(trajectory[-8:]):
        action = step.get("action") if isinstance(step.get("action"), dict) else {}
        observation = step.get("observation")
        if not isinstance(observation, dict):
            continue
        ref = artifact_ref_from_step(action, observation)
        if not ref:
            continue
        key = json.dumps(ref, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
        if len(refs) >= limit:
            break
    refs.reverse()
    return refs


def artifact_ref_from_step(action: Dict[str, Any], observation: Dict[str, Any]) -> Dict[str, Any]:
    params = action.get("params") if isinstance(action.get("params"), dict) else {}
    ref = {
        key: observation.get(key) if observation.get(key) not in (None, "") else params.get(key)
        for key in [
            "path",
            "url",
            "remote_id",
            "task_id",
            "file_id",
            "asset_id",
            "resource_id",
            "idempotency_key",
            "output_path",
        ]
        if (observation.get(key) if observation.get(key) not in (None, "") else params.get(key)) not in (None, "")
    }
    tool = observation.get("tool") or action.get("tool")
    if tool:
        ref["tool"] = tool
    if observation.get("committed") is not None:
        ref["committed"] = observation.get("committed")
    return ref


def commit_state_from_observation(observation: Dict[str, Any]) -> Dict[str, Any]:
    if not observation:
        return {}
    if observation.get("committed") is None and not observation.get("idempotency_key"):
        return {}
    return {
        "tool": observation.get("tool"),
        "idempotency_key": observation.get("idempotency_key"),
        "committed": observation.get("committed"),
        "observed_at": observation.get("observed_at"),
        "reconcile_status": observation.get("reconcile_status"),
        "remote_lookup_tool": observation.get("remote_lookup_tool"),
        "remote_lookup_attempts": observation.get("remote_lookup_attempts"),
    }
