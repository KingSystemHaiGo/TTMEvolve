"""
server/app_server.py — TTMEvolve 桌面级 App Server

基于 Python 标准库 http.server + ThreadingMixIn + SSE，
CLI / TUI / GUI 都可通过本地 HTTP 连接。
"""

from __future__ import annotations
import base64
import copy
import json
import queue
import threading
import time
import uuid
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any, Dict, List, Optional
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

try:
    from http.server import BaseHTTPRequestHandler, HTTPServer
except ImportError:
    BaseHTTPRequestHandler = None
    HTTPServer = None

from agent.agent import TapMakerAgent
from agent.mcp_integration import MCPIntegration
from core.cancellation import TaskCancelled
from core.config import Config
from core.portable_env import apply_portable_env, portable_diagnostics
from core.runtime_events import envelope_event
from ecosystem.skill_sync import SkillSyncRegistry
from llm.llm_factory import LLMFactory
from llm.provider_presets import OPENAI_COMPATIBLE_ALIASES, PROVIDER_PRESETS, model_hints, provider_preset
from llm.unconfigured_llm import UnconfiguredLLM
from server.approval_bridge import ApprovalBridge
from server.browser_service import BrowserService
from server.ide_service import IdeService
from server.settings_api import (
    build_provider_summary,
    build_settings_devtools_clear,
    build_settings_runtime_info,
)
from server.maker_setup import (
    MAKER_URL,
    agent_root_mcp_state,
    build_maker_setup_status,
    build_maker_tool_audit,
    complete_auth_flow,
    ensure_agent_root_maker_mcp_registration,
    ensure_internal_maker_mcp_latest_config,
    prepare_auth_flow,
    probe_maker_mcp_config,
    record_recent_project,
    render_maker_setup_markdown,
)
from server.maker_practice import MakerPracticeRunner
from server.protocol import ApprovalResponse, SessionRequest, TurnEvent
from server.session_store import SessionStore
from server.maker_faults import build_maker_fault_analysis


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
    learning_history: List[Dict[str, Any]] = []
    maker_guard_history: List[Dict[str, Any]] = []
    if session_id != "{session_id}":
        layer_history = server.session_store.get_layer_history(session_id, limit=20)
        context_history = server.session_store.get_context_sync_history(session_id, limit=3)
        runtime_metrics = server.session_store.get_runtime_metrics_history(session_id, limit=20)
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
        "runtime_metrics_summary": runtime_summary,
        "latest_context_sync": context_history[-1] if context_history else None,
        "learning_latest": learning_history[-1] if learning_history else None,
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
                "runtime_metrics",
                "learning_status",
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


def build_shared_memory_policy_summary(*, server: Any, agent_id: str = "default") -> Dict[str, Any]:
    """Return a compact, non-secret summary of the current shared-memory boundary."""
    try:
        memory_manager = getattr(server.agent, "memory_manager", None)
        cold = getattr(memory_manager, "cold", None)
        if cold is not None and hasattr(cold, "shared_policy"):
            policy = cold.shared_policy(agent_id)
            summary = policy.to_summary()
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
    learning_history: List[Dict[str, Any]] = []
    layer_history: List[Dict[str, Any]] = []
    maker_guard_history: List[Dict[str, Any]] = []
    llm_probe_history: List[Dict[str, Any]] = []
    if session_id != "{session_id}":
        context_history = server.session_store.get_context_sync_history(session_id, limit=min(steps, 20))
        runtime_metrics = server.session_store.get_runtime_metrics_history(session_id, limit=steps)
        learning_history = server.session_store.get_learning_history(session_id, limit=steps)
        layer_history = server.session_store.get_layer_history(session_id, limit=steps)
        maker_guard_history = server.session_store.get_maker_guard_history(session_id, limit=steps)
        llm_probe_history = server.session_store.get_llm_probe_history(session_id, limit=steps)

    runtime_summary = summarize_runtime_metrics(runtime_metrics)
    layer_summary = summarize_layer_events(layer_history)
    latest_context_sync = context_history[-1] if context_history else None
    continuation = summarize_continuation(latest_context_sync)
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
        "learning_status",
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
        "layer_summary": layer_summary,
        "runtime_metrics_summary": runtime_summary,
        "shared_memory": shared_memory,
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
            "learning": len(learning_history),
            "layer": len(layer_history),
            "maker_guard": len(maker_guard_history),
            "llm_probe": len(llm_probe_history),
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
    runtime_summary = (
        bundle.get("runtime_metrics_summary")
        if isinstance(bundle.get("runtime_metrics_summary"), dict)
        else {}
    )
    layer_summary = bundle.get("layer_summary") if isinstance(bundle.get("layer_summary"), dict) else {}
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
    guard = bundle.get("maker_guard_latest") if isinstance(bundle.get("maker_guard_latest"), dict) else {}
    probe = bundle.get("llm_probe_latest") if isinstance(bundle.get("llm_probe_latest"), dict) else {}
    call_proof = bundle.get("llm_call_proof") if isinstance(bundle.get("llm_call_proof"), dict) else {}
    feedback_summary = (
        bundle.get("llm_feedback_summary")
        if isinstance(bundle.get("llm_feedback_summary"), dict)
        else {}
    )
    shared_memory = bundle.get("shared_memory") if isinstance(bundle.get("shared_memory"), dict) else {}
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

    lines.extend(["", "## Layer Communication"])
    for layer in ["agent", "runtime", "learning"]:
        latest = latest_by_layer.get(layer) if isinstance(latest_by_layer.get(layer), dict) else {}
        lines.append(
            f"- {layer}: state=`{latest.get('state') or '-'}` event=`{latest.get('event') or '-'}` "
            f"route=`{latest.get('source_layer') or '-'}->{latest.get('target_layer') or '-'}`"
        )
    lines.append(f"- layer_events: `{layer_summary.get('event_count') or 0}`")

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
        "## Shared Memory",
        f"- status: `{shared_memory.get('status') or '-'}` agent_id=`{shared_memory.get('agent_id') or '-'}`",
        f"- boundary: `{shared_memory.get('boundary') or '-'}` default_visibility=`{shared_memory.get('default_visibility') or '-'}`",
        f"- read_profiles: `{', '.join(str(item) for item in (shared_memory.get('read_profiles') or [])) or '-'}`",
        f"- write_profiles: `{', '.join(str(item) for item in (shared_memory.get('write_profiles') or [])) or '-'}`",
        f"- shared=`{shared_memory.get('can_read_shared')}` public=`{shared_memory.get('can_read_public')}` private_other=`{shared_memory.get('can_read_private_other')}`",
        f"- profile_policy_count: `{shared_memory.get('profile_policy_count') if shared_memory.get('profile_policy_count') is not None else '-'}`",
        "",
        "## Continuation",
        f"- status: `{continuation.get('status') or '-'}` resume_ready=`{continuation.get('resume_ready')}` mode=`{continuation.get('resume_mode') or '-'}`",
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
    for key in ["context_sync", "runtime_metrics", "learning", "layer", "maker_guard", "llm_probe"]:
        lines.append(f"- {key}: `{counts.get(key, 0)}`")

    lines.extend(["", "## Detail Endpoints"])
    for key in [
        "evidence_bundle",
        "portable_runtime",
        "runtime_advice",
        "maker_briefing",
        "maker_guard",
        "context_sync",
        "runtime_metrics",
        "learning_status",
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
    continuation = (
        evidence.get("continuation")
        if isinstance(evidence.get("continuation"), dict)
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
            "runtime_metrics",
            "learning_status",
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
            "status": "ready" if (layer_summary.get("event_count") or 0) > 0 else "instrumented",
            "evidence": [endpoints.get("evidence_bundle"), endpoints.get("learning_status")],
            "summary": "Agent/Core Runtime/Learning are summarized through layer and learning evidence.",
        },
        {
            "id": "token_efficiency",
            "status": "ready" if (runtime_summary.get("event_count") or 0) > 0 else "instrumented",
            "evidence": [endpoints.get("runtime_metrics"), endpoints.get("context_sync")],
            "summary": "Use evidence and context sync before detailed histories; runtime metrics expose token/cache/tool ranking.",
        },
        {
            "id": "long_task_continuation",
            "status": "ready" if continuation.get("resume_ready") else "instrumented",
            "evidence": [endpoints.get("evidence_bundle"), endpoints.get("context_sync")],
            "summary": "Continuation checkpoint exposes workspace profile, open plan steps, goal focus, artifacts, and compression state.",
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
    if not learning_latest:
        live_gaps.append("learning_completion_sample")
    if not continuation.get("resume_ready"):
        live_gaps.append("continuation_checkpoint")

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
            "runtime_events": runtime_summary.get("event_count", 0),
            "learning": learning_latest.get("event") or learning_latest.get("state") or "not_observed",
            "maker_setup": maker_setup.get("readiness"),
            "maker_tool_audit": "ok" if maker_tool_audit.get("ok") else "needs_review",
            "continuation": continuation.get("status") or "missing",
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
        "shared_memory": shared_memory,
        "layer_summary": layer_summary,
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
                "Long tasks expose continuation checkpoints before raw transcript replay.",
                "Shared-memory policy is explicit before multi-agent memory reuse.",
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
    layer_summary = bundle.get("layer_summary") if isinstance(bundle.get("layer_summary"), dict) else {}
    runtime_summary = (
        bundle.get("runtime_metrics_summary")
        if isinstance(bundle.get("runtime_metrics_summary"), dict)
        else {}
    )
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
        f"- runtime_events: `{summary.get('runtime_events') or runtime_summary.get('event_count') or 0}`",
        f"- learning: `{summary.get('learning') or '-'}`",
        f"- continuation: `{summary.get('continuation') or continuation.get('status') or '-'}` resume_ready=`{continuation.get('resume_ready')}`",
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
        "runtime_metrics",
        "learning_status",
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
    boot_sequence = [
        f"GET {portable_endpoint}",
        f"GET {readiness_endpoint}",
        f"GET {quickstart_endpoint}",
        f"GET {evidence_endpoint}",
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
            "runtime_metrics",
            "llm_probe",
            "llm_probe_history",
            "learning_status",
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
        "runtime_metrics",
        "llm_probe",
        "llm_probe_history",
        "learning_status",
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


class Session:
    """单个任务会话，支持 SQLite 历史事件回放。"""

    def __init__(
        self,
        session_id: str,
        task: str,
        store: Optional[SessionStore] = None,
    ):
        self.session_id = session_id
        self.task = task
        self.result: Optional[Dict[str, Any]] = None
        self.done = False
        self.cancelled = False
        self.error: Optional[str] = None
        self.pending_action_id: Optional[str] = None
        self._event_queue: queue.Queue[Dict[str, Any]] = queue.Queue()
        self._store = store
        self._history: List[Dict[str, Any]] = []
        self._history_consumed = 0
        if store is not None:
            self._history = store.get_events(session_id)

    def emit(self, event: Dict[str, Any]) -> None:
        event = envelope_event(
            event,
            default_source=str(event.get("source") or "runtime"),
            correlation_id=self.session_id,
        )
        if self._store is not None:
            self._store.append_event(
                self.session_id,
                event.get("type", "unknown"),
                event.get("payload", {}),
                meta=event.get("meta", {}),
                source=event.get("source", ""),
            )
        self._event_queue.put(event)

    def cancel(self) -> bool:
        if self.done:
            return False
        self.cancelled = True
        return True

    def iter_events(self, timeout: Optional[float] = 0.5):
        """生成器：先产出历史事件，再阻塞等待新事件，直到 session 结束。"""
        # 回放已持久化的历史事件
        while self._history_consumed < len(self._history):
            event = self._history[self._history_consumed]
            self._history_consumed += 1
            yield event

        # 实时监听新事件
        while True:
            try:
                yield self._event_queue.get(timeout=timeout)
            except queue.Empty:
                if self.done:
                    break
                continue


class AppServer:
    """桌面级 Agent 服务。"""

    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 7345
    WEB_DIR = Path(__file__).resolve().parent.parent / "web"

    def __init__(
        self,
        agent: TapMakerAgent,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        approval_bridge: Optional[ApprovalBridge] = None,
        session_store: Optional[SessionStore] = None,
    ):
        self.agent = agent
        self.host = host
        self.port = port
        self._approval_bridge = approval_bridge or ApprovalBridge()
        self._sessions: Dict[str, Session] = {}
        self._session_llm_overrides: Dict[str, Dict[str, Optional[str]]] = {}
        self._lock = threading.Lock()
        self.ide_service = IdeService(agent)
        storage_root = Path(agent.config.storage_root())
        self.browser_service = BrowserService(storage_root)
        self.session_store = session_store or SessionStore(storage_root / "sessions.db")
        self.last_llm_probe: Dict[str, Any] = {}
        self.skill_sync_registry = getattr(
            self.agent,
            "skill_sync_registry",
            SkillSyncRegistry(self.agent.config.project_root(), storage_root),
        )
        self.pending_maker_auth: Dict[str, Any] = {}
        self.maker_practice_runner = MakerPracticeRunner(APP_ROOT)
        self._maker_mcp_probe_cache: Dict[str, Any] = {"checked_at": 0.0, "result": {}}
        self.agent.executor.set_browser_service(self.browser_service)

    def maker_tool_audit(self) -> Dict[str, Any]:
        return build_maker_tool_audit(agent=self.agent)

    def maker_mcp_probe(self, *, force: bool = False) -> Dict[str, Any]:
        ttl_seconds = 30.0
        now = time.time()
        cached = self._maker_mcp_probe_cache.get("result")
        checked_at = float(self._maker_mcp_probe_cache.get("checked_at") or 0.0)
        if not force and isinstance(cached, dict) and cached and now - checked_at < ttl_seconds:
            return {
                **cached,
                "probe_check": "cached",
                "cache_ttl_seconds": ttl_seconds,
            }
        probe = probe_maker_mcp_config(config=self.agent.config)
        probe["probe_check"] = "ok" if probe.get("ok") else "failed"
        probe["cache_ttl_seconds"] = ttl_seconds
        self._maker_mcp_probe_cache = {
            "checked_at": time.time(),
            "result": probe,
        }
        return probe

    def reconnect_maker_mcp(self) -> Dict[str, Any]:
        before_setup = self.maker_setup_status(check_latest=False)
        before_faults = before_setup.get("fault_analysis") if isinstance(before_setup.get("fault_analysis"), dict) else {}
        if self._has_active_sessions():
            return {
                "ok": False,
                "error": "Cannot reconnect Maker MCP while an agent session is running.",
                "restart_required": False,
            }
        integration = getattr(self.agent, "mcp_integration", None)
        if integration is not None:
            try:
                integration.stop()
            except Exception:
                pass
        try:
            config_sync = ensure_internal_maker_mcp_latest_config(
                self.agent.config,
                Path(self.agent.config.project_root()),
            )
            if config_sync.get("changed"):
                self.agent.config.save()
            unregister_source = getattr(self.agent.tools, "unregister_source", None)
            if callable(unregister_source):
                unregister_source("maker_mcp")
                unregister_source("maker_mcp_unavailable")
            clear_maker_tools = getattr(self.agent.executor, "clear_maker_tools", None)
            if callable(clear_maker_tools):
                clear_maker_tools()
            self.agent.mcp_integration = MCPIntegration(
                config=self.agent.config,
                tools=self.agent.tools,
                executor=self.agent.executor,
                event_log=self.agent.event_log,
            )
            self.agent._owns_mcp_integration = True
            status = self.agent.mcp_integration.status() if self.agent.mcp_integration else {}
            audit = self.maker_tool_audit()
            return {
                "ok": bool(status.get("connected")),
                "status": status,
                "tool_audit": audit,
                "setup_status": self.maker_setup_status(check_latest=False),
                "config_sync": config_sync,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc), "tool_audit": self.maker_tool_audit()}

    def repair_maker_access(self) -> Dict[str, Any]:
        """Hot-repair Maker MCP wiring without closing the GUI.

        This keeps Electron/BrowserView alive and only refreshes the internal
        Maker MCP subprocess plus Agent tool registrations when no session is
        currently running.
        """
        before_setup = self.maker_setup_status(check_latest=False)
        before_faults = before_setup.get("fault_analysis") if isinstance(before_setup.get("fault_analysis"), dict) else {}
        if self._has_active_sessions():
            return {
                "ok": False,
                "hot_repair": False,
                "restart_required": False,
                "error": "当前 Agent 正在执行任务，无法同时重连 Maker MCP。请等待本轮结束后再修复。",
                "setup_status": before_setup,
                "tool_audit": self.maker_tool_audit(),
                "fault_analysis": before_faults,
            }
        reconnect = self.reconnect_maker_mcp()
        agent_root_sync = ensure_agent_root_maker_mcp_registration(APP_ROOT)
        audit = reconnect.get("tool_audit") if isinstance(reconnect.get("tool_audit"), dict) else self.maker_tool_audit()
        setup = reconnect.get("setup_status") if isinstance(reconnect.get("setup_status"), dict) else self.maker_setup_status(check_latest=False)
        if isinstance(setup, dict):
            setup["agent_root_mcp"] = agent_root_mcp_state(APP_ROOT)
            setup["fault_analysis"] = build_maker_fault_analysis(
                setup_status=setup,
                tool_audit=audit,
            )
        repair_ok = bool(audit.get("repair_ok") or audit.get("ok"))
        return {
            **reconnect,
            "ok": repair_ok,
            "hot_repair": True,
            "restart_required": False,
            "repair_status": "success" if audit.get("ok") else ("degraded_success" if repair_ok else "blocked"),
            "agent_root_mcp_sync": agent_root_sync,
            "tool_audit": audit,
            "setup_status": setup,
            "fault_analysis_before": before_faults,
            "fault_analysis": setup.get("fault_analysis", {}) if isinstance(setup, dict) else {},
        }

    def maker_setup_status(self, *, check_latest: bool = False) -> Dict[str, Any]:
        return build_maker_setup_status(
            config=self.agent.config,
            app_root=APP_ROOT,
            check_latest=check_latest,
            tool_audit=self.maker_tool_audit(),
            mcp_probe=self.maker_mcp_probe(force=False),
            pending_auth=self.pending_maker_auth,
        )

    def _has_active_sessions(self) -> bool:
        with self._lock:
            return any(not session.done for session in self._sessions.values())

    def _reload_agent_for_project(self, project_root: Path) -> Dict[str, Any]:
        if self._has_active_sessions():
            return {
                "ok": False,
                "error": "Cannot switch Maker project while an agent session is running.",
                "restart_required": False,
            }
        cfg = self.agent.config
        cfg.data["project_root"] = str(project_root.resolve())
        config_sync = ensure_internal_maker_mcp_latest_config(cfg, project_root)
        cfg.save()

        old_agent = self.agent
        try:
            provider = cfg.llm_provider() or "deepseek"
            try:
                llm = LLMFactory.create(provider, cfg)
            except Exception as e:
                llm = UnconfiguredLLM(str(e))
            new_agent = TapMakerAgent(
                llm=llm,
                config=cfg,
                human_confirm_callback=None,
            )
            new_agent.executor.set_browser_service(self.browser_service)
            self.agent = new_agent
            self.ide_service = IdeService(new_agent)
            self.skill_sync_registry = getattr(
                new_agent,
                "skill_sync_registry",
                SkillSyncRegistry(new_agent.config.project_root(), Path(new_agent.config.storage_root())),
            )
            try:
                old_agent.close()
            except Exception:
                pass
            record_recent_project(Path(cfg.storage_root()), project_root)
            return {
                "ok": True,
                "project_root": str(project_root.resolve()),
                "restart_required": False,
                "config_sync": config_sync,
                "setup_status": self.maker_setup_status(check_latest=False),
            }
        except Exception as e:
            self.agent = old_agent
            self.ide_service = IdeService(old_agent)
            self.skill_sync_registry = getattr(old_agent, "skill_sync_registry", self.skill_sync_registry)
            return {"ok": False, "error": str(e), "restart_required": True}

    def _provider_api_key(self, provider: str, explicit_key: Optional[str] = None) -> str:
        if explicit_key and explicit_key.strip():
            return explicit_key.strip()
        llm_cfg = self.agent.config.data.setdefault("llm", {})
        api_keys = llm_cfg.get("api_keys") or {}
        key = str(api_keys.get(provider) or llm_cfg.get("api_key") or "").strip()
        if key.startswith("sk-..."):
            return ""
        return key

    def _fetch_provider_models(
        self,
        provider: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        selected = (provider or self.agent.config.llm_provider() or "deepseek").lower().strip()
        preset = provider_preset(selected)
        hints = model_hints(selected)
        if selected == "local":
            return {"ok": True, "source": "local", "models": hints}

        key = self._provider_api_key(selected, api_key)
        if not key:
            return {
                "ok": True,
                "source": "preset",
                "models": hints,
                "needs_api_key": True,
                "message": "缺少 API Key，先展示内置候选模型。",
            }

        kind = preset.get("kind", "openai-compatible")
        if kind not in {"openai-compatible", "anthropic"}:
            return {
                "ok": True,
                "source": "preset",
                "models": hints,
                "message": "该厂商暂未接入在线模型列表，先展示内置候选模型。",
            }

        resolved_base = (base_url or preset.get("base_url") or "").rstrip("/")
        if not resolved_base:
            return {"ok": True, "source": "preset", "models": hints, "message": "缺少 Base URL。"}

        headers = {"Content-Type": "application/json"}
        if kind == "anthropic":
            url = f"{resolved_base}/models"
            headers["x-api-key"] = key
            headers["anthropic-version"] = "2023-06-01"
        else:
            url = f"{resolved_base}/models"
            headers["Authorization"] = f"Bearer {key}"

        try:
            req = request.Request(url, headers=headers, method="GET")
            with request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            items = data.get("data") if isinstance(data, dict) else []
            live_models: List[str] = []
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        model_id = item.get("id") or item.get("name")
                        if isinstance(model_id, str) and model_id:
                            live_models.append(model_id)
                    elif isinstance(item, str):
                        live_models.append(item)
            merged = []
            for model_id in [*hints, *live_models]:
                if model_id and model_id not in merged:
                    merged.append(model_id)
            return {"ok": True, "source": "api", "models": merged}
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            return {
                "ok": True,
                "source": "preset",
                "models": hints,
                "message": f"在线模型列表获取失败，已回退到内置候选：{e}",
            }

    def _probe_llm_runtime(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Make one tiny call against a cloned LLM config and return diagnostics."""
        cfg = self.agent.config.clone()
        selected = self._apply_llm_values_to_config(
            cfg,
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
        )
        llm_cfg = cfg.data.setdefault("llm", {})
        if timeout is not None:
            try:
                llm_cfg["timeout"] = max(1, min(float(timeout), 45.0))
            except (TypeError, ValueError):
                pass
        preset = provider_preset(selected)
        if selected == "mock":
            runtime_kind = "mock"
        elif preset.get("kind") == "local" or selected in {"local", "gguf"}:
            runtime_kind = "local"
        else:
            runtime_kind = "api"
        started = time.perf_counter()
        llm = None
        try:
            llm = LLMFactory.create(selected, cfg)
            prompt = "Reply with exactly TTM_PROBE_OK. No Markdown, no explanation."
            call = getattr(llm, "_call", None)
            if callable(call):
                try:
                    output = call(
                        "TTMEvolve runtime probe. Return exactly TTM_PROBE_OK.",
                        [{"role": "user", "content": prompt}],
                        max_tokens=16,
                        temperature=0.0,
                    )
                except TypeError:
                    output = call(
                        "TTMEvolve runtime probe. Return exactly TTM_PROBE_OK.",
                        [{"role": "user", "content": prompt}],
                        max_tokens=16,
                    )
            else:
                output = llm.think("TTMEvolve runtime probe", prompt, [], "")
            stats_getter = getattr(llm, "last_call_stats", None)
            stats = stats_getter() if callable(stats_getter) else {}
            result = {
                "ok": True,
                "status": "ok",
                "provider": selected,
                "runtime_kind": runtime_kind,
                "llm_class": llm.__class__.__name__,
                "model": llm_cfg.get("model") or preset.get("model", ""),
                "base_url": llm_cfg.get("base_url") or preset.get("base_url", ""),
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                "output_preview": str(output or "")[:160],
                "last_call_stats": stats,
            }
        except Exception as e:
            stats = {}
            if llm is not None:
                stats_getter = getattr(llm, "last_call_stats", None)
                if callable(stats_getter):
                    try:
                        stats = stats_getter()
                    except Exception:
                        stats = {}
            result = {
                "ok": False,
                "status": "error",
                "provider": selected,
                "runtime_kind": runtime_kind,
                "llm_class": llm.__class__.__name__ if llm is not None else "",
                "model": llm_cfg.get("model") or preset.get("model", ""),
                "base_url": llm_cfg.get("base_url") or preset.get("base_url", ""),
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                "error": str(e),
                "last_call_stats": stats,
            }
        self.last_llm_probe = dict(result)
        return result

    def _latest_llm_probe_for_session(self, session_id: str) -> Dict[str, Any]:
        if session_id and session_id != "{session_id}":
            history = self.session_store.get_llm_probe_history(session_id, limit=1)
            if history:
                latest = dict(history[-1])
                stats: Dict[str, Any] = {}
                for key in ("endpoint", "http_status", "total_tokens", "generate_ms", "error_type"):
                    if latest.get(key) is not None:
                        stats[key] = latest.get(key)
                latest["last_call_stats"] = stats
                return latest
        return dict(self.last_llm_probe)

    def _apply_llm_runtime_config(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        allow_unconfigured: bool = False,
    ) -> None:
        cfg = self.agent.config
        selected = self._apply_llm_values_to_config(
            cfg,
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
        )
        llm_cfg = cfg.data.setdefault("llm", {})
        preset = provider_preset(selected)

        is_api_provider = selected in OPENAI_COMPATIBLE_ALIASES or selected in {"claude", "anthropic", "minimax"}
        current_key = str(llm_cfg.get("api_key") or "").strip()
        has_api_key = bool(current_key and not current_key.startswith("sk-..."))
        if is_api_provider and not has_api_key and allow_unconfigured:
            label = preset.get("label", selected)
            env_var = preset.get("env_var") or "LLM_API_KEY"
            self.agent.set_llm(UnconfiguredLLM(f"{label} needs an API key. Fill it in the GUI or set {env_var}."))
            return

        self.agent.set_llm(LLMFactory.create(selected, cfg))

    def _has_session_llm_override(
        self,
        overrides: Dict[str, Optional[str]],
        stored: Dict[str, Any],
    ) -> bool:
        return any(
            overrides.get(key) is not None
            for key in ("provider", "model", "base_url", "api_key")
        ) or bool(stored.get("provider"))

    def _clone_active_llm(self):
        try:
            return copy.deepcopy(self.agent.llm)
        except Exception:
            return self.agent.llm

    def _build_session_agent(
        self,
        session: Session,
        overrides: Dict[str, Optional[str]],
        stored: Dict[str, Any],
    ) -> TapMakerAgent:
        session_cfg = self.agent.config.clone()
        has_override = self._has_session_llm_override(overrides, stored)
        if has_override:
            selected = overrides.get("provider") or stored.get("provider") or session_cfg.llm_provider()
            self._apply_llm_values_to_config(
                session_cfg,
                provider=selected,
                model=overrides.get("model"),
                base_url=overrides.get("base_url"),
                api_key=overrides.get("api_key"),
            )
            llm = LLMFactory.create(selected, session_cfg)
        else:
            llm = self._clone_active_llm()

        session_agent = TapMakerAgent(
            llm=llm,
            config=session_cfg,
            human_confirm_callback=None,
            connect_mcp=False,
            shared_mcp_integration=self.agent.mcp_integration,
            cancel_check=lambda: session.cancelled,
        )
        session_agent.executor.set_browser_service(self.browser_service)
        return session_agent

    def _apply_llm_values_to_config(
        self,
        cfg: Config,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> str:
        llm_cfg = cfg.data.setdefault("llm", {})
        previous = (llm_cfg.get("provider") or cfg.llm_provider() or "").lower().strip()
        selected = (provider or previous or "deepseek").lower().strip()
        provider_changed = bool(provider and selected != previous)
        preset = provider_preset(selected)
        api_keys = llm_cfg.setdefault("api_keys", {})
        legacy_key = str(llm_cfg.get("api_key") or "").strip()
        if previous and legacy_key and previous not in api_keys:
            api_keys[previous] = legacy_key
        llm_cfg["provider"] = selected
        if model is not None:
            llm_cfg["model"] = model
        elif selected != "local" and (provider_changed or not llm_cfg.get("model")):
            llm_cfg["model"] = preset.get("model", "")
        if base_url is not None:
            llm_cfg["base_url"] = base_url
        elif preset.get("base_url") and (provider_changed or not llm_cfg.get("base_url")):
            llm_cfg["base_url"] = preset.get("base_url", "")
        if api_key is not None and api_key.strip():
            api_keys[selected] = api_key.strip()
        llm_cfg["api_key"] = api_keys.get(selected, "")
        return selected

    def _new_session_id(self) -> str:
        return str(uuid.uuid4())[:8]

    def create_session(self, req: SessionRequest) -> str:
        sid = req.session_id or self._new_session_id()
        self.session_store.create_session(
            sid,
            req.task,
            provider=req.provider,
            profile=req.profile,
        )
        with self._lock:
            self._sessions[sid] = Session(sid, req.task, store=self.session_store)
            self._session_llm_overrides[sid] = {
                "provider": req.provider,
                "model": req.model,
                "base_url": req.base_url,
                "api_key": req.api_key,
            }
        return sid

    def run_session(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
        if not session:
            return

        stored = self.session_store.get_session(session_id) or {}
        overrides = self._session_llm_overrides.get(session_id, {})
        try:
            session_agent = self._build_session_agent(session, overrides, stored)
        except Exception as e:
            session.error = str(e)
            session.emit({
                "type": "error",
                "session_id": session_id,
                "payload": {"message": f"LLM 初始化失败: {e}", "fatal": True},
            })
            self.session_store.mark_done(session_id, error=session.error)
            session.done = True
            session.emit({
                "type": "status",
                "session_id": session_id,
                "payload": {"message": "任务结束", "done": True},
            })
            return

        bridge = self._approval_bridge

        def event_sink(event: Dict[str, Any]) -> None:
            session.emit(event)

        def confirm_callback(message: str) -> bool:
            """Server 模式下的人类确认回调：通过 SSE 发送审批请求并阻塞等待 GUI 响应。"""
            if session.cancelled:
                raise TaskCancelled()
            action_id = str(uuid.uuid4())[:8]
            session.pending_action_id = action_id
            session.emit({
                "type": "approval_request",
                "session_id": session_id,
                "payload": {
                    "action_id": action_id,
                    "message": message,
                },
            })
            allowed = bridge.request(session_id, action_id)
            session.pending_action_id = None
            if session.cancelled:
                raise TaskCancelled()
            return allowed

        original_sink = session_agent.react.event_sink
        original_agent_sink = getattr(session_agent, "event_sink", None)
        original_agent_cb = session_agent.human_confirm_callback
        original_executor_cb = session_agent.executor.human_confirm_callback
        original_approval_cb = session_agent.executor.approval.human_confirm_callback
        original_evolution_cb = getattr(session_agent.evolution_protocol, "_human_confirm_callback", None)

        session_agent.react.event_sink = event_sink
        session_agent.event_sink = event_sink
        session_agent.human_confirm_callback = confirm_callback
        session_agent.executor.human_confirm_callback = confirm_callback
        session_agent.executor.approval.human_confirm_callback = confirm_callback
        if original_evolution_cb is not None:
            session_agent.evolution_protocol._human_confirm_callback = confirm_callback

        try:
            if session.cancelled:
                raise TaskCancelled()
            result = session_agent.run(session.task, session_id=session_id)
            session.result = result
        except TaskCancelled as e:
            session.cancelled = True
            session.result = {
                "session_id": session_id,
                "task": session.task,
                "output": "",
                "iteration_count": len(session_agent.react.trajectory),
                "trajectory": session_agent.react.trajectory,
                "cancelled": True,
            }
            session.emit({
                "type": "status",
                "session_id": session_id,
                "payload": {"message": str(e), "canceled": True},
            })
        except Exception as e:
            session.error = str(e)
            stats_getter = getattr(session_agent.llm, "last_call_stats", None)
            if callable(stats_getter):
                try:
                    stats = stats_getter()
                except Exception:
                    stats = {}
                if stats:
                    session.emit({
                        "type": "llm_usage",
                        "session_id": session_id,
                        "payload": {"phase": "fatal_error", **stats},
                    })
            session.emit({
                "type": "error",
                "session_id": session_id,
                "payload": {"message": str(e), "fatal": True},
            })
        finally:
            session_agent.react.event_sink = original_sink
            session_agent.event_sink = original_agent_sink
            session_agent.human_confirm_callback = original_agent_cb
            session_agent.executor.human_confirm_callback = original_executor_cb
            session_agent.executor.approval.human_confirm_callback = original_approval_cb
            if original_evolution_cb is not None:
                session_agent.evolution_protocol._human_confirm_callback = original_evolution_cb
            session_agent.close()
            if session.cancelled:
                self.session_store.mark_cancelled(session_id, result=session.result)
            else:
                self.session_store.mark_done(
                    session_id,
                    result=session.result,
                    error=session.error,
                )
            session.done = True
            session.emit({
                "type": "status",
                "session_id": session_id,
                "payload": {
                    "message": "任务已取消" if session.cancelled else "任务结束",
                    "done": True,
                    "canceled": session.cancelled,
                },
            })

    def cancel_session(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
        if not session:
            stored = self.session_store.get_session(session_id)
            if not stored:
                return {"ok": False, "status": 404, "error": "Session not found"}
            if stored.get("status") in ("done", "error", "canceled"):
                return {"ok": False, "status": 409, "error": "Session already finished"}
            self.session_store.mark_cancelled(session_id)
            return {"ok": True, "status": 200, "session_id": session_id, "canceled": True}

        changed = session.cancel()
        if not changed:
            return {"ok": False, "status": 409, "error": "Session already finished"}

        if session.pending_action_id:
            self._approval_bridge.respond(session_id, session.pending_action_id, False)
        session.emit({
            "type": "status",
            "session_id": session_id,
            "payload": {"message": "正在取消任务", "canceled": True},
        })
        return {"ok": True, "status": 200, "session_id": session_id, "canceled": True}

    def get_session(self, session_id: str) -> Optional[Session]:
        with self._lock:
            return self._sessions.get(session_id)

    def make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def handle(self) -> None:
                try:
                    super().handle()
                except (ConnectionResetError, BrokenPipeError, OSError):
                    pass

            def log_message(self, format: str, *args: Any) -> None:
                # 静默日志，减少噪音
                pass

            def _json_response(self, status: int, data: Dict[str, Any]) -> None:
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

            def _text_response(self, status: int, text: str, mime: str = "text/plain; charset=utf-8") -> None:
                body = text.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

            def _serve_bytes(self, status: int, data: bytes, mime: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)

            def _path_from_query(self, query: str, key: str = "path") -> str:
                params = parse_qs(query)
                return params.get(key, [""])[0]

            def _query_param(self, query: str, key: str, default: str = "") -> str:
                params = parse_qs(query)
                values = params.get(key)
                return values[0] if values else default

            def _serve_static(self, relative_path: str) -> None:
                """从 web/ 目录提供静态文件。"""
                base = server.WEB_DIR.resolve()
                target = (base / relative_path).resolve()
                try:
                    target.relative_to(base)
                except ValueError:
                    self.send_error(404, "Not found")
                    return
                if not target.exists():
                    self.send_error(404, "Not found")
                    return
                content = target.read_bytes()
                mime_types = {
                    ".html": "text/html; charset=utf-8",
                    ".css": "text/css; charset=utf-8",
                    ".js": "application/javascript; charset=utf-8",
                    ".json": "application/json; charset=utf-8",
                    ".png": "image/png",
                    ".svg": "image/svg+xml",
                }
                mime = mime_types.get(target.suffix, "application/octet-stream")
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)

            def _sse_stream(self, session_id: str) -> None:
                session = server.get_session(session_id)
                if not session:
                    self.send_error(404, "Session not found")
                    return

                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                for event in session.iter_events():
                    data = json.dumps(event, ensure_ascii=False)
                    try:
                        self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        break

            def do_OPTIONS(self) -> None:
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path
                import traceback as _tb

                if path == "/" or path == "/index.html":
                    self._serve_static("index.html")
                    return

                if path.startswith("/web/"):
                    self._serve_static(path[len("/web/"):])
                    return

                if path == "/health":
                    cfg = server.agent.config
                    llm = server.agent.llm
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
                    api_key = str(llm_cfg.get("api_key") or "").strip()
                    model_path = str(cfg.local_model_path())
                    if hasattr(llm, "tuning_info"):
                        try:
                            llm_params = llm.tuning_info()
                        except Exception:
                            llm_params = {}
                    else:
                        llm_params = {}
                    llm_params.update({
                        "cache_type_k": cfg.get("llm.cache_type_k", None),
                        "cache_type_v": cfg.get("llm.cache_type_v", None),
                        "kv_cache": cfg.get("llm.compression.enable_kv_cache", False),
                    })
                    last_call_stats = {}
                    if hasattr(llm, "last_call_stats"):
                        try:
                            last_call_stats = llm.last_call_stats()
                        except Exception:
                            last_call_stats = {}
                    loaded = bool(getattr(llm, "_model", None) is not None)
                    llama_cpp_available = False
                    try:
                        import llama_cpp  # type: ignore
                        llama_cpp_available = True
                    except Exception:
                        llama_cpp_available = False
                    self._json_response(200, {
                        "status": "ok",
                        "provider": provider,
                        "runtime_kind": runtime_kind,
                        "model": resolved_model,
                        "base_url": resolved_base_url,
                        "api_key_set": bool(api_key and not api_key.startswith("sk-...")),
                        "model_path": model_path,
                        "model_exists": Path(model_path).exists(),
                        "llm_class": llm.__class__.__name__,
                        "llm_configured": llm.__class__.__name__ != "UnconfiguredLLM",
                        "llama_cpp_available": llama_cpp_available,
                        "llm_loaded": loaded,
                        "llm_params": llm_params,
                        "last_call_stats": last_call_stats,
                        "last_probe": server.last_llm_probe,
                    })
                    return

                if path == "/config":
                    cfg = server.agent.config
                    maker_cfg = cfg.maker_mcp_config()
                    llm_cfg = cfg.llm_config()
                    self._json_response(200, {
                        "provider": cfg.llm_provider(),
                        "model": llm_cfg.get("model", ""),
                        "base_url": llm_cfg.get("base_url", ""),
                        "api_key_set": bool(llm_cfg.get("api_key", "")),
                        "profile": cfg.active_profile(),
                        "project_root": str(cfg.project_root()),
                        "maker_mcp": {
                            "command": maker_cfg.get("command", ""),
                            "args": maker_cfg.get("args", []),
                            "env": maker_cfg.get("env", {}),
                        },
                    })
                    return

                if path == "/llm/providers":
                    self._json_response(200, {"providers": PROVIDER_PRESETS})
                    return

                if path == "/api/settings/runtime-info":
                    self._json_response(200, build_settings_runtime_info(server))
                    return

                if path == "/api/settings/llm-providers":
                    self._json_response(200, build_provider_summary(server))
                    return

                if path == "/llm/feedback-summary":
                    self._json_response(200, build_llm_feedback_summary())
                    return

                if path == "/runtime/readiness":
                    params = parse_qs(parsed.query)
                    session_id = (params.get("session_id") or ["{session_id}"])[0]
                    if session_id != "{session_id}" and not server.get_session(session_id) and not server.session_store.get_session(session_id):
                        self.send_error(404, "Session not found")
                        return
                    self._json_response(200, build_runtime_readiness(server=server, session_id=session_id))
                    return

                if path == "/runtime/portable":
                    self._json_response(200, build_portable_runtime_status(server=server))
                    return

                if path == "/sessions":
                    sessions = server.session_store.list_sessions(limit=100)
                    self._json_response(200, {"sessions": sessions})
                    return

                if path.startswith("/sessions/") and path.endswith("/events"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        self._sse_stream(parts[2])
                        return

                if path.startswith("/sessions/") and path.endswith("/status"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        session = server.get_session(parts[2])
                        if not session:
                            # 内存里没有，尝试从 SQLite 读取
                            stored = server.session_store.get_session(parts[2])
                            if not stored:
                                self.send_error(404, "Session not found")
                                return
                            self._json_response(200, {
                                "session_id": stored["session_id"],
                                "task": stored["task"],
                                "done": stored["status"] in ("done", "error", "canceled"),
                                "error": stored["error"],
                                "status": stored["status"],
                                "canceled": stored["status"] == "canceled",
                            })
                            return
                        self._json_response(200, {
                            "session_id": session.session_id,
                            "task": session.task,
                            "done": session.done,
                            "status": "canceled" if session.cancelled else ("error" if session.error else ("done" if session.done else "running")),
                            "error": session.error,
                            "canceled": session.cancelled,
                        })
                        return

                if (
                    path.startswith("/sessions/")
                    and (path.endswith("/commit-history") or path.endswith("/submissions"))
                ):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        stored = server.session_store.get_session(sid)
                        if not stored and not server.get_session(sid):
                            self.send_error(404, "Session not found")
                            return
                        params = parse_qs(parsed.query)
                        try:
                            steps = int((params.get("steps") or params.get("limit") or ["100"])[0])
                        except (TypeError, ValueError):
                            steps = 100
                        steps = max(1, min(steps, 500))
                        history = server.session_store.get_commit_history(sid, limit=steps)
                        self._json_response(200, {
                            "session_id": sid,
                            "commit_history": history,
                            "count": len(history),
                        })
                        return

                if path.startswith("/sessions/") and path.endswith("/context-sync"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        stored = server.session_store.get_session(sid)
                        if not stored and not server.get_session(sid):
                            self.send_error(404, "Session not found")
                            return
                        params = parse_qs(parsed.query)
                        try:
                            steps = int((params.get("steps") or params.get("limit") or ["100"])[0])
                        except (TypeError, ValueError):
                            steps = 100
                        steps = max(1, min(steps, 500))
                        history = server.session_store.get_context_sync_history(sid, limit=steps)
                        self._json_response(200, {
                            "session_id": sid,
                            "context_sync": history,
                            "latest": history[-1] if history else None,
                            "count": len(history),
                        })
                        return

                if path.startswith("/sessions/") and path.endswith("/runtime-metrics"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        stored = server.session_store.get_session(sid)
                        if not stored and not server.get_session(sid):
                            self.send_error(404, "Session not found")
                            return
                        params = parse_qs(parsed.query)
                        try:
                            steps = int((params.get("steps") or params.get("limit") or ["100"])[0])
                        except (TypeError, ValueError):
                            steps = 100
                        steps = max(1, min(steps, 500))
                        metrics = server.session_store.get_runtime_metrics_history(sid, limit=steps)
                        self._json_response(200, {
                            "session_id": sid,
                            "runtime_metrics": metrics,
                            "latest": metrics[-1] if metrics else None,
                            "summary": summarize_runtime_metrics(metrics),
                            "count": len(metrics),
                        })
                        return

                if path.startswith("/sessions/") and path.endswith("/learning"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        stored = server.session_store.get_session(sid)
                        if not stored and not server.get_session(sid):
                            self.send_error(404, "Session not found")
                            return
                        params = parse_qs(parsed.query)
                        try:
                            steps = int((params.get("steps") or params.get("limit") or ["100"])[0])
                        except (TypeError, ValueError):
                            steps = 100
                        steps = max(1, min(steps, 500))
                        history = server.session_store.get_learning_history(sid, limit=steps)
                        self._json_response(200, {
                            "session_id": sid,
                            "learning": history,
                            "latest": history[-1] if history else None,
                            "count": len(history),
                        })
                        return

                if path.startswith("/sessions/") and path.endswith("/maker-guard"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        stored = server.session_store.get_session(sid)
                        if not stored and not server.get_session(sid):
                            self.send_error(404, "Session not found")
                            return
                        params = parse_qs(parsed.query)
                        try:
                            steps = int((params.get("steps") or params.get("limit") or ["100"])[0])
                        except (TypeError, ValueError):
                            steps = 100
                        steps = max(1, min(steps, 500))
                        history = server.session_store.get_maker_guard_history(sid, limit=steps)
                        self._json_response(200, {
                            "session_id": sid,
                            "maker_guard": history,
                            "latest": history[-1] if history else None,
                            "count": len(history),
                        })
                        return

                if path.startswith("/sessions/") and path.endswith("/llm-probe"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        stored = server.session_store.get_session(sid)
                        if not stored and not server.get_session(sid):
                            self.send_error(404, "Session not found")
                            return
                        params = parse_qs(parsed.query)
                        try:
                            steps = int((params.get("steps") or params.get("limit") or ["100"])[0])
                        except (TypeError, ValueError):
                            steps = 100
                        steps = max(1, min(steps, 500))
                        history = server.session_store.get_llm_probe_history(sid, limit=steps)
                        self._json_response(200, {
                            "session_id": sid,
                            "llm_probe": history,
                            "latest": history[-1] if history else None,
                            "count": len(history),
                        })
                        return

                if path.startswith("/sessions/") and (path.endswith("/evidence") or path.endswith("/evidence.md")):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        stored = server.session_store.get_session(sid)
                        if not stored and not server.get_session(sid):
                            self.send_error(404, "Session not found")
                            return
                        params = parse_qs(parsed.query)
                        try:
                            steps = int((params.get("steps") or params.get("limit") or ["20"])[0])
                        except (TypeError, ValueError):
                            steps = 20
                        steps = max(1, min(steps, 100))
                        bundle = build_session_evidence_bundle(
                            server=server,
                            session_id=sid,
                            steps=steps,
                        )
                        wants_markdown = (
                            path.endswith(".md")
                            or str((params.get("format") or [""])[0]).lower() in {"md", "markdown", "text"}
                        )
                        if wants_markdown:
                            self._text_response(
                                200,
                                render_session_evidence_markdown(bundle),
                                "text/markdown; charset=utf-8",
                            )
                            return
                        self._json_response(200, bundle)
                        return

                if path.startswith("/sessions/") and path.endswith("/runtime-advice"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        stored = server.session_store.get_session(sid)
                        if not stored and not server.get_session(sid):
                            self.send_error(404, "Session not found")
                            return
                        params = parse_qs(parsed.query)
                        try:
                            steps = int((params.get("steps") or params.get("limit") or ["20"])[0])
                        except (TypeError, ValueError):
                            steps = 20
                        steps = max(1, min(steps, 500))
                        task = (stored or {}).get("task", "")
                        maker_briefing = server.agent.maker_briefing(session_id=sid, task=task)
                        context_history = server.session_store.get_context_sync_history(sid, limit=min(steps, 20))
                        runtime_metrics = server.session_store.get_runtime_metrics_history(sid, limit=steps)
                        learning_history = server.session_store.get_learning_history(sid, limit=steps)
                        maker_guard_history = server.session_store.get_maker_guard_history(sid, limit=steps)
                        advice = build_runtime_advice(
                            maker_briefing=maker_briefing,
                            maker_guard_history=maker_guard_history,
                            runtime_metrics_summary=summarize_runtime_metrics(runtime_metrics),
                            learning_latest=learning_history[-1] if learning_history else None,
                            latest_context_sync=context_history[-1] if context_history else None,
                            llm_probe_latest=server._latest_llm_probe_for_session(sid),
                        )
                        self._json_response(200, {
                            "session_id": sid,
                            "runtime_advice": advice,
                        })
                        return

                # GET /sessions/{id}
                if path.startswith("/sessions/"):
                    parts = path.split("/")
                    if len(parts) == 3:
                        sid = parts[2]
                        # 优先读内存
                        session = server.get_session(sid)
                        if session:
                            status = "canceled" if session.cancelled else ("error" if session.error else ("done" if session.done else "running"))
                            self._json_response(200, {
                                "session_id": session.session_id,
                                "task": session.task,
                                "done": session.done,
                                "status": status,
                                "error": session.error,
                                "canceled": session.cancelled,
                                "result": session.result,
                            })
                            return
                        stored = server.session_store.get_session(sid)
                        if stored:
                            self._json_response(200, stored)
                            return
                        self.send_error(404, "Session not found")
                        return

                if path == "/fs/list":
                    fs_path = self._path_from_query(parsed.query)
                    result, status = server.ide_service.list_directory(fs_path)
                    self._json_response(status, result)
                    return

                if path == "/fs/read":
                    fs_path = self._path_from_query(parsed.query)
                    result, status = server.ide_service.read_file(fs_path)
                    self._json_response(status, result)
                    return

                if path == "/preview/file":
                    fs_path = self._path_from_query(parsed.query)
                    ok, data, mime, status = server.ide_service.preview_file(fs_path)
                    self._serve_bytes(status, data, mime)
                    return

                if path == "/fs/assets":
                    fs_path = self._path_from_query(parsed.query)
                    extensions = self._query_param(parsed.query, "extensions")
                    result, status = server.ide_service.scan_assets(fs_path, extensions)
                    self._json_response(status, result)
                    return

                if path == "/fs/stat":
                    fs_path = self._path_from_query(parsed.query)
                    result, status = server.ide_service.stat_file(fs_path)
                    self._json_response(status, result)
                    return

                if path == "/browser/info":
                    result = server.browser_service.get_info()
                    self._json_response(200 if result.get("ok") else 503, result)
                    return

                if path == "/browser/screenshot":
                    result = server.browser_service.screenshot()
                    if not result.get("ok"):
                        self._json_response(503, result)
                        return
                    data = base64.b64decode(result["data"])
                    self._serve_bytes(200, data, result.get("mime", "image/jpeg"))
                    return

                if path == "/browser/logs":
                    result = server.browser_service.get_logs()
                    self._json_response(200 if result.get("ok") else 503, result)
                    return

                if path in {"/maker/setup-status", "/maker/setup-status.md"}:
                    params = parse_qs(parsed.query)
                    check_latest = str((params.get("check_latest") or ["false"])[0]).lower() in {"1", "true", "yes"}
                    status = server.maker_setup_status(check_latest=check_latest)
                    wants_markdown = path.endswith(".md") or str((params.get("format") or [""])[0]).lower() in {"md", "markdown", "text"}
                    if wants_markdown:
                        self._text_response(200, render_maker_setup_markdown(status), "text/markdown; charset=utf-8")
                        return
                    self._json_response(200, status)
                    return

                if path == "/maker/tool-audit":
                    self._json_response(200, server.maker_tool_audit())
                    return

                if path == "/maker/auth/state":
                    self._json_response(200, {
                        "pending": server.pending_maker_auth,
                        "complete": complete_auth_flow(),
                        "maker_url": MAKER_URL,
                    })
                    return

                if path == "/maker/practice/status":
                    self._json_response(200, server.maker_practice_runner.status())
                    return

                if path == "/mcp/status":
                    params = parse_qs(parsed.query)
                    wants_probe = str((params.get("probe") or ["false"])[0]).lower() in {"1", "true", "yes"}
                    integration = server.agent.mcp_integration
                    if not integration:
                        status = {
                            "connected": False,
                            "tool_count": 0,
                            "tools": [],
                            "last_error": "Maker MCP integration is not configured",
                            "last_call": None,
                        }
                        if wants_probe:
                            status["probe"] = server.maker_mcp_probe(force=True)
                        self._json_response(200, status)
                        return
                    status = integration.status()
                    if wants_probe:
                        status["probe"] = server.maker_mcp_probe(force=True)
                    else:
                        status["probe"] = server.maker_mcp_probe(force=False)
                    self._json_response(200, status)
                    return

                if path == "/mcp/probe":
                    params = parse_qs(parsed.query)
                    force_probe = str((params.get("force") or ["true"])[0]).lower() not in {"0", "false", "no"}
                    self._json_response(200, server.maker_mcp_probe(force=force_probe))
                    return

                if path == "/mcp/tools":
                    integration = server.agent.mcp_integration
                    if not integration:
                        self._json_response(200, {"tools": []})
                        return
                    status = integration.status()
                    self._json_response(200, {"tools": status.get("tools", [])})
                    return

                if path == "/tools":
                    tools = [
                        {
                            "name": t["name"],
                            "description": t.get("description", ""),
                            "parameters": t.get("parameters", {}),
                        }
                        for t in server.agent.tools.list_tools()
                    ]
                    self._json_response(200, {"tools": tools})
                    return

                if path == "/agent/runtime-contract":
                    params = parse_qs(parsed.query)
                    session_id = (params.get("session_id") or ["{session_id}"])[0]
                    self._json_response(200, server.agent.runtime_contract(session_id=session_id))
                    return

                if path in {"/agent/onboarding", "/agent/onboarding.md"}:
                    params = parse_qs(parsed.query)
                    session_id = (params.get("session_id") or ["{session_id}"])[0]
                    try:
                        steps = int((params.get("steps") or params.get("limit") or ["20"])[0])
                    except (TypeError, ValueError):
                        steps = 20
                    steps = max(1, min(steps, 100))
                    surface = (params.get("surface") or ["generic"])[0]
                    if session_id != "{session_id}" and not server.get_session(session_id) and not server.session_store.get_session(session_id):
                        self.send_error(404, "Session not found")
                        return
                    bundle = build_llm_onboarding_bundle(
                        server=server,
                        session_id=session_id,
                        steps=steps,
                        surface=surface,
                    )
                    wants_markdown = (
                        path.endswith(".md")
                        or str((params.get("format") or [""])[0]).lower() in {"md", "markdown", "text"}
                    )
                    if wants_markdown:
                        self._text_response(
                            200,
                            str(bundle.get("prompt_markdown") or ""),
                            "text/markdown; charset=utf-8",
                        )
                        return
                    self._json_response(200, bundle)
                    return

                if path == "/agent/maker-briefing":
                    params = parse_qs(parsed.query)
                    session_id = (params.get("session_id") or ["{session_id}"])[0]
                    task = (params.get("task") or [""])[0]
                    if session_id != "{session_id}" and not server.get_session(session_id) and not server.session_store.get_session(session_id):
                        self.send_error(404, "Session not found")
                        return
                    self._json_response(200, server.agent.maker_briefing(session_id=session_id, task=task))
                    return

                if path == "/agent/handoff":
                    params = parse_qs(parsed.query)
                    session_id = (params.get("session_id") or ["{session_id}"])[0]
                    try:
                        steps = int((params.get("steps") or params.get("limit") or ["3"])[0])
                    except (TypeError, ValueError):
                        steps = 3
                    steps = max(1, min(steps, 20))
                    if session_id != "{session_id}" and not server.get_session(session_id) and not server.session_store.get_session(session_id):
                        self.send_error(404, "Session not found")
                        return
                    contract = server.agent.runtime_contract(session_id=session_id)
                    maker_briefing = server.agent.maker_briefing(
                        session_id=session_id,
                        task=(server.session_store.get_session(session_id) or {}).get("task", "") if session_id != "{session_id}" else "",
                    )
                    context_history = []
                    runtime_metrics = []
                    learning_history = []
                    maker_guard_history = []
                    if session_id != "{session_id}":
                        context_history = server.session_store.get_context_sync_history(session_id, limit=steps)
                        runtime_metrics = server.session_store.get_runtime_metrics_history(session_id, limit=20)
                        learning_history = server.session_store.get_learning_history(session_id, limit=20)
                        maker_guard_history = server.session_store.get_maker_guard_history(session_id, limit=20)
                    try:
                        skill_status = server.skill_sync_registry.status(force=False)
                    except Exception as e:
                        skill_status = {"ok": False, "error": str(e)}
                    skill_graph = skill_status.get("skill_graph") if isinstance(skill_status, dict) else {}
                    registry = skill_status.get("registry") if isinstance(skill_status, dict) else {}
                    manifest = skill_status.get("manifest") if isinstance(skill_status, dict) else {}
                    runtime_summary = summarize_runtime_metrics(runtime_metrics)
                    learning_latest = learning_history[-1] if learning_history else None
                    latest_context_sync = context_history[-1] if context_history else None
                    llm_probe_latest = server._latest_llm_probe_for_session(session_id)
                    runtime_advice = build_runtime_advice(
                        maker_briefing=maker_briefing,
                        maker_guard_history=maker_guard_history,
                        runtime_metrics_summary=runtime_summary,
                        learning_latest=learning_latest,
                        latest_context_sync=latest_context_sync,
                        llm_probe_latest=llm_probe_latest,
                    )
                    self._json_response(200, {
                        "session_id": session_id,
                        "runtime_contract": contract,
                        "maker_briefing": maker_briefing,
                        "latest_context_sync": latest_context_sync,
                        "context_sync": context_history,
                        "runtime_metrics_summary": runtime_summary,
                        "learning_latest": learning_latest,
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
                    })
                    return

                if path in {"/agent/quickstart", "/agent/quickstart.md"}:
                    params = parse_qs(parsed.query)
                    session_id = (params.get("session_id") or ["{session_id}"])[0]
                    try:
                        steps = int((params.get("steps") or (params.get("limit") or ["3"]))[0])
                    except (TypeError, ValueError):
                        steps = 3
                    steps = max(1, min(steps, 20))
                    surface = (params.get("surface") or ["generic"])[0]
                    if session_id != "{session_id}" and not server.get_session(session_id) and not server.session_store.get_session(session_id):
                        self.send_error(404, "Session not found")
                        return
                    stored = server.session_store.get_session(session_id) if session_id != "{session_id}" else {}
                    task = (stored or {}).get("task", "") if session_id != "{session_id}" else ""
                    contract = server.agent.runtime_contract(session_id=session_id)
                    maker_briefing = server.agent.maker_briefing(session_id=session_id, task=task)
                    context_history = []
                    runtime_metrics = []
                    learning_history = []
                    maker_guard_history = []
                    if session_id != "{session_id}":
                        context_history = server.session_store.get_context_sync_history(session_id, limit=steps)
                        runtime_metrics = server.session_store.get_runtime_metrics_history(session_id, limit=20)
                        learning_history = server.session_store.get_learning_history(session_id, limit=20)
                        maker_guard_history = server.session_store.get_maker_guard_history(session_id, limit=20)
                    llm_probe_latest = server._latest_llm_probe_for_session(session_id)
                    runtime_advice = build_runtime_advice(
                        maker_briefing=maker_briefing,
                        maker_guard_history=maker_guard_history,
                        runtime_metrics_summary=summarize_runtime_metrics(runtime_metrics),
                        learning_latest=learning_history[-1] if learning_history else None,
                        latest_context_sync=context_history[-1] if context_history else None,
                        llm_probe_latest=llm_probe_latest,
                    )
                    quickstart = build_llm_quickstart_bundle(
                        session_id=session_id,
                        task=task,
                        contract=contract,
                        maker_briefing=maker_briefing,
                        runtime_advice=runtime_advice,
                        context_history=context_history,
                        surface=surface,
                        llm_probe_latest=llm_probe_latest,
                    )
                    wants_markdown = (
                        path.endswith(".md")
                        or str((params.get("format") or [""])[0]).lower() in {"md", "markdown", "text"}
                    )
                    if wants_markdown:
                        self._text_response(
                            200,
                            str(quickstart.get("prompt_markdown") or quickstart.get("prompt") or ""),
                            "text/markdown; charset=utf-8",
                        )
                        return
                    self._json_response(200, quickstart)
                    return

                if path == "/skills/sync-status":
                    params = parse_qs(parsed.query)
                    force = str((params.get("force") or ["false"])[0]).lower() in {"1", "true", "yes"}
                    self._json_response(200, server.skill_sync_registry.status(force=force))
                    return

                # 兜底：未匹配的请求 → 404
                # 提示：当 path 是 /api/settings/* 但仍 404，说明前一个 if 块
                # 在调用 build_* 时抛了异常，被 Python 异常机制吞掉。
                import sys as _dbg_sys
                _dbg_sys.stderr.write(f"[do_GET-404] path={path!r}\n")
                _dbg_sys.stderr.flush()
                self.send_error(404, "Not found")

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                try:
                    data = json.loads(body) if body else {}
                except json.JSONDecodeError:
                    self._json_response(400, {"error": "Invalid JSON"})
                    return

                if path == "/api/settings/devtools":
                    self._json_response(200, build_settings_devtools_clear())
                    return

                if path == "/sessions":
                    req = SessionRequest(
                        task=data.get("task", ""),
                        profile=data.get("profile"),
                        provider=data.get("provider"),
                        model=data.get("model"),
                        base_url=data.get("base_url"),
                        api_key=data.get("api_key"),
                        session_id=data.get("session_id"),
                    )
                    sid = server.create_session(req)
                    # 启动后台线程执行任务
                    thread = threading.Thread(
                        target=server.run_session,
                        args=(sid,),
                        daemon=True,
                    )
                    thread.start()
                    self._json_response(202, {"session_id": sid, "status": "accepted"})
                    return

                if path == "/config/llm":
                    selected = server._apply_llm_values_to_config(
                        server.agent.config,
                        provider=data.get("provider"),
                        model=data.get("model") if "model" in data else None,
                        base_url=data.get("base_url") if "base_url" in data else None,
                        api_key=data.get("api_key"),
                    )
                    server.agent.config.save()
                    server._apply_llm_runtime_config(
                        provider=selected,
                        allow_unconfigured=True,
                    )
                    llm_cfg = server.agent.config.data.setdefault("llm", {})
                    self._json_response(200, {
                        "ok": True,
                        "provider": llm_cfg.get("provider"),
                        "model": llm_cfg.get("model", ""),
                        "base_url": llm_cfg.get("base_url", ""),
                        "api_key_set": bool(llm_cfg.get("api_key", "")),
                    })
                    return

                if path == "/llm/models":
                    provider = data.get("provider") or server.agent.config.llm_provider()
                    result = server._fetch_provider_models(
                        provider=provider,
                        base_url=data.get("base_url"),
                        api_key=data.get("api_key"),
                    )
                    self._json_response(200, result)
                    return

                if path == "/llm/probe":
                    session_id = data.get("session_id")
                    if session_id:
                        stored = server.session_store.get_session(session_id)
                        if not stored and not server.get_session(session_id):
                            self.send_error(404, "Session not found")
                            return
                    result = server._probe_llm_runtime(
                        provider=data.get("provider") or server.agent.config.llm_provider(),
                        model=data.get("model"),
                        base_url=data.get("base_url"),
                        api_key=data.get("api_key"),
                        timeout=data.get("timeout"),
                    )
                    if session_id:
                        session = server.get_session(session_id)
                        if session:
                            session.emit({
                                "type": "llm_probe",
                                "payload": result,
                                "source": "runtime",
                            })
                        else:
                            server.session_store.append_event(
                                session_id,
                                "llm_probe",
                                result,
                                source="runtime",
                            )
                    self._json_response(200 if result.get("ok") else 502, result)
                    return

                if path == "/maker/project/select":
                    raw_path = str(data.get("path") or "").strip()
                    if not raw_path:
                        self._json_response(400, {"ok": False, "error": "path is required"})
                        return
                    target = Path(raw_path).expanduser().resolve()
                    create = bool(data.get("create", False))
                    if create:
                        try:
                            target.mkdir(parents=True, exist_ok=True)
                        except Exception as e:
                            self._json_response(500, {"ok": False, "error": str(e)})
                            return
                    if not target.exists() or not target.is_dir():
                        self._json_response(400, {
                            "ok": False,
                            "error": "Project path must be an existing directory, or pass create=true.",
                            "path": str(target),
                        })
                        return
                    result = server._reload_agent_for_project(target)
                    self._json_response(200 if result.get("ok") else 409, result)
                    return

                if path == "/mcp/reconnect":
                    result = server.reconnect_maker_mcp()
                    self._json_response(200 if result.get("ok") else 409, result)
                    return

                if path == "/maker/repair":
                    result = server.repair_maker_access()
                    self._json_response(200 if result.get("ok") else 409, result)
                    return

                if path == "/maker/practice/start":
                    raw_path = str(data.get("path") or "").strip()
                    if raw_path:
                        target = Path(raw_path).expanduser().resolve()
                    else:
                        name = str(data.get("project_name") or "smoke-maker-game").strip() or "smoke-maker-game"
                        safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in name).strip("-_")
                        target = (APP_ROOT / "workspace" / (safe_name or "smoke-maker-game")).resolve()
                    if target == APP_ROOT.resolve():
                        self._json_response(400, {
                            "ok": False,
                            "error": "Refusing to use the TTMEvolve app root as the Maker game project.",
                            "path": str(target),
                        })
                        return
                    try:
                        target.mkdir(parents=True, exist_ok=True)
                    except Exception as e:
                        self._json_response(500, {"ok": False, "error": str(e), "path": str(target)})
                        return
                    selected = server._reload_agent_for_project(target)
                    if not selected.get("ok"):
                        self._json_response(409, selected)
                        return
                    result = server.maker_practice_runner.start(
                        project_dir=target,
                        skip_install=bool(data.get("skip_install", False)),
                        skip_init=bool(data.get("skip_init", False)),
                        app_selection=str(data.get("app_selection") or ("0" if not data.get("skip_init", False) else "")),
                    )
                    self._json_response(202 if result.get("ok") else 409, {
                        **result,
                        "setup_status": server.maker_setup_status(check_latest=False),
                    })
                    return

                if path == "/maker/practice/input":
                    result = server.maker_practice_runner.send_input(str(data.get("input") or ""))
                    self._json_response(200 if result.get("ok") else 409, result)
                    return

                if path == "/maker/practice/cancel":
                    self._json_response(200, server.maker_practice_runner.cancel())
                    return

                if path == "/maker/auth/prepare":
                    flow = prepare_auth_flow(str(data.get("auth_url") or ""))
                    server.pending_maker_auth = flow
                    self._json_response(200, flow)
                    return

                if path == "/maker/auth/complete":
                    result = complete_auth_flow()
                    if result.get("ok"):
                        server.pending_maker_auth = {}
                    self._json_response(200 if result.get("ok") else 409, result)
                    return

                if path.startswith("/sessions/") and path.endswith("/run"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        session = server.get_session(sid)
                        if not session:
                            self.send_error(404, "Session not found")
                            return
                        thread = threading.Thread(
                            target=server.run_session,
                            args=(sid,),
                            daemon=True,
                        )
                        thread.start()
                        self._json_response(202, {"session_id": sid, "status": "started"})
                        return

                if path.startswith("/sessions/") and path.endswith("/approve"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        action_id = data.get("action_id", "")
                        allowed = bool(data.get("allowed", False))
                        ok = server._approval_bridge.respond(sid, action_id, allowed)
                        if not ok:
                            self._json_response(410, {"error": "No pending approval request", "action_id": action_id})
                            return
                        self._json_response(200, {"action_id": action_id, "allowed": allowed})
                        return

                if path.startswith("/sessions/") and path.endswith("/cancel"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        result = server.cancel_session(sid)
                        status = int(result.pop("status", 200))
                        self._json_response(status, result)
                        return

                if path == "/fs/write":
                    fs_path = data.get("path", "")
                    content = data.get("content", "")
                    result, status = server.ide_service.write_file(fs_path, content)
                    self._json_response(status, result)
                    return

                if path == "/fs/delete":
                    fs_path = data.get("path", "")
                    result, status = server.ide_service.delete_file(fs_path)
                    self._json_response(status, result)
                    return

                if path == "/browser/navigate":
                    url = data.get("url", "")
                    if not url:
                        self._json_response(400, {"ok": False, "error": "缺少 url 参数"})
                        return
                    server.browser_service.start()
                    result = server.browser_service.navigate(url)
                    self._json_response(200 if result.get("ok") else 500, result)
                    return

                if path == "/browser/refresh":
                    server.browser_service.start()
                    result = server.browser_service.refresh()
                    self._json_response(200 if result.get("ok") else 500, result)
                    return

                if path == "/browser/evaluate":
                    script = data.get("script", "")
                    if not script:
                        self._json_response(400, {"ok": False, "error": "缺少 script 参数"})
                        return
                    server.browser_service.start()
                    result = server.browser_service.evaluate(script)
                    self._json_response(200 if result.get("ok") else 500, result)
                    return

                if path == "/browser/click":
                    selector = data.get("selector", "")
                    if not selector:
                        self._json_response(400, {"ok": False, "error": "缺少 selector 参数"})
                        return
                    server.browser_service.start()
                    result = server.browser_service.click(selector)
                    self._json_response(200 if result.get("ok") else 500, result)
                    return

                if path == "/browser/click_at":
                    try:
                        x = float(data.get("x"))
                        y = float(data.get("y"))
                    except (TypeError, ValueError):
                        self._json_response(400, {"ok": False, "error": "缺少 x/y 参数"})
                        return
                    server.browser_service.start()
                    result = server.browser_service.click_at(x, y)
                    self._json_response(200 if result.get("ok") else 500, result)
                    return

                self.send_error(404, "Not found")

        return Handler

    def start(self) -> None:
        if HTTPServer is None:
            raise RuntimeError("当前 Python 环境不支持 http.server")

        class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
            daemon_threads = True
            allow_reuse_address = True

        handler = self.make_handler()
        self._httpd = ThreadedHTTPServer((self.host, self.port), handler)
        print(f"[AppServer] 启动于 http://{self.host}:{self.port}")
        self._httpd.serve_forever()

    def stop(self) -> None:
        self.browser_service.stop()
        if hasattr(self, "_httpd"):
            self._httpd.shutdown()


def create_default_app_server(
    config_path: Optional[str] = None,
    provider: Optional[str] = None,
    port: Optional[int] = None,
) -> AppServer:
    """使用默认配置创建 App Server。"""
    cfg = Config(config_path) if config_path else Config()
    if cfg.base_dir.resolve() == APP_ROOT.resolve():
        apply_portable_env(cfg.base_dir, force=True)
    try:
        config_sync = ensure_internal_maker_mcp_latest_config(cfg, cfg.project_root())
        if config_sync.get("changed"):
            cfg.save()
    except Exception:
        pass
    if provider:
        cfg.data["llm"]["provider"] = provider
    active_provider = cfg.llm_provider() or "deepseek"
    try:
        llm = LLMFactory.create(active_provider, cfg)
    except Exception as e:
        llm = UnconfiguredLLM(str(e))

    bridge = ApprovalBridge()
    agent = TapMakerAgent(
        llm=llm,
        config=cfg,
        human_confirm_callback=None,
    )
    server = AppServer(agent, approval_bridge=bridge)
    if port is not None:
        server.port = port
    return server


if __name__ == "__main__":
    import sys
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    provider = sys.argv[2] if len(sys.argv) > 2 else None
    server = create_default_app_server(config_path, provider)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
