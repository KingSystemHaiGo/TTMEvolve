from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.plan_validation import summarize_plan_validation, validate_plan_step


def test_plan_validation_passes_successful_read_step():
    step = {
        "iteration": 0,
        "action": {"tool": "read_file", "params": {"path": "hello.txt"}},
        "observation": {"ok": True, "content": "world"},
    }

    report = validate_plan_step(task="read hello", step=step, trajectory=[])

    assert report["verdict"] == "pass"
    assert report["tool"] == "read_file"
    assert "observation.ok=true" in report["evidence"]
    assert report["next_check"] == "Continue to the next step."


def test_plan_validation_warns_on_unknown_commit_state():
    step = {
        "iteration": 0,
        "action": {"tool": "modify_file", "params": {"path": "hello.txt", "content": "world"}},
        "observation": {
            "ok": True,
            "tool": "modify_file",
            "path": "hello.txt",
            "idempotency_key": "s1:modify_file:abc",
            "committed": None,
        },
    }

    report = validate_plan_step(task="write hello", step=step, trajectory=[])

    assert report["verdict"] == "warn"
    assert report["issues"][0]["code"] == "commit_unknown"
    assert "commit state is unknown" in report["issues"][0]["message"]


def test_plan_validation_fails_validation_error_and_summarizes():
    step = {
        "iteration": 0,
        "action": {"tool": "read_file", "params": {}},
        "observation": {
            "ok": False,
            "failure_type": "tool_validation",
            "error": "missing required parameter 'path'",
            "suggested_next_step": "Add params.path.",
        },
    }

    report = validate_plan_step(task="read hello", step=step, trajectory=[])
    summary = summarize_plan_validation([{"plan_validation": report}])

    assert report["verdict"] == "fail"
    assert any(issue["code"] == "tool_validation_failed" for issue in report["issues"])
    assert report["next_check"] == "Add params.path."
    assert summary["counts"]["fail"] == 1
    assert summary["last"]["tool"] == "read_file"


if __name__ == "__main__":
    test_plan_validation_passes_successful_read_step()
    test_plan_validation_warns_on_unknown_commit_state()
    test_plan_validation_fails_validation_error_and_summarizes()
    print("[PASS] plan validation tests")
