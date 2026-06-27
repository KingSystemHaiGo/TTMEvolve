from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.context_sync import (
    artifact_ref_from_step,
    build_context_sync_snapshot,
    collect_artifact_refs,
    commit_state_from_observation,
    context_sync_diff_keys,
    context_sync_signature,
    open_plan_steps,
)


def _trajectory(count: int = 9):
    return [
        {
            "iteration": i,
            "thought": f"step {i}",
            "action": {
                "tool": "read_file" if i == 0 else "modify_file",
                "params": {"path": f"f{i}.txt"},
            },
            "observation": {
                "ok": i % 3 != 0,
                "tool": "modify_file",
                "path": f"f{i}.txt",
                "idempotency_key": f"k{i}" if i == count - 1 else None,
                "committed": True if i == count - 1 else None,
            },
            "plan_validation": {"verdict": "warn" if i == count - 1 else "pass", "summary": "checked"},
            "budget_stats": {"workspace_profile": "coding"},
        }
        for i in range(count)
    ]


def test_context_sync_snapshot_contains_checkpoint_and_artifacts():
    snapshot = build_context_sync_snapshot(
        session_id="ctx1",
        task="large ongoing project",
        iteration=8,
        trajectory=_trajectory(),
        goal_checklist={
            "overall": "active",
            "counts": {"done": 1, "pending": 2},
            "next_focus": "finish runtime bus",
        },
        plan={
            "summary": "system work",
            "steps": [
                {"id": "a", "title": "done", "status": "done"},
                {"id": "b", "title": "wire continuation", "status": "in_progress", "tool": "modify_file"},
                {"id": "c", "title": "verify", "status": "pending", "tool": "execute_shell"},
            ],
        },
        latest_skill_sync={"ok": True, "state": "ok", "signature": "sig", "changed": False},
        context_revision=4,
    )

    checkpoint = snapshot["continuation_checkpoint"]
    assert snapshot["session_id"] == "ctx1"
    assert snapshot["last_tool"] == "modify_file"
    assert snapshot["artifact_count"] == 8
    assert snapshot["commit_state"]["idempotency_key"] == "k8"
    assert checkpoint["version"] == "continuation-checkpoint.v1"
    assert checkpoint["context_revision"] == 5
    assert checkpoint["workspace_profile"] == "coding"
    assert checkpoint["open_plan_steps"][0]["id"] == "b"
    assert checkpoint["compression"]["needed"] is True
    assert "large ongoing project" in checkpoint["compression"]["summary"]


def test_context_sync_signature_ignores_context_revision_only():
    base = build_context_sync_snapshot(
        session_id="ctx1",
        task="same task",
        iteration=1,
        trajectory=_trajectory(2),
        goal_checklist={"overall": "active"},
        plan={},
        latest_skill_sync={},
        context_revision=1,
    )
    changed_revision = build_context_sync_snapshot(
        session_id="ctx1",
        task="same task",
        iteration=1,
        trajectory=_trajectory(2),
        goal_checklist={"overall": "active"},
        plan={},
        latest_skill_sync={},
        context_revision=99,
    )

    assert context_sync_signature(base) == context_sync_signature(changed_revision)
    changed_revision["task"] = "changed task"
    assert context_sync_signature(base) != context_sync_signature(changed_revision)


def test_context_sync_diff_keys_and_open_plan_steps_are_stable():
    assert context_sync_diff_keys({}, {"b": 1, "a": 2}) == ["a", "b"]
    assert context_sync_diff_keys({"a": 1, "b": 2}, {"a": 1, "b": 3}) == ["b"]
    assert open_plan_steps({
        "steps": [
            {"id": "done", "status": "done"},
            {"id": "next", "status": "pending", "description": "verify"},
        ],
    }) == [{"id": "next", "title": "verify", "status": "pending", "tool": None}]


def test_artifact_and_commit_helpers_prefer_observation_then_params_and_dedupe():
    action = {"tool": "write_file", "params": {"path": "from_params.txt"}}
    observation = {
        "ok": True,
        "tool": "write_file",
        "path": "",
        "idempotency_key": "k1",
        "committed": True,
        "reconcile_status": "verified_local",
    }

    ref = artifact_ref_from_step(action, observation)
    assert ref["path"] == "from_params.txt"
    assert ref["committed"] is True
    assert commit_state_from_observation(observation)["reconcile_status"] == "verified_local"

    refs = collect_artifact_refs([
        {"action": action, "observation": observation},
        {"action": action, "observation": observation},
    ])
    assert refs == [ref]
