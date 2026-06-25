"""Tests for v0.6.0 Maker game-planning knowledge libraries."""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from learning.game_knowledge import (
    all_game_types,
    find_game_type,
    render_game_type_card,
    search_game_knowledge,
    suggest_game_type_for,
)
from learning.copy_knowledge import (
    all_categories,
    all_voice_guidelines,
    critique_copy,
    render_category_card,
    render_slot,
    templates_for,
)
from learning.mechanics_knowledge import (
    all_mechanics_rules,
    mechanics_rules_for,
    render_balance_card,
    review_balance_card,
)
from learning.maker_cases import (
    all_cases,
    cases_for,
    design_lesson_for,
    render_all_case_cards,
    render_case_card,
)
from learning.socratic_planner import (
    all_questions,
    build_gdd,
    next_question,
    render_question_card,
    render_session_card,
)


# ---------- game_knowledge ----------


def test_all_game_types_non_empty():
    types = all_game_types()
    assert len(types) >= 5
    ids = {entry["id"] for entry in types}
    assert "endless_runner" in ids


def test_find_game_type_returns_entry():
    entry = find_game_type("tower_defense")
    assert entry["label"] == "塔防"
    assert "key_mechanics" in entry


def test_find_game_type_unknown_returns_empty():
    assert find_game_type("not-a-game") == {}


def test_search_game_knowledge_matches_keywords():
    results = search_game_knowledge("跑酷")
    assert any(entry["id"] == "endless_runner" for entry in results)


def test_search_game_knowledge_empty_query_returns_empty():
    assert search_game_knowledge("") == []


def test_render_game_type_card_contains_required_sections():
    card = render_game_type_card("endless_runner")
    assert "无尽跑酷" in card
    assert "核心循环" in card
    assert "关键机制" in card


def test_suggest_game_type_for_heuristics():
    assert "endless_runner" in suggest_game_type_for("我想做一个跑酷游戏")
    assert "tower_defense" in suggest_game_type_for("塔防 building game")


# ---------- copy_knowledge ----------


def test_voice_guidelines_non_empty():
    assert len(all_voice_guidelines()) >= 5


def test_templates_for_known_category():
    onboarding = templates_for("onboarding")
    assert any(entry["slot"] == "cta" for entry in onboarding)


def test_render_slot_substitutes_values():
    text = render_slot("victory", "stat", verb="跑出", number=1234, unit="米")
    assert "1234" in text and "米" in text


def test_render_slot_unknown_returns_empty():
    assert render_slot("nonexistent", "x") == ""


def test_critique_copy_flags_excess_exclamations():
    issues = critique_copy("太好玩了！！！再来！！！")
    codes = {issue["code"] for issue in issues}
    assert "exclamation_spam" in codes


def test_critique_copy_flags_insulting_words():
    issues = critique_copy("你这个菜鸟")
    codes = {issue["code"] for issue in issues}
    assert "insulting_word" in codes


def test_critique_copy_passes_short_kind_copy():
    issues = critique_copy("差一点！再试一次")
    assert issues[0]["code"] == "ok"


def test_render_category_card_includes_examples():
    card = render_category_card("onboarding")
    assert "title" in card


def test_all_categories_lists_known_keys():
    categories = set(all_categories())
    assert {"onboarding", "tutorial", "victory", "failure"}.issubset(categories)


# ---------- mechanics_knowledge ----------


def test_all_mechanics_rules_has_five_categories():
    rules = all_mechanics_rules()
    assert set(rules.keys()) == {"core_loop", "progression", "reward", "economy", "retention"}


def test_mechanics_rules_for_unknown_returns_empty():
    assert mechanics_rules_for("nope") == []


def test_render_balance_card_lists_each_category():
    card = render_balance_card()
    assert "core_loop" in card
    assert "progression" in card


def test_review_balance_card_flags_ad_reward_combo():
    warnings = review_balance_card(["广告激励", "奖励金币"])
    codes = {warning["code"] for warning in warnings}
    assert "ad_reward_check" in codes


def test_review_balance_card_flags_hard_currency():
    warnings = review_balance_card(["宝石商城"])
    codes = {warning["code"] for warning in warnings}
    assert "hard_currency_wall" in codes


def test_review_balance_card_clean_for_safe_features():
    warnings = review_balance_card(["无尽跑酷", "排行榜"])
    # safe features should not raise economy warnings
    codes = {warning["code"] for warning in warnings}
    assert "hard_currency_wall" not in codes


# ---------- maker_cases ----------


def test_all_cases_non_empty():
    cases = all_cases()
    assert len(cases) >= 5


def test_cases_for_filters_by_game_type():
    runner_cases = cases_for("endless_runner")
    assert all(case["game_type"] == "endless_runner" for case in runner_cases)


def test_render_case_card_includes_lesson_and_avoid():
    card = render_case_card("flappy-bird-style")
    assert "启示" in card
    assert "避坑" in card


def test_design_lesson_for_matches_runner_task():
    lesson = design_lesson_for("我想做一个跑酷游戏")
    assert "病毒传播" in lesson or "挫败" in lesson


def test_render_all_case_cards_lists_each_case():
    card = render_all_case_cards()
    for case in all_cases():
        assert case["id"] in card


# ---------- socratic_planner ----------


def test_socratic_questions_cover_required_ids():
    ids = {question["id"] for question in all_questions()}
    assert {"core_loop", "target_player", "progression", "monetization"}.issubset(ids)


def test_next_question_returns_first_unanswered():
    first = next_question({})
    assert first["id"] == "core_loop"
    second = next_question({"core_loop": "x"})
    assert second["id"] == "target_player"
    done = next_question({question["id"]: "answer" for question in all_questions()})
    assert done is None


def test_build_gdd_marks_incomplete_when_missing_answers():
    result = build_gdd({"core_loop": "x"})
    assert result["complete"] is False
    assert "target_player" in result["missing"]


def test_build_gdd_produces_complete_doc():
    answers = {question["id"]: "answer" for question in all_questions()}
    result = build_gdd(answers)
    assert result["complete"] is True
    assert "summary" in result["gdd"]


def test_render_question_card_includes_examples():
    question = all_questions()[0]
    card = render_question_card(question)
    assert question["prompt"] in card
    assert "可选示例" in card


def test_render_session_card_marks_answered_questions():
    card = render_session_card({"core_loop": "跳跃"})
    assert "✓" in card
    assert "·" in card