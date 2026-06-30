"""GoalLoop evidence builders.

GoalLoop state is reconstructed from append-only session events so HTTP
endpoints, Evidence Bundle, and external agents do not need live in-memory
loop state.
"""

from __future__ import annotations

from typing import Any, Dict, List


GOAL_LOOP_API_VERSION = "goal-loop-api.v1"

GOAL_EVENT_TYPES = {
    "goal_started",
    "goal_stage_started",
    "goal_stage_output",
    "goal_stage_review",
    "goal_stage_handoff",
    "goal_confirmation_requested",
    "goal_artifact_written",
    "goal_completed",
    "goal_blocked",
}


def goal_loop_from_server(server: Any, session_id: str, *, steps: int = 100) -> Dict[str, Any]:
    events = []
    try:
        events = server.session_store.get_events(session_id)
    except Exception:
        events = []
    return build_goal_loop_summary(session_id=session_id, events=events, steps=steps)


def build_goal_loop_summary(
    *,
    session_id: str,
    events: List[Dict[str, Any]],
    steps: int = 100,
) -> Dict[str, Any]:
    all_goal_events = [
        event for event in events
        if event.get("type") in GOAL_EVENT_TYPES
    ]
    recent_goal_events = all_goal_events[-steps:] if steps > 0 else list(all_goal_events)

    latest_goal: Dict[str, Any] = {}
    latest_by_stage: Dict[str, Dict[str, Any]] = {}
    confirmations: List[Dict[str, Any]] = []
    artifacts: List[Dict[str, Any]] = []
    terminal: Dict[str, Any] = {}

    for event in all_goal_events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        etype = event.get("type")
        if etype == "goal_started":
            latest_goal = {**payload, "timestamp": event.get("created_at")}
        elif etype in {"goal_completed", "goal_blocked"}:
            terminal = {**payload, "event": etype, "timestamp": event.get("created_at")}
            latest_goal = {**latest_goal, **payload}
        elif etype == "goal_confirmation_requested":
            confirmations.append({**payload, "timestamp": event.get("created_at")})
        elif etype == "goal_artifact_written":
            artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
            if artifact:
                artifacts.append({**artifact, "stage": payload.get("stage"), "timestamp": event.get("created_at")})
        elif etype and etype.startswith("goal_stage_"):
            stage = str(payload.get("stage") or "")
            if not stage:
                continue
            stage_run = payload.get("stage_run") if isinstance(payload.get("stage_run"), dict) else {}
            latest_by_stage[stage] = {
                "stage": stage,
                "event": etype,
                "status": stage_run.get("status"),
                "summary": (
                    stage_run.get("output", {}).get("summary")
                    if isinstance(stage_run.get("output"), dict)
                    else None
                ),
                "review": stage_run.get("review") if isinstance(stage_run.get("review"), dict) else {},
                "handoff": stage_run.get("handoff") if isinstance(stage_run.get("handoff"), dict) else {},
                "timestamp": event.get("created_at"),
            }

    stages = list(latest_by_stage.values())
    blocked = terminal.get("event") == "goal_blocked"
    completed = terminal.get("event") == "goal_completed"
    status = (
        "blocked" if blocked else
        "completed" if completed else
        "running" if all_goal_events else
        "not_started"
    )
    current_stage = (
        terminal.get("current_stage")
        or latest_goal.get("current_stage")
        or (stages[-1].get("stage") if stages else None)
    )
    counts = {
        "events": len(all_goal_events),
        "recent_events": len(recent_goal_events),
        "stages": len(stages),
        "confirmations": len(confirmations),
        "artifacts": len(artifacts),
    }
    return {
        "version": GOAL_LOOP_API_VERSION,
        "session_id": session_id,
        "status": status,
        "goal_id": latest_goal.get("goal_id"),
        "task": latest_goal.get("task"),
        "current_stage": current_stage,
        "progress": latest_goal.get("progress") if isinstance(latest_goal.get("progress"), dict) else {},
        "stages": stages,
        "latest_stage": stages[-1] if stages else None,
        "confirmations": confirmations,
        "latest_confirmation": confirmations[-1] if confirmations else None,
        "artifacts": artifacts,
        "terminal": terminal,
        "counts": counts,
        "recent_events": [
            {
                "type": event.get("type"),
                "timestamp": event.get("created_at"),
                "stage": (
                    event.get("payload", {}).get("stage")
                    if isinstance(event.get("payload"), dict)
                    else None
                ),
            }
            for event in recent_goal_events
        ],
    }
