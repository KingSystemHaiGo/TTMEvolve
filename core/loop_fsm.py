"""
core/loop_fsm.py - explicit sense-compare-decide-act FSM (Phase R5).

The ReAct loop's main iteration has always been logically an FSM:
the loop collects state (OBSERVE), reasons about the situation
(ORIENT), picks an action (DECIDE), executes it (ACT), and
records the outcome (REFLECT). R5 makes that state machine
explicit so the operator can see "what is the agent doing right
now" via the evidence bundle.

This module is a **declaration**, not a refactor. The existing
``_run_iteration`` and main loop are annotated with FSMState
values; the runtime flow is unchanged. R5 is observable, not
structural.

Five named states, per the redesign doc:
  - OBSERVE    - collect trajectory, observation, control signal
  - ORIENT     - update self-model (plan_progress, tool_state, budget)
  - DECIDE     - choose next action (or stuck/dead-man/ask-user)
  - ACT        - execute the chosen action
  - REFLECT    - score the action's outcome, update homeostasis

Each state has a soft timeout: a transition that does not
complete within the budget emits a homeostasis event. The
default timeouts are wide enough that they only fire on a real
hang.
"""

from __future__ import annotations

import time
from collections import deque
from enum import Enum
from typing import Any, Deque, Dict, Optional


LOOP_FSM_VERSION = "loop-fsm.v1"


class FSMState(str, Enum):
    OBSERVE = "OBSERVE"
    ORIENT = "ORIENT"
    DECIDE = "DECIDE"
    ACT = "ACT"
    REFLECT = "REFLECT"

    # Terminal states the loop can be in.
    DONE = "DONE"
    STUCK = "STUCK"


# Allowed transitions. The loop's main flow is OBSERVE -> ORIENT
# -> DECIDE -> ACT -> REFLECT -> (loop). Branching into STUCK or
# DONE happens from REFLECT.
_ALLOWED: Dict[FSMState, set] = {
    FSMState.OBSERVE: {FSMState.ORIENT, FSMState.STUCK},
    FSMState.ORIENT: {FSMState.DECIDE, FSMState.STUCK},
    FSMState.DECIDE: {FSMState.ACT, FSMState.STUCK},
    FSMState.ACT: {FSMState.REFLECT, FSMState.STUCK},
    FSMState.REFLECT: {FSMState.OBSERVE, FSMState.DONE, FSMState.STUCK},
    FSMState.DONE: set(),
    FSMState.STUCK: set(),
}


# Per-state default timeouts (seconds). Wide enough that a normal
# iteration completes in a small fraction of this. A real hang
# (e.g. LLM provider stuck) trips the budget.
DEFAULT_TIMEOUTS_S: Dict[FSMState, float] = {
    FSMState.OBSERVE: 5.0,
    FSMState.ORIENT: 5.0,
    FSMState.DECIDE: 60.0,
    FSMState.ACT: 60.0,
    FSMState.REFLECT: 5.0,
}


def can_transition(src: FSMState, dst: FSMState) -> bool:
    """Return True if ``src -> dst`` is a legal transition."""
    return dst in _ALLOWED.get(src, set())


class LoopFSM:
    """Tracks the current FSM state and recent transitions.

    The runtime flow does not pass through this class; instead the
    main loop calls ``enter(state)`` and ``exit(state)`` to record
    transitions. The evidence bundle reads the snapshot to render
    the fsm block.
    """

    def __init__(
        self,
        *,
        timeouts: Optional[Dict[FSMState, float]] = None,
        history_limit: int = 64,
    ):
        self._timeouts = dict(DEFAULT_TIMEOUTS_S)
        if timeouts:
            self._timeouts.update(timeouts)
        # No minimum on history_limit. The deque maxlen is
        # whatever the caller asked for; the test suite uses
        # small values (4) to verify truncation.
        self._history_limit = max(1, int(history_limit))
        self._current: FSMState = FSMState.OBSERVE
        self._current_entered_at: float = 0.0
        self._history: Deque[Dict[str, Any]] = deque(maxlen=self._history_limit)

    @property
    def current(self) -> FSMState:
        return self._current

    def enter(self, state: FSMState) -> None:
        """Mark ``state`` as the current state and record the
        transition. The previous state's elapsed time is appended
        to the history.
        """
        now = time.time()
        if self._current_entered_at:
            self._history.append({
                "from": self._current.value,
                "to": state.value,
                "elapsed_s": round(now - self._current_entered_at, 4),
                "at": now,
            })
        if not can_transition(self._current, state):
            # The transition is illegal. We still record it (the
            # operator needs to know) but mark it with a flag.
            self._history.append({
                "illegal": True,
                "from": self._current.value,
                "to": state.value,
            })
        self._current = state
        self._current_entered_at = now

    def check_timeout(self) -> Optional[FSMState]:
        """Return the current state if its timeout has elapsed,
        else None. Callers emit a homeostasis event for the
        returned state.
        """
        if not self._current_entered_at:
            return None
        if self._current in (FSMState.DONE, FSMState.STUCK):
            return None
        budget = self._timeouts.get(self._current, 60.0)
        if time.time() - self._current_entered_at > float(budget):
            return self._current
        return None

    def snapshot(self) -> Dict[str, Any]:
        """Render a compact view for the evidence bundle."""
        recent = list(self._history)[-8:]
        return {
            "schema_version": LOOP_FSM_VERSION,
            "current_state": self._current.value,
            "recent_transitions": recent,
        }
