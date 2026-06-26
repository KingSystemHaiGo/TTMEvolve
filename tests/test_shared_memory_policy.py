"""
tests/test_shared_memory_policy.py - multi-agent cold memory policy tests.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.config import Config
from llm.context_budget import ContextBudgetManager
from memory.cold import ColdMemory
from memory.manager import MemoryManager
from memory.shared_policy import SharedMemoryPolicy


def _mock_encoder(texts):
    dim = 8
    vectors = []
    for text in texts:
        vec = np.zeros(dim, dtype=np.float32)
        for ch in text.lower():
            vec[ord(ch) % dim] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        vectors.append(vec)
    return np.array(vectors, dtype=np.float32)


def test_shared_policy_hides_other_agent_private_memory():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp),
            vector_index_config={"enabled": False, "fallback_to_keyword": True},
            encoder=_mock_encoder,
        )
        cold.index(
            {"id": "a-private", "workspace_profile": "coding", "agent_id": "agent-a", "visibility": "private"},
            "shared-boundary private-token",
        )
        cold.index(
            {"id": "a-shared", "workspace_profile": "coding", "agent_id": "agent-a", "visibility": "shared"},
            "shared-boundary shared-token",
        )

        a_hits = cold.search("shared-boundary", workspace_profile="coding", agent_id="agent-a")
        b_hits = cold.search("shared-boundary", workspace_profile="coding", agent_id="agent-b")

        assert {hit["id"] for hit in a_hits} == {"a-private", "a-shared"}
        assert {hit["id"] for hit in b_hits} == {"a-shared"}


def test_shared_policy_can_disable_shared_reads_but_keep_public():
    policy = SharedMemoryPolicy.from_config(
        {"can_read_shared": False, "can_read_public": True},
        agent_id="agent-b",
    )
    assert policy.can_read(
        {"agent_id": "agent-a", "visibility": "shared", "workspace_profile": "docs"},
        "docs",
    ) is False
    assert policy.can_read(
        {"agent_id": "agent-a", "visibility": "public", "workspace_profile": "docs"},
        "docs",
    ) is True


def test_shared_policy_blocks_disallowed_write_profile():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp),
            vector_index_config={
                "enabled": False,
                "shared_memory": {
                    "profiles": {
                        "docs-agent": {"write_profiles": ["docs"]},
                    }
                },
            },
            encoder=_mock_encoder,
        )

        cold.index(
            {"id": "doc", "workspace_profile": "docs", "agent_id": "docs-agent"},
            "allowed docs write",
        )
        try:
            cold.index(
                {"id": "maker", "workspace_profile": "maker", "agent_id": "docs-agent"},
                "blocked maker write",
            )
        except PermissionError as exc:
            assert "cannot index maker" in str(exc)
        else:
            raise AssertionError("expected PermissionError for disallowed write profile")


def test_memory_manager_archives_agent_visibility_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cfg = Config()
        cfg.data = {
            "llm": {"n_ctx": 8192, "reserve_tokens": 256},
            "memory": {"vector_index": {"enabled": False, "fallback_to_keyword": True}},
        }
        cfg._profiles = {}
        manager = MemoryManager(
            project_root=root / "project",
            storage_root=root / "storage",
            skills_dir=root / "skills",
            budget_manager=ContextBudgetManager(n_ctx=8192, reserve_tokens=256),
            config=cfg,
        )

        manager.archive_session(
            "session-a",
            "manager shared-memory handoff",
            workspace_profile="coding",
            agent_id="agent-a",
            visibility="shared",
        )
        hits = manager.recall(
            "shared-memory handoff",
            workspace_profile="coding",
            agent_id="agent-b",
        )

        assert hits[0]["id"] == "session-a"
        assert hits[0]["agent_id"] == "agent-a"
        assert hits[0]["visibility"] == "shared"


if __name__ == "__main__":
    test_shared_policy_hides_other_agent_private_memory()
    test_shared_policy_can_disable_shared_reads_but_keep_public()
    test_shared_policy_blocks_disallowed_write_profile()
    test_memory_manager_archives_agent_visibility_metadata()
    print("\nAll shared memory policy tests passed.")
