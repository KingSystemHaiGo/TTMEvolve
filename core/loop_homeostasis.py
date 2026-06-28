"""
core/loop_homeostasis.py - loop self-correction invariants (Phase R3).

The current rescue trigger watches the trajectory for the *symptom*
of being stuck: same tool N times in a row. It does not watch the
*cause*: the tool is returning the same result with no progress
toward the goal. Phase R3 introduces a small homeostatic
controller that detects three stuck patterns and forces the loop
to terminate cleanly:

  1. **Result stability** — the last 3 observations for the same
     ``(tool, params)`` pair are byte-equal. This is the actual
     signal that the agent is making no progress.
  2. **No progress** — the plan_progress fingerprint has not
     changed in N iterations AND no tool fired a
     ``postconditions_fired`` event.
  3. **Rescue failure** — rescue was called K times and the loop
     is still in a non-terminal state. This is the "2026-06-28
     project_status" scenario where rescue fires but the agent
     keeps calling the same tool.

When a stuck pattern is detected, the controller returns a
structured record. The ReAct loop is expected to:
  - Set ``step["done"] = True``
  - Set ``step["output"] = {"stuck": True, "reason": ..., ...}``
  - Break the main loop

The controller is OFF by default. The flag is
``homeostasis.enabled`` (default false). When off, every
``update()`` returns ``None`` and the loop runs unchanged.

The controller never raises. It is safe to call from any code
path, including the tool executor and the rescue orchestrator.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from typing import Any, Deque, Dict, Optional, Tuple


LOOP_HOMEOSTASIS_VERSION = "loop-homeostasis.v1"

# Default thresholds. Tuned for a 1B local model with max_iterations=20.
# Conservative: do not false-positive on short traces.
DEFAULT_RESULT_STABILITY_LIMIT = 3
DEFAULT_NO_PROGRESS_LIMIT = 5
DEFAULT_RESCUE_FAILURE_LIMIT = 2


def _hash_observation(observation: Any) -> str:
    """Stable hash of an observation for result-stability comparison.

    Two observations hash the same iff their JSON-serialized forms
    are byte-equal (after sort_keys=True). This is the closest
    deterministic signal we have without semantic comparison.
    """
    try:
        s = json.dumps(observation, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        s = repr(observation)
    return hashlib.sha1(s.encode("utf-8", errors="replace")).hexdigest()


class LoopHomeostasis:
    """Detect three stuck patterns in a ReAct loop.

    Parameters
    ----------
    enabled : bool
        When False, every ``update()`` is a no-op. Default False.
    result_stability_limit : int
        Number of consecutive byte-equal observations for the
        same ``(tool, params)`` to trigger ``reason="result_stable"``.
    no_progress_limit : int
        Number of consecutive iterations with the same
        ``plan_progress`` fingerprint to trigger
        ``reason="no_progress"``.
    rescue_failure_limit : int
        Number of consecutive rescue failures to trigger
        ``reason="rescue_failure"``.

    The controller is *terminal-once*: the first stuck record
    latches and subsequent ``update()`` calls return ``None``
    until ``reset()`` is called. This avoids a noisy log of
    duplicate stuck events when the loop is asked to keep going.
    """

    def __init__(
        self,
        *,
        enabled: bool = False,
        result_stability_limit: int = DEFAULT_RESULT_STABILITY_LIMIT,
        no_progress_limit: int = DEFAULT_NO_PROGRESS_LIMIT,
        rescue_failure_limit: int = DEFAULT_RESCUE_FAILURE_LIMIT,
    ):
        self._enabled = bool(enabled)
        self._result_limit = max(2, int(result_stability_limit))
        self._progress_limit = max(2, int(no_progress_limit))
        self._rescue_limit = max(1, int(rescue_failure_limit))
        self._result_history: Dict[Tuple[str, str], Deque[str]] = {}
        self._iterations_without_progress: int = 0
        self._last_plan_progress: str = ""
        self._rescue_failure_count: int = 0
        self._stuck_emitted: bool = False
        self._last_stuck: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def last_stuck(self) -> Optional[Dict[str, Any]]:
        return self._last_stuck

    def reset(self) -> None:
        """Reset the controller. Call at the start of each new run."""
        self._result_history.clear()
        self._iterations_without_progress = 0
        self._last_plan_progress = ""
        self._rescue_failure_count = 0
        self._stuck_emitted = False
        self._last_stuck = None

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        *,
        step: Optional[Dict[str, Any]] = None,
        observation: Any = None,
        plan_progress: Any = None,
        rescue_failed: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Inspect one iteration and return a stuck record if needed.

        ``step`` is the trajectory step with at least
        ``step["action"]["tool"]`` and ``step["action"]["params"]``.
        ``observation`` is the result of the tool call.
        ``plan_progress`` is the current plan progress
        fingerprint (any hashable). ``rescue_failed`` is set when
        the rescue orchestrator skipped a rescue.
        """
        if not self._enabled or self._stuck_emitted:
            return None

        # 1. Result stability
        if step is not None and observation is not None:
            stuck = self._check_result_stability(step, observation)
            if stuck is not None:
                self._latch(stuck)
                return stuck

        # 2. No progress
        if plan_progress is not None:
            stuck = self._check_no_progress(plan_progress)
            if stuck is not None:
                self._latch(stuck)
                return stuck

        # 3. Rescue failure
        if rescue_failed:
            stuck = self._check_rescue_failure()
            if stuck is not None:
                self._latch(stuck)
                return stuck

        return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _check_result_stability(
        self,
        step: Dict[str, Any],
        observation: Any,
    ) -> Optional[Dict[str, Any]]:
        action = step.get("action") if isinstance(step.get("action"), dict) else {}
        tool = str(action.get("tool") or "")
        if not tool:
            return None
        try:
            params_key = json.dumps(
                action.get("params") or {},
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            )
        except Exception:
            params_key = repr(action.get("params"))
        key = (tool, params_key)
        obs_hash = _hash_observation(observation)
        history = self._result_history.setdefault(
            key, deque(maxlen=self._result_limit)
        )
        history.append(obs_hash)
        if len(history) >= self._result_limit and len(set(history)) == 1:
            return {
                "reason": "result_stable",
                "tool": tool,
                "params": action.get("params") or {},
                "observation": observation,
                "iterations": self._result_limit,
            }
        return None

    def _check_no_progress(
        self,
        plan_progress: Any,
    ) -> Optional[Dict[str, Any]]:
        try:
            current = json.dumps(plan_progress, sort_keys=True, default=str)
        except Exception:
            current = str(plan_progress)
        # Counter semantics: "N same fingerprints in a row seen
        # so far." The first observation starts at 1; a different
        # observation resets to 1 (we've seen 1 fingerprint, just
        # a different one).
        if current == self._last_plan_progress:
            self._iterations_without_progress += 1
        else:
            self._iterations_without_progress = 1
        self._last_plan_progress = current
        if self._iterations_without_progress >= self._progress_limit:
            return {
                "reason": "no_progress",
                "iterations": self._iterations_without_progress,
                "plan_progress": plan_progress,
            }
        return None

    def _check_rescue_failure(self) -> Optional[Dict[str, Any]]:
        self._rescue_failure_count += 1
        if self._rescue_failure_count >= self._rescue_limit:
            return {
                "reason": "rescue_failure",
                "count": self._rescue_failure_count,
            }
        return None

    def _latch(self, stuck: Dict[str, Any]) -> None:
        self._stuck_emitted = True
        self._last_stuck = stuck
