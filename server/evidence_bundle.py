"""Evidence, readiness, onboarding, and handoff builders for AppServer.

This module keeps compact runtime evidence assembly separate from HTTP route
handling so AppServer can stay focused on transport and session lifecycle.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from core.intent_classifier import COS_GATE_VERSION, classify_cos_gate
from core.portable_env import portable_diagnostics
from llm.provider_presets import provider_preset
from server.engineering_control import build_engineering_control_snapshot
from server.layer_control import build_layer_control_snapshot
from server.layer_health import build_layer_health_snapshot
from server.memory_observer import memory_metric_from_runtime_metric, summarize_memory_recall_history
from server.project_control import build_project_control
from server.project_writeback import build_project_writeback_plan, compact_project_writeback
from server.resume_drill import build_resume_drill_report


APP_ROOT = Path(__file__).resolve().parent.parent


def summarize_runtime_metrics(metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
    latest_by_kind: Dict[str, Dict[str, Any]] = {}
    total_tokens = 0
    max_latency: Dict[str, Any] = {}
    for item in metrics:
        kind = str(item.get("kind") or "unknown")
        latest_by_kind[kind] = item
        if kind == "llm_usage":
            tokens = item.get("total_tokens")
            if isinstance(tokens, (int, float)):
                total_tokens += int(tokens)
        if kind == "latency":
            elapsed = item.get("elapsed_ms")
            if isinstance(elapsed, (int, float)) and elapsed >= max_latency.get("elapsed_ms", -1):
                max_latency = item

    latest_context = latest_by_kind.get("context_budget", {})
    latest_tool_selection = latest_by_kind.get("tool_selection", {})
    return {
        "event_count": len(metrics),
        "latest_by_kind": latest_by_kind,
        "llm_total_tokens": total_tokens,
        "max_latency": max_latency,
        "token_cache": {
            "hits": latest_context.get("token_cache_hits"),
            "misses": latest_context.get("token_cache_misses"),
            "size": latest_context.get("token_cache_size"),
        },
        "retrieval": {
            "agents_md_hits": latest_context.get("agents_md_hits"),
            "cold_recall_hits": latest_context.get("cold_recall_hits"),
            "context_build_ms": latest_context.get("context_build_ms"),
        },
        "tool_ranking": {
            "phase": latest_tool_selection.get("phase"),
            "candidate_count": latest_tool_selection.get("candidate_count"),
            "selected_count": latest_tool_selection.get("selected_count"),
            "ranking_ms": latest_tool_selection.get("ranking_ms"),
            "cache_hit": latest_tool_selection.get("cache_hit"),
            "cache_size": latest_tool_selection.get("cache_size"),
        },
    }


def runtime_metrics_from_server(server: Any, session_id: str, *, limit: int = 100) -> Dict[str, Any]:
    """Return durable runtime metrics plus live bus-observer evidence."""
    store_metrics: List[Dict[str, Any]] = []
    observer_metrics: List[Dict[str, Any]] = []
    observer_summary: Dict[str, Any] = {"status": "missing"}
    try:
        store_metrics = server.session_store.get_runtime_metrics_history(session_id, limit=limit)
    except Exception:
        store_metrics = []
    observer = getattr(server, "runtime_metrics_observer", None)
    if observer is not None:
        try:
            observer_metrics = observer.history(session_id, limit=limit)
            observer_summary = observer.summary(session_id, limit=limit)
            observer_summary["status"] = "ready"
        except Exception as exc:
            observer_metrics = []
            observer_summary = {"status": "error", "error": str(exc)}
    return {
        "source": "runtime_event_bus_observer" if observer_metrics else "session_store",
        "history": observer_metrics or store_metrics,
        "observer_history": observer_metrics,
        "store_history": store_metrics,
        "observer": observer_summary,
        "store_count": len(store_metrics),
        "observer_count": len(observer_metrics),
    }


def project_state_from_server(
    server: Any,
    session_id: str,
    *,
    layer_control: Optional[Dict[str, Any]] = None,
    engineering_control: Optional[Dict[str, Any]] = None,
    runtime_advice: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    observer = getattr(server, "project_observer", None)
    if observer is None:
        return _attach_project_control(
            {
                "status": "missing",
                "source": "runtime_event_bus_project_observer",
                "session_id": session_id,
            },
            cos_gate_from_server(server, session_id),
            runtime_advice=runtime_advice,
            layer_control=layer_control,
            engineering_control=engineering_control,
        )
    try:
        snapshot = observer.snapshot(session_id)
    except Exception as exc:
        return _attach_project_control(
            {
                "status": "error",
                "source": "runtime_event_bus_project_observer",
                "session_id": session_id,
                "error": str(exc),
            },
            cos_gate_from_server(server, session_id),
            runtime_advice=runtime_advice,
            layer_control=layer_control,
            engineering_control=engineering_control,
        )
    if snapshot.get("status") == "missing":
        context_history = []
        try:
            context_history = server.session_store.get_context_sync_history(session_id, limit=1)
        except Exception:
            context_history = []
        if context_history:
            latest = context_history[-1]
            checkpoint = latest.get("continuation_checkpoint") if isinstance(latest.get("continuation_checkpoint"), dict) else {}
            return _attach_project_control(
                {
                    "status": "replay",
                    "source": "session_store_context_sync",
                    "session_id": session_id,
                    "task": (latest.get("snapshot") or {}).get("task") if isinstance(latest.get("snapshot"), dict) else None,
                    "workspace_profile": latest.get("workspace_profile"),
                    "goal_overall": latest.get("goal_overall"),
                    "next_focus": checkpoint.get("goal_next_focus"),
                    "last_tool": latest.get("last_tool"),
                    "plan_verdict": latest.get("plan_verdict"),
                    "continuation": {
                        "status": "ready" if latest.get("resume_ready") else "partial",
                        "resume_ready": latest.get("resume_ready"),
                        "resume_mode": latest.get("resume_mode"),
                        "open_plan_count": latest.get("open_plan_count"),
                    },
                    "next_action": checkpoint.get("goal_next_focus") or "Resume from latest context_sync checkpoint.",
                },
                cos_gate_from_server(server, session_id),
                runtime_advice=runtime_advice,
                layer_control=layer_control,
                engineering_control=engineering_control,
            )
    return _attach_project_control(
        snapshot,
        cos_gate_from_server(server, session_id),
        runtime_advice=runtime_advice,
        layer_control=layer_control,
        engineering_control=engineering_control,
    )


def _attach_project_control(
    project_state: Dict[str, Any],
    cos_gate: Dict[str, Any],
    runtime_advice: Optional[Dict[str, Any]] = None,
    layer_control: Optional[Dict[str, Any]] = None,
    engineering_control: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    state = dict(project_state) if isinstance(project_state, dict) else {}
    state["project_control"] = build_project_control(
        project_state=state,
        cos_gate=cos_gate,
        runtime_advice=runtime_advice,
        layer_control=layer_control,
        engineering_control=engineering_control,
    )
    return state


def project_writeback_from_server(
    server: Any,
    session_id: str,
    project_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Return compact project-control writeback plan evidence."""
    project_state = project_state if isinstance(project_state, dict) else {}
    project_control = (
        project_state.get("project_control")
        if isinstance(project_state.get("project_control"), dict)
        else {}
    )
    try:
        plan = build_project_writeback_plan(
            project_root=Path(server.agent.config.project_root()),
            session_id=session_id,
            project_state=project_state,
            project_control=project_control,
        )
        plan["endpoint"] = f"/sessions/{session_id}/project-writeback"
        return compact_project_writeback(plan)
    except Exception as exc:
        return {
            "version": "project-writeback.v1",
            "session_id": session_id,
            "status": "error",
            "applicable": False,
            "operation_count": 0,
            "files": [],
            "invalid_target_count": 0,
            "reason": str(exc),
            "endpoint": f"/sessions/{session_id}/project-writeback",
        }


def learning_state_from_server(server: Any, session_id: str, *, limit: int = 100) -> Dict[str, Any]:
    observer = getattr(server, "learning_observer", None)
    observer_summary: Dict[str, Any] = {
        "status": "missing",
        "source": "runtime_event_bus_learning_observer",
        "session_id": session_id,
    }
    if observer is not None:
        try:
            observer_summary = observer.summary(session_id)
        except Exception as exc:
            observer_summary = {
                "status": "error",
                "source": "runtime_event_bus_learning_observer",
                "session_id": session_id,
                "error": str(exc),
            }

    store_history: List[Dict[str, Any]] = []
    try:
        store_history = server.session_store.get_learning_history(session_id, limit=limit)
    except Exception:
        store_history = []

    if observer_summary.get("status") == "ready":
        latest = {
            "event": observer_summary.get("event"),
            "state": observer_summary.get("state"),
            "detail": observer_summary.get("detail"),
            "source_layer": observer_summary.get("source_layer"),
            "target_layer": observer_summary.get("target_layer"),
            "cause": observer_summary.get("cause"),
            "metrics": {
                "async": observer_summary.get("async"),
                "eligible": observer_summary.get("eligible"),
                "elapsed_ms": observer_summary.get("elapsed_ms"),
                "error": observer_summary.get("error"),
            },
            "timestamp": observer_summary.get("timestamp"),
        }
        return {
            **observer_summary,
            "latest": latest,
            "observer": observer_summary,
            "store_count": len(store_history),
        }

    if store_history:
        latest = store_history[-1]
        return {
            "status": "replay",
            "source": "session_store_learning_history",
            "session_id": session_id,
            "latest": latest,
            "event": latest.get("event"),
            "state": latest.get("state"),
            "observer": observer_summary,
            "store_count": len(store_history),
        }

    return {
        **observer_summary,
        "latest": {},
        "observer": observer_summary,
        "store_count": 0,
    }


def memory_recall_from_server(server: Any, session_id: str, *, limit: int = 100) -> Dict[str, Any]:
    observer = getattr(server, "memory_observer", None)
    observer_summary: Dict[str, Any] = {
        "status": "missing",
        "source": "runtime_event_bus_memory_observer",
        "session_id": session_id,
        "event_count": 0,
    }
    if observer is not None:
        try:
            observer_summary = observer.summary(session_id, limit=limit)
        except Exception as exc:
            observer_summary = {
                "status": "error",
                "source": "runtime_event_bus_memory_observer",
                "session_id": session_id,
                "event_count": 0,
                "error": str(exc),
            }
    if observer_summary.get("status") == "ready":
        return {**observer_summary, "observer": observer_summary, "store_count": 0}

    store_history: List[Dict[str, Any]] = []
    try:
        metrics = server.session_store.get_runtime_metrics_history(session_id, limit=limit)
        for metric in metrics:
            recall_metric = memory_metric_from_runtime_metric(metric)
            if recall_metric is not None:
                store_history.append(recall_metric)
    except Exception:
        store_history = []

    if store_history:
        return {
            **summarize_memory_recall_history(
                store_history,
                session_id=session_id,
                source="session_store_context_budget",
                status="replay",
                observed_event_count=int(observer_summary.get("observed_event_count") or 0),
                observed_session_count=int(observer_summary.get("observed_session_count") or 0),
                history_limit=observer_summary.get("history_limit"),
            ),
            "observer": observer_summary,
            "store_count": len(store_history),
        }

    return {**observer_summary, "observer": observer_summary, "store_count": 0}


def summarize_layer_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    latest_by_layer: Dict[str, Dict[str, Any]] = {}
    recent_routes: List[Dict[str, Any]] = []
    for item in events:
        layer = str(item.get("layer") or "unknown")
        compact = {
            "layer": layer,
            "state": item.get("state"),
            "event": item.get("event"),
            "detail": item.get("detail"),
            "source_layer": item.get("source_layer"),
            "target_layer": item.get("target_layer"),
            "cause": item.get("cause"),
            "metrics": item.get("metrics") if isinstance(item.get("metrics"), dict) else {},
            "timestamp": item.get("timestamp"),
        }
        latest_by_layer[layer] = compact
        recent_routes.append({
            "route": f"{item.get('source_layer') or '-'}->{item.get('target_layer') or '-'}",
            "layer": layer,
            "state": item.get("state"),
            "event": item.get("event"),
        })
    return {
        "event_count": len(events),
        "latest_by_layer": latest_by_layer,
        "recent_routes": recent_routes[-6:],
    }


def session_status_from_server(server: Any, session_id: str) -> Dict[str, Any]:
    session = server.get_session(session_id) if session_id != "{session_id}" else None
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
        }
    stored = server.session_store.get_session(session_id) if session_id != "{session_id}" else {}
    if stored:
        return {
            "session_id": stored.get("session_id") or session_id,
            "task": stored.get("task"),
            "done": stored.get("status") in {"done", "error", "canceled"},
            "status": stored.get("status"),
            "error": stored.get("error"),
        }
    return {
        "session_id": session_id,
        "status": "missing" if session_id != "{session_id}" else "not_requested",
        "done": False,
        "error": None,
    }


def learning_job_from_server(server: Any, session_id: str) -> Dict[str, Any]:
    session = server.get_session(session_id) if session_id != "{session_id}" else None
    candidates = []
    active_agent = getattr(session, "active_agent", None) if session is not None else None
    if active_agent is not None:
        candidates.append(active_agent)
    candidates.append(getattr(server, "agent", None))
    for agent in candidates:
        getter = getattr(agent, "get_learning_job", None)
        if not callable(getter):
            continue
        try:
            job = getter(session_id)
        except Exception:
            continue
        if isinstance(job, dict) and job.get("status") != "missing":
            return job
    if session_id != "{session_id}":
        try:
            history = server.session_store.get_learning_history(session_id, limit=1)
        except Exception:
            history = []
        if history:
            return learning_job_from_history(session_id, history[-1])
    return {"session_id": session_id, "status": "missing"}


def learning_job_from_history(session_id: str, latest: Dict[str, Any]) -> Dict[str, Any]:
    """Reconstruct a conservative public job snapshot from durable layer events."""
    latest = latest if isinstance(latest, dict) else {}
    event = str(latest.get("event") or "")
    metrics = latest.get("metrics") if isinstance(latest.get("metrics"), dict) else {}
    status = "missing"
    if event.endswith(".queued") or event.endswith(".retry_queued"):
        status = "queued"
    elif event.endswith(".started") or event.endswith(".cancel_requested"):
        status = "running"
    elif event.endswith(".finished"):
        status = "done"
    elif event.endswith(".failed"):
        status = "error"
    elif event.endswith(".skipped"):
        status = "skipped"
    elif event.endswith(".cancelled") or event.endswith(".canceled"):
        status = "cancelled"
    return {
        "session_id": session_id,
        "status": status,
        "source": "session_store_learning_history",
        "event": latest.get("event"),
        "state": latest.get("state"),
        "eligible": metrics.get("eligible"),
        "async": metrics.get("async"),
        "attempts": metrics.get("attempts", 0),
        "max_attempts": metrics.get("max_attempts"),
        "retryable": metrics.get("retryable"),
        "cancel_requested": metrics.get("cancel_requested"),
        "elapsed_ms": metrics.get("elapsed_ms", 0),
        "error": metrics.get("error", ""),
        "insight_count": metrics.get("insight_count"),
        "shared_memory": {
            "counts": {
                "archived": metrics.get("shared_memory_archived", 0),
                "promoted": metrics.get("shared_memory_promoted", 0),
                "conflicts": metrics.get("shared_memory_conflicts", 0),
            }
        },
        "policy": {
            "managed": True,
            "source": "durable_event_replay",
            "truthfulness_rule": "live queue handles are not reconstructed from persisted events",
        },
    }


def layer_health_from_server(server: Any, session_id: str, *, steps: int = 20) -> Dict[str, Any]:
    layer_history: List[Dict[str, Any]] = []
    if session_id != "{session_id}":
        try:
            layer_history = server.session_store.get_layer_history(session_id, limit=steps)
        except Exception:
            layer_history = []
    runtime_metrics_evidence = (
        runtime_metrics_from_server(server, session_id, limit=steps)
        if session_id != "{session_id}"
        else {"history": []}
    )
    runtime_summary = summarize_runtime_metrics(runtime_metrics_evidence.get("history", []))
    learning_state = (
        learning_state_from_server(server, session_id, limit=steps)
        if session_id != "{session_id}"
        else {"status": "not_requested"}
    )
    event_bus_summary = build_runtime_event_bus_summary(server=server, session_id=session_id)
    return build_layer_health_snapshot(
        session_id=session_id,
        session_status=session_status_from_server(server, session_id),
        layer_summary=summarize_layer_events(layer_history),
        runtime_metrics_summary=runtime_summary,
        learning_state=learning_state,
        learning_job=learning_job_from_server(server, session_id),
        event_bus_summary=event_bus_summary,
    )


def layer_control_from_server(server: Any, session_id: str, *, steps: int = 20) -> Dict[str, Any]:
    """Build engineering-control advice from the current layer-health snapshot."""
    return build_layer_control_snapshot(
        layer_health=layer_health_from_server(server, session_id, steps=steps),
    )


def engineering_control_from_server(
    server: Any,
    session_id: str,
    *,
    steps: int = 20,
    layer_control: Optional[Dict[str, Any]] = None,
    memory_recall: Optional[Dict[str, Any]] = None,
    runtime_metrics_summary: Optional[Dict[str, Any]] = None,
    project_state: Optional[Dict[str, Any]] = None,
    cos_gate: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build engineering-control advice from compact public evidence."""
    recent_events: List[Dict[str, Any]] = []
    if session_id != "{session_id}":
        try:
            recent_events = server.session_store.get_events(session_id)
        except Exception:
            recent_events = []
    if steps > 0:
        recent_events = recent_events[-max(steps * 4, steps):]

    if layer_control is None:
        layer_control = layer_control_from_server(server, session_id, steps=steps)
    if memory_recall is None:
        memory_recall = (
            memory_recall_from_server(server, session_id, limit=steps)
            if session_id != "{session_id}"
            else {"status": "not_requested"}
        )
    if runtime_metrics_summary is None:
        metrics = []
        if session_id != "{session_id}":
            try:
                metrics = runtime_metrics_from_server(server, session_id, limit=steps).get("history", [])
            except Exception:
                metrics = []
        runtime_metrics_summary = summarize_runtime_metrics(metrics)
    if cos_gate is None:
        cos_gate = cos_gate_from_server(server, session_id)

    return build_engineering_control_snapshot(
        session_id=session_id,
        layer_control=layer_control,
        memory_recall=memory_recall,
        runtime_metrics_summary=runtime_metrics_summary,
        project_state=project_state,
        cos_gate=cos_gate,
        recent_events=recent_events,
    )


def resume_drill_from_server(server: Any, session_id: str, *, steps: int = 20) -> Dict[str, Any]:
    """Return store-replay long-task resume evidence without live runtime state."""
    stored: Dict[str, Any] = {}
    context_history: List[Dict[str, Any]] = []
    events: List[Dict[str, Any]] = []
    try:
        stored = server.session_store.get_session(session_id) or {}
    except Exception:
        stored = {}
    try:
        context_history = server.session_store.get_context_sync_history(session_id, limit=steps)
    except Exception:
        context_history = []
    try:
        events = server.session_store.get_events(session_id)
    except Exception:
        events = []
    if steps > 0:
        events = events[-steps:]
    return build_resume_drill_report(
        session_id=session_id,
        stored_session=stored,
        context_history=context_history,
        event_history=events,
        live_session_present=bool(server.get_session(session_id)),
    )


def build_runtime_advice(
    *,
    maker_briefing: Dict[str, Any],
    maker_guard_history: List[Dict[str, Any]],
    runtime_metrics_summary: Dict[str, Any],
    learning_latest: Optional[Dict[str, Any]],
    latest_context_sync: Optional[Dict[str, Any]],
    llm_probe_latest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Derive a compact next-step diagnosis from runtime evidence."""
    latest_guard = maker_guard_history[-1] if maker_guard_history else None
    reasons: List[str] = []
    evidence: Dict[str, Any] = {}
    if llm_probe_latest:
        evidence["llm_probe"] = {
            "ok": llm_probe_latest.get("ok"),
            "provider": llm_probe_latest.get("provider"),
            "runtime_kind": llm_probe_latest.get("runtime_kind"),
            "endpoint": (llm_probe_latest.get("last_call_stats") or {}).get("endpoint")
                if isinstance(llm_probe_latest.get("last_call_stats"), dict)
                else None,
            "elapsed_ms": llm_probe_latest.get("elapsed_ms"),
            "error": llm_probe_latest.get("error"),
        }
        if llm_probe_latest.get("ok") is False:
            return {
                "status": "needs_action",
                "priority": "llm_provider",
                "next_action": "Fix provider/API key/base URL or run /llm/probe before starting a full Maker task.",
                "reasons": [llm_probe_latest.get("error") or "Latest LLM probe failed."],
                "evidence": evidence,
            }

    if latest_guard:
        evidence["maker_guard"] = {
            "decision": latest_guard.get("decision"),
            "tool": latest_guard.get("tool"),
            "reason": latest_guard.get("reason"),
        }
        if latest_guard.get("decision") == "block":
            return {
                "status": "needs_action",
                "priority": "maker_alignment",
                "next_action": latest_guard.get("recommended_first_action")
                    or "Follow Maker briefing before local side effects.",
                "reasons": [latest_guard.get("reason") or "Maker first-action guard blocked the first action."],
                "evidence": evidence,
            }

    if maker_briefing.get("connected") is False or maker_briefing.get("readiness") == "disconnected":
        return {
            "status": "needs_action",
            "priority": "maker_mcp_connection",
            "next_action": maker_briefing.get("recommended_first_action")
                or "Check MakerMCP status before continuing.",
            "reasons": maker_briefing.get("warning_codes") or ["MakerMCP is disconnected or not ready."],
            "evidence": {
                **evidence,
                "maker_briefing": {
                    "readiness": maker_briefing.get("readiness"),
                    "authority": maker_briefing.get("authority"),
                },
            },
        }

    max_latency = runtime_metrics_summary.get("max_latency") if isinstance(runtime_metrics_summary.get("max_latency"), dict) else {}
    elapsed_ms = max_latency.get("elapsed_ms")
    if isinstance(elapsed_ms, (int, float)) and elapsed_ms >= 30000:
        reasons.append(f"{max_latency.get('phase') or 'runtime'} took {elapsed_ms}ms")
        evidence["max_latency"] = max_latency
        return {
            "status": "needs_action",
            "priority": "latency",
            "next_action": "Inspect runtime_metrics before changing prompts or provider routing.",
            "reasons": reasons,
            "evidence": evidence,
        }

    token_cache = runtime_metrics_summary.get("token_cache") if isinstance(runtime_metrics_summary.get("token_cache"), dict) else {}
    misses = token_cache.get("misses")
    hits = token_cache.get("hits")
    total_tokens = runtime_metrics_summary.get("llm_total_tokens")
    if (
        isinstance(total_tokens, int) and total_tokens >= 20000
    ) or (
        isinstance(misses, (int, float))
        and isinstance(hits, (int, float))
        and misses > hits + 3
    ):
        reasons.append("Token/cache evidence suggests prompt or retrieval pressure.")
        evidence["token_cache"] = token_cache
        evidence["llm_total_tokens"] = total_tokens
        return {
            "status": "needs_action",
            "priority": "token_efficiency",
            "next_action": "Use ranked tools, context_sync, and runtime_metrics summaries before fetching raw transcripts.",
            "reasons": reasons,
            "evidence": evidence,
        }

    if learning_latest and learning_latest.get("state") in {"queued", "running"}:
        return {
            "status": "watch",
            "priority": "learning_async",
            "next_action": "Continue the user task; learning is running asynchronously.",
            "reasons": [learning_latest.get("detail") or learning_latest.get("event") or "learning pending"],
            "evidence": {**evidence, "learning": learning_latest},
        }

    if not latest_context_sync:
        return {
            "status": "needs_action",
            "priority": "context_sync",
            "next_action": "Wait for or request a compact context_sync snapshot before external handoff.",
            "reasons": ["No context_sync snapshot is available."],
            "evidence": evidence,
        }
    continuation = summarize_continuation(latest_context_sync)
    if continuation.get("resume_ready"):
        evidence["continuation"] = {
            "resume_ready": continuation.get("resume_ready"),
            "resume_mode": continuation.get("resume_mode"),
            "workspace_profile": continuation.get("workspace_profile"),
            "open_plan_count": continuation.get("open_plan_count"),
            "compression_needed": continuation.get("compression_needed"),
        }

    return {
        "status": "ready",
        "priority": "continue",
        "next_action": "Proceed from continuation checkpoint using maker_briefing and compact handoff evidence.",
        "reasons": ["Maker alignment and compact runtime evidence are available."],
        "evidence": {
            **evidence,
            "context_revision": latest_context_sync.get("revision"),
            "learning": learning_latest,
        },
    }


def summarize_continuation(latest_context_sync: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(latest_context_sync, dict) or not latest_context_sync:
        return {
            "status": "missing",
            "resume_ready": False,
            "next_action": "Wait for context_sync before long-task handoff.",
        }
    checkpoint = latest_context_sync.get("continuation_checkpoint")
    if not isinstance(checkpoint, dict):
        snapshot = latest_context_sync.get("snapshot") if isinstance(latest_context_sync.get("snapshot"), dict) else {}
        checkpoint = (
            snapshot.get("continuation_checkpoint")
            if isinstance(snapshot.get("continuation_checkpoint"), dict)
            else {}
        )
    compression = checkpoint.get("compression") if isinstance(checkpoint.get("compression"), dict) else {}
    open_plan_steps = (
        checkpoint.get("open_plan_steps")
        if isinstance(checkpoint.get("open_plan_steps"), list)
        else []
    )
    artifacts = (
        checkpoint.get("artifact_refs")
        if isinstance(checkpoint.get("artifact_refs"), list)
        else []
    )
    return {
        "status": "ready" if checkpoint.get("resume_ready") else "partial",
        "version": checkpoint.get("version"),
        "resume_ready": bool(checkpoint.get("resume_ready")),
        "resume_mode": checkpoint.get("resume_mode") or "context_handoff",
        "workspace_profile": checkpoint.get("workspace_profile")
            or latest_context_sync.get("workspace_profile")
            or "general",
        "context_revision": checkpoint.get("context_revision") or latest_context_sync.get("revision"),
        "iteration": checkpoint.get("iteration") or latest_context_sync.get("step"),
        "trajectory_steps": checkpoint.get("trajectory_steps"),
        "goal_next_focus": checkpoint.get("goal_next_focus"),
        "goal_overall": checkpoint.get("goal_overall") or latest_context_sync.get("goal_overall"),
        "last_tool": checkpoint.get("last_tool") or latest_context_sync.get("last_tool"),
        "last_ok": checkpoint.get("last_ok"),
        "plan_verdict": checkpoint.get("plan_verdict") or latest_context_sync.get("plan_verdict"),
        "open_plan_count": len(open_plan_steps),
        "open_plan_steps": open_plan_steps[:6],
        "artifact_count": checkpoint.get("artifact_count") or latest_context_sync.get("artifact_count", 0),
        "artifact_refs": artifacts[:6],
        "compression_needed": bool(compression.get("needed")),
        "compressed_step_count": compression.get("compressed_step_count", 0),
        "skipped_step_count": compression.get("skipped_step_count", 0),
        "summary": str(compression.get("summary") or "")[:800],
        "resume_limits": checkpoint.get("resume_limits") if isinstance(checkpoint.get("resume_limits"), dict) else {},
        "handoff_hint": checkpoint.get("handoff_hint") or "Use context_sync/runtime_metrics before raw SSE.",
    }


def compact_llm_probe(probe: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(probe, dict) or not probe:
        return {
            "status": "not_run",
            "ok": None,
            "next_action": "POST /llm/probe when provider wiring is uncertain.",
        }
    stats = probe.get("last_call_stats") if isinstance(probe.get("last_call_stats"), dict) else {}
    return {
        "status": "ok" if probe.get("ok") else "error",
        "ok": probe.get("ok"),
        "provider": probe.get("provider"),
        "runtime_kind": probe.get("runtime_kind"),
        "llm_class": probe.get("llm_class"),
        "model": probe.get("model"),
        "base_url": probe.get("base_url"),
        "elapsed_ms": probe.get("elapsed_ms"),
        "endpoint": stats.get("endpoint"),
        "total_tokens": stats.get("total_tokens"),
        "error_type": stats.get("error_type"),
        "error": probe.get("error"),
    }


def expected_llm_endpoint(provider: str, base_url: str) -> str:
    """Return the endpoint this runtime should hit for provider calls."""
    normalized = (provider or "").lower().strip()
    base = (base_url or "").rstrip("/")
    if not base:
        return ""
    if normalized == "minimax":
        return f"{base}/text/chatcompletion_v2"
    if normalized in {"claude", "anthropic"}:
        return f"{base}/messages"
    return f"{base}/chat/completions"


def build_llm_call_proof(
    *,
    server: Any,
    session_id: str = "{session_id}",
    llm_probe: Optional[Dict[str, Any]] = None,
    last_call_stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Summarize local evidence that an API provider was really invoked.

    This is intentionally no-network: it only explains existing config,
    latest probe history, and the active LLM's last_call_stats.
    """
    cfg = server.agent.config
    llm_cfg = cfg.llm_config()
    config_provider = cfg.llm_provider()
    compact_probe = compact_llm_probe(llm_probe if llm_probe is not None else server._latest_llm_probe_for_session(session_id))
    provider = str(compact_probe.get("provider") or config_provider)
    preset = provider_preset(provider)
    runtime_kind = str(compact_probe.get("runtime_kind") or "")
    if not runtime_kind:
        if provider == "mock":
            runtime_kind = "mock"
        elif preset.get("kind") == "local" or provider in {"local", "gguf"}:
            runtime_kind = "local"
        else:
            runtime_kind = "api"

    model = compact_probe.get("model") or llm_cfg.get("model") or preset.get("model", "")
    base_url = compact_probe.get("base_url") or llm_cfg.get("base_url") or preset.get("base_url", "")
    expected_endpoint = expected_llm_endpoint(provider, base_url) if runtime_kind == "api" else ""
    if runtime_kind == "api" and provider == config_provider:
        api_key_set = bool(server._provider_api_key(provider))
    elif runtime_kind == "api":
        api_key_set = None
    else:
        api_key_set = None
    stats = dict(last_call_stats or {})
    if not stats:
        stats_getter = getattr(server.agent.llm, "last_call_stats", None)
        if callable(stats_getter):
            try:
                stats = stats_getter() or {}
            except Exception:
                stats = {}

    probe_endpoint = compact_probe.get("endpoint")
    runtime_endpoint = stats.get("endpoint")
    observed_endpoint = probe_endpoint or runtime_endpoint or ""
    evidence_source = "none"
    if probe_endpoint:
        evidence_source = "llm_probe"
    elif runtime_endpoint:
        evidence_source = "active_runtime_last_call"

    endpoint_matches = None
    if expected_endpoint and observed_endpoint:
        endpoint_matches = observed_endpoint.rstrip("/") == expected_endpoint.rstrip("/")

    if runtime_kind != "api":
        conclusion = f"{runtime_kind}_runtime"
    elif api_key_set is False:
        conclusion = "api_key_missing"
    elif not observed_endpoint:
        conclusion = "api_call_not_observed"
    elif endpoint_matches is False:
        conclusion = "api_call_observed_endpoint_mismatch"
    else:
        conclusion = "api_call_observed"

    return {
        "version": "llm-call-proof.v1",
        "provider": provider,
        "runtime_kind": runtime_kind,
        "llm_class": server.agent.llm.__class__.__name__,
        "model": model,
        "base_url": base_url,
        "api_key_set": api_key_set,
        "expected_endpoint": expected_endpoint,
        "observed_endpoint": observed_endpoint,
        "evidence_source": evidence_source,
        "endpoint_matches_expected": endpoint_matches,
        "conclusion": conclusion,
        "probe": compact_probe,
        "last_call": {
            "endpoint": runtime_endpoint,
            "http_status": stats.get("http_status"),
            "error_type": stats.get("error_type"),
            "total_tokens": stats.get("total_tokens"),
            "generate_ms": stats.get("generate_ms"),
            "request_id": stats.get("request_id"),
        },
        "note": (
            "MiniMax must use /text/chatcompletion_v2; OpenAI-compatible providers use /chat/completions."
            if provider == "minimax"
            else "No network call is made while building this proof."
        ),
    }


def build_llm_feedback_summary(feedback_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Summarize saved LLM-as-user feedback artifacts without calling an external model."""
    target = feedback_dir or (APP_ROOT / "docs" / "llm-feedback")
    try:
        from scripts.summarize_llm_feedback import summarize

        summary = summarize(target)
    except Exception as e:
        return {
            "version": "llm-feedback-summary.v1",
            "feedback_dir": str(target),
            "total_runs": 0,
            "counts": {},
            "latest_run": {"ok": False, "failure_type": "summary_error", "error": str(e)},
            "latest_successful_feedback": None,
        }

    latest = summary.get("latest_run") if isinstance(summary.get("latest_run"), dict) else {}
    latest_stats = latest.get("call_stats") if isinstance(latest.get("call_stats"), dict) else {}
    latest_successful_feedback = (
        summary.get("latest_successful_feedback")
        if isinstance(summary.get("latest_successful_feedback"), dict)
        else None
    )
    return {
        "version": "llm-feedback-summary.v1",
        "feedback_dir": str(target),
        "total_runs": summary.get("total_runs", 0),
        "counts": summary.get("counts") if isinstance(summary.get("counts"), dict) else {},
        "latest_run": {
            "ok": latest.get("ok"),
            "failure_type": latest.get("failure_type"),
            "provider": latest.get("provider"),
            "mode": latest.get("mode"),
            "attempt": latest.get("attempt"),
            "actionable": latest.get("actionable"),
            "decision": latest.get("decision"),
            "elapsed_ms": latest.get("elapsed_ms"),
            "artifact": latest.get("artifact") or latest.get("path"),
            "error": latest.get("error"),
            "call_stats": {
                "endpoint": latest_stats.get("endpoint"),
                "http_status": latest_stats.get("http_status"),
                "error_type": latest_stats.get("error_type"),
                "total_tokens": latest_stats.get("total_tokens"),
                "generate_ms": latest_stats.get("generate_ms"),
                "response_started": latest_stats.get("response_started"),
            },
        },
        "latest_successful_feedback": latest_successful_feedback,
        "note": "This endpoint reads saved artifacts only; it does not send project data to an external LLM.",
    }


def build_runtime_readiness(
    *,
    server: Any,
    session_id: str = "{session_id}",
) -> Dict[str, Any]:
    """Build a no-network readiness snapshot for users and attached LLMs."""
    cfg = server.agent.config
    llm_cfg = cfg.llm_config()
    provider = cfg.llm_provider()
    preset = provider_preset(provider)
    preset_kind = preset.get("kind", "")
    if provider == "mock":
        runtime_kind = "mock"
    elif preset_kind == "local" or provider in {"local", "gguf"}:
        runtime_kind = "local"
    else:
        runtime_kind = "api"

    resolved_model = llm_cfg.get("model") or preset.get("model", "")
    resolved_base_url = llm_cfg.get("base_url") or preset.get("base_url", "")
    api_key_set = bool(server._provider_api_key(provider)) if runtime_kind == "api" else None
    llm = server.agent.llm
    llm_class = llm.__class__.__name__
    last_call_stats: Dict[str, Any] = {}
    stats_getter = getattr(llm, "last_call_stats", None)
    if callable(stats_getter):
        try:
            last_call_stats = stats_getter()
        except Exception:
            last_call_stats = {}

    contract = server.agent.runtime_contract(session_id=session_id)
    communication = contract.get("communication") if isinstance(contract.get("communication"), dict) else {}
    maker = contract.get("maker_mcp") if isinstance(contract.get("maker_mcp"), dict) else {}
    layer_history: List[Dict[str, Any]] = []
    context_history: List[Dict[str, Any]] = []
    runtime_metrics: List[Dict[str, Any]] = []
    runtime_metrics_evidence: Dict[str, Any] = {}
    learning_history: List[Dict[str, Any]] = []
    maker_guard_history: List[Dict[str, Any]] = []
    if session_id != "{session_id}":
        layer_history = server.session_store.get_layer_history(session_id, limit=20)
        context_history = server.session_store.get_context_sync_history(session_id, limit=3)
        runtime_metrics_evidence = runtime_metrics_from_server(server, session_id, limit=20)
        runtime_metrics = runtime_metrics_evidence.get("history", [])
        learning_history = server.session_store.get_learning_history(session_id, limit=20)
        maker_guard_history = server.session_store.get_maker_guard_history(session_id, limit=20)

    llm_probe = compact_llm_probe(server._latest_llm_probe_for_session(session_id))
    llm_call_proof = build_llm_call_proof(
        server=server,
        session_id=session_id,
        llm_probe=server._latest_llm_probe_for_session(session_id),
        last_call_stats=last_call_stats,
    )
    llm_feedback_summary = build_llm_feedback_summary()
    layer_summary = summarize_layer_events(layer_history)
    runtime_summary = summarize_runtime_metrics(runtime_metrics)
    event_bus_summary = build_runtime_event_bus_summary(server=server, session_id=session_id)
    resume_drill = (
        resume_drill_from_server(server, session_id, steps=20)
        if session_id != "{session_id}"
        else {"version": "resume-drill.v1", "status": "not_requested", "session_id": session_id}
    )
    learning_observer_summary = (
        learning_state_from_server(server, session_id, limit=20)
        if session_id != "{session_id}"
        else {"status": "not_requested"}
    )
    memory_recall = (
        memory_recall_from_server(server, session_id, limit=20)
        if session_id != "{session_id}"
        else {"status": "not_requested"}
    )
    # Phase C: extract the most-recent prompt-loader stats from the memory
    # recall summary so the evidence surface can show fragment counts
    # without leaking full prompt content. The compact view exposes
    # counters only.
    prompt_loader = _prompt_loader_from_recall(memory_recall)
    # Phase D: plan v2 and control loop summaries. We probe the
    # agent's plan and control loop state when available; otherwise
    # return the ``not_provided`` / ``no_plan`` boundary so the
    # Workbench always sees a stable shape.
    plan_v2 = _plan_v2_summary(_safe_getattr(server.agent, "plan", None))
    control_loop = _control_loop_summary(_safe_getattr(server.agent, "control_loop", None))
    layer_health = build_layer_health_snapshot(
        session_id=session_id,
        session_status=session_status_from_server(server, session_id),
        layer_summary=layer_summary,
        runtime_metrics_summary=runtime_summary,
        learning_state=learning_observer_summary,
        learning_job=learning_job_from_server(server, session_id),
        event_bus_summary=event_bus_summary,
    )
    layer_control = build_layer_control_snapshot(layer_health=layer_health)
    cos_gate = cos_gate_from_server(server, session_id)
    project_state = (
        project_state_from_server(server, session_id, layer_control=layer_control)
        if session_id != "{session_id}"
        else {"status": "not_requested"}
    )
    engineering_control = engineering_control_from_server(
        server,
        session_id,
        steps=20,
        layer_control=layer_control,
        memory_recall=memory_recall,
        runtime_metrics_summary=runtime_summary,
        project_state=project_state,
        cos_gate=cos_gate,
    )
    if session_id != "{session_id}":
        project_state = project_state_from_server(
            server,
            session_id,
            layer_control=layer_control,
            engineering_control=engineering_control,
        )
    rag_benchmark = server.rag_benchmark_status()
    rag_quality = (
        rag_benchmark.get("embedding_quality")
        if isinstance(rag_benchmark.get("embedding_quality"), dict)
        else {}
    )
    rag_closure = (
        rag_benchmark.get("closure_gate")
        if isinstance(rag_benchmark.get("closure_gate"), dict)
        else {}
    )
    # Phase B: graph-on vs graph-off evidence (opt-in, only meaningful
    # when memory.graph.enabled=true).
    try:
        graph_recall = server.rag_graph_status()
    except Exception:
        graph_recall = {
            "version": "rag-graph-on-off.v1",
            "status": "not_enabled",
            "graph_enabled": False,
            "truthfulness": "graph memory is opt-in; enable memory.graph.enabled to produce this evidence",
        }
    learning_latest = learning_history[-1] if learning_history else learning_observer_summary.get("latest")
    issues: List[Dict[str, str]] = []
    next_actions: List[str] = []

    if runtime_kind == "api" and not api_key_set:
        issues.append({
            "id": "api_key_missing",
            "severity": "blocker",
            "detail": "API provider is selected but no provider-scoped API key is configured.",
        })
        next_actions.append("Save provider API key in the GUI or POST /config/llm, then POST /llm/probe.")
    if llm_class == "UnconfiguredLLM":
        issues.append({
            "id": "llm_unconfigured",
            "severity": "blocker",
            "detail": "Runtime is intentionally unconfigured; it will fail clearly instead of falling back to mock.",
        })
    if runtime_kind == "api" and llm_probe.get("status") == "not_run":
        issues.append({
            "id": "llm_probe_missing",
            "severity": "warn",
            "detail": "Provider wiring has not been verified by a tiny probe call.",
        })
        next_actions.append("POST /llm/probe before a full Maker run.")
    if llm_probe.get("status") == "error":
        issues.append({
            "id": "llm_probe_failed",
            "severity": "blocker",
            "detail": str(llm_probe.get("error") or llm_probe.get("error_type") or "Latest LLM probe failed."),
        })
        next_actions.append("Fix provider/base URL/API key or model, then rerun POST /llm/probe.")
    if runtime_kind == "api" and llm_call_proof.get("conclusion") == "api_call_not_observed":
        issues.append({
            "id": "api_call_not_observed",
            "severity": "warn",
            "detail": "Provider is configured, but no probe/session last_call_stats endpoint has been observed yet.",
        })
        next_actions.append("Run Provider Probe or a tiny session, then verify llm_call_proof.observed_endpoint.")
    if runtime_kind == "api" and llm_call_proof.get("conclusion") == "api_call_observed_endpoint_mismatch":
        issues.append({
            "id": "api_endpoint_mismatch",
            "severity": "blocker",
            "detail": (
                f"Observed endpoint {llm_call_proof.get('observed_endpoint')}; "
                f"expected {llm_call_proof.get('expected_endpoint')}."
            ),
        })
        next_actions.append("Fix provider/base URL routing before continuing.")
    if maker.get("readiness") != "ready":
        issues.append({
            "id": "maker_mcp_not_ready",
            "severity": "warn",
            "detail": f"MakerMCP readiness is {maker.get('readiness') or 'unknown'}; remote Maker authority may be unavailable.",
        })
        next_actions.append("GET /mcp/status and use local inspection until MakerMCP is connected.")
    if session_id != "{session_id}" and not context_history:
        issues.append({
            "id": "context_sync_missing",
            "severity": "warn",
            "detail": "No compact context_sync snapshot exists yet for this session.",
        })
        next_actions.append(f"Start or resume the session, then read /sessions/{session_id}/context-sync?steps=3.")
    if layer_control.get("status") == "blocked":
        issues.append({
            "id": "layer_control_blocked",
            "severity": "blocker",
            "detail": "Layer-control signals block claims of complete Agent/Core Runtime/Learning independence.",
        })
        next_actions.append(f"Read /sessions/{session_id}/layer-control?steps=20 and apply the top corrective action.")
    elif layer_control.get("status") == "needs_action":
        issues.append({
            "id": "layer_control_needs_action",
            "severity": "warn",
            "detail": "Layer-control signals require correction before claiming the three-layer contract is fully healthy.",
        })
        next_actions.append(f"Read /sessions/{session_id}/layer-control?steps=20 and resolve warn-level signals.")
    if engineering_control.get("status") == "blocked":
        issues.append({
            "id": "engineering_control_blocked",
            "severity": "blocker",
            "detail": "Engineering-control signals block readiness claims for memory, tooling, or plan gates.",
        })
        next_actions.append(f"Read /sessions/{session_id}/engineering-control?steps=20 and apply the top corrective action.")
    elif engineering_control.get("status") == "needs_action":
        issues.append({
            "id": "engineering_control_needs_action",
            "severity": "warn",
            "detail": "Engineering-control signals require correction before claiming project control is healthy.",
        })
        next_actions.append(f"Read /sessions/{session_id}/engineering-control?steps=20 and resolve warn-level signals.")

    if not next_actions:
        next_actions.append("Proceed via runtime_advice and maker_briefing; use Evidence Bundle before detailed histories.")

    has_blocker = any(issue.get("severity") == "blocker" for issue in issues)
    has_warning = any(issue.get("severity") == "warn" for issue in issues)
    status = "blocked" if has_blocker else ("degraded" if has_warning else "ready")
    release_gate = {
        "stable_small_version": "ready" if not has_blocker else "blocked",
        "checks": [
            {"id": "provider_config", "ok": not (runtime_kind == "api" and not api_key_set)},
            {"id": "provider_probe", "ok": runtime_kind != "api" or llm_probe.get("status") == "ok"},
            {"id": "maker_mcp_evidence", "ok": maker.get("readiness") == "ready"},
            {"id": "layer_evidence", "ok": session_id == "{session_id}" or bool(layer_history)},
            {"id": "context_sync", "ok": session_id == "{session_id}" or bool(context_history)},
            {
                "id": "resume_drill",
                "ok": session_id == "{session_id}"
                or (resume_drill.get("closure_gate") or {}).get("can_claim_long_task_durable_handoff") is True,
            },
            {"id": "runtime_event_bus", "ok": event_bus_summary.get("status") in {"ready", "partial"}},
            {"id": "layer_health", "ok": layer_health.get("status") in {"ready", "active", "degraded", "missing"}},
            {"id": "layer_control", "ok": layer_control.get("status") in {"ready", "watch"}},
            {"id": "engineering_control", "ok": engineering_control.get("status") in {"ready", "watch"}},
            {"id": "cos_gate", "ok": cos_gate.get("status") in {"ready", "computed", "not_requested"}},
            {"id": "rag_benchmark", "ok": rag_benchmark.get("status") != "error" and rag_benchmark.get("budget_status") != "fail"},
            {
                "id": "rag_graph_on_off",
                "ok": graph_recall.get("status") in {"ready", "not_run", "not_enabled"},
                "graph_enabled": graph_recall.get("graph_enabled", False),
                "ratio_warm_p95": graph_recall.get("ratio_warm_p95"),
                "ratio_budget": graph_recall.get("ratio_budget", 1.5),
            },
            {
                "id": "rag_embedding_quality",
                "ok": rag_closure.get("can_claim_production_embedding_quality") is True,
            },
        ],
    }

    return {
        "version": "runtime-readiness.v1",
        "status": status,
        "session_id": session_id,
        "no_network_call": True,
        "summary": {
            "provider": provider,
            "runtime_kind": runtime_kind,
            "llm_class": llm_class,
            "model": resolved_model,
            "base_url": resolved_base_url,
            "api_key_set": api_key_set,
            "maker_readiness": maker.get("readiness"),
            "maker_connected": maker.get("connected"),
            "maker_tool_count": maker.get("tool_count"),
            "probe_status": llm_probe.get("status"),
            "probe_endpoint": llm_probe.get("endpoint") or llm_probe.get("base_url"),
            "last_call_endpoint": last_call_stats.get("endpoint"),
            "call_proof": llm_call_proof.get("conclusion"),
            "event_bus": event_bus_summary.get("status"),
            "project_state": project_state.get("status"),
            "cos_gate": cos_gate.get("mode") or cos_gate.get("status"),
            "resume_drill": resume_drill.get("status"),
            "layer_health": layer_health.get("status"),
            "layer_control": layer_control.get("status"),
            "engineering_control": engineering_control.get("status"),
            "learning_observer": learning_observer_summary.get("status"),
            "memory_recall": memory_recall.get("status"),
            "prompt_loader": prompt_loader.get("status") if isinstance(prompt_loader, dict) else "not_run",
            "plan_v2": plan_v2.get("status") if isinstance(plan_v2, dict) else "no_plan",
            "control_loop": control_loop.get("status") if isinstance(control_loop, dict) else "not_provided",
            "rag_benchmark": rag_benchmark.get("status"),
            "rag_embedding_quality": rag_quality.get("status") or "unproven",
            "graph_recall": graph_recall.get("status"),
        },
        "issues": issues,
        "next_actions": next_actions,
        "llm_probe_latest": llm_probe,
        "llm_call_proof": llm_call_proof,
        "llm_feedback_summary": {
            "version": llm_feedback_summary.get("version"),
            "total_runs": llm_feedback_summary.get("total_runs", 0),
            "counts": llm_feedback_summary.get("counts", {}),
            "latest_run": llm_feedback_summary.get("latest_run", {}),
            "latest_successful_feedback": llm_feedback_summary.get("latest_successful_feedback"),
            "note": llm_feedback_summary.get("note"),
        },
        "maker_mcp": {
            "readiness": maker.get("readiness"),
            "connected": maker.get("connected"),
            "tool_count": maker.get("tool_count"),
            "remote_identity": maker.get("remote_identity") if isinstance(maker.get("remote_identity"), dict) else {},
            "last_call": maker.get("last_call") if isinstance(maker.get("last_call"), dict) else maker.get("last_call"),
        },
        "layer_summary": layer_summary,
        "layer_health": layer_health,
        "layer_control": layer_control,
        "engineering_control": engineering_control,
        "runtime_event_bus": event_bus_summary,
        "runtime_metrics_source": runtime_metrics_evidence.get("source") if runtime_metrics_evidence else "session_store",
        "runtime_metrics_observer": runtime_metrics_evidence.get("observer") if runtime_metrics_evidence else {"status": "not_requested"},
        "runtime_metrics_summary": runtime_summary,
        "project_state": project_state,
        "cos_gate": cos_gate,
        "resume_drill": resume_drill,
        "learning_observer": learning_observer_summary,
        "memory_recall": memory_recall,
        "prompt_loader": prompt_loader,
        "plan_v2": plan_v2,
        "control_loop": control_loop,
        "rag_benchmark": rag_benchmark,
        "graph_recall": graph_recall,
        "latest_context_sync": context_history[-1] if context_history else None,
        "learning_latest": learning_latest,
        "maker_guard_latest": maker_guard_history[-1] if maker_guard_history else None,
        "release_gate": release_gate,
        "endpoints": {
            key: communication.get(key)
            for key in [
                "portable_runtime",
                "runtime_readiness",
                "quickstart_bundle",
                "evidence_bundle",
                "runtime_advice",
                "maker_briefing",
                "maker_guard",
                "context_sync",
                "resume_drill",
                "runtime_metrics",
                "layer_health",
                "layer_control",
                "engineering_control",
                "project_writeback",
                "learning_status",
                "learning_cancel",
                "learning_retry",
                "rag_benchmark",
                "rag_quality",
                "llm_probe",
                "llm_probe_history",
                "llm_feedback_summary",
                "mcp_status",
                "mcp_tools",
            ]
            if communication.get(key)
        },
        "token_rule": "Read portable runtime and runtime readiness first; probe only when provider evidence is missing or stale.",
    }


def build_portable_runtime_status(*, server: Any) -> Dict[str, Any]:
    """Build a no-network status packet for the self-contained Agent folder."""
    cfg = server.agent.config
    diagnostics = portable_diagnostics(
        cfg.base_dir,
        configured_portable_root=cfg.portable_root(),
    )
    diagnostics["config"] = {
        "config_path": str(cfg.path.resolve()),
        "config_base_dir": str(cfg.base_dir),
        "project_root": str(cfg.project_root()),
        "storage_root": str(cfg.storage_root()),
        "portable_root": str(cfg.portable_root()),
        "local_model_path": str(cfg.local_model_path()),
    }
    diagnostics["endpoints"] = {
        "portable": "/runtime/portable",
        "readiness": "/runtime/readiness?session_id={session_id}",
        "maker_setup_status": "/maker/setup-status",
        "evidence_bundle": "/sessions/{session_id}/evidence?steps=20",
    }
    diagnostics["next_action"] = (
        "Fix blocked portable paths before real Maker development testing."
        if diagnostics.get("status") == "blocked"
        else "Portable runtime paths are observable; continue with Maker setup/readiness checks."
    )
    return diagnostics


def _safe_getattr(obj: Any, name: str, default: Any = None) -> Any:
    """Safe attribute accessor that returns ``default`` when the
    attribute is missing or raises. The evidence bundle is built
    even when the agent is not fully wired (e.g. smoke tests with
    a stub agent).
    """
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _prompt_loader_from_recall(memory_recall: Any) -> Dict[str, Any]:
    """Return a compact prompt-loader status payload derived from
    ``memory_recall`` evidence. The recall summary already carries
    per-call ``BudgetStats`` (including fragment_count / deferred_count
    / stubbed_count when ``loader.enabled=true``). This helper extracts
    just the compact counters and never leaks full prompt content.
    """
    if not isinstance(memory_recall, dict):
        return {"version": "prompt-loader.v1", "status": "not_run"}
    # Some recall summaries nest per-call stats under ``latest`` or
    # ``recall_metrics``; we probe each known shape.
    candidates: List[Dict[str, Any]] = []
    latest = memory_recall.get("latest") if isinstance(memory_recall.get("latest"), dict) else None
    if latest:
        candidates.append(latest)
    if isinstance(memory_recall.get("recall_metrics"), dict):
        candidates.append(memory_recall["recall_metrics"])
    if isinstance(memory_recall.get("budget_stats"), dict):
        candidates.append(memory_recall["budget_stats"])
    # Pick the most recent candidate that has at least one fragment field.
    picked: Dict[str, Any] = {}
    for c in candidates:
        if "fragment_count" in c or "deferred_count" in c or "stubbed_count" in c:
            picked = c
            break
    if not picked:
        return {"version": "prompt-loader.v1", "status": "not_run"}
    return {
        "version": "prompt-loader.v1",
        "status": "ready" if picked.get("fragment_count", 0) > 0 else "not_run",
        "fragment_count": int(picked.get("fragment_count", 0)),
        "deferred_count": int(picked.get("deferred_count", 0)),
        "stubbed_count": int(picked.get("stubbed_count", 0)),
        "graph_recall_hits": int(picked.get("graph_recall_hits", 0)),
        "compression_applied": bool(picked.get("compression_applied", False)),
    }


def _plan_v2_summary(plan: Any) -> Dict[str, Any]:
    """Compact plan v2 evidence payload.

    The plan may be ``None`` (no approved plan yet) or a dict carrying
    either ``plan-format.v1`` or ``plan-format.v2``. We never leak the
    full plan; only counters and the latest verdict.
    """
    if not isinstance(plan, dict):
        return {"version": "plan-format.v2", "status": "no_plan"}
    version = str(plan.get("version") or "plan-format.v1")
    progress = plan.get("progress") if isinstance(plan.get("progress"), dict) else {}
    counts = progress.get("counts") if isinstance(progress.get("counts"), dict) else {}
    return {
        "version": "plan-format.v2",
        "status": progress.get("overall") or "draft",
        "source_version": version,
        "current_step": progress.get("current_step"),
        "counts": {
            "pending": int(counts.get("pending", 0)),
            "in_progress": int(counts.get("in_progress", 0)),
            "done": int(counts.get("done", 0)),
            "skipped": int(counts.get("skipped", 0)),
            "failed": int(counts.get("failed", 0)),
        },
        "control_signal": plan.get("control_signal") if isinstance(plan.get("control_signal"), dict) else None,
    }


def _control_loop_summary(control_loop: Any) -> Dict[str, Any]:
    """Compact ControlLoop evidence payload. Reads ``last_signal()`` and
    ``last_verdict()`` when present; otherwise returns the ``not_run``
    boundary. Never invents a verdict.
    """
    if control_loop is None:
        return {"version": "control-loop.v1", "status": "not_provided"}
    last_signal = 0.0
    last_verdict = "stable"
    try:
        if hasattr(control_loop, "last_signal"):
            last_signal = float(control_loop.last_signal() or 0.0)
        if hasattr(control_loop, "last_verdict"):
            last_verdict = str(control_loop.last_verdict() or "stable")
    except Exception:
        return {"version": "control-loop.v1", "status": "error"}
    return {
        "version": "control-loop.v1",
        "status": "ready",
        "last_signal": round(last_signal, 4),
        "last_verdict": last_verdict,
    }


def build_shared_memory_policy_summary(*, server: Any, agent_id: str = "default") -> Dict[str, Any]:
    """Return a compact, non-secret summary of the current shared-memory boundary."""
    try:
        memory_manager = getattr(server.agent, "memory_manager", None)
        cold = getattr(memory_manager, "cold", None)
        if cold is not None and hasattr(cold, "shared_policy"):
            policy = cold.shared_policy(agent_id)
            summary = policy.to_summary()
            if hasattr(cold, "shared_outcome_summary"):
                summary["outcomes"] = cold.shared_outcome_summary()
        else:
            summary = {
                "agent_id": agent_id,
                "read_profiles": ["*"],
                "write_profiles": ["*"],
                "include_general": True,
                "can_read_shared": True,
                "can_read_public": True,
                "can_read_private_own": True,
                "can_read_private_other": False,
                "default_visibility": "private",
                "boundary": "owner_private_plus_explicit_shared",
                "outcomes": {
                    "promotion_rule": "verified_positive_task_evidence_without_unresolved_conflict",
                    "demotion_rule": "stale_or_regression_or_repeated_misleading_evidence",
                    "default_visibility_rule": "private_until_verified",
                    "conflict_count": 0,
                    "unresolved_conflict_count": 0,
                },
            }
        vector_cfg = server.agent.config.vector_index_config()
        profile_policies = vector_cfg.get("profile_policies") if isinstance(vector_cfg, dict) else {}
        summary["profile_policy_count"] = len(profile_policies) if isinstance(profile_policies, dict) else 0
        summary["storage"] = "cold_memory"
        summary["status"] = "ready"
        return summary
    except Exception as exc:
        return {
            "agent_id": agent_id,
            "status": "error",
            "error": str(exc),
            "boundary": "unknown",
        }


def build_runtime_event_bus_summary(*, server: Any, session_id: str = "{session_id}") -> Dict[str, Any]:
    """Return compact observability for the in-process runtime event buses."""
    def _stats(bus: Any) -> Dict[str, Any]:
        if bus is None:
            return {"status": "missing"}
        try:
            stats = bus.stats() if hasattr(bus, "stats") else {}
            return {"status": "ready", **(stats if isinstance(stats, dict) else {})}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _count(bus: Any, **criteria: Any) -> int:
        if bus is None or not hasattr(bus, "replay"):
            return 0
        try:
            return len(bus.replay(limit=0, **criteria))
        except Exception:
            return 0

    server_bus = getattr(server, "event_bus", None)
    agent_bus = getattr(getattr(server, "agent", None), "event_bus", None)
    server_bus_stats = _stats(server_bus)
    agent_bus_stats = _stats(agent_bus)
    observer_error_count = int(server_bus_stats.get("observer_error_count") or 0) + int(
        agent_bus_stats.get("observer_error_count") or 0
    )
    summary = {
        "status": "ready" if server_bus is not None and agent_bus is not None else "partial",
        "observer_health": "degraded" if observer_error_count else "ready",
        "observer_error_count": observer_error_count,
        "server_bus": server_bus_stats,
        "agent_bus": agent_bus_stats,
        "runtime_metrics_observer": (
            getattr(server.runtime_metrics_observer, "stats", lambda: {"status": "missing"})()
            if getattr(server, "runtime_metrics_observer", None) is not None
            else {"status": "missing"}
        ),
        "project_observer": (
            getattr(server.project_observer, "stats", lambda: {"status": "missing"})()
            if getattr(server, "project_observer", None) is not None
            else {"status": "missing"}
        ),
        "learning_observer": (
            getattr(server.learning_observer, "stats", lambda: {"status": "missing"})()
            if getattr(server, "learning_observer", None) is not None
            else {"status": "missing"}
        ),
        "memory_observer": (
            getattr(server.memory_observer, "stats", lambda: {"status": "missing"})()
            if getattr(server, "memory_observer", None) is not None
            else {"status": "missing"}
        ),
        "session_id": session_id,
        "session_events": 0,
        "session_layer_events": 0,
        "compatibility": "sse_sqlite_shape_preserved",
    }
    if session_id != "{session_id}":
        summary["session_events"] = _count(server_bus, session_id=session_id)
        summary["session_layer_events"] = _count(server_bus, session_id=session_id, event_type="layer")
        summary["agent_session_events"] = _count(agent_bus, session_id=session_id)
        summary["agent_session_layer_events"] = _count(agent_bus, session_id=session_id, event_type="layer")
    return summary


def cos_gate_from_server(server: Any, session_id: str) -> Dict[str, Any]:
    """Return the latest COS Gate 0 decision for a session."""
    if session_id == "{session_id}":
        return {
            "version": COS_GATE_VERSION,
            "status": "not_requested",
            "source": "not_requested",
            "event_count": 0,
        }
    history_getter = getattr(server.session_store, "get_cos_gate_history", None)
    history: List[Dict[str, Any]] = []
    if callable(history_getter):
        history = history_getter(session_id, limit=20)
    if history:
        latest = dict(history[-1])
        latest["status"] = "ready"
        latest["source"] = "session_store_cos_gate"
        latest["event_count"] = len(history)
        return latest

    stored = server.session_store.get_session(session_id)
    task = (stored or {}).get("task", "")
    if task:
        computed = classify_cos_gate(task, trigger="session_task_fallback").to_dict()
        computed["status"] = "computed"
        computed["source"] = "computed_from_session_task"
        computed["event_count"] = 0
        return computed
    return {
        "version": COS_GATE_VERSION,
        "status": "missing",
        "source": "missing",
        "event_count": 0,
    }


def build_session_evidence_bundle(
    *,
    server: Any,
    session_id: str,
    steps: int = 20,
) -> Dict[str, Any]:
    """Build one compact current-state packet for attached coding agents."""
    stored = server.session_store.get_session(session_id) if session_id != "{session_id}" else {}
    task = (stored or {}).get("task", "") if session_id != "{session_id}" else ""
    contract = server.agent.runtime_contract(session_id=session_id)
    communication = contract.get("communication") if isinstance(contract.get("communication"), dict) else {}
    maker_mcp = contract.get("maker_mcp") if isinstance(contract.get("maker_mcp"), dict) else {}
    maker_briefing = server.agent.maker_briefing(session_id=session_id, task=task)

    context_history: List[Dict[str, Any]] = []
    runtime_metrics: List[Dict[str, Any]] = []
    runtime_metrics_evidence: Dict[str, Any] = {}
    learning_history: List[Dict[str, Any]] = []
    layer_history: List[Dict[str, Any]] = []
    maker_guard_history: List[Dict[str, Any]] = []
    llm_probe_history: List[Dict[str, Any]] = []
    if session_id != "{session_id}":
        context_history = server.session_store.get_context_sync_history(session_id, limit=min(steps, 20))
        runtime_metrics_evidence = runtime_metrics_from_server(server, session_id, limit=steps)
        runtime_metrics = runtime_metrics_evidence.get("history", [])
        learning_history = server.session_store.get_learning_history(session_id, limit=steps)
        layer_history = server.session_store.get_layer_history(session_id, limit=steps)
        maker_guard_history = server.session_store.get_maker_guard_history(session_id, limit=steps)
        llm_probe_history = server.session_store.get_llm_probe_history(session_id, limit=steps)

    runtime_summary = summarize_runtime_metrics(runtime_metrics)
    layer_summary = summarize_layer_events(layer_history)
    latest_context_sync = context_history[-1] if context_history else None
    continuation = summarize_continuation(latest_context_sync)
    resume_drill = resume_drill_from_server(server, session_id, steps=steps)
    learning_latest = learning_history[-1] if learning_history else None
    maker_guard_latest = maker_guard_history[-1] if maker_guard_history else None
    llm_probe_latest = server._latest_llm_probe_for_session(session_id)
    llm_call_proof = build_llm_call_proof(
        server=server,
        session_id=session_id,
        llm_probe=llm_probe_latest,
    )
    llm_feedback_summary = build_llm_feedback_summary()
    runtime_advice = build_runtime_advice(
        maker_briefing=maker_briefing,
        maker_guard_history=maker_guard_history,
        runtime_metrics_summary=runtime_summary,
        learning_latest=learning_latest,
        latest_context_sync=latest_context_sync,
        llm_probe_latest=llm_probe_latest,
    )
    maker_setup = server.maker_setup_status(check_latest=False)
    shared_memory = build_shared_memory_policy_summary(server=server)
    event_bus_summary = build_runtime_event_bus_summary(server=server, session_id=session_id)
    learning_observer_summary = learning_state_from_server(server, session_id, limit=steps)
    memory_recall = memory_recall_from_server(server, session_id, limit=steps)
    # Phase C/D: extract compact summaries for the new evidence fields.
    prompt_loader = _prompt_loader_from_recall(memory_recall)
    try:
        graph_recall = server.rag_graph_status()
    except Exception:
        graph_recall = {"version": "rag-graph-on-off.v1", "status": "not_enabled", "graph_enabled": False}
    plan_v2 = _plan_v2_summary(_safe_getattr(server.agent, "plan", None))
    control_loop = _control_loop_summary(_safe_getattr(server.agent, "control_loop", None))
    layer_health = build_layer_health_snapshot(
        session_id=session_id,
        session_status=session_status_from_server(server, session_id),
        layer_summary=layer_summary,
        runtime_metrics_summary=runtime_summary,
        learning_state=learning_observer_summary,
        learning_job=learning_job_from_server(server, session_id),
        event_bus_summary=event_bus_summary,
    )
    layer_control = build_layer_control_snapshot(layer_health=layer_health)
    cos_gate = cos_gate_from_server(server, session_id)
    project_state = project_state_from_server(
        server,
        session_id,
        runtime_advice=runtime_advice,
        layer_control=layer_control,
    )
    engineering_control = engineering_control_from_server(
        server,
        session_id,
        steps=steps,
        layer_control=layer_control,
        memory_recall=memory_recall,
        runtime_metrics_summary=runtime_summary,
        project_state=project_state,
        cos_gate=cos_gate,
    )
    project_state = project_state_from_server(
        server,
        session_id,
        runtime_advice=runtime_advice,
        layer_control=layer_control,
        engineering_control=engineering_control,
    )
    project_writeback = project_writeback_from_server(server, session_id, project_state)
    rag_benchmark = server.rag_benchmark_status()
    if learning_latest is None:
        learning_latest = learning_observer_summary.get("latest")

    endpoint_keys = [
        "onboarding_bundle",
        "quickstart_bundle",
        "portable_runtime",
        "runtime_readiness",
        "handoff_bundle",
        "runtime_contract",
        "maker_briefing",
        "evidence_bundle",
        "runtime_advice",
        "runtime_metrics",
        "layer_health",
        "layer_control",
        "engineering_control",
        "resume_drill",
        "project_state",
        "project_writeback",
        "learning_status",
        "learning_cancel",
        "learning_retry",
        "rag_benchmark",
        "rag_quality",
        "maker_guard",
        "context_sync",
        "llm_probe",
        "llm_probe_history",
        "llm_feedback_summary",
        "maker_setup_status",
        "maker_setup_status_markdown",
        "maker_tool_audit",
        "maker_project_select",
        "maker_auth_prepare",
        "maker_auth_complete",
        "mcp_status",
        "mcp_tools",
    ]
    return {
        "version": "session-evidence.v1",
        "session_id": session_id,
        "task": task,
        "cos_gate": cos_gate,
        "runtime_advice": runtime_advice,
        "maker_mcp": {
            "readiness": maker_mcp.get("readiness"),
            "connected": maker_mcp.get("connected"),
            "tool_count": maker_mcp.get("tool_count"),
            "top_tools": (maker_mcp.get("top_tools") or [])[:6]
                if isinstance(maker_mcp.get("top_tools"), list)
                else [],
            "remote_identity": maker_mcp.get("remote_identity")
                if isinstance(maker_mcp.get("remote_identity"), dict)
                else {},
            "last_call": maker_mcp.get("last_call")
                if isinstance(maker_mcp.get("last_call"), dict)
                else maker_mcp.get("last_call"),
        },
        "maker_setup": {
            "readiness": maker_setup.get("readiness"),
            "blockers": maker_setup.get("blockers", []),
            "warnings": maker_setup.get("warnings", []),
            "project": maker_setup.get("project", {}),
            "auth": maker_setup.get("auth", {}),
            "maker_package": maker_setup.get("maker_package", {}),
        },
        "maker_tool_audit": maker_setup.get("tool_audit", {}),
        "maker_briefing": maker_briefing,
        "latest_context_sync": latest_context_sync,
        "continuation": continuation,
        "resume_drill": resume_drill,
        "layer_summary": layer_summary,
        "layer_health": layer_health,
        "layer_control": layer_control,
        "engineering_control": engineering_control,
        "runtime_event_bus": event_bus_summary,
        "runtime_metrics_source": runtime_metrics_evidence.get("source") if runtime_metrics_evidence else "session_store",
        "runtime_metrics_observer": runtime_metrics_evidence.get("observer") if runtime_metrics_evidence else {"status": "not_requested"},
        "runtime_metrics_summary": runtime_summary,
        "project_state": project_state,
        "project_writeback": project_writeback,
        "shared_memory": shared_memory,
        "learning_observer": learning_observer_summary,
        "memory_recall": memory_recall,
        "prompt_loader": prompt_loader,
        "plan_v2": plan_v2,
        "control_loop": control_loop,
        "graph_recall": graph_recall,
        "rag_benchmark": rag_benchmark,
        "learning_latest": learning_latest,
        "maker_guard_latest": maker_guard_latest,
        "llm_probe_latest": compact_llm_probe(llm_probe_latest),
        "llm_call_proof": llm_call_proof,
        "llm_feedback_summary": {
            "version": llm_feedback_summary.get("version"),
            "total_runs": llm_feedback_summary.get("total_runs", 0),
            "counts": llm_feedback_summary.get("counts", {}),
            "latest_run": llm_feedback_summary.get("latest_run", {}),
            "latest_successful_feedback": llm_feedback_summary.get("latest_successful_feedback"),
            "note": llm_feedback_summary.get("note"),
        },
        "counts": {
            "context_sync": len(context_history),
            "runtime_metrics": len(runtime_metrics),
            "memory_recall": memory_recall.get("event_count", 0),
            "learning": len(learning_history),
            "layer": len(layer_history),
            "maker_guard": len(maker_guard_history),
            "llm_probe": len(llm_probe_history),
            "cos_gate": cos_gate.get("event_count", 0),
        },
        "endpoints": {
            key: communication.get(key)
            for key in endpoint_keys
            if communication.get(key)
        },
        "token_rule": "Use this evidence bundle before fetching detailed histories or raw SSE.",
    }


def render_session_evidence_markdown(bundle: Dict[str, Any]) -> str:
    """Render the compact session evidence bundle as a pasteable agent card."""
    advice = bundle.get("runtime_advice") if isinstance(bundle.get("runtime_advice"), dict) else {}
    maker_mcp = bundle.get("maker_mcp") if isinstance(bundle.get("maker_mcp"), dict) else {}
    maker_setup = bundle.get("maker_setup") if isinstance(bundle.get("maker_setup"), dict) else {}
    maker_tool_audit = bundle.get("maker_tool_audit") if isinstance(bundle.get("maker_tool_audit"), dict) else {}
    briefing = bundle.get("maker_briefing") if isinstance(bundle.get("maker_briefing"), dict) else {}
    selected_template = (
        briefing.get("selected_template")
        if isinstance(briefing.get("selected_template"), dict)
        else {}
    )
    latest_context = (
        bundle.get("latest_context_sync")
        if isinstance(bundle.get("latest_context_sync"), dict)
        else {}
    )
    continuation = bundle.get("continuation") if isinstance(bundle.get("continuation"), dict) else {}
    resume_drill = bundle.get("resume_drill") if isinstance(bundle.get("resume_drill"), dict) else {}
    resume_capabilities = (
        resume_drill.get("capability_levels")
        if isinstance(resume_drill.get("capability_levels"), dict)
        else {}
    )
    durable_resume = (
        resume_capabilities.get("durable_handoff")
        if isinstance(resume_capabilities.get("durable_handoff"), dict)
        else {}
    )
    warm_resume = (
        resume_capabilities.get("warm_process")
        if isinstance(resume_capabilities.get("warm_process"), dict)
        else {}
    )
    hot_resume = (
        resume_capabilities.get("hot_tool_call")
        if isinstance(resume_capabilities.get("hot_tool_call"), dict)
        else {}
    )
    runtime_summary = (
        bundle.get("runtime_metrics_summary")
        if isinstance(bundle.get("runtime_metrics_summary"), dict)
        else {}
    )
    layer_summary = bundle.get("layer_summary") if isinstance(bundle.get("layer_summary"), dict) else {}
    layer_health = bundle.get("layer_health") if isinstance(bundle.get("layer_health"), dict) else {}
    layer_health_layers = (
        layer_health.get("layers")
        if isinstance(layer_health.get("layers"), dict)
        else {}
    )
    layer_health_summary = (
        layer_health.get("summary")
        if isinstance(layer_health.get("summary"), dict)
        else {}
    )
    layer_control = bundle.get("layer_control") if isinstance(bundle.get("layer_control"), dict) else {}
    layer_control_actions = (
        layer_control.get("corrective_actions")
        if isinstance(layer_control.get("corrective_actions"), list)
        else []
    )
    engineering_control = (
        bundle.get("engineering_control")
        if isinstance(bundle.get("engineering_control"), dict)
        else {}
    )
    engineering_control_summary = (
        engineering_control.get("summary")
        if isinstance(engineering_control.get("summary"), dict)
        else {}
    )
    engineering_control_actions = (
        engineering_control.get("corrective_actions")
        if isinstance(engineering_control.get("corrective_actions"), list)
        else []
    )
    event_bus = bundle.get("runtime_event_bus") if isinstance(bundle.get("runtime_event_bus"), dict) else {}
    server_bus = event_bus.get("server_bus") if isinstance(event_bus.get("server_bus"), dict) else {}
    agent_bus = event_bus.get("agent_bus") if isinstance(event_bus.get("agent_bus"), dict) else {}
    runtime_observer = (
        event_bus.get("runtime_metrics_observer")
        if isinstance(event_bus.get("runtime_metrics_observer"), dict)
        else {}
    )
    project_observer = (
        event_bus.get("project_observer")
        if isinstance(event_bus.get("project_observer"), dict)
        else {}
    )
    learning_bus_observer = (
        event_bus.get("learning_observer")
        if isinstance(event_bus.get("learning_observer"), dict)
        else {}
    )
    memory_bus_observer = (
        event_bus.get("memory_observer")
        if isinstance(event_bus.get("memory_observer"), dict)
        else {}
    )
    latest_by_layer = (
        layer_summary.get("latest_by_layer")
        if isinstance(layer_summary.get("latest_by_layer"), dict)
        else {}
    )
    token_cache = (
        runtime_summary.get("token_cache")
        if isinstance(runtime_summary.get("token_cache"), dict)
        else {}
    )
    tool_ranking = (
        runtime_summary.get("tool_ranking")
        if isinstance(runtime_summary.get("tool_ranking"), dict)
        else {}
    )
    learning = bundle.get("learning_latest") if isinstance(bundle.get("learning_latest"), dict) else {}
    learning_observer = (
        bundle.get("learning_observer")
        if isinstance(bundle.get("learning_observer"), dict)
        else {}
    )
    if not learning and isinstance(learning_observer.get("latest"), dict):
        learning = learning_observer.get("latest") or {}
    memory_recall = bundle.get("memory_recall") if isinstance(bundle.get("memory_recall"), dict) else {}
    rag_benchmark = bundle.get("rag_benchmark") if isinstance(bundle.get("rag_benchmark"), dict) else {}
    rag_metrics = (
        rag_benchmark.get("metrics")
        if isinstance(rag_benchmark.get("metrics"), dict)
        else {}
    )
    rag_quality = (
        rag_benchmark.get("embedding_quality")
        if isinstance(rag_benchmark.get("embedding_quality"), dict)
        else {}
    )
    memory_latest = (
        memory_recall.get("latest")
        if isinstance(memory_recall.get("latest"), dict)
        else {}
    )
    memory_totals = (
        memory_recall.get("totals")
        if isinstance(memory_recall.get("totals"), dict)
        else {}
    )
    memory_latency = (
        memory_recall.get("max_latency")
        if isinstance(memory_recall.get("max_latency"), dict)
        else {}
    )
    guard = bundle.get("maker_guard_latest") if isinstance(bundle.get("maker_guard_latest"), dict) else {}
    probe = bundle.get("llm_probe_latest") if isinstance(bundle.get("llm_probe_latest"), dict) else {}
    call_proof = bundle.get("llm_call_proof") if isinstance(bundle.get("llm_call_proof"), dict) else {}
    feedback_summary = (
        bundle.get("llm_feedback_summary")
        if isinstance(bundle.get("llm_feedback_summary"), dict)
        else {}
    )
    shared_memory = bundle.get("shared_memory") if isinstance(bundle.get("shared_memory"), dict) else {}
    project_state = bundle.get("project_state") if isinstance(bundle.get("project_state"), dict) else {}
    project_control = (
        project_state.get("project_control")
        if isinstance(project_state.get("project_control"), dict)
        else {}
    )
    project_writeback = (
        bundle.get("project_writeback")
        if isinstance(bundle.get("project_writeback"), dict)
        else {}
    )
    cos_gate = bundle.get("cos_gate") if isinstance(bundle.get("cos_gate"), dict) else {}
    latest_feedback_run = (
        feedback_summary.get("latest_run")
        if isinstance(feedback_summary.get("latest_run"), dict)
        else {}
    )
    latest_feedback = (
        feedback_summary.get("latest_successful_feedback")
        if isinstance(feedback_summary.get("latest_successful_feedback"), dict)
        else {}
    )
    counts = bundle.get("counts") if isinstance(bundle.get("counts"), dict) else {}
    endpoints = bundle.get("endpoints") if isinstance(bundle.get("endpoints"), dict) else {}
    reasons = advice.get("reasons") if isinstance(advice.get("reasons"), list) else []
    top_tools = maker_mcp.get("top_tools") if isinstance(maker_mcp.get("top_tools"), list) else []
    remote_identity = (
        maker_mcp.get("remote_identity")
        if isinstance(maker_mcp.get("remote_identity"), dict)
        else {}
    )
    last_call = maker_mcp.get("last_call") if isinstance(maker_mcp.get("last_call"), dict) else {}
    suggested_tools = briefing.get("suggested_tools") if isinstance(briefing.get("suggested_tools"), list) else []
    snapshot = latest_context.get("snapshot") if isinstance(latest_context.get("snapshot"), dict) else {}
    feedback_first_change = (
        latest_feedback.get("one_change_to_do_first")
        if isinstance(latest_feedback.get("one_change_to_do_first"), dict)
        else {}
    )

    lines = [
        "# TTMEvolve Session Evidence",
        "",
        "Use this compact card before fetching detailed histories or raw SSE.",
        "",
        "## Session",
        f"- session_id: `{bundle.get('session_id') or '-'}`",
        f"- task: {bundle.get('task') or snapshot.get('task') or '-'}",
        f"- version: `{bundle.get('version') or '-'}`",
        "",
        "## Next Action",
        f"- status: `{advice.get('status') or '-'}`",
        f"- priority: `{advice.get('priority') or '-'}`",
        f"- next_action: {advice.get('next_action') or '-'}",
    ]
    for reason in reasons[:3]:
        lines.append(f"- reason: {reason}")

    lines.extend([
        "",
        "## COS Gate",
        f"- declaration: {cos_gate.get('declaration') or '-'}",
        f"- task_type: `{cos_gate.get('task_type') or '-'}` level=`{cos_gate.get('level') or '-'}`",
        f"- mode: `{cos_gate.get('mode') or '-'}` understanding=`{cos_gate.get('understanding_status') or '-'}`",
        f"- source: `{cos_gate.get('source') or '-'}` events=`{cos_gate.get('event_count', 0)}`",
        f"- required_gates: `{', '.join(str(item) for item in (cos_gate.get('required_gates') or [])) or '-'}`",
        "",
        "## Maker Authority",
        f"- mcp_readiness: `{maker_mcp.get('readiness') or briefing.get('readiness') or '-'}`",
        f"- mcp_connected: `{maker_mcp.get('connected')}`",
        f"- mcp_tool_count: `{maker_mcp.get('tool_count') if maker_mcp.get('tool_count') is not None else '-'}`",
        f"- setup_readiness: `{maker_setup.get('readiness') or '-'}` blockers=`{', '.join(maker_setup.get('blockers') or []) or '-'}`",
        f"- tool_audit: `{'ok' if maker_tool_audit.get('ok') else 'needs_review'}` remote_tools=`{maker_tool_audit.get('remote_tool_count') if maker_tool_audit else '-'}`",
        f"- remote_identity: `{remote_identity.get('status') or '-'}`",
        f"- last_call: tool=`{last_call.get('tool') or '-'}` ok=`{last_call.get('ok') if last_call else '-'}`",
        f"- authority: `{briefing.get('authority') or '-'}`",
        f"- flow: `{selected_template.get('id') or '-'}`",
        f"- first_action: {briefing.get('recommended_first_action') or '-'}",
    ])
    top_tool_names = [
        str(tool.get("name"))
        for tool in top_tools[:6]
        if isinstance(tool, dict) and tool.get("name")
    ]
    if top_tool_names:
        lines.append(f"- mcp_top_tools: {', '.join(top_tool_names)}")
    if suggested_tools:
        lines.append(f"- suggested_tools: {', '.join(str(tool) for tool in suggested_tools[:4])}")

    lines.extend([
        "",
        "## Project State",
        f"- status: `{project_state.get('status') or '-'}` source=`{project_state.get('source') or '-'}`",
        f"- next_action: {project_state.get('next_action') or '-'}",
        f"- next_focus: {project_state.get('next_focus') or '-'}",
        f"- goal: `{project_state.get('goal_overall') or '-'}` plan=`{project_state.get('plan_verdict') or '-'}` last_tool=`{project_state.get('last_tool') or '-'}`",
        f"- risks: {', '.join(project_state.get('risk_flags') or []) or '-'}",
        f"- project_control: `{project_control.get('status') or '-'}` next=`{project_control.get('next_action') or '-'}` verification=`{(project_control.get('verification') or {}).get('status') if isinstance(project_control.get('verification'), dict) else '-'}`",
        f"- engineering_control: `{engineering_control.get('status') or '-'}` decision=`{engineering_control.get('decision') or '-'}` actions=`{len(engineering_control_actions)}`",
        f"- memory_due: {', '.join(str(item.get('file')) for item in (project_control.get('memory_updates_due') or []) if isinstance(item, dict) and item.get('file')) or '-'}",
        f"- project_writeback: `{project_writeback.get('status') or '-'}` applicable=`{project_writeback.get('applicable')}` files=`{', '.join(project_writeback.get('files') or []) or '-'}`",
    ])

    lines.extend(["", "## Layer Communication"])
    for layer in ["agent", "runtime", "learning"]:
        latest = latest_by_layer.get(layer) if isinstance(latest_by_layer.get(layer), dict) else {}
        health = layer_health_layers.get(layer) if isinstance(layer_health_layers.get(layer), dict) else {}
        lines.append(
            f"- {layer}: state=`{latest.get('state') or '-'}` event=`{latest.get('event') or '-'}` "
            f"health=`{health.get('health') or '-'}` route=`{latest.get('source_layer') or '-'}->{latest.get('target_layer') or '-'}`"
        )
    lines.append(f"- layer_events: `{layer_summary.get('event_count') or 0}`")
    lines.append(
        f"- layer_health: `{layer_health.get('status') or '-'}` "
        f"queue_depth=`{layer_health_summary.get('learning_queue_depth') if layer_health_summary else '-'}` "
        f"max_latency_ms=`{layer_health_summary.get('max_latency_ms') if layer_health_summary else '-'}`"
    )
    lines.append(
        f"- layer_control: `{layer_control.get('status') or '-'}` "
        f"decision=`{layer_control.get('decision') or '-'}` "
        f"actions=`{len(layer_control_actions)}`"
    )
    lines.extend([
        "",
        "## Runtime Event Bus",
        f"- status: `{event_bus.get('status') or '-'}` compatibility=`{event_bus.get('compatibility') or '-'}`",
        f"- observer_health: `{event_bus.get('observer_health') or '-'}` observer_errors=`{event_bus.get('observer_error_count') if event_bus.get('observer_error_count') is not None else '-'}`",
        f"- server_bus: history=`{server_bus.get('history_size') if server_bus else '-'}` subscribers=`{server_bus.get('subscriber_count') if server_bus else '-'}` limit=`{server_bus.get('history_limit') if server_bus else '-'}`",
        f"- agent_bus: history=`{agent_bus.get('history_size') if agent_bus else '-'}` subscribers=`{agent_bus.get('subscriber_count') if agent_bus else '-'}` limit=`{agent_bus.get('history_limit') if agent_bus else '-'}`",
        f"- session_events: server=`{event_bus.get('session_events')}` agent=`{event_bus.get('agent_session_events')}` layer_server=`{event_bus.get('session_layer_events')}` layer_agent=`{event_bus.get('agent_session_layer_events')}`",
        f"- observers: runtime=`{runtime_observer.get('status') or '-'}` project=`{project_observer.get('status') or '-'}` learning=`{learning_bus_observer.get('status') or '-'}` memory=`{memory_bus_observer.get('status') or '-'}`",
    ])

    lines.extend([
        "",
        "## Latest Evidence",
        f"- context_revision: `{latest_context.get('revision') if latest_context else '-'}`",
        f"- context_signature: `{latest_context.get('signature') if latest_context else '-'}`",
        f"- guard: `{guard.get('decision') or '-'}` tool=`{guard.get('tool') or '-'}`",
        f"- learning: `{learning.get('event') or learning.get('state') or '-'}` state=`{learning.get('state') or '-'}`",
        f"- llm_probe: `{probe.get('status') or 'not_run'}` provider=`{probe.get('provider') or '-'}` endpoint=`{probe.get('endpoint') or probe.get('base_url') or '-'}`",
        f"- llm_call_proof: `{call_proof.get('conclusion') or '-'}` source=`{call_proof.get('evidence_source') or '-'}` observed=`{call_proof.get('observed_endpoint') or '-'}` expected=`{call_proof.get('expected_endpoint') or '-'}`",
        f"- llm_feedback: runs=`{feedback_summary.get('total_runs', 0)}` latest=`{latest_feedback_run.get('failure_type') or ('ok' if latest_feedback_run.get('ok') else '-')}` actionable=`{latest_feedback_run.get('actionable')}`",
        f"- runtime_events: `{runtime_summary.get('event_count') if runtime_summary else 0}`",
        f"- llm_total_tokens: `{runtime_summary.get('llm_total_tokens') if runtime_summary else 0}`",
        f"- token_cache: hits=`{token_cache.get('hits')}` misses=`{token_cache.get('misses')}` size=`{token_cache.get('size')}`",
        f"- tool_ranking: selected=`{tool_ranking.get('selected_count')}` candidates=`{tool_ranking.get('candidate_count')}` cache_hit=`{tool_ranking.get('cache_hit')}`",
        "",
        "## Memory And RAG",
        f"- status: `{memory_recall.get('status') or '-'}` source=`{memory_recall.get('source') or '-'}` events=`{memory_recall.get('event_count', 0)}`",
        f"- rag_benchmark: `{rag_benchmark.get('status') or '-'}` budget=`{rag_benchmark.get('budget_status') or '-'}` p95_ms=`{rag_metrics.get('warm_recall_p95_ms') if rag_metrics else '-'}` endpoint=`{rag_benchmark.get('endpoint') or '/memory/rag-benchmark'}`",
        f"- embedding_quality: `{rag_quality.get('status') or 'unproven'}` claim=`{rag_quality.get('can_claim_production_embedding_quality')}` coverage=`{rag_quality.get('coverage') or '-'}`",
        f"- workspace_profiles: `{', '.join(str(item) for item in (memory_recall.get('workspace_profiles') or [])) or '-'}`",
        f"- latest: phase=`{memory_latest.get('phase') or '-'}` iteration=`{memory_latest.get('iteration') if memory_latest else '-'}` profile=`{memory_latest.get('workspace_profile') or '-'}` context_build_ms=`{memory_latest.get('context_build_ms') if memory_latest else '-'}`",
        f"- hits: agents_md=`{memory_totals.get('agents_md_hits')}` cold_recall=`{memory_totals.get('cold_recall_hits')}`",
        f"- control: memory_hits=`{engineering_control_summary.get('memory_total_hits')}` tool_failures=`{engineering_control_summary.get('tool_failure_count')}` plan=`{engineering_control_summary.get('plan_verdict') or '-'}`",
        f"- max_latency: context_build_ms=`{memory_latency.get('context_build_ms')}` cold_recall_ms=`{memory_latency.get('cold_recall_ms')}`",
        "",
        "## Shared Memory",
        f"- status: `{shared_memory.get('status') or '-'}` agent_id=`{shared_memory.get('agent_id') or '-'}`",
        f"- boundary: `{shared_memory.get('boundary') or '-'}` default_visibility=`{shared_memory.get('default_visibility') or '-'}`",
        f"- read_profiles: `{', '.join(str(item) for item in (shared_memory.get('read_profiles') or [])) or '-'}`",
        f"- write_profiles: `{', '.join(str(item) for item in (shared_memory.get('write_profiles') or [])) or '-'}`",
        f"- shared=`{shared_memory.get('can_read_shared')}` public=`{shared_memory.get('can_read_public')}` private_other=`{shared_memory.get('can_read_private_other')}`",
        f"- profile_policy_count: `{shared_memory.get('profile_policy_count') if shared_memory.get('profile_policy_count') is not None else '-'}`",
        f"- promotion_rule: `{(shared_memory.get('outcomes') or {}).get('promotion_rule') or '-'}`",
        f"- demotion_rule: `{(shared_memory.get('outcomes') or {}).get('demotion_rule') or '-'}`",
        f"- unresolved_conflicts: `{(shared_memory.get('outcomes') or {}).get('unresolved_conflict_count') if isinstance(shared_memory.get('outcomes'), dict) else '-'}`",
        "",
        "## Continuation",
        f"- status: `{continuation.get('status') or '-'}` resume_ready=`{continuation.get('resume_ready')}` mode=`{continuation.get('resume_mode') or '-'}`",
        f"- resume_drill: `{resume_drill.get('status') or '-'}` durable=`{durable_resume.get('status') or '-'}` warm=`{warm_resume.get('status') or '-'}` hot=`{hot_resume.get('status') or '-'}`",
        f"- resume_truth: durable_claim=`{(resume_drill.get('closure_gate') or {}).get('can_claim_long_task_durable_handoff') if isinstance(resume_drill.get('closure_gate'), dict) else '-'}` hot_claim=`{(resume_drill.get('closure_gate') or {}).get('can_claim_hot_tool_call_resume') if isinstance(resume_drill.get('closure_gate'), dict) else '-'}`",
        f"- workspace_profile: `{continuation.get('workspace_profile') or '-'}` context_revision=`{continuation.get('context_revision') or '-'}`",
        f"- goal_next_focus: {continuation.get('goal_next_focus') or '-'}",
        f"- last_tool: `{continuation.get('last_tool') or '-'}` ok=`{continuation.get('last_ok')}` plan=`{continuation.get('plan_verdict') or '-'}`",
        f"- open_plan_count: `{continuation.get('open_plan_count') or 0}` artifact_count=`{continuation.get('artifact_count') or 0}`",
        f"- compression: needed=`{continuation.get('compression_needed')}` compressed_steps=`{continuation.get('compressed_step_count') or 0}` skipped=`{continuation.get('skipped_step_count') or 0}`",
        "",
        "## Counts",
    ])
    if continuation.get("summary"):
        lines.append(f"- compressed_summary: {continuation.get('summary')}")
    if latest_feedback:
        lines.extend([
            "",
            "## Latest LLM Feedback",
            f"- top_pain_point: {latest_feedback.get('top_pain_point') or feedback_first_change.get('title') or '-'}",
            f"- priority: `{latest_feedback.get('priority') or '-'}`",
            f"- smallest_fix: {latest_feedback.get('smallest_fix') or '-'}",
        ])
    for key in ["context_sync", "runtime_metrics", "memory_recall", "learning", "layer", "maker_guard", "llm_probe", "cos_gate"]:
        lines.append(f"- {key}: `{counts.get(key, 0)}`")

    lines.extend(["", "## Detail Endpoints"])
    for key in [
        "evidence_bundle",
        "portable_runtime",
        "runtime_advice",
        "maker_briefing",
        "maker_guard",
        "context_sync",
        "resume_drill",
        "runtime_metrics",
        "engineering_control",
        "project_writeback",
        "learning_status",
        "learning_cancel",
        "learning_retry",
        "rag_benchmark",
        "rag_quality",
        "llm_probe",
        "llm_probe_history",
        "handoff_bundle",
        "mcp_status",
        "mcp_tools",
    ]:
        if endpoints.get(key):
            lines.append(f"- {key}: `{endpoints[key]}`")

    token_rule = bundle.get("token_rule")
    if token_rule:
        lines.extend(["", "## Token Rule", f"- {token_rule}"])
    return "\n".join(lines)


def build_llm_onboarding_bundle(
    *,
    server: Any,
    session_id: str,
    steps: int = 20,
    surface: str = "generic",
) -> Dict[str, Any]:
    """Build a one-stop startup and closure packet for any coding LLM."""
    stored = server.session_store.get_session(session_id) if session_id != "{session_id}" else {}
    task = (stored or {}).get("task", "") if session_id != "{session_id}" else ""
    contract = server.agent.runtime_contract(session_id=session_id)
    communication = contract.get("communication") if isinstance(contract.get("communication"), dict) else {}
    surface_profile = quickstart_surface_profile(surface)
    readiness = build_runtime_readiness(server=server, session_id=session_id)
    evidence = build_session_evidence_bundle(server=server, session_id=session_id, steps=steps)
    maker = evidence.get("maker_mcp") if isinstance(evidence.get("maker_mcp"), dict) else {}
    advice = evidence.get("runtime_advice") if isinstance(evidence.get("runtime_advice"), dict) else {}
    layer_summary = evidence.get("layer_summary") if isinstance(evidence.get("layer_summary"), dict) else {}
    layer_health = evidence.get("layer_health") if isinstance(evidence.get("layer_health"), dict) else {}
    layer_control = evidence.get("layer_control") if isinstance(evidence.get("layer_control"), dict) else {}
    engineering_control = (
        evidence.get("engineering_control")
        if isinstance(evidence.get("engineering_control"), dict)
        else {}
    )
    runtime_summary = (
        evidence.get("runtime_metrics_summary")
        if isinstance(evidence.get("runtime_metrics_summary"), dict)
        else {}
    )
    counts = evidence.get("counts") if isinstance(evidence.get("counts"), dict) else {}
    call_proof = (
        evidence.get("llm_call_proof")
        if isinstance(evidence.get("llm_call_proof"), dict)
        else {}
    )
    learning_latest = (
        evidence.get("learning_latest")
        if isinstance(evidence.get("learning_latest"), dict)
        else {}
    )
    shared_memory = (
        evidence.get("shared_memory")
        if isinstance(evidence.get("shared_memory"), dict)
        else {}
    )
    learning_observer = (
        evidence.get("learning_observer")
        if isinstance(evidence.get("learning_observer"), dict)
        else {}
    )
    memory_recall = (
        evidence.get("memory_recall")
        if isinstance(evidence.get("memory_recall"), dict)
        else {}
    )
    rag_benchmark = (
        evidence.get("rag_benchmark")
        if isinstance(evidence.get("rag_benchmark"), dict)
        else {}
    )
    rag_quality = (
        rag_benchmark.get("embedding_quality")
        if isinstance(rag_benchmark.get("embedding_quality"), dict)
        else {}
    )
    rag_closure = (
        rag_benchmark.get("closure_gate")
        if isinstance(rag_benchmark.get("closure_gate"), dict)
        else {}
    )
    event_bus_summary = (
        evidence.get("runtime_event_bus")
        if isinstance(evidence.get("runtime_event_bus"), dict)
        else {}
    )
    project_state = (
        evidence.get("project_state")
        if isinstance(evidence.get("project_state"), dict)
        else {}
    )
    project_control = (
        project_state.get("project_control")
        if isinstance(project_state.get("project_control"), dict)
        else {}
    )
    project_writeback = (
        evidence.get("project_writeback")
        if isinstance(evidence.get("project_writeback"), dict)
        else {}
    )
    cos_gate = (
        evidence.get("cos_gate")
        if isinstance(evidence.get("cos_gate"), dict)
        else {}
    )
    continuation = (
        evidence.get("continuation")
        if isinstance(evidence.get("continuation"), dict)
        else {}
    )
    resume_drill = (
        evidence.get("resume_drill")
        if isinstance(evidence.get("resume_drill"), dict)
        else {}
    )
    resume_closure = (
        resume_drill.get("closure_gate")
        if isinstance(resume_drill.get("closure_gate"), dict)
        else {}
    )
    endpoints = {
        key: communication.get(key)
        for key in [
            "onboarding_bundle",
            "portable_runtime",
            "runtime_readiness",
            "quickstart_bundle",
            "evidence_bundle",
            "runtime_advice",
            "maker_briefing",
            "maker_guard",
            "context_sync",
            "resume_drill",
            "runtime_metrics",
            "layer_health",
            "layer_control",
            "engineering_control",
            "project_state",
            "project_writeback",
            "learning_status",
            "learning_cancel",
            "learning_retry",
            "rag_benchmark",
            "rag_quality",
            "llm_probe",
            "llm_probe_history",
            "llm_feedback_summary",
            "maker_setup_status",
            "maker_setup_status_markdown",
            "maker_tool_audit",
            "maker_project_select",
            "maker_auth_prepare",
            "maker_auth_complete",
            "runtime_contract",
            "handoff_bundle",
            "mcp_status",
            "mcp_tools",
        ]
        if communication.get(key)
    }
    maker_setup = server.maker_setup_status(check_latest=False)
    maker_tool_audit = maker_setup.get("tool_audit") if isinstance(maker_setup.get("tool_audit"), dict) else {}

    gate_checks = [
        {
            "id": "any_llm_startup",
            "status": "ready" if endpoints.get("portable_runtime") and endpoints.get("runtime_readiness") and endpoints.get("evidence_bundle") else "warn",
            "evidence": [endpoints.get("portable_runtime"), endpoints.get("runtime_readiness"), endpoints.get("evidence_bundle")],
            "summary": "External agents can start from one compact packet without raw SSE replay.",
        },
        {
            "id": "maker_setup_doctor",
            "status": "ready" if maker_setup.get("readiness") == "ready" else maker_setup.get("readiness", "warn"),
            "evidence": [endpoints.get("maker_setup_status"), endpoints.get("maker_tool_audit")],
            "summary": f"Maker setup readiness is {maker_setup.get('readiness') or 'unknown'}.",
        },
        {
            "id": "maker_mcp_binding",
            "status": "ready" if maker.get("readiness") == "ready" else "degraded",
            "evidence": [endpoints.get("mcp_status"), endpoints.get("mcp_tools")],
            "summary": f"MakerMCP readiness is {maker.get('readiness') or 'unknown'}.",
        },
        {
            "id": "layer_independence",
            "status": "ready"
                if layer_health.get("status") in {"ready", "active"}
                else layer_health.get("status", "instrumented"),
            "evidence": [endpoints.get("evidence_bundle"), endpoints.get("layer_health"), endpoints.get("learning_status")],
            "summary": (
                "Agent/Core Runtime/Learning health is "
                f"{layer_health.get('status') or 'not_observed'} with queue depth "
                f"{(layer_health.get('summary') or {}).get('learning_queue_depth') if isinstance(layer_health.get('summary'), dict) else '-'}."
            ),
        },
        {
            "id": "layer_control",
            "status": layer_control.get("status") or "instrumented",
            "evidence": [endpoints.get("evidence_bundle"), endpoints.get("layer_health"), endpoints.get("layer_control")],
            "summary": (
                "Layer-control decision is "
                f"{layer_control.get('decision') or 'not_available'} with "
                f"{len(layer_control.get('corrective_actions') or []) if isinstance(layer_control.get('corrective_actions'), list) else 0} corrective actions."
            ),
        },
        {
            "id": "engineering_control",
            "status": engineering_control.get("status") or "instrumented",
            "evidence": [endpoints.get("evidence_bundle"), endpoints.get("engineering_control")],
            "summary": (
                "Engineering-control decision is "
                f"{engineering_control.get('decision') or 'not_available'} with "
                f"{len(engineering_control.get('corrective_actions') or []) if isinstance(engineering_control.get('corrective_actions'), list) else 0} corrective actions."
            ),
        },
        {
            "id": "token_efficiency",
            "status": "ready" if (runtime_summary.get("event_count") or 0) > 0 else "instrumented",
            "evidence": [endpoints.get("runtime_metrics"), endpoints.get("context_sync")],
            "summary": "Use evidence and context sync before detailed histories; runtime metrics expose token/cache/tool ranking.",
        },
        {
            "id": "memory_rag_observer",
            "status": "ready" if memory_recall.get("status") in {"ready", "replay"} else "instrumented",
            "evidence": [endpoints.get("evidence_bundle"), endpoints.get("runtime_metrics")],
            "summary": (
                "Memory/RAG recall evidence is "
                f"{memory_recall.get('status') or 'missing'} from "
                f"{memory_recall.get('source') or 'unknown'}."
            ),
        },
        {
            "id": "rag_benchmark",
            "status": "ready"
                if rag_benchmark.get("status") == "ready" and rag_benchmark.get("budget_status") == "pass"
                else ("warn" if rag_benchmark.get("status") == "error" or rag_benchmark.get("budget_status") == "fail" else "instrumented"),
            "evidence": [endpoints.get("rag_benchmark"), endpoints.get("evidence_bundle")],
            "summary": (
                "Deterministic local RAG benchmark is "
                f"{rag_benchmark.get('status') or 'not_run'} with budget "
                f"{rag_benchmark.get('budget_status') or 'not_checked'}."
            ),
        },
        {
            "id": "rag_embedding_quality",
            "status": "ready"
                if rag_closure.get("can_claim_production_embedding_quality")
                else "unproven",
            "evidence": [endpoints.get("rag_benchmark"), endpoints.get("evidence_bundle")],
            "summary": (
                "Production embedding quality is "
                f"{rag_quality.get('status') or 'unproven'}; deterministic speed evidence alone "
                "does not prove semantic recall quality."
            ),
        },
        {
            "id": "long_task_continuation",
            "status": "ready"
                if resume_closure.get("can_claim_long_task_durable_handoff")
                else resume_drill.get("status", "instrumented"),
            "evidence": [endpoints.get("evidence_bundle"), endpoints.get("context_sync"), endpoints.get("resume_drill")],
            "summary": (
                "Resume drill is "
                f"{resume_drill.get('status') or 'missing'}; durable handoff can be claimed only when task, "
                "open plan, last result, artifacts, and next action are recoverable from persisted evidence."
            ),
        },
        {
            "id": "shared_memory_policy",
            "status": "ready" if shared_memory.get("status") == "ready" else "instrumented",
            "evidence": [endpoints.get("evidence_bundle")],
            "summary": (
                "Shared-memory boundary is "
                f"{shared_memory.get('boundary') or 'unknown'} with default visibility "
                f"{shared_memory.get('default_visibility') or 'unknown'}."
            ),
        },
        {
            "id": "runtime_event_bus",
            "status": "ready" if event_bus_summary.get("status") in {"ready", "partial"} else "instrumented",
            "evidence": [endpoints.get("runtime_readiness"), endpoints.get("evidence_bundle")],
            "summary": (
                "Runtime event bus is "
                f"{event_bus_summary.get('status') or 'unknown'} with "
                f"{(event_bus_summary.get('server_bus') or {}).get('history_size', 0)} server events retained."
            ),
        },
        {
            "id": "cos_gate",
            "status": "ready" if cos_gate.get("status") in {"ready", "computed"} else "instrumented",
            "evidence": [endpoints.get("evidence_bundle"), endpoints.get("runtime_readiness")],
            "summary": (
                "COS Gate 0 is "
                f"{cos_gate.get('status') or 'missing'}: "
                f"{cos_gate.get('declaration') or 'no declaration'}"
            ),
        },
        {
            "id": "project_management_state",
            "status": "ready" if project_state.get("status") in {"ready", "replay"} else "instrumented",
            "evidence": [endpoints.get("evidence_bundle"), endpoints.get("context_sync")],
            "summary": (
                "Project observer state is "
                f"{project_state.get('status') or 'unknown'} with next action: "
                f"{project_state.get('next_action') or 'not observed'}"
            ),
        },
        {
            "id": "project_control",
            "status": "ready" if project_control.get("status") in {"ready", "needs_action"} else project_control.get("status", "instrumented"),
            "evidence": [endpoints.get("evidence_bundle"), endpoints.get("runtime_advice")],
            "summary": (
                "Project control is "
                f"{project_control.get('status') or 'missing'} with next action: "
                f"{project_control.get('next_action') or 'not observed'}"
            ),
        },
        {
            "id": "project_writeback",
            "status": "ready"
                if project_writeback.get("status") in {"ready", "already_applied", "no_updates_due"}
                else project_writeback.get("status", "instrumented"),
            "evidence": [endpoints.get("project_writeback"), endpoints.get("evidence_bundle")],
            "summary": (
                "Project writeback plan is "
                f"{project_writeback.get('status') or 'missing'} for "
                f"{', '.join(project_writeback.get('files') or []) or 'no files'}."
            ),
        },
        {
            "id": "frontend_backend_loop",
            "status": "ready" if endpoints.get("onboarding_bundle") and endpoints.get("evidence_bundle") else "warn",
            "evidence": ["AgentWorkbench", endpoints.get("onboarding_bundle")],
            "summary": "Workbench can copy the same onboarding packet external LLMs read.",
        },
        {
            "id": "theme_and_release",
            "status": "ready",
            "evidence": ["styles.css", "frontend/src/styles/index.css", "docs/releases/v0.4.2-onboarding-closure.md"],
            "summary": "TapTapMaker token language is the visual baseline for this small release.",
        },
    ]
    blockers = [item for item in readiness.get("issues", []) if item.get("severity") == "blocker"]
    live_gaps: List[str] = []
    if call_proof.get("conclusion") != "api_call_observed":
        live_gaps.append("api_call_proof")
    if maker.get("readiness") != "ready":
        live_gaps.append("maker_mcp_remote_authority")
    if maker_setup.get("readiness") != "ready":
        live_gaps.append("maker_setup_doctor")
    if maker_tool_audit.get("ok") is False:
        live_gaps.append("maker_tool_audit")
    if (runtime_summary.get("event_count") or 0) == 0:
        live_gaps.append("runtime_metrics_sample")
    if layer_health.get("status") not in {"ready", "active"}:
        live_gaps.append("layer_health_snapshot")
    if layer_control.get("status") not in {"ready", "watch"}:
        live_gaps.append("layer_control_actions")
    if engineering_control.get("status") not in {"ready", "watch"}:
        live_gaps.append("engineering_control_actions")
    if memory_recall.get("status") not in {"ready", "replay"}:
        live_gaps.append("memory_recall_sample")
    if not (rag_benchmark.get("status") == "ready" and rag_benchmark.get("budget_status") == "pass"):
        live_gaps.append("rag_benchmark_report")
    if rag_closure.get("can_claim_production_embedding_quality") is not True:
        live_gaps.append("production_embedding_quality_benchmark")
    if not learning_latest:
        live_gaps.append("learning_completion_sample")
    if not resume_closure.get("can_claim_long_task_durable_handoff"):
        live_gaps.append("resume_drill")
    if cos_gate.get("status") not in {"ready", "computed"}:
        live_gaps.append("cos_gate")
    if project_control.get("status") not in {"ready", "needs_action"}:
        live_gaps.append("project_control")
    if project_writeback.get("status") not in {"ready", "already_applied", "no_updates_due"}:
        live_gaps.append("project_writeback")

    closure_decision = "stable_small_version_ready"
    if blockers:
        closure_decision = "blocked_until_provider_configured"
    elif live_gaps:
        closure_decision = "stable_small_version_ready_live_validation_pending"

    startup_order = [
        endpoints.get("onboarding_bundle") or f"/agent/onboarding?session_id={session_id}&steps={steps}",
        endpoints.get("portable_runtime") or "/runtime/portable",
        endpoints.get("runtime_readiness") or f"/runtime/readiness?session_id={session_id}",
        endpoints.get("evidence_bundle") or f"/sessions/{session_id}/evidence?steps=20",
        endpoints.get("maker_setup_status") or "/maker/setup-status",
        endpoints.get("maker_tool_audit") or "/maker/tool-audit",
        endpoints.get("runtime_advice") or f"/sessions/{session_id}/runtime-advice?steps=20",
        endpoints.get("maker_briefing") or f"/agent/maker-briefing?session_id={session_id}",
    ]

    bundle = {
        "version": "llm-onboarding.v1",
        "release": "v0.4.2-onboarding-closure",
        "session_id": session_id,
        "task": task,
        "surface": surface_profile,
        "summary": {
            "status": readiness.get("status"),
            "decision": closure_decision,
            "next_action": advice.get("next_action") or (readiness.get("next_actions") or [""])[0],
            "maker_readiness": maker.get("readiness"),
            "api_call_proof": call_proof.get("conclusion"),
            "layer_events": layer_summary.get("event_count", 0),
            "layer_health": layer_health.get("status") or "missing",
            "layer_control": layer_control.get("status") or "missing",
            "engineering_control": engineering_control.get("status") or "missing",
            "runtime_events": runtime_summary.get("event_count", 0),
            "event_bus": event_bus_summary.get("status") or "missing",
            "memory_recall": memory_recall.get("status") or "missing",
            "rag_benchmark": rag_benchmark.get("status") or "not_run",
            "rag_embedding_quality": rag_quality.get("status") or "unproven",
            "project_state": project_state.get("status") or "missing",
            "project_control": project_control.get("status") or "missing",
            "project_writeback": project_writeback.get("status") or "missing",
            "cos_gate": cos_gate.get("mode") or cos_gate.get("status") or "missing",
            "learning": learning_latest.get("event") or learning_latest.get("state") or "not_observed",
            "maker_setup": maker_setup.get("readiness"),
            "maker_tool_audit": "ok" if maker_tool_audit.get("ok") else "needs_review",
            "continuation": continuation.get("status") or "missing",
            "resume_drill": resume_drill.get("status") or "missing",
        },
        "startup_order": [item for item in startup_order if item],
        "for_any_llm": [
            "Read Runtime Readiness and this onboarding bundle before selecting tools.",
            "Use MakerMCP as the authority for Maker remote state when connected; otherwise report local-only limits.",
            "Use Evidence Bundle before raw SSE, full tool lists, or detailed histories.",
            "Keep one small verifiable change in flight and cite the endpoint that justified the first action.",
        ],
        "maker_mcp": maker,
        "maker_setup": maker_setup,
        "maker_tool_audit": maker_tool_audit,
        "runtime_readiness": {
            "status": readiness.get("status"),
            "summary": readiness.get("summary", {}),
            "issues": readiness.get("issues", []),
            "next_actions": readiness.get("next_actions", []),
            "release_gate": readiness.get("release_gate", {}),
        },
        "runtime_advice": advice,
        "continuation": continuation,
        "resume_drill": resume_drill,
        "cos_gate": cos_gate,
        "shared_memory": shared_memory,
        "learning_observer": learning_observer,
        "memory_recall": memory_recall,
        "rag_benchmark": rag_benchmark,
        "runtime_event_bus": event_bus_summary,
        "project_state": project_state,
        "project_control": project_control,
        "project_writeback": project_writeback,
        "layer_summary": layer_summary,
        "layer_health": layer_health,
        "layer_control": layer_control,
        "engineering_control": engineering_control,
        "runtime_metrics_summary": runtime_summary,
        "learning_latest": learning_latest or None,
        "llm_call_proof": call_proof,
        "counts": counts,
        "closure_gate": {
            "decision": closure_decision,
            "checks": gate_checks,
            "live_validation_gaps": live_gaps,
            "stable_definition": [
                "No mock fallback for normal API runs.",
                "External agents have a single compact onboarding packet.",
                "Maker installation, project initialization, auth, and tool exposure are checked before real Maker work.",
                "MakerMCP authority and guard evidence are visible before Maker side effects.",
                "Agent/Core Runtime/Learning evidence is independently pullable.",
                "Token strategy prefers readiness/evidence/context summaries over raw histories.",
                "Long tasks expose a resume drill before durable handoff claims.",
                "Shared-memory policy is explicit before multi-agent memory reuse.",
                "Runtime Event Bus status is exposed before observers rely on decoupled event streams.",
                "Project-management state is derived from bus/context evidence before asking the user to decide next steps.",
                "Project writeback is planned from project_control and only applied through an explicit POST.",
                "Workbench and backend expose the same compact evidence path.",
            ],
        },
        "token_strategy": {
            "rule": "Read onboarding -> readiness -> evidence; fetch detailed histories only when the packet points there.",
            "metrics": {
                "llm_total_tokens": runtime_summary.get("llm_total_tokens"),
                "token_cache": runtime_summary.get("token_cache", {}),
                "tool_ranking": runtime_summary.get("tool_ranking", {}),
                "retrieval": runtime_summary.get("retrieval", {}),
                "memory_recall": memory_recall,
                "rag_benchmark": rag_benchmark,
            },
            "rules": (contract.get("token_efficiency") or {}).get("rules", [])[:6],
        },
        "frontend_backend": {
            "surface": "AgentWorkbench External Agent Boot",
            "primary_endpoint": endpoints.get("onboarding_bundle"),
            "evidence_endpoint": endpoints.get("evidence_bundle"),
            "theme_tokens": ["#00D9C5", "#00CDBA", "#F7F9FA", "#060A26"],
        },
        "reference_principles": [
            "TapTap Maker Plus style principle: do not bypass MakerMCP for Maker authority.",
            "Prefer schema/evidence-driven surfaces over hand-written guesses.",
            "Show raw errors and logs through copyable evidence only when compact summaries are insufficient.",
        ],
        "endpoints": endpoints,
    }
    bundle["prompt_markdown"] = render_llm_onboarding_markdown(bundle)
    return bundle


def render_llm_onboarding_markdown(bundle: Dict[str, Any]) -> str:
    """Render the one-stop onboarding bundle as a pasteable card."""
    summary = bundle.get("summary") if isinstance(bundle.get("summary"), dict) else {}
    readiness = bundle.get("runtime_readiness") if isinstance(bundle.get("runtime_readiness"), dict) else {}
    maker = bundle.get("maker_mcp") if isinstance(bundle.get("maker_mcp"), dict) else {}
    maker_setup = bundle.get("maker_setup") if isinstance(bundle.get("maker_setup"), dict) else {}
    maker_tool_audit = bundle.get("maker_tool_audit") if isinstance(bundle.get("maker_tool_audit"), dict) else {}
    advice = bundle.get("runtime_advice") if isinstance(bundle.get("runtime_advice"), dict) else {}
    closure = bundle.get("closure_gate") if isinstance(bundle.get("closure_gate"), dict) else {}
    token_strategy = bundle.get("token_strategy") if isinstance(bundle.get("token_strategy"), dict) else {}
    continuation = bundle.get("continuation") if isinstance(bundle.get("continuation"), dict) else {}
    resume_drill = bundle.get("resume_drill") if isinstance(bundle.get("resume_drill"), dict) else {}
    resume_capabilities = (
        resume_drill.get("capability_levels")
        if isinstance(resume_drill.get("capability_levels"), dict)
        else {}
    )
    durable_resume = (
        resume_capabilities.get("durable_handoff")
        if isinstance(resume_capabilities.get("durable_handoff"), dict)
        else {}
    )
    layer_summary = bundle.get("layer_summary") if isinstance(bundle.get("layer_summary"), dict) else {}
    layer_health = bundle.get("layer_health") if isinstance(bundle.get("layer_health"), dict) else {}
    layer_health_summary = (
        layer_health.get("summary")
        if isinstance(layer_health.get("summary"), dict)
        else {}
    )
    layer_control = bundle.get("layer_control") if isinstance(bundle.get("layer_control"), dict) else {}
    layer_control_actions = (
        layer_control.get("corrective_actions")
        if isinstance(layer_control.get("corrective_actions"), list)
        else []
    )
    engineering_control = (
        bundle.get("engineering_control")
        if isinstance(bundle.get("engineering_control"), dict)
        else {}
    )
    engineering_control_actions = (
        engineering_control.get("corrective_actions")
        if isinstance(engineering_control.get("corrective_actions"), list)
        else []
    )
    runtime_summary = (
        bundle.get("runtime_metrics_summary")
        if isinstance(bundle.get("runtime_metrics_summary"), dict)
        else {}
    )
    memory_recall = (
        bundle.get("memory_recall")
        if isinstance(bundle.get("memory_recall"), dict)
        else {}
    )
    rag_benchmark = (
        bundle.get("rag_benchmark")
        if isinstance(bundle.get("rag_benchmark"), dict)
        else {}
    )
    rag_metrics = (
        rag_benchmark.get("metrics")
        if isinstance(rag_benchmark.get("metrics"), dict)
        else {}
    )
    rag_quality = (
        rag_benchmark.get("embedding_quality")
        if isinstance(rag_benchmark.get("embedding_quality"), dict)
        else {}
    )
    event_bus = bundle.get("runtime_event_bus") if isinstance(bundle.get("runtime_event_bus"), dict) else {}
    server_bus = event_bus.get("server_bus") if isinstance(event_bus.get("server_bus"), dict) else {}
    project_state = bundle.get("project_state") if isinstance(bundle.get("project_state"), dict) else {}
    project_control = (
        bundle.get("project_control")
        if isinstance(bundle.get("project_control"), dict)
        else project_state.get("project_control")
        if isinstance(project_state.get("project_control"), dict)
        else {}
    )
    project_writeback = (
        bundle.get("project_writeback")
        if isinstance(bundle.get("project_writeback"), dict)
        else {}
    )
    cos_gate = bundle.get("cos_gate") if isinstance(bundle.get("cos_gate"), dict) else {}
    call_proof = bundle.get("llm_call_proof") if isinstance(bundle.get("llm_call_proof"), dict) else {}
    surface = bundle.get("surface") if isinstance(bundle.get("surface"), dict) else {}
    endpoints = bundle.get("endpoints") if isinstance(bundle.get("endpoints"), dict) else {}
    checks = closure.get("checks") if isinstance(closure.get("checks"), list) else []
    gaps = closure.get("live_validation_gaps") if isinstance(closure.get("live_validation_gaps"), list) else []
    lines = [
        "# TTMEvolve LLM Onboarding Bundle",
        "",
        "Use this card as the first packet for any coding LLM entering TTMEvolve.",
        "",
        "## Release",
        f"- release: `{bundle.get('release') or '-'}`",
        f"- session_id: `{bundle.get('session_id') or '-'}`",
        f"- task: {bundle.get('task') or '-'}",
        f"- surface: `{surface.get('id') or 'generic'}`",
        f"- decision: `{summary.get('decision') or closure.get('decision') or '-'}`",
        f"- next_action: {summary.get('next_action') or '-'}",
        "",
        "## Startup Order",
    ]
    for index, item in enumerate(bundle.get("startup_order", [])[:6], start=1):
        lines.append(f"{index}. `{item}`")
    lines.extend([
        "",
        "## Readiness",
        f"- status: `{readiness.get('status') or summary.get('status') or '-'}`",
        f"- maker: `{summary.get('maker_readiness') or maker.get('readiness') or '-'}` connected=`{maker.get('connected')}` tools=`{maker.get('tool_count')}`",
        f"- maker_setup: `{maker_setup.get('readiness') or summary.get('maker_setup') or '-'}` blockers=`{', '.join(maker_setup.get('blockers') or []) or '-'}`",
        f"- maker_tool_audit: `{'ok' if maker_tool_audit.get('ok') else 'needs_review'}` remote_tools=`{maker_tool_audit.get('remote_tool_count') if maker_tool_audit else '-'}`",
        f"- api_call_proof: `{summary.get('api_call_proof') or call_proof.get('conclusion') or '-'}` observed=`{call_proof.get('observed_endpoint') or '-'}`",
        f"- advice_priority: `{advice.get('priority') or '-'}`",
        f"- layer_events: `{summary.get('layer_events') or layer_summary.get('event_count') or 0}`",
        f"- layer_health: `{summary.get('layer_health') or layer_health.get('status') or '-'}` queue_depth=`{layer_health_summary.get('learning_queue_depth') if layer_health_summary else '-'}`",
        f"- layer_control: `{summary.get('layer_control') or layer_control.get('status') or '-'}` decision=`{layer_control.get('decision') or '-'}` actions=`{len(layer_control_actions)}`",
        f"- engineering_control: `{summary.get('engineering_control') or engineering_control.get('status') or '-'}` decision=`{engineering_control.get('decision') or '-'}` actions=`{len(engineering_control_actions)}`",
        f"- runtime_events: `{summary.get('runtime_events') or runtime_summary.get('event_count') or 0}`",
        f"- event_bus: `{summary.get('event_bus') or event_bus.get('status') or '-'}` server_history=`{server_bus.get('history_size', '-')}` observer_health=`{event_bus.get('observer_health') or '-'}` observer_errors=`{event_bus.get('observer_error_count') if event_bus.get('observer_error_count') is not None else '-'}`",
        f"- memory_recall: `{summary.get('memory_recall') or memory_recall.get('status') or '-'}` source=`{memory_recall.get('source') or '-'}` events=`{memory_recall.get('event_count', 0)}`",
        f"- rag_benchmark: `{rag_benchmark.get('status') or '-'}` budget=`{rag_benchmark.get('budget_status') or '-'}` p95_ms=`{rag_metrics.get('warm_recall_p95_ms') if rag_metrics else '-'}`",
        f"- rag_embedding_quality: `{summary.get('rag_embedding_quality') or rag_quality.get('status') or 'unproven'}` claim=`{rag_quality.get('can_claim_production_embedding_quality')}`",
        f"- project_state: `{summary.get('project_state') or project_state.get('status') or '-'}` next=`{project_state.get('next_action') or '-'}`",
        f"- project_control: `{summary.get('project_control') or project_control.get('status') or '-'}` next=`{project_control.get('next_action') or '-'}`",
        f"- project_writeback: `{summary.get('project_writeback') or project_writeback.get('status') or '-'}` applicable=`{project_writeback.get('applicable')}` files=`{', '.join(project_writeback.get('files') or []) or '-'}`",
        f"- cos_gate: `{summary.get('cos_gate') or cos_gate.get('mode') or '-'}` level=`{cos_gate.get('level') or '-'}` source=`{cos_gate.get('source') or '-'}`",
        f"- learning: `{summary.get('learning') or '-'}`",
        f"- continuation: `{summary.get('continuation') or continuation.get('status') or '-'}` resume_ready=`{continuation.get('resume_ready')}`",
        f"- resume_drill: `{summary.get('resume_drill') or resume_drill.get('status') or '-'}` durable=`{durable_resume.get('status') or '-'}` hot_claim=`{(resume_drill.get('closure_gate') or {}).get('can_claim_hot_tool_call_resume') if isinstance(resume_drill.get('closure_gate'), dict) else '-'}`",
        "",
        "## Closure Gate",
        f"- decision: `{closure.get('decision') or '-'}`",
    ])
    for check in checks[:6]:
        if isinstance(check, dict):
            lines.append(f"- {check.get('id')}: `{check.get('status')}` - {check.get('summary')}")
    if gaps:
        lines.append(f"- live_validation_gaps: {', '.join(str(item) for item in gaps)}")
    lines.extend([
        "",
        "## Token Strategy",
        f"- rule: {token_strategy.get('rule') or '-'}",
    ])
    metrics = token_strategy.get("metrics") if isinstance(token_strategy.get("metrics"), dict) else {}
    tool_ranking = metrics.get("tool_ranking") if isinstance(metrics.get("tool_ranking"), dict) else {}
    token_cache = metrics.get("token_cache") if isinstance(metrics.get("token_cache"), dict) else {}
    lines.extend([
        f"- llm_total_tokens: `{metrics.get('llm_total_tokens') if metrics else '-'}`",
        f"- token_cache: hits=`{token_cache.get('hits')}` misses=`{token_cache.get('misses')}` size=`{token_cache.get('size')}`",
        f"- tool_ranking: selected=`{tool_ranking.get('selected_count')}` candidates=`{tool_ranking.get('candidate_count')}` cache_hit=`{tool_ranking.get('cache_hit')}`",
        "",
        "## Continuation",
        f"- status: `{continuation.get('status') or '-'}` mode=`{continuation.get('resume_mode') or '-'}` workspace=`{continuation.get('workspace_profile') or '-'}`",
        f"- resume_drill: `{resume_drill.get('status') or '-'}` durable=`{durable_resume.get('status') or '-'}` missing=`{', '.join(str(item) for item in (resume_drill.get('missing_fields') or [])) or '-'}`",
        f"- goal_next_focus: {continuation.get('goal_next_focus') or '-'}",
        f"- last_tool: `{continuation.get('last_tool') or '-'}` plan=`{continuation.get('plan_verdict') or '-'}`",
        f"- open_plan_count: `{continuation.get('open_plan_count') or 0}` compression_needed=`{continuation.get('compression_needed')}`",
        "",
        "## Rules For Any LLM",
    ])
    for rule in bundle.get("for_any_llm", [])[:6]:
        lines.append(f"- {rule}")
    lines.extend(["", "## Endpoints"])
    for key in [
        "onboarding_bundle",
        "portable_runtime",
        "runtime_readiness",
        "quickstart_bundle",
        "evidence_bundle",
        "runtime_advice",
        "maker_briefing",
        "maker_guard",
        "context_sync",
        "resume_drill",
        "runtime_metrics",
        "layer_health",
        "layer_control",
        "engineering_control",
        "project_writeback",
        "learning_status",
        "learning_cancel",
        "learning_retry",
        "rag_benchmark",
        "rag_quality",
        "llm_probe",
        "llm_probe_history",
        "llm_feedback_summary",
        "maker_setup_status",
        "maker_setup_status_markdown",
        "maker_tool_audit",
        "maker_project_select",
        "maker_auth_prepare",
        "maker_auth_complete",
        "mcp_status",
        "mcp_tools",
    ]:
        if endpoints.get(key):
            lines.append(f"- {key}: `{endpoints[key]}`")
    return "\n".join(lines)


def build_llm_quickstart_bundle(
    *,
    session_id: str,
    task: str,
    contract: Dict[str, Any],
    maker_briefing: Dict[str, Any],
    runtime_advice: Dict[str, Any],
    context_history: List[Dict[str, Any]],
    surface: str = "generic",
    llm_probe_latest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a compact startup packet for external coding agents."""
    surface_profile = quickstart_surface_profile(surface)
    communication = contract.get("communication") if isinstance(contract.get("communication"), dict) else {}
    maker = contract.get("maker_mcp") if isinstance(contract.get("maker_mcp"), dict) else {}
    warning_codes = contract.get("warning_codes") if isinstance(contract.get("warning_codes"), list) else []
    latest_context = context_history[-1] if context_history else None
    quickstart_endpoint = communication.get("quickstart_bundle") or f"/agent/quickstart?session_id={session_id}&steps=3"
    if surface_profile.get("id") and surface_profile.get("id") != "generic":
        quickstart_endpoint = f"{quickstart_endpoint}&surface={surface_profile['id']}"
    evidence_endpoint = communication.get("evidence_bundle") or f"/sessions/{session_id}/evidence?steps=20"
    portable_endpoint = communication.get("portable_runtime") or "/runtime/portable"
    readiness_endpoint = communication.get("runtime_readiness") or f"/runtime/readiness?session_id={session_id}"
    resume_drill_endpoint = communication.get("resume_drill") or f"/sessions/{session_id}/resume-drill?steps=20"
    boot_sequence = [
        f"GET {portable_endpoint}",
        f"GET {readiness_endpoint}",
        f"GET {quickstart_endpoint}",
        f"GET {evidence_endpoint}",
        f"GET {resume_drill_endpoint} before claiming long-task durable handoff.",
        f"Read runtime_advice priority={runtime_advice.get('priority') or '-'} before choosing the next action.",
        "Use maker_briefing before the first Maker side effect.",
        "If provider wiring is uncertain, inspect latest llm_probe or POST /llm/probe before a full run.",
        "Check maker_guard after the first action; if blocked, follow its suggested tools.",
        "Use context_sync/runtime_metrics summaries instead of replaying raw SSE.",
    ]
    if warning_codes:
        boot_sequence.insert(2, f"Resolve warning_codes first: {', '.join(str(code) for code in warning_codes[:4])}")

    prompt = (
        f"You are a {surface_profile['label']} coding agent attached to TTMEvolve. "
        f"Session={session_id}. Task={task or maker_briefing.get('task') or '-'}。"
        "Start from runtime_advice, then maker_briefing. "
        "For Maker work, MakerMCP is the authority before local side effects. "
        "Use compact endpoints, not raw transcripts. "
        "Report which endpoint/evidence justified your first action."
    )
    maker_summary = {
        "readiness": maker.get("readiness"),
        "connected": maker.get("connected"),
        "tool_count": maker.get("tool_count"),
        "warning_codes": warning_codes[:6],
    }
    advice_summary = {
        "status": runtime_advice.get("status"),
        "priority": runtime_advice.get("priority"),
        "next_action": runtime_advice.get("next_action"),
        "reasons": (runtime_advice.get("reasons") or [])[:3]
            if isinstance(runtime_advice.get("reasons"), list)
            else [],
    }
    briefing_summary = {
        "authority": maker_briefing.get("authority"),
        "selected_template": maker_briefing.get("selected_template"),
        "recommended_first_action": maker_briefing.get("recommended_first_action"),
        "suggested_tools": maker_briefing.get("suggested_tools", [])[:4]
            if isinstance(maker_briefing.get("suggested_tools"), list)
            else [],
    }
    endpoints = {
        key: communication.get(key)
        for key in [
            "onboarding_bundle",
            "portable_runtime",
            "runtime_readiness",
            "evidence_bundle",
            "runtime_advice",
            "runtime_readiness",
            "maker_briefing",
            "maker_guard",
            "context_sync",
            "resume_drill",
            "runtime_metrics",
            "engineering_control",
            "project_writeback",
            "llm_probe",
            "llm_probe_history",
            "learning_status",
            "learning_cancel",
            "learning_retry",
            "rag_benchmark",
            "rag_quality",
            "mcp_status",
            "mcp_tools",
            "handoff_bundle",
        ]
        if communication.get(key)
    }
    rules = [
        "Do not fetch raw SSE unless the compact endpoints are insufficient.",
        "Do not make local side effects before Maker authority when MakerMCP is connected.",
        "Use llm_probe evidence before blaming MakerMCP or prompts for provider/API failures.",
        "Use ranked tools and compact context surfaces to preserve tokens.",
        "After acting, verify via maker_guard, context_sync, commit_history, or runtime_metrics.",
        "Claim long-task durable handoff only when resume_drill is ready; never claim hot tool-call resume from context_sync alone.",
    ]
    prompt_markdown = render_quickstart_markdown(
        session_id=session_id,
        task=task or maker_briefing.get("task") or "-",
        prompt=prompt,
        surface_profile=surface_profile,
        boot_sequence=boot_sequence,
        maker=maker_summary,
        runtime_advice=advice_summary,
        maker_briefing=briefing_summary,
        llm_probe=compact_llm_probe(llm_probe_latest),
        endpoints=endpoints,
        rules=rules,
    )
    return {
        "version": "llm-quickstart.v1",
        "session_id": session_id,
        "task": task,
        "surface": surface_profile,
        "prompt": prompt,
        "prompt_markdown": prompt_markdown,
        "boot_sequence": boot_sequence,
        "maker": maker_summary,
        "runtime_advice": advice_summary,
        "maker_briefing": briefing_summary,
        "llm_probe": compact_llm_probe(llm_probe_latest),
        "latest_context_sync": latest_context,
        "endpoints": endpoints,
        "rules": rules,
    }


def quickstart_surface_profile(surface: str) -> Dict[str, Any]:
    key = str(surface or "generic").strip().lower().replace("_", "-")
    aliases = {
        "claude": "claude-code",
        "claude_code": "claude-code",
        "cc": "claude-code",
        "open-code": "opencode",
        "openclaw": "generic",
        "hermes": "generic",
    }
    key = aliases.get(key, key)
    profiles: Dict[str, Dict[str, Any]] = {
        "codex": {
            "id": "codex",
            "label": "Codex",
            "memory_files": ["AGENTS.md"],
            "skill_style": "Use Codex skills only when explicitly relevant; prefer project Runtime Contract and compact endpoints first.",
            "start_rule": "Read this quickstart card, then call runtime_advice before selecting tools.",
        },
        "claude-code": {
            "id": "claude-code",
            "label": "Claude Code",
            "memory_files": ["CLAUDE.md", "AGENTS.md"],
            "skill_style": "Treat this card as the active project instruction; map reusable workflows to Claude skills only after Maker authority is clear.",
            "start_rule": "Load the quickstart card before editing files; use maker_briefing before Maker side effects.",
        },
        "opencode": {
            "id": "opencode",
            "label": "opencode",
            "memory_files": ["AGENTS.md", "opencode agent config"],
            "skill_style": "Use this card as the session bootstrap and keep tool calls aligned with runtime_advice.",
            "start_rule": "Start in the build agent only after runtime_advice and maker_briefing are read.",
        },
        "generic": {
            "id": "generic",
            "label": "external",
            "memory_files": ["AGENTS.md or equivalent project memory"],
            "skill_style": "Use your native skill system only after reading TTMEvolve runtime evidence.",
            "start_rule": "Read runtime_advice first, then maker_briefing, then act.",
        },
    }
    return profiles.get(key, profiles["generic"])


def render_quickstart_markdown(
    *,
    session_id: str,
    task: str,
    prompt: str,
    surface_profile: Dict[str, Any],
    boot_sequence: List[str],
    maker: Dict[str, Any],
    runtime_advice: Dict[str, Any],
    maker_briefing: Dict[str, Any],
    llm_probe: Dict[str, Any],
    endpoints: Dict[str, str],
    rules: List[str],
) -> str:
    selected_template = maker_briefing.get("selected_template")
    if not isinstance(selected_template, dict):
        selected_template = {}
    lines = [
        "# TTMEvolve External Agent Quickstart",
        "",
        prompt,
        "",
        "## Session",
        f"- session_id: `{session_id}`",
        f"- task: {task}",
        "",
        "## Surface Profile",
        f"- surface: `{surface_profile.get('id') or 'generic'}`",
        f"- label: {surface_profile.get('label') or '-'}",
        f"- memory_files: {', '.join(str(item) for item in surface_profile.get('memory_files', []))}",
        f"- start_rule: {surface_profile.get('start_rule') or '-'}",
        f"- skill_style: {surface_profile.get('skill_style') or '-'}",
        "",
        "## Runtime Advice",
        f"- status: `{runtime_advice.get('status') or '-'}`",
        f"- priority: `{runtime_advice.get('priority') or '-'}`",
        f"- next_action: {runtime_advice.get('next_action') or '-'}",
    ]
    reasons = runtime_advice.get("reasons") if isinstance(runtime_advice.get("reasons"), list) else []
    for reason in reasons[:3]:
        lines.append(f"- reason: {reason}")
    lines.extend([
        "",
        "## LLM Runtime",
        f"- probe_status: `{llm_probe.get('status') or 'not_run'}`",
        f"- provider: `{llm_probe.get('provider') or '-'}`",
        f"- model: `{llm_probe.get('model') or '-'}`",
        f"- endpoint: `{llm_probe.get('endpoint') or llm_probe.get('base_url') or '-'}`",
    ])
    if llm_probe.get("elapsed_ms") is not None:
        lines.append(f"- elapsed_ms: `{llm_probe.get('elapsed_ms')}`")
    if llm_probe.get("error"):
        lines.append(f"- error: {llm_probe.get('error')}")
    lines.extend([
        "",
        "## Maker Authority",
        f"- readiness: `{maker.get('readiness') or '-'}`",
        f"- connected: `{maker.get('connected')}`",
        f"- authority: `{maker_briefing.get('authority') or '-'}`",
        f"- flow: `{selected_template.get('id') or '-'}`",
        f"- first_action: {maker_briefing.get('recommended_first_action') or '-'}",
    ])
    tools = maker_briefing.get("suggested_tools") if isinstance(maker_briefing.get("suggested_tools"), list) else []
    if tools:
        lines.append(f"- suggested_tools: {', '.join(str(tool) for tool in tools[:4])}")
    lines.extend(["", "## Boot Sequence"])
    for index, step in enumerate(boot_sequence[:6], start=1):
        lines.append(f"{index}. {step}")
    lines.extend(["", "## Compact Endpoints"])
    for key in [
        "portable_runtime",
        "runtime_readiness",
        "runtime_advice",
        "maker_briefing",
        "maker_guard",
        "context_sync",
        "resume_drill",
        "runtime_metrics",
        "engineering_control",
        "layer_health",
        "layer_control",
        "project_writeback",
        "rag_benchmark",
        "rag_quality",
        "llm_probe",
        "llm_probe_history",
        "learning_status",
        "learning_cancel",
        "learning_retry",
        "mcp_status",
        "mcp_tools",
        "handoff_bundle",
    ]:
        if endpoints.get(key):
            lines.append(f"- {key}: `{endpoints[key]}`")
    lines.extend(["", "## Rules"])
    for rule in rules:
        lines.append(f"- {rule}")
    return "\n".join(lines)
