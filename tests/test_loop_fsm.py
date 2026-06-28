"""
tests/test_loop_fsm.py - explicit FSM tests (Phase R5).

Covers:
  - FSMState enum values
  - can_transition legality
  - LoopFSM.enter / snapshot / check_timeout
  - The five-state flow OBSERVE -> ORIENT -> DECIDE -> ACT -> REFLECT
    round-trips and produces a non-empty history.
  - STUCK and DONE are terminal.
  - Illegal transitions are still recorded (operator must see them)
    but flagged with ``illegal=True``.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.loop_fsm import (  # noqa: E402
    FSMState,
    LOOP_FSM_VERSION,
    LoopFSM,
    can_transition,
)


# ---------------------------------------------------------------------------
# State / transition legality
# ---------------------------------------------------------------------------

def test_states_match_redesign_doc():
    assert FSMState.OBSERVE.value == "OBSERVE"
    assert FSMState.ORIENT.value == "ORIENT"
    assert FSMState.DECIDE.value == "DECIDE"
    assert FSMState.ACT.value == "ACT"
    assert FSMState.REFLECT.value == "REFLECT"
    assert FSMState.DONE.value == "DONE"
    assert FSMState.STUCK.value == "STUCK"


def test_main_loop_legal_transitions():
    assert can_transition(FSMState.OBSERVE, FSMState.ORIENT)
    assert can_transition(FSMState.ORIENT, FSMState.DECIDE)
    assert can_transition(FSMState.DECIDE, FSMState.ACT)
    assert can_transition(FSMState.ACT, FSMState.REFLECT)
    assert can_transition(FSMState.REFLECT, FSMState.OBSERVE)
    assert can_transition(FSMState.REFLECT, FSMState.DONE)
    assert can_transition(FSMState.REFLECT, FSMState.STUCK)


def test_terminal_states_have_no_transitions():
    for src in (FSMState.DONE, FSMState.STUCK):
        for dst in FSMState:
            assert not can_transition(src, dst), (
                f"{src} should not transition to {dst}"
            )


def test_illegal_jump_recorded_with_flag():
    """Even illegal transitions are recorded, with a flag so the
    operator can see them. R5 is observable, not enforcing.
    """
    fsm = LoopFSM()
    fsm.enter(FSMState.OBSERVE)
    fsm.enter(FSMState.ORIENT)
    # ACT -> OBSERVE is illegal (must go through REFLECT)
    fsm.enter(FSMState.ACT)
    fsm.enter(FSMState.OBSERVE)
    snap = fsm.snapshot()
    # The last entry is marked illegal
    illegal_entries = [e for e in snap["recent_transitions"] if e.get("illegal")]
    assert any(
        e.get("from") == "ACT" and e.get("to") == "OBSERVE"
        for e in illegal_entries
    )


# ---------------------------------------------------------------------------
# LoopFSM
# ---------------------------------------------------------------------------

def test_fsm_initial_state_is_observe():
    fsm = LoopFSM()
    assert fsm.current == FSMState.OBSERVE


def test_fsm_full_round_trip_records_each_transition():
    fsm = LoopFSM()
    # Round trip: enter through the main flow and back to OBSERVE.
    # Note: the first call (enter OBSERVE when already in OBSERVE)
    # is recorded as an illegal transition so the operator sees it.
    flow = [
        FSMState.OBSERVE,  # illegal (OBSERVE -> OBSERVE); operator sees this
        FSMState.ORIENT,
        FSMState.DECIDE,
        FSMState.ACT,
        FSMState.REFLECT,
        FSMState.OBSERVE,  # loop back
    ]
    for s in flow:
        fsm.enter(s)
    snap = fsm.snapshot()
    assert snap["current_state"] == "OBSERVE"
    # 5 legal transitions + 1 illegal entry at the start
    legal = [t for t in snap["recent_transitions"] if not t.get("illegal")]
    illegal = [t for t in snap["recent_transitions"] if t.get("illegal")]
    assert len(legal) == 5
    assert len(illegal) == 1
    # Each legal entry has from / to / elapsed_s / at
    for t in legal:
        assert "from" in t
        assert "to" in t
        assert "elapsed_s" in t


def test_fsm_snapshot_is_serdeable():
    """The snapshot must be JSON-serializable so the evidence
    bundle can render it.
    """
    import json
    fsm = LoopFSM()
    fsm.enter(FSMState.ORIENT)
    snap = fsm.snapshot()
    json.dumps(snap)
    assert snap["schema_version"] == LOOP_FSM_VERSION


def test_fsm_check_timeout_returns_current_state_when_overrun():
    fsm = LoopFSM(timeouts={FSMState.OBSERVE: 0.001})
    fsm.enter(FSMState.OBSERVE)
    # Wait past the budget
    time.sleep(0.05)
    assert fsm.check_timeout() == FSMState.OBSERVE


def test_fsm_check_timeout_returns_none_when_within_budget():
    fsm = LoopFSM()
    fsm.enter(FSMState.OBSERVE)
    assert fsm.check_timeout() is None


def test_fsm_check_timeout_returns_none_for_terminal_states():
    fsm = LoopFSM()
    fsm.enter(FSMState.OBSERVE)
    fsm.enter(FSMState.ORIENT)
    fsm.enter(FSMState.DECIDE)
    fsm.enter(FSMState.ACT)
    fsm.enter(FSMState.REFLECT)
    fsm.enter(FSMState.DONE)
    assert fsm.check_timeout() is None


def test_fsm_history_respects_limit():
    fsm = LoopFSM(history_limit=4)
    # Cycle OBSERVE -> REFLECT 10 times. The history has at most 4 entries.
    for _ in range(10):
        fsm.enter(FSMState.OBSERVE)
        fsm.enter(FSMState.REFLECT)
    snap = fsm.snapshot()
    assert len(snap["recent_transitions"]) <= 4
