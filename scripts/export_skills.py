"""
scripts/export_skills.py — 导出 TTMEvolve canonical skills 到各生态格式

用法：
  python scripts/export_skills.py --format hermes --output ./exported
  python scripts/export_skills.py --format openclaw --output ./exported
  python scripts/export_skills.py --format claude_code --output ./exported
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ecosystem.skill_schema import CanonicalSkill
from ecosystem.hermes_adapter import export_to_hermes
from ecosystem.openclaw_adapter import export_to_openclaw
from ecosystem.claude_code_adapter import export_to_claude_code


EXPORTERS = {
    "hermes": export_to_hermes,
    "openclaw": export_to_openclaw,
    "claude_code": export_to_claude_code,
}


def discover_canonical_skills(skills_dir: Path) -> list:
    skills = []
    if not skills_dir.exists():
        return skills
    for skill_json in skills_dir.rglob("skill.json"):
        try:
            data = json.loads(skill_json.read_text(encoding="utf-8"))
            skill = CanonicalSkill.from_dict(data)
            # 如果存在 skill.py，读取代码
            py_path = skill_json.with_name("skill.py")
            if py_path.exists():
                skill.code = py_path.read_text(encoding="utf-8")
            skills.append(skill)
        except Exception:
            continue
    return skills


def main():
    parser = argparse.ArgumentParser(description="Export TTMEvolve skills")
    parser.add_argument("--format", choices=list(EXPORTERS.keys()), required=True)
    parser.add_argument("--output", default="./exported_skills", help="输出目录")
    parser.add_argument("--skills-dir", default="./storage/skills", help="canonical skill 根目录")
    args = parser.parse_args()

    skills_dir = Path(args.skills_dir).resolve()
    output_dir = Path(args.output).resolve() / args.format
    output_dir.mkdir(parents=True, exist_ok=True)

    skills = discover_canonical_skills(skills_dir)
    exporter = EXPORTERS[args.format]

    for skill in skills:
        skill_dir = output_dir / skill.id
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(exporter(skill), encoding="utf-8")
        if skill.code:
            (skill_dir / "skill.py").write_text(skill.code, encoding="utf-8")

    print(f"[export] 导出 {len(skills)} 个 skills 到 {output_dir}")


if __name__ == "__main__":
    main()
