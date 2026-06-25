"""Tests for v0.6.0 knowledge integration:
- core/scroll_chapter.py (Abidingenuity-inspired)
- core/control_loop.py (Ima 之五 PID)
- learning/engine_knowledge.py (engine subsystems)
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.control_loop import ControlLoop
from core.scroll_chapter import (
    ScrollChapterMemory,
    fingerprint_chapter,
    make_chapter,
)
from learning.engine_knowledge import (
    all_rules,
    render_all_cards,
    render_subsystem_card,
    rules_for_subsystem,
    search_rules,
)


# ---------- scroll_chapter ----------


def test_make_chapter_has_required_fields():
    chapter = make_chapter(
        session_id="s1",
        index=0,
        title="first chapter",
        summary="we built the menu",
        actions=[{"tool": "modify_file", "outcome": "ok"}],
        outcome="success",
        tags=["menu", "ui"],
    )
    for key in ("id", "session_id", "title", "summary", "actions", "outcome", "tags"):
        assert key in chapter


def test_scroll_chapter_memory_appends_in_order():
    memory = ScrollChapterMemory(max_chapters=10)
    memory.append(make_chapter(session_id="s1", index=0, title="a", summary="x"))
    memory.append(make_chapter(session_id="s1", index=1, title="b", summary="y"))
    chapters = memory.list_chapters()
    assert [c["title"] for c in chapters] == ["a", "b"]


def test_scroll_chapter_memory_filters_by_session():
    memory = ScrollChapterMemory(max_chapters=10)
    memory.append(make_chapter(session_id="s1", index=0, title="a", summary="x"))
    memory.append(make_chapter(session_id="s2", index=0, title="b", summary="y"))
    s1 = memory.list_chapters(session_id="s1")
    assert [c["title"] for c in s1] == ["a"]


def test_scroll_chapter_recall_ranks_by_keyword_overlap():
    memory = ScrollChapterMemory(max_chapters=10)
    memory.append(make_chapter(session_id="s1", index=0, title="menu build", summary="built the start menu UI"))
    memory.append(make_chapter(session_id="s1", index=1, title="audio setup", summary="added bgm and sfx"))
    memory.append(make_chapter(session_id="s1", index=2, title="physics test", summary="player jumps and collides"))
    top = memory.recall("menu")
    assert top and top[0]["title"] == "menu build"


def test_scroll_chapter_recall_boosts_successful_outcomes():
    memory = ScrollChapterMemory(max_chapters=10)
    memory.append(make_chapter(session_id="s1", index=0, title="runner attempt", summary="endless runner prototype", outcome="success"))
    memory.append(make_chapter(session_id="s1", index=1, title="runner attempt", summary="endless runner prototype", outcome="failed"))
    top = memory.recall("runner")
    assert top and top[0]["outcome"] == "success"


def test_scroll_chapter_recall_empty_query_returns_empty():
    memory = ScrollChapterMemory(max_chapters=10)
    memory.append(make_chapter(session_id="s1", index=0, title="x", summary="y"))
    assert memory.recall("") == []


def test_scroll_chapter_capacity_trims_oldest():
    memory = ScrollChapterMemory(max_chapters=4)
    for i in range(6):
        memory.append(make_chapter(session_id="s1", index=i, title=f"chapter {i}", summary="x"))
    chapters = memory.list_chapters()
    # 6 appends with max_chapters=4 → trim to keep=2 once we hit 5, then
    # append #6 brings len to 3 (still ≤ 4 so no further trim).
    assert len(chapters) == 3
    assert chapters[-1]["title"] == "chapter 5"
    assert chapters[0]["title"] == "chapter 3"


def test_scroll_chapter_render_card_includes_outcome():
    memory = ScrollChapterMemory(max_chapters=10)
    chapter = make_chapter(
        session_id="s1",
        index=0,
        title="shipped",
        summary="first release",
        outcome="success",
    )
    card = memory.render_chapter_card(chapter)
    assert "shipped" in card
    assert "success" in card


def test_build_scroll_context_block_is_bounded():
    memory = ScrollChapterMemory(max_chapters=10)
    memory.append(make_chapter(session_id="s1", index=0, title="a", summary="summary " * 50))
    memory.append(make_chapter(session_id="s1", index=1, title="b", summary="another " * 50, outcome="ok"))
    block = memory.build_scroll_context_block(memory.list_chapters(), max_chars=200)
    assert "scroll_memory" in block
    assert len(block) <= 220


def test_fingerprint_chapter_is_stable():
    chapter = make_chapter(session_id="s1", index=0, title="x", summary="y")
    assert fingerprint_chapter(chapter) == fingerprint_chapter(chapter)


# ---------- control_loop ----------


def test_control_loop_stable_for_clean_trajectory():
    controller = ControlLoop()
    trajectory = [
        {"iteration": 0, "action": {"tool": "modify_file"}, "observation": {"ok": True}},
        {"iteration": 1, "action": {"tool": "read_file"}, "observation": {"ok": True}},
        {"iteration": 2, "action": {"tool": "shell"}, "observation": {"ok": True}},
    ]
    result = controller.evaluate(trajectory)
    assert result["verdict"] == "stable"


def test_control_loop_detects_drift_on_repeats():
    controller = ControlLoop(repeat_threshold=2)
    trajectory = [
        {"iteration": i, "action": {"tool": "modify_file"}, "observation": {"ok": True}}
        for i in range(4)
    ]
    result = controller.evaluate(trajectory)
    assert result["verdict"] in {"drift", "diverging"}


def test_control_loop_detects_diverging_on_failures():
    controller = ControlLoop()
    trajectory = [
        {
            "iteration": i,
            "action": {"tool": "shell"},
            "observation": {"ok": False, "error": "boom"},
        }
        for i in range(6)
    ]
    result = controller.evaluate(trajectory)
    assert result["verdict"] == "diverging"
    assert "rollback" in result["recommendation"].lower() or "recovery" in result["recommendation"].lower()


def test_control_loop_reset_clears_state():
    controller = ControlLoop()
    trajectory = [
        {"iteration": i, "action": {"tool": "shell"}, "observation": {"ok": False}}
        for i in range(6)
    ]
    controller.evaluate(trajectory)
    controller.reset()
    assert controller._integral == 0.0
    assert controller._last_error == 0.0


def test_control_loop_recommendation_mentions_repeated_tool():
    controller = ControlLoop()
    trajectory = [
        {"iteration": i, "action": {"tool": "modify_file"}, "observation": {"ok": True}}
        for i in range(5)
    ]
    result = controller.evaluate(trajectory)
    assert "modify_file" in result["recommendation"]


def test_control_loop_invalid_history_window_raises():
    try:
        ControlLoop(history_window=0)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


# ---------- engine_knowledge ----------


def test_all_rules_includes_five_subsystems():
    subsystems = {rule["subsystem"] for rule in all_rules()}
    assert {"physics", "audio", "input", "network", "graphics"}.issubset(subsystems)


def test_rules_for_subsystem_filters_correctly():
    physics_rules = rules_for_subsystem("physics")
    assert all(rule["subsystem"] == "physics" for rule in physics_rules)


def test_search_rules_matches_keywords():
    results = search_rules("collision")
    assert any("collision" in (rule.get("rule") or "").lower() for rule in results)


def test_search_rules_empty_returns_empty():
    assert search_rules("") == []


def test_render_subsystem_card_includes_warning_marker():
    card = render_subsystem_card("physics")
    assert "physics" in card
    assert "⚠" in card or "✓" in card


def test_render_all_cards_lists_each_subsystem():
    card = render_all_cards()
    for name in ("physics", "audio", "input", "network", "graphics"):
        assert name in card