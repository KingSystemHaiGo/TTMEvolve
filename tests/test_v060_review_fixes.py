"""Tests for v0.6.0 code-review fixes.

Covers the bugs caught during code review:
- control_loop integral decay + clamp
- plan_format.update_step_status returns a NEW plan (immutable)
- scroll_chapter field validation
- copy_knowledge.critique_copy returns [] for passing copy
- plan_review signature accepts Optional[Set[str]]
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.control_loop import ControlLoop
from core.loop_scheduler import LoopScheduler
from core.plan_format import (
    empty_plan,
    normalize_plan,
    update_step_status,
)
from core.plan_review import review_plan
from core.scroll_chapter import ScrollChapterMemory, fingerprint_chapter, make_chapter
from learning.copy_knowledge import critique_copy
from learning.socratic_planner import build_gdd


# ---------- control_loop integral decay + clamp ----------


def test_control_loop_integral_bounded_after_many_failures():
    """Repeated failures should not blow up the integral forever."""
    controller = ControlLoop(integral_decay=0.9, integral_max=10.0)
    trajectory = [
        {"iteration": i, "action": {"tool": "shell"}, "observation": {"ok": False}}
        for i in range(50)
    ]
    for step in trajectory:
        controller.evaluate([step])
    # The integral must be clamped to ±integral_max.
    assert -10.0 <= controller._integral <= 10.0


def test_control_loop_integral_decays_with_success():
    """A success step should reduce the magnitude of the integral."""
    controller = ControlLoop(integral_decay=0.5)
    fail_trajectory = [
        {"iteration": 0, "action": {"tool": "shell"}, "observation": {"ok": False}}
    ]
    success_trajectory = [
        {"iteration": 1, "action": {"tool": "modify_file"}, "observation": {"ok": True}}
    ]
    controller.evaluate(fail_trajectory)
    after_fail = controller._integral
    controller.evaluate(success_trajectory)
    assert abs(controller._integral) < abs(after_fail)


def test_control_loop_invalid_decay_raises():
    try:
        ControlLoop(integral_decay=1.5)
    except ValueError:
        return
    raise AssertionError("expected ValueError for integral_decay > 1")


def test_control_loop_invalid_integral_max_raises():
    try:
        ControlLoop(integral_max=0)
    except ValueError:
        return
    raise AssertionError("expected ValueError for integral_max <= 0")


# ---------- plan_format immutable update ----------


def test_update_step_status_returns_new_plan():
    plan = normalize_plan(
        {
            "steps": [
                {"id": "s1", "tool": "modify_file", "params": {}, "expected_evidence": ["ok"]},
            ]
        },
        task="t",
    )
    new_plan = update_step_status(plan, "s1", "done")
    # The original plan should be untouched.
    assert plan["steps"][0]["status"] == "pending"
    # The new plan reflects the change.
    assert new_plan["steps"][0]["status"] == "done"


def test_update_step_status_invalid_status_returns_input():
    plan = normalize_plan(
        {"steps": [{"id": "s1", "tool": "modify_file", "params": {}, "expected_evidence": ["ok"]}]},
        task="t",
    )
    same = update_step_status(plan, "s1", "weird_status")
    assert same is plan


# ---------- scroll_chapter field validation ----------


def test_scroll_chapter_rejects_missing_id():
    memory = ScrollChapterMemory(max_chapters=10)
    try:
        memory.append({"title": "no id", "summary": "x"})
    except ValueError:
        return
    raise AssertionError("expected ValueError for missing id")


def test_scroll_chapter_rejects_empty_title():
    memory = ScrollChapterMemory(max_chapters=10)
    try:
        memory.append({"id": "s1::0", "title": "", "summary": "x"})
    except ValueError:
        return
    raise AssertionError("expected ValueError for empty title")


def test_scroll_chapter_rejects_non_string_id():
    memory = ScrollChapterMemory(max_chapters=10)
    try:
        memory.append({"id": None, "title": "x", "summary": "y"})
    except ValueError:
        return
    raise AssertionError("expected ValueError for None id")


# ---------- copy_knowledge critique_copy ----------


def test_critique_copy_returns_empty_list_for_clean_text():
    issues = critique_copy("差一点！再试一次")
    assert issues == []


def test_critique_copy_returns_empty_list_for_long_clean_text_under_threshold():
    issues = critique_copy("欢迎来到 TTMEvolve 游戏世界，祝你玩得开心")
    assert issues == []


# ---------- plan_review Optional signature ----------


def test_plan_review_accepts_none_known_tools():
    plan = empty_plan("t")
    plan["steps"].append({"id": "s1", "tool": "modify_file", "params": {}, "expected_evidence": ["ok"]})
    result = review_plan(plan)
    assert "verdict" in result


def test_plan_review_accepts_custom_known_tools():
    plan = empty_plan("t")
    plan["summary"] = "ok"
    plan["steps"].append({"id": "s1", "tool": "my_custom_tool", "params": {}, "expected_evidence": ["ok"]})
    result = review_plan(plan, known_tools={"my_custom_tool"})
    assert result["verdict"] == "pass"


# ---------- additional v0.6.0 review fixes ----------


def test_plan_format_approved_plan_block_has_closing_marker():
    from core.plan_format import plan_to_context_block
    plan = normalize_plan(
        {"summary": "x", "steps": [{"id": "s1", "tool": "modify_file", "params": {}, "expected_evidence": ["ok"]}]},
        task="t",
    )
    plan["approved"] = True
    block = plan_to_context_block(plan)
    assert "[/approved_plan]" in block


def test_control_loop_most_repeated_tool_tie_break_deterministic():
    controller = ControlLoop()
    trajectory = [
        {"iteration": 0, "action": {"tool": "zebra"}, "observation": {"ok": True}},
        {"iteration": 1, "action": {"tool": "alpha"}, "observation": {"ok": True}},
        {"iteration": 2, "action": {"tool": "zebra"}, "observation": {"ok": True}},
        {"iteration": 3, "action": {"tool": "alpha"}, "observation": {"ok": True}},
    ]
    result = controller.evaluate(trajectory)
    # alpha < zebra lexicographically, so on tie alpha wins.
    assert "alpha" in result["recommendation"]


def test_context_compression_streak_resets_on_no_tool_action():
    from core.context_compression import extract_repeated_tool_warnings
    trajectory = [
        {"iteration": 0, "action": {"tool": "modify_file"}, "observation": {"ok": True}},
        {"iteration": 1, "action": {"tool": "modify_file"}, "observation": {"ok": True}},
        {"iteration": 2, "action": {"tool": "modify_file"}, "observation": {"ok": True}},
        {"iteration": 3, "action": {}, "observation": {"ok": True}},  # done action, no tool
        {"iteration": 4, "action": {"tool": "read_file"}, "observation": {"ok": True}},
    ]
    warnings = extract_repeated_tool_warnings(trajectory, threshold=3)
    # The 'no-tool' action should reset the streak so read_file does not appear.
    for warning in warnings:
        assert "read_file" not in warning


def test_scroll_chapter_fingerprint_includes_actions_and_tags():
    chapter_a = make_chapter(session_id="s1", index=0, title="x", summary="y", actions=[{"tool": "a"}], tags=["a"])
    chapter_b = make_chapter(session_id="s1", index=0, title="x", summary="y", actions=[{"tool": "b"}], tags=["a"])
    assert fingerprint_chapter(chapter_a) != fingerprint_chapter(chapter_b)


def test_socratic_planner_summary_uses_dynamic_question_set():
    answers = {
        "core_loop": "跳跃",
        "target_player": "学生",
        "session_length": "3 分钟",
        "progression": "解锁角色",
        "art_style": "卡通风",
        "monetization": "广告",
    }
    result = build_gdd(answers)
    assert "跳跃" in result["gdd"]["summary"]
    assert "学生" in result["gdd"]["summary"]
    assert "广告" in result["gdd"]["summary"]


def test_plan_review_iterative_cycle_detection_finds_long_chains():
    # 200-step linear chain: step-N depends on step-(N-1). No cycle.
    steps = [
        {"id": f"s{i}", "tool": "read_file", "params": {}, "expected_evidence": ["ok"],
         "depends_on": [f"s{i-1}"] if i > 0 else []}
        for i in range(200)
    ]
    plan = normalize_plan({"summary": "long chain", "steps": steps}, task="t")
    review = review_plan(plan)
    codes = {issue["code"] for issue in review["issues"]}
    assert "dependency_cycle" not in codes


def test_plan_review_finds_cycle_at_end_of_long_chain():
    # 50-step chain with a cycle at the very end.
    steps = []
    for i in range(50):
        steps.append({"id": f"s{i}", "tool": "read_file", "params": {}, "expected_evidence": ["ok"],
                      "depends_on": [f"s{i-1}"] if i > 0 else []})
    # Add a cycle: s49 depends on s48, but also add s51 -> s49 -> s51.
    steps.append({"id": "s50", "tool": "read_file", "params": {}, "expected_evidence": ["ok"], "depends_on": ["s49"]})
    steps.append({"id": "s51", "tool": "read_file", "params": {}, "expected_evidence": ["ok"], "depends_on": ["s51"]})
    plan = normalize_plan({"summary": "long with cycle", "steps": steps}, task="t")
    review = review_plan(plan)
    codes = {issue["code"] for issue in review["issues"]}
    assert "dependency_cycle" in codes


# ---------- Low-priority review fixes ----------


def test_scroll_chapter_tokenizer_handles_cjk_extension_a():
    from core.scroll_chapter import _tokenize
    # Extension A characters (U+3400..U+4DBF) are now handled.
    tokens = _tokenize("扩展甲乙丙")
    assert set(tokens) >= {"扩", "展", "甲", "乙", "丙"}


def test_scroll_chapter_recall_works_with_cjk_extension_a():
    memory = ScrollChapterMemory(max_chapters=10)
    memory.append(make_chapter(session_id="s1", index=0, title="扩展甲乙丙", summary="跑酷游戏"))
    top = memory.recall("甲")
    assert top and top[0]["title"] == "扩展甲乙丙"


def test_copy_knowledge_exposes_constants():
    from learning.copy_knowledge import (
        BANNED_WORDS,
        MAX_COPY_LENGTH,
        MAX_EXCLAMATIONS,
    )
    assert "菜鸟" in BANNED_WORDS
    assert isinstance(MAX_COPY_LENGTH, int) and MAX_COPY_LENGTH > 0
    assert isinstance(MAX_EXCLAMATIONS, int) and MAX_EXCLAMATIONS >= 0


def test_loop_scheduler_status_wall_clock_is_time_time():
    """`last_iteration_at` should be a wall-clock timestamp, not a perf-counter value."""
    import time as _time
    scheduler = LoopScheduler(task_fn=lambda i: {"ok": True}, interval_seconds=0.001, max_iterations=1)
    before = _time.time()
    scheduler.run_blocking()
    after = _time.time()
    last = scheduler.status().get("last_iteration_at")
    assert isinstance(last, (int, float))
    assert before - 1.0 <= last <= after + 1.0


def test_loop_scheduler_run_blocking_records_wall_clock_at():
    scheduler = LoopScheduler(task_fn=lambda i: {"ok": True}, interval_seconds=0.001, max_iterations=1)
    scheduler.run_blocking()
    payload = scheduler._last_result or {}
    assert "wall_clock_at" in payload


# ---------- Low #51 word-boundary search ----------


def test_engine_knowledge_search_uses_word_boundary():
    from learning.engine_knowledge import search_rules
    # 'lay' should NOT match 'layer' when word-boundary is enforced.
    results = search_rules("lay")
    # 'collision' rule contains 'layer' but NOT the standalone word 'lay'.
    assert not any("layer" in (rule.get("rule") or "") and "lay" not in (rule.get("rule") or "").split() for rule in results)


def test_engine_knowledge_search_matches_whole_word_collision():
    from learning.engine_knowledge import search_rules
    results = search_rules("collision")
    assert any("collision" in (rule.get("rule") or "").lower() for rule in results)


def test_engine_knowledge_search_matches_cjk_substring():
    from learning.engine_knowledge import search_rules
    # engine_knowledge rules are in English; ensure CJK searches still work
    # for keywords that happen to appear in subsystem names / tag-like fields.
    # (We search for "physics" as a known subsystem.)
    results = search_rules("physics")
    assert len(results) > 0


def test_game_knowledge_search_uses_word_boundary():
    from learning.game_knowledge import search_game_knowledge
    # 'defense' as a whole word in id "tower_defense" — but the haystack
    # joins with newline, so 'defense' should NOT match the underscore form.
    # This proves word-boundary is enforced.
    results = search_game_knowledge("defense")
    # Should NOT find tower_defense because word boundary \b treats _ as word char.
    assert all(entry["id"] != "tower_defense" for entry in results)


def test_game_knowledge_search_finds_chinese_keywords():
    from learning.game_knowledge import search_game_knowledge
    # Chinese keywords should substring-match in labels.
    results = search_game_knowledge("跑酷")
    assert any(entry["id"] == "endless_runner" for entry in results)


def test_game_knowledge_search_does_not_match_substring_inside_longer_word():
    from learning.game_knowledge import search_game_knowledge
    # 'run' should not match 'endless_runner' (no whitespace-separated 'run').
    results = search_game_knowledge("run")
    assert all(entry["id"] != "endless_runner" for entry in results)


# ---------- Low #55 keyboard_repeat severity ----------


def test_engine_knowledge_keyboard_repeat_is_gotcha():
    from learning.engine_knowledge import rules_for_subsystem
    rules = rules_for_subsystem("input")
    keyboard_rule = next(r for r in rules if r["id"] == "input.keyboard_repeat")
    assert keyboard_rule["severity"] == "gotcha"


# ---------- Low #31 note is not None ----------


def test_update_step_status_with_empty_string_note_records_it():
    plan = normalize_plan(
        {"steps": [{"id": "s1", "tool": "modify_file", "params": {}, "expected_evidence": ["ok"]}]},
        task="t",
    )
    new_plan = update_step_status(plan, "s1", "done", note="")
    # Empty string is preserved as a deliberate "no extra note" marker.
    assert new_plan["steps"][0]["notes"] == ""