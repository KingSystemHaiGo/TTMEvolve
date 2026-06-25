"""Successful Maker-style game cases for pattern mining.

Each case captures:
- game_type: the closest entry in game_knowledge.GAME_TYPES
- standout_mechanic: the one thing that made the game memorable
- lesson: the takeaway the agent should remember when designing similar games
- avoid: the common pitfall this case shows how to dodge

These cases are intentionally compact so they fit cheaply into context.
"""

from __future__ import annotations

from typing import Any, Dict, List


MAKER_CASES_VERSION = "maker-cases.v1"


CASES: List[Dict[str, Any]] = [
    {
        "id": "flappy-bird-style",
        "game_type": "endless_runner",
        "standout_mechanic": "Single tap, instant failure, shareable score",
        "lesson": "极致简单 + 极强挫败感 + 朋友圈炫耀是病毒传播的黄金三角",
        "avoid": "不要试图给这种游戏加复杂教程，玩家会立刻流失",
    },
    {
        "id": "candy-crush-style",
        "game_type": "match_three",
        "standout_mechanic": "关卡目标多样化 + 步数限制 + 社交求助",
        "lesson": "三消的长期留存来自关卡设计师的节奏感，而非消除算法本身",
        "avoid": "无解局面是三消头号杀手，必须提供重置或提示",
    },
    {
        "id": "kingdom-rush-style",
        "game_type": "tower_defense",
        "standout_mechanic": "英雄单位 + 多种塔搭配 + 战场英雄技能",
        "lesson": "在经典机制上叠加一层'英雄'即可大幅提升策略深度",
        "avoid": "塔种类过多会让玩家陷入搭配瘫痪，控制在 4-6 种",
    },
    {
        "id": "airattack-style",
        "game_type": "shooting_2d",
        "standout_mechanic": "炸弹清屏 + 护盾道具 + 升级战机",
        "lesson": "弹幕游戏需要定期给玩家'喘息+爆发'节奏",
        "avoid": "弹幕过密+碰撞盒不准=劝退",
    },
    {
        "id": "idle-tiny-tycoon",
        "game_type": "idle_tycoon",
        "standout_mechanic": "离线收益 + 解锁新店 + 简单合成",
        "lesson": "放置游戏的关键是让玩家感觉'离开也在变强'",
        "avoid": "不要让前期产出太慢，否则玩家在第 5 分钟就走了",
    },
    {
        "id": "monument-valley-style",
        "game_type": "puzzle_logic",
        "standout_mechanic": "视觉错觉 + 一句话指引 + 无惩罚",
        "lesson": "解谜游戏的沉浸感来自美术 + 音乐 + 不催促玩家",
        "avoid": "不要给解谜游戏加倒计时或血量",
    },
]


def all_cases() -> List[Dict[str, Any]]:
    return list(CASES)


def cases_for(game_type_id: str) -> List[Dict[str, Any]]:
    return [case for case in CASES if case.get("game_type") == game_type_id]


def render_case_card(case_id: str) -> str:
    for case in CASES:
        if case.get("id") == case_id:
            return (
                f"# {case['id']} ({case['game_type']})\n"
                f"亮点机制：{case['standout_mechanic']}\n"
                f"启示：{case['lesson']}\n"
                f"避坑：{case['avoid']}"
            )
    return ""


def render_all_case_cards() -> str:
    lines = ["# Maker 案例库", ""]
    for case in CASES:
        lines.append(
            f"- **{case['id']}** ({case['game_type']})：{case['standout_mechanic']} — "
            f"启示：{case['lesson']}"
        )
    return "\n".join(lines)


def design_lesson_for(task: str) -> str:
    """Heuristic: pick a case lesson based on the task description."""
    lowered = (task or "").lower()
    for case in CASES:
        game_type = case.get("game_type", "")
        keywords = {
            "endless_runner": ["跑酷", "runner", "躲避"],
            "tower_defense": ["塔防", "tower", "炮塔"],
            "match_three": ["三消", "消除"],
            "shooting_2d": ["射击", "弹幕", "战机"],
            "idle_tycoon": ["放置", "经营"],
            "puzzle_logic": ["解谜", "puzzle"],
        }
        if any(word.lower() in lowered for word in keywords.get(game_type, [])):
            return case.get("lesson", "")
    return ""