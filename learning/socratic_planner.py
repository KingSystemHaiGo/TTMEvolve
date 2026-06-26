"""Socratic game-design planner — guided Q&A for Maker projects.

Inspired by Abidingenuity's `socratic.py`. The planner holds a stack of
structured questions the agent walks through with the user, one at a time.
Once enough answers are collected, it produces a compact Game Design
Document (GDD) summary.

The questions are deterministic — chosen by rule, not by LLM — so the
flow is testable and reproducible.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


SOCRATIC_VERSION = "socratic-planner.v1"


SOCRATIC_QUESTIONS: List[Dict[str, Any]] = [
    {
        "id": "core_loop",
        "prompt": "用一个短句描述玩家在 30 秒内反复做的核心动作是什么？",
        "examples": ["跳跃躲避障碍", "三消获得连击", "建造炮塔击退敌人"],
    },
    {
        "id": "target_player",
        "prompt": "这款游戏的目标玩家是谁？（年龄段 + 场景）",
        "examples": ["通勤地铁的上班族", "学生课间 5 分钟", "睡前休闲玩家"],
    },
    {
        "id": "session_length",
        "prompt": "单局游戏时长控制在多久？",
        "examples": ["30 秒-2 分钟", "3-5 分钟", "10-15 分钟"],
    },
    {
        "id": "progression",
        "prompt": "玩家长期玩下去的动力来自哪里？",
        "examples": ["解锁新角色", "排行榜冲榜", "剧情章节解锁"],
    },
    {
        "id": "art_style",
        "prompt": "美术风格倾向？",
        "examples": ["像素风", "卡通风", "极简几何风"],
    },
    {
        "id": "monetization",
        "prompt": "变现方式？",
        "examples": ["广告 + 激励视频", "皮肤付费", "月卡订阅"],
    },
]


def all_questions() -> List[Dict[str, Any]]:
    return list(SOCRATIC_QUESTIONS)


def next_question(answers: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Return the first unanswered question, or None if all answered."""
    for question in SOCRATIC_QUESTIONS:
        if question["id"] not in answers or not answers[question["id"]].strip():
            return question
    return None


def build_gdd(answers: Dict[str, str]) -> Dict[str, Any]:
    """Build a compact Game Design Document from the collected answers."""
    missing = [q["id"] for q in SOCRATIC_QUESTIONS if not answers.get(q["id"], "").strip()]
    if missing:
        return {
            "version": SOCRATIC_VERSION,
            "complete": False,
            "missing": missing,
            "gdd": {},
        }
    return {
        "version": SOCRATIC_VERSION,
        "complete": True,
        "missing": [],
        "gdd": {
            "core_loop": answers["core_loop"],
            "target_player": answers["target_player"],
            "session_length": answers["session_length"],
            "progression": answers["progression"],
            "art_style": answers["art_style"],
            "monetization": answers["monetization"],
            "summary": _summary(answers),
        },
    }


def _summary(answers: Dict[str, str]) -> str:
    # Build the summary dynamically so adding a new SOCRATIC_QUESTION
    # does not require updating this helper. Each question contributes one
    # sentence keyed by its id.
    sentence_map = {
        "core_loop": lambda v: f"核心循环：{v}。",
        "target_player": lambda v: f"面向{v}的玩家。",
        "session_length": lambda v: f"单局时长{v}。",
        "progression": lambda v: f"长期动力来自{v}。",
        "art_style": lambda v: f"美术风格：{v}。",
        "monetization": lambda v: f"变现方式：{v}。",
    }
    parts: List[str] = []
    for question in SOCRATIC_QUESTIONS:
        qid = question["id"]
        value = answers.get(qid, "")
        formatter = sentence_map.get(qid)
        if formatter and value:
            parts.append(formatter(value))
    return "".join(parts)


def render_question_card(question: Dict[str, Any]) -> str:
    """Render a single question as a UI card."""
    lines = [f"# {question['prompt']}"]
    lines.append("\n可选示例：")
    for example in question.get("examples") or []:
        lines.append(f"  - {example}")
    return "\n".join(lines)


def render_session_card(answers: Dict[str, str]) -> str:
    """Render the current session state as a UI card."""
    lines = ["# Socratic Planner 当前进度", ""]
    for question in SOCRATIC_QUESTIONS:
        answer = answers.get(question["id"], "")
        status = "✓" if answer.strip() else "·"
        lines.append(f"{status} **{question['prompt']}**")
        if answer:
            lines.append(f"  → {answer}")
    return "\n".join(lines)