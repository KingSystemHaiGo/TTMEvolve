"""Game-type knowledge base for TapTap Maker development.

Inspired by Abidingenuity's game design knowledge and Maker patterns.
Each entry is a structured rule the agent can search, render, or inject into
prompts when the user asks for game design help.
"""

from __future__ import annotations

from typing import Any, Dict, List


GAME_KNOWLEDGE_VERSION = "game-knowledge.v1"


GAME_TYPES: List[Dict[str, Any]] = [
    {
        "id": "endless_runner",
        "label": "无尽跑酷",
        "core_loop": "奔跑 → 障碍 → 收集金币 → 升级 → 跑得更远",
        "key_mechanics": [
            "自动前进 + 左右/跳跃控制",
            "程序生成或预制关卡块",
            "距离/分数累计，失败即结束",
            "升级系统：角色、解锁、皮肤",
        ],
        "starter_scenes": [
            "主菜单 / 角色选择",
            "游戏场景（无尽跑道）",
            "结算场景（最佳距离、奖励）",
        ],
        "starter_scripts": [
            "scripts/main.lua — 入口与全局状态",
            "scripts/player.lua — 角色控制",
            "scripts/level.lua — 关卡生成或滚动",
            "scripts/ui.lua — HUD 与结算",
        ],
        "common_pitfalls": [
            "障碍难度曲线不平滑 → 玩家秒退",
            "金币/升级回报感弱 → 留存差",
            "主角碰撞盒过大 → 误判死亡",
        ],
        "copy_anchors": [
            "开局引导：『左右滑动躲避障碍，收集金币解锁角色』",
            "失败文案：『差一点！再跑一次突破 XXX 米？』",
            "成就文案：『跑酷大师：连续跑出 1000 米！』",
        ],
    },
    {
        "id": "tower_defense",
        "label": "塔防",
        "core_loop": "建造防御塔 → 敌人波次来袭 → 击杀获金币 → 升级或重建",
        "key_mechanics": [
            "格子地图 + 路径规划",
            "多种塔类型（攻速/范围/单体/群体）",
            "敌人种类与抗性",
            "波次 + BOSS 关卡",
        ],
        "starter_scenes": [
            "关卡选择地图",
            "战斗场景",
            "结算场景",
        ],
        "starter_scripts": [
            "scripts/level.lua — 波次与路径",
            "scripts/tower.lua — 塔放置/升级",
            "scripts/enemy.lua — 敌人 AI",
            "scripts/economy.lua — 金币与奖励",
        ],
        "common_pitfalls": [
            "塔平衡数值崩坏 → 单一最优解",
            "敌人抗性表混乱 → 玩家无从下手",
        ],
        "copy_anchors": [
            "建造引导：『点击空地放置炮塔，金币不足时可拆除重建』",
            "胜利文案：『防御成功！下一波敌人更强，准备好了吗？』",
        ],
    },
    {
        "id": "match_three",
        "label": "三消",
        "core_loop": "交换方块 → 三连消除 → 连锁特效 → 计分",
        "key_mechanics": [
            "网格棋盘 + 拖拽交换",
            "消除规则（三连 / 特殊块 / 连锁）",
            "关卡目标（分数 / 收集 / 步数限制）",
            "道具系统（炸弹、刷子、交换）",
        ],
        "starter_scenes": [
            "关卡地图",
            "对战 / 单局场景",
            "结算场景",
        ],
        "starter_scripts": [
            "scripts/board.lua — 棋盘逻辑",
            "scripts/match.lua — 消除与连锁",
            "scripts/level.lua — 关卡目标",
            "scripts/ui.lua — 计分与道具栏",
        ],
        "common_pitfalls": [
            "无解局面 → 玩家挫败感",
            "连锁特效卡顿",
        ],
        "copy_anchors": [
            "开局：『交换相邻方块，三个连成一线即可消除』",
            "胜利文案：『完美消除！连击 X5！』",
        ],
    },
    {
        "id": "shooting_2d",
        "label": "2D 射击",
        "core_loop": "移动射击 → 击毁敌机 → 拾取道具 → BOSS 战",
        "key_mechanics": [
            "屏幕摇杆 / 触摸控制",
            "子弹类型、敌机 AI",
            "血量 / 护盾 / 炸弹",
            "关卡 + BOSS",
        ],
        "starter_scenes": [
            "战机选择",
            "关卡场景",
            "结算场景",
        ],
        "starter_scripts": [
            "scripts/player.lua — 战机控制",
            "scripts/enemy.lua — 敌机与子弹",
            "scripts/boss.lua — BOSS 战",
            "scripts/ui.lua — HUD",
        ],
        "common_pitfalls": [
            "弹幕过密 → 看不清",
            "碰撞检测抖动",
        ],
        "copy_anchors": [
            "开局：『拖动战机左右移动，自动射击来袭敌机』",
            "胜利文案：『击坠全部敌机！解锁战机 X』",
        ],
    },
    {
        "id": "idle_tycoon",
        "label": "放置 + 经营",
        "core_loop": "建造 → 自动产出 → 离线收益 → 升级扩张",
        "key_mechanics": [
            "建筑放置 + 升级",
            "离线收益 / 时间加速",
            "解锁新区域 / 业务线",
            "广告 / 奖励解锁",
        ],
        "starter_scenes": [
            "经营主场景",
            "解锁 / 升级面板",
        ],
        "starter_scripts": [
            "scripts/manager.lua — 经营主逻辑",
            "scripts/building.lua — 建筑升级",
            "scripts/offline.lua — 离线收益",
            "scripts/ui.lua — 经营面板",
        ],
        "common_pitfalls": [
            "前期数值太高 → 后期通货膨胀",
            "离线收益上限过低 → 玩家失望",
        ],
        "copy_anchors": [
            "开局：『建造你的第一家小店，自动营业赚金币』",
            "升级文案：『升级后产能提升 200%，还差 X 金币』",
        ],
    },
    {
        "id": "puzzle_logic",
        "label": "解谜",
        "core_loop": "观察 → 推理 → 操作 → 解开谜题 → 进入下一关",
        "key_mechanics": [
            "关卡谜题设计",
            "提示系统",
            "逐步解锁的复杂度",
        ],
        "starter_scenes": [
            "关卡选择",
            "解谜场景",
        ],
        "starter_scripts": [
            "scripts/level.lua — 关卡数据",
            "scripts/puzzle.lua — 谜题逻辑",
            "scripts/hint.lua — 提示系统",
        ],
        "common_pitfalls": [
            "谜题歧义 → 玩家不理解",
            "难度跳跃过大",
        ],
        "copy_anchors": [
            "开局：『点击物体触发机关，揭示隐藏路径』",
            "胜利文案：『真相揭晓！下一关更烧脑』",
        ],
    },
]


def all_game_types() -> List[Dict[str, Any]]:
    """Return the full list of supported game types."""
    return list(GAME_TYPES)


def find_game_type(game_type_id: str) -> Dict[str, Any]:
    """Return the entry for a given game-type id, or an empty dict."""
    for entry in GAME_TYPES:
        if entry.get("id") == game_type_id:
            return entry
    return {}


def search_game_knowledge(query: str, *, limit: int = 3) -> List[Dict[str, Any]]:
    """Word-boundary keyword search across labels, mechanics, pitfalls, copy."""
    import re
    lowered = (query or "").lower()
    if not lowered.strip():
        return []
    scored: List[Dict[str, Any]] = []
    for entry in GAME_TYPES:
        haystacks = [entry.get("label", ""), entry.get("id", "")]
        haystacks.extend(entry.get("key_mechanics") or [])
        haystacks.extend(entry.get("common_pitfalls") or [])
        haystacks.extend(entry.get("copy_anchors") or [])
        joined = "\n".join(str(item) for item in haystacks).lower()
        score = 0.0
        for word in lowered.split():
            if not word:
                continue
            if any("一" <= ch <= "鿿" for ch in word) or any(0x3400 <= ord(ch) <= 0x4DBF for ch in word):
                if word in joined:
                    score += 1.0
                continue
            if re.search(rf"\b{re.escape(word)}\b", joined):
                score += 1.0
        if score > 0:
            scored.append({"entry": entry, "score": score})
    scored.sort(key=lambda item: item["score"], reverse=True)
    return [item["entry"] for item in scored[:limit]]


def render_game_type_card(game_type_id: str) -> str:
    """Render a single game type as a UI card text."""
    entry = find_game_type(game_type_id)
    if not entry:
        return ""
    lines = [
        f"# {entry.get('label')} ({entry.get('id')})",
        f"\n核心循环：{entry.get('core_loop', '')}",
        "\n关键机制：",
    ]
    for item in entry.get("key_mechanics") or []:
        lines.append(f"  - {item}")
    if entry.get("starter_scenes"):
        lines.append("\n必备场景：")
        for item in entry.get("starter_scenes"):
            lines.append(f"  - {item}")
    if entry.get("starter_scripts"):
        lines.append("\n初始脚本：")
        for item in entry.get("starter_scripts"):
            lines.append(f"  - {item}")
    if entry.get("common_pitfalls"):
        lines.append("\n常见陷阱：")
        for item in entry.get("common_pitfalls"):
            lines.append(f"  - {item}")
    if entry.get("copy_anchors"):
        lines.append("\n文案锚点：")
        for item in entry.get("copy_anchors"):
            lines.append(f"  - {item}")
    return "\n".join(lines)


def suggest_game_type_for(task: str) -> List[str]:
    """Heuristic suggestion of game type ids from a free-form task description."""
    lowered = (task or "").lower()
    suggestions: List[str] = []
    for game_type_id, words in _SUGGEST_KEYWORDS.items():
        if any(word.lower() in lowered for word in words):
            suggestions.append(game_type_id)
    return suggestions


# Module-level lookup table — built once instead of on every call.
_SUGGEST_KEYWORDS: Dict[str, List[str]] = {
    "endless_runner": ["跑酷", "runner", "jump", "躲避"],
    "tower_defense": ["塔防", "tower", "defense", "炮塔"],
    "match_three": ["三消", "match", "消除", "方块"],
    "shooting_2d": ["射击", "shoot", "弹幕", "战机"],
    "idle_tycoon": ["放置", "经营", "idle", "tycoon"],
    "puzzle_logic": ["解谜", "puzzle", "机关"],
}