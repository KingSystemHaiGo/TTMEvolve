"""门槛 0：意图分类器（COS 协议 §三）

每次用户输入后立即执行：
  1. 分类用户意图（Coding / Game / Plan / Project / Ops / Maker / Question）
  2. 判断单步 vs 多步
  3. 给出建议的处理路径

设计原则：
- 纯函数，无 I/O
- 可测试（关键词 + 模式匹配 + LLM fallback 可选）
- 输出结构化 dict，便于日志/记忆/Settings 面板消费
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


INTENT_CLASSIFIER_VERSION = "intent-classifier.v1"


CATEGORIES = (
    "coding",      # 实现 / 修复 / 重构 / 加功能 / 测试
    "game",        # 游戏 / 策划 / 文案 / Maker / 案例
    "plan",        # 路线图 / 规划 / 下一步 / 计划
    "project",     # 发布 / tag / 版本 / 文档
    "ops",         # 部署 / 打包 / 内嵌 / 启动 / 修复脚本
    "maker",       # Maker MCP / Maker 项目 / Maker 工具
    "question",    # 询问 / 解释 / 为什么
)


CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "coding": ["实现", "修复", "重构", "加功能", "测试", "bug", "fix", "implement", "refactor", "add feature"],
    "game": ["游戏", "策划", "文案", "案例", "玩法", "数值", "平衡", "策划", "game", "design"],
    "plan": ["路线图", "规划", "下一步", "计划", "roadmap", "plan"],
    "project": ["发布", "tag", "版本", "文档", "release", "version"],
    "ops": ["部署", "打包", "内嵌", "启动", "修复脚本", "deploy", "build", "package", "portable", "start"],
    "maker": ["maker", "mcp", "taptap maker", "tapmaker", "maker 项目", "maker 工具"],
    "question": ["为什么", "是什么", "怎么", "如何", "why", "what", "how", "?"],
}


@dataclass
class Intent:
    """Structured result of intent classification."""

    category: str
    confidence: float
    multi_step: bool
    suggested_path: str
    matched_keywords: List[str]
    alternatives: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": INTENT_CLASSIFIER_VERSION,
            "category": self.category,
            "confidence": round(self.confidence, 3),
            "multi_step": self.multi_step,
            "suggested_path": self.suggested_path,
            "matched_keywords": list(self.matched_keywords),
            "alternatives": list(self.alternatives),
        }


def _score_category(text_lower: str, keywords: List[str]) -> tuple:
    """Return (score, matched_keywords)."""
    matched: List[str] = []
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in text_lower:
            matched.append(kw)
    return len(matched), matched


def _looks_multi_step(text: str) -> bool:
    """Heuristics: text contains multiple sentences / lines / conjunction words."""
    multi_indicators = [
        "\n",  # multi-line input
        " 然后 ", " 然后再 ", "接着 ", " 之后 ",
        " and ", " then ", " after ",
        "1.", "2.", "3.",  # numbered steps
        "、",  # 中文列表
        "首先", "其次", "最后", "接着",
        "first", "second", "third", "finally",
    ]
    text_lower = text.lower()
    for indicator in multi_indicators:
        if indicator in text or indicator in text_lower:
            return True
    # 多个动词暗示多步
    action_verbs = ("实现", "创建", "修复", "重构", "测试", "部署", "打包", "发布", "添加", "删除")
    verb_count = sum(1 for v in action_verbs if v in text)
    return verb_count >= 2


def _suggested_path(category: str, multi_step: bool) -> str:
    paths = {
        "coding": "plan_first_then_implement" if multi_step else "single_tool_call",
        "game": "consult_game_knowledge_then_implement",
        "plan": "update_roadmap_then_notify_user",
        "project": "prepare_release_then_tag",
        "ops": "run_build_script_then_verify",
        "maker": "maker_briefing_then_mcp_call",
        "question": "consult_knowledge_base_or_docs",
    }
    return paths.get(category, "ask_user_for_clarification")


def classify(user_input: str, *, context: Optional[Dict[str, Any]] = None) -> Intent:
    """Classify a user input into an Intent.

    Args:
        user_input: raw text from the user.
        context: optional dict (e.g. previous category, session state) to influence
            classification. Currently unused but kept for future LLM fallback.
    """
    text = user_input or ""
    text_lower = text.lower()
    scored: List[tuple] = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        score, matched = _score_category(text_lower, keywords)
        if score > 0:
            scored.append((category, score, matched))
    scored.sort(key=lambda item: item[1], reverse=True)

    if not scored:
        # Default to "question" when nothing matches.
        return Intent(
            category="question",
            confidence=0.2,
            multi_step=_looks_multi_step(text),
            suggested_path=_suggested_path("question", _looks_multi_step(text)),
            matched_keywords=[],
            alternatives=[],
        )

    top_category, top_score, top_matched = scored[0]
    total_score = sum(item[1] for item in scored) or 1
    confidence = min(1.0, top_score / total_score)
    multi_step = _looks_multi_step(text)

    alternatives = [
        {
            "category": category,
            "score": score,
            "matched": matched,
        }
        for category, score, matched in scored[1:3]
    ]

    return Intent(
        category=top_category,
        confidence=confidence,
        multi_step=multi_step,
        suggested_path=_suggested_path(top_category, multi_step),
        matched_keywords=top_matched,
        alternatives=alternatives,
    )


def render_card(intent: Intent) -> str:
    """Render an Intent as a UI card text."""
    lines = [f"# Intent Classification"]
    lines.append(f"\n类别：{intent.category}")
    lines.append(f"置信度：{intent.confidence}")
    lines.append(f"多步：{'是' if intent.multi_step else '否'}")
    lines.append(f"建议路径：{intent.suggested_path}")
    if intent.matched_keywords:
        lines.append(f"\n匹配关键词：{', '.join(intent.matched_keywords)}")
    if intent.alternatives:
        lines.append("\n备选：")
        for alt in intent.alternatives:
            lines.append(f"  - {alt['category']} (score={alt['score']})")
    return "\n".join(lines)