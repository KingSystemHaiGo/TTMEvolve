"""
tests/test_cross_ecosystem.py — 跨生态兼容测试
"""

from __future__ import annotations
import shutil
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ecosystem.skill_schema import CanonicalSkill
from ecosystem.hermes_adapter import export_to_hermes, load_hermes_skill
from ecosystem.openclaw_adapter import export_to_openclaw, load_openclaw_skill
from ecosystem.claude_code_adapter import export_to_claude_code, load_claude_code_skill


def test_hermes_roundtrip():
    skill = CanonicalSkill(
        id="test_skill",
        name="test_skill",
        version="1.0",
        description="A test skill",
        parameters={"type": "object", "properties": {}},
        tags=["test"],
        body="Usage: run(input)",
    )
    md = export_to_hermes(skill)
    tmp = Path(tempfile.mkdtemp())
    try:
        skill_file = tmp / "SKILL.md"
        skill_file.write_text(md, encoding="utf-8")
        loaded = load_hermes_skill(skill_file)
        assert loaded is not None
        assert loaded.id == skill.id
        assert loaded.description == skill.description
        print("[PASS] hermes roundtrip")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_openclaw_roundtrip():
    skill = CanonicalSkill(
        id="oc_skill",
        name="oc_skill",
        version="1.0",
        description="OpenClaw skill",
        parameters={"type": "object", "properties": {}},
        tags=["test"],
        body="Run me",
    )
    md = export_to_openclaw(skill)
    tmp = Path(tempfile.mkdtemp())
    try:
        skill_file = tmp / "SKILL.md"
        skill_file.write_text(md, encoding="utf-8")
        loaded = load_openclaw_skill(skill_file)
        assert loaded is not None
        assert loaded.id == skill.id
        print("[PASS] openclaw roundtrip")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_claude_code_roundtrip():
    skill = CanonicalSkill(
        id="cc_skill",
        name="cc_skill",
        version="1.0",
        description="Claude Code skill",
        parameters={"type": "object", "properties": {}},
        tags=["test"],
        body="Do this",
    )
    md = export_to_claude_code(skill)
    tmp = Path(tempfile.mkdtemp())
    try:
        skill_dir = tmp / "cc_skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(md, encoding="utf-8")
        loaded = load_claude_code_skill(skill_file)
        assert loaded is not None
        assert loaded.id == skill.id
        print("[PASS] claude code roundtrip")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_hermes_roundtrip()
    test_openclaw_roundtrip()
    test_claude_code_roundtrip()
    print("[PASS] all cross ecosystem tests")
