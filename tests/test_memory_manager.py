"""
tests/test_memory_manager.py — Unit tests for MemoryManager context orchestration.
"""

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import Config
from llm.context_budget import ContextBudgetManager
from memory.manager import MemoryManager


def _make_manager(n_ctx: int = 1024) -> MemoryManager:
    cfg = Config()
    cfg.data = {"llm": {"n_ctx": n_ctx, "reserve_tokens": 64, "max_history_steps": 6}}
    cfg._profiles = {}
    budget = ContextBudgetManager(n_ctx=n_ctx, reserve_tokens=64, tokenizer=len)
    return MemoryManager(
        project_root=Path(ROOT),
        storage_root=Path(ROOT) / "storage",
        skills_dir=Path(ROOT) / "skills",
        budget_manager=budget,
        config=cfg,
    )


def test_prepare_task_context():
    mgr = _make_manager()
    ctx = mgr.prepare_task_context(
        system_prompt="system",
        task="task",
        warm_items=["skill:not_exist", "doc:not_exist.md", "raw warm item"],
    )
    roles = [m["role"] for m in ctx]
    assert roles[0] == "system"
    assert "user" in roles
    assert any("[Warm Memory]" in m.get("content", "") for m in ctx)
    print("[PASS] test_prepare_task_context")


def test_prepare_think_payload_prioritizes_task():
    mgr = _make_manager(n_ctx=1024)
    mgr.set_system_prompt("system")
    trajectory = [
        {"iteration": i, "thought": f"t{i}", "action": {"tool": "a"}, "observation": {"ok": True}}
        for i in range(3)
    ]
    text, stats = mgr.prepare_think_payload(
        task="my task",
        context="context info",
        trajectory=trajectory,
        tools_description="tools",
        max_tokens=64,
    )
    assert "my task" in text
    assert "tools" in text
    assert stats.token_count <= 1024 - 64 - 64
    assert stats.context_build_ms >= 0
    assert stats.token_cache_misses >= 0
    assert stats.agents_md_hits >= 0
    assert stats.cold_recall_hits >= 0
    print("[PASS] test_prepare_think_payload_prioritizes_task")


def test_prepare_think_payload_keeps_trajectory():
    mgr = _make_manager(n_ctx=1024)
    mgr.set_system_prompt("system")
    trajectory = [
        {"iteration": 0, "thought": "think", "action": {"tool": "read_file"}, "observation": {"ok": True}},
    ]
    text, stats = mgr.prepare_think_payload(
        task="task",
        context="context",
        trajectory=trajectory,
        tools_description="tools",
        max_tokens=64,
    )
    assert "Step 0" in text or "read_file" in text
    print("[PASS] test_prepare_think_payload_keeps_trajectory")


def test_prepare_think_payload_drops_trajectory_when_tight():
    # Very small context; task/tools must survive, trajectory should be dropped.
    mgr = _make_manager(n_ctx=200)
    mgr.set_system_prompt("system")  # 6 tokens
    trajectory = [
        {"iteration": i, "thought": "x" * 50, "action": {"tool": "a"}, "observation": {"ok": True}}
        for i in range(10)
    ]
    text, stats = mgr.prepare_think_payload(
        task="important task",
        context="",
        trajectory=trajectory,
        tools_description="tools",
        max_tokens=32,
    )
    assert "important task" in text
    assert "tools" in text
    assert "Step" not in text
    assert stats.token_count <= 200 - 64 - 32
    assert stats.compression_applied is True
    assert stats.dropped_parts > 0
    print("[PASS] test_prepare_think_payload_drops_trajectory_when_tight")


if __name__ == "__main__":
    test_prepare_task_context()
    test_prepare_think_payload_prioritizes_task()
    test_prepare_think_payload_keeps_trajectory()
    test_prepare_think_payload_drops_trajectory_when_tight()
    print("\nAll memory_manager tests passed.")
