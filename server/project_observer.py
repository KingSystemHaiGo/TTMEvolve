"""Bus-backed project management observer.

The observer turns live RuntimeEventBus session events into a compact project
control snapshot: next focus, plan/goal state, latest tool, artifacts, risks,
and continuation readiness. It is intentionally derived from public bus events
instead of ReActLoop private state.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from core.runtime_events import RuntimeEventBus


class ProjectManagementObserver:
    """Maintain session-level project control snapshots from bus events."""

    def __init__(self, bus: RuntimeEventBus):
        self.bus = bus
        self._lock = threading.RLock()
        self._snapshots: Dict[str, Dict[str, Any]] = {}
        self._event_count = 0
        self._unsubscribe = bus.subscribe(self._handle_event, channel="session", replay=True)

    def close(self) -> None:
        self._unsubscribe()

    def snapshot(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            snapshot = dict(self._snapshots.get(session_id, {}))
        if not snapshot:
            return {
                "status": "missing",
                "source": "runtime_event_bus_project_observer",
                "session_id": session_id,
                "next_action": "Wait for context_sync or project events before deriving project state.",
            }
        return snapshot

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "status": "ready",
                "source": "runtime_event_bus_project_observer",
                "observed_event_count": self._event_count,
                "observed_session_count": len(self._snapshots),
            }

    def _handle_event(self, event: Dict[str, Any]) -> None:
        update = project_update_from_event(event)
        if update is None:
            return
        session_id = str(event.get("session_id") or "")
        if not session_id:
            return
        with self._lock:
            current = dict(self._snapshots.get(session_id, {}))
            merged = merge_project_snapshot(current, update)
            merged["status"] = "ready"
            merged["source"] = "runtime_event_bus_project_observer"
            merged["session_id"] = session_id
            self._snapshots[session_id] = merged
            self._event_count += 1


def project_update_from_event(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    event_type = event.get("type")
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    meta = event.get("meta") if isinstance(event.get("meta"), dict) else {}
    timestamp = meta.get("timestamp") or event.get("created_at")

    if event_type == "context_sync":
        snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else {}
        checkpoint = (
            snapshot.get("continuation_checkpoint")
            if isinstance(snapshot.get("continuation_checkpoint"), dict)
            else {}
        )
        goal = snapshot.get("goal_checklist") if isinstance(snapshot.get("goal_checklist"), dict) else {}
        plan = snapshot.get("plan_validation") if isinstance(snapshot.get("plan_validation"), dict) else {}
        update = {
            "task": snapshot.get("task"),
            "workspace_profile": snapshot.get("workspace_profile") or checkpoint.get("workspace_profile"),
            "iteration": snapshot.get("iteration"),
            "trajectory_steps": snapshot.get("trajectory_steps"),
            "last_tool": snapshot.get("last_tool") or checkpoint.get("last_tool"),
            "goal_overall": goal.get("overall") or checkpoint.get("goal_overall"),
            "goal_counts": goal.get("counts") if isinstance(goal.get("counts"), dict) else {},
            "next_focus": goal.get("next_focus") or checkpoint.get("goal_next_focus"),
            "plan_verdict": plan.get("verdict") or checkpoint.get("plan_verdict"),
            "plan_summary": plan.get("summary"),
            "plan_issues_count": plan.get("issues_count"),
            "continuation": {
                "status": "ready" if checkpoint.get("resume_ready") else "partial",
                "resume_ready": checkpoint.get("resume_ready"),
                "resume_mode": checkpoint.get("resume_mode"),
                "open_plan_steps": checkpoint.get("open_plan_steps") if isinstance(checkpoint.get("open_plan_steps"), list) else [],
                "artifact_count": checkpoint.get("artifact_count") or snapshot.get("artifact_count", 0),
                "artifact_refs": checkpoint.get("artifact_refs") if isinstance(checkpoint.get("artifact_refs"), list) else [],
                "compression_needed": (checkpoint.get("compression") or {}).get("needed")
                    if isinstance(checkpoint.get("compression"), dict)
                    else None,
            },
            "latest_event": "context_sync",
            "updated_at": timestamp,
        }
        update["risk_flags"] = project_risk_flags(update)
        update["next_action"] = project_next_action(update)
        return update

    if event_type == "goal_checklist":
        update = {
            "goal_overall": payload.get("overall"),
            "goal_counts": payload.get("counts") if isinstance(payload.get("counts"), dict) else {},
            "next_focus": payload.get("next_focus"),
            "latest_event": "goal_checklist",
            "updated_at": timestamp,
        }
        update["risk_flags"] = project_risk_flags(update)
        update["next_action"] = project_next_action(update)
        return update

    if event_type == "plan_validation":
        update = {
            "plan_verdict": payload.get("verdict"),
            "plan_summary": payload.get("summary"),
            "plan_issues_count": len(payload.get("issues") or []) if isinstance(payload.get("issues"), list) else None,
            "latest_event": "plan_validation",
            "updated_at": timestamp,
        }
        update["risk_flags"] = project_risk_flags(update)
        update["next_action"] = project_next_action(update)
        return update

    if event_type == "action":
        action = payload.get("action") if isinstance(payload.get("action"), dict) else {}
        if action.get("tool"):
            return {
                "last_tool": action.get("tool"),
                "latest_event": "action",
                "updated_at": timestamp,
            }

    if event_type == "status":
        message = payload.get("message")
        done = bool(payload.get("done"))
        canceled = bool(payload.get("canceled"))
        return {
            "runtime_status": "canceled" if canceled else ("done" if done else "running"),
            "status_message": message,
            "latest_event": "status",
            "updated_at": timestamp,
        }

    if event_type == "commit_reconcile":
        return {
            "last_commit_status": payload.get("status"),
            "latest_event": "commit_reconcile",
            "updated_at": timestamp,
        }

    return None


def merge_project_snapshot(current: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(current)
    for key, value in update.items():
        if value is None:
            continue
        if key == "risk_flags":
            merged[key] = sorted(set((merged.get(key) or []) + value))
        else:
            merged[key] = value
    merged["risk_flags"] = sorted(set(project_risk_flags(merged) + (merged.get("risk_flags") or [])))
    merged["next_action"] = project_next_action(merged)
    return merged


def project_risk_flags(snapshot: Dict[str, Any]) -> List[str]:
    flags: List[str] = []
    if snapshot.get("plan_verdict") in {"warn", "fail"}:
        flags.append(f"plan_{snapshot.get('plan_verdict')}")
    if snapshot.get("goal_overall") in {"warn", "fail"}:
        flags.append(f"goal_{snapshot.get('goal_overall')}")
    continuation = snapshot.get("continuation") if isinstance(snapshot.get("continuation"), dict) else {}
    if continuation and not continuation.get("resume_ready"):
        flags.append("continuation_not_ready")
    if continuation.get("compression_needed"):
        flags.append("compression_needed")
    if not snapshot.get("next_focus") and not continuation.get("open_plan_steps"):
        flags.append("next_focus_missing")
    return flags


def project_next_action(snapshot: Dict[str, Any]) -> str:
    if snapshot.get("plan_verdict") == "fail":
        return "Fix plan validation failures before taking more side effects."
    if snapshot.get("goal_overall") == "fail":
        return "Resolve failing goal criteria before continuing."
    if snapshot.get("next_focus"):
        return str(snapshot["next_focus"])
    continuation = snapshot.get("continuation") if isinstance(snapshot.get("continuation"), dict) else {}
    open_steps = continuation.get("open_plan_steps") if isinstance(continuation.get("open_plan_steps"), list) else []
    if open_steps:
        first = open_steps[0]
        if isinstance(first, dict):
            return str(first.get("title") or first.get("id") or "Continue the next open plan step.")
    if snapshot.get("last_tool"):
        return f"Verify result after {snapshot.get('last_tool')}."
    return "Wait for context_sync before deriving the next project action."
