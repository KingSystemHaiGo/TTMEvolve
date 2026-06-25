"""
tests/test_expert_protocol.py — 专家救援协议测试
"""

from __future__ import annotations
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm.expert_protocol import RescueAction, RescueContext, EXPERT_RESCUE_PROMPT


def test_rescue_action_from_dict():
    data = {
        "mode": "thought_injection",
        "thought": "先检查文件是否存在",
        "skill_seed": {"domain": "file", "rule": "检查存在性"},
    }
    action = RescueAction.from_dict(data)
    assert action.mode == "thought_injection"
    assert action.thought == "先检查文件是否存在"
    assert action.skill_seed["domain"] == "file"
    print("[PASS] RescueAction.from_dict thought_injection")


def test_rescue_action_direct_action():
    data = {
        "mode": "direct_action",
        "action": {"tool": "read_file", "params": {"path": "test.txt"}},
    }
    action = RescueAction.from_dict(data)
    assert action.mode == "direct_action"
    assert action.action["tool"] == "read_file"
    print("[PASS] RescueAction.from_dict direct_action")


def test_rescue_action_loop_takeover():
    data = {
        "mode": "loop_takeover",
        "takeover_steps": 5,
    }
    action = RescueAction.from_dict(data)
    assert action.mode == "loop_takeover"
    assert action.takeover_steps == 5
    print("[PASS] RescueAction.from_dict loop_takeover")


def test_rescue_context_build():
    trajectory = [
        {
            "source": "local",
            "thought": "读取文件",
            "action": {"tool": "read_file", "params": {"path": "a.txt"}},
            "observation": {"ok": False, "error": "文件不存在"},
        },
        {
            "source": "local",
            "thought": "重试",
            "action": {"tool": "read_file", "params": {"path": "a.txt"}},
            "observation": {"ok": False, "error": "文件不存在"},
        },
    ]
    ctx = RescueContext.build(
        task="读取 a.txt",
        trajectory=trajectory,
        health_state={"status": "degraded"},
        tools_description="read_file(path)",
        warm_context="无",
        max_step_text_len=50,
    )
    assert ctx.task == "读取 a.txt"
    assert ctx.consecutive_errors == 2
    assert ctx.health_status == "degraded"
    assert "文件不存在" in ctx.error_summary
    # 长文本应被截断
    long_text = "x" * 100
    trajectory[0]["thought"] = long_text
    ctx2 = RescueContext.build(
        task="t",
        trajectory=trajectory,
        health_state=None,
        tools_description="",
        warm_context="",
        max_step_text_len=30,
    )
    assert "[截断]" in ctx2.truncated_trajectory
    print("[PASS] RescueContext.build")


def test_prompt_format():
    ctx = RescueContext(
        task="任务",
        truncated_trajectory="轨迹",
        error_summary="错误",
        tools_description="工具",
        warm_context="经验",
        iteration_count=5,
        consecutive_errors=2,
        health_status="degraded",
    )
    prompt = EXPERT_RESCUE_PROMPT.format(**ctx.to_prompt_kwargs())
    assert "任务" in prompt
    assert "轨迹" in prompt
    assert "高级专家" in prompt
    print("[PASS] EXPERT_RESCUE_PROMPT format")


if __name__ == "__main__":
    test_rescue_action_from_dict()
    test_rescue_action_direct_action()
    test_rescue_action_loop_takeover()
    test_rescue_context_build()
    test_prompt_format()
    print("[PASS] all expert protocol tests")
