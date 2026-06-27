"""
agent/agent.py — TapMaker Agent 顶层入口

组装三层：
- Agent 层：ReActLoop + ToolRegistry
- 核心运转层：HealthMonitor + Executor + RepairScheduler + VersionManager + EventLog
- 学习转化层：TrajectoryCollector + ReflectionEngine + SkillGenerator

对外提供 run(task) 接口。
"""

from __future__ import annotations
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.config import Config
from agent.builtin_tools import register_builtin_tools
from agent.mcp_integration import MCPIntegration
from agent.learning_queue import LearningJobQueue, LearningJobRequest
from agent.react_loop import ReActLoop
from agent.rescue_orchestrator import RescueOrchestrator
from agent.rescue_trigger import RescueTrigger
from agent.tool_registry import ToolRegistry

from core.event_log import EventLog, Event
from core.executor import Executor
from core.health import HealthMonitor
from core.repair import RepairScheduler
from core.version_manager import VersionManager
from core.sandbox import SandboxMode
from core.approval import ApprovalPolicy
from core.cancellation import TaskCancelled
from core.layer_events import make_layer_event
from core.runtime_events import RuntimeEventBus
from core.resource_registry import ResourceRegistry
from core.evolution_protocol import EvolutionProtocol
from core.runtime_contract import build_maker_briefing, build_runtime_contract
from ecosystem.skill_sync import SkillSyncRegistry

from learning.trajectory_collector import TrajectoryCollector
from learning.reflection import ReflectionEngine
from learning.skill_generator import SkillGenerator
from learning.knowledge_base import KnowledgeBase
from learning.knowledge_seeds import seed_knowledge_base
from learning.shared_memory_bridge import archive_learning_insights_to_shared_memory
from learning.validator import SkillValidator

from llm.expert_rescuer import ExpertRescuer
from learning.expert_distiller import ExpertDistiller
from llm.interface import LLMInterface
from memory.manager import MemoryManager
from llm.context_budget import ContextBudgetManager


class TapMakerAgent:
    """自进化 TapMaker 开发 Agent。"""

    def __init__(
        self,
        llm: LLMInterface,
        config: Optional[Config] = None,
        project_root: Optional[Path] = None,
        storage_root: Optional[Path] = None,
        human_confirm_callback: Optional[Any] = None,
        connect_mcp: bool = True,
        shared_mcp_integration: Optional[MCPIntegration] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ):
        self.config = config or Config()
        self.project_root = Path(project_root or self.config.project_root())
        self.storage_root = Path(storage_root or self.config.storage_root())
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.skill_sync_registry = SkillSyncRegistry(self.project_root, self.storage_root)

        self.llm = llm
        self.human_confirm_callback = human_confirm_callback
        self.cancel_check = cancel_check
        self.event_sink: Optional[Callable[[Dict[str, Any]], None]] = None
        self.event_bus = RuntimeEventBus()
        self._event_queues: Dict[str, List[Dict[str, Any]]] = {}

        # 记忆 / 上下文预算
        self.memory_manager = MemoryManager(
            project_root=self.project_root,
            storage_root=self.storage_root,
            skills_dir=self.project_root / "skills",
            llm=self.llm,
            budget_manager=ContextBudgetManager(
                n_ctx=self.config.get("llm.n_ctx", 8192),
                reserve_tokens=self.config.get("llm.reserve_tokens", 256),
            ),
            config=self.config,
        )

        # 持久化
        self.event_log = EventLog(self.storage_root / "log" / "events.jsonl")
        self.version_manager = VersionManager(
            project_root=self.project_root,
            storage_path=self.storage_root / "versions",
        )
        self.resource_registry = ResourceRegistry(self.storage_root / "resources")
        self.evolution_protocol = EvolutionProtocol(
            registry=self.resource_registry,
            event_log=self.event_log,
            storage_path=self.storage_root / "evolution",
            human_confirm_callback=human_confirm_callback,
        )

        # 核心运转层
        self.health = HealthMonitor(self.storage_root / "health")
        self.executor = Executor(
            project_root=self.project_root,
            event_log=self.event_log,
            version_manager=self.version_manager,
            human_confirm_callback=human_confirm_callback,
            sandbox_mode=SandboxMode(self.config.sandbox_mode()),
            approval_policy=ApprovalPolicy(self.config.approval_policy()),
            tool_timeout_seconds=self.config.runtime_tool_timeout_seconds(),
            shell_timeout_seconds=self.config.runtime_shell_timeout_seconds(),
        )
        self.repair = RepairScheduler(
            health=self.health,
            version_manager=self.version_manager,
            event_log=self.event_log,
            max_attempts=self.config.get("runtime.max_repair_attempts", 3),
            on_repair_success=self._on_repair_success,
        )

        # Agent 层
        self.tools = ToolRegistry(self.project_root / "skills")
        self.mcp_integration: Optional[MCPIntegration] = None
        self._owns_mcp_integration = False
        if shared_mcp_integration is not None:
            self.mcp_integration = shared_mcp_integration
            shared_mcp_integration.attach(self.tools, self.executor)
        elif connect_mcp:
            self.mcp_integration = MCPIntegration(
                config=self.config,
                tools=self.tools,
                executor=self.executor,
                event_log=self.event_log,
            )
            self._owns_mcp_integration = True
        self.react = ReActLoop(
            llm=self.llm,
            tools=self.tools,
            executor=self.executor,
            event_log=self.event_log,
            max_iterations=20,
            event_sink=self._on_react_event,
            memory_manager=self.memory_manager,
            cancel_check=cancel_check,
            skill_sync_status=self.skill_sync_registry.status,
            runtime_contract_provider=self.runtime_contract,
            plan_first_enabled=self.config.get("agent.plan_first_enabled", False),
            plan_approval_provider=self._plan_approval_provider,
        )

        # 学习转化层
        self.trajectory_collector = TrajectoryCollector(
            storage_path=self.storage_root / "trajectories"
        )
        self.knowledge_base = KnowledgeBase(
            storage_path=self.storage_root / "knowledge",
            vector_index_config=self.config.vector_index_config(),
        )
        self.knowledge_seed_status = seed_knowledge_base(self.knowledge_base)
        self.reflection = ReflectionEngine(
            llm=self.llm,
            knowledge_base=self.knowledge_base,
        )
        self.skill_generator = SkillGenerator(
            llm=self.llm,
            skills_dir=self.project_root / "skills",
            validator=SkillValidator(),
            registry=self.resource_registry,
            skill_sync_registry=self.skill_sync_registry,
        )
        self.learning_jobs = LearningJobQueue(
            processor=self._process_learning_job,
            on_transition=self._on_learning_job_transition,
            max_attempts=int(self.config.get("learning.max_attempts", 1) or 1),
            retry_delay_seconds=float(self.config.get("learning.retry_delay_seconds", 0.0) or 0.0),
            worker_idle_timeout_seconds=float(
                self.config.get("learning.worker_idle_timeout_seconds", 5.0) or 5.0
            ),
        )
        # 专家救援与教学闭环（可选）
        self.expert_rescuer: Optional[ExpertRescuer] = None
        self.rescue_orchestrator: Optional[RescueOrchestrator] = None
        self.expert_distiller: Optional[ExpertDistiller] = None
        if self.config.get("expert.enabled", False):
            expert_key = self.config.get("expert.api_key", "")
            skip_if_no_key = self.config.get("rescue.skip_if_no_expert_key", True)
            if skip_if_no_key and (not expert_key or expert_key.strip() == "sk-..." or expert_key.strip().lower().startswith("sk-...")):
                self.event_log.append(Event.create(
                    "expert_rescuer_init_skipped",
                    session_id="init",
                    source="runtime",
                    payload={"reason": "expert.api_key missing or placeholder"},
                ))
            else:
                try:
                    self.expert_rescuer = ExpertRescuer(self.config)
                    self.expert_distiller = ExpertDistiller(
                        reflection=self.reflection,
                        skill_generator=self.skill_generator,
                        knowledge_base=self.knowledge_base,
                        config=self.config,
                    )
                    self.rescue_orchestrator = RescueOrchestrator(
                        react_loop=self.react,
                        expert_rescuer=self.expert_rescuer,
                        trigger=RescueTrigger(self.config),
                        distiller=self.expert_distiller,
                        health=self.health,
                        config=self.config,
                    )
                except Exception as e:
                    self.event_log.append(Event.create(
                        "expert_rescuer_init_failed",
                        session_id="init",
                        source="runtime",
                        payload={"error": str(e)},
                    ))

        # 注册基础内置工具
        register_builtin_tools(self.tools, self.executor)
        self._register_runtime_contract_tool()
        self._register_maker_briefing_tool()
        self._register_query_skills_tool()

        # 从 AGENTS.md 注册动态工具
        if self.config.get("agents_md.dynamic_tools_enabled", True):
            for spec in self.memory_manager.agents_md_index.list_tools():
                self._register_agents_md_tool(spec)

        self._sync_generated_tools_to_executor()

    def runtime_contract(self, session_id: str = "{session_id}") -> Dict[str, Any]:
        mcp_status: Dict[str, Any]
        if self.mcp_integration is not None:
            try:
                mcp_status = self.mcp_integration.status()
            except Exception as e:
                mcp_status = {
                    "connected": False,
                    "tool_count": 0,
                    "tools": [],
                    "last_error": str(e),
                }
        else:
            mcp_status = {
                "connected": False,
                "tool_count": 0,
                "tools": [],
                "last_error": "Maker MCP integration is not configured",
            }
        try:
            skill_status = self.skill_sync_registry.status()
        except Exception as e:
            skill_status = {"registry": {"state": "error", "error": str(e)}}
        return build_runtime_contract(
            project_root=self.project_root,
            mcp_status=mcp_status,
            skill_status=skill_status,
            session_id=session_id,
        )

    def _register_runtime_contract_tool(self) -> None:
        self.executor.register_dynamic_tool("runtime_contract", self._runtime_contract_tool, risk_level="low")
        self.tools.register(
            name="runtime_contract",
            description="Return the compact TTMEvolve + MakerMCP runtime contract for fast LLM onboarding.",
            parameters={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Optional session id for context endpoints."},
                },
            },
            handler=self.executor.propose_action,
            source="runtime",
        )

    def _runtime_contract_tool(self, session_id: str = "{session_id}", **kwargs: Any) -> Dict[str, Any]:
        return {
            "ok": True,
            "tool": "runtime_contract",
            "contract": self.runtime_contract(session_id=session_id or "{session_id}"),
        }

    def _plan_approval_provider(self, plan: Dict[str, Any]) -> bool:
        """Default plan approval provider.

        When plan_first_enabled is on but no human-in-the-loop provider is wired
        in (no session_store, no approval callback), fall back to auto-approving
        plans that pass the deterministic review. Real human approval is provided
        by the server-side handler via the runtime plan_approval callable.
        """
        try:
            provider = getattr(self, "_plan_approval_callable", None)
            if callable(provider):
                return bool(provider(plan))
        except Exception:
            pass
        return True

    def set_plan_approval_callable(self, provider: Optional[Callable[[Dict[str, Any]], bool]]) -> None:
        """Install a human-in-the-loop plan approval callable (server sets this)."""
        self._plan_approval_callable = provider

    def maker_briefing(self, session_id: str = "{session_id}", task: str = "") -> Dict[str, Any]:
        contract = self.runtime_contract(session_id=session_id or "{session_id}")
        return build_maker_briefing(contract, task=task)

    def _register_maker_briefing_tool(self) -> None:
        self.executor.register_dynamic_tool("maker_briefing", self._maker_briefing_tool, risk_level="low")
        self.tools.register(
            name="maker_briefing",
            description="Return the compact first-action briefing for MakerMCP coding tasks.",
            parameters={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Optional session id for context endpoints."},
                    "task": {"type": "string", "description": "Current user task used to select the Maker workflow template."},
                },
            },
            handler=self.executor.propose_action,
            source="runtime",
        )

    def _maker_briefing_tool(
        self,
        session_id: str = "{session_id}",
        task: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return {
            "ok": True,
            "tool": "maker_briefing",
            "briefing": self.maker_briefing(session_id=session_id or "{session_id}", task=task),
        }

    def _register_query_skills_tool(self) -> None:
        self.executor.register_dynamic_tool("query_skills", self._query_skills, risk_level="low")
        self.tools.register(
            name="query_skills",
            description="Query the shared skill registry/graph by capability, ecosystem, or callability.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Optional text to match skill id, name, or description."},
                    "ecosystem": {"type": "string", "description": "Optional provider ecosystem such as canonical, codex, claude_code, hermes, openclaw."},
                    "callability": {"type": "string", "enum": ["available", "blocked_by_conflict"]},
                    "limit": {"type": "integer", "minimum": 1},
                },
            },
            handler=self.executor.propose_action,
            source="skill_sync",
        )

    def _query_skills(
        self,
        query: str = "",
        ecosystem: str = "",
        callability: str = "",
        limit: int = 20,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        status = self.skill_sync_registry.status()
        graph = status.get("skill_graph", {})
        nodes = graph.get("nodes", [])
        needle = str(query or "").strip().lower()
        ecosystem = str(ecosystem or "").strip()
        callability = str(callability or "").strip()
        try:
            limit = max(1, min(int(limit or 20), 100))
        except (TypeError, ValueError):
            limit = 20

        matches: List[Dict[str, Any]] = []
        for node in nodes:
            providers = node.get("providers", [])
            if ecosystem and not any(provider.get("ecosystem") == ecosystem for provider in providers):
                continue
            if callability and node.get("callability") != callability:
                continue
            haystack = " ".join([
                str(node.get("skill_id", "")),
                str(node.get("name", "")),
                str(node.get("description", "")),
                " ".join(str(tag) for tag in node.get("preconditions", {}).get("tags", [])),
            ]).lower()
            if needle and needle not in haystack:
                continue
            matches.append({
                "skill_id": node.get("skill_id"),
                "name": node.get("name"),
                "description": node.get("description"),
                "versions": node.get("versions", []),
                "providers": providers,
                "input_schema": node.get("input_schema", {}),
                "output_schema": node.get("output_schema", {}),
                "callability": node.get("callability"),
                "conflicts": node.get("conflicts", []),
                "pending_export_actions": node.get("pending_export_actions", []),
            })
            if len(matches) >= limit:
                break

        return {
            "ok": True,
            "tool": "query_skills",
            "query": query,
            "ecosystem": ecosystem,
            "callability": callability,
            "count": len(matches),
            "skills": matches,
            "registry": status.get("registry", {}),
            "graph_summary": graph.get("summary", {}),
        }

    def set_llm(self, llm: LLMInterface) -> None:
        """Swap the active LLM for the next session.

        GUI provider switching must update every component that holds a direct
        LLM reference; changing only ``self.llm`` leaves the ReAct loop on the
        old provider.
        """
        self.llm = llm
        self.react.llm = llm
        self.memory_manager.llm = llm
        self.reflection.llm = llm
        self.skill_generator.llm = llm

    def _sync_generated_tools_to_executor(self) -> None:
        """把 ToolRegistry 中已加载的自生成技能同步注册到 Executor。"""
        for tool in self.tools.generated_tools():
            name = tool["name"]
            handler = tool["handler"]
            if name not in self.executor._dynamic_tools:
                self.executor.register_dynamic_tool(name, handler)

    def _register_agents_md_tool(self, spec: Dict[str, Any]) -> None:
        """注册从 AGENTS.md 解析出的单个动态工具。"""
        name = spec.get("name")
        if not name or self.tools.has(name):
            return
        handler = self._build_agents_md_handler(spec)
        if handler is None:
            return
        risk_level = spec.get("risk_level", "medium")
        self.tools.register_agents_md_tool(
            name=name,
            description=spec.get("description", ""),
            parameters=spec.get("parameters", {"type": "object", "properties": {}}),
            handler=handler,
            risk_level=risk_level,
        )
        self.executor.register_dynamic_tool(name, handler, risk_level=risk_level)

    def _build_agents_md_handler(self, spec: Dict[str, Any]):
        """根据 AGENTS.md 中的 handler 配置生成工具执行函数。"""
        handler_cfg = spec.get("handler", {})
        htype = handler_cfg.get("type")

        if htype == "shell":
            command_template = handler_cfg.get("command", "")
            def shell_handler(**kwargs):
                session_id = kwargs.pop("_session_id", "unknown")
                try:
                    command = command_template.format(**kwargs)
                except KeyError as e:
                    return {"ok": False, "error": f"missing parameter: {e}"}
                return self.executor.propose_action(
                    session_id=session_id,
                    tool_name="execute_shell",
                    params={"command": command},
                )
            return shell_handler

        if htype == "builtin":
            builtin_name = handler_cfg.get("builtin", "")
            if builtin_name not in self.executor.ALLOWED_LOCAL_TOOLS:
                return None
            def builtin_handler(**kwargs):
                session_id = kwargs.pop("_session_id", "unknown")
                return self.executor.propose_action(
                    session_id=session_id,
                    tool_name=builtin_name,
                    params=kwargs,
                )
            return builtin_handler

        if htype == "python":
            if not self.config.get("agents_md.allow_python_handlers", False):
                return None
            code = handler_cfg.get("code", "")
            if not code:
                return None
            local_ns: Dict[str, Any] = {}
            try:
                exec(compile(code, f"<agents_md:{spec.get('name')}>", "exec"), local_ns)
            except Exception as e:
                return lambda **kwargs: {"ok": False, "error": f"python handler compile failed: {e}"}
            run_fn = local_ns.get("run")
            if not callable(run_fn):
                return lambda **kwargs: {"ok": False, "error": "python handler has no run()"}
            return run_fn

        # 未知 handler 类型：返回一个占位函数，避免注册失败导致整个启动崩溃
        return lambda **kwargs: {"ok": False, "error": f"unsupported agents_md handler type: {htype}"}

    def _on_react_event(self, event: Dict[str, Any]) -> None:
        """把 ReActLoop 事件写入 session 事件队列，供 App Server 消费。"""
        sid = event.get("session_id")
        if not sid:
            return
        self._record_event(sid, event, notify_sink=False)

    def _record_event(
        self,
        session_id: str,
        event: Dict[str, Any],
        *,
        sink: Optional[Callable[[Dict[str, Any]], None]] = None,
        notify_sink: bool = True,
    ) -> Dict[str, Any]:
        recorded = self.event_bus.publish(
            event,
            default_source=str(event.get("source") or "agent"),
            correlation_id=session_id,
        )
        q = self._event_queues.get(session_id)
        if q is not None:
            q.append(recorded)
        target_sink = sink or self.event_sink
        if notify_sink and callable(target_sink):
            try:
                target_sink(recorded)
            except Exception:
                pass
        return recorded

    def _emit_layer_event(
        self,
        session_id: str,
        layer: str,
        state: str,
        detail: str = "",
        *,
        event: str = "layer.transition",
        source_layer: str = "runtime",
        target_layer: Optional[str] = None,
        correlation_id: str = "",
        cause: str = "",
        metrics: Optional[Dict[str, Any]] = None,
        sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        event_payload = make_layer_event(
            session_id=session_id,
            layer=layer,
            state=state,
            event=event,
            detail=detail,
            source_layer=source_layer,
            target_layer=target_layer,
            correlation_id=correlation_id,
            cause=cause,
            metrics=metrics,
        ).to_turn_event()
        self._record_event(session_id, event_payload, sink=sink)

    def run(self, task: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """执行一个开发任务。"""
        sid = session_id or self._new_session_id()
        self._event_queues[sid] = []

        try:
            result = self._run_internal(task, sid)
        finally:
            # 保留最近 100 个 session 的队列
            if len(self._event_queues) > 100:
                oldest = next(iter(self._event_queues))
                del self._event_queues[oldest]

        return result

    def get_events(self, session_id: str) -> List[Dict[str, Any]]:
        """获取某个 session 的当前事件队列副本。"""
        return list(self._event_queues.get(session_id, []))

    def get_learning_job(self, session_id: str) -> Dict[str, Any]:
        return self.learning_jobs.get(session_id)

    def list_learning_jobs(self) -> List[Dict[str, Any]]:
        return self.learning_jobs.list_jobs()

    def learning_queue_summary(self) -> Dict[str, Any]:
        return self.learning_jobs.summary()

    def cancel_learning_job(self, session_id: str) -> Dict[str, Any]:
        return self.learning_jobs.cancel(session_id)

    def retry_learning_job(self, session_id: str) -> Dict[str, Any]:
        return self.learning_jobs.retry(session_id)

    def _run_internal(self, task: str, sid: str) -> Dict[str, Any]:
        run_started_at = time.time()
        layer_correlation_id = sid
        self._check_cancelled()
        # 前馈：预加载相关记忆/规则到 LLM 上下文
        warm_context = self._load_warm_context(task)

        # 记录任务开始
        self.event_log.append(Event.create(
            "task_started",
            session_id=sid,
            source="agent",
            payload={"task": task, "warm_context": warm_context},
        ))

        # 执行 ReAct 循环（有专家救援编排器时自动启用救援）
        self._emit_layer_event(
            sid,
            "agent",
            "active",
            "理解目标并规划下一步",
            event="agent.run.started",
            source_layer="user",
            target_layer="agent",
            correlation_id=layer_correlation_id,
            cause="user_task",
            metrics={"task_chars": len(task), "warm_context_chars": len(warm_context)},
        )
        if self.rescue_orchestrator:
            result = self.rescue_orchestrator.run(task, session_id=sid)
        else:
            result = self.react.run(task, session_id=sid)
        self._check_cancelled()
        self._emit_layer_event(
            sid,
            "agent",
            "done",
            "推理循环完成，轨迹交给运行层审计",
            event="agent.run.finished",
            source_layer="agent",
            target_layer="runtime",
            correlation_id=layer_correlation_id,
            cause="react_loop_completed",
            metrics={
                "iteration_count": result.get("iteration_count", 0),
                "trajectory_steps": len(result.get("trajectory", [])),
                "elapsed_ms": (time.time() - run_started_at) * 1000,
            },
        )

        # 收集轨迹
        self._check_cancelled()
        self._emit_layer_event(
            sid,
            "runtime",
            "active",
            "收集轨迹、更新健康度并检查修复",
            event="runtime.audit.started",
            source_layer="agent",
            target_layer="runtime",
            correlation_id=layer_correlation_id,
            cause="agent_trajectory_ready",
            metrics={"trajectory_steps": len(result.get("trajectory", []))},
        )
        self.trajectory_collector.append(sid, result["trajectory"])

        # 更新健康状态（注入真实上下文预算指标）
        last_budget_stats = self._extract_budget_stats(result.get("trajectory", []))
        health_state = self.health.heartbeat({
            "pid": 0,
            "last_progress_event": time.time(),
            "iteration_count": result["iteration_count"],
            "error_count": sum(1 for s in result["trajectory"] if not s.get("observation", {}).get("ok", True)),
            "progress_metric": 1.0 if result["output"] else 0.0,
            "token_usage_ratio": last_budget_stats.get("token_usage_ratio", 0.0),
            "context_window_ratio": last_budget_stats.get("context_window_ratio", 0.0),
        })

        # 核心运转层检查修复
        self._check_cancelled()
        repair_status = self.repair.check_and_repair(sid)
        self._emit_layer_event(
            sid,
            "runtime",
            "done" if health_state.status == "healthy" else "error",
            "运行层检查完成",
            event="runtime.audit.finished",
            source_layer="runtime",
            target_layer="learning",
            correlation_id=layer_correlation_id,
            cause="health_and_repair_checked",
            metrics={
                "health_status": health_state.status,
                "repair_status": repair_status or "none",
                "error_count": health_state.error_count,
                "token_usage_ratio": health_state.token_usage_ratio,
                "context_window_ratio": health_state.context_window_ratio,
                "context_saturation": health_state.context_saturation,
                "compression_applied": last_budget_stats.get("compression_applied", False),
                "dropped_parts": last_budget_stats.get("dropped_parts", 0),
                "truncated_chars": last_budget_stats.get("truncated_chars", 0),
                "token_cache_hits": last_budget_stats.get("token_cache_hits", 0),
                "token_cache_misses": last_budget_stats.get("token_cache_misses", 0),
                "token_cache_size": last_budget_stats.get("token_cache_size", 0),
                "agents_md_hits": last_budget_stats.get("agents_md_hits", 0),
                "cold_recall_hits": last_budget_stats.get("cold_recall_hits", 0),
                "agents_md_ms": last_budget_stats.get("agents_md_ms", 0),
                "cold_recall_ms": last_budget_stats.get("cold_recall_ms", 0),
                "context_build_ms": last_budget_stats.get("context_build_ms", 0),
            },
        )

        learning_job = self._dispatch_learning_job(
            sid,
            task,
            result,
            correlation_id=layer_correlation_id,
        )

        result["repair_status"] = repair_status
        result["learning_job"] = learning_job
        return result

    def _check_cancelled(self) -> None:
        if self.cancel_check and self.cancel_check():
            raise TaskCancelled()

    def _dispatch_learning_job(
        self,
        session_id: str,
        task: str,
        result: Dict[str, Any],
        *,
        correlation_id: str,
    ) -> Dict[str, Any]:
        eligible = int(result.get("iteration_count") or 0) >= 2
        async_enabled = bool(self.config.get("learning.async_enabled", True))
        return self.learning_jobs.submit(
            LearningJobRequest(
                session_id=session_id,
                task=task,
                result=result,
                correlation_id=correlation_id,
                sink=self.event_sink,
            ),
            eligible=eligible,
            async_enabled=async_enabled,
        )
    def _process_learning_job(self, session_id: str, task: str, result: Dict[str, Any]) -> Dict[str, Any]:
        learning_summary = self._learn_from_session(session_id, task, result)
        if learning_summary.get("error"):
            raise RuntimeError(str(learning_summary.get("error")))
        return learning_summary

    def _on_learning_job_transition(self, transition: str, session_id: str, job: Dict[str, Any]) -> None:
        event_map = {
            "queued": ("learning.reflection.queued", "active", "runtime", "learning", "runtime_audit_finished"),
            "skipped": ("learning.reflection.skipped", "done", "runtime", "learning", "runtime_audit_finished"),
            "started": ("learning.reflection.started", "active", "runtime", "learning", "learning_job_started"),
            "retry_queued": ("learning.reflection.retry_queued", "active", "learning", "learning", "learning_job_retry"),
            "cancel_requested": (
                "learning.reflection.cancel_requested",
                "active",
                "runtime",
                "learning",
                "learning_job_cancel_requested",
            ),
            "cancelled": ("learning.reflection.cancelled", "done", "learning", "storage", "learning_job_cancelled"),
            "finished": ("learning.reflection.finished", "done", "learning", "storage", "reflection_pipeline_completed"),
            "failed": ("learning.reflection.failed", "error", "learning", "storage", "reflection_pipeline_failed"),
        }
        event_name, state, source_layer, target_layer, cause = event_map.get(
            transition,
            ("learning.reflection.status", "active", "learning", "learning", "learning_job_status"),
        )
        summary = job.get("summary") if isinstance(job.get("summary"), dict) else {}
        shared_memory = job.get("shared_memory") if isinstance(job.get("shared_memory"), dict) else {}
        shared_counts = shared_memory.get("counts") if isinstance(shared_memory.get("counts"), dict) else {}
        metrics = {
            "eligible": job.get("eligible"),
            "async": job.get("async"),
            "attempts": job.get("attempts", 0),
            "max_attempts": job.get("max_attempts"),
            "retryable": job.get("retryable"),
            "cancel_requested": job.get("cancel_requested"),
            "elapsed_ms": job.get("elapsed_ms", 0),
            "error": job.get("error", ""),
            "insight_count": job.get("insight_count", summary.get("insight_count", 0)),
            "shared_memory_archived": shared_counts.get("archived", 0),
            "shared_memory_promoted": shared_counts.get("promoted", 0),
            "shared_memory_conflicts": shared_counts.get("conflicts", 0),
        }
        self._emit_layer_event(
            session_id,
            "learning",
            state,
            self._learning_transition_detail(transition),
            event=event_name,
            source_layer=source_layer,
            target_layer=target_layer,
            correlation_id=str(job.get("correlation_id") or session_id),
            cause=cause,
            metrics=metrics,
            sink=job.get("sink"),
        )

    def _learning_transition_detail(self, transition: str) -> str:
        return {
            "queued": "Learning job queued.",
            "skipped": "Learning skipped because the trajectory is too short.",
            "started": "Learning job started.",
            "retry_queued": "Learning job retry queued after a failed attempt.",
            "cancel_requested": "Learning cancellation requested; running work stops at the next boundary.",
            "cancelled": "Learning job cancelled.",
            "finished": "Learning job finished; knowledge is available on demand.",
            "failed": "Learning job failed; user task result is kept separate.",
        }.get(transition, "Learning job state changed.")

    def _extract_budget_stats(self, trajectory: List[Dict[str, Any]]) -> Dict[str, float]:
        """从最后一步中提取 budget stats。"""
        if not trajectory:
            return {}
        stats = trajectory[-1].get("budget_stats")
        if not stats:
            return {}
        keys = [
            "token_usage_ratio",
            "context_window_ratio",
            "compression_applied",
            "dropped_parts",
            "truncated_chars",
            "token_cache_hits",
            "token_cache_misses",
            "token_cache_size",
            "agents_md_hits",
            "cold_recall_hits",
            "agents_md_ms",
            "cold_recall_ms",
            "context_build_ms",
        ]
        return {key: stats.get(key, 0) for key in keys}

    def _load_warm_context(self, task: str) -> str:
        """从知识库加载与当前任务相关的经验。"""
        hits = self.knowledge_base.search(task, top_k=3)
        if not hits:
            return ""
        lines = ["\n【相关经验】"]
        for h in hits:
            lines.append(f"- [{h.get('domain', '')}] {h.get('rule', '')}")
        return "\n".join(lines)

    def _learn_from_session(
        self,
        session_id: str,
        task: str,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            insights = self.reflection.reflect(session_id, task, result["trajectory"])
            for item in insights:
                self.knowledge_base.store(item)

            # Archive insights privately before shared-memory promotion review.
            shared_summary: Dict[str, Any] = {}
            cold_memory = getattr(self.memory_manager, "cold", None)
            if cold_memory is not None and self.config.get("learning.shared_memory_outcomes_enabled", True):
                shared_summary = archive_learning_insights_to_shared_memory(
                    cold_memory,
                    session_id=session_id,
                    task=task,
                    insights=insights,
                    result=result,
                    agent_id=str(self.config.get("agent.id", "default")),
                    workspace_profile=str(result.get("workspace_profile") or "general"),
                )

            # 如果反思发现可复用模式，生成技能
            if self.config.get("learning.skill_generation_enabled", True):
                generated = self.skill_generator.generate(session_id, result["trajectory"], insights)
                if generated:
                    self.tools.discover_generated_skills()
                    self._sync_generated_tools_to_executor()
                for skill in generated:
                    self.event_log.append(Event.create(
                        "skill_generated",
                        session_id=session_id,
                        source="learning",
                        payload={"skill": skill},
                    ))
            return {"insight_count": len(insights), "shared_memory": shared_summary}
        except Exception as e:
            self.event_log.append(Event.create(
                "learning_failed",
                session_id=session_id,
                source="learning",
                payload={"error": str(e)},
            ))
            return {"insight_count": 0, "shared_memory": {}, "error": str(e)}

    def _on_repair_success(self, session_id: str, info: Dict[str, Any]) -> None:
        """修复成功后，触发学习转化层从修复中学习。"""
        try:
            insights = self.reflection.reflect_on_repair(session_id, info)
            for item in insights:
                self.knowledge_base.store(item)
                self._store_fault_pattern(item)
        except Exception:
            pass

    def _store_fault_pattern(self, item: Dict[str, Any]) -> None:
        """把修复经验写入 fault_patterns.jsonl，供核心运转层下次匹配。"""
        import json
        path = self.storage_root / "fault_patterns.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    def _new_session_id(self) -> str:
        import uuid
        return str(uuid.uuid4())[:8]

    def close(self) -> None:
        if self.mcp_integration and self._owns_mcp_integration:
            self.mcp_integration.stop()
