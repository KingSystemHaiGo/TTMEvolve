"""
tests/test_hot_memory.py — Unit tests for HotMemory summarization.
"""

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from memory.hot import HotMemory


def test_add_turn_within_limit():
    hot = HotMemory(max_turns=6)
    hot.set_system_prompt("system")
    for i in range(4):
        hot.add_turn("user", f"msg{i}")
    ctx = hot.build_context()
    assert len(ctx) == 5  # system + 4 turns
    print("[PASS] test_add_turn_within_limit")


def test_compress_drops_oldest_when_no_summarizer():
    hot = HotMemory(max_turns=3)
    hot.set_system_prompt("system")
    for i in range(5):
        hot.add_turn("user", f"msg{i}")
    ctx = hot.build_context()
    contents = [m["content"] for m in ctx]
    assert "msg0" not in contents
    assert "msg4" in contents
    assert len(ctx) <= 4  # system + max_turns
    print("[PASS] test_compress_drops_oldest_when_no_summarizer")


def test_compress_summarizes_oldest_when_summarizer_present():
    calls = []

    def summarizer(batch):
        calls.append(batch)
        return "summary of " + ",".join(t["content"] for t in batch)

    hot = HotMemory(max_turns=3, batch_size=2, summarize_fn=summarizer)
    hot.set_system_prompt("system")
    for i in range(5):
        hot.add_turn("user", f"msg{i}")
    ctx = hot.build_context()
    contents = [m["content"] for m in ctx]

    assert any("[摘要]" in c for c in contents)
    assert any("summary" in c for c in contents)
    # Oldest raw messages should be gone, but their summary remains.
    assert "msg0" not in contents or "msg1" not in contents
    assert "msg4" in contents
    assert len(calls) >= 1
    print("[PASS] test_compress_summarizes_oldest_when_summarizer_present")


def test_summarize_fn_failure_fallback():
    def bad_summarizer(_batch):
        raise RuntimeError("summarizer failed")

    hot = HotMemory(max_turns=3, batch_size=2, summarize_fn=bad_summarizer)
    hot.set_system_prompt("system")
    for i in range(5):
        hot.add_turn("user", f"msg{i}")
    ctx = hot.build_context()
    contents = [m["content"] for m in ctx]
    # Should fall back to dropping oldest turns.
    assert "msg0" not in contents
    assert "msg4" in contents
    print("[PASS] test_summarize_fn_failure_fallback")


if __name__ == "__main__":
    test_add_turn_within_limit()
    test_compress_drops_oldest_when_no_summarizer()
    test_compress_summarizes_oldest_when_summarizer_present()
    test_summarize_fn_failure_fallback()
    print("\nAll hot_memory tests passed.")
