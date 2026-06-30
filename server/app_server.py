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
from core.intent_classifier import classify_cos_gate
from core.portable_env import apply_portable_env
from core.runtime_events import RuntimeEventBus
from ecosystem.skill_sync import SkillSyncRegistry
from llm.llm_factory import LLMFactory
from llm.provider_presets import OPENAI_COMPATIBLE_ALIASES, PROVIDER_PRESETS, model_hints, provider_preset
from llm.unconfigured_llm import UnconfiguredLLM
from server.agent_bootstrap_api import AgentBootstrapApi
from server.approval_bridge import ApprovalBridge
from server.browser_service import BrowserService
from server.ide_service import IdeService
from server.rag_evidence_service import RagEvidenceService
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
from server.learning_observer import LearningStateObserver
from server.memory_observer import MemoryRecallObserver
from server.project_observer import ProjectManagementObserver
from server.protocol import ApprovalResponse, SessionRequest, TurnEvent
from server.runtime_observer import RuntimeMetricsObserver
from server.session_api import SessionRouteApi, parse_step_limit
from server.session_store import SessionStore
from server.maker_faults import build_maker_fault_analysis
from server.evidence_bundle import (
    build_llm_feedback_summary,
    build_portable_runtime_status,
    build_runtime_readiness,
    render_session_evidence_markdown,
)


APP_ROOT = Path(__file__).resolve().parent.parent

class Session:
    """单个任务会话，支持 SQLite 历史事件回放。"""

    def __init__(
        self,
        session_id: str,
        task: str,
        store: Optional[SessionStore] = None,
        event_bus: Optional[RuntimeEventBus] = None,
    ):
        self.session_id = session_id
        self.task = task
        self.result: Optional[Dict[str, Any]] = None
        self.done = False
        self.cancelled = False
        self.error: Optional[str] = None
        self.pending_action_id: Optional[str] = None
        self.active_agent: Optional[TapMakerAgent] = None
        self._event_queue: queue.Queue[Dict[str, Any]] = queue.Queue()
        self._store = store
        self.event_bus = event_bus or RuntimeEventBus()
        self._history: List[Dict[str, Any]] = []
        self._history_consumed = 0
        if store is not None:
            self._history = store.get_events(session_id)

    def emit(self, event: Dict[str, Any]) -> None:
        event = self.event_bus.publish(
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
        self._session_threads: Dict[str, threading.Thread] = {}
        self.event_bus = RuntimeEventBus()
        self.runtime_metrics_observer = RuntimeMetricsObserver(self.event_bus)
        self.project_observer = ProjectManagementObserver(self.event_bus)
        self.learning_observer = LearningStateObserver(self.event_bus)
        self.memory_observer = MemoryRecallObserver(self.event_bus)
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
        self.rag_evidence_service = RagEvidenceService(lambda: self.agent.config)
        self.agent.executor.set_browser_service(self.browser_service)

    def maker_tool_audit(self) -> Dict[str, Any]:
        return build_maker_tool_audit(agent=self.agent)

    def rag_benchmark_status(self) -> Dict[str, Any]:
        return self.rag_evidence_service.benchmark_status()

    def rag_benchmark_report(self, *, force: bool = False) -> Dict[str, Any]:
        return self.rag_evidence_service.benchmark_report(force=force)

    def rag_quality_status(self) -> Dict[str, Any]:
        return self.rag_evidence_service.quality_status()

    def rag_quality_report(self, *, force: bool = False) -> Dict[str, Any]:
        return self.rag_evidence_service.quality_report(force=force)

    def rag_graph_status(self) -> Dict[str, Any]:
        """Phase B: graph-on vs graph-off evidence payload.

        Returns the ``not_enabled`` boundary payload when
        ``memory.graph.enabled=false``. This keeps callers from
        branching on the existence of the field.
        """
        return self.rag_evidence_service.graph_status()

    def rag_graph_report(self, *, force: bool = False) -> Dict[str, Any]:
        return self.rag_evidence_service.graph_report(force=force)

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
            self._sessions[sid] = Session(
                sid,
                req.task,
                store=self.session_store,
                event_bus=self.event_bus,
            )
            self._session_llm_overrides[sid] = {
                "provider": req.provider,
                "model": req.model,
                "base_url": req.base_url,
                "api_key": req.api_key,
            }
            self._sessions[sid].emit({
                "type": "cos_gate",
                "session_id": sid,
                "source": "cos_gate",
                "payload": {
                    **classify_cos_gate(req.task, trigger="user_input").to_dict(),
                    "session_id": sid,
                },
            })
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
            with self._lock:
                self._session_threads.pop(session_id, None)
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
        session.active_agent = session_agent
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
            learning_job = (
                session.result.get("learning_job")
                if isinstance(session.result, dict) and isinstance(session.result.get("learning_job"), dict)
                else {}
            )
            keep_agent_for_learning = bool(
                learning_job.get("async")
                and learning_job.get("status") in {"queued", "running"}
            )
            if keep_agent_for_learning:
                session.active_agent = session_agent
            else:
                session.active_agent = None
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
            with self._lock:
                self._session_threads.pop(session_id, None)

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

    def cancel_learning_job(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
            active_agent = getattr(session, "active_agent", None) if session is not None else None
        if active_agent is None or not hasattr(active_agent, "cancel_learning_job"):
            if not self.session_store.get_session(session_id):
                return {"ok": False, "status": 404, "error": "Session not found"}
            return {
                "ok": False,
                "status": 409,
                "session_id": session_id,
                "error": "No live learning queue is attached; durable replay cannot be cancelled.",
            }
        job = active_agent.cancel_learning_job(session_id)
        return {"ok": bool(job.get("cancelled")), "status": 200, "session_id": session_id, "job": job}

    def retry_learning_job(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
            active_agent = getattr(session, "active_agent", None) if session is not None else None
        if active_agent is None or not hasattr(active_agent, "retry_learning_job"):
            if not self.session_store.get_session(session_id):
                return {"ok": False, "status": 404, "error": "Session not found"}
            return {
                "ok": False,
                "status": 409,
                "session_id": session_id,
                "error": "No live learning queue is attached; durable replay cannot be retried.",
            }
        job = active_agent.retry_learning_job(session_id)
        return {"ok": bool(job.get("retried")), "status": 200, "session_id": session_id, "job": job}

    def get_session(self, session_id: str) -> Optional[Session]:
        with self._lock:
            return self._sessions.get(session_id)

    def make_handler(self):
        server = self
        session_api = SessionRouteApi(server)
        agent_bootstrap_api = AgentBootstrapApi(server)

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

                if path == "/memory/rag-benchmark":
                    params = parse_qs(parsed.query)
                    force = str((params.get("force") or ["false"])[0]).lower() in {"1", "true", "yes", "on"}
                    self._json_response(200, server.rag_benchmark_report(force=force))
                    return

                if path == "/memory/rag-quality":
                    params = parse_qs(parsed.query)
                    force = str((params.get("force") or ["false"])[0]).lower() in {"1", "true", "yes", "on"}
                    self._json_response(200, server.rag_quality_report(force=force))
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
                        payload = session_api.status_payload(parts[2])
                        if payload is None:
                            self.send_error(404, "Session not found")
                            return
                        self._json_response(200, payload)
                        return

                if (
                    path.startswith("/sessions/")
                    and (path.endswith("/commit-history") or path.endswith("/submissions"))
                ):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        if not session_api.exists(sid):
                            self.send_error(404, "Session not found")
                            return
                        params = parse_qs(parsed.query)
                        steps = parse_step_limit(params, default=100, maximum=500)
                        self._json_response(200, session_api.commit_history_payload(sid, steps=steps))
                        return

                if path.startswith("/sessions/") and path.endswith("/context-sync"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        if not session_api.exists(sid):
                            self.send_error(404, "Session not found")
                            return
                        params = parse_qs(parsed.query)
                        steps = parse_step_limit(params, default=100, maximum=500)
                        self._json_response(200, session_api.context_sync_payload(sid, steps=steps))
                        return

                if path.startswith("/sessions/") and path.endswith("/goal-loop"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        if not session_api.exists(sid):
                            self.send_error(404, "Session not found")
                            return
                        params = parse_qs(parsed.query)
                        steps = parse_step_limit(params, default=100, maximum=500)
                        self._json_response(200, session_api.goal_loop_payload(sid, steps=steps))
                        return

                if path.startswith("/sessions/") and path.endswith("/resume-drill"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        if not session_api.exists(sid):
                            self.send_error(404, "Session not found")
                            return
                        params = parse_qs(parsed.query)
                        steps = parse_step_limit(params, default=20, maximum=100)
                        self._json_response(200, session_api.resume_drill_payload(sid, steps=steps))
                        return

                if path.startswith("/sessions/") and path.endswith("/runtime-metrics"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        if not session_api.exists(sid):
                            self.send_error(404, "Session not found")
                            return
                        params = parse_qs(parsed.query)
                        steps = parse_step_limit(params, default=100, maximum=500)
                        self._json_response(200, session_api.runtime_metrics_payload(sid, steps=steps))
                        return

                if path.startswith("/sessions/") and path.endswith("/layer-health"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        if not session_api.exists(sid):
                            self.send_error(404, "Session not found")
                            return
                        params = parse_qs(parsed.query)
                        steps = parse_step_limit(params, default=20, maximum=100)
                        self._json_response(200, session_api.layer_health_payload(sid, steps=steps))
                        return

                if path.startswith("/sessions/") and path.endswith("/layer-control"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        if not session_api.exists(sid):
                            self.send_error(404, "Session not found")
                            return
                        params = parse_qs(parsed.query)
                        steps = parse_step_limit(params, default=20, maximum=100)
                        self._json_response(200, session_api.layer_control_payload(sid, steps=steps))
                        return

                if path.startswith("/sessions/") and path.endswith("/engineering-control"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        if not session_api.exists(sid):
                            self.send_error(404, "Session not found")
                            return
                        params = parse_qs(parsed.query)
                        steps = parse_step_limit(params, default=20, maximum=100)
                        self._json_response(200, session_api.engineering_control_payload(sid, steps=steps))
                        return

                if path.startswith("/sessions/") and path.endswith("/project-state"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        if not session_api.exists(sid):
                            self.send_error(404, "Session not found")
                            return
                        self._json_response(200, session_api.project_state_payload(sid))
                        return

                if path.startswith("/sessions/") and path.endswith("/project-writeback"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        if not session_api.exists(sid):
                            self.send_error(404, "Session not found")
                            return
                        self._json_response(200, session_api.project_writeback_plan(sid))
                        return

                if path.startswith("/sessions/") and path.endswith("/learning"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        if not session_api.exists(sid):
                            self.send_error(404, "Session not found")
                            return
                        params = parse_qs(parsed.query)
                        steps = parse_step_limit(params, default=100, maximum=500)
                        self._json_response(200, session_api.learning_payload(sid, steps=steps))
                        return

                if path.startswith("/sessions/") and path.endswith("/maker-guard"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        if not session_api.exists(sid):
                            self.send_error(404, "Session not found")
                            return
                        params = parse_qs(parsed.query)
                        steps = parse_step_limit(params, default=100, maximum=500)
                        self._json_response(200, session_api.maker_guard_payload(sid, steps=steps))
                        return

                if path.startswith("/sessions/") and path.endswith("/llm-probe"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        if not session_api.exists(sid):
                            self.send_error(404, "Session not found")
                            return
                        params = parse_qs(parsed.query)
                        steps = parse_step_limit(params, default=100, maximum=500)
                        self._json_response(200, session_api.llm_probe_payload(sid, steps=steps))
                        return

                if path.startswith("/sessions/") and (path.endswith("/evidence") or path.endswith("/evidence.md")):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        if not session_api.exists(sid):
                            self.send_error(404, "Session not found")
                            return
                        params = parse_qs(parsed.query)
                        steps = parse_step_limit(params, default=20, maximum=100)
                        bundle = session_api.evidence_bundle(sid, steps=steps)
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
                        if not session_api.exists(sid):
                            self.send_error(404, "Session not found")
                            return
                        params = parse_qs(parsed.query)
                        steps = parse_step_limit(params, default=20, maximum=500)
                        self._json_response(200, session_api.runtime_advice_payload(sid, steps=steps))
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
                    steps = parse_step_limit(params, default=20, maximum=100)
                    surface = (params.get("surface") or ["generic"])[0]
                    if not agent_bootstrap_api.session_available(session_id):
                        self.send_error(404, "Session not found")
                        return
                    bundle = agent_bootstrap_api.onboarding_bundle(session_id, steps=steps, surface=surface)
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
                    if not agent_bootstrap_api.session_available(session_id):
                        self.send_error(404, "Session not found")
                        return
                    self._json_response(200, agent_bootstrap_api.maker_briefing_payload(session_id, task=task))
                    return

                if path == "/agent/handoff":
                    params = parse_qs(parsed.query)
                    session_id = (params.get("session_id") or ["{session_id}"])[0]
                    steps = parse_step_limit(params, default=3, maximum=20)
                    if not agent_bootstrap_api.session_available(session_id):
                        self.send_error(404, "Session not found")
                        return
                    self._json_response(200, agent_bootstrap_api.handoff_bundle(session_id, steps=steps))
                    return

                if path in {"/agent/quickstart", "/agent/quickstart.md"}:
                    params = parse_qs(parsed.query)
                    session_id = (params.get("session_id") or ["{session_id}"])[0]
                    steps = parse_step_limit(params, default=3, maximum=20)
                    surface = (params.get("surface") or ["generic"])[0]
                    if not agent_bootstrap_api.session_available(session_id):
                        self.send_error(404, "Session not found")
                        return
                    quickstart = agent_bootstrap_api.quickstart_bundle(session_id, steps=steps, surface=surface)
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
                    with server._lock:
                        server._session_threads[sid] = thread
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

                if path.startswith("/sessions/") and path.endswith("/project-writeback"):
                    parts = path.split("/")
                    if len(parts) >= 4:
                        sid = parts[2]
                        if not session_api.exists(sid):
                            self.send_error(404, "Session not found")
                            return
                        self._json_response(
                            200,
                            session_api.apply_project_writeback_payload(
                                sid,
                                apply=data.get("apply") is True,
                            ),
                        )
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
                        with server._lock:
                            server._session_threads[sid] = thread
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

                if path.startswith("/sessions/") and path.endswith("/goal-loop/confirm"):
                    parts = path.split("/")
                    if len(parts) >= 5:
                        sid = parts[2]
                        action_id = data.get("action_id", "")
                        allowed = bool(data.get("allowed", False))
                        ok = server._approval_bridge.respond(sid, action_id, allowed) if action_id else False
                        if not ok:
                            self._json_response(410, {"error": "No pending GoalLoop confirmation", "action_id": action_id})
                            return
                        self._json_response(200, {"action_id": action_id, "allowed": allowed, "goal_loop": True})
                        return

                if path.startswith("/sessions/") and path.endswith("/learning/cancel"):
                    parts = path.split("/")
                    if len(parts) >= 5:
                        sid = parts[2]
                        result = server.cancel_learning_job(sid)
                        status = int(result.pop("status", 200))
                        self._json_response(status, result)
                        return

                if path.startswith("/sessions/") and path.endswith("/learning/retry"):
                    parts = path.split("/")
                    if len(parts) >= 5:
                        sid = parts[2]
                        result = server.retry_learning_job(sid)
                        status = int(result.pop("status", 200))
                        self._json_response(status, result)
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
        with self._lock:
            live_sessions = [session for session in self._sessions.values() if not session.done]
            live_threads = list(self._session_threads.values())
        for session in live_sessions:
            session.cancel()
            if session.pending_action_id:
                self._approval_bridge.respond(session.session_id, session.pending_action_id, False)
        deadline = time.time() + 5.0
        for thread in live_threads:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            thread.join(timeout=min(remaining, 1.0))
        observer = getattr(self, "runtime_metrics_observer", None)
        if observer is not None:
            observer.close()
        project_observer = getattr(self, "project_observer", None)
        if project_observer is not None:
            project_observer.close()
        learning_observer = getattr(self, "learning_observer", None)
        if learning_observer is not None:
            learning_observer.close()
        memory_observer = getattr(self, "memory_observer", None)
        if memory_observer is not None:
            memory_observer.close()
        self.browser_service.stop()
        if hasattr(self, "_httpd"):
            self._httpd.shutdown()
            self._httpd.server_close()


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
        provider = provider.lower().strip()
        cfg.data.setdefault("llm", {})["provider"] = provider
        active_profile = cfg.active_profile()
        profile = cfg.data.setdefault("profiles", {}).get(active_profile)
        if isinstance(profile, dict) and isinstance(profile.get("llm"), dict):
            profile["llm"]["provider"] = provider
        cfg._profiles = cfg.data.get("profiles", {})
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
