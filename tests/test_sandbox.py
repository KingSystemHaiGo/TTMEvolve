"""
tests/test_sandbox.py — 沙箱校验测试
"""

from __future__ import annotations
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.sandbox import Sandbox, SandboxMode


def test_read_only_blocks_write():
    sb = Sandbox(_PROJECT_ROOT, SandboxMode.READ_ONLY)
    result = sb.validate("modify_file", {"path": "test.txt", "content": "x"})
    assert not result["allowed"], result
    print("[PASS] read-only blocks write")


def test_workspace_allows_git():
    sb = Sandbox(_PROJECT_ROOT, SandboxMode.WORKSPACE_WRITE)
    result = sb.validate("execute_shell", {"command": "git status"})
    assert result["allowed"], result
    print("[PASS] workspace-write allows git")


def test_read_only_allows_project_status():
    sb = Sandbox(_PROJECT_ROOT, SandboxMode.READ_ONLY)
    result = sb.validate("project_status", {})
    assert result["allowed"], result
    print("[PASS] read-only allows project status")


def test_path_escape_blocked():
    sb = Sandbox(_PROJECT_ROOT, SandboxMode.WORKSPACE_WRITE)
    result = sb.validate("read_file", {"path": "../../../etc/passwd"})
    assert not result["allowed"], result
    print("[PASS] path escape blocked")


def test_dangerous_command_blocked():
    sb = Sandbox(_PROJECT_ROOT, SandboxMode.DANGER_FULL_ACCESS)
    result = sb.validate("execute_shell", {"command": "rm -rf /"})
    assert not result["allowed"], result
    print("[PASS] dangerous command blocked even in danger mode")


if __name__ == "__main__":
    test_read_only_blocks_write()
    test_read_only_allows_project_status()
    test_workspace_allows_git()
    test_path_escape_blocked()
    test_dangerous_command_blocked()
    print("[PASS] all sandbox tests")
