"""
agent/react_loop.py — ReAct 推理循环

思考 → 行动 → 观察 → ... → 输出。
所有动作经过核心运转层的 Executor 执行。

扩展：支持专家救援注入（thought / action / loop_takeover）。
"""

from __future__ import annotations
import json
import hashlib
import concurrent.futures
import time
import uuid
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from agent.tool_registry import ToolRegistry
from core.cancellation import TaskCancelled
from core.executor import Executor
from core.event_log import EventLog
from core.goal_tracking import checklist_context_hint, update_goal_checklist
from core.plan_validation import summarize_plan_validation, validate_plan_step
from llm.interface import LLMInterface

if TYPE_CHECKING:
    from memory.manager import MemoryManager


class ReActLoop:
    """ReAct 循环：Agent 层的核心推理引擎。"""

    def __init__(
        self,
        llm: LLMInterface,
        tools: ToolRegistry,
        executor: Executor,
        event_log: EventLog,
        max_iterations: int = 20,
        event_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
        memory_manager: Optional["MemoryManager"] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        tool_progress_interval_seconds: float = 5.0,
        skill_sync_status: Optional[Callable[[], Dict[str, Any]]] = None,
        runtime_contract_provider: Optional[Callable[[str], Dict[str, Any]]] = None,
    ):
        self.llm = llm
        self.tools = tools
        self.executor = executor
        self.event_log = event_log
        self.max_iterations = max_iterations
        self.event_sink = event_sink
        self.memory_manager = memory_manager
        self.cancel_check = cancel_check
        self.tool_progress_interval_seconds = max(0.1, float(tool_progress_interval_seconds or 5.0))
        self.skill_sync_status = skill_sync_status
        self.runtime_contract_provider = runtime_contract_provider

        # 专家救援相关状态
        self._expert_context: str = ""
        self._trajectory: List[Dict[str, Any]] = []
        self._context: str = ""
        self._task: str = ""
        self._session_id: str = ""
        self._on_step: Optional[Callable[[Dict[str, Any], List[Dict[str, Any]]], None]] = None
        self._run_started_at: float = 0.0
        self._first_response_emitted = False
        self._goal_checklist: Dict[str, Any] = {}
        self._skill_sync_signature: Optional[str] = None
        self._latest_skill_sync: Dict[str, Any] = {}
        self._context_sync_signature: Optional[str] = None
        self._context_sync_snapshot: Dict[str, Any] = {}
        self._context_sync_revision = 0
        self._runtime_contract_snapshot: Dict[str, Any] = {}
        self._maker_briefing_snapshot: Dict[str, Any] = {}
        self._maker_goal_templates: List[Dict[str, Any]] = []

    def _emit(self, session_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        if self.event_sink:
            try:
                self.event_sink({
                    "type": event_type,
                    "session_id": session_id,
                    "payload": payload,
                })
            except Exception:
                pass

    def _emit_llm_usage(self, phase: str) -> None:
        stats_getter = getattr(self.llm, "last_call_stats", None)
        if not callable(stats_getter):
            return
        try:
            stats = stats_getter()
        except Exception:
            return
        if stats:
            self._emit(self._session_id, "llm_usage", {"phase": phase, **stats})

    def _emit_latency(self, phase: str, started_at: float, **payload: Any) -> None:
        self._emit(self._session_id, "latency", {
            "phase": phase,
            "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 1),
            **payload,
        })

    def _emit_first_response_latency(self, phase: str) -> None:
        if self._first_response_emitted or not self._run_started_at:
            return
        self._first_response_emitted = True
        self._emit_latency("first_response", self._run_started_at, source_phase=phase)

    def _check_cancelled(self) -> None:
        if self.cancel_check and self.cancel_check():
            raise TaskCancelled()

    @property
    def trajectory(self) -> List[Dict[str, Any]]:
        """当前轨迹，供 RescueOrchestrator 读取。"""
        return self._trajectory

    def run(
        self,
        task: str,
        session_id: Optional[str] = None,
        on_step: Optional[Callable[[Dict[str, Any], List[Dict[str, Any]]], None]] = None,
        resume: bool = False,
    ) -> Dict[str, Any]:
        """运行 ReAct 循环。on_step 在每步观测后被调用，可抛出 RescueRequired。
        resume=True 时保留已有 trajectory 和 context，用于救援后继续。"""
        if not resume:
            self._session_id = session_id or str(uuid.uuid4())[:8]
            self._task = task
            self._trajectory = []
            self._runtime_contract_snapshot = self._load_runtime_contract_snapshot()
            self._maker_briefing_snapshot = self._build_maker_briefing_snapshot(task)
            self._maker_goal_templates = self._extract_maker_goal_templates(self._runtime_contract_snapshot)
            self._context = self._build_context(task)
            self._expert_context = ""
            self._first_response_emitted = False
            self._goal_checklist = update_goal_checklist(
                task=task,
                trajectory=[],
                maker_templates=self._maker_goal_templates,
            )
            self._latest_skill_sync = {}
            self._context_sync_signature = None
            self._context_sync_snapshot = {}
            self._context_sync_revision = 0
        else:
            self._session_id = session_id or self._session_id or str(uuid.uuid4())[:8]
            self._task = task or self._task
            self._first_response_emitted = False
            if not self._goal_checklist:
                if not self._runtime_contract_snapshot:
                    self._runtime_contract_snapshot = self._load_runtime_contract_snapshot()
                if not self._maker_briefing_snapshot:
                    self._maker_briefing_snapshot = self._build_maker_briefing_snapshot(self._task)
                if not self._maker_goal_templates:
                    self._maker_goal_templates = self._extract_maker_goal_templates(self._runtime_contract_snapshot)
                self._goal_checklist = update_goal_checklist(
                    task=self._task,
                    trajectory=self._trajectory,
                    maker_templates=self._maker_goal_templates,
                )
        self._on_step = on_step

        self._run_started_at = time.perf_counter()
        self._emit(self._session_id, "status", {"message": "任务开始", "task": task})
        if self._maker_briefing_snapshot:
            self._emit(self._session_id, "maker_briefing", self._maker_briefing_snapshot)
        self._emit(self._session_id, "goal_checklist", self._goal_checklist)
        self._maybe_emit_skill_sync(iteration=-1, reason="session_start", force=True)
        self._maybe_emit_context_sync(iteration=-1, reason="session_start", force=True)

        for i in range(self.max_iterations):
            iteration_started_at = time.perf_counter()
            self._check_cancelled()
            step = self._run_iteration(i)
            self._check_cancelled()
            self._emit_latency("iteration_planning", iteration_started_at, iteration=i)

            if step.get("done"):
                self._trajectory.append(step)
                self._emit(self._session_id, "output", {"output": step.get("output", "")})
                self._refresh_goal_checklist(output=step.get("output", ""))
                self._maybe_emit_context_sync(iteration=i, reason="output")
                break

            # 执行动作前先进行 tool-call schema 校验
            tool_name = step["action"].get("tool")
            params = step["action"].get("params", {})
            guard = self._maker_first_action_guard(i, tool_name, params)
            if guard["decision"] == "block":
                self._emit(self._session_id, "maker_briefing_guard", guard)
                observation = self._maker_guard_observation(tool_name, guard)
                step["observation"] = observation
                plan_validation = self._validate_plan_step(step)
                step["plan_validation"] = plan_validation
                self._trajectory.append(step)
                self._emit(self._session_id, "observation", {
                    "iteration": i,
                    "tool": tool_name,
                    "observation": observation,
                })
                self._emit(self._session_id, "plan_validation", plan_validation)
                self._refresh_goal_checklist()
                self._maybe_emit_skill_sync(iteration=i, reason="maker_briefing_guard")
                self._maybe_emit_context_sync(iteration=i, reason="maker_briefing_guard")
                self._context += self._maker_guard_context_hint(guard)
                self._emit(self._session_id, "error", {"iteration": i, "message": guard["reason"]})

                if self._on_step:
                    self._on_step(step, self._trajectory)
                continue
            if guard["decision"] != "skip":
                self._emit(self._session_id, "maker_briefing_guard", guard)
            preflight = self.tools.preflight_action(
                tool_name,
                params,
                query=f"{self._task}\n{step.get('thought', '')}\n{self._context}",
            )
            if not preflight["ok"]:
                self._emit(self._session_id, "tool_preflight", {
                    "iteration": i,
                    "tool": tool_name,
                    "ok": False,
                    "errors": preflight.get("structured_errors") or preflight.get("errors", []),
                    "alternatives": preflight.get("alternatives", []),
                    "suggested_next_step": preflight.get("suggested_next_step", ""),
                })
                error_text = "; ".join(preflight["errors"])
                observation = self._validation_observation(tool_name, preflight)
                step["observation"] = observation
                plan_validation = self._validate_plan_step(step)
                step["plan_validation"] = plan_validation
                self._trajectory.append(step)
                self._emit(self._session_id, "observation", {
                    "iteration": i,
                    "tool": tool_name,
                    "observation": observation,
                })
                self._emit(self._session_id, "plan_validation", plan_validation)
                self._refresh_goal_checklist()
                self._maybe_emit_skill_sync(iteration=i, reason="plan_validation")
                self._maybe_emit_context_sync(iteration=i, reason="plan_validation")
                self._context += self._validation_context_hint(tool_name, preflight)
                self._emit(self._session_id, "error", {"iteration": i, "message": error_text})

                if self._on_step:
                    self._on_step(step, self._trajectory)
                continue
            self._emit(self._session_id, "tool_preflight", {
                "iteration": i,
                "tool": tool_name,
                "ok": True,
                "alternatives": preflight.get("alternatives", []),
            })

            # 校验通过，正常执行
            self._emit(self._session_id, "tool_call", {"tool": tool_name, "params": params})

            self._check_cancelled()
            tool_started_at = time.perf_counter()
            observation = self._execute_action_with_progress(
                self._session_id,
                tool_name,
                params,
                iteration=i,
                started_at=tool_started_at,
            )
            self._check_cancelled()
            self._emit_latency(
                "tool_call",
                tool_started_at,
                iteration=i,
                tool=tool_name,
                ok=bool(observation.get("ok")),
            )
            observation = self._reconcile_if_uncertain_commit(i, tool_name, observation)
            step["observation"] = observation
            plan_validation = self._validate_plan_step(step)
            step["plan_validation"] = plan_validation
            self._trajectory.append(step)
            self._emit(self._session_id, "observation", {
                "iteration": i,
                "tool": tool_name,
                "observation": observation,
            })
            self._emit(self._session_id, "plan_validation", plan_validation)
            self._refresh_goal_checklist()
            self._maybe_emit_skill_sync(iteration=i, reason="plan_validation")
            self._maybe_emit_context_sync(iteration=i, reason="plan_validation")

            # 失败时更新上下文
            if not observation.get("ok"):
                error_msg = f"\n[错误] {tool_name} 失败: {observation.get('error')}"
                self._context += error_msg
                if observation.get("error_type") == "tool_timeout" or observation.get("partial"):
                    self._context += self._tool_timeout_context_hint(tool_name, observation)
                self._emit(self._session_id, "error", {"iteration": i, "message": error_msg})

            # 触发外部回调（救援触发器在此检查）
            if self._on_step:
                self._on_step(step, self._trajectory)

        result = self._build_result()
        self._emit_latency("session_total", self._run_started_at, iteration_count=len(self._trajectory))
        self._emit(self._session_id, "status", {"message": "任务结束", "result_summary": self._summarize(result)})
        return result

    def _execute_action_with_progress(
        self,
        session_id: str,
        tool_name: Optional[str],
        params: Dict[str, Any],
        *,
        iteration: int,
        started_at: float,
    ) -> Dict[str, Any]:
        heartbeat_count = 0
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = pool.submit(self._execute_action, session_id, tool_name, params)
        try:
            while True:
                try:
                    return future.result(timeout=self.tool_progress_interval_seconds)
                except concurrent.futures.TimeoutError:
                    self._check_cancelled()
                    heartbeat_count += 1
                    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
                    self._emit(session_id, "tool_progress", {
                        "iteration": iteration,
                        "tool": tool_name,
                        "status": "running",
                        "elapsed_ms": elapsed_ms,
                        "heartbeat_count": heartbeat_count,
                        "partial": True,
                    })
        except Exception:
            future.cancel()
            raise
        finally:
            pool.shutdown(wait=future.done(), cancel_futures=True)

    def _reconcile_if_uncertain_commit(
        self,
        iteration: int,
        tool_name: Optional[str],
        observation: Dict[str, Any],
    ) -> Dict[str, Any]:
        if observation.get("committed") is not None or not observation.get("idempotency_key"):
            return observation
        self._emit(self._session_id, "commit_reconcile", {
            "iteration": iteration,
            "tool": tool_name,
            "idempotency_key": observation.get("idempotency_key"),
            "status": "checking",
        })
        reconciler = getattr(self.executor, "reconcile_commit_state", None)
        if not callable(reconciler):
            return observation
        reconciled = reconciler(observation)
        self._emit(self._session_id, "commit_reconcile", {
            "iteration": iteration,
            "tool": tool_name,
            "idempotency_key": reconciled.get("idempotency_key"),
            "status": reconciled.get("reconcile_status", "unknown"),
            "committed": reconciled.get("committed"),
            "observation": reconciled,
        })
        return reconciled

    def _validate_plan_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        return validate_plan_step(
            task=self._task,
            step=step,
            trajectory=self._trajectory,
        )

    def _maker_first_action_guard(
        self,
        iteration: int,
        tool_name: Optional[str],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        briefing = self._maker_briefing_snapshot if isinstance(self._maker_briefing_snapshot, dict) else {}
        if iteration != 0 or not briefing or not tool_name:
            return {"decision": "skip", "iteration": iteration}
        if not briefing.get("connected"):
            return {
                "decision": "pass",
                "iteration": iteration,
                "tool": tool_name,
                "reason": "MakerMCP is disconnected; local diagnostics are allowed.",
                "authority": briefing.get("authority"),
                "recommended_first_action": briefing.get("recommended_first_action"),
            }

        selected_template = briefing.get("selected_template")
        if not isinstance(selected_template, dict):
            selected_template = {}
        suggested_tools = [
            str(item)
            for item in briefing.get("suggested_tools", [])
            if item
        ] if isinstance(briefing.get("suggested_tools"), list) else []
        maker = self._runtime_contract_snapshot.get("maker_mcp") if isinstance(self._runtime_contract_snapshot, dict) else {}
        top_tools = [
            str(item.get("name"))
            for item in (maker.get("top_tools", []) if isinstance(maker, dict) else [])
            if isinstance(item, dict) and item.get("name")
        ]
        allowed_tools = sorted(set(suggested_tools + top_tools + [
            "maker_briefing",
            "runtime_contract",
            "query_skills",
        ]))
        if not allowed_tools:
            return {
                "decision": "pass",
                "iteration": iteration,
                "tool": tool_name,
                "reason": "No Maker authority tools are known yet; current diagnostic action is allowed.",
                "authority": briefing.get("authority"),
                "recommended_first_action": briefing.get("recommended_first_action"),
            }
        if tool_name in allowed_tools or tool_name.startswith("maker_") or tool_name.startswith("mcp_"):
            return {
                "decision": "pass",
                "iteration": iteration,
                "tool": tool_name,
                "reason": "First action matches Maker briefing authority.",
                "authority": briefing.get("authority"),
                "selected_template": selected_template,
                "allowed_tools": allowed_tools[:8],
                "recommended_first_action": briefing.get("recommended_first_action"),
            }

        if self._looks_like_local_side_effect(tool_name, params):
            return {
                "decision": "block",
                "iteration": iteration,
                "tool": tool_name,
                "reason": (
                    "First action would make a local side effect before using the Maker briefing "
                    "authority. Use a MakerMCP/status/briefing action first, or explain why local "
                    "files are the authority for this task."
                ),
                "authority": briefing.get("authority"),
                "selected_template": selected_template,
                "allowed_tools": allowed_tools[:8],
                "suggested_tools": suggested_tools[:4],
                "recommended_first_action": briefing.get("recommended_first_action"),
                "recommended_endpoint": briefing.get("recommended_endpoint"),
            }

        return {
            "decision": "warn",
            "iteration": iteration,
            "tool": tool_name,
            "reason": "First action does not directly match Maker briefing, but appears diagnostic.",
            "authority": briefing.get("authority"),
            "selected_template": selected_template,
            "allowed_tools": allowed_tools[:8],
            "suggested_tools": suggested_tools[:4],
            "recommended_first_action": briefing.get("recommended_first_action"),
            "recommended_endpoint": briefing.get("recommended_endpoint"),
        }

    @staticmethod
    def _looks_like_local_side_effect(tool_name: str, params: Dict[str, Any]) -> bool:
        name = tool_name.lower()
        side_effect_words = [
            "write",
            "delete",
            "move",
            "rename",
            "create",
            "save",
            "patch",
            "apply",
            "build",
            "submit",
            "publish",
        ]
        if any(word in name for word in side_effect_words):
            return True
        if not isinstance(params, dict):
            return False
        return any(
            key in params
            for key in ["content", "patch", "diff", "destination", "new_path", "target_path"]
        )

    def _maker_guard_observation(
        self,
        tool_name: Optional[str],
        guard: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "ok": False,
            "valid": False,
            "failure_type": "maker_briefing_guard",
            "tool": tool_name,
            "decision": guard.get("decision"),
            "reason": guard.get("reason"),
            "authority": guard.get("authority"),
            "allowed_tools": guard.get("allowed_tools", []),
            "suggested_tools": guard.get("suggested_tools", []),
            "recommended_first_action": guard.get("recommended_first_action"),
            "recommended_endpoint": guard.get("recommended_endpoint"),
            "suggested_fix": (
                "Follow maker_briefing first: choose one suggested MakerMCP/status tool, "
                "or call maker_briefing/runtime_contract before making local side effects."
            ),
        }

    @staticmethod
    def _maker_guard_context_hint(guard: Dict[str, Any]) -> str:
        payload = {
            "failure_type": "maker_briefing_guard",
            "decision": guard.get("decision"),
            "reason": guard.get("reason"),
            "authority": guard.get("authority"),
            "allowed_tools": guard.get("allowed_tools", []),
            "suggested_tools": guard.get("suggested_tools", []),
            "recommended_first_action": guard.get("recommended_first_action"),
            "recommended_endpoint": guard.get("recommended_endpoint"),
        }
        return (
            "\n[maker_briefing_guard]\n"
            f"{json.dumps(payload, ensure_ascii=False)}\n"
            "Before local side effects, follow the Maker briefing authority or fetch the compact briefing/contract again.\n"
        )

    def _refresh_goal_checklist(self, output: str = "") -> None:
        self._goal_checklist = update_goal_checklist(
            task=self._task,
            trajectory=self._trajectory,
            output=output,
            maker_templates=self._maker_goal_templates,
        )
        self._emit(self._session_id, "goal_checklist", self._goal_checklist)
        self._context += checklist_context_hint(self._goal_checklist)

    def _maybe_emit_skill_sync(self, iteration: int, reason: str, force: bool = False) -> None:
        if not callable(self.skill_sync_status):
            return
        try:
            status = self.skill_sync_status()
        except Exception as e:
            self._emit(self._session_id, "skill_sync", {
                "iteration": iteration,
                "reason": reason,
                "ok": False,
                "error": str(e),
            })
            self._latest_skill_sync = {
                "ok": False,
                "state": "error",
                "error": str(e),
            }
            return

        registry = status.get("registry", {}) if isinstance(status, dict) else {}
        manifest = status.get("manifest", {}) if isinstance(status, dict) else {}
        export_plan = status.get("export_plan", {}) if isinstance(status, dict) else {}
        signature = registry.get("signature")
        previous = self._skill_sync_signature
        changed = bool(signature and previous and previous != signature)
        if signature:
            self._skill_sync_signature = str(signature)

        manifest_summary = manifest.get("summary", {})
        export_summary = export_plan.get("summary", {})
        has_compatibility_warning = bool(
            manifest.get("conflicts")
            or int(export_summary.get("needs_review") or 0) > 0
        )
        if not force and not changed and not registry.get("changed") and not has_compatibility_warning:
            return

        actions = export_plan.get("actions", []) if isinstance(export_plan, dict) else []
        actionable = [
            action for action in actions
            if action.get("action") != "skip"
        ][:8]
        payload = {
            "iteration": iteration,
            "reason": reason,
            "ok": True,
            "changed": changed or bool(registry.get("changed")),
            "state": registry.get("state", "unknown"),
            "signature": signature,
            "previous_signature": previous or registry.get("previous_signature"),
            "compatibility_status": "needs_review" if has_compatibility_warning else "ok",
            "manifest_summary": manifest_summary,
            "export_plan_summary": export_summary,
            "conflicts": manifest.get("conflicts", []),
            "actions_preview": actionable,
        }
        self._latest_skill_sync = payload
        if payload["changed"] and hasattr(self.tools, "discover_generated_skills"):
            self.tools.discover_generated_skills()
            self._context += (
                "\n[skill_sync_changed]\n"
                f"{json.dumps(payload, ensure_ascii=False)}\n"
                "Generated skills were re-discovered; use the refreshed tool list before the next action.\n"
            )
        elif has_compatibility_warning:
            self._context += (
                "\n[skill_compatibility_warning]\n"
                f"{json.dumps(payload, ensure_ascii=False)}\n"
                "Resolve skill version/content conflicts or review export actions before relying on cross-agent skill calls.\n"
            )
        self._emit(self._session_id, "skill_sync", payload)

    def _maybe_emit_context_sync(self, iteration: int, reason: str, force: bool = False) -> None:
        snapshot = self._build_context_sync_snapshot(iteration)
        encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str)
        signature = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
        previous_signature = self._context_sync_signature
        changed = bool(previous_signature and previous_signature != signature)
        if not force and not changed:
            return

        diff_keys = self._context_sync_diff_keys(self._context_sync_snapshot, snapshot)
        self._context_sync_signature = signature
        self._context_sync_snapshot = snapshot
        self._context_sync_revision += 1
        self._emit(self._session_id, "context_sync", {
            "iteration": iteration,
            "reason": reason,
            "revision": self._context_sync_revision,
            "changed": force or changed,
            "signature": signature,
            "previous_signature": previous_signature,
            "diff_keys": diff_keys,
            "snapshot": snapshot,
        })

    def _build_context_sync_snapshot(self, iteration: int) -> Dict[str, Any]:
        last_step = self._latest_actionable_step()
        action = last_step.get("action") if isinstance(last_step.get("action"), dict) else {}
        observation = last_step.get("observation") if isinstance(last_step.get("observation"), dict) else {}
        plan_validation = (
            last_step.get("plan_validation")
            if isinstance(last_step.get("plan_validation"), dict)
            else {}
        )
        skill_sync = self._latest_skill_sync if isinstance(self._latest_skill_sync, dict) else {}
        artifacts = self._collect_artifact_refs(limit=8)
        params = action.get("params") if isinstance(action.get("params"), dict) else {}
        return {
            "session_id": self._session_id,
            "task": self._task,
            "iteration": iteration,
            "trajectory_steps": len(self._trajectory),
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
                "overall": self._goal_checklist.get("overall"),
                "counts": self._goal_checklist.get("counts", {}),
                "next_focus": self._goal_checklist.get("next_focus"),
            },
            "commit_state": self._commit_state_from_observation(observation),
            "skill_sync": {
                "ok": skill_sync.get("ok"),
                "state": skill_sync.get("state"),
                "signature": skill_sync.get("signature"),
                "compatibility_status": skill_sync.get("compatibility_status"),
                "changed": bool(skill_sync.get("changed")),
            },
            "artifact_refs": artifacts,
            "artifact_count": len(artifacts),
        }

    def _latest_actionable_step(self) -> Dict[str, Any]:
        for step in reversed(self._trajectory):
            action = step.get("action")
            observation = step.get("observation")
            if isinstance(observation, dict):
                return step
            if isinstance(action, dict) and action.get("tool"):
                return step
        return self._trajectory[-1] if self._trajectory else {}

    @staticmethod
    def _context_sync_diff_keys(previous: Dict[str, Any], current: Dict[str, Any]) -> List[str]:
        if not previous:
            return sorted(current.keys())
        return sorted(
            key for key in current.keys()
            if previous.get(key) != current.get(key)
        )

    def _collect_artifact_refs(self, limit: int = 8) -> List[Dict[str, Any]]:
        refs: List[Dict[str, Any]] = []
        seen = set()
        for step in reversed(self._trajectory[-8:]):
            action = step.get("action") if isinstance(step.get("action"), dict) else {}
            observation = step.get("observation")
            if not isinstance(observation, dict):
                continue
            ref = self._artifact_ref_from_step(action, observation)
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

    @staticmethod
    def _artifact_ref_from_step(action: Dict[str, Any], observation: Dict[str, Any]) -> Dict[str, Any]:
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

    @staticmethod
    def _commit_state_from_observation(observation: Dict[str, Any]) -> Dict[str, Any]:
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

    def _run_iteration(self, iteration: int) -> Dict[str, Any]:
        """执行单轮思考+动作选择。"""
        self._check_cancelled()
        step = {
            "iteration": iteration,
            "timestamp": time.time(),
            "source": "local",
        }

        # 准备上下文：如果注入了 MemoryManager，由它统一编排并返回预算统计。
        raw_context = self._context + self._expert_context
        think_tools = self.tools.rank_tools(
            query=f"{self._task}\n{raw_context}",
            limit=10,
        )
        think_rank_stats = self.tools.last_rank_stats() if hasattr(self.tools, "last_rank_stats") else {}
        think_tools_description = self.tools.schema_for_llm(tools=think_tools)
        step["selected_tools"] = [tool.get("name") for tool in think_tools]
        self._emit(self._session_id, "tool_selection", {
            "iteration": iteration,
            "phase": "think",
            "tools": [
                {"name": tool.get("name"), "source": tool.get("source", "")}
                for tool in think_tools
            ],
            "stats": think_rank_stats,
        })
        if self.memory_manager is not None:
            prepared_context, budget_stats = self.memory_manager.prepare_think_payload(
                task=self._task,
                context=raw_context,
                trajectory=self._trajectory,
                tools_description=think_tools_description,
                max_tokens=512,
            )
            step["budget_stats"] = budget_stats.to_dict() if budget_stats else None
            if budget_stats:
                self._emit(self._session_id, "context_budget", {
                    "iteration": iteration,
                    "phase": "think",
                    **budget_stats.to_dict(),
                })
            # trajectory/tools 已包含在 prepared_context 中，避免 LLM 重复拼接。
            trajectory_for_llm: List[Dict[str, Any]] = []
            tools_for_llm = ""
        else:
            prepared_context = raw_context
            trajectory_for_llm = self._trajectory
            tools_for_llm = think_tools_description
            step["budget_stats"] = None

        # 思考
        think_started_at = time.perf_counter()
        thought = self.llm.think(
            task=self._task,
            context=prepared_context,
            trajectory=trajectory_for_llm,
            tools_description=tools_for_llm,
        )
        self._check_cancelled()
        self._emit_latency("llm_think", think_started_at, iteration=iteration)
        self._emit_first_response_latency("thought")
        step["thought"] = thought
        self._emit(self._session_id, "thought", {"iteration": iteration, "thought": thought})
        self._emit_llm_usage("think")

        # 决定动作：根据刚产生的思考再裁剪一次工具，减少 action prompt 体积和误选概率。
        action_tools = self.tools.rank_tools(
            query=f"{self._task}\n{thought}\n{raw_context}",
            limit=8,
        )
        action_rank_stats = self.tools.last_rank_stats() if hasattr(self.tools, "last_rank_stats") else {}
        action_tools_description = self.tools.schema_for_llm(tools=action_tools)
        step["selected_tools"] = [tool.get("name") for tool in action_tools]
        self._emit(self._session_id, "tool_selection", {
            "iteration": iteration,
            "phase": "action",
            "tools": [
                {"name": tool.get("name"), "source": tool.get("source", "")}
                for tool in action_tools
            ],
            "stats": action_rank_stats,
        })
        action_started_at = time.perf_counter()
        action = self.llm.choose_action(
            task=self._task,
            thought=thought,
            tools_description=action_tools_description,
        )
        self._check_cancelled()
        self._emit_latency("llm_action", action_started_at, iteration=iteration)
        step["action"] = action
        self._emit(self._session_id, "action", {"iteration": iteration, "action": action})
        self._emit_llm_usage("action")

        if action.get("_parse_error"):
            step["output"] = "本地模型没有输出合法动作 JSON。请查看上一条“决策”事件中的 raw 字段。"
            step["done"] = True

        if action.get("done"):
            step["output"] = action.get("output", "")
            step["done"] = True

        # 清空一次性专家上下文
        self._expert_context = ""

        return step
    def _execute_action(
        self,
        session_id: str,
        tool_name: Optional[str],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not tool_name:
            return {"ok": False, "error": "没有选择工具"}
        if not self.tools.has(tool_name):
            return {"ok": False, "error": f"工具 {tool_name} 不存在"}

        self._check_cancelled()
        validation = self.tools.validate_action(tool_name, params)
        if not validation["ok"]:
            return self._validation_observation(tool_name, validation)

        # 本地工具统一走 Executor；MCP 工具由 Executor 转发给 MCP handler
        self._check_cancelled()
        result = self.executor.propose_action(session_id, tool_name, params)
        return result

    def _validation_observation(
        self,
        tool_name: Optional[str],
        validation: Dict[str, Any],
    ) -> Dict[str, Any]:
        errors = validation.get("errors", [])
        structured_errors = validation.get("structured_errors", [])
        first = structured_errors[0] if structured_errors else {}
        return {
            "ok": False,
            "valid": False,
            "failure_type": "tool_validation",
            "tool": tool_name,
            "error": "; ".join(errors),
            "validation_errors": errors,
            "structured_errors": structured_errors,
            "rule_id": first.get("rule_id"),
            "path": first.get("path"),
            "reason": first.get("reason"),
            "suggested_fix": first.get("suggested_fix"),
            "alternatives": validation.get("alternatives", []),
            "suggested_next_step": validation.get("suggested_next_step"),
        }

    def _validation_context_hint(
        self,
        tool_name: Optional[str],
        validation: Dict[str, Any],
    ) -> str:
        errors = validation.get("errors", [])
        structured_errors = validation.get("structured_errors", [])
        payload = {
            "valid": False,
            "failure_type": "tool_validation",
            "tool": tool_name,
            "errors": structured_errors or errors,
            "alternatives": validation.get("alternatives", []),
            "suggested_next_step": validation.get("suggested_next_step"),
        }
        return (
            "\n[tool_validation_failed]\n"
            f"{json.dumps(payload, ensure_ascii=False)}\n"
            "Fix the tool name or params exactly as suggested, or choose one of the alternatives before retrying.\n"
        )

    def _tool_timeout_context_hint(
        self,
        tool_name: Optional[str],
        observation: Dict[str, Any],
    ) -> str:
        payload = {
            "failure_type": "tool_timeout",
            "tool": tool_name,
            "elapsed_ms": observation.get("elapsed_ms"),
            "timeout_seconds": observation.get("timeout_seconds"),
            "partial": observation.get("partial", False),
            "stdout_tail": self._tail_text(observation.get("stdout")),
            "stderr_tail": self._tail_text(observation.get("stderr")),
            "suggested_fix": (
                "Do not repeat the same long call blindly. Use a smaller timeout, "
                "narrow the command/tool params, inspect partial output, or choose "
                "a cheaper diagnostic tool before continuing."
            ),
        }
        return (
            "\n[tool_timeout]\n"
            f"{json.dumps(payload, ensure_ascii=False)}\n"
            "Continue reasoning in the next step with the partial result instead of blocking.\n"
        )

    @staticmethod
    def _tail_text(value: Any, limit: int = 1200) -> str:
        if value is None:
            return ""
        text = str(value)
        if len(text) <= limit:
            return text
        return text[-limit:]

    def _build_context(self, task: str) -> str:
        base = f"Task: {task}\nUse the available tools step by step."
        if not callable(self.runtime_contract_provider):
            return base
        try:
            from core.runtime_contract import render_maker_briefing_for_llm, render_runtime_contract_for_llm

            contract = getattr(self, "_runtime_contract_snapshot", {}) or self._load_runtime_contract_snapshot()
            rendered = render_runtime_contract_for_llm(contract)
            briefing = getattr(self, "_maker_briefing_snapshot", {}) or self._build_maker_briefing_snapshot(task)
            rendered_briefing = render_maker_briefing_for_llm(briefing)
        except Exception as e:
            rendered = json.dumps({"runtime_contract_error": str(e)}, ensure_ascii=False)
            rendered_briefing = json.dumps({"maker_briefing_error": str(e)}, ensure_ascii=False)
        return (
            f"{base}\n"
            "[runtime_contract]\n"
            f"{rendered}\n"
            "[/runtime_contract]\n"
            "[maker_briefing]\n"
            f"{rendered_briefing}\n"
            "[/maker_briefing]\n"
        )

    def _load_runtime_contract_snapshot(self) -> Dict[str, Any]:
        if not callable(self.runtime_contract_provider):
            return {}
        try:
            contract = self.runtime_contract_provider(self._session_id or "{session_id}")
            return contract if isinstance(contract, dict) else {}
        except Exception:
            return {}

    def _build_maker_briefing_snapshot(self, task: str) -> Dict[str, Any]:
        try:
            from core.runtime_contract import build_maker_briefing

            contract = getattr(self, "_runtime_contract_snapshot", {}) or self._load_runtime_contract_snapshot()
            briefing = build_maker_briefing(contract, task=task)
            return briefing if isinstance(briefing, dict) else {}
        except Exception as e:
            return {
                "version": "maker-briefing.v1",
                "task": task,
                "readiness": "unknown",
                "connected": False,
                "warning_codes": ["maker_briefing_error"],
                "authority": "runtime_contract",
                "recommended_first_action": f"Maker briefing unavailable: {e}",
                "suggested_tools": [],
            }

    @staticmethod
    def _extract_maker_goal_templates(contract: Dict[str, Any]) -> List[Dict[str, Any]]:
        maker = contract.get("maker_mcp") if isinstance(contract.get("maker_mcp"), dict) else {}
        templates = maker.get("task_templates") if isinstance(maker.get("task_templates"), list) else []
        return [item for item in templates if isinstance(item, dict)]

    def _build_result(self) -> Dict[str, Any]:
        output = ""
        for step in reversed(self._trajectory):
            if step.get("done") or "output" in step:
                output = step.get("output", "")
                break
        return {
            "session_id": self._session_id,
            "task": self._task,
            "trajectory": self._trajectory,
            "output": output,
            "iteration_count": len(self._trajectory),
            "plan_validation": summarize_plan_validation(self._trajectory),
            "goal_checklist": self._goal_checklist,
        }

    def _summarize(self, result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "iteration_count": result.get("iteration_count", 0),
            "output_length": len(result.get("output", "")),
        }

    # ------------------------------------------------------------------
    # 专家救援接口
    # ------------------------------------------------------------------
    def inject_expert_thought(self, thought: str) -> None:
        """在下一轮思考前注入专家提示。"""
        self._expert_context = f"\n[专家提示] {thought}\n"

    def inject_expert_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """直接执行专家指定的动作，并返回观察结果。"""
        tool_name = action.get("tool")
        params = action.get("params", {})
        self._emit(self._session_id, "tool_call", {"tool": tool_name, "params": params, "source": "expert"})
        observation = self._execute_action(self._session_id, tool_name, params)
        return observation

    def takeover(self, expert_llm: LLMInterface, steps: int) -> None:
        """由专家 LLM 接管循环若干轮。"""
        for i in range(steps):
            iteration = len(self._trajectory)
            step = {
                "iteration": iteration,
                "timestamp": time.time(),
                "source": "expert",
            }

            thought = expert_llm.think(
                task=self._task,
                context=self._context,
                trajectory=self._trajectory,
                tools_description=self.tools.schema_for_llm(),
            )
            step["thought"] = thought
            self._emit(self._session_id, "thought", {"iteration": iteration, "thought": thought, "source": "expert"})

            action = expert_llm.choose_action(
                task=self._task,
                thought=thought,
                tools_description=self.tools.schema_for_llm(),
            )
            step["action"] = action
            self._emit(self._session_id, "action", {"iteration": iteration, "action": action, "source": "expert"})

            if action.get("done"):
                step["output"] = action.get("output", "")
                step["done"] = True
                self._trajectory.append(step)
                self._emit(self._session_id, "output", {"output": step["output"], "source": "expert"})
                return

            tool_name = action.get("tool")
            params = action.get("params", {})
            self._emit(self._session_id, "tool_call", {"tool": tool_name, "params": params, "source": "expert"})
            observation = self._execute_action(self._session_id, tool_name, params)
            step["observation"] = observation
            self._trajectory.append(step)
            self._emit(self._session_id, "observation", {
                "iteration": iteration,
                "tool": tool_name,
                "observation": observation,
                "source": "expert",
            })

            if not observation.get("ok"):
                error_msg = f"\n[错误] {tool_name} 失败: {observation.get('error')}"
                self._context += error_msg
                self._emit(self._session_id, "error", {"iteration": iteration, "message": error_msg, "source": "expert"})

            if self._on_step:
                self._on_step(step, self._trajectory)
