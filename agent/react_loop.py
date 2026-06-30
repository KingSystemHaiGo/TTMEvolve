"""
agent/react_loop.py — ReAct 推理循环

思考 → 行动 → 观察 → ... → 输出。
所有动作经过核心运转层的 Executor 执行。

扩展：支持专家救援注入（thought / action / loop_takeover）。
"""

from __future__ import annotations
import json
import time
import uuid
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from agent.action_execution import (
    ActionExecutionService,
    tool_timeout_context_hint,
    validation_context_hint,
    validation_observation,
)
from agent.maker_guard import (
    maker_first_action_guard,
    maker_guard_context_hint,
    maker_guard_observation,
)
from agent.plan_first import (
    build_plan_first_result,
    draft_plan_from_llm,
    known_tool_names,
    run_plan_first_phase,
)
from agent.trajectory_result import (
    build_react_result,
    record_observation_step,
    record_output_step,
    summarize_react_result,
)
from agent.context_sync import (
    build_context_sync_snapshot,
    context_sync_diff_keys,
    context_sync_signature,
)
from agent.expert_takeover import run_expert_takeover
from agent.tool_registry import ToolRegistry
from core.cancellation import TaskCancelled
from core.executor import Executor
from core.event_log import EventLog
from core.goal_tracking import checklist_context_hint, update_goal_checklist
from core.plan_format import (
    empty_plan,
    plan_to_context_block,
)
from core.plan_validation import validate_plan_step
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
        plan_first_enabled: bool = False,
        plan_approval_provider: Optional[Callable[[Dict[str, Any]], bool]] = None,
        vsm_shell: Optional["VSMShell"] = None,
        homeostasis: Optional["LoopHomeostasis"] = None,
        thought_chain_strict: bool = False,
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
        self.action_execution = ActionExecutionService(
            tools=self.tools,
            executor=self.executor,
            emit=self._emit,
            check_cancelled=self._check_cancelled,
            progress_interval_seconds=self.tool_progress_interval_seconds,
        )
        self.skill_sync_status = skill_sync_status
        self.runtime_contract_provider = runtime_contract_provider
        self._plan_first_enabled = bool(plan_first_enabled)
        self._plan_approval_provider = plan_approval_provider
        # Phase D: thin VSM adapter. When ``is_active()`` is False the
        # pre/post step hooks short-circuit; the iteration loop is
        # unchanged for the default ``vsm.enabled=false`` configuration.
        self._vsm_shell = vsm_shell
        self._vsm_replan_requested: bool = False
        # Phase R1: when true, the LLM's think() output is parsed
        # into a structured ThoughtRecord (plan_step, hypothesis,
        # confidence, ...). When false (default), the existing
        # free-text path runs unchanged. The flag is opt-in.
        self._thought_chain_strict = bool(thought_chain_strict)
        # Phase R5: explicit FSM. Each main-loop phase calls
        # ``self._fsm.enter(STATE)`` so the evidence bundle can
        # render "what the agent is doing right now." The default
        # constructor gives a fully-functional FSM; no flag is
        # required because R5 is purely observational.
        from core.loop_fsm import LoopFSM, FSMState
        self._fsm = LoopFSM()
        # Phase R3: homeostatic dead-man's switch. When enabled,
        # the controller detects three stuck patterns and forces
        # the loop to terminate. The flag ``homeostasis.enabled``
        # is read by the caller; when None is passed, the
        # controller is disabled and the loop runs unchanged.
        self._homeostasis = homeostasis

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
        # Plan First state (already initialized above from constructor args)
        self._plan: Dict[str, Any] = empty_plan()
        self._plan_review: Dict[str, Any] = {}
        self._plan_approval_event: Optional[Any] = None
        self._plan_first_completed: bool = False

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
            # Plan First reset
            self._plan = empty_plan(task=task)
            self._plan_review = {}
            self._plan_first_completed = not self._plan_first_enabled
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

        # Plan First phase: build a structured plan and wait for user approval
        # before letting the ReAct loop execute any tool.
        if self._plan_first_enabled and not self._plan_first_completed:
            approved_plan = self._run_plan_first_phase(task)
            if approved_plan is None:
                # Plan phase aborted — return a minimal result so the UI can show
                # the draft plan and the rejection reason.
                return self._build_plan_first_result(reason="not_approved")
            self._plan_first_completed = True
            self._context += plan_to_context_block(approved_plan)

        for i in range(self.max_iterations):
            iteration_started_at = time.perf_counter()
            self._check_cancelled()
            # Phase R5: enter OBSERVE (collect current state).
            from core.loop_fsm import FSMState
            self._fsm_transition(FSMState.OBSERVE, iteration=i)
            # Phase D: VSM pre_step hook (no-op when shell inactive).
            self._vsm_pre_step(i)
            # Phase R5: ORIENT (memory + budget context).
            self._fsm_transition(FSMState.ORIENT, iteration=i)
            step = self._run_iteration(i)
            self._check_cancelled()
            self._emit_latency("iteration_planning", iteration_started_at, iteration=i)

            # Phase R3: homeostatic dead-man's switch. If the
            # controller detects a stuck pattern, force the loop to
            # terminate with a structured "stuck" output. We do
            # this *after* the iteration's observation is recorded
            # so the controller has the full step to inspect.
            # Phase R5: mark DECIDE / ACT transitions just before
            # execution; the actual final state is set in REFLECT
            # via _homeostasis_check's stuck branch.
            self._fsm_transition(FSMState.DECIDE, iteration=i)
            stuck = self._homeostasis_check(step)
            if stuck is not None:
                self._emit_stuck(stuck, i)
                # Phase R5: terminal state STUCK.
                self._fsm_transition(FSMState.STUCK, iteration=i)
                step["done"] = True
                step["output"] = {
                    "stuck": True,
                    "reason": stuck.get("reason"),
                    "homeostasis": stuck,
                }
                record_output_step(
                    trajectory=self._trajectory,
                    step=step,
                    iteration=i,
                    session_id=self._session_id,
                    emit=self._emit,
                    refresh_goal=self._refresh_goal_checklist,
                    emit_context_sync=self._maybe_emit_context_sync,
                )
                self._vsm_post_step(step, {"ok": False, "stuck": True}, i)
                break

            if step.get("done"):
                record_output_step(
                    trajectory=self._trajectory,
                    step=step,
                    iteration=i,
                    session_id=self._session_id,
                    emit=self._emit,
                    refresh_goal=self._refresh_goal_checklist,
                    emit_context_sync=self._maybe_emit_context_sync,
                )
                # VSM post_step on the final step (treat as the closing
                # observation so the shell can surface a verdict).
                self._vsm_post_step(step, {"ok": True}, i)
                break

            # Phase R5: ACT — enter before tool execution and
            # REFLECT after the observation is recorded below.
            self._fsm_transition(FSMState.ACT, iteration=i)

            # 执行动作前先进行 tool-call schema 校验
            tool_name = step["action"].get("tool")
            params = step["action"].get("params", {})
            guard = maker_first_action_guard(
                iteration=i,
                task=self._task,
                briefing=self._maker_briefing_snapshot,
                runtime_contract=self._runtime_contract_snapshot,
                tool_name=tool_name,
                params=params,
            )
            if guard["decision"] == "block":
                self._emit(self._session_id, "maker_briefing_guard", guard)
                observation = maker_guard_observation(tool_name, guard)
                record_observation_step(
                    trajectory=self._trajectory,
                    step=step,
                    iteration=i,
                    session_id=self._session_id,
                    tool_name=tool_name,
                    observation=observation,
                    emit=self._emit,
                    validate_step=self._validate_plan_step,
                    refresh_goal=self._refresh_goal_checklist,
                    emit_skill_sync=self._maybe_emit_skill_sync,
                    emit_context_sync=self._maybe_emit_context_sync,
                    reason="maker_briefing_guard",
                )
                self._context += maker_guard_context_hint(guard)
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
                observation = validation_observation(tool_name, preflight)
                record_observation_step(
                    trajectory=self._trajectory,
                    step=step,
                    iteration=i,
                    session_id=self._session_id,
                    tool_name=tool_name,
                    observation=observation,
                    emit=self._emit,
                    validate_step=self._validate_plan_step,
                    refresh_goal=self._refresh_goal_checklist,
                    emit_skill_sync=self._maybe_emit_skill_sync,
                    emit_context_sync=self._maybe_emit_context_sync,
                )
                self._context += validation_context_hint(tool_name, preflight)
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
            observation = self.action_execution.execute_with_progress(
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
            observation = self.action_execution.reconcile_if_uncertain_commit(
                self._session_id,
                i,
                tool_name,
                observation,
            )
            record_observation_step(
                trajectory=self._trajectory,
                step=step,
                iteration=i,
                session_id=self._session_id,
                tool_name=tool_name,
                observation=observation,
                emit=self._emit,
                validate_step=self._validate_plan_step,
                refresh_goal=self._refresh_goal_checklist,
                emit_skill_sync=self._maybe_emit_skill_sync,
                emit_context_sync=self._maybe_emit_context_sync,
            )

            # 失败时更新上下文
            if not observation.get("ok"):
                error_msg = f"\n[错误] {tool_name} 失败: {observation.get('error')}"
                self._context += error_msg
                if observation.get("error_type") == "tool_timeout" or observation.get("partial"):
                    self._context += tool_timeout_context_hint(tool_name, observation)
                self._emit(self._session_id, "error", {"iteration": i, "message": error_msg})

            # 触发外部回调（救援触发器在此检查）
            if self._on_step:
                self._on_step(step, self._trajectory)

            # Phase R5: REFLECT — record outcome and close the cycle.
            self._fsm_transition(FSMState.REFLECT, iteration=i)

        result = self._build_result()
        self._emit_latency("session_total", self._run_started_at, iteration_count=len(self._trajectory))
        self._emit(self._session_id, "status", {"message": "任务结束", "result_summary": self._summarize(result)})
        return result

    def _validate_plan_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        return validate_plan_step(
            task=self._task,
            step=step,
            trajectory=self._trajectory,
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
        snapshot = build_context_sync_snapshot(
            session_id=self._session_id,
            task=self._task,
            iteration=iteration,
            trajectory=self._trajectory,
            goal_checklist=self._goal_checklist,
            plan=self._plan,
            latest_skill_sync=self._latest_skill_sync,
            context_revision=self._context_sync_revision,
        )
        signature = context_sync_signature(snapshot)
        previous_signature = self._context_sync_signature
        changed = bool(previous_signature and previous_signature != signature)
        if not force and not changed:
            return

        diff_keys = context_sync_diff_keys(self._context_sync_snapshot, snapshot)
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

    def _homeostasis_check(self, step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Phase R3: consult the homeostatic dead-man's switch.

        Returns a stuck record if the controller fires. Returns
        ``None`` when the controller is disabled or has not
        detected a stuck pattern.

        The controller is consulted with the current step's
        ``action`` (for tool+params keying) and the ``observation``
        (for result stability). The plan_progress fingerprint
        comes from the current goal checklist; we use a simple
        hash of the counts to detect "no progress" without
        coupling to a specific plan format.
        """
        if self._homeostasis is None or not self._homeostasis.enabled:
            return None
        observation = step.get("observation")
        # Build a tiny plan_progress fingerprint from the
        # goal checklist. If the checklist is not present, we
        # only check result stability and rescue failure.
        fingerprint: Optional[Dict[str, Any]] = None
        if isinstance(self._goal_checklist, dict):
            counts = self._goal_checklist.get("counts") or {}
            if isinstance(counts, dict):
                fingerprint = {
                    "overall": self._goal_checklist.get("overall"),
                    "done": int(counts.get("done", 0) or 0),
                    "pending": int(counts.get("pending", 0) or 0),
                    "failed": int(counts.get("failed", 0) or 0),
                }
        return self._homeostasis.update(
            step=step,
            observation=observation,
            plan_progress=fingerprint,
            rescue_failed=False,
        )

    def _emit_stuck(self, stuck: Dict[str, Any], iteration: int) -> None:
        """Emit a structured ``loop.stuck`` event so the operator
        and the runtime errors log can see the dead-man's switch
        fire. This is the operator-facing signal of "I am stuck,
        please help."
        """
        # Phase L: surface the stuck event through the error hook
        # so the runtime_errors.jsonl log captures it.
        from core import error_hooks
        error_hooks.fire(
            "vsm",
            message=f"loop stuck: {stuck.get('reason')}",
            severity="critical",
            extra={
                "stuck": stuck,
                "iteration": iteration,
            },
        )
        self._emit(self._session_id, "loop_stuck", {
            "iteration": iteration,
            **stuck,
        })

    def _fsm_transition(self, state, *, iteration: int = -1) -> None:
        """Phase R5: record a transition on the loop FSM and emit
        a ``fsm_state`` event so the evidence bundle can render
        the current state. The runtime flow is unchanged; this is
        observation only.
        """
        from core.loop_fsm import FSMState
        self._fsm.enter(FSMState(state) if not isinstance(state, FSMState) else state)
        self._emit(self._session_id, "fsm_state", {
            "iteration": iteration,
            "state": self._fsm.current.value,
        })

    def _vsm_pre_step(self, iteration: int) -> None:
        """Phase D: VSM pre_step hook. No-op when the shell is inactive."""
        if not self._vsm_shell or not self._vsm_shell.is_active():
            return
        step = {
            "id": f"iter-{iteration}",
            "kind": "tool",
            "vsm_layer": "S1",
        }
        try:
            self._vsm_shell.pre_step(
                step=step,
                plan=self._plan,
                trajectory=self._trajectory,
                policy=None,
                emit=self._emit,
            )
        except Exception:
            return

    def _vsm_post_step(self, step, observation, iteration) -> str:
        """Phase D: VSM post_step hook. Returns the shell's verdict and
        sets ``_vsm_replan_requested`` when the shell asks for re-plan.
        """
        if not self._vsm_shell or not self._vsm_shell.is_active():
            return "continue"
        try:
            verdict = self._vsm_shell.post_step(
                step=step,
                observation=observation or {},
                trajectory=self._trajectory,
                plan=self._plan,
                emit=self._emit,
            )
        except Exception:
            return "continue"
        if verdict == "replan":
            self._vsm_replan_requested = True
        return verdict

    def _collect_think_attachments(
        self, trajectory: List[Dict[str, Any]],
    ) -> tuple[List[Any], str]:
        """Pull image attachments from the most recent observation that
        carried them. Returns ``(images, text_summary)``; ``images`` is
        empty when the last step had no images, and ``text_summary``
        carries a short caption list so even the text-only fallback
        mentions what was on screen."""
        if not trajectory:
            return [], ""
        last = trajectory[-1]
        if not isinstance(last, dict):
            return [], ""
        observation = last.get("observation")
        if not isinstance(observation, dict):
            return [], ""
        content = observation.get("content")
        if not isinstance(content, list) or not content:
            return [], ""
        from llm.content import ImageBlock, TextBlock
        images: List[ImageBlock] = []
        text_lines: List[str] = []
        for block in content:
            if isinstance(block, ImageBlock):
                images.append(block)
                if block.caption:
                    text_lines.append(f"[image: {block.caption}]")
                else:
                    text_lines.append(f"[image: {block.source}]")
            elif isinstance(block, TextBlock) and block.text:
                text_lines.append(block.text)
            elif isinstance(block, dict):
                # Allow pre-serialized blocks in case the trajectory was
                # reconstructed from a JSON session store.
                if block.get("type") == "image" or "source" in block:
                    caption = str(block.get("caption") or "")
                    if caption:
                        text_lines.append(f"[image: {caption}]")
                    try:
                        images.append(ImageBlock(
                            source=str(block.get("source") or ""),
                            media_type=block.get("media_type"),
                            caption=caption,
                        ))
                    except Exception:
                        pass
        return images, "\n".join(text_lines)

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
        # Phase R4: VSMShell S2 anti-oscillation. Disabled tools
        # are filtered from rank_tools here. The blacklist is
        # consulted on every iteration; expired entries are
        # dropped inside ``disabled_tools()``.
        disabled = []
        if self._vsm_shell is not None and self._vsm_shell.is_active():
            disabled = self._vsm_shell.disabled_tools()
        think_tools = self.tools.rank_tools(
            query=f"{self._task}\n{raw_context}",
            limit=10,
            disabled_tools=disabled,
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
                workspace_profile=str(think_rank_stats.get("workspace_profile") or "general"),
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
        # Phase Q1 (multimodal): if the last observation carried image
        # content and the configured LLM supports multimodal, route the
        # think call through ``think_multimodal`` so the model can see
        # what the previous tool produced. Text-only observations and
        # text-only LLMs keep the legacy code path untouched.
        attachments, attachment_text = self._collect_think_attachments(trajectory_for_llm)
        if attachments and getattr(self.llm, "supports_multimodal", False):
            from llm.content import TextBlock
            content_blocks: List[Any] = []
            if prepared_context:
                content_blocks.append(TextBlock(str(prepared_context)))
            if attachment_text:
                content_blocks.append(TextBlock(attachment_text))
            thought = self.llm.think_multimodal(
                task=self._task,
                content=content_blocks,
                trajectory=[],
                tools_description=tools_for_llm,
                attachments=attachments,
            )
            step["think_mode"] = "multimodal"
            step["attachment_count"] = len(attachments)
        else:
            thought = self.llm.think(
                task=self._task,
                context=prepared_context,
                trajectory=trajectory_for_llm,
                tools_description=tools_for_llm,
            )
            step["think_mode"] = "text"
        self._check_cancelled()
        self._emit_latency("llm_think", think_started_at, iteration=iteration)
        self._emit_first_response_latency("thought")
        step["thought"] = thought
        # Phase R1: optionally parse the thought into a structured
        # record. The flag is off by default; when off, the parser
        # is a no-op and the existing free-text path runs unchanged.
        from llm.thought_record import parse_thought_record
        record = parse_thought_record(thought, enabled=self._thought_chain_strict)
        if record is not None and not record.is_empty:
            step["thought_record"] = record.to_dict()
        self._emit(self._session_id, "thought", {"iteration": iteration, "thought": thought})
        self._emit_llm_usage("think")

        # 决定动作：根据刚产生的思考再裁剪一次工具，减少 action prompt 体积和误选概率。
        # Phase R4: same S2 anti-oscillation blacklist; the action
        # phase must not pick a tool the think phase already
        # blacklisted.
        action_tools = self.tools.rank_tools(
            query=f"{self._task}\n{thought}\n{raw_context}",
            limit=8,
            disabled_tools=disabled,
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

    # ------------------------------------------------------------------
    # Plan First
    # ------------------------------------------------------------------

    def _run_plan_first_phase(self, task: str) -> Optional[Dict[str, Any]]:
        result = run_plan_first_phase(
            llm=self.llm,
            tools=self.tools,
            task=task,
            context=self._context,
            session_id=self._session_id,
            emit=self._emit,
            approval_provider=self._plan_approval_provider,
            draft_plan=self._draft_plan_from_llm,
        )
        self._plan = result.plan
        self._plan_review = result.review
        return self._plan if result.approved else None

    def _draft_plan_from_llm(self, task: str) -> Dict[str, Any]:
        return draft_plan_from_llm(
            llm=self.llm,
            tools=self.tools,
            task=task,
            context=self._context,
            session_id=self._session_id,
            emit=self._emit,
        )

    def _known_tool_names(self) -> List[str]:
        return known_tool_names(self.tools)

    def _build_plan_first_result(self, reason: str = "not_approved") -> Dict[str, Any]:
        return build_plan_first_result(
            session_id=self._session_id,
            task=self._task,
            plan=self._plan,
            review=self._plan_review,
            reason=reason,
        )

    def _build_result(self) -> Dict[str, Any]:
        return build_react_result(
            session_id=self._session_id,
            task=self._task,
            trajectory=self._trajectory,
            goal_checklist=self._goal_checklist,
            plan=self._plan,
            plan_review=self._plan_review,
            include_plan=bool(self._plan_first_enabled or self._plan.get("steps")),
        )

    def _summarize(self, result: Dict[str, Any]) -> Dict[str, Any]:
        return summarize_react_result(result)

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
        observation = self.action_execution.execute(self._session_id, tool_name, params)
        return observation

    def takeover(self, expert_llm: LLMInterface, steps: int) -> None:
        """由专家 LLM 接管循环若干轮。"""
        run_expert_takeover(
            expert_llm=expert_llm,
            steps=steps,
            task=self._task,
            session_id=self._session_id,
            trajectory=self._trajectory,
            context=lambda: self._context,
            tools_description=self.tools.schema_for_llm,
            emit=self._emit,
            execute_action=self.action_execution.execute,
            append_context=lambda text: setattr(self, "_context", self._context + text),
            on_step=self._on_step,
        )
