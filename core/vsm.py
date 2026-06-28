"""
core/vsm.py - VSM (Viable System Model) thin adapter.

Phase D. Stafford Beer's S1-S5 vocabulary is used only as a *naming layer*
over existing control surfaces (engineering_control, project_control,
Evidence Bundle, RescueOrchestrator). The shell does **not** create a
parallel control dashboard; every VSM-labeled event flows back into the
existing bus so the rest of the system stays the source of truth.

Mapping (per ADR-0008):
  S1  Operations       - current tool/action execution
  S2  Anti-oscillation - rescue cooldown and repeated-tool detection
  S3  Audit            - plan progress, budget, goal checklist
  S3* Exception        - ControlLoop.verdict == "diverging"
  S4  Strategy         - guarded re-plan or expert rescue
  S5  Policy           - sandbox / profile / approval / runtime contract

Reference: viable-systems.github.io/vsm-docs
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


VSM_VERSION = "vsm-shell.v1"
VSM_LAYERS: frozenset = frozenset({"S1", "S2", "S3", "S3*", "S4", "S5"})

EmitFn = Callable[[str, str, Dict[str, Any]], None]


class VSMShell:
    """Thin VSM adapter. Wired into ReActLoop at every step boundary
    when ``vsm.enabled=true`` in config. Disabled by default.

    Parameters
    ----------
    control_loop : object
        Any object that exposes ``last_signal() -> float`` and
        ``last_verdict() -> str`` (plus ``evaluate(trajectory)``).
        The TTMEvolve ``core.control_loop.ControlLoop`` fits this shape.
    config : dict, optional
        ``enabled`` (bool, default false),
        ``auto_replan`` (bool, default false),
        ``replan_cooldown_steps`` (int, default 3),
        ``max_replan_depth`` (int, default 1),
        ``expert_rescue_on_diverging`` (bool, default true).
    emit : callable, optional
        ``emit(session_id, event_name, payload)`` for observability.
    """

    @classmethod
    def from_config(
        cls,
        config: Any,
        *,
        control_loop: Any = None,
        emit: Optional[EmitFn] = None,
    ) -> Optional["VSMShell"]:
        """Build a VSMShell from a TTMEvolve config object.

        Returns ``None`` when ``vsm.enabled=false`` so callers can
        write ``self._vsm_shell = VSMShell.from_config(cfg)`` and
        the loop's hooks short-circuit naturally.

        ``config`` may be a ``Config`` instance or any object with a
        ``get(key, default)`` method. Unknown keys fall back to
        VSMShell's constructor defaults.
        """
        if config is None:
            return None
        try:
            vsm_cfg = config.get("vsm", {}) if hasattr(config, "get") else {}
        except Exception:
            return None
        if not isinstance(vsm_cfg, dict):
            vsm_cfg = {}
        if not bool(vsm_cfg.get("enabled", False)):
            return None
        if control_loop is None:
            from core.control_loop import ControlLoop
            control_loop = ControlLoop()
        return cls(
            control_loop=control_loop,
            config=vsm_cfg,
            emit=emit,
        )

    def __init__(
        self,
        control_loop: Any,
        config: Optional[Dict[str, Any]] = None,
        emit: Optional[EmitFn] = None,
    ):
        self._control_loop = control_loop
        cfg = dict(config or {})
        self._enabled = bool(cfg.get("enabled", False))
        self._auto_replan = bool(cfg.get("auto_replan", False))
        self._replan_cooldown_steps = int(cfg.get("replan_cooldown_steps", 3))
        self._max_replan_depth = int(cfg.get("max_replan_depth", 1))
        self._expert_rescue_on_diverging = bool(
            cfg.get("expert_rescue_on_diverging", True)
        )
        self._emit = emit
        self._replan_steps_remaining = 0
        self._last_replan_at_step = -10_000
        self._step_counter = 0
        # Phase R4: S2 anti-oscillation. Tools that the shell has
        # blacklisted are filtered from rank_tools until the
        # ``until_iter`` is reached. ``disable_tool`` is the only
        # public write; the shell decides when to call it.
        self._disabled: Dict[str, int] = {}
        # Persistent S3* counter; reset to 0 when we leave the
        # diverging state.
        self._s3_star_run: int = 0
        # Phase R4: S5 policy gate. ``off`` lets the shell write
        # silently. ``audit`` (default for cautious) emits a
        # ``vsm.write_audit`` event for every write. ``cautious``
        # additionally emits a ``policy_check_pending`` event so a
        # future R5 operator-approval flow can hook here.
        self._policy = str(cfg.get("policy", "audit"))
        # Phase R4: persistent S3* counter. When S3* fires this
        # many iterations in a row, the shell calls ``disable_tool``
        # on the offending tool. Three is a conservative threshold.
        self._s3_star_persistence = int(cfg.get("s3_star_persistence", 3))

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def is_active(self) -> bool:
        return self._enabled

    def classify(self, step: Dict[str, Any]) -> str:
        """Return the VSM layer a step belongs to. Defaults to S1."""
        layer = str(step.get("vsm_layer") or "S1")
        if layer not in VSM_LAYERS:
            return "S1"
        return layer

    # ------------------------------------------------------------------
    # Step boundary hooks
    # ------------------------------------------------------------------

    def pre_step(
        self,
        step: Dict[str, Any],
        plan: Dict[str, Any],
        trajectory: List[Dict[str, Any]],
        policy: Optional[Dict[str, Any]] = None,
        emit: Optional[EmitFn] = None,
    ) -> None:
        """Called before each step. Emits S3 audit and S5 policy events
        when the shell is active. Does not block execution.
        """
        if not self._enabled:
            return
        # S5: surface the active policy (sandbox / profile / approval).
        if policy:
            self._emit_event(plan, "vsm_s5_policy", {
                "layer": "S5",
                "step_id": step.get("id"),
                "policy": dict(policy),
            }, emit=emit)
        # S3: audit (plan progress + control signal).
        if hasattr(self._control_loop, "evaluate"):
            try:
                self._control_loop.evaluate(trajectory)
            except Exception:
                pass
        self._step_counter += 1

    def post_step(
        self,
        step: Dict[str, Any],
        observation: Dict[str, Any],
        trajectory: List[Dict[str, Any]],
        plan: Dict[str, Any],
        emit: Optional[EmitFn] = None,
    ) -> str:
        """Called after each step. Returns one of:
          - ``"continue"`` (no action needed)
          - ``"replan"`` (S4 escalation: VSMShell recommends re-plan)
          - ``"needs_action"`` (S3* detected anomaly; runtime may
            trigger expert rescue via the existing RescueTrigger path)
        """
        if not self._enabled:
            return "continue"
        verdict = "stable"
        signal = 0.0
        if hasattr(self._control_loop, "last_verdict"):
            try:
                verdict = self._control_loop.last_verdict()
            except Exception:
                verdict = "stable"
        if hasattr(self._control_loop, "last_signal"):
            try:
                signal = self._control_loop.last_signal()
            except Exception:
                signal = 0.0
        # S3* exception
        if verdict == "diverging":
            self._emit_event(plan, "vsm_s3_star_exception", {
                "layer": "S3*",
                "step_id": step.get("id"),
                "verdict": verdict,
                "signal": signal,
            }, emit=emit)
            # Phase R4: S2 anti-oscillation. When S3* persists for
            # ``s3_star_persistence`` consecutive iterations, the
            # shell disables the current tool. This is the
            # write-action that gives the shell actual control
            # over the loop instead of just observation.
            self._s3_star_run += 1
            if self._s3_star_run >= self._s3_star_persistence:
                action = (step.get("action") or {})
                tool = action.get("tool")
                if tool:
                    self._do_disable_tool(
                        tool,
                        until_iter=self._step_counter
                        + int(self._replan_cooldown_steps),
                        reason="s3_star_persistence",
                    )
                self._s3_star_run = 0
            return self._s4_escalate(step, plan, observation, verdict, signal, emit=emit)
        # S2 anti-oscillation: same step id running too often
        if self._is_repeating(trajectory):
            self._emit_event(plan, "vsm_s2_anti_oscillation", {
                "layer": "S2",
                "step_id": step.get("id"),
                "consecutive_same_step": self._consecutive_same_step(trajectory),
            }, emit=emit)
            # Same-tool-repeat is a different signal from a
            # persistent S3*. Disable after a smaller threshold.
            if self._consecutive_same_step(trajectory) >= 2:
                action = (step.get("action") or {})
                tool = action.get("tool")
                if tool:
                    self._do_disable_tool(
                        tool,
                        until_iter=self._step_counter
                        + int(self._replan_cooldown_steps),
                        reason="s2_repeat",
                    )
        # Reset the S3* counter when we leave the diverging
        # state; persistent divergence is the trigger, not a
        # one-off.
        if self._s3_star_run > 0:
            self._s3_star_run = 0
        return "continue"

    # ------------------------------------------------------------------
    # S4 escalation
    # ------------------------------------------------------------------

    def _s4_escalate(
        self,
        step: Dict[str, Any],
        plan: Dict[str, Any],
        observation: Dict[str, Any],
        verdict: str,
        signal: float,
        emit: Optional[EmitFn] = None,
    ) -> str:
        """S4 decides between re-plan, expert rescue, or needs_action."""
        if self._auto_replan and self._cooldown_allows() and self._replan_depth_available():
            self._replan_steps_remaining += 1
            self._last_replan_at_step = self._step_counter
            self._emit_event(plan, "vsm_s4_replan", {
                "layer": "S4",
                "action": "replan",
                "step_id": step.get("id"),
                "reason": verdict,
                "signal": signal,
            }, emit=emit)
            return "replan"
        if self._expert_rescue_on_diverging:
            self._emit_event(plan, "vsm_s4_expert_rescue", {
                "layer": "S4",
                "action": "expert_rescue",
                "step_id": step.get("id"),
                "reason": verdict,
                "signal": signal,
            }, emit=emit)
            return "needs_action"
        self._emit_event(plan, "vsm_s4_watch", {
            "layer": "S4",
            "action": "watch",
            "step_id": step.get("id"),
            "reason": verdict,
            "signal": signal,
        }, emit=emit)
        return "needs_action"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cooldown_allows(self) -> bool:
        return (self._step_counter - self._last_replan_at_step) >= self._replan_cooldown_steps

    def _replan_depth_available(self) -> bool:
        return self._replan_steps_remaining <= self._max_replan_depth

    def _is_repeating(self, trajectory: List[Dict[str, Any]]) -> bool:
        return self._consecutive_same_step(trajectory) >= 2

    def _consecutive_same_step(self, trajectory: List[Dict[str, Any]]) -> int:
        if not trajectory:
            return 0
        last_id = (trajectory[-1].get("step_id")
                   or trajectory[-1].get("action", {}).get("tool"))
        if not last_id:
            return 0
        count = 0
        for step in reversed(trajectory):
            sid = (step.get("step_id")
                   or step.get("action", {}).get("tool"))
            if sid == last_id:
                count += 1
            else:
                break
        return count

    # ------------------------------------------------------------------
    # Phase R4: S2 writes — disable_tool + is_tool_disabled
    # ------------------------------------------------------------------

    def disable_tool(
        self,
        name: str,
        *,
        until_iter: Optional[int] = None,
        reason: str = "vsm_decision",
    ) -> bool:
        """Public S2 write. Filter the tool from rank_tools until
        ``until_iter``. If ``until_iter`` is ``None``, the cooldown
        length defaults to ``replan_cooldown_steps``.
        Returns True if the write was actually applied.
        """
        if not self._enabled:
            return False
        if not name:
            return False
        if until_iter is None:
            until_iter = self._step_counter + int(self._replan_cooldown_steps)
        return self._do_disable_tool(
            name, until_iter=int(until_iter), reason=reason,
        )

    def _do_disable_tool(
        self,
        name: str,
        *,
        until_iter: int,
        reason: str,
    ) -> bool:
        # Policy gate: ``off`` lets writes pass; ``audit`` emits a
        # ``vsm.write_audit`` event; ``cautious`` additionally emits
        # ``policy_check_pending`` so a future R5 operator-approval
        # flow can hook here. The write itself always happens
        # because the shell is the only writer and a stuck tool is
        # worse than a gated write.
        already = self._disabled.get(name)
        new_until = max(int(until_iter), int(already or 0))
        self._disabled[name] = new_until
        if self._policy in {"audit", "cautious"}:
            self._emit_event(None, "vsm_write_audit", {
                "layer": "S2",
                "action": "disable_tool",
                "tool": name,
                "until_iter": new_until,
                "reason": reason,
                "policy": self._policy,
            })
        if self._policy == "cautious":
            self._emit_event(None, "policy_check_pending", {
                "layer": "S5",
                "action": "disable_tool",
                "tool": name,
                "until_iter": new_until,
            })
        return True

    def is_tool_disabled(self, name: str) -> bool:
        """Return True if the tool is currently blacklisted. The
        blacklist expires when ``self._step_counter`` passes
        ``until_iter``.
        """
        if not self._enabled:
            return False
        until = self._disabled.get(name)
        if until is None:
            return False
        if self._step_counter >= until:
            # Expired; clean up.
            del self._disabled[name]
            return False
        return True

    def disabled_tools(self) -> List[str]:
        """Return a snapshot of the currently blacklisted tool names."""
        if not self._enabled:
            return []
        # Drop expired entries.
        expired = [
            n for n, u in self._disabled.items()
            if self._step_counter >= u
        ]
        for n in expired:
            del self._disabled[n]
        return list(self._disabled.keys())

    def _emit_event(self, plan, name, payload, emit: Optional[EmitFn] = None):
        emit_fn = emit or self._emit
        if not emit_fn:
            return
        try:
            session_id = ""
            if isinstance(plan, dict):
                session_id = str(plan.get("_session_id") or "")
            emit_fn(session_id, name, payload)
        except Exception:
            return
