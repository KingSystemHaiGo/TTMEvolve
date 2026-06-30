"""Session route payload builders for AppServer.

This module keeps session/history/evidence response assembly out of the HTTP
handler. AppServer should decide transport details; this module decides the
shape of session API payloads.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from server.evidence_bundle import (
    build_runtime_advice,
    build_session_evidence_bundle,
    engineering_control_from_server,
    layer_control_from_server,
    layer_health_from_server,
    learning_job_from_server,
    project_state_from_server,
    resume_drill_from_server,
    runtime_metrics_from_server,
    summarize_runtime_metrics,
)
from server.goal_loop_api import goal_loop_from_server
from server.project_writeback import (
    apply_project_writeback_plan,
    build_project_writeback_plan,
    compact_project_writeback,
)


def parse_step_limit(
    params: Mapping[str, list[str]],
    *,
    default: int,
    maximum: int,
    minimum: int = 1,
) -> int:
    """Parse steps/limit query params with safe bounds."""
    try:
        value = int((params.get("steps") or params.get("limit") or [str(default)])[0])
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


class SessionRouteApi:
    """Build payloads for `/sessions/*` AppServer routes."""

    def __init__(self, server: Any):
        self.server = server

    def exists(self, session_id: str) -> bool:
        return bool(self.server.get_session(session_id) or self.server.session_store.get_session(session_id))

    def stored(self, session_id: str) -> Dict[str, Any]:
        stored = self.server.session_store.get_session(session_id)
        return stored if isinstance(stored, dict) else {}

    def status_payload(self, session_id: str) -> Optional[Dict[str, Any]]:
        session = self.server.get_session(session_id)
        if session:
            return {
                "session_id": session.session_id,
                "task": session.task,
                "done": session.done,
                "status": (
                    "canceled"
                    if session.cancelled
                    else ("error" if session.error else ("done" if session.done else "running"))
                ),
                "error": session.error,
                "canceled": session.cancelled,
            }
        stored = self.server.session_store.get_session(session_id)
        if not stored:
            return None
        return {
            "session_id": stored["session_id"],
            "task": stored["task"],
            "done": stored["status"] in ("done", "error", "canceled"),
            "error": stored["error"],
            "status": stored["status"],
            "canceled": stored["status"] == "canceled",
        }

    def commit_history_payload(self, session_id: str, *, steps: int) -> Dict[str, Any]:
        history = self.server.session_store.get_commit_history(session_id, limit=steps)
        return {
            "session_id": session_id,
            "commit_history": history,
            "count": len(history),
        }

    def context_sync_payload(self, session_id: str, *, steps: int) -> Dict[str, Any]:
        history = self.server.session_store.get_context_sync_history(session_id, limit=steps)
        return {
            "session_id": session_id,
            "context_sync": history,
            "latest": history[-1] if history else None,
            "count": len(history),
        }

    def goal_loop_payload(self, session_id: str, *, steps: int) -> Dict[str, Any]:
        return goal_loop_from_server(self.server, session_id, steps=steps)

    def runtime_metrics_payload(self, session_id: str, *, steps: int) -> Dict[str, Any]:
        metrics_evidence = runtime_metrics_from_server(self.server, session_id, limit=steps)
        metrics = metrics_evidence.get("history", [])
        return {
            "session_id": session_id,
            "runtime_metrics": metrics,
            "latest": metrics[-1] if metrics else None,
            "summary": summarize_runtime_metrics(metrics),
            "source": metrics_evidence.get("source"),
            "observer": metrics_evidence.get("observer"),
            "observer_count": metrics_evidence.get("observer_count"),
            "store_count": metrics_evidence.get("store_count"),
            "count": len(metrics),
        }

    def layer_health_payload(self, session_id: str, *, steps: int) -> Dict[str, Any]:
        return layer_health_from_server(self.server, session_id, steps=steps)

    def layer_control_payload(self, session_id: str, *, steps: int) -> Dict[str, Any]:
        return layer_control_from_server(self.server, session_id, steps=steps)

    def engineering_control_payload(self, session_id: str, *, steps: int) -> Dict[str, Any]:
        return engineering_control_from_server(self.server, session_id, steps=steps)

    def resume_drill_payload(self, session_id: str, *, steps: int) -> Dict[str, Any]:
        return resume_drill_from_server(self.server, session_id, steps=steps)

    def project_state_payload(self, session_id: str) -> Dict[str, Any]:
        layer_control = layer_control_from_server(self.server, session_id, steps=20)
        engineering_control = engineering_control_from_server(
            self.server,
            session_id,
            steps=20,
            layer_control=layer_control,
        )
        return project_state_from_server(
            self.server,
            session_id,
            layer_control=layer_control,
            engineering_control=engineering_control,
        )

    def project_writeback_plan(self, session_id: str) -> Dict[str, Any]:
        project_state = self.project_state_payload(session_id)
        project_control = (
            project_state.get("project_control")
            if isinstance(project_state.get("project_control"), dict)
            else {}
        )
        plan = build_project_writeback_plan(
            project_root=Path(self.server.agent.config.project_root()),
            session_id=session_id,
            project_state=project_state,
            project_control=project_control,
        )
        plan["endpoint"] = f"/sessions/{session_id}/project-writeback"
        return plan

    def apply_project_writeback_payload(self, session_id: str, *, apply: bool) -> Dict[str, Any]:
        plan = self.project_writeback_plan(session_id)
        if not apply:
            return {**plan, "dry_run": True, "apply_required": True}
        result = apply_project_writeback_plan(
            Path(self.server.agent.config.project_root()),
            plan,
        )
        event_payload = {
            "plan": compact_project_writeback(plan),
            "result": result,
        }
        session = self.server.get_session(session_id)
        if session:
            session.emit({
                "type": "project_writeback",
                "session_id": session_id,
                "source": "project_control",
                "payload": event_payload,
            })
        else:
            self.server.session_store.append_event(
                session_id,
                "project_writeback",
                event_payload,
                source="project_control",
            )
        return {**result, "plan": compact_project_writeback(plan)}

    def learning_payload(self, session_id: str, *, steps: int) -> Dict[str, Any]:
        history = self.server.session_store.get_learning_history(session_id, limit=steps)
        job = learning_job_from_server(self.server, session_id)
        return {
            "session_id": session_id,
            "learning": history,
            "latest": history[-1] if history else None,
            "count": len(history),
            "job": job,
            "policy": job.get("policy") if isinstance(job.get("policy"), dict) else {},
        }

    def maker_guard_payload(self, session_id: str, *, steps: int) -> Dict[str, Any]:
        history = self.server.session_store.get_maker_guard_history(session_id, limit=steps)
        return {
            "session_id": session_id,
            "maker_guard": history,
            "latest": history[-1] if history else None,
            "count": len(history),
        }

    def llm_probe_payload(self, session_id: str, *, steps: int) -> Dict[str, Any]:
        history = self.server.session_store.get_llm_probe_history(session_id, limit=steps)
        return {
            "session_id": session_id,
            "llm_probe": history,
            "latest": history[-1] if history else None,
            "count": len(history),
        }

    def evidence_bundle(self, session_id: str, *, steps: int) -> Dict[str, Any]:
        return build_session_evidence_bundle(
            server=self.server,
            session_id=session_id,
            steps=steps,
        )

    def runtime_advice_payload(self, session_id: str, *, steps: int) -> Dict[str, Any]:
        stored = self.stored(session_id)
        task = stored.get("task", "")
        maker_briefing = self.server.agent.maker_briefing(session_id=session_id, task=task)
        context_history = self.server.session_store.get_context_sync_history(session_id, limit=min(steps, 20))
        runtime_metrics = self.server.session_store.get_runtime_metrics_history(session_id, limit=steps)
        learning_history = self.server.session_store.get_learning_history(session_id, limit=steps)
        maker_guard_history = self.server.session_store.get_maker_guard_history(session_id, limit=steps)
        advice = build_runtime_advice(
            maker_briefing=maker_briefing,
            maker_guard_history=maker_guard_history,
            runtime_metrics_summary=summarize_runtime_metrics(runtime_metrics),
            learning_latest=learning_history[-1] if learning_history else None,
            latest_context_sync=context_history[-1] if context_history else None,
            llm_probe_latest=self.server._latest_llm_probe_for_session(session_id),
        )
        return {
            "session_id": session_id,
            "runtime_advice": advice,
        }
