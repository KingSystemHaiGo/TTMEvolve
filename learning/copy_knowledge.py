"""Copywriting knowledge base for TapTap Maker games.

Structured rules the agent follows when generating in-game text:
- onboarding copy
- tutorial copy
- failure / victory copy
- achievement copy
- notification copy

The goal is short, vivid, encouraging, and never condescending. Voice is
casual but respectful, addressing the player in second person.
"""

from __future__ import annotations

from typing import Any, Dict, List


COPY_KNOWLEDGE_VERSION = "copy-knowledge.v1"


VOICE_GUIDELINES = [
    "Use second person addressing the player directly.",
    "Prefer concrete verbs over abstract nouns (跑/打/算/解锁 instead of 进行/操作).",
    "Keep sentences short (≤ 20 characters for short prompts).",
    "Avoid exclamation spam: one exclamation per paragraph at most.",
    "Never call the player names like 菜鸟 unless the game is humorous and committed.",
    "When a player fails, encourage rather than scold. (差一点 / 再试一次 / 越挫越勇)",
    "When a player succeeds, anchor on the action: 击中 / 突破 / 解锁.",
    "Numbers in achievements should feel real (突破 1000 米) not inflated (突破 100000000 米).",
]


# Banned player-facing words. Kept as a module-level constant so the list
# is easy to audit and extend; tests assert against this same set.
BANNED_WORDS: List[str] = ["菜鸟", "废物", "弱鸡"]


# Length threshold (in characters) above which the copy is considered too long
# for a short prompt.
MAX_COPY_LENGTH: int = 80


# Maximum number of exclamations (ASCII + full-width) before we flag spam.
MAX_EXCLAMATIONS: int = 2


COPY_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    "onboarding": [
        {"slot": "title", "example": "欢迎来到 {game_name}", "pattern": "欢迎来到 {game_name}"},
        {"slot": "subtitle", "example": "三步上手，即刻开战", "pattern": "{benefit_in_one_line}"},
        {"slot": "cta", "example": "开始游戏", "pattern": "开始游戏"},
    ],
    "tutorial": [
        {"slot": "step1", "example": "左右滑动屏幕，控制角色移动", "pattern": "{control_hint}"},
        {"slot": "step2", "example": "点击金币可以收集奖励", "pattern": "{collect_hint}"},
        {"slot": "step3", "example": "躲避障碍，跑得越远分数越高", "pattern": "{avoid_hint}"},
    ],
    "victory": [
        {"slot": "headline", "example": "完美通关！", "pattern": "{positive_adjective}通关！"},
        {"slot": "stat", "example": "你跑出了 1234 米", "pattern": "你{verb}了 {number} {unit}"},
        {"slot": "cta", "example": "再来一局", "pattern": "再来一局"},
    ],
    "failure": [
        {"slot": "headline", "example": "差一点！", "pattern": "{empathy_phrase}！"},
        {"slot": "stat", "example": "本次跑出 999 米", "pattern": "本次{verb}了 {number} {unit}"},
        {"slot": "cta", "example": "再试一次", "pattern": "再试一次"},
        {"slot": "encouragement", "example": "每一次失败都让你更接近最佳记录", "pattern": "{short_encouragement}"},
    ],
    "achievement": [
        {"slot": "headline", "example": "成就解锁：跑酷大师", "pattern": "成就解锁：{achievement_name}"},
        {"slot": "reward", "example": "奖励：100 金币", "pattern": "奖励：{reward_summary}"},
        {"slot": "share", "example": "炫耀给好友", "pattern": "分享给好友"},
    ],
    "notification": [
        {"slot": "energy_full", "example": "体力已回满，快回来继续挑战", "pattern": "{resource_name}已回满，{cta}"},
        {"slot": "daily_reward", "example": "今日签到：领取 50 金币", "pattern": "今日签到：{reward}"},
        {"slot": "new_unlock", "example": "新角色【闪电小子】已解锁", "pattern": "新{content_type}【{name}】已解锁"},
    ],
}


def all_voice_guidelines() -> List[str]:
    return list(VOICE_GUIDELINES)


def templates_for(category: str) -> List[Dict[str, Any]]:
    """Return the slot definitions for a given copy category."""
    return list(COPY_TEMPLATES.get(category, []))


def render_slot(category: str, slot: str, **values: Any) -> str:
    """Render a single slot from a category using the pattern and provided values."""
    for entry in COPY_TEMPLATES.get(category, []):
        if entry.get("slot") == slot:
            try:
                return entry["pattern"].format(**values)
            except KeyError:
                return entry.get("example", "")
    return ""


def render_category_card(category: str) -> str:
    """Render all slots for a category as a UI card text."""
    templates = COPY_TEMPLATES.get(category)
    if not templates:
        return ""
    lines = [f"# {category}", ""]
    for entry in templates:
        lines.append(f"- {entry['slot']}: {entry['pattern']}  e.g. \"{entry['example']}\"")
    return "\n".join(lines)


def all_categories() -> List[str]:
    return list(COPY_TEMPLATES.keys())


def critique_copy(text: str) -> List[Dict[str, Any]]:
    """Lightweight, deterministic critique of a player-facing copy string.

    Returns a list of issue dicts. An empty list means the copy passed all
    checks — callers should treat `len(result) == 0` as the success signal
    rather than looking for an "ok" sentinel.
    """
    issues: List[Dict[str, Any]] = []
    if not text:
        return [{"code": "empty", "message": "文案为空", "suggested_fix": "使用文案模板填充内容"}]
    if len(text) > MAX_COPY_LENGTH:
        issues.append({
            "code": "too_long",
            "message": f"文案超过 {MAX_COPY_LENGTH} 字，玩家可能跳读",
            "suggested_fix": "拆分成 2-3 段，每段 ≤ 20 字",
        })
    exclamation_count = text.count("!") + text.count("！")
    if exclamation_count > MAX_EXCLAMATIONS:
        issues.append({
            "code": "exclamation_spam",
            "message": "感叹号过多，会显得吵闹",
            "suggested_fix": "保留 1 个感叹号，其余改用句号",
        })
    for word in BANNED_WORDS:
        if word in text:
            issues.append({
                "code": "insulting_word",
                "message": f"文案包含冒犯性词汇「{word}」",
                "suggested_fix": "改用鼓励或中性的描述",
            })
    return issues