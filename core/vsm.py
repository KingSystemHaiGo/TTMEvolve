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
            return self._s4_escalate(step, plan, observation, verdict, signal, emit=emit)
        # S2 anti-oscillation: same step id running too often
        if self._is_repeating(trajectory):
            self._emit_event(plan, "vsm_s2_anti_oscillation", {
                "layer": "S2",
                "step_id": step.get("id"),
                "consecutive_same_step": self._consecutive_same_step(trajectory),
            }, emit=emit)
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

    def _emit_event(self, plan, name, payload, emit: Optional[EmitFn] = None):
        emit_fn = emit or self._emit
        if not emit_fn:
            return
        try:
            emit_fn(str(plan.get("_session_id") or ""), name, payload)
        except Exception:
            return
