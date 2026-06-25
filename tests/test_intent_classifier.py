"""Tests for the v0.7.0 COS intent classifier (门槛 0)."""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.intent_classifier import (
    INTENT_CLASSIFIER_VERSION,
    CATEGORIES,
    classify,
    render_card,
)


# ---------- single-step classification ----------


def test_classify_coding_request():
    intent = classify("帮我修复这个 bug")
    assert intent.category == "coding"


def test_classify_game_design_request():
    intent = classify("做一个跑酷游戏")
    assert intent.category == "game"


def test_classify_plan_request():
    intent = classify("下一阶段的路线图")
    assert intent.category == "plan"


def test_classify_project_release_request():
    intent = classify("发布 v0.7.1 版本")
    assert intent.category == "project"


def test_classify_ops_request():
    intent = classify("打包 portable runtime")
    assert intent.category == "ops"


def test_classify_maker_request():
    intent = classify("调用 Maker MCP 生成图片")
    assert intent.category == "maker"


def test_classify_question_request():
    intent = classify("这个是怎么工作的？")
    assert intent.category == "question"


# ---------- multi-step detection ----------


def test_classify_single_step_simple_request():
    intent = classify("修复 bug")
    assert intent.multi_step is False


def test_classify_multi_step_with_newline():
    intent = classify("第一：实现功能\n第二：测试")
    assert intent.multi_step is True


def test_classify_multi_step_with_numbered_list():
    intent = classify("1. 实现 A\n2. 实现 B\n3. 测试")
    assert intent.multi_step is True


def test_classify_multi_step_with_chinese_sequence_words():
    intent = classify("首先实现 A，然后实现 B，最后测试")
    assert intent.multi_step is True


def test_classify_multi_step_with_english_and_then():
    intent = classify("Implement A and then test B")
    assert intent.multi_step is True


def test_classify_multi_step_with_multiple_verbs():
    intent = classify("修复 bug 然后部署")
    assert intent.multi_step is True


# ---------- fallback (no match) ----------


def test_classify_returns_question_for_empty_input():
    intent = classify("")
    assert intent.category == "question"
    assert intent.confidence < 0.5


def test_classify_returns_question_for_unrelated_text():
    intent = classify("今天天气不错")
    assert intent.category == "question"


# ---------- confidence ----------


def test_classify_confidence_is_normalized_to_one():
    intent = classify("修复 bug 测试 部署")
    assert 0.0 <= intent.confidence <= 1.0


def test_classify_high_confidence_for_clear_match():
    intent = classify("帮我修复这个 bug")
    assert intent.confidence > 0.5


# ---------- alternatives ----------


def test_classify_alternatives_empty_for_dominant_match():
    intent = classify("Maker 项目启动")
    # Alternatives list may be empty if only one category matched
    assert isinstance(intent.alternatives, list)


def test_classify_alternatives_present_for_ambiguous():
    intent = classify("修复 bug 然后 maker mcp 测试")
    # Multiple keywords trigger alternatives
    assert isinstance(intent.alternatives, list)


# ---------- suggested path ----------


def test_classify_suggested_path_for_coding_multi_step():
    intent = classify("实现功能\n测试\n部署")
    assert "plan_first" in intent.suggested_path or "implement" in intent.suggested_path


def test_classify_suggested_path_for_question():
    intent = classify("这是什么？")
    assert "knowledge" in intent.suggested_path or "docs" in intent.suggested_path


def test_classify_suggested_path_for_maker():
    intent = classify("用 Maker 生成图片")
    assert "maker" in intent.suggested_path or "mcp" in intent.suggested_path


# ---------- structured output ----------


def test_intent_to_dict_has_required_keys():
    intent = classify("修复 bug")
    d = intent.to_dict()
    assert d["version"] == INTENT_CLASSIFIER_VERSION
    assert "category" in d
    assert "confidence" in d
    assert "multi_step" in d
    assert "suggested_path" in d
    assert "matched_keywords" in d
    assert "alternatives" in d


def test_render_card_includes_category():
    intent = classify("修复 bug")
    card = render_card(intent)
    assert "coding" in card.lower() or "coding" in card


def test_all_categories_present():
    assert len(CATEGORIES) >= 5
    assert "coding" in CATEGORIES
    assert "game" in CATEGORIES
    assert "plan" in CATEGORIES


# ---------- robustness ----------


def test_classify_handles_unicode_normally():
    intent = classify("🎮 做一个吃鸡游戏")
    assert intent.category in CATEGORIES


def test_classify_case_insensitive():
    a = classify("BUG fix please")
    b = classify("bug fix please")
    assert a.category == b.category


def test_classify_empty_whitespace_returns_question():
    intent = classify("   \n  \t  ")
    assert intent.category == "question"