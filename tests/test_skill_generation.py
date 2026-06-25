"""
tests/test_skill_generation.py — 技能生成链路冒烟测试

验证：Agent 执行一次多步 mock 任务后，学习转化层能成功生成、
验证并注册第一个自生成技能。
"""

from __future__ import annotations
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

# 把项目根加入路径
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.agent import TapMakerAgent
from core.config import Config
from llm.mock_llm import MockLLM
from learning.validator import SkillValidator


def make_test_dirs():
    """创建临时项目与存储目录。"""
    tmp = Path(tempfile.gettempdir()) / f"ttmevolve_test_{uuid.uuid4().hex[:8]}"
    project_root = tmp / "project"
    storage_root = tmp / "storage"
    project_root.mkdir(parents=True)
    storage_root.mkdir(parents=True)
    return project_root, storage_root, tmp


def test_skill_generation_flow():
    project_root, storage_root, tmp = make_test_dirs()
    try:
        # Mock LLM 脚本：先列目录，再结束（保证迭代数 >=2，触发学习层）
        llm = MockLLM(scripted_actions=[
            {"tool": "list_directory", "params": {"path": "."}},
            {"done": True, "output": "已列出目录并生成技能"},
        ])

        agent = TapMakerAgent(
            llm=llm,
            config=Config(str(_PROJECT_ROOT / "config.json")),
            project_root=project_root,
            storage_root=storage_root,
            human_confirm_callback=None,
        )

        result = agent.run("列出项目文件")
        agent.close()

        # 1. 任务成功且迭代数 >=2
        assert result["iteration_count"] >= 2, f"迭代数不足：{result['iteration_count']}"

        # 2. 生成了技能文件
        generated_dir = project_root / "skills" / "generated"
        assert generated_dir.exists(), "未生成 skills/generated 目录"
        py_files = list(generated_dir.glob("gen_*.py"))
        json_files = list(generated_dir.glob("gen_*.json"))
        assert len(py_files) >= 1, "未生成 .py 技能文件"
        assert len(json_files) >= 1, "未生成 .json 技能规格文件"

        # 3. 技能代码能通过验证
        validator = SkillValidator()
        code = py_files[0].read_text(encoding="utf-8")
        assert validator.validate(code), "生成的技能代码未通过安全验证"

        # 4. 技能可以执行
        exec_result = validator.run_skill(code, "hello")
        assert exec_result.get("ok"), f"技能执行失败：{exec_result.get('error')}"

        # 5. ToolRegistry 重新加载后能发现该技能，并且 Executor 能执行它
        fresh_agent = TapMakerAgent(
            llm=MockLLM(),
            config=Config(str(_PROJECT_ROOT / "config.json")),
            project_root=project_root,
            storage_root=storage_root / "second",
            human_confirm_callback=None,
        )
        skill_names = [t["name"] for t in fresh_agent.tools.list_tools()]
        gen_name = next((n for n in skill_names if n.startswith("gen_")), None)
        assert gen_name, f"未在工具列表中发现生成技能：{skill_names}"

        exec_result = fresh_agent.executor.propose_action("test", gen_name, {"input": "hello"})
        assert exec_result.get("ok"), f"通过 Executor 执行生成技能失败：{exec_result.get('error')}"
        fresh_agent.close()

        print("[PASS] 技能生成链路冒烟测试通过")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_skill_generation_flow()
