"""Payload builders for external-agent startup and handoff routes."""

from __future__ import annotations

from typing import Any, Dict, List

from server.evidence_bundle import (
    build_llm_onboarding_bundle,
    build_llm_quickstart_bundle,
    build_runtime_advice,
    compact_llm_probe,
    summarize_runtime_metrics,
)


class AgentBootstrapApi:
    """Build `/agent/*` startup, quickstart, and handoff payloads."""

    def __init__(self, server: Any):
        self.server = server

    def session_available(self, session_id: str) -> bool:
        return (
            session_id == "{session_id}"
            or bool(self.server.get_session(session_id))
            or bool(self.server.session_store.get_session(session_id))
        )

    def onboarding_bundle(self, session_id: str, *, steps: int, surface: str = "generic") -> Dict[str, Any]:
        return build_llm_onboarding_bundle(
            server=self.server,
            session_id=session_id,
            steps=steps,
            surface=surface,
        )

    def maker_briefing_payload(self, session_id: str, *, task: str = "") -> Dict[str, Any]:
        return self.server.agent.maker_briefing(session_id=session_id, task=task)

    def handoff_bundle(self, session_id: str, *, steps: int) -> Dict[str, Any]:
        task = self._task_for(session_id)
        contract = self.server.agent.runtime_contract(session_id=session_id)
        maker_briefing = self.server.agent.maker_briefing(session_id=session_id, task=task)
        context_history = self._context_history(session_id, limit=steps)
        runtime_metrics = self._runtime_metrics(session_id, limit=20)
        learning_history = self._learning_history(session_id, limit=20)
        maker_guard_history = self._maker_guard_history(session_id, limit=20)
        skill_status = self._skill_status()
        skill_graph = skill_status.get("skill_graph") if isinstance(skill_status, dict) else {}
        registry = skill_status.get("registry") if isinstance(skill_status, dict) else {}
        manifest = skill_status.get("manifest") if isinstance(skill_status, dict) else {}
        runtime_summary = summarize_runtime_metrics(runtime_metrics)
        llm_probe_latest = self.server._latest_llm_probe_for_session(session_id)
        runtime_advice = build_runtime_advice(
            maker_briefing=maker_briefing,
            maker_guard_history=maker_guard_history,
            runtime_metrics_summary=runtime_summary,
            learning_latest=learning_history[-1] if learning_history else None,
            latest_context_sync=context_history[-1] if context_history else None,
            llm_probe_latest=llm_probe_latest,
        )
        return {
            "session_id": session_id,
            "runtime_contract": contract,
            "maker_briefing": maker_briefing,
            "latest_context_sync": context_history[-1] if context_history else None,
            "context_sync": context_history,
            "runtime_metrics_summary": runtime_summary,
            "learning_latest": learning_history[-1] if learning_history else None,
            "maker_guard_latest": maker_guard_history[-1] if maker_guard_history else None,
            "maker_guard": maker_guard_history[-steps:],
            "runtime_advice": runtime_advice,
            "llm_probe_latest": compact_llm_probe(llm_probe_latest),
            "skill_summary": {
                "registry": registry,
                "graph_summary": skill_graph.get("summary", {}) if isinstance(skill_graph, dict) else {},
                "manifest_summary": manifest.get("summary", {}) if isinstance(manifest, dict) else {},
            },
            "attach_sequence": (contract.get("external_agents") or {}).get("attach_sequence", []),
            "token_rule": "Use this handoff bundle first; fetch full tools, transcripts, or skill graph only when needed.",
        }

    def quickstart_bundle(self, session_id: str, *, steps: int, surface: str = "generic") -> Dict[str, Any]:
        task = self._task_for(session_id)
        contract = self.server.agent.runtime_contract(session_id=session_id)
        maker_briefing = self.server.agent.maker_briefing(session_id=session_id, task=task)
        context_history = self._context_history(session_id, limit=steps)
        runtime_metrics = self._runtime_metrics(session_id, limit=20)
        learning_history = self._learning_history(session_id, limit=20)
        maker_guard_history = self._maker_guard_history(session_id, limit=20)
        llm_probe_latest = self.server._latest_llm_probe_for_session(session_id)
        runtime_advice = build_runtime_advice(
            maker_briefing=maker_briefing,
            maker_guard_history=maker_guard_history,
            runtime_metrics_summary=summarize_runtime_metrics(runtime_metrics),
            learning_latest=learning_history[-1] if learning_history else None,
            latest_context_sync=context_history[-1] if context_history else None,
            llm_probe_latest=llm_probe_latest,
        )
        return build_llm_quickstart_bundle(
            session_id=session_id,
            task=task,
            contract=contract,
            maker_briefing=maker_briefing,
            runtime_advice=runtime_advice,
            context_history=context_history,
            surface=surface,
            llm_probe_latest=llm_probe_latest,
        )

    def _task_for(self, session_id: str) -> str:
        stored = self.server.session_store.get_session(session_id) if session_id != "{session_id}" else {}
        return (stored or {}).get("task", "") if session_id != "{session_id}" else ""

    def _context_history(self, session_id: str, *, limit: int) -> List[Dict[str, Any]]:
        if session_id == "{session_id}":
            return []
        return self.server.session_store.get_context_sync_history(session_id, limit=limit)

    def _runtime_metrics(self, session_id: str, *, limit: int) -> List[Dict[str, Any]]:
        if session_id == "{session_id}":
            return []
        return self.server.session_store.get_runtime_metrics_history(session_id, limit=limit)

    def _learning_history(self, session_id: str, *, limit: int) -> List[Dict[str, Any]]:
        if session_id == "{session_id}":
            return []
        return self.server.session_store.get_learning_history(session_id, limit=limit)

    def _maker_guard_history(self, session_id: str, *, limit: int) -> List[Dict[str, Any]]:
        if session_id == "{session_id}":
            return []
        return self.server.session_store.get_maker_guard_history(session_id, limit=limit)

    def _skill_status(self) -> Dict[str, Any]:
        try:
            return self.server.skill_sync_registry.status(force=False)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
