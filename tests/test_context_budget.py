"""
tests/test_context_budget.py — Unit tests for ContextBudgetManager.
"""

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from llm.context_budget import ContextBudgetManager, BudgetStats


def test_estimate_tokens_with_tokenizer():
    mgr = ContextBudgetManager(n_ctx=1024, reserve_tokens=64, tokenizer=lambda t: len(t) // 2)
    assert mgr.estimate_tokens("abcd") == 2
    print("[PASS] test_estimate_tokens_with_tokenizer")


def test_estimate_tokens_fallback():
    mgr = ContextBudgetManager(n_ctx=1024, reserve_tokens=64)
    # fallback is len(text) // 4
    assert mgr.estimate_tokens("abcdefgh") == 2
    print("[PASS] test_estimate_tokens_fallback")


def test_estimate_tokens_reports_cache_stats():
    mgr = ContextBudgetManager(n_ctx=1024, reserve_tokens=64)
    text = "cached text " * 20
    assert mgr.estimate_tokens(text) > 0
    assert mgr.estimate_tokens(text) > 0
    stats = mgr.cache_stats()
    assert stats["token_cache_hits"] >= 1
    assert stats["token_cache_misses"] >= 1
    assert stats["token_cache_size"] >= 1
    print("[PASS] test_estimate_tokens_reports_cache_stats")


def test_fit_within_budget():
    mgr = ContextBudgetManager(n_ctx=100, reserve_tokens=10, tokenizer=len)
    user, stats = mgr.fit(system="sys", user="small", max_tokens=10)
    assert user == "small"
    assert stats.token_count == 8  # 3 + 5
    assert stats.context_window_ratio == (8 + 10 + 10) / 100
    print("[PASS] test_fit_within_budget")


def test_fit_truncates_user_top():
    mgr = ContextBudgetManager(n_ctx=100, reserve_tokens=10, tokenizer=len)
    # budget = 100 - 10 - 10 = 80; system takes 3, so user can be at most 77.
    big = "A" * 40 + "B" * 60  # 100 chars
    user, stats = mgr.fit(system="sys", user=big, max_tokens=10)
    # Budget allows 77 chars of user; top 23 chars (A's) should be dropped.
    assert user.startswith("A" * 17)
    assert user.endswith("B" * 60)
    assert stats.token_count <= 80
    print("[PASS] test_fit_truncates_user_top")


def test_fit_parts_respects_priority():
    mgr = ContextBudgetManager(n_ctx=100, reserve_tokens=10, tokenizer=len)
    # budget = 80. system=10, so user budget=70.
    # parts: high=30, medium=30, low=30 -> total 90, drop low.
    parts = [
        ("H" * 30, 3),
        ("M" * 30, 2),
        ("L" * 30, 1),
    ]
    text, stats = mgr.fit_parts("SYS" * 4, parts, max_tokens=10)
    assert "H" * 30 in text
    assert "M" * 30 in text
    assert "L" * 30 not in text
    assert stats.token_count <= 80
    assert stats.compression_applied is True
    assert stats.dropped_parts == 1
    print("[PASS] test_fit_parts_respects_priority")


def test_fit_parts_marks_truncation():
    mgr = ContextBudgetManager(n_ctx=80, reserve_tokens=10, tokenizer=len)
    text, stats = mgr.fit_parts("sys", [("A" * 200, 5)], max_tokens=10)
    assert len(text) <= 57
    assert stats.compression_applied is True
    assert stats.truncated_chars > 0
    assert stats.token_count <= 60
    print("[PASS] test_fit_parts_marks_truncation")


def test_slice_trajectory():
    trajectory = [
        {"iteration": 0, "thought": "t0", "action": {"tool": "a"}, "observation": {"ok": True}},
        {"iteration": 1, "thought": "t1", "action": {"tool": "b"}, "observation": {"ok": False}},
        {"iteration": 2, "thought": "t2", "action": {"tool": "c"}, "observation": {"ok": True}},
    ]
    mgr = ContextBudgetManager(n_ctx=1024, reserve_tokens=64)
    out = mgr.slice_trajectory(trajectory, max_steps=2, max_chars_per_step=50)
    assert "Step 0" not in out
    assert "Step 1" in out
    assert "Step 2" in out
    print("[PASS] test_slice_trajectory")


def test_slice_trajectory_omitted_count():
    trajectory = [{"iteration": i, "thought": f"t{i}", "action": {}, "observation": {}} for i in range(10)]
    mgr = ContextBudgetManager(n_ctx=1024, reserve_tokens=64)
    out = mgr.slice_trajectory(trajectory, max_steps=3, max_chars_per_step=10)
    assert "[omitted 7 earlier low-importance steps]" in out
    print("[PASS] test_slice_trajectory_omitted_count")


def test_slice_trajectory_preserves_important_old_steps():
    trajectory = [
        {"iteration": 0, "thought": "old fail", "action": {"tool": "read_file"}, "observation": {"ok": False}},
        {"iteration": 1, "thought": "boring", "action": {"tool": "a"}, "observation": {"ok": True}},
        {"iteration": 2, "thought": "recent", "action": {"tool": "b"}, "observation": {"ok": True}},
        {"iteration": 3, "thought": "latest", "action": {"tool": "c"}, "observation": {"ok": True}},
    ]
    mgr = ContextBudgetManager(n_ctx=1024, reserve_tokens=64)
    out = mgr.slice_trajectory(trajectory, max_steps=2, max_chars_per_step=50)
    assert "Step 0" in out
    assert "Step 1" not in out
    assert "Step 2" in out
    assert "Step 3" in out
    print("[PASS] test_slice_trajectory_preserves_important_old_steps")


if __name__ == "__main__":
    test_estimate_tokens_with_tokenizer()
    test_estimate_tokens_fallback()
    test_estimate_tokens_reports_cache_stats()
    test_fit_within_budget()
    test_fit_truncates_user_top()
    test_fit_parts_respects_priority()
    test_fit_parts_marks_truncation()
    test_slice_trajectory()
    test_slice_trajectory_omitted_count()
    test_slice_trajectory_preserves_important_old_steps()
    print("\nAll context_budget tests passed.")
