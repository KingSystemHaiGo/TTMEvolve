"""End-to-end boss-fight regression that fuses Slice A (skill packs),
Slice B (typed DAG) and Slice C (feature state). One realistic
"add a boss fight to level 3" task drives every layer:

- UNDERSTAND auto-recalls the engine / platformer / maker packs
  so the LLM has working knowledge available before reasoning.
- PROPOSE proposes a typed DAG with asset + code + scene sub-goals.
- The DAG runs the parallel sub-goals through per-type sub-loops.
- An auto-appended integration sub-goal depends on every upstream.
- POST advances the feature state and writes the sprint board.

Constraints honoured: no model names (only capability hints), no
code line thresholds (complexity is a function of acceptance /
dependency / capability signals).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.goal_loop import GoalLoop


# ---------------------------------------------------------------------------
# LLM stubs that drive the goal loop deterministically
# ---------------------------------------------------------------------------


class _BossLLM:
    """LLM that produces realistic output for every stage the goal
    loop asks it to reason about. The output is shaped so that a
    typed sub-goal DAG emerges from PROPOSE."""

    def reflect(self, prompt: str) -> str:
        if "UNDERSTAND stage" in prompt:
            return json.dumps({
                "restated_goal": "Add a boss fight to level 3 with a sprite, an AI, and a scene integration.",
                "subtasks": [
                    "design the boss state machine",
                    "implement the AI and collision",
                    "wire the boss into the level",
                ],
                "success_criteria": [
                    "boss sprite generated",
                    "boss AI compiles and tests pass",
                    "scene loads without errors",
                ],
                "open_questions": [],
            })
        if "PROPOSE stage" in prompt:
            return json.dumps({
                "recommended": "Generate the boss sprite, implement the boss AI behind a feature flag, and wire it into the level scene.",
                "alternatives": ["reuse an existing enemy sprite", "skip the boss for now"],
                "risks": ["scope creep", "no integration test for the level"],
                "acceptance": [
                    "boss sprite exists and is sized correctly",
                    "boss AI compiles and unit tests pass",
                    "level 3 loads the boss and the player can trigger it",
                ],
                "sub_goals": [
                    {
                        "id": "asset-boss-sprite",
                        "task": "Generate the boss sprite with 4 animation states",
                        "type": "asset",
                        "acceptance": ["png exists", "size under 64KB", "transparent background"],
                        "model_hint": "fast",
                    },
                    {
                        "id": "code-boss-ai",
                        "task": "Implement the boss AI with idle / chase / attack states",
                        "type": "code",
                        "depends_on": ["asset-boss-sprite"],
                        "acceptance": ["compiles", "state machine has 3 states", "tests pass"],
                        "model_hint": "balanced",
                        "assigned_agent": "programmer-1",
                    },
                    {
                        "id": "scene-level-3",
                        "task": "Add the boss spawner to level 3 and wire the trigger",
                        "type": "scene",
                        "depends_on": ["code-boss-ai"],
                        "acceptance": ["scene loads", "trigger fires on player proximity"],
                        "model_hint": "balanced",
                    },
                    {
                        "id": "test-boss-flow",
                        "task": "Verify the boss fight end-to-end in a test scene",
                        "type": "test",
                        "depends_on": ["scene-level-3"],
                        "acceptance": ["trigger fires", "boss takes damage", "boss state machine cycles"],
                        "model_hint": "deep",
                    },
                ],
            })
        if "RESEARCH stage" in prompt:
            return json.dumps({
                "constraints": ["use the project's existing UrhoX patterns", "stay within the modular monolith"],
                "risks": ["scope creep into combat system rewrite"],
                "summary": "constraints collected",
            })
        if "REV stage" in prompt:
            return json.dumps({
                "intent_match": True,
                "issues": [],
                "summary": "boss fight wired and tested",
            })
        return "{}"


def _code_dev_runner(task: str, session_id: str) -> Dict[str, Any]:
    """Code sub-loop dev runner. Returns a success result so the
    code sub-goal completes and downstream sub-goals can run."""
    return {
        "session_id": session_id,
        "task": task,
        "done": True,
        "output": f"implemented: {task[:60]}",
        "trajectory": [
            {
                "action": {"tool": "modify_file"},
                "observation": {"tool": "pytest", "output": "1 passed", "ok": True},
            }
        ],
        "iteration_count": 1,
    }


# ---------------------------------------------------------------------------
# The fused e2e
# ---------------------------------------------------------------------------


def test_boss_fight_fuses_skill_packs_dag_and_feature_state(tmp_path: Path):
    events: List[Dict[str, Any]] = []

    def _emit(event: Dict[str, Any]) -> None:
        events.append(event)

    loop = GoalLoop(
        project_root=tmp_path,
        emit=_emit,
        dev_runner=_code_dev_runner,
        approval_policy="never",
        llm=_BossLLM(),
        max_subgoals=6,
        max_concurrent_subgoals=3,
        auto_post=True,
        artifacts_root=tmp_path,
    )

    result = loop.run("Add a boss fight to level 3", session_id="boss-session")

    # 1. The goal completed end-to-end.
    assert result["done"] is True
    assert result["goal_loop"]["status"] == "completed"

    # 2. Slice A — skill packs were auto-recalled during UNDERSTAND.
    recall_events = [
        e for e in events if e.get("type") == "goal_skill_packs_recalled"
    ]
    assert recall_events, "UNDERSTAND did not recall any skill packs"
    recalled_ids = {
        rec["pack"]["pack_id"]
        for rec in recall_events[0]["payload"]["packs"]
    }
    # At least one project-side pack matches. "Add a boss fight"
    # does not contain "urhox" by itself, so the genre pack is
    # the most natural match — we just assert that recall ran.
    assert recalled_ids
    assert "genre_platformer" in recalled_ids or "engine_urhox" in recalled_ids

    # 3. Slice B — the typed DAG ran. All four LLM sub-goals
    # plus the auto-appended integration sub-goal completed.
    sub_goal_results = result["goal_loop"]["sub_goals"]
    assert len(sub_goal_results) == 5
    sub_ids = {s["sub_id"] for s in sub_goal_results}
    assert "asset-boss-sprite" in sub_ids
    assert "code-boss-ai" in sub_ids
    assert "scene-level-3" in sub_ids
    assert "test-boss-flow" in sub_ids
    assert "integration" in sub_ids

    # 4. Per-type sub-loops produced the right artefacts.
    asset_result = next(s for s in sub_goal_results if s["sub_id"] == "asset-boss-sprite")
    code_result = next(s for s in sub_goal_results if s["sub_id"] == "code-boss-ai")
    scene_result = next(s for s in sub_goal_results if s["sub_id"] == "scene-level-3")
    test_result = next(s for s in sub_goal_results if s["sub_id"] == "test-boss-flow")
    integration_result = next(s for s in sub_goal_results if s["sub_id"] == "integration")

    assert asset_result["status"] == "done"
    assert code_result["status"] == "done"
    assert scene_result["status"] == "done"
    assert test_result["status"] == "done"
    assert integration_result["status"] == "done"

    # 5. The integration sub-goal depends on every upstream one.
    assert set(integration_result["depends_on"]) == {
        "asset-boss-sprite",
        "code-boss-ai",
        "scene-level-3",
        "test-boss-flow",
    }

    # 6. Slice C — the feature ledger recorded the goal, the
    # sprint board and progress.md exist on disk, and the feature
    # ended up either shipped (with artefacts) or in_progress.
    ledger_path = tmp_path / ".ttmevolve" / "features.jsonl"
    assert ledger_path.is_file()
    ledger_events = [
        json.loads(line) for line in
        ledger_path.read_text(encoding="utf-8").strip().splitlines()
    ]
    assert any(e["event"] == "opened" for e in ledger_events)
    final_event = ledger_events[-1]
    # The feature is either in_progress (no confirmed artefacts) or
    # shipped (artifacts were attached during the run).
    assert final_event["state"] in {"in_progress", "shipped"}

    sprint_path = tmp_path / "docs" / "sprint-board.md"
    progress_path = tmp_path / "docs" / "progress.md"
    assert sprint_path.is_file()
    assert progress_path.is_file()
    assert "boss" in sprint_path.read_text(encoding="utf-8").lower()

    # 7. The POST stage emitted the feature summary.
    post_output = next(
        e["payload"]["stage_run"]["output"]
        for e in events
        if e["type"] == "goal_stage_output" and e["payload"]["stage"] == "POST"
    )
    assert post_output["feature"]["ok"] is True
    assert post_output["feature"]["state"] in {"in_progress", "shipped"}


def test_boss_fight_no_model_names_no_line_thresholds(tmp_path: Path):
    """Verify the Slice A and Slice B surfaces never bake in a
    specific model name or a code-line threshold."""
    import re
    from pathlib import Path
    # Walk the project-side sources and assert no forbidden names.
    forbidden_models = ("claude", "sonnet", "haiku", "opus", "anthropic")
    forbidden_phrases = (
        r"≤\s*\d+\s*lines",   # ≤N lines
        r"<\s*\d+\s*lines",   # <N lines
        r"max.*lines",
        r"limit.*lines",
    )
    sources = [
        _PROJECT_ROOT / "agent" / "goal_dag.py",
        _PROJECT_ROOT / "agent" / "typed_subloop.py",
        _PROJECT_ROOT / "agent" / "feature_state.py",
        _PROJECT_ROOT / "agent" / "skill_packs" / "__init__.py",
    ]
    for source in sources:
        text = source.read_text(encoding="utf-8", errors="replace")
        lowered = text.lower()
        for name in forbidden_models:
            assert name not in lowered, (
                f"{source.name} mentions forbidden model name '{name}'"
            )
        for pattern in forbidden_phrases:
            assert not re.search(pattern, lowered), (
                f"{source.name} uses a code-line threshold matching {pattern!r}"
            )


def test_boss_fight_event_chain_is_complete(tmp_path: Path):
    """The full event stream should record every key transition
    so an external observer (Workbench) can reconstruct progress."""
    events: List[Dict[str, Any]] = []
    loop = GoalLoop(
        project_root=tmp_path,
        emit=events.append,
        dev_runner=_code_dev_runner,
        approval_policy="never",
        llm=_BossLLM(),
        auto_post=True,
        artifacts_root=tmp_path,
    )
    loop.run("Add a boss fight to level 3", session_id="obs")

    event_types = {e["type"] for e in events}
    # Must include all the slices' key events.
    for required in (
        "goal_started",
        "goal_skill_packs_recalled",
        "goal_sub_goals_started",
        "goal_sub_goals_completed",
        "goal_post_completed",
    ):
        assert required in event_types, f"missing required event: {required}"
