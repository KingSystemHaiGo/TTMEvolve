"""PID-style control loop for Agent self-correction (Ima 之五).

The agent monitors its own trajectory and gently steers itself back on track
when:
- repeated failures (raise the proportional term)
- rapid plan validation flips (raise the integral term)
- recovery stalls (add derivative damping)

The controller exposes a single `evaluate(trajectory)` method that returns
a control signal — a small dict the host can read to decide whether to
slow down, switch tools, or escalate to a higher-tier model.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from . import error_hooks


CONTROL_LOOP_VERSION = "control-loop.v1"


class ControlLoop:
    """Tiny PID controller for Agent self-correction."""

    def __init__(
        self,
        *,
        kp: float = 0.4,
        ki: float = 0.2,
        kd: float = 0.1,
        history_window: int = 6,
        repeat_threshold: int = 2,
        integral_decay: float = 0.9,
        integral_max: float = 20.0,
    ) -> None:
        if history_window <= 0:
            raise ValueError("history_window must be > 0")
        if repeat_threshold <= 0:
            raise ValueError("repeat_threshold must be > 0")
        if not (0.0 <= integral_decay <= 1.0):
            raise ValueError("integral_decay must be in [0, 1]")
        if integral_max <= 0:
            raise ValueError("integral_max must be > 0")
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)
        self.history_window = int(history_window)
        self.repeat_threshold = int(repeat_threshold)
        self.integral_decay = float(integral_decay)
        self.integral_max = float(integral_max)
        self._integral = 0.0
        self._last_error = 0.0

    def reset(self) -> None:
        self._integral = 0.0
        self._last_error = 0.0

    def evaluate(self, trajectory: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Inspect the recent trajectory and return a control signal.

        Output shape:
        {
            "version": ...,
            "signal": float,         # higher = more urgent, agent should slow/escalate
            "verdict": "stable" | "drift" | "diverging",
            "recommendation": "<human-readable next-step hint>",
            "stats": {...},
        }
        """
        window = trajectory[-self.history_window:] if trajectory else []
        error = self._error(window)
        # Apply decay before adding so transient failures bleed off; clamp to
        # integral_max so the controller never "ratchets" to diverging forever.
        self._integral = self._integral * self.integral_decay + error
        self._integral = max(-self.integral_max, min(self.integral_max, self._integral))
        derivative = error - self._last_error
        self._last_error = error
        signal = self.kp * error + self.ki * self._integral + self.kd * derivative
        verdict = self._verdict(error, signal)
        # Phase D: persist the latest values for VSMShell / external
        # consumers that read the loop state outside the call site.
        self._last_signal = round(signal, 4)
        self._last_verdict = verdict
        self._last_evaluated_at = time.time()
        # Phase L: surface a diverging verdict through the error
        # hooks. Stable and drift verdicts are not errors; the
        # agent is "stuck" when this fires repeatedly.
        if verdict == "diverging":
            fails = sum(
                1 for s in window
                if isinstance(s.get("observation"), dict)
                and s["observation"].get("ok") is False
            )
            error_hooks.fire(
                "vsm",
                message=f"control loop diverging (signal={self._last_signal})",
                severity="critical",
                extra={
                    "verdict": verdict,
                    "signal": self._last_signal,
                    "failures_in_window": int(fails),
                },
            )
        return {
            "version": CONTROL_LOOP_VERSION,
            "signal": round(signal, 4),
            "error": round(error, 4),
            "integral": round(self._integral, 4),
            "derivative": round(derivative, 4),
            "verdict": verdict,
            "recommendation": self._recommend(verdict, window),
            "stats": self._stats(window),
        }

    def last_signal(self) -> float:
        """Return the most recent control signal. ``0.0`` before any
        ``evaluate()`` call."""
        return float(getattr(self, "_last_signal", 0.0))

    def last_verdict(self) -> str:
        """Return the most recent verdict. ``"stable"`` before any
        ``evaluate()`` call (a safe default for S3* consumers)."""
        return str(getattr(self, "_last_verdict", "stable"))

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _error(self, window: List[Dict[str, Any]]) -> float:
        if not window:
            return 0.0
        repeats = 0
        failures = 0
        tool_count: Dict[str, int] = {}
        for step in window:
            action = step.get("action") if isinstance(step.get("action"), dict) else {}
            observation = step.get("observation") if isinstance(step.get("observation"), dict) else {}
            plan_validation = observation.get("plan_validation") if isinstance(observation.get("plan_validation"), dict) else None
            tool = action.get("tool")
            ok = observation.get("ok")
            if ok is False:
                failures += 1
            if tool:
                tool_count[tool] = tool_count.get(tool, 0) + 1
        repeats = sum(count for count in tool_count.values() if count >= self.repeat_threshold)
        # Error score: failures + repeats, weighted
        return float(failures) + 0.5 * float(repeats)

    def _stats(self, window: List[Dict[str, Any]]) -> Dict[str, Any]:
        tool_count: Dict[str, int] = {}
        ok_count = 0
        fail_count = 0
        for step in window:
            action = step.get("action") if isinstance(step.get("action"), dict) else {}
            observation = step.get("observation") if isinstance(step.get("observation"), dict) else {}
            tool = str(action.get("tool") or "")
            if tool:
                tool_count[tool] = tool_count.get(tool, 0) + 1
            if observation.get("ok") is True:
                ok_count += 1
            elif observation.get("ok") is False:
                fail_count += 1
        return {
            "window_size": len(window),
            "ok_count": ok_count,
            "fail_count": fail_count,
            "tool_count": tool_count,
        }

    def _verdict(self, error: float, signal: float) -> str:
        if error <= 1.0 and signal < 1.0:
            return "stable"
        if error <= 3.0 and signal < 3.0:
            return "drift"
        return "diverging"

    def _recommend(self, verdict: str, window: List[Dict[str, Any]]) -> str:
        if verdict == "stable":
            return "Continue with the current plan."
        if verdict == "drift":
            tool = self._most_repeated_tool(window)
            if tool:
                return (
                    f"Drift detected — the agent is repeating tool '{tool}'. "
                    "Consider switching strategy or fetching a hint."
                )
            return "Drift detected — pause and re-evaluate the plan."
        return (
            "Diverging trajectory — multiple failures or loops. "
            "Suggest recovery: roll back last step, switch tool, or escalate to expert model."
        )

    def _most_repeated_tool(self, window: List[Dict[str, Any]]) -> str:
        counts: Dict[str, int] = {}
        for step in window:
            action = step.get("action") if isinstance(step.get("action"), dict) else {}
            tool = str(action.get("tool") or "")
            if tool:
                counts[tool] = counts.get(tool, 0) + 1
        if not counts:
            return ""
        # Sort by (-count, name) so ties resolve deterministically to the
        # lexicographically smallest tool name.
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]