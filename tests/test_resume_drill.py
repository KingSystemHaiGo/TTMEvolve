from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from server.resume_drill import build_resume_drill_report
from server.session_store import SessionStore


def _checkpoint_event() -> dict:
    return {
        "iteration": 6,
        "reason": "scheduled",
        "revision": 3,
        "changed": True,
        "signature": "resume-sig",
        "snapshot": {
            "session_id": "resume1",
            "task": "optimize long task continuity",
            "workspace_profile": "coding",
            "continuation_checkpoint": {
                "version": "continuation-checkpoint.v1",
                "context_revision": 3,
                "workspace_profile": "coding",
                "resume_ready": True,
                "resume_mode": "context_handoff",
                "open_plan_steps": [
                    {"id": "verify", "title": "Run restart drill", "status": "pending", "tool": "pytest"}
                ],
                "goal_next_focus": "Run restart drill",
                "goal_overall": "active",
                "last_tool": "modify_file",
                "last_ok": True,
                "plan_verdict": "pass",
                "artifact_count": 1,
                "artifact_refs": [{"path": "server/resume_drill.py", "tool": "modify_file"}],
                "compression": {
                    "needed": True,
                    "version": "trajectory-compression.v1",
                    "compressed_step_count": 4,
                    "skipped_step_count": 0,
                    "summary": "Task: optimize long task continuity",
                },
                "resume_limits": {
                    "process_resurrection": False,
                    "requires_runtime_replay": False,
                    "raw_sse_replay_required": False,
                },
            },
        },
    }


def test_resume_drill_recovers_from_reopened_session_store(tmp_path: Path):
    db_path = tmp_path / "sessions.db"
    store = SessionStore(db_path)
    store.create_session("resume1", "optimize long task continuity")
    store.append_event("resume1", "context_sync", _checkpoint_event())
    store.append_event(
        "resume1",
        "observation",
        {
            "iteration": 6,
            "tool": "modify_file",
            "observation": {"ok": True, "tool": "modify_file", "path": "server/resume_drill.py"},
        },
    )

    reopened = SessionStore(db_path)
    report = build_resume_drill_report(
        session_id="resume1",
        stored_session=reopened.get_session("resume1"),
        context_history=reopened.get_context_sync_history("resume1", limit=20),
        event_history=reopened.get_events("resume1"),
        live_session_present=False,
    )

    assert report["version"] == "resume-drill.v1"
    assert report["status"] == "ready"
    assert report["source"] == "session_store_replay"
    assert report["drill"]["uses_live_runtime_state"] is False
    assert report["drill"]["live_session_present"] is False
    assert report["capability_levels"]["durable_handoff"]["status"] == "ready"
    assert report["capability_levels"]["warm_process"]["status"] == "unproven"
    assert report["capability_levels"]["hot_tool_call"]["status"] == "unproven"
    assert report["closure_gate"]["can_claim_long_task_durable_handoff"] is True
    assert report["closure_gate"]["can_claim_warm_process_resume"] is False
    assert report["closure_gate"]["can_claim_hot_tool_call_resume"] is False
    assert report["recovered"]["task"] == "optimize long task continuity"
    assert report["recovered"]["open_plan_steps"][0]["title"] == "Run restart drill"
    assert report["recovered"]["last_result"]["tool"] == "modify_file"
    assert report["recovered"]["last_result"]["ok"] is True
    assert report["recovered"]["artifact_refs"][0]["path"] == "server/resume_drill.py"
    assert report["missing_required_fields"] == []
    assert report["next_action"] == "Continue with open plan step: Run restart drill."


def test_resume_drill_is_partial_without_continuation_checkpoint():
    report = build_resume_drill_report(
        session_id="partial1",
        stored_session={"session_id": "partial1", "task": "continue safely", "status": "running"},
        context_history=[
            {
                "revision": 1,
                "signature": "partial-sig",
                "snapshot": {"session_id": "partial1", "task": "continue safely"},
            }
        ],
        event_history=[],
    )

    assert report["status"] == "partial"
    assert report["capability_levels"]["durable_handoff"]["status"] == "partial"
    assert report["closure_gate"]["can_claim_long_task_durable_handoff"] is False
    assert report["closure_gate"]["can_claim_hot_tool_call_resume"] is False
    assert "continuation_checkpoint" in report["missing_required_fields"]
    assert "hot_tool_call" in report["capability_levels"]
