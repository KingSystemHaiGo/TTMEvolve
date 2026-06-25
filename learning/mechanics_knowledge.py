"""Mechanics knowledge base — core gameplay loops, progression, rewards.

Each rule is a single sentence the agent can quote when designing or
reviewing a Maker game's economy. The intent is to encode the most
common balance gotchas so the agent catches them early.
"""

from __future__ import annotations

from typing import Any, Dict, List


MECHANICS_VERSION = "mechanics.v1"


CORE_LOOP_RULES = [
    "Every game needs ONE core loop that the player can repeat within 5-15 seconds.",
    "A core loop must contain a clear feedback signal (visual + audio + numeric) within 1 second of completion.",
    "Secondary loops (progression, social, meta) should reinforce the core loop, not compete with it.",
]


PROGRESSION_RULES = [
    "Difficulty must scale with the player's growth metric, not absolute time, or new players get stuck.",
    "Each progression tier should introduce ONE new mechanic — never bundle 2-3 unknown systems at once.",
    "Player power and enemy power should track within a constant ratio (e.g. 1.0x to 1.2x per level); if the ratio drifts above 1.5x the difficulty is unfair.",
]


REWARD_RULES = [
    "Rewards should arrive within 30 seconds of meaningful action — long delays weaken dopamine loops.",
    "Daily rewards must have a 'visible catch-up' rule so returning players don't feel punished.",
    "If a reward requires watching an ad, the reward should be ≥ 2x the equivalent free reward, otherwise the player resents the interruption.",
]


ECONOMY_RULES = [
    "Soft currency (coins) inflation should be modelled over 30 days; if a late-game coin cost exceeds early-game by >100x, the price ladder is broken.",
    "Hard currency (gems) should never be the only path past a hard wall — there must be a free fallback.",
    "Sinks (consumable costs) and faucets (sources) must balance within ±10% per active player-day.",
]


RETENTION_RULES = [
    "First session: hook the player with a tutorial that ends in a tiny win (first upgrade, first clear, first skin).",
    "Day-1 retention is driven by 'one more run' feel; day-7 retention is driven by an unlock or social hook.",
    "Push notifications should fire at a player's habitual play time, not at midnight UTC.",
]


def all_mechanics_rules() -> Dict[str, List[str]]:
    return {
        "core_loop": list(CORE_LOOP_RULES),
        "progression": list(PROGRESSION_RULES),
        "reward": list(REWARD_RULES),
        "economy": list(ECONOMY_RULES),
        "retention": list(RETENTION_RULES),
    }


def mechanics_rules_for(category: str) -> List[str]:
    return {
        "core_loop": CORE_LOOP_RULES,
        "progression": PROGRESSION_RULES,
        "reward": REWARD_RULES,
        "economy": ECONOMY_RULES,
        "retention": RETENTION_RULES,
    }.get(category, [])


def render_balance_card() -> str:
    """Render a single balance/review card covering all rule categories."""
    lines = ["# Maker 平衡设计速查", ""]
    for category, rules in all_mechanics_rules().items():
        lines.append(f"## {category}")
        for rule in rules:
            lines.append(f"- {rule}")
        lines.append("")
    return "\n".join(lines)


def review_balance_card(proposed_features: List[str]) -> List[Dict[str, Any]]:
    """Given a list of proposed features, return rule matches the agent should warn about.

    This is a deterministic keyword scan — useful for the planning phase to
    catch obvious misses before code is written.
    """
    warnings: List[Dict[str, Any]] = []
    text = "\n".join(proposed_features).lower()
    if "广告" in text and "奖励" in text:
        warnings.append({
            "code": "ad_reward_check",
            "message": "检测到『广告 + 奖励』组合，请确认广告奖励 ≥ 免费奖励 2 倍",
            "suggested_fix": "在 reward 表中明确广告倍率",
        })
    if "宝石" in text or "钻石" in text:
        warnings.append({
            "code": "hard_currency_wall",
            "message": "硬通货（宝石/钻石）出现，请确保不存在『只能付费』的死路",
            "suggested_fix": "为每个硬通货关卡提供免费替代路径",
        })
    if "金币" in text or "coins" in text:
        warnings.append({
            "code": "soft_currency_check",
            "message": "金币存在，请建模 30 天通胀，避免后期金币数字失控",
            "suggested_fix": "用金币 → 钻石 → 时间的三层结构锚定",
        })
    if "新手" in text or "引导" in text or "tutorial" in text:
        warnings.append({
            "code": "tutorial_end_with_win",
            "message": "新手引导存在，请确认结束时玩家获得一个小胜利",
            "suggested_fix": "在引导最后解锁第一个角色/皮肤/技能",
        })
    return warnings