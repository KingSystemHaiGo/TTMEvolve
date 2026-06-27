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
COS_GATE_VERSION = "cos-gate.v1"
COS_SOURCE_DOC = r"D:\CC\taptap-maker-project\docs\cos-collaboration-os.md"


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


COS_TASK_LABELS = {
    "bug_fix": "bug修复",
    "new_feature": "新功能",
    "adjustment_optimization": "调整优化",
    "refactor_optimization": "重构优化",
    "pure_discussion": "纯讨论",
}

COS_UNDERSTANDING_LABELS = {
    "confirmed": "已确认",
    "needs_confirmation": "待确认",
    "decompose_vague": "模糊拆解中",
}

COS_REFACTOR_KEYWORDS = (
    "重构", "架构", "解耦", "模块", "性能", "运行效率", "响应速度", "通信总线",
    "代码重组", "审计", "rag", "向量", "知识库", "记忆加载", "agent层",
    "核心运行层", "学习转化层", "控制论", "系统性", "context", "vector",
    "memory", "knowledge base", "decouple", "architecture", "performance",
    "audit", "event bus",
)
COS_BUG_KEYWORDS = (
    "bug", "修复", "报错", "错误", "失败", "崩溃", "异常", "不工作",
    "fix", "broken", "error", "fail", "crash",
)
COS_FEATURE_KEYWORDS = (
    "新功能", "新增", "增加", "添加", "实现", "创建", "支持", "接入",
    "做一个", "生成", "build", "create", "implement", "add",
)
COS_ADJUST_KEYWORDS = (
    "调整", "优化一下", "微调", "美化", "调参", "改参数", "提速",
    "改善", "改一下", "tune", "polish",
)
COS_DISCUSSION_KEYWORDS = (
    "讨论", "想法", "分析", "解释", "为什么", "是什么", "如何", "怎么",
    "聊聊", "question", "why", "what", "how",
)
COS_VAGUE_KEYWORDS = (
    "做好一点", "好玩一点", "优化一下", "感觉不对", "参考", "弄一下",
    "搞一下", "完善一下", "提升一下",
)
COS_STRATEGIC_KEYWORDS = (
    "代码审计", "模块解耦", "内部通信总线", "运行效率", "响应速度", "向量记忆",
    "rag", "知识库", "记忆加载", "agent层", "核心运行层", "学习转化层",
    "cos", "多agent", "共享记忆", "工程控制论", "项目管理", "超长任务",
    "上下文自动管理", "系统性",
)


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


@dataclass
class CosGate:
    """COS Gate 0 classification result."""

    task_type: str
    level: str
    mode: str
    understanding_status: str
    declaration: str
    required_gates: List[str]
    intent: Dict[str, Any]
    matched_keywords: Dict[str, List[str]]
    process_template: str
    post_requirements: Dict[str, Any]
    truthfulness: Dict[str, Any]
    vague_protocol: Dict[str, Any]
    multi_agent: Dict[str, Any]
    project_management: Dict[str, Any]
    trigger: str
    source_doc: str = COS_SOURCE_DOC

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": COS_GATE_VERSION,
            "source_doc": self.source_doc,
            "trigger": self.trigger,
            "task_type": self.task_type,
            "task_type_label": COS_TASK_LABELS.get(self.task_type, self.task_type),
            "level": self.level,
            "mode": self.mode,
            "understanding_status": self.understanding_status,
            "understanding_label": COS_UNDERSTANDING_LABELS.get(
                self.understanding_status,
                self.understanding_status,
            ),
            "declaration": self.declaration,
            "required_gates": list(self.required_gates),
            "process_template": self.process_template,
            "intent": dict(self.intent),
            "matched_keywords": {
                key: list(value)
                for key, value in self.matched_keywords.items()
            },
            "post_requirements": dict(self.post_requirements),
            "truthfulness": dict(self.truthfulness),
            "vague_protocol": dict(self.vague_protocol),
            "multi_agent": dict(self.multi_agent),
            "project_management": dict(self.project_management),
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


def _matched_keywords(text_lower: str, keywords: tuple[str, ...]) -> List[str]:
    return [kw for kw in keywords if kw.lower() in text_lower]


def _cos_task_type(text_lower: str) -> tuple[str, Dict[str, List[str]]]:
    matched = {
        "refactor_optimization": _matched_keywords(text_lower, COS_REFACTOR_KEYWORDS),
        "bug_fix": _matched_keywords(text_lower, COS_BUG_KEYWORDS),
        "new_feature": _matched_keywords(text_lower, COS_FEATURE_KEYWORDS),
        "adjustment_optimization": _matched_keywords(text_lower, COS_ADJUST_KEYWORDS),
        "pure_discussion": _matched_keywords(text_lower, COS_DISCUSSION_KEYWORDS),
    }
    if matched["refactor_optimization"]:
        return "refactor_optimization", matched
    if matched["bug_fix"]:
        return "bug_fix", matched
    if matched["new_feature"]:
        return "new_feature", matched
    if matched["adjustment_optimization"]:
        return "adjustment_optimization", matched
    if matched["pure_discussion"]:
        return "pure_discussion", matched
    return "pure_discussion", matched


def _numbered_or_list_count(text: str) -> int:
    markers = ["1.", "2.", "3.", "4.", "5.", "一，", "二，", "三，", "四，", "五，", "六，", "七，", "八，", "九，"]
    return sum(1 for marker in markers if marker in text)


def _cos_level(text: str, task_type: str, multi_step: bool, matched: Dict[str, List[str]]) -> str:
    text_lower = text.lower()
    strategic_hits = _matched_keywords(text_lower, COS_STRATEGIC_KEYWORDS)
    list_count = _numbered_or_list_count(text)
    refactor_hit_count = len(matched.get("refactor_optimization", []))
    if len(text) >= 260 or list_count >= 6 or len(strategic_hits) >= 3 or refactor_hit_count >= 4:
        return "XL"
    if len(text) >= 140 or list_count >= 3 or len(strategic_hits) >= 2:
        return "L"
    if multi_step or task_type in {"new_feature", "refactor_optimization"} or len(text) >= 48:
        return "M"
    return "S"


def _cos_understanding_status(text_lower: str, intent: Intent) -> str:
    vague_hits = _matched_keywords(text_lower, COS_VAGUE_KEYWORDS)
    if vague_hits:
        return "decompose_vague"
    if not text_lower.strip() or intent.confidence < 0.25:
        return "needs_confirmation"
    return "confirmed"


def _cos_mode(task_type: str, level: str) -> str:
    if level in {"L", "XL"}:
        return "System 2"
    if task_type in {"new_feature", "refactor_optimization", "pure_discussion"}:
        return "System 2"
    if task_type in {"bug_fix", "adjustment_optimization"} and level in {"S", "M"}:
        return "System 1"
    return "混合"


def _cos_required_gates(
    *,
    task_type: str,
    level: str,
    mode: str,
    understanding_status: str,
) -> tuple[List[str], str]:
    if understanding_status == "decompose_vague":
        return (
            ["GATE_0_DECLARE", "DECOMPOSE_VAGUE", "USER_CONFIRM", "SUBTASK_GATE_0"],
            "vague_instruction_protocol",
        )
    if task_type == "pure_discussion":
        return (
            ["GATE_0_DECLARE", "UNDERSTAND", "DISCUSS", "POST_MEM_IF_DECISION", "POST_SYNC_IF_SUBSTANTIVE"],
            "discussion_no_todowrite",
        )
    if mode == "System 1" and level == "S":
        return (
            ["GATE_0_DECLARE", "UNDERSTAND", "DEV", "BUILD", "POST_GIT", "POST_MEM", "POST_SYNC"],
            "system1_six_step",
        )
    if mode == "System 1":
        return (
            ["GATE_0_DECLARE", "TODO_WRITE", "UNDERSTAND", "DOC_READ", "DEV", "REV", "BUILD", "POST_GIT", "POST_MEM", "POST_SYNC", "HEALTH_CHECK"],
            "system1_m_eleven_step",
        )
    return (
        ["GATE_0_DECLARE", "TODO_WRITE", "UNDERSTAND", "CONFIRM", "DOC_READ", "RESEARCH", "PROPOSE", "DEV", "REV", "BUILD", "POST_GIT", "POST_MEM", "POST_SYNC", "HEALTH_CHECK"],
        "system2_full",
    )


def _cos_vague_protocol(text_lower: str, understanding_status: str) -> Dict[str, Any]:
    if understanding_status != "decompose_vague":
        return {"active": False, "proposed_subtasks": []}
    if "战斗" in text_lower or "combat" in text_lower:
        subtasks = [
            {"level": "M", "title": "确认战斗体验目标和当前痛点"},
            {"level": "S", "title": "检查并调整伤害/节奏数值"},
            {"level": "M", "title": "补足打击反馈、音效或屏幕反馈"},
            {"level": "S", "title": "用一次可复现试玩验证手感变化"},
        ]
    else:
        subtasks = [
            {"level": "S", "title": "确认目标模块和可观察问题"},
            {"level": "M", "title": "拆出收益最高的一项具体改动"},
            {"level": "S", "title": "定义验证方式和完成证据"},
        ]
    return {
        "active": True,
        "rule": "Decompose vague input into 2-5 candidate subtasks, rank by value/cost, ask confirmation before execution.",
        "proposed_subtasks": subtasks,
    }


def _cos_multi_agent(level: str) -> Dict[str, Any]:
    if level in {"S", "M"}:
        return {
            "recommendation": "not_recommended",
            "rule": "S/M tasks stay on the main thread unless the user explicitly asks otherwise.",
        }
    if level == "L":
        return {
            "recommendation": "optional",
            "rule": "Independent review, docs, or asset subtasks may be delegated when available.",
        }
    return {
        "recommendation": "encouraged",
        "rule": "L/XL tasks should consider independent reviewers or parallel research/docs/assets, with main-thread merge and POST.",
    }


def classify_cos_gate(
    user_input: str,
    *,
    trigger: str = "user_input",
    context: Optional[Dict[str, Any]] = None,
) -> CosGate:
    """Classify a task according to COS Gate 0 without LLM or I/O."""
    intent = classify(user_input, context=context)
    text = user_input or ""
    text_lower = text.lower()
    task_type, matched = _cos_task_type(text_lower)
    level = _cos_level(text, task_type, intent.multi_step, matched)
    understanding_status = _cos_understanding_status(text_lower, intent)
    mode = _cos_mode(task_type, level)
    required_gates, process_template = _cos_required_gates(
        task_type=task_type,
        level=level,
        mode=mode,
        understanding_status=understanding_status,
    )
    task_label = COS_TASK_LABELS.get(task_type, task_type)
    understanding_label = COS_UNDERSTANDING_LABELS.get(understanding_status, understanding_status)
    declaration = f"分类: {task_label} | 级别: {level} | 模式: {mode} | 理解: {understanding_label}"
    substantive = task_type != "pure_discussion" or level in {"L", "XL"}
    return CosGate(
        task_type=task_type,
        level=level,
        mode=mode,
        understanding_status=understanding_status,
        declaration=declaration,
        required_gates=required_gates,
        intent=intent.to_dict(),
        matched_keywords=matched,
        process_template=process_template,
        post_requirements={
            "required": substantive,
            "files": ["docs/memory-index.md", "docs/sprint-board.md"],
            "rule": "POST_MEM and POST_SYNC remain required for substantive delivery; System 1 may simplify coding/review only.",
        },
        truthfulness={
            "requires_evidence": True,
            "rule": "Do not claim completion without file, test, endpoint, or runtime evidence; label unknowns as unproven.",
            "unknown_word": "unproven",
        },
        vague_protocol=_cos_vague_protocol(text_lower, understanding_status),
        multi_agent=_cos_multi_agent(level),
        project_management={
            "health_check_required": level in {"L", "XL"} or "project" in intent.category,
            "rule": "Project manager state should expose next action, blockers, verification status, and memory updates due.",
        },
        trigger=trigger,
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
