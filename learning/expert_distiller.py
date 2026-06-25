"""
learning/expert_distiller.py — 专家救援蒸馏器

把专家救援的成功经验沉淀为知识和技能。
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional

from core.config import Config
from learning.knowledge_base import KnowledgeBase
from learning.reflection import ReflectionEngine
from learning.skill_generator import SkillGenerator


class ExpertDistiller:
    """对比本地失败与专家成功，蒸馏出可复用技能。"""

    def __init__(
        self,
        reflection: ReflectionEngine,
        skill_generator: SkillGenerator,
        knowledge_base: KnowledgeBase,
        config: Optional[Config] = None,
    ):
        self.reflection = reflection
        self.skill_generator = skill_generator
        self.knowledge_base = knowledge_base
        self.cfg = config or Config()
        self.confidence_floor = float(
            self.cfg.get("learning.expert_skill_confidence_floor", 0.75)
        )

    def distill(
        self,
        session_id: Optional[str],
        trajectory: List[Dict[str, Any]],
        skill_seed: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """从救援轨迹中蒸馏知识和技能。"""
        session_id = session_id or "unknown"
        diff = self._compute_diff(trajectory)

        # 1. 反思：本地 vs 专家差值
        insights = self.reflection.reflect_on_rescue(session_id, diff)

        # 2. 合并专家提供的 skill_seed
        if skill_seed:
            seed_insight = {
                "domain": skill_seed.get("domain", diff.get("domain", "general")),
                "rule": skill_seed.get("rule", ""),
                "context": skill_seed.get("context", ""),
                "tags": ["skill", "expert_rescue"],
                "confidence": max(skill_seed.get("confidence", 0.8), self.confidence_floor),
                "source_session": session_id,
            }
            insights.append(seed_insight)

        # 3. 标记来源、提升置信度
        stored_ids = []
        for item in insights:
            tags = list(item.get("tags", []))
            if "expert_rescue" not in tags:
                tags.append("expert_rescue")
            item["tags"] = tags
            item["confidence"] = max(item.get("confidence", 0.5), self.confidence_floor)
            item["source_session"] = session_id
            stored_ids.append(self.knowledge_base.store(item))

        # 4. 生成技能
        skill_names = self.skill_generator.generate(
            session_id=session_id,
            trajectory=trajectory,
            insights=insights,
            source="expert_rescue",
        )

        return {
            "session_id": session_id,
            "insights_count": len(insights),
            "knowledge_ids": stored_ids,
            "skill_names": skill_names,
        }

    def _compute_diff(self, trajectory: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分离本地失败段和专家成功段，计算关键差异。"""
        local_steps = [s for s in trajectory if s.get("source", "local") == "local"]
        expert_steps = [s for s in trajectory if s.get("source") == "expert"]

        failed_local = [s for s in local_steps if not (s.get("observation", {}) or {}).get("ok", True)]
        successful_expert = [s for s in expert_steps if (s.get("observation", {}) or {}).get("ok", True)]

        # 提取最后一个失败动作和最后一个专家成功动作
        last_failure = failed_local[-1] if failed_local else {}
        last_success = successful_expert[-1] if successful_expert else {}

        # 构建差值描述
        failure_tool = (last_failure.get("action") or {}).get("tool", "unknown")
        failure_error = (last_failure.get("observation") or {}).get("error", "未知错误")
        success_tool = (last_success.get("action") or {}).get("tool", "unknown")
        success_action = last_success.get("action", {})

        domain = failure_tool if failure_tool != "unknown" else "general"

        diff_text = f"""本地模型尝试：
- 工具：{failure_tool}
- 结果：失败，{failure_error}

专家救援成功：
- 工具：{success_tool}
- 动作：{success_action}
- 思考：{last_success.get('thought', '')[:300]}

关键差异：
请分析本地模型失败的原因，以及专家成功动作背后的方法论。"""

        return {
            "domain": domain,
            "local_failure": last_failure,
            "expert_success": last_success,
            "diff_text": diff_text,
            "expert_steps": expert_steps,
            "local_steps": local_steps,
        }
