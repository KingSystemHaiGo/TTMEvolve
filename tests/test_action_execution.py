from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.action_execution import (
    ActionExecutionService,
    tail_text,
    tool_timeout_context_hint,
    validation_context_hint,
    validation_observation,
)


class _Tools:
    def __init__(self, validation=None):
        self.validation = validation or {"ok": True}

    def has(self, tool_name):
        return tool_name != "missing_tool"

    def validate_action(self, tool_name, params):
        return self.validation


class _Executor:
    def __init__(self):
        self.calls = []

    def propose_action(self, session_id, tool_name, params):
        self.calls.append((session_id, tool_name, params))
        return {"ok": True, "tool": tool_name, "params": params}


def _validation():
    return {
        "ok": False,
        "errors": ["missing required parameter 'path'"],
        "structured_errors": [
            {
                "rule_id": "missing_required",
                "path": "read_file().path",
                "reason": "path is required",
                "suggested_fix": "Add params.path.",
            }
        ],
        "alternatives": [{"tool": "project_status"}],
        "suggested_next_step": "Add params.path.",
    }


def test_validation_observation_preserves_machine_readable_fields():
    observation = validation_observation("read_file", _validation())

    assert observation["failure_type"] == "tool_validation"
    assert observation["rule_id"] == "missing_required"
    assert observation["path"] == "read_file().path"
    assert observation["suggested_fix"] == "Add params.path."
    assert observation["alternatives"] == [{"tool": "project_status"}]
    assert observation["suggested_next_step"] == "Add params.path."


def test_validation_context_hint_is_parseable_json():
    hint = validation_context_hint("read_file", _validation())
    payload = json.loads(hint.split("\n")[2])

    assert payload["failure_type"] == "tool_validation"
    assert payload["tool"] == "read_file"
    assert payload["errors"][0]["rule_id"] == "missing_required"


def test_execute_rejects_unknown_and_invalid_tools_before_executor():
    executor = _Executor()
    unknown = ActionExecutionService(tools=_Tools(), executor=executor).execute("s1", "missing_tool", {})
    invalid = ActionExecutionService(
        tools=_Tools(validation=_validation()),
        executor=executor,
    ).execute("s1", "read_file", {})

    assert unknown["ok"] is False
    assert "does not exist" in unknown["error"]
    assert invalid["failure_type"] == "tool_validation"
    assert executor.calls == []


def test_execute_calls_executor_after_validation_passes():
    executor = _Executor()
    service = ActionExecutionService(tools=_Tools(), executor=executor)

    result = service.execute("s1", "read_file", {"path": "a.txt"})

    assert result["ok"] is True
    assert executor.calls == [("s1", "read_file", {"path": "a.txt"})]


def test_execute_with_progress_emits_heartbeat_before_result():
    class SlowExecutor(_Executor):
        def propose_action(self, session_id, tool_name, params):
            time.sleep(0.16)
            return super().propose_action(session_id, tool_name, params)

    events = []
    service = ActionExecutionService(
        tools=_Tools(),
        executor=SlowExecutor(),
        emit=lambda session_id, event_type, payload: events.append({
            "session_id": session_id,
            "type": event_type,
            "payload": payload,
        }),
        progress_interval_seconds=0.05,
    )

    result = service.execute_with_progress(
        "s1",
        "slow_tool",
        {},
        iteration=2,
        started_at=time.perf_counter(),
    )

    assert result["ok"] is True
    assert events
    assert events[0]["type"] == "tool_progress"
    assert events[0]["payload"]["iteration"] == 2
    assert events[0]["payload"]["partial"] is True


def test_reconcile_uncertain_commit_emits_check_and_result():
    class ReconcileExecutor(_Executor):
        def reconcile_commit_state(self, observation):
            return {
                **observation,
                "committed": True,
                "reconcile_status": "verified_local",
            }

    events = []
    service = ActionExecutionService(
        tools=_Tools(),
        executor=ReconcileExecutor(),
        emit=lambda session_id, event_type, payload: events.append((session_id, event_type, payload)),
    )
    observation = {
        "ok": False,
        "idempotency_key": "s1:tool:1",
        "committed": None,
    }

    result = service.reconcile_if_uncertain_commit("s1", 0, "tool", observation)

    assert result["committed"] is True
    assert result["reconcile_status"] == "verified_local"
    assert [event[1] for event in events] == ["commit_reconcile", "commit_reconcile"]
    assert events[-1][2]["committed"] is True


def test_timeout_context_hint_trims_large_output():
    hint = tool_timeout_context_hint(
        "shell",
        {
            "elapsed_ms": 2000,
            "timeout_seconds": 1,
            "partial": True,
            "stdout": "x" * 1305,
            "stderr": None,
        },
    )
    payload = json.loads(hint.split("\n")[2])

    assert payload["failure_type"] == "tool_timeout"
    assert len(payload["stdout_tail"]) == 1200
    assert tail_text("abcdef", limit=3) == "def"
