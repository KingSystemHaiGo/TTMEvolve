from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.goal_tracking import checklist_context_hint, derive_goal_checklist, update_goal_checklist


def test_goal_checklist_derives_side_effect_criteria():
    criteria = derive_goal_checklist("create a file")
    ids = [item["id"] for item in criteria]

    assert "task_defined" in ids
    assert "side_effect_state" in ids
    assert "final_response" in ids


def test_goal_checklist_updates_from_plan_validation_and_output():
    trajectory = [
        {
            "iteration": 0,
            "action": {"tool": "modify_file", "params": {"path": "hello.txt"}},
            "observation": {
                "ok": True,
                "tool": "modify_file",
                "path": "hello.txt",
                "idempotency_key": "s1:modify_file:abc",
                "committed": True,
            },
            "plan_validation": {
                "verdict": "pass",
                "summary": "modify_file produced acceptable evidence.",
            },
        }
    ]

    checklist = update_goal_checklist(
        task="create a file",
        trajectory=trajectory,
        output="done",
    )

    statuses = {item["id"]: item["status"] for item in checklist["criteria"]}
    assert checklist["overall"] == "done"
    assert statuses["valid_action"] == "done"
    assert statuses["step_evidence"] == "done"
    assert statuses["side_effect_state"] == "done"
    assert statuses["final_response"] == "done"


def test_goal_checklist_context_hint_keeps_open_items_only():
    checklist = update_goal_checklist(task="create a file", trajectory=[])
    hint = checklist_context_hint(checklist)

    assert "[goal_checklist]" in hint
    assert "task_defined" not in hint
    assert "valid_action" in hint
    assert "side_effect_state" in hint


def test_goal_checklist_seeds_maker_template_acceptance_criteria():
    templates = [
        {
            "id": "maker_inspect_project",
            "label": "Inspect Maker project state",
            "acceptance_criteria": [
                "MakerMCP readiness and warning_codes are known.",
                "The next action names whether it uses MakerMCP authority or local file authority.",
            ],
        },
        {
            "id": "maker_plan_small_change",
            "label": "Plan one verifiable Maker change",
            "acceptance_criteria": [
                "Plan has a single expected outcome.",
                "Plan references exact files, Maker artifact ids, or tool evidence.",
            ],
        },
    ]

    checklist = update_goal_checklist(
        task="build a TapTap Maker game",
        trajectory=[],
        maker_templates=templates,
    )
    criteria = {item["id"]: item for item in checklist["criteria"]}

    assert criteria["maker:maker_inspect_project:0"]["status"] == "done"
    assert criteria["maker:maker_inspect_project:0"]["evidence"] == ["runtime_contract"]
    assert criteria["maker:maker_plan_small_change:0"]["status"] == "pending"
    assert checklist["counts"]["pending"] >= 1


if __name__ == "__main__":
    test_goal_checklist_derives_side_effect_criteria()
    test_goal_checklist_updates_from_plan_validation_and_output()
    test_goal_checklist_context_hint_keeps_open_items_only()
    test_goal_checklist_seeds_maker_template_acceptance_criteria()
    print("[PASS] goal tracking tests")
