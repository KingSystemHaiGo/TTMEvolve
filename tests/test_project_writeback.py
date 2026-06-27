from __future__ import annotations

from datetime import datetime
from pathlib import Path

from server.project_writeback import (
    PROJECT_WRITEBACK_VERSION,
    apply_project_writeback_plan,
    build_project_writeback_plan,
)


def _project_control(*, status: str = "ready", due: list[dict[str, str]] | None = None) -> dict:
    return {
        "version": "project-control.v1",
        "status": status,
        "next_action": "Run focused verification",
        "current_focus": "Project control writeback",
        "blockers": [],
        "required_gates": ["GATE_0_DECLARE", "POST_MEM", "POST_SYNC"],
        "completed_gates": ["GATE_0_DECLARE"],
        "pending_gates": ["POST_MEM", "POST_SYNC"],
        "memory_updates_due": due
        if due is not None
        else [
            {"gate": "POST_MEM", "file": "docs/memory-index.md"},
            {"gate": "POST_SYNC", "file": "docs/sprint-board.md"},
        ],
        "verification": {
            "status": "requires_evidence",
            "rule": "Strong claims require test, endpoint, runtime, or file evidence.",
        },
        "truthfulness": {
            "rule": "Strong claims require test, endpoint, runtime, or file evidence.",
        },
    }


def _project_state() -> dict:
    return {
        "status": "ready",
        "task": "Add project-control writeback",
        "next_action": "Run focused verification",
        "plan_verdict": "pass",
    }


def _make_docs(root: Path) -> None:
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "memory-index.md").write_text("# Memory\n", encoding="utf-8")
    (root / "docs" / "sprint-board.md").write_text("# Sprint\n", encoding="utf-8")


def test_project_writeback_plan_is_append_only_and_limited_to_due_files(tmp_path: Path):
    _make_docs(tmp_path)

    plan = build_project_writeback_plan(
        project_root=tmp_path,
        session_id="writeback1",
        project_state=_project_state(),
        project_control=_project_control(),
        now=datetime(2026, 6, 27, 3, 30),
    )

    assert plan["version"] == PROJECT_WRITEBACK_VERSION
    assert plan["status"] == "ready"
    assert plan["applicable"] is True
    assert [op["file"] for op in plan["operations"]] == [
        "docs/memory-index.md",
        "docs/sprint-board.md",
    ]
    assert all(op["action"] == "append" for op in plan["operations"])
    assert all(op["status"] == "pending_append" for op in plan["operations"])
    assert all("TTMEVOLVE-PROJECT-WRITEBACK" in op["content"] for op in plan["operations"])
    assert "2026-06-27 03:30" in plan["operations"][0]["content"]
    assert "Run focused verification" in plan["operations"][0]["content"]
    assert "source: `project_control`" in plan["operations"][0]["content"]


def test_project_writeback_apply_writes_once_and_is_idempotent(tmp_path: Path):
    _make_docs(tmp_path)
    plan = build_project_writeback_plan(
        project_root=tmp_path,
        session_id="writeback2",
        project_state=_project_state(),
        project_control=_project_control(),
        now=datetime(2026, 6, 27, 3, 31),
    )

    result = apply_project_writeback_plan(tmp_path, plan)

    assert result["status"] == "applied"
    assert result["applied_count"] == 2
    memory_text = (tmp_path / "docs" / "memory-index.md").read_text(encoding="utf-8")
    sprint_text = (tmp_path / "docs" / "sprint-board.md").read_text(encoding="utf-8")
    assert plan["operations"][0]["marker"] in memory_text
    assert plan["operations"][1]["marker"] in sprint_text

    second = apply_project_writeback_plan(tmp_path, plan)

    assert second["status"] == "already_applied"
    assert second["skipped_count"] == 2
    assert (tmp_path / "docs" / "memory-index.md").read_text(encoding="utf-8").count(plan["operations"][0]["marker"]) == 1
    assert (tmp_path / "docs" / "sprint-board.md").read_text(encoding="utf-8").count(plan["operations"][1]["marker"]) == 1


def test_project_writeback_rejects_paths_outside_allowed_post_docs(tmp_path: Path):
    _make_docs(tmp_path)

    plan = build_project_writeback_plan(
        project_root=tmp_path,
        session_id="writeback3",
        project_state=_project_state(),
        project_control=_project_control(
            due=[{"gate": "POST_MEM", "file": "../outside.md"}],
        ),
    )
    result = apply_project_writeback_plan(tmp_path, plan)

    assert plan["status"] == "blocked"
    assert plan["applicable"] is False
    assert plan["invalid_targets"][0]["file"] == "../outside.md"
    assert result["status"] == "blocked"
    assert not (tmp_path.parent / "outside.md").exists()


def test_project_writeback_blocks_vague_or_blocked_project_control(tmp_path: Path):
    _make_docs(tmp_path)
    control = _project_control(status="needs_confirmation")
    control["blockers"] = [
        {
            "id": "vague_instruction_needs_confirmation",
            "severity": "blocker",
            "detail": "Confirm decomposed vague subtasks before execution.",
        }
    ]

    plan = build_project_writeback_plan(
        project_root=tmp_path,
        session_id="writeback4",
        project_state=_project_state(),
        project_control=control,
    )
    result = apply_project_writeback_plan(tmp_path, plan)

    assert plan["status"] == "blocked"
    assert plan["operations"] == []
    assert result["status"] == "blocked"

