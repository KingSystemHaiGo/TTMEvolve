"""
learning/validator.py — 技能验证门

新技能必须在隔离环境中通过测试才能注册。
"""

from __future__ import annotations
from typing import Any, Dict
import ast
import sys


class SkillValidator:
    """验证自动生成的技能代码是否安全。"""

    def validate(self, code: str) -> bool:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return False

        # 禁止导入敏感模块
        banned = {"os", "sys", "subprocess", "shutil", "socket", "requests"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    mod = alias.name.split(".")[0]
                    if mod in banned:
                        return False

        # 检查是否有 run 函数
        has_run = any(
            isinstance(n, ast.FunctionDef) and n.name == "run"
            for n in ast.walk(tree)
        )
        return has_run

    def run_skill(self, code: str, test_input: str) -> Dict[str, Any]:
        """在受限命名空间中执行技能代码。"""
        namespace: Dict[str, Any] = {"__builtins__": {}}
        try:
            exec(code, namespace)
            run = namespace.get("run")
            if not callable(run):
                return {"ok": False, "error": "技能缺少 run 函数"}
            return run(test_input)
        except Exception as e:
            return {"ok": False, "error": str(e)}
