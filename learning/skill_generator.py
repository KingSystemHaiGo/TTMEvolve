"""
learning/skill_generator.py — 技能生成器

把高频成功模式转化为可复用工具（skills/generated/*.py）。
新技能必须经过验证才能注册。
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from llm.interface import LLMInterface


class SkillGenerator:
    """根据反思结果自动生成技能文件。"""

    def __init__(
        self,
        llm: LLMInterface,
        skills_dir: Path,
        validator: Optional[Any] = None,
        registry: Optional[Any] = None,
    ):
        self.llm = llm
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.generated_dir = self.skills_dir / "generated"
        self.generated_dir.mkdir(parents=True, exist_ok=True)
        self.validator = validator
        self.registry = registry

    def generate(
        self,
        session_id: str,
        trajectory: List[Dict[str, Any]],
        insights: List[Dict[str, Any]],
        source: str = "skill_generator",
    ) -> List[str]:
        """生成技能，返回生成的技能名列表。"""
        generated = []
        for insight in insights:
            # 只有高置信度、可操作的规则才生成技能
            if insight.get("confidence", 0) < 0.7:
                continue
            if "skill" not in insight.get("tags", []):
                continue

            skill_name = self._skill_name(insight.get("domain", "general"))
            spec = self._build_skill_spec(skill_name, insight, session_id)
            code = self._generate_skill_code(skill_name, insight)

            if self.validator and not self.validator.validate(code):
                continue

            self._write_skill(skill_name, spec, code)
            if self.registry:
                self.registry.register(
                    resource_id=skill_name,
                    resource_type="skill",
                    content=code,
                    source=f"{source}:{session_id}",
                    metadata={"spec": spec},
                )
            generated.append(skill_name)
        return generated

    def _skill_name(self, domain: str) -> str:
        import re, time
        safe = re.sub(r"[^\w一-鿿]+", "_", domain).strip("_") or "skill"
        return f"gen_{safe}_{int(time.time())}"

    def _build_skill_spec(
        self,
        skill_name: str,
        insight: Dict[str, Any],
        session_id: str,
    ) -> Dict[str, Any]:
        return {
            "name": skill_name,
            "description": insight.get("rule", ""),
            "source_session": session_id,
            "domain": insight.get("domain", "general"),
            "parameters": {
                "type": "object",
                "properties": {
                    "input": {"type": "string", "description": "技能输入"},
                },
            },
        }

    def _generate_skill_code(self, skill_name: str, insight: Dict[str, Any]) -> str:
        prompt = f"""
根据以下反思规则，生成一个 Python 函数 `run(input: str) -> dict`：
规则：{insight.get('rule', '')}
上下文：{insight.get('context', '')}

要求：
- 函数签名固定：def run(input: str) -> dict:
- 返回 dict 必须包含 "ok" 字段
- 代码自包含，不依赖外部状态
- 只输出代码，不要解释
"""
        return self.llm.generate_code(prompt)

    def _write_skill(
        self,
        skill_name: str,
        spec: Dict[str, Any],
        code: str,
    ) -> None:
        """写入 canonical skill 格式：skills/generated/{name}/{version}/skill.json + skill.py。"""
        import re
        safe_name = re.sub(r"[^\w\-]+", "_", skill_name).strip("_") or "skill"
        version = "v1"
        skill_dir = self.generated_dir / safe_name / version
        skill_dir.mkdir(parents=True, exist_ok=True)
        spec["version"] = version
        spec["id"] = safe_name
        (skill_dir / "skill.json").write_text(
            json.dumps(spec, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (skill_dir / "skill.py").write_text(code, encoding="utf-8")
        # 兼容性：同时保留旧格式入口
        (self.generated_dir / f"{skill_name}.json").write_text(
            json.dumps(spec, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (self.generated_dir / f"{skill_name}.py").write_text(code, encoding="utf-8")
