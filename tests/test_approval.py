"""
tests/test_approval.py — 审批策略测试
"""

from __future__ import annotations
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.approval import ApprovalEngine, ApprovalPolicy


def test_never_auto_approves():
    engine = ApprovalEngine(ApprovalPolicy.NEVER)
    result = engine.check("modify_file", {"path": "x"})
    assert result["allowed"], result
    print("[PASS] never policy auto-approves")


def test_always_asks():
    called = []
    engine = ApprovalEngine(
        ApprovalPolicy.ALWAYS,
        human_confirm_callback=lambda msg: (called.append(msg) or True),
    )
    result = engine.check("read_file", {"path": "x"})
    assert result["allowed"], result
    assert len(called) == 1, called
    print("[PASS] always policy asks for read")


def test_on_request_high_risk():
    called = []
    engine = ApprovalEngine(
        ApprovalPolicy.ON_REQUEST,
        human_confirm_callback=lambda msg: (called.append(msg) or True),
    )
    result = engine.check("execute_shell", {"command": "git status"})
    assert result["allowed"], result
    assert len(called) == 1, called
    print("[PASS] on-request policy asks for high risk")


def test_on_request_low_risk_skips():
    called = []
    engine = ApprovalEngine(
        ApprovalPolicy.ON_REQUEST,
        human_confirm_callback=lambda msg: (called.append(msg) or True),
    )
    result = engine.check("read_file", {"path": "x"})
    assert result["allowed"], result
    assert len(called) == 0, called
    print("[PASS] on-request policy skips low risk")


if __name__ == "__main__":
    test_never_auto_approves()
    test_always_asks()
    test_on_request_high_risk()
    test_on_request_low_risk_skips()
    print("[PASS] all approval tests")
